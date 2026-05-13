# Stark — Claude Code Reference

A developer-first voice assistant: browser mic → WebSocket → FastAPI → Claude Haiku → ElevenLabs TTS → audio back to browser.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY (required) and ELEVENLABS_API_KEY (optional)
python server.py       # or: uvicorn server:app --reload --port 8000
# open http://localhost:8000
```

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Claude Haiku (voice loop) + Sonnet (planning, screen reader) |
| `ELEVENLABS_API_KEY` | No | — | Primary TTS; falls back to Kokoro → pyttsx3 if absent |
| `ELEVENLABS_VOICE_ID` | No | Adam (`pNInz6obpgDQGcFmaJgB`) | ElevenLabs voice |
| `STARK_USER_NAME` | No | — | Stark addresses you by name |
| `STARK_PROJECTS_DIR` | No | `~/projects` | Root for new project dirs and `projects.json` |
| `STARK_HOTKEY` | No | `ctrl+shift+s` | Global hotkey to trigger voice input |

## Project Structure

```
server.py          FastAPI app — WebSocket /ws, 12-layer intent router, serves frontend
voice.py           TTS: ElevenLabs → Kokoro → pyttsx3 (fallback chain)
memory.py          SQLite + FTS5 memory: save/recall/list_all/delete/delete_matching
projects.py        JSON registry: add/remove/resolve/list_projects (fuzzy name match)
claude_runner.py   Spawns `claude "<instruction>"` subprocess; PLAN.md-aware
planner.py         Claude Sonnet planning flow: PlanningSession + research + PLAN.md gen
computer.py        launch(app), screenshot(), describe_screen(), briefing()
frontend/
  index.html       Single-file UI: Web Speech API + WebSocket + audio playback
tests/
  test_memory.py   16 unit tests for memory.py (all passing)
requirements.txt   All Python deps
.env.example       Env var template with full comments
PLAN.md            Full milestone roadmap (all 6 milestones complete)
projects.json      Auto-created: {name → path} project registry
memory.db          Auto-created: SQLite + FTS5 persistent memory
```

## WebSocket Protocol

All messages are JSON.

**Client → Server:**
```json
{ "type": "transcript", "text": "what time is it" }
```

**Server → Client:**
```json
{ "type": "response",       "text": "It's 3pm.", "audio": "<base64>", "audio_format": "audio/mpeg" }
{ "type": "start_listening" }   // triggered by STARK_HOTKEY
{ "type": "error",          "message": "..." }
```

## Intent Routing (server.py)

Messages are processed through 12 intent layers in order:
1. Active planning session (capture Q&A answers in order)
2. Pending confirmation (yes/no for spawn)
3. Remember → FTS5 memory save
4. Forget → FTS5 memory delete
5. Register project `<name>` at `<path>`
6. List projects
7. Work on / continue / start `<project>` → confirmation flow
8. Open app
9. Screen reader ("what's on my screen")
10. Project briefing ("brief me")
11. Planning mode trigger ("I have a new idea")
12. Normal conversation (memory-augmented Haiku)

## TTS Fallback Chain

`voice.speak(text)` tries in order:
1. **ElevenLabs** — API call, returns MP3. Used when `ELEVENLABS_API_KEY` is set.
2. **Kokoro** — local neural TTS (`pip install kokoro`). Auto-downloads on first use.
3. **pyttsx3** — system TTS (SAPI on Windows). Always available.

## Claude Models

- **Voice loop / intent extraction** (server.py): `claude-haiku-4-5-20251001` — fast, cheap
- **Planning + screen reader** (planner.py, computer.py): `claude-sonnet-4-6` — quality

## Key Data Files (auto-created at runtime)

- `memory.db` — SQLite with FTS5, holds all remembered facts
- `projects.json` — JSON map `{name: path}` for the project registry

## Hotkey Notes

The `keyboard` library requires **admin privileges on Windows** for global hotkeys. Without admin, hotkey silently skips — the orb button and Space bar still work.

## Running Tests

```bash
python -m pytest tests/ -v
```

## Current Milestone

**All 6 milestones complete.** See PLAN.md for the full roadmap.

## Resume Command

```
claude "Read PLAN.md, find the first incomplete task, and continue. Mark tasks done as you go. Commit when a milestone is complete."
```
