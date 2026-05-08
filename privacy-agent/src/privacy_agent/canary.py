"""Canary / honeytoken subsystem (H7).

Plant decoy "sensitive" files containing unique markers (``CANARY-<ID>``).
The redactor already detects them as the highest-severity tier. This module
seeds the canary corpus and provides a helper that, given any text, emits
critical audit events when a canary pattern is found.

Operationally: the operator runs ``privacy-cli canary seed`` once at setup,
and the post-tool-use hook checks every outbound payload for canary patterns
via ``CanaryWatcher.check_outbound``. A canary appearing in a payload that
left the host is the strongest possible signal that the privacy boundary has
broken.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .audit import AuditLogger
from .redactor import PIIRedactor


CANARY_FILE_TEMPLATES = [
    # Each template is a content snippet; ``{id}`` is replaced with a unique ID.
    (
        "Q4 quarterly review (DRAFT — do not distribute)\n"
        "Account: 4111-1111-1111-1111\n"
        "Reference: CANARY-{id}\n"
        "SSN on file: 999-67-{tail}\n"
        "Total: $9,876.54\n"
    ),
    (
        "Internal memo: project budget update\n"
        "Marker: CANARY-{id}\n"
        "Approved by: jane.canary@example.test\n"
    ),
    (
        "Tax filing draft (FY2024)\n"
        "Filer SSN: 999-65-{tail}\n"
        "Tracking: CANARY-{id}\n"
    ),
]


@dataclass(frozen=True)
class CanaryFile:
    relative_path: str
    canary_id: str
    abs_path: str


def seed_canaries(target_dir: Path, count: int = 3) -> list[CanaryFile]:
    """Plant ``count`` canary files under ``target_dir``. Returns metadata.

    The file content is deliberately mundane-looking: nothing in the file
    identifies it as a canary except the embedded marker, which is
    indistinguishable from a legitimate identifier to a casual reader. The
    redactor recognizes the marker; routine search results do not surface
    the files because they are placed in a hidden subdirectory.
    """
    target_dir = target_dir.expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    seeded: list[CanaryFile] = []
    for i in range(count):
        canary_id = secrets.token_hex(4).upper()
        tail = secrets.choice(("0001", "0002", "0003", "0004", "0005"))
        template = CANARY_FILE_TEMPLATES[i % len(CANARY_FILE_TEMPLATES)]
        content = template.format(id=canary_id, tail=tail)

        # Filenames don't betray their nature.
        filename = f"q4_review_draft_{canary_id[:4].lower()}.txt"
        path = target_dir / filename
        path.write_text(content)
        # 0600 — same posture as the audit DB. A future enumerator from another
        # user account on the host would still see directory entries, but not
        # the contents.
        try:
            path.chmod(0o600)
        except OSError:  # pragma: no cover
            pass

        seeded.append(
            CanaryFile(
                relative_path=filename,
                canary_id=canary_id,
                abs_path=str(path),
            )
        )
    return seeded


class CanaryWatcher:
    """Wires the canary detector to the audit log.

    The redactor surfaces canary hits via ``RedactionResult.canary_hits``. This
    class records a critical audit event whenever a hit is observed in a
    payload that is about to leave the privacy boundary.
    """

    def __init__(self, redactor: PIIRedactor, audit: AuditLogger):
        self.redactor = redactor
        self.audit = audit

    def check_outbound(
        self,
        payload_text: str,
        *,
        orchestrator: str,
        action: str,
        provenance_id: Optional[str] = None,
    ) -> int:
        """Inspect a payload that is about to be returned. Returns canary count.

        When a canary marker is present, a ``canary_hit`` audit entry is
        recorded with severity=critical. The caller decides whether to also
        block the response (typical post-tool-use hook behavior).
        """
        if not payload_text:
            return 0
        if not self.redactor.has_canary_hit(payload_text):
            return 0

        result = self.redactor.scrub(payload_text)
        self.audit.log(
            "canary_hit",
            orchestrator=orchestrator,
            severity="critical",
            data_returned="redacted",
            bytes_returned=len(payload_text),
            provenance_id=provenance_id,
            paths_accessed=[],  # canary may have been embedded in a payload, not a path
        )
        return result.canary_hits


def list_canaries(seed_dir: Path) -> list[CanaryFile]:
    """Enumerate currently-seeded canary files under ``seed_dir``."""
    seed_dir = seed_dir.expanduser()
    if not seed_dir.exists():
        return []
    out: list[CanaryFile] = []
    for p in sorted(seed_dir.glob("*.txt")):
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Naive parse — find the CANARY-<id> token.
        for line in content.splitlines():
            line = line.strip()
            if "CANARY-" in line:
                token = line.split("CANARY-", 1)[1].split()[0].rstrip(",.;:")
                out.append(
                    CanaryFile(
                        relative_path=p.name,
                        canary_id=token,
                        abs_path=str(p),
                    )
                )
                break
    return out
