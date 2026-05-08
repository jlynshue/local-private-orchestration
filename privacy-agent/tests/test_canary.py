"""Tests for the canary subsystem (H7)."""
from __future__ import annotations

from pathlib import Path


from privacy_agent.audit import AuditLogger
from privacy_agent.canary import CanaryWatcher, list_canaries, seed_canaries
from privacy_agent.redactor import default_redactor


def test_seed_creates_files_with_markers(tmp_path: Path):
    seeded = seed_canaries(tmp_path / "canaries", count=3)
    assert len(seeded) == 3
    for cf in seeded:
        p = Path(cf.abs_path)
        assert p.exists()
        content = p.read_text()
        assert f"CANARY-{cf.canary_id}" in content


def test_seeded_files_are_0600(tmp_path: Path):
    import stat

    seeded = seed_canaries(tmp_path / "canaries", count=1)
    mode = Path(seeded[0].abs_path).stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_list_canaries_recovers_metadata(tmp_path: Path):
    seed_dir = tmp_path / "canaries"
    original = seed_canaries(seed_dir, count=2)
    listed = list_canaries(seed_dir)
    listed_ids = {c.canary_id for c in listed}
    original_ids = {c.canary_id for c in original}
    assert original_ids <= listed_ids


def test_list_canaries_empty_when_dir_missing(tmp_path: Path):
    assert list_canaries(tmp_path / "nope") == []


def test_watcher_logs_critical_on_canary_hit(conn, tmp_path: Path):
    audit = AuditLogger(conn)
    redactor = default_redactor()
    watcher = CanaryWatcher(redactor, audit)

    seeded = seed_canaries(tmp_path / "canaries", count=1)
    payload = f"some text containing CANARY-{seeded[0].canary_id} marker"
    hits = watcher.check_outbound(payload, orchestrator="claude_code", action="search")
    assert hits >= 1

    rows = audit.query(severity_filter="critical", limit=10)
    assert len(rows) == 1
    assert rows[0].action == "canary_hit"
    assert rows[0].severity == "critical"


def test_watcher_no_hit_no_audit(conn):
    audit = AuditLogger(conn)
    watcher = CanaryWatcher(default_redactor(), audit)
    hits = watcher.check_outbound(
        "totally innocent payload", orchestrator="claude_code", action="search"
    )
    assert hits == 0
    assert audit.query(severity_filter="critical") == []


def test_watcher_handles_empty_payload(conn):
    audit = AuditLogger(conn)
    watcher = CanaryWatcher(default_redactor(), audit)
    assert watcher.check_outbound("", orchestrator="claude_code", action="search") == 0


def test_canary_redacted_in_payload(tmp_path: Path):
    """When the redactor processes canary payload, the marker must be masked."""
    seeded = seed_canaries(tmp_path / "canaries", count=1)
    redactor = default_redactor()
    text = f"leaked CANARY-{seeded[0].canary_id} into output"
    res = redactor.scrub(text)
    assert "[REDACTED:CANARY]" in res.text
    assert seeded[0].canary_id not in res.text
    assert res.canary_hits == 1
