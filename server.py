"""Stark — FastAPI server.

WebSocket /ws handles the full voice loop:
  transcript → intent detection → Claude Haiku / memory / Claude Code → TTS → audio
"""

import asyncio
import base64
import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

import claude_runner
import computer
import memory
import planner as planning
import projects
import voice

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Stark")
executor = ThreadPoolExecutor(max_workers=4)

_loop: asyncio.AbstractEventLoop | None = None
_user_name = os.getenv("STARK_USER_NAME", "")


# ─────────────────────────── Intent patterns ──────────────────────────────────

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
_RE_CODE = re.compile(
    r"^(hey\s+stark[,\s]+)?"
    r"(work on|continue( working on)?|start|code on|launch|resume)\s+"
    r"(my\s+)?(.+)",
    re.I | re.S,
)
_RE_REGISTER = re.compile(
    r"^(hey\s+stark[,\s]+)?"
    r"(register|add)\s+(project\s+)?(?P<name>.+?)\s+at\s+(?P<path>.+)",
    re.I | re.S,
)
_RE_LIST_PROJECTS = re.compile(
    r"(list|show)\s+(my\s+)?(project|repo)s?"
    r"|what (project|repo)s"
    r"|which (project|repo)s",
    re.I,
)
_RE_YES = re.compile(r"^(yes|yeah|yep|sure|ok|okay|go ahead|do it|confirm|sounds good)([\s,\.\!].*)?$", re.I)
_RE_NO  = re.compile(r"^(no|nope|cancel|stop|abort|never mind|don.?t)([\s,\.\!].*)?$", re.I)
_RE_OPEN_APP = re.compile(
    r"^(hey\s+stark[,\s]+)?(please\s+)?"
    r"(open|launch|start|run)\s+(?P<app>.+)",
    re.I,
)
_RE_SCREEN = re.compile(
    r"(what('?s| is)( on)? (my )?screen|what (can|do) (you |i )?see|"
    r"describe (my |the )?screen|read (my |the )?screen)",
    re.I,
)
_RE_BRIEF = re.compile(
    r"(brief( me)?|what am i working on|morning briefing|"
    r"what('?s| is) (my |the )?status|what (do I|should I) work on)",
    re.I,
)
_RE_PLAN_TRIGGER = re.compile(
    r"\b(i have (a |an )?(new )?idea|let'?s plan|new project|plan (a |an |something|this)|"
    r"i want to build|i('?m| am) building|help me plan)\b",
    re.I,
)


# ─────────────────────────── Connection manager ───────────────────────────────

@dataclass
class PendingSpawn:
    project_name: str
    repo_path: str
    instruction: str


class ConnectionManager:
    def __init__(self):
        self.active: set[WebSocket] = set()
        self._pending: dict[int, PendingSpawn] = {}          # keyed by id(ws)
        self._planning: dict[int, planning.PlanningSession] = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        logger.info("Client connected. Total: %d", len(self.active))

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        self._pending.pop(id(ws), None)
        self._planning.pop(id(ws), None)
        logger.info("Client disconnected. Total: %d", len(self.active))

    async def broadcast(self, message: dict):
        dead: set[WebSocket] = set()
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.active -= dead

    def set_pending(self, ws: WebSocket, spawn: PendingSpawn):
        self._pending[id(ws)] = spawn

    def get_pending(self, ws: WebSocket) -> PendingSpawn | None:
        return self._pending.get(id(ws))

    def clear_pending(self, ws: WebSocket):
        self._pending.pop(id(ws), None)

    def start_planning(self, ws: WebSocket) -> planning.PlanningSession:
        session = planning.PlanningSession()
        self._planning[id(ws)] = session
        return session

    def get_planning(self, ws: WebSocket) -> planning.PlanningSession | None:
        return self._planning.get(id(ws))

    def clear_planning(self, ws: WebSocket):
        self._planning.pop(id(ws), None)


manager = ConnectionManager()
_anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ─────────────────────────── Prompt helpers ───────────────────────────────────

_BASE_SYSTEM = (
    "You are Stark, a sharp, witty voice assistant built for a developer"
    + (f" named {_user_name}" if _user_name else "")
    + ". Keep responses concise and conversational — you're being spoken aloud. "
    "No markdown, no bullet points, no code blocks in your replies. "
    "Just clear, direct spoken English. Be helpful but not sycophantic."
)


def _build_system(mems: list[dict]) -> str:
    if not mems:
        return _BASE_SYSTEM
    lines = "\n".join(f"- {m['key']}: {m['value']}" for m in mems)
    return _BASE_SYSTEM + f"\n\nRelevant memories from previous sessions:\n{lines}"


# ─────────────────────────── Claude helpers ───────────────────────────────────

def _claude_call(text: str, system: str, max_tokens: int = 512) -> str:
    msg = _anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": text}],
    )
    return msg.content[0].text


async def _get_reply(text: str, system: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _claude_call, text, system, 512)


async def _get_tts(text: str) -> tuple[bytes, str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, voice.speak, text)


async def _send_spoken(ws: WebSocket, text: str) -> None:
    """Send a response with TTS audio. Degrades to text-only if TTS fails."""
    logger.info("Response: %s", text)
    try:
        audio_bytes, audio_format = await _get_tts(text)
        await ws.send_json({
            "type": "response",
            "text": text,
            "audio": base64.b64encode(audio_bytes).decode(),
            "audio_format": audio_format,
        })
    except Exception as e:
        logger.warning("TTS failed (%s) — sending text-only response", e)
        # Send text without audio so the user still sees the reply
        await ws.send_json({"type": "response", "text": text, "audio": None, "audio_format": None})


# ─────────────────────────── Intent handlers ─────────────────────────────────

async def _handle_remember(ws: WebSocket, raw: str) -> None:
    extract_sys = (
        "Extract a concise topic key and the fact from this memory statement. "
        "Return ONLY valid JSON: {\"key\": \"short topic\", \"value\": \"the fact\"}.\n"
        "Examples:\n"
        "  'I use Next.js for my portfolio' → {\"key\": \"portfolio tech stack\", \"value\": \"uses Next.js\"}\n"
        "  'my dog is called Biscuit' → {\"key\": \"dog name\", \"value\": \"Biscuit\"}"
    )
    loop = asyncio.get_event_loop()
    raw_json = await loop.run_in_executor(
        executor, _claude_call, raw, extract_sys, 100
    )
    try:
        clean = re.sub(r"```[a-z]*\n?|\n?```", "", raw_json).strip()
        parsed = json.loads(clean)
        key = str(parsed["key"]).strip()
        value = str(parsed["value"]).strip()
    except Exception as e:
        logger.warning("Memory extraction failed: %s — raw: %s", e, raw_json)
        await _send_spoken(ws, "Sorry, I couldn't figure out what to remember there.")
        return

    await loop.run_in_executor(executor, memory.save, key, value)
    logger.info("Memory saved — %r: %r", key, value)
    await _send_spoken(ws, f"Got it. I'll remember that {value}.")


async def _handle_forget(ws: WebSocket, query: str) -> None:
    loop = asyncio.get_event_loop()
    deleted = await loop.run_in_executor(executor, memory.delete_matching, query)
    if deleted:
        logger.info("Memory deleted — %r", deleted["key"])
        await _send_spoken(ws, f"Done. I've forgotten about {deleted['key']}.")
    else:
        await _send_spoken(ws, "I don't have anything stored about that.")


async def _handle_code_intent(ws: WebSocket, raw_name: str) -> None:
    """Resolve project, build confirmation message, arm pending spawn."""
    project_name = raw_name.strip().rstrip(".")
    loop = asyncio.get_event_loop()
    repo_path = await loop.run_in_executor(executor, projects.resolve, project_name)

    if not repo_path:
        await _send_spoken(
            ws,
            f"I don't have {project_name} in my project registry. "
            "You can add it by saying: register project name at path.",
        )
        return

    instruction = claude_runner.build_instruction(repo_path)
    using_resume = claude_runner.has_plan(repo_path)
    plan_note = "the resume command" if using_resume else "a generic prompt"

    display_name = projects.closest_name(project_name) or project_name
    confirm_text = (
        f"I'll run Claude Code on {display_name} using {plan_note}. Shall I?"
    )
    manager.set_pending(ws, PendingSpawn(
        project_name=display_name,
        repo_path=repo_path,
        instruction=instruction,
    ))
    await _send_spoken(ws, confirm_text)


async def _handle_confirmation(ws: WebSocket, text: str) -> bool:
    """Handle yes/no for a pending spawn. Returns True if the text was consumed."""
    pending = manager.get_pending(ws)
    if not pending:
        return False

    if _RE_YES.match(text):
        manager.clear_pending(ws)
        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(
            executor,
            lambda: claude_runner.run(
                pending.repo_path, pending.instruction, new_window=True
            ),
        )
        if proc:
            await _send_spoken(
                ws, f"Launching Claude Code on {pending.project_name}. Good luck."
            )
        else:
            await _send_spoken(
                ws,
                "I couldn't start Claude Code. Make sure the claude CLI is installed and on PATH.",
            )
        return True

    if _RE_NO.match(text):
        manager.clear_pending(ws)
        await _send_spoken(ws, "Cancelled.")
        return True

    # Anything else — cancel and treat as new request
    manager.clear_pending(ws)
    return False


async def _handle_register(ws: WebSocket, name: str, path: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, projects.add, name, path)
    await _send_spoken(ws, f"Registered {name}. You can now say 'work on {name}'.")


async def _handle_open_app(ws: WebSocket, app_name: str) -> None:
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(executor, computer.launch, app_name)
    if ok:
        await _send_spoken(ws, f"Opening {app_name}.")
    else:
        await _send_spoken(
            ws,
            f"I don't know how to open {app_name}. "
            "Try the full name, like 'VS Code' or 'Google Chrome'.",
        )


async def _handle_screen_read(ws: WebSocket) -> None:
    await _send_spoken(ws, "Let me take a look.")
    loop = asyncio.get_event_loop()
    description = await loop.run_in_executor(executor, computer.describe_screen)
    await _send_spoken(ws, description)


async def _handle_briefing(ws: WebSocket) -> None:
    loop = asyncio.get_event_loop()
    summary = await loop.run_in_executor(executor, computer.briefing)
    await _send_spoken(ws, summary)


async def _handle_plan_trigger(ws: WebSocket) -> None:
    """Enter planning mode and ask the first question."""
    session = manager.start_planning(ws)
    await _send_spoken(
        ws,
        "Alright, let's plan this out. I'll ask you five quick questions. "
        + session.current_question,
    )


async def _handle_plan_answer(ws: WebSocket, session: planning.PlanningSession, text: str) -> None:
    """Record an answer; ask the next question or kick off research when done."""
    session.record(text)

    if not session.done:
        await _send_spoken(ws, session.current_question)
        return

    # All 5 answers collected — run research + generate PLAN.md
    manager.clear_planning(ws)
    project_name = session.project_name()

    await _send_spoken(
        ws,
        f"Perfect. Give me a moment while I research {project_name} and put together a plan.",
    )

    loop = asyncio.get_event_loop()
    try:
        research = await loop.run_in_executor(executor, planning.conduct_research, session)
        plan_md  = await loop.run_in_executor(executor, planning.generate_plan_md, session, research)
        plan_path = await loop.run_in_executor(executor, planning.save_plan, session, plan_md)

        # Auto-register the project
        await loop.run_in_executor(executor, projects.add, project_name, str(plan_path.parent))

        # Speak a summary of the research
        spoken_summary = research[:600]  # stay within reasonable TTS length
        await _send_spoken(
            ws,
            f"Done. Here's what I found: {spoken_summary} "
            f"I've written the PLAN.md to {plan_path} and registered {project_name} in your projects. "
            f"Say 'work on {project_name}' when you're ready to start.",
        )

    except Exception as e:
        logger.error("Planning failed: %s", e, exc_info=True)
        await _send_spoken(ws, f"Sorry, something went wrong while planning: {e}")


async def _handle_list_projects(ws: WebSocket) -> None:
    loop = asyncio.get_event_loop()
    reg = await loop.run_in_executor(executor, projects.list_projects)
    if not reg:
        await _send_spoken(ws, "No projects registered yet.")
        return
    names = ", ".join(reg.keys())
    await _send_spoken(ws, f"I know about: {names}.")


# ─────────────────────────── WebSocket endpoint ───────────────────────────────

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
                # ── 1. Active planning session (capture answers in order) ──
                plan_session = manager.get_planning(ws)
                if plan_session:
                    await _handle_plan_answer(ws, plan_session, text)
                    continue

                # ── 2. Pending confirmation (yes / no) ─────────────────────
                consumed = await _handle_confirmation(ws, text)
                if consumed:
                    continue

                # ── 3. Remember intent ─────────────────────────────────────
                m = _RE_REMEMBER.match(text)
                if m:
                    await _handle_remember(ws, m.group(5).strip())
                    continue

                # ── 4. Forget intent ───────────────────────────────────────
                m = _RE_FORGET.match(text)
                if m:
                    await _handle_forget(ws, m.group(5).strip())
                    continue

                # ── 5. Register project ────────────────────────────────────
                m = _RE_REGISTER.match(text)
                if m:
                    await _handle_register(ws, m.group("name").strip(), m.group("path").strip())
                    continue

                # ── 6. List projects ───────────────────────────────────────
                if _RE_LIST_PROJECTS.search(text):
                    await _handle_list_projects(ws)
                    continue

                # ── 7. Open app (checked before code — 'open' is in both) ─
                m = _RE_OPEN_APP.match(text)
                if m:
                    await _handle_open_app(ws, m.group("app").strip())
                    continue

                # ── 8. Code / work-on intent ───────────────────────────────
                m = _RE_CODE.match(text)
                if m:
                    await _handle_code_intent(ws, m.group(5).strip())
                    continue

                # ── 9. Screen reader ───────────────────────────────────────
                if _RE_SCREEN.search(text):
                    await _handle_screen_read(ws)
                    continue

                # ── 10. Project briefing ───────────────────────────────────
                if _RE_BRIEF.search(text):
                    await _handle_briefing(ws)
                    continue

                # ── 11. Planning mode trigger ──────────────────────────────
                if _RE_PLAN_TRIGGER.search(text):
                    await _handle_plan_trigger(ws)
                    continue

                # ── 12. Normal conversation (memory-augmented) ─────────────
                loop = asyncio.get_event_loop()
                mems = await loop.run_in_executor(executor, memory.recall, text, 5)
                system = _build_system(mems)
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


# ─────────────────────────── Hotkey setup ─────────────────────────────────────

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


# ─────────────────────────── Routes ───────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "frontend" / "index.html")


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/projects")
async def api_projects():
    return JSONResponse(projects.list_projects())


# ─────────────────────────── Dev entry point ──────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
