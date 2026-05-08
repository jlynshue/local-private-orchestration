"""Sensitivity classification: maps file paths to one of the 4 levels.

Levels (ordered): public < internal < confidential < restricted.
Path rules from config or persisted overrides take precedence over the default
level. When multiple rules match, the highest-classification rule wins
(ratchet upward only — never downgrade by accident).

Phase 2 will add content-based heuristics (currently stubbed in
``classify_content``); for Phase 1 we are path-only.
"""
from __future__ import annotations

import fnmatch
import uuid
from typing import Optional

from .config import ClassificationConfig
from .types import (
    ClassificationRule,
    ORDERED_LEVELS,
    classification_rank,
)


class Classifier:
    def __init__(self, cfg: ClassificationConfig, overrides: Optional[list[ClassificationRule]] = None):
        if cfg.default_level not in ORDERED_LEVELS:
            raise ValueError(f"default_level must be one of {ORDERED_LEVELS}")
        self._default = cfg.default_level
        self._rules: list[ClassificationRule] = []
        for r in cfg.rules:
            self._rules.append(
                ClassificationRule(
                    rule_id=str(uuid.uuid4()),
                    pattern=r.pattern,
                    classification=r.level,
                    reason="from config",
                    auto_detected=False,
                )
            )
        if overrides:
            self._rules.extend(overrides)

    def classify_path(self, path: str) -> str:
        """Return the highest-classification rule that matches, or the default."""
        best = self._default
        best_rank = classification_rank(best)
        for rule in self._rules:
            if rule.classification == "canary":
                # canary tier is set explicitly by the canary subsystem, not via rules
                continue
            if fnmatch.fnmatch(path, rule.pattern):
                rank = classification_rank(rule.classification)
                if rank > best_rank:
                    best = rule.classification
                    best_rank = rank
        return best

    def classify_content(self, content: str, path: str) -> str:  # pragma: no cover
        """Phase 2 hook — content-based heuristics. Currently delegates to path."""
        return self.classify_path(path)

    def add_rule(
        self,
        pattern: str,
        level: str,
        reason: str = "manual",
        auto_detected: bool = False,
    ) -> ClassificationRule:
        if level not in ORDERED_LEVELS:
            raise ValueError(f"level must be one of {ORDERED_LEVELS}, got {level!r}")
        rule = ClassificationRule(
            rule_id=str(uuid.uuid4()),
            pattern=pattern,
            classification=level,
            reason=reason,
            auto_detected=auto_detected,
        )
        self._rules.append(rule)
        return rule

    @property
    def rules(self) -> tuple[ClassificationRule, ...]:
        return tuple(self._rules)
