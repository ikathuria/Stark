import asyncio
import base64
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

import voice

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Stark")
executor = ThreadPoolExecutor(max_workers=4)

_loop: asyncio.AbstractEventLoop | None = None


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
_user_name = os.getenv("STARK_USER_NAME", "")

SYSTEM_PROMPT = (
    f"You are Stark, a sharp, witty voice assistant built for a developer"
    + (f" named {_user_name}" if _user_name else "")
    + ". Keep responses concise and conversational — you're being spoken aloud. "
    "No markdown, no bullet points, no code blocks in your replies. "
    "Just clear, direct spoken English. Be helpful but not sycophantic."
)


def _claude_call(text: str) -> str:
    message = _anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    return message.content[0].text


async def _get_reply(text: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _claude_call, text)


async def _get_tts(text: str) -> tuple[bytes, str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, voice.speak, text)


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
        keyboard.wait()  # block to keep the hook alive
    except ImportError:
        logger.warning("keyboard library not available — hotkey disabled")
    except Exception as e:
        logger.warning("Could not register hotkey '%s': %s", hotkey, e)


@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_event_loop()
    threading.Thread(target=_setup_hotkey, daemon=True).start()


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "frontend" / "index.html")


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


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
                reply = await _get_reply(text)
                logger.info("Reply: %s", reply)

                audio_bytes, audio_format = await _get_tts(reply)
                audio_b64 = base64.b64encode(audio_bytes).decode()

                await ws.send_json(
                    {
                        "type": "response",
                        "text": reply,
                        "audio": audio_b64,
                        "audio_format": audio_format,
                    }
                )
            except Exception as e:
                logger.error("Error processing transcript: %s", e, exc_info=True)
                await ws.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        manager.disconnect(ws)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
