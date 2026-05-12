# Stark — Claude Code Reference

A developer-first voice assistant: browser mic → WebSocket → FastAPI → Claude Haiku → ElevenLabs TTS → audio back to browser.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY and ELEVENLABS_API_KEY
python server.py       # or: uvicorn server:app --reload --port 8000
# open http://localhost:8000
```

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Claude Haiku for voice replies |
| `ELEVENLABS_API_KEY` | No | — | Primary TTS; falls back to local if absent |
| `ELEVENLABS_VOICE_ID` | No | Adam (`pNInz6obpgDQGcFmaJgB`) | ElevenLabs voice |
| `STARK_USER_NAME` | No | — | Stark addresses you by name |
| `STARK_PROJECTS_DIR` | No | — | Root dir for Milestone 3 project registry |
| `STARK_HOTKEY` | No | `ctrl+shift+s` | Global hotkey to trigger voice input |

## Project Structure

```
server.py          # FastAPI app — WebSocket /ws, serves frontend/index.html
voice.py           # TTS: ElevenLabs → Kokoro → pyttsx3 (fallback chain)
memory.py          # SQLite memory (stub — Milestone 2)
claude_runner.py   # Claude Code subprocess runner (stub — Milestone 3)
frontend/
  index.html       # Single-file UI: Web Speech API + WebSocket + audio playback
requirements.txt
.env.example
PLAN.md            # Full roadmap with milestones and tasks
```

## WebSocket Protocol

All messages are JSON.

**Client → Server:**
```json
{ "type": "transcript", "text": "what time is it" }
```

**Server → Client:**
```json
{ "type": "response",  "text": "It's 3pm.",  "audio": "<base64>", "audio_format": "audio/mpeg" }
{ "type": "start_listening" }   // triggered by STARK_HOTKEY
{ "type": "error",     "message": "..." }
```

## TTS Fallback Chain

`voice.speak(text)` tries in order:
1. **ElevenLabs** — API call, returns MP3. Used when `ELEVENLABS_API_KEY` is set.
2. **Kokoro** — local neural TTS (`pip install kokoro`). Auto-downloads model weights on first use.
3. **pyttsx3** — system TTS (SAPI on Windows). Always available, no downloads.

## Voice Loop Flow

```
User speaks
  → Web Speech API transcribes in browser
  → WebSocket sends { type: "transcript", text: "..." }
  → server.py calls Claude Haiku (claude-haiku-4-5-20251001)
  → voice.py generates TTS audio
  → WebSocket returns { type: "response", text, audio (base64), audio_format }
  → browser decodes + plays audio
```

## Claude Model Used

- **Voice loop** (Milestone 1–2): `claude-haiku-4-5-20251001` — fast, cheap, <1s
- **Planning / vision** (Milestone 4–5): `claude-sonnet-4-6` — quality over speed

## Hotkey Notes

The `keyboard` library requires **admin privileges on Windows** for global hotkeys. If the server starts without admin rights, hotkey registration silently skips — the orb button and Space bar still work in the browser tab.

Run PowerShell as Administrator if you need the global hotkey.

## Current Milestone

**Milestone 1 complete.** See PLAN.md for remaining milestones.

## Resume Command

```
claude "Read PLAN.md, find the first incomplete task, and continue. Mark tasks done as you go. Commit when a milestone is complete."
```
