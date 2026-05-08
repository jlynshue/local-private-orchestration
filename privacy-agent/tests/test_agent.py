"""Tests for the PrivacyAgent core (M1.5/M1.6 handler logic, no MCP transport)."""
from __future__ import annotations

from pathlib import Path

import pytest

from privacy_agent.agent import (
    ClassificationBlocked,
    ConsentRequired,
    PrivacyAgent,
    ToolDisabled,
)
from privacy_agent.config import (
    ClassificationConfig,
    ClassificationRuleConfig,
    Config,
    ConsentConfig,
    ProfileOverride,
    ProfilesConfig,
)


def _make_config(**overrides):
    cfg = Config()
    cfg.consent = ConsentConfig(
        default_expiry_hours=168,
        excerpt_lease_minutes=30,
        require_per_volume_consent=True,
    )
    cfg.classification = ClassificationConfig(
        default_level="internal",
        rules=[
            ClassificationRuleConfig("*/tax/*", "confidential"),
            ClassificationRuleConfig("*/medical/*", "restricted"),
        ],
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture
def agent(conn):
    return PrivacyAgent(conn, _make_config(), orchestrator="claude_code")


def _seed_volume(root: Path) -> None:
    (root / "memo.txt").write_text("Quarterly memo. Phone 555-867-5309 on file.")
    tax = root / "tax"
    tax.mkdir()
    (tax / "2024.txt").write_text("Federal tax return — SSN 123-45-6789, $5,000.")
    medical = root / "medical"
    medical.mkdir()
    (medical / "labs.txt").write_text("Lab results from quarterly checkup.")


def _grant_index(agent, path: Path) -> None:
    agent.consent.grant(str(path), "index", "volume")


def _grant_search(agent, path: Path) -> None:
    agent.consent.grant(str(path), "search", "volume")


# -- search handler --

def test_search_blocked_without_consent(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    _grant_index(agent, tmp_path)
    agent.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")

    with pytest.raises(ConsentRequired):
        agent.handle_search(query="quarterly", scope=str(tmp_path))


def test_search_returns_results_with_consent(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    _grant_index(agent, tmp_path)
    agent.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")
    _grant_search(agent, tmp_path)

    resp = agent.handle_search(query="quarterly", scope=str(tmp_path))
    assert resp.payload["count"] >= 1
    assert all("[REDACTED:" not in r["volume_id"] for r in resp.payload["results"])
    # NFR-PRIV-2: relative_path must not be absolute
    for r in resp.payload["results"]:
        assert not r["relative_path"].startswith("/")


def test_search_excludes_restricted_under_goose_profile(conn, tmp_path: Path):
    """M2: Goose profile caps at 'internal' — restricted (medical) must be filtered."""
    cfg = _make_config()
    cfg.profiles = ProfilesConfig(
        goose=ProfileOverride(enable_excerpt_tool=False, classification_cap="internal")
    )
    a = PrivacyAgent(conn, cfg, orchestrator="goose")
    _seed_volume(tmp_path)
    a.consent.grant(str(tmp_path), "index", "volume")
    a.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")
    a.consent.grant(str(tmp_path), "search", "volume")

    resp = a.handle_search(query="quarterly")
    classifications = {r["classification"] for r in resp.payload["results"]}
    assert "restricted" not in classifications
    assert "confidential" not in classifications


def test_search_audit_entry_has_provenance(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    _grant_index(agent, tmp_path)
    agent.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")
    _grant_search(agent, tmp_path)
    resp = agent.handle_search(query="quarterly", scope=str(tmp_path))

    rows = agent.audit.query(action_filter="search", limit=1)
    assert len(rows) == 1
    assert rows[0].provenance_id == resp.provenance_id


# -- index handler --

def test_index_blocked_without_consent(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    with pytest.raises(ConsentRequired):
        agent.handle_index_volume(volume_path=str(tmp_path))


def test_index_emits_audit_with_consent_id(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    rec = agent.consent.grant(str(tmp_path), "index", "volume")
    agent.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")
    rows = agent.audit.query(action_filter="index", limit=1)
    assert rows[0].consent_id == rec.consent_id


# -- excerpt handler --

def test_excerpt_disabled_by_default(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    _grant_index(agent, tmp_path)
    agent.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")

    with pytest.raises(ToolDisabled):
        agent.handle_read_excerpt(volume_id="vol_test", relative_path="memo.txt")


def test_excerpt_blocks_restricted_when_enabled(conn, tmp_path: Path):
    """Even with the tool enabled, a profile cap below restricted blocks medical reads."""
    cfg = _make_config()
    cfg.agent.enable_excerpt_tool = True
    cfg.profiles = ProfilesConfig(
        claude_code=ProfileOverride(
            enable_excerpt_tool=True, classification_cap="confidential"
        )
    )
    a = PrivacyAgent(conn, cfg, orchestrator="claude_code")
    _seed_volume(tmp_path)
    a.consent.grant(str(tmp_path), "index", "volume")
    a.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")

    medical_abs = str(tmp_path / "medical" / "labs.txt")
    a.consent.grant(medical_abs, "read", "file", window_seconds=60)
    with pytest.raises(ClassificationBlocked):
        a.handle_read_excerpt(volume_id="vol_test", relative_path="medical/labs.txt")


def test_excerpt_works_when_enabled_and_consented(conn, tmp_path: Path):
    cfg = _make_config()
    cfg.agent.enable_excerpt_tool = True
    cfg.profiles = ProfilesConfig(
        claude_code=ProfileOverride(enable_excerpt_tool=True, classification_cap="restricted")
    )
    a = PrivacyAgent(conn, cfg, orchestrator="claude_code")
    _seed_volume(tmp_path)
    a.consent.grant(str(tmp_path), "index", "volume")
    a.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")
    a.consent.grant(str(tmp_path / "memo.txt"), "read", "file", window_seconds=60)
    resp = a.handle_read_excerpt(volume_id="vol_test", relative_path="memo.txt")
    assert "Quarterly" in resp.payload["excerpt"]
    # PII must still be redacted in excerpt.
    assert "555-867-5309" not in resp.payload["excerpt"]
    assert "[REDACTED:PHONE]" in resp.payload["excerpt"]


# -- list_volumes / consent / audit_log handlers --

def test_list_volumes_no_absolute_paths(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    _grant_index(agent, tmp_path)
    agent.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")
    resp = agent.handle_list_volumes()
    payload = resp.payload
    for v in payload["volumes"]:
        assert "abs_path" not in v
        assert v["volume_id"] == "vol_test"


def test_get_consent_returns_pending_with_instructions(agent):
    resp = agent.handle_get_consent(path="/Volumes/Backup", scope="search", request=True)
    assert resp.payload["status"] == "pending"
    assert "privacy-cli" in resp.payload["instructions"]


def test_audit_log_excludes_paths_accessed(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    _grant_index(agent, tmp_path)
    agent.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")
    resp = agent.handle_audit_log(action_filter="index", limit=10)
    for entry in resp.payload["entries"]:
        # NFR-PRIV-2: paths_accessed (which contains absolute paths) is not exposed via MCP.
        assert "paths_accessed" not in entry


# -- classify handler --

def test_classify_get(agent):
    resp = agent.handle_classify(path="/Volumes/Backup/medical/labs.pdf")
    assert resp.payload["classification"] == "restricted"


def test_classify_set_persists(agent):
    resp = agent.handle_classify(
        path="*/special/*", set_level="confidential", reason="user override"
    )
    assert resp.payload["classification"] == "confidential"
    # Subsequent classify_path must reflect the new rule.
    assert agent.classifier.classify_path("/Volumes/Backup/special/file.txt") == "confidential"


def test_classify_invalid_level_raises(agent):
    with pytest.raises(ValueError):
        agent.handle_classify(path="*/x/*", set_level="ultra")


# -- file_summary handler --

def test_file_summary_returns_metadata_only(agent, tmp_path: Path):
    _seed_volume(tmp_path)
    _grant_index(agent, tmp_path)
    agent.handle_index_volume(volume_path=str(tmp_path), volume_id="vol_test")
    resp = agent.handle_file_summary(volume_id="vol_test", relative_path="memo.txt")
    assert "summary" in resp.payload
    assert "555-867-5309" not in resp.payload["summary"]
    assert "abs_path" not in resp.payload


# -- profile resolution (M2) --

def test_unknown_orchestrator_gets_strictest_profile(conn):
    cfg = _make_config()
    cfg.profiles = ProfilesConfig(
        goose=ProfileOverride(enable_excerpt_tool=False, classification_cap="internal")
    )
    a = PrivacyAgent(conn, cfg, orchestrator="random_unknown")
    assert a.profile.classification_cap == "internal"


def test_claude_code_profile_inherits_defaults(conn):
    cfg = _make_config()
    cfg.profiles = ProfilesConfig()  # claude_code default = no overrides
    a = PrivacyAgent(conn, cfg, orchestrator="claude_code")
    assert a.profile.classification_cap is None  # uncapped — uses agent default
