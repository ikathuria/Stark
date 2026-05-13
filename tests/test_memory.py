"""Unit tests for memory.py — save, recall, list_all, delete."""
import sys
import tempfile
from pathlib import Path

import pytest

# ── isolate each test with its own DB ────────────────────────────────────────
import memory as mem


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Give each test a fresh DB file and a clean thread-local connection."""
    db = tmp_path / "test_memory.db"
    monkeypatch.setattr(mem, "DB_PATH", db)
    # Reset any cached thread-local connection
    if hasattr(mem._local, "conn"):
        try:
            mem._local.conn.close()
        except Exception:
            pass
        del mem._local.conn
    yield
    if hasattr(mem._local, "conn"):
        try:
            mem._local.conn.close()
        except Exception:
            pass
        del mem._local.conn


# ── save ─────────────────────────────────────────────────────────────────────

def test_save_creates_entry():
    mem.save("framework", "using React")
    rows = mem.list_all()
    assert len(rows) == 1
    assert rows[0]["key"] == "framework"
    assert rows[0]["value"] == "using React"


def test_save_upserts_existing_key():
    mem.save("framework", "using React")
    mem.save("framework", "switched to Vue")
    rows = mem.list_all()
    assert len(rows) == 1
    assert rows[0]["value"] == "switched to Vue"


def test_save_multiple_distinct_keys():
    mem.save("frontend", "React")
    mem.save("backend", "FastAPI")
    mem.save("database", "PostgreSQL")
    assert len(mem.list_all()) == 3


# ── recall ────────────────────────────────────────────────────────────────────

def test_recall_finds_value():
    mem.save("portfolio tech stack", "using Next.js and Tailwind")
    results = mem.recall("portfolio")
    assert len(results) >= 1
    assert any("portfolio" in r["key"] for r in results)


def test_recall_finds_by_value_word():
    mem.save("portfolio tech", "using Next.js")
    results = mem.recall("Next.js")
    assert len(results) >= 1


def test_recall_returns_empty_for_no_match():
    mem.save("cats", "I own two cats")
    results = mem.recall("kubernetes")
    assert results == []


def test_recall_respects_limit():
    for i in range(10):
        mem.save(f"key {i}", f"value about testing topic {i}")
    results = mem.recall("testing topic", limit=3)
    assert len(results) <= 3


def test_recall_with_special_chars_doesnt_crash():
    mem.save("test", "some value")
    # Should not raise — FTS5 special chars sanitised
    results = mem.recall('what is the "best" framework?')
    # No crash is the pass condition


# ── list_all ──────────────────────────────────────────────────────────────────

def test_list_all_empty():
    assert mem.list_all() == []


def test_list_all_returns_all():
    mem.save("a", "alpha")
    mem.save("b", "beta")
    rows = mem.list_all()
    assert len(rows) == 2
    keys = {r["key"] for r in rows}
    assert keys == {"a", "b"}


def test_list_all_has_created_at():
    mem.save("x", "y")
    rows = mem.list_all()
    assert "created_at" in rows[0]
    assert rows[0]["created_at"]  # non-empty


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_removes_entry():
    mem.save("to-remove", "some value")
    result = mem.delete("to-remove")
    assert result is True
    assert mem.list_all() == []


def test_delete_returns_false_when_not_found():
    result = mem.delete("nonexistent")
    assert result is False


def test_delete_only_removes_target():
    mem.save("keep", "this stays")
    mem.save("remove", "this goes")
    mem.delete("remove")
    rows = mem.list_all()
    assert len(rows) == 1
    assert rows[0]["key"] == "keep"


# ── delete_matching ───────────────────────────────────────────────────────────

def test_delete_matching_removes_best_match():
    mem.save("portfolio project", "Next.js portfolio site")
    deleted = mem.delete_matching("portfolio")
    assert deleted is not None
    assert deleted["key"] == "portfolio project"
    assert mem.list_all() == []


def test_delete_matching_returns_none_when_empty():
    result = mem.delete_matching("nothing here")
    assert result is None
