"""Project registry: maps project names → local paths.

Stored in `projects.json` next to this file (or in STARK_PROJECTS_DIR if set).
Exposes a simple CRUD API used by server.py and voice commands.

JSON schema
-----------
{
  "stark":     "C:/Users/you/projects/stark",
  "portfolio": "~/projects/portfolio"
}
"""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECTS_DIR = os.getenv("STARK_PROJECTS_DIR", "")
REGISTRY_PATH = (
    Path(_PROJECTS_DIR) / "projects.json"
    if _PROJECTS_DIR
    else Path(__file__).parent / "projects.json"
)


def _load() -> dict[str, str]:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Could not load project registry: %s", e)
        return {}


def _save(registry: dict[str, str]) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _normalise(name: str) -> str:
    """Lower-case and strip filler words for fuzzy matching."""
    name = name.lower().strip()
    name = re.sub(r"\b(my|the|a|an|project|repo|app)\b", "", name)
    return re.sub(r"\s+", " ", name).strip()


# ── Public API ────────────────────────────────────────────────────────────────

def list_projects() -> dict[str, str]:
    """Return the full {name: path} registry."""
    return _load()


def add(name: str, path: str) -> None:
    """Register a project. Creates projects.json if it doesn't exist."""
    reg = _load()
    reg[_normalise(name)] = str(Path(path).expanduser())
    _save(reg)
    logger.info("Project registered: %r → %s", name, path)


def remove(name: str) -> bool:
    """Remove a project by name. Returns True if it existed."""
    reg = _load()
    key = _normalise(name)
    if key in reg:
        del reg[key]
        _save(reg)
        return True
    return False


def resolve(name: str) -> str | None:
    """Find the path for a project name (fuzzy match).

    Returns the resolved absolute path string, or None if not found.
    """
    reg = _load()
    needle = _normalise(name)

    # 1. Exact match
    if needle in reg:
        return str(Path(reg[needle]).expanduser().resolve())

    # 2. Partial / substring match — pick the best
    candidates = [(k, v) for k, v in reg.items() if needle in k or k in needle]
    if len(candidates) == 1:
        return str(Path(candidates[0][1]).expanduser().resolve())
    if len(candidates) > 1:
        # Prefer the one whose normalised key is longest (most specific)
        best = max(candidates, key=lambda kv: len(kv[0]))
        return str(Path(best[1]).expanduser().resolve())

    return None


def closest_name(name: str) -> str | None:
    """Return the registry key that best matches *name*, or None."""
    reg = _load()
    needle = _normalise(name)
    if needle in reg:
        return needle
    candidates = [k for k in reg if needle in k or k in needle]
    if candidates:
        return max(candidates, key=len)
    return None
