"""Voice-driven project planning — Milestone 4.

Flow
----
  1. Trigger phrase in server.py creates a PlanningSession and arms it on the WebSocket.
  2. server.py routes each subsequent transcript through PlanningSession.next_answer().
  3. After all 5 answers: conduct_research() → generate_plan_md() → save_plan().
  4. server.py registers the new project and speaks the summary back.

The heavy lifting (research + PLAN.md generation) uses claude-sonnet-4-6 for quality.
"""

import logging
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SONNET = "claude-sonnet-4-6"

_QUESTIONS = [
    "What's the project name?",
    "What problem does it solve — one or two sentences?",
    "Who's the target user?",
    "What's your preferred tech stack, if any? Say 'none' to keep it open.",
    "What's the single most important feature for version one?",
]

_PROJECTS_DIR = os.getenv("STARK_PROJECTS_DIR", "")


# ─────────────────────────── Session dataclass ────────────────────────────────

@dataclass
class PlanningSession:
    answers: list[str] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return len(self.answers) >= len(_QUESTIONS)

    @property
    def current_question(self) -> str | None:
        idx = len(self.answers)
        return _QUESTIONS[idx] if idx < len(_QUESTIONS) else None

    def record(self, answer: str) -> None:
        self.answers.append(answer.strip())

    def project_name(self) -> str:
        """Slug the first answer into a filesystem-safe name."""
        if not self.answers:
            return "new-project"
        raw = self.answers[0].strip()
        slug = re.sub(r"[^\w\s-]", "", raw.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")
        return slug or "new-project"

    def as_context(self) -> str:
        lines = []
        for q, a in zip(_QUESTIONS, self.answers):
            lines.append(f"Q: {q}\nA: {a}")
        return "\n\n".join(lines)


# ─────────────────────────── Claude Sonnet helpers ────────────────────────────

def _sonnet(system: str, user: str, max_tokens: int = 2048) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=SONNET,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


def conduct_research(session: PlanningSession) -> str:
    """Return a spoken-friendly research summary (competitors, feasibility, stack)."""
    system = textwrap.dedent("""
        You are a technical co-founder doing a rapid feasibility analysis.
        Given a new project idea (described via Q&A), produce a concise research summary
        covering:
        1. Similar existing products / competitors (2-3 key ones)
        2. Technical feasibility (is this realistic solo / small team?)
        3. Recommended free or open-source tech stack if none was specified
        4. The biggest risk or challenge

        Write in plain spoken English — no markdown headers, no bullet symbols.
        Keep it under 200 words. This will be read aloud.
    """).strip()

    return _sonnet(system, session.as_context(), max_tokens=400)


def generate_plan_md(session: PlanningSession, research: str) -> str:
    """Return the full PLAN.md content as a string."""
    system = textwrap.dedent("""
        You are a senior software architect writing a PLAN.md for a new project.
        Use this exact structure (fill in content based on the project brief and research):

        # <Project Name>

        > <one-line description>

        ---

        ## Viability Summary

        | | |
        |---|---|
        | **Market** | ... |
        | **Feasibility** | ... |
        | **Free to build** | ... |
        | **Monetization** | ... |

        ---

        ## Tech Stack

        | Layer | Choice | Reason |
        |---|---|---|
        | ... | ... | ... |

        ---

        ## Milestones

        ### Milestone 1: <name>
        **Goal:** <goal>

        Tasks:
        - [ ] <task> — Done when: <criterion>
        ...

        ### Milestone 2: <name>
        ...

        (3-5 milestones total, each with 3-6 tasks)

        ---

        ## Claude Code Commands

        **Start Milestone 1:**
        ```
        claude "Read PLAN.md and complete Milestone 1. ..."
        ```

        **Resume from any point:**
        ```
        claude "Read PLAN.md, find the first incomplete task, and continue. Mark tasks done as you go. Commit when a milestone is complete."
        ```

        Write only the markdown. No preamble, no commentary.
    """).strip()

    user = f"Project brief:\n\n{session.as_context()}\n\nResearch notes:\n{research}"
    return _sonnet(system, user, max_tokens=2048)


def save_plan(session: PlanningSession, plan_md: str) -> Path:
    """Write PLAN.md to <projects_dir>/<project_name>/PLAN.md. Returns the path."""
    name = session.project_name()

    if _PROJECTS_DIR:
        base = Path(_PROJECTS_DIR).expanduser()
    else:
        base = Path.home() / "projects"

    project_dir = base / name
    project_dir.mkdir(parents=True, exist_ok=True)

    plan_path = project_dir / "PLAN.md"
    plan_path.write_text(plan_md, encoding="utf-8")
    logger.info("PLAN.md written to %s", plan_path)
    return plan_path
