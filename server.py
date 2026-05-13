import asyncio
import base64
import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

import memory
import voice

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Stark")
executor = ThreadPoolExecutor(max_workers=4)

_loop: asyncio.AbstractEventLoop | None = None

_user_name = os.getenv("STARK_USER_NAME", "")

# ── Intent detection patterns ─────────────────────────────────────────────────
_RE_REMEMBER = re.compile(
    r"^(hey\s+stark[,\s]+)?(please\s+)?"
    r"(remember|save|note|keep in mind)\s+(that\s+|this[:\s]+)?(.+)",
    re.I | re.S,
)
_RE_FORGET = re.compile(
    r"^(hey\s+stark[,\s]+)?(please\s+)?"
    r"(forget|delete|remove|erase)\s+(about\s+|that\s+)?(.+)",
    re.I | re.S,
)


# ── WebSocket connection manager ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        logger.info("Client connected. Total: %d", len(self.active))

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        logger.info("Client disconnected. Total: %d", len(self.active))

    async def broadcast(self, message: dict):
        dead: set[WebSocket] = set()
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.active -= dead


manager = ConnectionManager()
_anthropic = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ── Prompt helpers ────────────────────────────────────────────────────────────
_BASE_SYSTEM = (
    "You are Stark, a sharp, witty voice assistant built for a developer"
    + (f" named {_user_name}" if _user_name else "")
    + ". Keep responses concise and conversational — you're being spoken aloud. "
    "No markdown, no bullet points, no code blocks in your replies. "
    "Just clear, direct spoken English. Be helpful but not sycophantic."
)


def _build_system(memories: list[dict]) -> str:
    if not memories:
        return _BASE_SYSTEM
    mem_lines = "\n".join(f"- {m['key']}: {m['value']}" for m in memories)
    return (
        _BASE_SYSTEM
        + f"\n\nRelevant memories from previous sessions:\n{mem_lines}"
    )


# ── Claude helpers ────────────────────────────────────────────────────────────
def _claude(text: str, system: str, max_tokens: int = 512) -> str:
    msg = _anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": text}],
    )
    return msg.content[0].text


async def _get_reply(text: str, system: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _claude, text, system, 512)


async def _get_tts(text: str) -> tuple[bytes, str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, voice.speak, text)


async def _send_spoken(ws: WebSocket, text: str) -> None:
    """Synthesise text, send it over WebSocket, log it."""
    logger.info("Response: %s", text)
    audio_bytes, audio_format = await _get_tts(text)
    await ws.send_json(
        {
            "type": "response",
            "text": text,
            "audio": base64.b64encode(audio_bytes).decode(),
            "audio_format": audio_format,
        }
    )


# ── Memory command handling ───────────────────────────────────────────────────
async def _handle_remember(ws: WebSocket, raw_content: str) -> None:
    """Extract key/value with Claude and persist the memory."""
    extract_system = (
        "You are a memory extraction assistant. "
        "Given a statement the user wants to remember, extract a short topic key "
        "and the fact to remember. Return ONLY valid JSON in this exact shape: "
        '{"key": "short topic label", "value": "the fact"}\n'
        "Examples:\n"
        '  "I use Next.js for my portfolio" → {"key": "portfolio tech stack", "value": "uses Next.js"}\n'
        '  "my dog is called Biscuit" → {"key": "dog name", "value": "Biscuit"}\n'
        '  "the API key lives in .env" → {"key": "API key location", "value": "stored in .env"}'
    )
    loop = asyncio.get_event_loop()
    raw_json = await loop.run_in_executor(
        executor, _claude, raw_content, extract_system, 100
    )

    try:
        # Tolerate ```json ... ``` fences
        clean = re.sub(r"```[a-z]*\n?|\n?```", "", raw_json).strip()
        parsed = json.loads(clean)
        key = str(parsed["key"]).strip()
        value = str(parsed["value"]).strip()
    except Exception as e:
        logger.warning("Memory extraction parse failed: %s — raw: %s", e, raw_json)
        await _send_spoken(ws, "Sorry, I couldn't figure out what to remember there.")
        return

    await loop.run_in_executor(executor, memory.save, key, value)
    logger.info("Memory saved — key: %r  value: %r", key, value)
    await _send_spoken(ws, f"Got it. I'll remember that {value}.")


async def _handle_forget(ws: WebSocket, query: str) -> None:
    """Delete the best-matching memory and confirm, or say not found."""
    loop = asyncio.get_event_loop()
    deleted = await loop.run_in_executor(executor, memory.delete_matching, query)

    if deleted:
        logger.info("Memory deleted — key: %r", deleted["key"])
        await _send_spoken(ws, f"Done. I've forgotten about {deleted['key']}.")
    else:
        await _send_spoken(ws, "I don't have anything stored about that.")


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()

            if data.get("type") != "transcript":
                continue

            text = data.get("text", "").strip()
            if not text:
                continue

            logger.info("Transcript: %s", text)

            try:
                # ── Check for remember intent ──────────────────────────────
                m = _RE_REMEMBER.match(text)
                if m:
                    await _handle_remember(ws, m.group(5).strip())
                    continue

                # ── Check for forget intent ────────────────────────────────
                m = _RE_FORGET.match(text)
                if m:
                    await _handle_forget(ws, m.group(5).strip())
                    continue

                # ── Normal conversation with memory injection ──────────────
                loop = asyncio.get_event_loop()
                recent_mems = await loop.run_in_executor(
                    executor, memory.recall, text, 5
                )
                system = _build_system(recent_mems)
                reply = await _get_reply(text, system)
                await _send_spoken(ws, reply)

            except Exception as e:
                logger.error("Error processing transcript: %s", e, exc_info=True)
                await ws.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        manager.disconnect(ws)


# ── Hotkey setup ──────────────────────────────────────────────────────────────
def _setup_hotkey():
    hotkey = os.getenv("STARK_HOTKEY", "ctrl+shift+s")
    try:
        import keyboard

        def _on_hotkey():
            if _loop:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({"type": "start_listening"}), _loop
                )

        keyboard.add_hotkey(hotkey, _on_hotkey)
        logger.info("Hotkey registered: %s", hotkey)
        keyboard.wait()
    except ImportError:
        logger.warning("keyboard library not available — hotkey disabled")
    except Exception as e:
        logger.warning("Could not register hotkey '%s': %s", hotkey, e)


@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_event_loop()
    threading.Thread(target=_setup_hotkey, daemon=True).start()


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "frontend" / "index.html")


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


# ── Dev entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
