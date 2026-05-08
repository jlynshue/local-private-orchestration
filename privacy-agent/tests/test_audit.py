"""Tests for the append-only audit log with hash chain."""
from __future__ import annotations

import pytest

from privacy_agent.audit import GENESIS_HASH, AuditLogger


@pytest.fixture
def logger(conn):
    return AuditLogger(conn)


def test_first_entry_chains_from_genesis(logger):
    e = logger.log("search", "claude_code", query="taxes", data_returned="snippet")
    assert e.hash_chain != GENESIS_HASH
    assert len(e.hash_chain) == 64  # SHA-256 hex
    valid, broken = logger.verify_chain_integrity()
    assert valid is True
    assert broken == []


def test_subsequent_entries_chain(logger):
    e1 = logger.log("search", "claude_code", query="q1")
    e2 = logger.log("search", "claude_code", query="q2")
    e3 = logger.log("read", "codex", paths_accessed=["/x/a.txt"])
    assert e1.hash_chain != e2.hash_chain != e3.hash_chain
    valid, broken = logger.verify_chain_integrity()
    assert valid is True
    assert broken == []


def test_provenance_id_round_trip(logger):
    """M6 — provenance survives the chain."""
    logger.log(
        "search",
        "claude_code",
        provenance_id="prov-abc-123",
        bytes_returned=42,
    )
    rows = logger.query(limit=1)
    assert rows[0].provenance_id == "prov-abc-123"


def test_canary_hit_severity(logger):
    e = logger.log(
        "canary_hit",
        "claude_code",
        severity="critical",
        paths_accessed=["/Volumes/Backup/canary_001.txt"],
    )
    assert e.severity == "critical"
    rows = logger.query(severity_filter="critical", limit=10)
    assert len(rows) == 1


def test_query_filters(logger):
    logger.log("search", "claude_code")
    logger.log("read", "codex")
    logger.log("index", "goose")
    assert len(logger.query(action_filter="search")) == 1
    assert len(logger.query(action_filter="read")) == 1
    assert len(logger.query()) == 3


def test_query_orders_descending_by_sequence(logger):
    logger.log("search", "claude_code", query="first")
    logger.log("search", "claude_code", query="second")
    logger.log("search", "claude_code", query="third")
    rows = logger.query(limit=10)
    queries = [r.query for r in rows]
    assert queries == ["third", "second", "first"]


def test_tamper_detection_flips_hash(logger, conn):
    logger.log("search", "claude_code", query="alpha")
    logger.log("search", "claude_code", query="bravo")
    # Tamper: rewrite the query of entry 1 directly in the DB.
    conn.execute("UPDATE audit SET query = 'TAMPERED' WHERE sequence_num = 1")
    conn.commit()
    valid, broken = logger.verify_chain_integrity()
    assert valid is False
    assert len(broken) >= 1


def test_tamper_detection_flips_data_returned(logger, conn):
    """Even small field changes break the chain."""
    logger.log("search", "claude_code", data_returned="snippet")
    logger.log("search", "claude_code", data_returned="metadata_only")
    conn.execute("UPDATE audit SET bytes_returned = 999 WHERE sequence_num = 2")
    conn.commit()
    valid, broken = logger.verify_chain_integrity()
    assert valid is False
    assert len(broken) >= 1


def test_query_limit_capped(logger):
    """Limit must be capped at 500 to prevent expensive queries."""
    for i in range(10):
        logger.log("search", "claude_code", query=f"q{i}")
    # Asking for more than 500 should still work (capped, not errored).
    rows = logger.query(limit=10000)
    assert len(rows) == 10
