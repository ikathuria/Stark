# Stark

> A developer-first voice assistant. Speak to it, it answers. Tell it to work on a project, it spawns Claude Code. Give it a new idea, it writes the plan.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-16%20passing-brightgreen)](#running-tests)
[![v0.1.0](https://img.shields.io/badge/version-v0.1.0-informational)](https://github.com/ikathuria/Stark/releases/tag/v0.1.0)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

---

## What it does

| Say | What happens |
|---|---|
| *"What's the difference between async and await?"* | Claude Haiku answers, spoken aloud |
| *"Remember I'm using Tailwind for my portfolio"* | Saved to SQLite memory, recalled automatically in future turns |
| *"Forget about my dog name"* | Deletes that memory entry |
| *"Work on stark"* | Confirms, then spawns `claude` in the registered repo |
| *"I have a new idea"* | Enters planning mode — 5 questions, Claude Sonnet research, PLAN.md written to disk |
| *"Open VS Code"* | Launches VS Code |
| *"What's on my screen?"* | Takes a screenshot, Claude Sonnet describes it |
| *"Brief me"* | Reads every registered project's next incomplete task aloud |

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/ikathuria/Stark.git
cd Stark

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY

# 4. Run
python server.py
# Open http://localhost:8000
```

Hot-reload for development:
```bash
uvicorn server:app --reload --port 8000
```

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.11+ | Tested on 3.12 |
| `ANTHROPIC_API_KEY` | Required — get from [console.anthropic.com](https://console.anthropic.com) |
| Chrome or Edge | Web Speech API for mic input — Firefox is not supported |
| `claude` CLI | Only needed for "work on" commands — [install Claude Code](https://claude.ai/download) |

---

## Environment variables

See [`.env.example`](.env.example) for the full annotated list.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | — | Claude Haiku (voice loop) + Sonnet (planning, vision) |
| `ELEVENLABS_API_KEY` | No | — | High-quality TTS; falls back to Kokoro → pyttsx3 if absent |
| `ELEVENLABS_VOICE_ID` | No | Adam | Any ElevenLabs voice ID |
| `STARK_USER_NAME` | No | — | Stark addresses you by name |
| `STARK_PROJECTS_DIR` | No | `~/projects` | Where new project directories and `projects.json` are created |
| `STARK_HOTKEY` | No | `ctrl+shift+s` | Global hotkey — requires admin on Windows |

---

## TTS fallback chain

`voice.speak(text)` tries each option in order, falling back silently on any error:

1. **ElevenLabs** — high quality, ~500 ms latency (`ELEVENLABS_API_KEY` required)
2. **Kokoro** — local neural TTS (`pip install kokoro`), auto-downloads model weights on first use
3. **pyttsx3** — system TTS (SAPI on Windows, espeak on Linux), zero setup, always works

---

## Voice commands

### Conversation
Any phrase that doesn't match a special intent is sent to Claude Haiku with relevant memories automatically injected into the system prompt.

### Memory
```
remember [that] <fact>
  → "remember I use Postgres for all my side projects"

forget [about] <topic>
  → "forget about my Postgres preference"
```

### Projects
```
register project <name> at <path>
  → "register project portfolio at C:\Users\me\projects\portfolio"

list projects  /  show my projects

work on / continue / start <project>
  → "work on stark"
```
Stark confirms before running anything. If the repo has a `PLAN.md`, the standard resume command is used automatically; otherwise a generic exploration prompt is used.

### Planning mode
```
"I have a new idea"   "let's plan something"   "I want to build <x>"
```
Stark enters planning mode and asks 5 questions one at a time:

1. Project name
2. Problem it solves
3. Target user
4. Tech stack preference
5. #1 feature for v1

After the last answer, Claude Sonnet researches the idea and generates a full `PLAN.md` in `~/projects/<project-name>/`. The project is automatically registered so you can say *"work on it"* immediately.

### Computer control
```
open <app>            → "open VS Code"  /  "open terminal"  /  "open Chrome"
what's on my screen?  → screenshot + Claude Sonnet vision description
brief me              → next incomplete task for every registered project
```

---

## Project structure

```
server.py          FastAPI app — WebSocket /ws, 12-layer intent router, serves frontend
voice.py           TTS chain: ElevenLabs → Kokoro → pyttsx3
memory.py          SQLite + FTS5 memory store
projects.py        JSON-backed project registry with fuzzy name resolution
claude_runner.py   Spawns `claude "<instruction>"` subprocess, PLAN.md-aware
planner.py         Planning flow: 5 intake questions → Sonnet research → PLAN.md
computer.py        App launcher, screenshot, Sonnet screen reader, briefing
frontend/
  index.html       Single-file UI: Web Speech API + WebSocket + audio playback
tests/
  test_memory.py   Memory unit tests (16 tests, all passing)
requirements.txt
.env.example
PLAN.md            Full milestone roadmap (all 6 milestones complete)
CLAUDE.md          Reference for future Claude Code sessions
```

---

## Adding a project manually

Edit `projects.json` (created next to `server.py`, or in `STARK_PROJECTS_DIR`):

```json
{
  "stark":     "C:/Users/you/projects/stark",
  "portfolio": "C:/Users/you/projects/portfolio"
}
```

Or just say: *"register project portfolio at C:\Users\you\projects\portfolio"*

---

## Global hotkey

`ctrl+shift+s` (configurable via `STARK_HOTKEY`) triggers voice input from any window.

**Windows:** Run PowerShell as Administrator for the hotkey to work globally. Without admin rights it silently skips — the orb button and Space bar still work in the browser tab.

**Mac / Linux:** No elevated privileges needed.

---

## Running tests

```bash
python -m pytest tests/ -v
```

---

## Roadmap

See [`PLAN.md`](PLAN.md) — all 6 milestones complete as of v0.1.0.
