"""Tests for the SQLite/SQLCipher abstraction."""
from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from privacy_agent import db


def test_open_creates_file_and_schema(tmp_db_path: Path):
    conn = db.open_db(tmp_db_path)
    try:
        assert tmp_db_path.exists()
        tables = db.schema_tables(conn)
        # All four core tables + FTS5 virtual table.
        assert {"files", "files_fts", "consent", "audit", "classification_rules"} <= tables
    finally:
        db.close_db(conn)


def test_db_file_is_0600(tmp_db_path: Path):
    conn = db.open_db(tmp_db_path)
    try:
        mode = tmp_db_path.stat().st_mode
        # NFR-AUD-3: 0600. Mask off the file-type bits, compare permission bits.
        assert stat.S_IMODE(mode) == 0o600
    finally:
        db.close_db(conn)


def test_wal_journal_mode(tmp_db_path: Path):
    conn = db.open_db(tmp_db_path)
    try:
        cur = conn.execute("PRAGMA journal_mode;")
        assert cur.fetchone()[0].lower() == "wal"
    finally:
        db.close_db(conn)


def test_fts5_inserts_and_searches(tmp_db_path: Path):
    conn = db.open_db(tmp_db_path)
    try:
        conn.execute(
            "INSERT INTO files_fts(abs_path, title, content, file_type, volume_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("/x/a.txt", "alpha", "the quick brown fox", "txt", "vol1"),
        )
        conn.execute(
            "INSERT INTO files_fts(abs_path, title, content, file_type, volume_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("/x/b.txt", "bravo", "lazy dog jumped over", "txt", "vol1"),
        )
        conn.commit()

        cur = conn.execute(
            "SELECT abs_path, snippet(files_fts, 2, '<', '>', '...', 8) AS snip "
            "FROM files_fts WHERE files_fts MATCH ? ORDER BY rank",
            ("fox",),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["abs_path"] == "/x/a.txt"
        assert "<fox>" in rows[0]["snip"]
    finally:
        db.close_db(conn)


def test_files_table_constraints(tmp_db_path: Path):
    conn = db.open_db(tmp_db_path)
    try:
        conn.execute(
            "INSERT INTO files (abs_path, volume_id, relative_path, size_bytes, "
            "modified_at, indexed_at, classification) VALUES (?,?,?,?,?,?,?)",
            ("/x/a.txt", "vol1", "a.txt", 12, "2026-01-01", "2026-01-02", "internal"),
        )
        conn.commit()

        # Re-insert same primary key should fail.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO files (abs_path, volume_id, relative_path, size_bytes, "
                "modified_at, indexed_at, classification) VALUES (?,?,?,?,?,?,?)",
                ("/x/a.txt", "vol1", "a.txt", 13, "2026-01-01", "2026-01-02", "internal"),
            )
    finally:
        db.close_db(conn)


def test_audit_sequence_unique(tmp_db_path: Path):
    conn = db.open_db(tmp_db_path)
    try:
        conn.execute(
            "INSERT INTO audit (entry_id, timestamp, action, orchestrator, "
            "data_returned, bytes_returned, hash_chain, sequence_num) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("e1", "2026-01-01", "search", "claude_code", "snippet", 100, "h1", 1),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO audit (entry_id, timestamp, action, orchestrator, "
                "data_returned, bytes_returned, hash_chain, sequence_num) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("e2", "2026-01-01", "search", "claude_code", "snippet", 100, "h2", 1),
            )
    finally:
        db.close_db(conn)


def test_open_with_key_falls_back_when_no_sqlcipher(tmp_db_path: Path, caplog):
    """When sqlcipher3 is not installed, supplying a key must not crash; warn instead."""
    if db.HAS_SQLCIPHER:
        pytest.skip("sqlcipher3 is installed — fallback path not exercised")
    with caplog.at_level("WARNING", logger="privacy_agent.db"):
        conn = db.open_db(tmp_db_path, encryption_key="hunter2")
        try:
            assert tmp_db_path.exists()
            assert any("sqlcipher3" in rec.message for rec in caplog.records)
        finally:
            db.close_db(conn)


@pytest.mark.skipif(not db.HAS_SQLCIPHER, reason="requires sqlcipher3-binary")
def test_sqlcipher_round_trip(tmp_db_path: Path):
    """When SQLCipher is installed, a wrong key on reopen must fail."""
    key = "correct horse battery staple"
    conn = db.open_db(tmp_db_path, encryption_key=key)
    conn.execute(
        "INSERT INTO files (abs_path, volume_id, relative_path, size_bytes, "
        "modified_at, indexed_at, classification) VALUES (?,?,?,?,?,?,?)",
        ("/x/a.txt", "vol1", "a.txt", 12, "2026-01-01", "2026-01-02", "internal"),
    )
    conn.commit()
    db.close_db(conn)

    # Wrong key must fail to read.
    with pytest.raises(Exception):  # sqlcipher3 raises DatabaseError
        bad = db.open_db(tmp_db_path, encryption_key="wrong key")
        bad.execute("SELECT * FROM files").fetchall()
        db.close_db(bad)
