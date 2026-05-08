"""PrivacyAgent — the application core that the MCP server, CLI, and hooks all use.

The 8 MCP tools are thin wrappers around handlers on this class. Putting the
handlers here (rather than in ``server.py``) lets us:

- Unit-test handlers directly without a live MCP transport
- Reuse the same logic from ``privacy-cli`` (consent management, manual reindex)
- Keep ``server.py`` focused on protocol concerns

Per-orchestrator profiles (M2) are resolved via ``self.orchestrator``, set from
the ``PRIVACY_AGENT_ORCHESTRATOR`` env var at construction. Each orchestrator
launches its own MCP server process with a different value, so the profile is
fixed for the life of the connection.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from .audit import AuditLogger
from .canary import CanaryWatcher
from .classifier import Classifier
from .config import Config, ProfileOverride
from .consent import ConsentManager
from .db import open_db
from .extractors import ExtractorRegistry
from .extractors.base import ExtractorError
from .indexer import Indexer
from .redactor import PIIRedactor, default_redactor
from .search import SearchEngine
from .types import (
    ORDERED_LEVELS,
    classification_rank,
)

logger = logging.getLogger(__name__)


KNOWN_ORCHESTRATORS = ("claude_code", "codex", "goose", "manual")


class ToolDisabled(Exception):
    """Raised when a tool is disabled by config or profile."""


class ConsentRequired(Exception):
    """Raised when an action lacks the required consent."""


class ClassificationBlocked(Exception):
    """Raised when a result's classification exceeds the orchestrator's cap."""


@dataclass
class ToolResponse:
    """Wrapper around a tool's payload + the audit metadata it generated.

    The MCP server returns ``payload`` to the caller; the audit row is recorded
    as a side effect of constructing the response inside the handler.
    """
    payload: Any
    provenance_id: str


class PrivacyAgent:
    def __init__(
        self,
        conn,
        cfg: Config,
        redactor: Optional[PIIRedactor] = None,
        orchestrator: Optional[str] = None,
    ):
        self.conn = conn
        self.cfg = cfg
        self.redactor = redactor or default_redactor()
        self.classifier = Classifier(cfg.classification)
        self.consent = ConsentManager(conn, cfg.consent)
        self.audit = AuditLogger(conn)
        self.canary = CanaryWatcher(self.redactor, self.audit)
        self.registry = ExtractorRegistry()
        self.indexer = Indexer(
            conn, self.registry, self.classifier, self.redactor, cfg.extractors
        )
        self.search = SearchEngine(conn, self.redactor, cfg.agent)

        env_value = orchestrator or os.getenv("PRIVACY_AGENT_ORCHESTRATOR", "unknown")
        if env_value not in KNOWN_ORCHESTRATORS and env_value != "unknown":
            logger.warning(
                "unknown orchestrator %r — applying strictest profile", env_value
            )
        self.orchestrator = env_value

    # -- profile resolution (M2) --

    @property
    def profile(self) -> ProfileOverride:
        """Profile in effect for this orchestrator. Unknown → strictest."""
        if self.orchestrator == "claude_code":
            return self.cfg.profiles.claude_code
        if self.orchestrator == "codex":
            return self.cfg.profiles.codex
        if self.orchestrator == "goose":
            return self.cfg.profiles.goose
        # Unknown orchestrator: fall back to Goose's strict cap.
        return self.cfg.profiles.goose

    def _excerpt_enabled(self) -> bool:
        if self.profile.enable_excerpt_tool is not None:
            return self.profile.enable_excerpt_tool
        return self.cfg.agent.enable_excerpt_tool

    def _classification_cap(self) -> Optional[str]:
        return self.profile.classification_cap

    def _max_results(self, requested: Optional[int]) -> int:
        upper = self.profile.max_results_per_query or self.cfg.agent.max_results_per_query
        return min(requested or upper, upper)

    # -- tool handlers --

    def handle_search(
        self,
        query: str,
        scope: Optional[str] = None,
        max_results: Optional[int] = None,
        classification_filter: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
    ) -> ToolResponse:
        prov = str(uuid.uuid4())
        consent = self.consent.check(scope, "search") if scope else None
        # Volume consent is required when require_per_volume_consent is true.
        if scope and self.cfg.consent.require_per_volume_consent and consent is None:
            self.audit.log(
                "search",
                self.orchestrator,
                query=query,
                hook_decision="block",
                provenance_id=prov,
                severity="warning",
            )
            raise ConsentRequired(
                f"no active 'search' consent covers scope {scope!r}; "
                "use `privacy-cli consent grant` to authorize"
            )

        # ``scope`` is a path (volume mount or subdirectory). Used for both
        # the consent check (above) and the abs-path prefix filter.
        results = self.search.search(
            query,
            scope_path=scope,
            max_results=self._max_results(max_results),
            classification_filter=classification_filter,
            classification_cap=self._classification_cap(),
            file_types=file_types,
        )
        payload = [asdict(r) for r in results]
        # Stamp every result's provenance with this call's provenance prefix
        # so the audit log can correlate the MCP request with returned items.
        for item in payload:
            item["provenance_id"] = f"{prov}:{item['provenance_id']}"

        self.audit.log(
            "search",
            self.orchestrator,
            query=query,
            paths_accessed=[r.relative_path for r in results],
            data_returned="snippet",
            bytes_returned=sum(len(r.snippet) for r in results),
            consent_id=consent.consent_id if consent else None,
            pii_redactions_applied=sum(r.pii_redactions_applied for r in results),
            provenance_id=prov,
        )
        return ToolResponse(payload={"results": payload, "count": len(payload)}, provenance_id=prov)

    def handle_index_volume(
        self,
        volume_path: str,
        volume_id: Optional[str] = None,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
        force_reindex: bool = False,
    ) -> ToolResponse:
        prov = str(uuid.uuid4())
        path_obj = Path(volume_path).expanduser()
        consent = self.consent.check(str(path_obj), "index")
        if consent is None:
            self.audit.log(
                "index",
                self.orchestrator,
                paths_accessed=[str(path_obj)],
                hook_decision="block",
                provenance_id=prov,
                severity="warning",
            )
            raise ConsentRequired(
                f"no active 'index' consent for {path_obj}; "
                "use `privacy-cli consent grant --scope index` to authorize"
            )

        vid = volume_id or path_obj.name or "vol_default"
        stats = self.indexer.index_volume(
            path_obj,
            vid,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            force_reindex=force_reindex,
        )
        self.audit.log(
            "index",
            self.orchestrator,
            paths_accessed=[str(path_obj)],
            data_returned="metadata_only",
            bytes_returned=stats.total_indexed_bytes,
            consent_id=consent.consent_id,
            provenance_id=prov,
        )
        return ToolResponse(payload=asdict(stats), provenance_id=prov)

    def handle_read_excerpt(
        self,
        volume_id: str,
        relative_path: str,
        page: Optional[int] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        max_chars: Optional[int] = None,
    ) -> ToolResponse:
        prov = str(uuid.uuid4())
        if not self._excerpt_enabled():
            self.audit.log(
                "read",
                self.orchestrator,
                hook_decision="block",
                provenance_id=prov,
                severity="warning",
            )
            raise ToolDisabled(
                "privacy_read_excerpt is disabled. Phase 1 default is "
                "enable_excerpt_tool=false; the tool unlocks in Phase 2 once "
                "H1 (local-LLM redactor), M1 (capability tokens), and H3 "
                "(out-of-band consent) ship together."
            )

        # Resolve volume_id+relative_path → absolute path via the index.
        cur = self.conn.execute(
            "SELECT abs_path, classification FROM files "
            "WHERE volume_id = ? AND relative_path = ?",
            (volume_id, relative_path),
        )
        row = cur.fetchone()
        if row is None:
            raise FileNotFoundError(f"{volume_id}/{relative_path} not in index")
        abs_path = row["abs_path"]
        classification = row["classification"]

        # Profile cap blocks reads of higher-classification content.
        cap = self._classification_cap()
        if cap and classification in ORDERED_LEVELS:
            if classification_rank(classification) > classification_rank(cap):
                self.audit.log(
                    "read",
                    self.orchestrator,
                    paths_accessed=[abs_path],
                    hook_decision="block",
                    provenance_id=prov,
                    severity="warning",
                )
                raise ClassificationBlocked(
                    f"file classification {classification!r} exceeds profile cap "
                    f"{cap!r} for orchestrator {self.orchestrator!r}"
                )

        # Per-file consent (read scope) with M5 short-window default.
        consent = self.consent.check(abs_path, "read")
        if consent is None:
            self.audit.log(
                "read",
                self.orchestrator,
                paths_accessed=[abs_path],
                hook_decision="block",
                provenance_id=prov,
                severity="warning",
            )
            raise ConsentRequired(
                "no active 'read' consent for this file; "
                "use `privacy-cli consent grant --scope read --granularity file` "
                "with the absolute path"
            )

        # Extract → redact → cap.
        path = Path(abs_path)
        extractor = self.registry.get(path)
        if extractor is None:
            raise ExtractorError(f"no extractor available for {path.suffix}")
        budget = max_chars or self.cfg.agent.excerpt_max_chars
        try:
            raw = extractor.extract_excerpt(
                path,
                start_line=start_line,
                end_line=end_line,
                page=page,
                max_chars=budget,
            )
        except ExtractorError:
            raise
        scrubbed = self.redactor.scrub(raw)

        self.audit.log(
            "read",
            self.orchestrator,
            paths_accessed=[abs_path],
            data_returned="excerpt",
            bytes_returned=len(scrubbed.text),
            consent_id=consent.consent_id,
            pii_redactions_applied=scrubbed.redactions_applied,
            provenance_id=prov,
        )

        return ToolResponse(
            payload={
                "volume_id": volume_id,
                "relative_path": relative_path,
                "excerpt": scrubbed.text,
                "page": page,
                "start_line": start_line,
                "end_line": end_line,
                "pii_redactions_applied": scrubbed.redactions_applied,
                "classification": classification,
                "provenance_id": prov,
            },
            provenance_id=prov,
        )

    def handle_list_volumes(self) -> ToolResponse:
        prov = str(uuid.uuid4())
        # NFR-PRIV-2: never expose mount points outside the daemon.
        cur = self.conn.execute(
            "SELECT volume_id, COUNT(*) AS file_count, MAX(indexed_at) AS last_indexed "
            "FROM files GROUP BY volume_id"
        )
        volumes = []
        for row in cur.fetchall():
            volumes.append(
                {
                    "volume_id": row["volume_id"],
                    "file_count": row["file_count"],
                    "last_indexed": row["last_indexed"],
                }
            )
        self.audit.log(
            "list_volumes",
            self.orchestrator,
            data_returned="metadata_only",
            bytes_returned=0,
            provenance_id=prov,
        )
        return ToolResponse(payload={"volumes": volumes}, provenance_id=prov)

    def handle_get_consent(
        self,
        path: str,
        scope: str,
        request: bool = False,
    ) -> ToolResponse:
        """Look up consent state. Phase 1 does NOT prompt the user via stdio.

        ``request=True`` returns a ``"pending"`` status with instructions for
        the operator to run ``privacy-cli consent grant``. Phase 2 will route
        ``request=True`` to the out-of-band consent UI (H3).
        """
        prov = str(uuid.uuid4())
        rec = self.consent.check(path, scope)
        if rec is not None:
            payload = {
                "status": "granted",
                "consent_id": rec.consent_id,
                "scope": rec.scope,
                "granularity": rec.granularity,
                "expires_at": rec.expires_at,
            }
        elif request:
            payload = {
                "status": "pending",
                "instructions": (
                    f"run `privacy-cli consent grant --path {path!r} "
                    f"--scope {scope}` on the host out-of-band"
                ),
            }
        else:
            payload = {"status": "denied"}

        self.audit.log(
            "consent_check",
            self.orchestrator,
            paths_accessed=[path],
            data_returned="metadata_only",
            bytes_returned=0,
            consent_id=rec.consent_id if rec else None,
            provenance_id=prov,
        )
        return ToolResponse(payload=payload, provenance_id=prov)

    def handle_audit_log(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        action_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 50,
    ) -> ToolResponse:
        prov = str(uuid.uuid4())
        rows = self.audit.query(
            since=since,
            until=until,
            action_filter=action_filter,
            severity_filter=severity_filter,
            limit=limit,
        )
        # Only return safe fields. paths_accessed contains abs paths and is
        # excluded from MCP responses (NFR-PRIV-2).
        payload = []
        for r in rows:
            payload.append(
                {
                    "entry_id": r.entry_id,
                    "timestamp": r.timestamp,
                    "action": r.action,
                    "orchestrator": r.orchestrator,
                    "data_returned": r.data_returned,
                    "bytes_returned": r.bytes_returned,
                    "pii_redactions_applied": r.pii_redactions_applied,
                    "hook_decision": r.hook_decision,
                    "severity": r.severity,
                    "provenance_id": r.provenance_id,
                }
            )
        self.audit.log(
            "audit_log",
            self.orchestrator,
            data_returned="metadata_only",
            bytes_returned=0,
            provenance_id=prov,
        )
        return ToolResponse(payload={"entries": payload}, provenance_id=prov)

    def handle_classify(
        self,
        path: str,
        set_level: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> ToolResponse:
        prov = str(uuid.uuid4())
        if set_level is not None:
            rule = self.classifier.add_rule(
                pattern=path, level=set_level, reason=reason or "manual override"
            )
            self.audit.log(
                "classify",
                self.orchestrator,
                paths_accessed=[path],
                data_returned="metadata_only",
                bytes_returned=0,
                provenance_id=prov,
            )
            return ToolResponse(
                payload={
                    "path": path,
                    "classification": rule.classification,
                    "rule_id": rule.rule_id,
                },
                provenance_id=prov,
            )
        cls = self.classifier.classify_path(path)
        self.audit.log(
            "classify",
            self.orchestrator,
            paths_accessed=[path],
            data_returned="metadata_only",
            bytes_returned=0,
            provenance_id=prov,
        )
        return ToolResponse(
            payload={"path": path, "classification": cls},
            provenance_id=prov,
        )

    def handle_file_summary(
        self,
        volume_id: str,
        relative_path: str,
    ) -> ToolResponse:
        """Plan A's get_file_summary — sanitized natural-language summary.

        Phase 1: returns a deterministic summary built from indexed metadata
        (no LLM). Phase 2 H1 routes through the local LLM for richer summaries.
        """
        prov = str(uuid.uuid4())
        cur = self.conn.execute(
            "SELECT f.abs_path, f.classification, f.file_type, f.size_bytes, "
            "f.modified_at, f.title, f.pii_redactions_applied "
            "FROM files f WHERE f.volume_id = ? AND f.relative_path = ?",
            (volume_id, relative_path),
        )
        row = cur.fetchone()
        if row is None:
            raise FileNotFoundError(f"{volume_id}/{relative_path} not in index")

        cap = self._classification_cap()
        if cap and row["classification"] in ORDERED_LEVELS:
            if classification_rank(row["classification"]) > classification_rank(cap):
                raise ClassificationBlocked(
                    f"classification {row['classification']!r} exceeds profile cap"
                )

        kb = max(1, row["size_bytes"] // 1024)
        summary = (
            f"{row['file_type'].upper()} document "
            f"approx {kb} KB, modified {row['modified_at'][:10]}. "
            f"Sensitivity: {row['classification']}. "
            f"PII redactions applied during indexing: {row['pii_redactions_applied']}."
        )

        self.audit.log(
            "summary",
            self.orchestrator,
            paths_accessed=[row["abs_path"]],
            data_returned="metadata_only",
            bytes_returned=len(summary),
            provenance_id=prov,
        )

        return ToolResponse(
            payload={
                "volume_id": volume_id,
                "relative_path": relative_path,
                "title": row["title"] or "",
                "classification": row["classification"],
                "file_type": row["file_type"],
                "size_kb": kb,
                "modified_at": row["modified_at"],
                "summary": summary,
                "provenance_id": prov,
            },
            provenance_id=prov,
        )


def build_agent(
    db_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    encryption_key: Optional[str] = None,
    orchestrator: Optional[str] = None,
) -> PrivacyAgent:
    """Convenience constructor used by both server.py and cli.py."""
    from .config import load_config

    cfg = load_config(config_path)
    errors = validate_or_raise(cfg)  # noqa: F841
    if db_path is None:
        db_path = Path("~/.privacy-agent/db.sqlite").expanduser()
    conn = open_db(db_path, encryption_key=encryption_key)
    return PrivacyAgent(conn, cfg, orchestrator=orchestrator)


def validate_or_raise(cfg: Config):
    from .config import validate

    errors = validate(cfg)
    if errors:
        raise ValueError("config validation failed: " + "; ".join(errors))
    return cfg
