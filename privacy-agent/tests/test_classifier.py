"""Tests for the path-based classifier."""
from __future__ import annotations

import pytest

from privacy_agent.classifier import Classifier
from privacy_agent.config import ClassificationConfig, ClassificationRuleConfig


def _config_with(rules):
    return ClassificationConfig(
        default_level="internal",
        rules=[ClassificationRuleConfig(pattern=p, level=lvl) for p, lvl in rules],
    )


def test_default_when_no_rules_match():
    c = Classifier(_config_with([]))
    assert c.classify_path("/tmp/random/file.txt") == "internal"


def test_path_rule_match():
    c = Classifier(_config_with([("*/medical/*", "restricted")]))
    assert c.classify_path("/Volumes/Backup/medical/labs.pdf") == "restricted"


def test_higher_classification_wins():
    """Two rules match — must pick the more sensitive one (ratchet up only)."""
    c = Classifier(
        _config_with(
            [
                ("*/tax*", "confidential"),
                ("*/tax/medical*", "restricted"),
            ]
        )
    )
    assert c.classify_path("/x/tax/medical/2024.pdf") == "restricted"


def test_rejects_unknown_default_level():
    cfg = ClassificationConfig(default_level="ultra")
    with pytest.raises(ValueError):
        Classifier(cfg)


def test_add_rule_validates():
    c = Classifier(_config_with([]))
    with pytest.raises(ValueError):
        c.add_rule(pattern="*/x/*", level="not-a-level")


def test_add_rule_appended_and_used():
    c = Classifier(_config_with([]))
    c.add_rule(pattern="*/secret/*", level="restricted", reason="user override")
    assert c.classify_path("/Volumes/Backup/secret/foo.txt") == "restricted"


def test_canary_rule_is_ignored_for_path_classification():
    """Canary tier is set by the canary subsystem, not via rules."""
    cfg = ClassificationConfig(default_level="internal")
    c = Classifier(cfg)
    # Manually inject a canary rule via overrides — should be skipped.
    from privacy_agent.types import ClassificationRule

    c._rules.append(  # type: ignore[attr-defined]
        ClassificationRule(
            rule_id="canary-test",
            pattern="*/canary/*",
            classification="canary",
            reason="test",
            auto_detected=False,
        )
    )
    assert c.classify_path("/Volumes/Backup/canary/x") == "internal"
