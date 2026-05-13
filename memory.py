"""Persistent memory backed by SQLite with FTS5 full-text search.

Schema
------
memories_data   — primary row store (id, key, value, created_at)
memories_fts    — FTS5 external-content virtual table, kept in sync via triggers

Public API
----------
save(key, value)          upsert a memory entry
recall(query, limit=5)    full-text search → list of dicts
list_all()                return all memories newest-first
delete(key)               exact-key delete → bool
delete_matching(query)    delete top full-text match → deleted dict | None
"""

import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("memory.db")

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(conn)
        _local.conn = conn
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories_data (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            key        TEXT    NOT NULL,
            value      TEXT    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            key,
            value,
            content      = 'memories_data',
            content_rowid = 'id',
            tokenize     = 'unicode61 remove_diacritics 1'
        );

        CREATE TRIGGER IF NOT EXISTS memories_ai
          AFTER INSERT ON memories_data BEGIN
            INSERT INTO memories_fts(rowid, key, value)
            VALUES (new.id, new.key, new.value);
          END;

        CREATE TRIGGER IF NOT EXISTS memories_ad
          AFTER DELETE ON memories_data BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, value)
            VALUES ('delete', old.id, old.key, old.value);
          END;

        CREATE TRIGGER IF NOT EXISTS memories_au
          AFTER UPDATE ON memories_data BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, value)
            VALUES ('delete', old.id, old.key, old.value);
            INSERT INTO memories_fts(rowid, key, value)
            VALUES (new.id, new.key, new.value);
          END;
    """)
    conn.commit()


def _fts_query(raw: str) -> str:
    """Convert free-form user text into a safe FTS5 MATCH expression."""
    # Strip non-word chars, drop very short tokens, limit to 6 tokens
    tokens = [t for t in re.sub(r"[^\w\s]", " ", raw).split() if len(t) > 2][:6]
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ────────────────────────────────────────────────────────────────

def save(key: str, value: str) -> None:
    """Upsert a memory. If the key already exists it is replaced."""
    conn = _get_conn()
    existing = conn.execute(
        "SELECT id FROM memories_data WHERE key = ?", (key,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE memories_data SET value = ?, created_at = ? WHERE id = ?",
            (value, _now(), existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO memories_data(key, value, created_at) VALUES (?, ?, ?)",
            (key, value, _now()),
        )
    conn.commit()


def recall(query: str, limit: int = 5) -> list[dict]:
    """Full-text search. Returns list of {key, value, created_at} dicts."""
    conn = _get_conn()
    fts = _fts_query(query)
    try:
        rows = conn.execute(
            """
            SELECT d.key, d.value, d.created_at
            FROM memories_fts f
            JOIN memories_data d ON d.id = f.rowid
            WHERE memories_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # Malformed query — return empty rather than crash
        rows = []
    return [dict(r) for r in rows]


def list_all() -> list[dict]:
    """Return every memory, newest first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT key, value, created_at FROM memories_data ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def delete(key: str) -> bool:
    """Delete a memory by exact key. Returns True if something was deleted."""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM memories_data WHERE key = ?", (key,))
    conn.commit()
    return cur.rowcount > 0


def delete_matching(query: str) -> dict | None:
    """Delete the top full-text search match. Returns the deleted row or None."""
    results = recall(query, limit=1)
    if not results:
        return None
    deleted = results[0]
    delete(deleted["key"])
    return deleted
