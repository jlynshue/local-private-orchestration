"""SQLite (and optionally SQLCipher) database for privacy-agent.

H5 — encrypted at rest from day 1. When ``sqlcipher3`` is installed, ``open_db``
returns an encrypted connection keyed by the supplied passphrase. When not
installed, falls back to plain ``sqlite3`` and emits a warning. The DB then
relies on FileVault for at-rest protection — operationally fine for Phase 1
soak, but should be remediated before Phase 2 starts.

Schema covers:
- files / files_fts: indexed corpus + FTS5 virtual table for BM25 search
- consent: consent records with M5 time-window leases
- audit: append-only with SHA-256 hash chain (NFR-AUD-1, M6 provenance)
- classification_rules: persisted rule overrides
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

try:
    import sqlcipher3 as _sqlcipher  # type: ignore[import-not-found]

    HAS_SQLCIPHER = True
except ImportError:
    HAS_SQLCIPHER = False


Connection = Union[sqlite3.Connection, "Any"]


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    abs_path TEXT PRIMARY KEY,
    volume_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    title TEXT,
    file_type TEXT,
    size_bytes INTEGER NOT NULL,
    modified_at TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    classification TEXT NOT NULL,
    pii_redactions_applied INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_volume ON files(volume_id);
CREATE INDEX IF NOT EXISTS idx_files_classification ON files(classification);
CREATE INDEX IF NOT EXISTS idx_files_relative ON files(volume_id, relative_path);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    abs_path UNINDEXED,
    title,
    content,
    file_type UNINDEXED,
    volume_id UNINDEXED,
    tokenize = 'porter unicode61'
);

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
CREATE INDEX IF NOT EXISTS idx_consent_expires ON consent(expires_at);

CREATE TABLE IF NOT EXISTS audit (
    entry_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    orchestrator TEXT NOT NULL,
    query TEXT,
    paths_accessed TEXT,
    data_returned TEXT NOT NULL,
    bytes_returned INTEGER NOT NULL,
    consent_id TEXT,
    pii_redactions_applied INTEGER NOT NULL DEFAULT 0,
    hook_decision TEXT,
    provenance_id TEXT,
    hash_chain TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    sequence_num INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_sequence ON audit(sequence_num);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit(action);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit(severity);

CREATE TABLE IF NOT EXISTS classification_rules (
    rule_id TEXT PRIMARY KEY,
    pattern TEXT NOT NULL,
    classification TEXT NOT NULL,
    reason TEXT,
    auto_detected INTEGER NOT NULL DEFAULT 0
);
"""


def open_db(db_path: Path, encryption_key: Optional[str] = None) -> Connection:
    """Open or create the privacy-agent SQLite database.

    Args:
        db_path: Path to the database file. Parent directory created if missing.
        encryption_key: Optional passphrase for SQLCipher. If sqlcipher3 is not
            installed, a warning is logged and plain sqlite3 is used instead.

    Returns:
        A DB-API 2.0 Connection (sqlite3 or sqlcipher3).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if encryption_key and HAS_SQLCIPHER:
        conn = _sqlcipher.connect(str(db_path))
        # Quote escaping: SQLCipher PRAGMA key takes a string literal.
        # Doubling single quotes to defend against keys containing them.
        safe_key = encryption_key.replace("'", "''")
        conn.execute(f"PRAGMA key = '{safe_key}';")
        conn.execute("PRAGMA cipher_compatibility = 4;")
    else:
        if encryption_key and not HAS_SQLCIPHER:
            logger.warning(
                "encryption_key supplied but sqlcipher3 is not installed — "
                "falling back to plain sqlite3 (depends on FileVault for at-rest "
                "protection). Install with: pip install sqlcipher3-binary"
            )
        conn = sqlite3.connect(str(db_path))

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    # NFR-AUD-3: 0600 perms on the DB file. Best-effort — fails silently on
    # filesystems that don't support chmod (e.g. some network mounts).
    try:
        db_path.chmod(0o600)
    except (OSError, FileNotFoundError):  # pragma: no cover
        pass

    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def close_db(conn: Connection) -> None:
    conn.close()


def schema_tables(conn: Connection) -> set[str]:
    """Helper for tests — return the set of table/virtual-table names present."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    )
    return {row["name"] for row in cur.fetchall()}


def is_encrypted(conn: Connection) -> bool:
    """True if the connection is a SQLCipher connection. Best-effort."""
    return HAS_SQLCIPHER and isinstance(conn, _sqlcipher.Connection)  # type: ignore[attr-defined]
