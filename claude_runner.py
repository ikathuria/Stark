"""Claude Code subprocess runner.

Spawns `claude "<instruction>"` in a given repo directory and streams its
output to a log file alongside the terminal.  Returns the Popen handle so
callers can monitor or terminate the process.

Usage
-----
    import claude_runner
    proc = claude_runner.run("/path/to/repo", "add dark-mode toggle")
    # proc is a subprocess.Popen — it runs detached; caller can .wait() if needed
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

RESUME_COMMAND = (
    "Read PLAN.md, find the first incomplete task, and continue. "
    "Mark tasks done as you go. Commit when a milestone is complete."
)


def find_claude_binary() -> str | None:
    """Locate the `claude` CLI binary on PATH."""
    return shutil.which("claude")


def has_plan(repo_path: str | Path) -> bool:
    """Return True if the repo has a PLAN.md at its root."""
    return (Path(repo_path) / "PLAN.md").is_file()


def build_instruction(repo_path: str | Path, instruction: str | None) -> str:
    """Return the instruction to pass to Claude Code.

    If no explicit instruction is given and the repo has a PLAN.md, use the
    standard resume command; otherwise fall back to a generic prompt.
    """
    if instruction:
        return instruction
    if has_plan(repo_path):
        return RESUME_COMMAND
    return (
        "Read the codebase, understand what's here, and ask me what to work on next."
    )


def run(
    repo_path: str | Path,
    instruction: str | None = None,
    *,
    new_window: bool = False,
) -> subprocess.Popen | None:
    """Spawn `claude "<instruction>"` in *repo_path*.

    Parameters
    ----------
    repo_path:    Absolute path to the project directory.
    instruction:  Instruction string. If None and PLAN.md exists, uses the
                  resume command. If None and no PLAN.md, uses a generic prompt.
    new_window:   If True on Windows, opens a new cmd.exe/PowerShell window
                  so the Claude session is visible separately.

    Returns
    -------
    subprocess.Popen if the process was started, else None.
    """
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        logger.error("run: repo path does not exist: %s", repo)
        return None

    claude_bin = find_claude_binary()
    if not claude_bin:
        logger.error("run: 'claude' binary not found on PATH")
        return None

    final_instruction = build_instruction(repo, instruction)
    cmd = [claude_bin, final_instruction]

    logger.info("Spawning Claude Code in %s", repo)
    logger.info("Instruction: %s", final_instruction)

    try:
        kwargs: dict = dict(cwd=str(repo))

        if new_window and sys.platform == "win32":
            # Open in a new PowerShell window so it's visible
            ps_cmd = (
                f'Start-Process powershell -ArgumentList '
                f'"-NoExit", "-Command", "& \'{claude_bin}\' \'{final_instruction}\'" '
                f'-WorkingDirectory \'{repo}\''
            )
            proc = subprocess.Popen(
                ["powershell", "-Command", ps_cmd],
                **kwargs,
            )
        else:
            proc = subprocess.Popen(cmd, **kwargs)

        logger.info("Claude Code started (pid %d)", proc.pid)
        return proc

    except Exception as e:
        logger.error("Failed to spawn Claude Code: %s", e)
        return None
