"""PII redactor — regex pass over outbound text fields.

NFR-PRIV-3: every text field crossing the MCP boundary passes through this
class. The redactor is the *first* layer of a layered defense. Phase 2 adds
H1 (local-LLM gate) and M4 (user-corpus NER) on top; this module is designed
to compose with them rather than replace them.

H7: canary patterns are tracked separately. A canary hit yields severity=critical
and is intended to trigger an audit-log entry tagged ``canary_hit`` — the call
site (typically the post-tool-use hook or audit forwarder) is responsible for
emitting that audit event.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml


@dataclass(frozen=True)
class PatternSpec:
    name: str
    regex: re.Pattern
    severity: str  # low | medium | high | critical


@dataclass(frozen=True)
class RedactionResult:
    text: str
    redactions_applied: int
    canary_hits: int
    hit_types: tuple[str, ...]  # set of pattern names that matched (sorted)


class PIIRedactor:
    """Regex-based redactor with separate canary tracking."""

    def __init__(
        self,
        patterns: Iterable[PatternSpec] = (),
        canary_patterns: Iterable[PatternSpec] = (),
    ) -> None:
        self._patterns: tuple[PatternSpec, ...] = tuple(patterns)
        self._canary_patterns: tuple[PatternSpec, ...] = tuple(canary_patterns)

    @classmethod
    def from_yaml(cls, path: Path) -> "PIIRedactor":
        raw = yaml.safe_load(path.read_text())
        patterns = [_compile(p) for p in raw.get("patterns", [])]
        canary = [_compile(p) for p in raw.get("canary_patterns", [])]
        return cls(patterns, canary)

    def scrub(self, text: str) -> RedactionResult:
        """Apply all patterns. Returns (redacted_text, stats).

        Patterns are applied in declared order. A pattern that matches inside
        an already-redacted token will not double-redact (the redaction marker
        contains characters that won't match typical PII patterns).
        """
        if not text:
            return RedactionResult(text="", redactions_applied=0, canary_hits=0, hit_types=())

        out = text
        total = 0
        canary_count = 0
        hit_types: set[str] = set()

        # H7: canaries first — they are the highest-severity signal.
        for spec in self._canary_patterns:
            count = len(spec.regex.findall(out))
            if count:
                canary_count += count
                hit_types.add(spec.name)
                out = spec.regex.sub(f"[REDACTED:{spec.name}]", out)

        for spec in self._patterns:
            count = len(spec.regex.findall(out))
            if count:
                total += count
                hit_types.add(spec.name)
                out = spec.regex.sub(f"[REDACTED:{spec.name}]", out)

        return RedactionResult(
            text=out,
            redactions_applied=total,
            canary_hits=canary_count,
            hit_types=tuple(sorted(hit_types)),
        )

    def has_canary_hit(self, text: str) -> bool:
        """Fast check used by post-tool-use safety nets."""
        return any(spec.regex.search(text) for spec in self._canary_patterns)


def _compile(raw: dict) -> PatternSpec:
    flags = re.IGNORECASE if raw.get("ignore_case", False) else 0
    return PatternSpec(
        name=raw["name"],
        regex=re.compile(raw["regex"], flags),
        severity=raw.get("severity", "low"),
    )


def default_redactor(repo_root: Optional[Path] = None) -> PIIRedactor:
    """Convenience: load the shipped ``config/default_pii_patterns.yaml``."""
    if repo_root is None:
        # privacy-agent/src/privacy_agent/redactor.py → privacy-agent/
        repo_root = Path(__file__).resolve().parents[2]
    return PIIRedactor.from_yaml(repo_root / "config" / "default_pii_patterns.yaml")
