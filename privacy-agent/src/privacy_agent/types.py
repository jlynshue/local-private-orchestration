"""Data types for privacy-agent.

Frozen dataclasses double as the return-schema whitelist (NFR-PRIV-4): no field
not declared here can appear in an MCP response. The serialization layer in
``server.py`` validates against these shapes before sending payloads to any
orchestrator.

Path policy (NFR-PRIV-2): nothing that crosses the MCP boundary contains an
absolute filesystem path. All external-facing types use ``volume_id`` and
``relative_path``. Absolute paths exist only inside the audit log and the
internal DB metadata table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


CLASSIFICATION_LEVELS = ("public", "internal", "confidential", "restricted", "canary")
ORDERED_LEVELS = ("public", "internal", "confidential", "restricted")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classification_rank(level: str) -> int:
    """Return ordering rank: public(0) < internal(1) < confidential(2) < restricted(3).

    `canary` is special — not in the comparable ladder, raises if compared.
    """
    if level not in ORDERED_LEVELS:
        raise ValueError(f"classification {level!r} is not in the ordered ladder")
    return ORDERED_LEVELS.index(level)


@dataclass(frozen=True)
class IndexStats:
    total_files: int = 0
    indexed_files: int = 0
    failed_files: int = 0
    last_indexed_at: Optional[str] = None
    file_type_counts: dict[str, int] = field(default_factory=dict)
    total_indexed_bytes: int = 0


@dataclass(frozen=True)
class VolumeInfo:
    volume_id: str
    name: str
    total_bytes: int
    available_bytes: int
    indexed: bool
    consent_status: str  # granted | pending | denied | expired
    index_stats: Optional[IndexStats] = None


@dataclass(frozen=True)
class ConsentRecord:
    consent_id: str
    path_pattern: str
    scope: str  # index | read | search
    granted: bool
    granted_at: str
    expires_at: Optional[str]
    granularity: str  # file | directory | volume
    revoked_at: Optional[str] = None


@dataclass(frozen=True)
class AuditEntry:
    """One row in the append-only audit log.

    `paths_accessed` carries absolute paths — this dataclass is internal and
    its serialization is restricted to the audit DB. It is never returned via
    MCP. (NFR-PRIV-2)
    """
    entry_id: str
    timestamp: str
    action: str  # search | read | index | classify | consent_grant
                 # | consent_revoke | hook_block | canary_hit
    orchestrator: str  # claude_code | codex | goose | manual
    query: Optional[str]
    paths_accessed: list[str]
    data_returned: str  # snippet | excerpt | metadata_only | full_content | none
    bytes_returned: int
    consent_id: Optional[str]
    pii_redactions_applied: int
    hook_decision: Optional[str]  # allow | block | n/a
    provenance_id: Optional[str]
    hash_chain: str  # SHA-256 of previous + this entry
    severity: str = "info"  # info | warning | critical


@dataclass(frozen=True)
class SearchResult:
    """Returned to orchestrators. NFR-PRIV-2: no absolute path."""
    volume_id: str
    relative_path: str
    title: str
    snippet: str  # ≤ snippet_max_chars, post-redaction
    score: float
    classification: str
    file_type: str
    size_bytes: int
    modified_at: str
    indexed_at: str
    pii_redactions_applied: int
    provenance_id: str


@dataclass(frozen=True)
class ExcerptResult:
    """Returned only when enable_excerpt_tool=true and consent is active."""
    volume_id: str
    relative_path: str
    excerpt: str  # ≤ max_chars (default 500), post-redaction
    page: Optional[int]
    start_line: Optional[int]
    end_line: Optional[int]
    pii_redactions_applied: int
    classification: str
    provenance_id: str


@dataclass(frozen=True)
class ClassificationRule:
    rule_id: str
    pattern: str  # glob, e.g. "*/tax-returns/*"
    classification: str
    reason: str
    auto_detected: bool


@dataclass
class ExtractedContent:
    """Internal — the raw output of an extractor before redaction."""
    text: str
    title: str
    file_type: str
    page_count: Optional[int] = None
    line_count: Optional[int] = None
    extraction_errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FileEntry:
    """Internal — what the indexer yields for each file in a crawl."""
    abs_path: str
    volume_id: str
    relative_path: str
    size_bytes: int
    modified_at: str
    file_type: str  # MIME or extension
