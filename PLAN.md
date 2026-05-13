# Stark

> A developer-first voice assistant that bounces ideas, spawns Claude Code sessions, and keeps you locked in on your projects — built for one person, designed to ship.

---

## Viability Summary

| | |
|---|---|
| **Market** | Developer-specific voice + Claude Code niche is wide open. Generic jarvis clones miss this loop entirely |
| **Feasibility** | Medium — voice loop + subprocess spawning are well-solved in Python. Latency is the main challenge |
| **Free to build** | Mostly — Web Speech API (free), ElevenLabs free tier (10k chars/mo), Kokoro fallback (unlimited local), Claude API (pay per token) |
| **Monetization** | Open source core → hosted/managed version or team tier later |

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python + FastAPI | Best ecosystem for audio libs and subprocess control |
| STT | Web Speech API (browser) | Free, no setup, good accuracy |
| TTS (primary) | ElevenLabs free tier | High quality, low latency (~500ms), British butler voice |
| TTS (fallback) | Kokoro (local) | Free, unlimited, offline — kicks in when ElevenLabs cap is hit |
| Brain — fast loop | Claude Haiku | <1s replies for voice conversation |
| Brain — deep tasks | Claude Sonnet | Planning, idea bouncing, complex reasoning |
| Claude Code | Python subprocess | Stark runs `claude "..."` commands on your behalf |
| Memory | SQLite + FTS5 | Persists context, decisions, project state across sessions |
| Frontend | HTML/JS served by FastAPI | No framework needed |
| Trigger | Hotkey via `keyboard` lib | Configurable key combo to activate Stark |

---

## Environment Variables

```
# Required
ANTHROPIC_API_KEY=        # Claude Haiku + Sonnet — get from console.anthropic.com
ELEVENLABS_API_KEY=       # TTS — get from elevenlabs.io (free tier)

# Optional
ELEVENLABS_VOICE_ID=      # Default: ElevenLabs "Antoni" or similar — override with any voice ID
STARK_USER_NAME=          # Your name — Stark will address you by it
STARK_PROJECTS_DIR=       # Path to your local projects folder e.g. ~/projects
```

---

## Milestones

### Milestone 1: Scaffold + Core Voice Loop
**Goal:** Speak → transcribed → Claude Haiku responds → spoken back. Under 2 seconds end to end.

Tasks:
- [x] Initialize Python project with FastAPI, install dependencies (anthropic, elevenlabs, pyttsx3/kokoro, keyboard, sqlite3) — Done when: `pip install -r requirements.txt` succeeds with no errors
- [x] Set up project structure: `server.py`, `memory.py`, `voice.py`, `claude_runner.py`, `frontend/index.html` — Done when: all files exist with stubs
- [x] Build WebSocket endpoint in FastAPI that receives transcript text and returns a response — Done when: sending a message over WebSocket returns a Claude Haiku reply
- [x] Build frontend: microphone button, Web Speech API integration, WebSocket connection, text display — Done when: browser can capture voice and display transcript
- [x] Integrate ElevenLabs TTS — send Claude reply text, receive audio, play it back in browser — Done when: Stark speaks responses out loud
- [x] Add Kokoro/pyttsx3 as TTS fallback — automatically used when ElevenLabs API call fails or quota is exceeded — Done when: fallback triggers silently without crashing
- [x] Add hotkey trigger (configurable in .env) to focus the browser tab or toggle listening — Done when: pressing the hotkey activates voice input without clicking
- [x] Write CLAUDE.md explaining project structure for future Claude Code sessions — Done when: file exists with accurate setup instructions

---

### Milestone 2: Memory
**Goal:** Stark remembers things across sessions — project names, decisions, preferences, anything you tell it to remember.

Tasks:
- [x] Set up SQLite database with FTS5 full-text search — Done when: `memory.db` is created on first run
- [x] Create `memory.py` with `save(key, value)`, `recall(query)`, `list_all()` functions — Done when: unit tests pass for all three
- [x] Wire memory into the conversation: inject recent relevant memories into Claude Haiku's system prompt on each turn — Done when: Stark references a fact you told it in a previous session
- [x] Add explicit "remember" trigger — if user says "remember that..." Stark saves it and confirms — Done when: "remember I'm using Next.js for my portfolio" persists and is recalled next session
- [x] Add "forget" trigger — user can remove specific memories — Done when: "forget about X" removes the entry and confirms

---

### Milestone 3: Claude Code Integration
**Goal:** Stark spawns real Claude Code sessions from voice commands.

Tasks:
- [x] Build `claude_runner.py` — takes a repo path + instruction string, spawns `claude "<instruction>"` as a subprocess in that directory — Done when: function runs a Claude Code session in a given repo and streams output to terminal
- [x] Build project registry — a JSON or SQLite table mapping project names to local paths e.g. `{"portfolio": "~/projects/portfolio"}` — Done when: Stark knows where each project lives
- [x] Add voice intent detection for coding commands — "work on [project]", "continue [project]", "start [project]" → maps to the right repo and spawns Claude Code with the resume command — Done when: saying "work on my portfolio" opens a Claude Code session in the right directory
- [x] Add PLAN.md awareness — when spawning a session, Stark checks if PLAN.md exists and uses the resume command; if not, uses a generic instruction — Done when: projects with PLAN.md get the correct resume command automatically
- [x] Confirm before spawning — Stark reads back what it's about to run and waits for voice confirmation — Done when: "work on stark" triggers "I'll run Claude Code on stark with the resume command. Shall I?" before executing

---

### Milestone 4: Idea Bouncing + Planning Mode
**Goal:** Trigger the full project planning flow hands-free. "I have a new idea" → intake questions → research → PLAN.md.

Tasks:
- [x] Add planning mode trigger — "I have an idea", "let's plan something", "new project" → switches Stark into planning mode with Claude Sonnet — Done when: trigger phrase activates a distinct planning conversation context
- [x] Implement voice-driven intake — Stark asks the 5 planning questions one at a time, waits for voice answers, stores them — Done when: all 5 answers are captured in a structured object
- [x] Run market research — after intake, Stark uses Claude Sonnet with web search to research competitors, feasibility, free stack options — Done when: research summary is spoken back and saved
- [x] Generate PLAN.md — Stark writes the full plan file using the gathered context and saves it to the new project directory — Done when: PLAN.md exists in `~/projects/<project-name>/PLAN.md`
- [x] Register new project — automatically adds the new project to the project registry — Done when: the new project is immediately accessible via "work on [project name]"

---

### Milestone 5: Minimal Computer Control
**Goal:** Open apps, read the screen, switch context — the basics.

Tasks:
- [x] App launcher — "open VS Code", "open terminal", "open Chrome" → uses `subprocess` / `os.system` to launch apps — Done when: 5 common apps launch correctly by voice
- [x] Screen reader — "what's on my screen" → takes screenshot, sends to Claude Sonnet vision, speaks the summary — Done when: Stark accurately describes an active window
- [x] Project briefing — "what am I working on" or "brief me" → Stark reads project registry, checks PLAN.md files, gives a spoken summary of active projects and next tasks — Done when: morning briefing covers all registered projects with their next incomplete task

---

### Milestone 6: Polish + Ship
**Goal:** Clean enough for someone else to clone and run. Ready to put on GitHub.

Tasks:
- [x] Add `config.json` or `.env.example` with all configurable options documented — Done when: a new user can set up Stark with only that file
- [x] Write detailed README — what it does, how to install, how to add projects, how to use each mode — Done when: README covers all milestones' features
- [x] Update CLAUDE.md with final project structure so future Claude Code sessions can navigate it — Done when: running `claude "read CLAUDE.md and add X feature"` works without confusion
- [x] Error handling pass — every external call (ElevenLabs, Anthropic, subprocess) has a graceful fallback and user-facing voice error message — Done when: pulling the network cable doesn't crash Stark
- [x] GitHub release — tag v0.1.0, write release notes — Done when: repo is public with a release

---

## Claude Code Commands

**Start Milestone 1:**
```
claude "Read PLAN.md and complete Milestone 1. Goal is a working voice loop: browser mic → Web Speech API → WebSocket → FastAPI → Claude Haiku → ElevenLabs TTS → audio out, with Kokoro as fallback. Mark tasks done as you go. Stop after Milestone 1 and commit."
```

**Resume from any point:**
```
claude "Read PLAN.md, find the first incomplete task, and continue. Mark tasks done as you go. Commit when a milestone is complete."
```

**Test current state:**
```
claude "Read PLAN.md. Without building anything new, test everything marked done. Report what works and what's broken."
```

---

## Notes & Decisions

- Name: Stark (personal nod to Iron Man, not on the nose)
- TTS: ElevenLabs primary, Kokoro local fallback — no hard dependency on paid service
- LLM split: Haiku for the real-time voice loop (speed), Sonnet for planning and vision (quality)
- Computer control is intentionally minimal for v0.1 — no system automation beyond app launching and screen reading
- Claude Code sessions are spawned as subprocesses, not embedded — Stark stays lightweight
