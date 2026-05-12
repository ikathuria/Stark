"""SQLite memory — implemented in Milestone 2."""
from pathlib import Path

DB_PATH = Path("memory.db")


def save(key: str, value: str) -> None:
    pass


def recall(query: str) -> list[dict]:
    return []


def list_all() -> list[dict]:
    return []
