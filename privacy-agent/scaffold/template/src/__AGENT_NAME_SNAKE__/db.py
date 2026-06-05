"""SQLite database setup — WAL, 0600 perms, consent + audit tables."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    entry_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    orchestrator TEXT NOT NULL,
    hash_chain TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    payload TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_seq ON audit(sequence_num);

CREATE TABLE IF NOT EXISTS consent (
    consent_id TEXT PRIMARY KEY,
    path_pattern TEXT NOT NULL,
    scope TEXT NOT NULL,
    granted INTEGER NOT NULL,
    granted_at TEXT NOT NULL,
    expires_at TEXT,
    granularity TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_consent_pattern ON consent(path_pattern);
"""


def open_db(db_path: Path, encryption_key: Optional[str] = None) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA)
    conn.commit()
    try:
        db_path.chmod(0o600)
    except OSError:
        pass
    return conn
