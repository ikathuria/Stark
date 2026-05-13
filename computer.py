"""Minimal computer control — Milestone 5.

Capabilities
------------
launch(app_name)    → bool         open a common app by voice name
screenshot()        → bytes | None  PNG bytes of the primary screen
describe_screen()   → str           Claude Sonnet vision summary of current screen
briefing()          → str           spoken summary of all registered projects + next tasks
"""

import base64
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

import projects

load_dotenv()
logger = logging.getLogger(__name__)

SONNET = "claude-sonnet-4-6"

# ─────────────────────────── App launcher ─────────────────────────────────────

# Map of normalised voice names → launch commands per platform
_APPS_WINDOWS: dict[str, list[str]] = {
    "vs code":          ["code"],
    "vscode":           ["code"],
    "visual studio code": ["code"],
    "terminal":         ["cmd.exe"],
    "powershell":       ["powershell.exe"],
    "chrome":           ["chrome"],
    "google chrome":    ["chrome"],
    "firefox":          ["firefox"],
    "edge":             ["msedge"],
    "microsoft edge":   ["msedge"],
    "notepad":          ["notepad.exe"],
    "explorer":         ["explorer.exe"],
    "file explorer":    ["explorer.exe"],
    "slack":            ["slack"],
    "discord":          ["discord"],
    "spotify":          ["spotify"],
    "obsidian":         ["obsidian"],
    "notion":           ["notion"],
    "cursor":           ["cursor"],
}

_APPS_MAC: dict[str, list[str]] = {
    "vs code":          ["code"],
    "vscode":           ["code"],
    "visual studio code": ["code"],
    "terminal":         ["open", "-a", "Terminal"],
    "iterm":            ["open", "-a", "iTerm"],
    "chrome":           ["open", "-a", "Google Chrome"],
    "google chrome":    ["open", "-a", "Google Chrome"],
    "firefox":          ["open", "-a", "Firefox"],
    "safari":           ["open", "-a", "Safari"],
    "finder":           ["open", "-a", "Finder"],
    "slack":            ["open", "-a", "Slack"],
    "discord":          ["open", "-a", "Discord"],
    "spotify":          ["open", "-a", "Spotify"],
    "obsidian":         ["open", "-a", "Obsidian"],
    "notion":           ["open", "-a", "Notion"],
    "cursor":           ["open", "-a", "Cursor"],
}

_APPS_LINUX: dict[str, list[str]] = {
    "vs code":          ["code"],
    "vscode":           ["code"],
    "terminal":         ["x-terminal-emulator"],
    "chrome":           ["google-chrome"],
    "google chrome":    ["google-chrome"],
    "firefox":          ["firefox"],
    "slack":            ["slack"],
    "discord":          ["discord"],
    "spotify":          ["spotify"],
}

_PLATFORM_MAP = {
    "win32":  _APPS_WINDOWS,
    "darwin": _APPS_MAC,
}


def _get_app_map() -> dict[str, list[str]]:
    return _PLATFORM_MAP.get(sys.platform, _APPS_LINUX)


def launch(app_name: str) -> bool:
    """Launch an app by voice name. Returns True if launched successfully."""
    key = re.sub(r"\s+", " ", app_name.lower().strip())
    app_map = _get_app_map()

    cmd = app_map.get(key)
    if not cmd:
        # Fuzzy: check if any registered name contains the key or vice-versa
        for registered, registered_cmd in app_map.items():
            if key in registered or registered in key:
                cmd = registered_cmd
                break

    if not cmd:
        logger.warning("No launcher found for: %r", app_name)
        return False

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=(sys.platform == "win32"),
        )
        logger.info("Launched: %s (cmd: %s)", app_name, cmd)
        return True
    except Exception as e:
        logger.error("Failed to launch %r: %s", app_name, e)
        return False


# ─────────────────────────── Screenshot ───────────────────────────────────────

def screenshot() -> bytes | None:
    """Capture the primary screen and return PNG bytes, or None on error."""
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            img = sct.grab(monitor)
            return mss.tools.to_png(img.rgb, img.size)

    except ImportError:
        pass  # mss not installed — try PIL

    try:
        import io
        from PIL import ImageGrab

        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as e:
        logger.warning("screenshot failed: %s", e)
        return None


# ─────────────────────────── Screen reader ────────────────────────────────────

def describe_screen() -> str:
    """Take a screenshot and ask Claude Sonnet vision to describe it."""
    png = screenshot()
    if not png:
        return "I couldn't take a screenshot. Make sure mss or Pillow is installed."

    b64 = base64.standard_b64encode(png).decode()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    try:
        msg = client.messages.create(
            model=SONNET,
            max_tokens=300,
            system=(
                "You are a screen reader assistant. Describe what's on the screen "
                "in plain spoken English. Focus on the active window and any visible "
                "content. Be concise — under 100 words. No markdown."
            ),
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64},
                    },
                    {"type": "text", "text": "What's on my screen?"},
                ],
            }],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error("describe_screen Claude call failed: %s", e)
        return f"I couldn't read the screen: {e}"


# ─────────────────────────── Project briefing ─────────────────────────────────

def _next_task(plan_path: Path) -> str | None:
    """Return the first unchecked task line from a PLAN.md, or None."""
    if not plan_path.is_file():
        return None
    try:
        for line in plan_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("- [ ]"):
                task = re.sub(r"^- \[ \]\s*", "", line.strip())
                # Strip the "Done when: ..." suffix for brevity
                task = re.sub(r"\s*—\s*Done when:.*$", "", task)
                return task.strip()
    except Exception:
        pass
    return None


def briefing() -> str:
    """Return a spoken summary of all registered projects and their next task."""
    reg = projects.list_projects()
    if not reg:
        return "You have no projects registered yet."

    parts: list[str] = []
    for name, path in reg.items():
        plan_path = Path(path).expanduser() / "PLAN.md"
        next_task = _next_task(plan_path)
        if next_task:
            parts.append(f"{name}: next task is {next_task}")
        else:
            parts.append(f"{name}: all tasks complete or no PLAN.md found")

    joined = ". ".join(parts)
    return f"Here's your briefing. {joined}."
