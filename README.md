# Stark

> A developer-first voice assistant. Speak to it, it answers. Tell it to work on a project, it spawns Claude Code. Give it a new idea, it writes the plan.

---

## What it does

| Say | What happens |
|---|---|
| *"What's the difference between async and await?"* | Claude Haiku answers, spoken aloud |
| *"Remember I'm using Tailwind for my portfolio"* | Saved to SQLite memory, recalled automatically in future turns |
| *"Forget about my dog name"* | Deletes that memory |
| *"Work on stark"* | Confirms, then spawns `claude` in the registered repo |
| *"I have a new idea"* | Enters planning mode — 5 questions, Claude Sonnet research, PLAN.md written to disk |
| *"Open VS Code"* | Launches VS Code |
| *"What's on my screen?"* | Takes a screenshot, Claude Sonnet describes it |
| *"Brief me"* | Reads every registered project's next incomplete task |

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/your-username/stark
cd stark

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY

# 4. Run
python server.py
# Open http://localhost:8000
```

Or with hot-reload for development:
```bash
uvicorn server:app --reload --port 8000
```

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.11+ | Tested on 3.12 |
| `ANTHROPIC_API_KEY` | Required — get from [console.anthropic.com](https://console.anthropic.com) |
| Chrome or Edge | Web Speech API for mic input. Firefox is not supported. |
| `claude` CLI | Only needed for "work on" commands — [install Claude Code](https://docs.anthropic.com/claude-code) |

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

`voice.speak(text)` tries in order, silently falling back on any error:

1. **ElevenLabs** — high quality, ~500 ms latency (`ELEVENLABS_API_KEY` required)
2. **Kokoro** — local neural TTS (`pip install kokoro`), auto-downloads weights on first use
3. **pyttsx3** — system TTS (SAPI on Windows, espeak on Linux), zero setup, always works

---

## Voice commands reference

### Conversation
Any phrase that doesn't match a special intent goes to Claude Haiku with relevant memories injected.

### Memory
```
remember [that] <fact>
  e.g. "remember I use Postgres for all my side projects"

forget [about] <topic>
  e.g. "forget about my Postgres preference"
```

### Projects
```
register project <name> at <path>
  e.g. "register project portfolio at C:\Users\me\projects\portfolio"

list projects  /  show my projects

work on / continue / start <project>
  e.g. "work on stark"
```
Stark asks for confirmation, then runs `claude "<instruction>"` in the repo directory.
If the repo has a `PLAN.md`, the resume command is used automatically.

### Planning mode
```
"I have a new idea"   "let's plan something"   "I want to build <x>"
```
Stark asks 5 questions one at a time (name, problem, user, stack, v1 feature).
After the last answer, Claude Sonnet researches the idea and writes a `PLAN.md`
to `~/projects/<project-name>/`. The project is automatically registered.

### Computer control
```
open <app>            e.g. "open VS Code" / "open terminal" / "open Chrome"
what's on my screen?  screenshot → Claude Sonnet vision description
brief me              next incomplete task for every registered project
```

---

## Project structure

```
server.py          FastAPI app — WebSocket /ws, intent routing, serves frontend
voice.py           TTS chain: ElevenLabs → Kokoro → pyttsx3
memory.py          SQLite + FTS5 memory store
projects.py        JSON-backed project registry with fuzzy name resolution
claude_runner.py   Spawns `claude "<instruction>"` in a repo directory
planner.py         Voice planning flow: 5 intake Qs → Sonnet research → PLAN.md
computer.py        App launcher, screenshot, Sonnet screen reader, briefing
frontend/
  index.html       Single-file UI: Web Speech API + WebSocket + audio playback
tests/
  test_memory.py   Memory unit tests (16 tests, all passing)
requirements.txt
.env.example
PLAN.md            Full milestone roadmap
CLAUDE.md          Reference for future Claude Code sessions
```

---

## Adding a project manually

Edit `projects.json` (next to `server.py`, or in `STARK_PROJECTS_DIR`):

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

**Windows:** Run PowerShell as Administrator for the global hotkey to work. Without admin rights it silently skips — the orb button and Space bar still work in the browser.

---

## Running tests

```bash
python -m pytest tests/ -v
```

---

## Roadmap

See [`PLAN.md`](PLAN.md) — all 6 milestones complete as of v0.1.0.
