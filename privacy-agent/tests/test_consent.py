"""Tests for the consent manager."""
from __future__ import annotations

import time

import pytest

from privacy_agent.config import ConsentConfig
from privacy_agent.consent import ConsentManager


@pytest.fixture
def manager(conn):
    return ConsentManager(conn, ConsentConfig(default_expiry_hours=168))


def test_grant_and_check_volume(manager):
    rec = manager.grant("/Volumes/Backup", "search", "volume")
    assert rec.scope == "search"
    found = manager.check("/Volumes/Backup/Tax/2024.pdf", "search")
    assert found is not None
    assert found.consent_id == rec.consent_id


def test_check_returns_none_for_uncovered_path(manager):
    manager.grant("/Volumes/Backup", "search", "volume")
    assert manager.check("/Volumes/Other/file.txt", "search") is None


def test_directory_scope(manager):
    manager.grant("/Volumes/Backup/Tax", "search", "directory")
    assert manager.check("/Volumes/Backup/Tax/2024.pdf", "search") is not None
    assert manager.check("/Volumes/Backup/Legal/contract.pdf", "search") is None


def test_file_scope_matches_only_exact(manager):
    manager.grant("/Volumes/Backup/x.pdf", "read", "file")
    assert manager.check("/Volumes/Backup/x.pdf", "read") is not None
    assert manager.check("/Volumes/Backup/y.pdf", "read") is None


def test_scope_separation(manager):
    """Search consent should not satisfy a read-scope check."""
    manager.grant("/Volumes/Backup", "search", "volume")
    assert manager.check("/Volumes/Backup/x.txt", "read") is None


def test_revoke(manager):
    rec = manager.grant("/Volumes/Backup", "search", "volume")
    assert manager.check("/Volumes/Backup/x", "search") is not None
    assert manager.revoke(rec.consent_id) is True
    assert manager.check("/Volumes/Backup/x", "search") is None
    # Idempotent: second revoke fails (no rows updated).
    assert manager.revoke(rec.consent_id) is False


def test_window_lease_expires(manager):
    """M5 — short window leases auto-expire on check."""
    manager.grant("/Volumes/Backup", "read", "volume", window_seconds=1)
    assert manager.check("/Volumes/Backup/x", "read") is not None
    time.sleep(1.1)
    assert manager.check("/Volumes/Backup/x", "read") is None


def test_cleanup_expired_marks_revoked(manager):
    manager.grant("/Volumes/Backup", "read", "volume", window_seconds=1)
    time.sleep(1.1)
    count = manager.cleanup_expired()
    assert count == 1
    # Re-running cleanup is idempotent.
    assert manager.cleanup_expired() == 0


def test_invalid_scope_raises(manager):
    with pytest.raises(ValueError):
        manager.grant("/x", "execute", "volume")
    with pytest.raises(ValueError):
        manager.check("/x", "execute")


def test_invalid_granularity_raises(manager):
    with pytest.raises(ValueError):
        manager.grant("/x", "search", "all-files")


def test_list_active_excludes_expired_and_revoked(manager):
    rec1 = manager.grant("/A", "search", "volume")
    rec2 = manager.grant("/B", "search", "volume", window_seconds=1)
    manager.grant("/C", "search", "volume")
    manager.revoke(rec1.consent_id)
    time.sleep(1.1)
    active = manager.list_active()
    ids = {r.consent_id for r in active}
    assert rec1.consent_id not in ids   # revoked
    assert rec2.consent_id not in ids   # expired
    assert len(active) == 1


def test_most_recent_wins_when_multiple_cover(manager):
    """If two consents both cover a path, the most recently granted should win."""
    manager.grant("/Volumes/Backup", "search", "volume")
    # Force a slightly later timestamp.
    time.sleep(0.01)
    rec2 = manager.grant("/Volumes/Backup", "search", "volume")
    found = manager.check("/Volumes/Backup/x", "search")
    assert found.consent_id == rec2.consent_id
