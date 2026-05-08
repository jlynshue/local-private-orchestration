"""Tests for config loading and validation."""
from __future__ import annotations

from pathlib import Path


from privacy_agent import config


def test_defaults_are_safe():
    cfg = config.Config()
    # Most important default: excerpt tool off (NFR-PRIV-1).
    assert cfg.agent.enable_excerpt_tool is False
    # Plus stdio bind (NFR-PORT-1) and snippet cap (NFR-PERF-2).
    assert cfg.agent.bind == "stdio"
    assert cfg.agent.snippet_max_chars == 200
    # Encryption on by default (H5).
    assert cfg.encryption.enabled is True
    # Canaries on by default (H7).
    assert cfg.canary.enabled is True
    # Goose ships stricter than claude_code (M2).
    assert cfg.profiles.goose.classification_cap == "internal"
    assert cfg.profiles.codex.classification_cap == "confidential"
    assert cfg.profiles.claude_code.classification_cap is None  # inherits


def test_validate_clean():
    cfg = config.Config()
    assert config.validate(cfg) == []


def test_validate_rejects_non_stdio_bind():
    cfg = config.Config()
    cfg.agent.bind = "tcp"
    errors = config.validate(cfg)
    assert any("stdio" in e for e in errors)


def test_validate_rejects_oversized_snippet():
    cfg = config.Config()
    cfg.agent.snippet_max_chars = 1000
    errors = config.validate(cfg)
    assert any("snippet_max_chars" in e for e in errors)


def test_validate_rejects_unknown_classification_level():
    cfg = config.Config()
    cfg.classification.default_level = "top-secret"
    errors = config.validate(cfg)
    assert any("default_level" in e for e in errors)


def test_validate_rejects_invalid_classification_rule():
    cfg = config.Config()
    cfg.classification.rules = [
        config.ClassificationRuleConfig(pattern="*/x/*", level="not-a-level")
    ]
    errors = config.validate(cfg)
    assert any("invalid level" in e for e in errors)


def test_validate_rejects_bad_profile_cap():
    cfg = config.Config()
    cfg.profiles.goose.classification_cap = "ultra"
    errors = config.validate(cfg)
    assert any("classification_cap" in e for e in errors)


def test_load_default_toml():
    """The shipped default.toml must parse cleanly and validate."""
    repo_root = Path(__file__).parent.parent
    cfg = config.load_config(repo_root / "config" / "default.toml")
    assert config.validate(cfg) == []
    # Spot-check that toml-driven values came through.
    assert cfg.agent.enable_excerpt_tool is False
    assert cfg.consent.excerpt_lease_minutes == 30
    assert cfg.canary.pattern_prefix == "CANARY-"
    medical_rule = next(
        (r for r in cfg.classification.rules if "medical" in r.pattern), None
    )
    assert medical_rule is not None
    assert medical_rule.level == "restricted"


def test_load_missing_file_returns_defaults(tmp_path: Path):
    cfg = config.load_config(tmp_path / "nonexistent.toml")
    assert config.validate(cfg) == []


def test_unknown_keys_dropped():
    """Extra keys in TOML should not crash the loader (forward-compat)."""
    raw = {
        "agent": {"snippet_max_chars": 150, "future_field": "ignored"},
        "consent": {"excerpt_lease_minutes": 15},
    }
    cfg = config.from_dict(raw)
    assert cfg.agent.snippet_max_chars == 150
    assert cfg.consent.excerpt_lease_minutes == 15
