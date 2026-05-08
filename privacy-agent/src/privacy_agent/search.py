"""FTS5-backed search engine.

Returns ``SearchResult`` instances with ``volume_id + relative_path`` (NFR-PRIV-2).
Snippets pass through the redactor a second time (NFR-PRIV-3 defense-in-depth)
even though the indexed content was redacted at index time.

Each result carries a ``provenance_id`` (M6) — a UUIDv4 stamped at issue time.
The audit log is responsible for linking the provenance_id back to the query
context. The search engine itself is stateless beyond the DB connection.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from .config import AgentConfig
from .redactor import PIIRedactor
from .types import (
    ORDERED_LEVELS,
    SearchResult,
    classification_rank,
    utc_now_iso,
)


# FTS5 operators and other troublesome characters: control chars, null bytes,
# punctuation FTS5 reserves. We replace with spaces, then collapse and quote.
_FTS_DANGEROUS = re.compile(r'[\x00-\x1f"()\*:\^\-\+\\/]')


class SearchEngine:
    def __init__(self, conn, redactor: PIIRedactor, agent_cfg: AgentConfig):
        self.conn = conn
        self.redactor = redactor
        self.cfg = agent_cfg

    def search(
        self,
        query: str,
        scope_volume: Optional[str] = None,
        scope_path: Optional[str] = None,
        max_results: Optional[int] = None,
        classification_filter: Optional[list[str]] = None,
        classification_cap: Optional[str] = None,
        file_types: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Search the FTS5 index.

        ``scope_volume`` filters by indexed volume_id; ``scope_path`` filters
        by absolute-path prefix (volume mount or subdirectory). Either or both
        may be supplied. The internal abs_path used for filtering is never
        exposed in the returned ``SearchResult`` (NFR-PRIV-2).
        """
        if not query or not query.strip():
            return []

        limit = min(max_results or self.cfg.max_results_per_query, self.cfg.max_results_per_query)

        fts_query = self._sanitize(query)
        if not fts_query:
            # Sanitizer reduced the query to nothing — no actionable terms.
            return []
        snippet_chars = self.cfg.snippet_max_chars

        sql = (
            "SELECT f.abs_path AS abs_path, f.volume_id AS volume_id, "
            "       f.relative_path AS relative_path, f.title AS title, "
            "       f.file_type AS file_type, f.size_bytes AS size_bytes, "
            "       f.modified_at AS modified_at, f.indexed_at AS indexed_at, "
            "       f.classification AS classification, "
            "       f.pii_redactions_applied AS pii_idx, "
            "       snippet(files_fts, 2, '<<', '>>', '...', 12) AS snip, "
            "       bm25(files_fts) AS rank_score "
            "FROM files_fts JOIN files f ON f.abs_path = files_fts.abs_path "
            "WHERE files_fts MATCH ? "
        )
        params: list = [fts_query]

        if scope_volume:
            sql += "AND f.volume_id = ? "
            params.append(scope_volume)
        if scope_path:
            # Prefix match against absolute path. Trailing slash normalizes
            # so /a/b matches /a/b/c but not /a/bb.
            prefix = scope_path.rstrip("/")
            sql += "AND (f.abs_path = ? OR f.abs_path LIKE ?) "
            params.append(prefix)
            params.append(prefix + "/%")
        if classification_filter:
            placeholders = ",".join("?" * len(classification_filter))
            sql += f"AND f.classification IN ({placeholders}) "
            params.extend(classification_filter)
        if file_types:
            placeholders = ",".join("?" * len(file_types))
            sql += f"AND f.file_type IN ({placeholders}) "
            params.extend(file_types)

        sql += "ORDER BY rank_score LIMIT ?"
        params.append(limit)

        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()

        cap_rank = (
            classification_rank(classification_cap)
            if classification_cap and classification_cap in ORDERED_LEVELS
            else None
        )

        results: list[SearchResult] = []
        for row in rows:
            cls = row["classification"]
            if cap_rank is not None and cls in ORDERED_LEVELS:
                if classification_rank(cls) > cap_rank:
                    continue  # blocked by cap

            raw_snippet = (row["snip"] or "")[:snippet_chars]
            scrubbed = self.redactor.scrub(raw_snippet)

            results.append(
                SearchResult(
                    volume_id=row["volume_id"],
                    relative_path=row["relative_path"],
                    title=row["title"] or "",
                    snippet=scrubbed.text,
                    score=float(row["rank_score"] or 0.0),
                    classification=cls,
                    file_type=row["file_type"] or "",
                    size_bytes=int(row["size_bytes"] or 0),
                    modified_at=row["modified_at"] or "",
                    indexed_at=row["indexed_at"] or utc_now_iso(),
                    pii_redactions_applied=int(row["pii_idx"] or 0)
                    + scrubbed.redactions_applied,
                    provenance_id=str(uuid.uuid4()),
                )
            )
        return results

    @staticmethod
    def _sanitize(query: str) -> str:
        """Strip FTS5 dangerous characters; collapse whitespace; wrap as a phrase.

        For Phase 1 we accept the loss of FTS5 advanced operators (NEAR, OR,
        column filters) in exchange for predictable, injection-resistant
        behavior. Phase 2 can add a parsed query DSL.

        Returns an empty string if the query reduces to nothing — the caller
        treats that as a no-op (returns no results).
        """
        cleaned = _FTS_DANGEROUS.sub(" ", query)
        # Collapse runs of whitespace and trim.
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            return ""
        # Phrase quoting handles spaces safely. Inner quotes were stripped.
        return f'"{cleaned}"'
