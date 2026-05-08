"""Append-only audit log with mandatory SHA-256 hash chain.

NFR-AUD-1: hash chain is non-optional. Each entry's ``hash_chain`` field is
``SHA256(prev_chain || canonical_entry_bytes)`` where ``canonical_entry_bytes``
is the JSON-serialized entry with sorted keys, ``ensure_ascii=True``, and the
``hash_chain`` field excluded.

``verify_chain_integrity()`` walks the chain in sequence-num order and reports
any breaks. The privacy-agent daemon should call it on startup; a broken
chain blocks all tools until the operator acknowledges.

M6: every entry carries an optional ``provenance_id`` linking the audit row
to a specific outbound payload. Provenance lets a future leak investigation
trace response → entry → source files → orchestrator session.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Iterable, Optional

from .types import AuditEntry, utc_now_iso


GENESIS_HASH = "0" * 64  # The hash before the first entry.


class AuditLogger:
    def __init__(self, conn):
        self.conn = conn

    # -- writes --

    def log(
        self,
        action: str,
        orchestrator: str,
        *,
        query: Optional[str] = None,
        paths_accessed: Optional[Iterable[str]] = None,
        data_returned: str = "none",
        bytes_returned: int = 0,
        consent_id: Optional[str] = None,
        pii_redactions_applied: int = 0,
        hook_decision: Optional[str] = None,
        provenance_id: Optional[str] = None,
        severity: str = "info",
    ) -> AuditEntry:
        prev_hash = self._last_hash()
        seq = self._next_sequence()

        # Build the entry without hash_chain first; compute hash; then assemble final.
        entry_id = str(uuid.uuid4())
        timestamp = utc_now_iso()
        paths = list(paths_accessed) if paths_accessed else []

        partial = {
            "entry_id": entry_id,
            "timestamp": timestamp,
            "action": action,
            "orchestrator": orchestrator,
            "query": query,
            "paths_accessed": paths,
            "data_returned": data_returned,
            "bytes_returned": bytes_returned,
            "consent_id": consent_id,
            "pii_redactions_applied": pii_redactions_applied,
            "hook_decision": hook_decision,
            "provenance_id": provenance_id,
            "severity": severity,
            "sequence_num": seq,
        }
        chain = self._compute_hash(prev_hash, partial)

        entry = AuditEntry(
            entry_id=entry_id,
            timestamp=timestamp,
            action=action,
            orchestrator=orchestrator,
            query=query,
            paths_accessed=paths,
            data_returned=data_returned,
            bytes_returned=bytes_returned,
            consent_id=consent_id,
            pii_redactions_applied=pii_redactions_applied,
            hook_decision=hook_decision,
            provenance_id=provenance_id,
            hash_chain=chain,
            severity=severity,
        )

        self.conn.execute(
            "INSERT INTO audit (entry_id, timestamp, action, orchestrator, query, "
            "paths_accessed, data_returned, bytes_returned, consent_id, "
            "pii_redactions_applied, hook_decision, provenance_id, hash_chain, "
            "severity, sequence_num) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                entry_id,
                timestamp,
                action,
                orchestrator,
                query,
                json.dumps(paths),
                data_returned,
                bytes_returned,
                consent_id,
                pii_redactions_applied,
                hook_decision,
                provenance_id,
                chain,
                severity,
                seq,
            ),
        )
        self.conn.commit()
        return entry

    # -- queries --

    def query(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        action_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        where = []
        params: list = []
        if since:
            where.append("timestamp >= ?")
            params.append(since)
        if until:
            where.append("timestamp <= ?")
            params.append(until)
        if action_filter:
            where.append("action = ?")
            params.append(action_filter)
        if severity_filter:
            where.append("severity = ?")
            params.append(severity_filter)
        sql = "SELECT * FROM audit"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY sequence_num DESC LIMIT ?"
        params.append(min(int(limit), 500))
        cur = self.conn.execute(sql, params)
        return [_row_to_entry(r) for r in cur.fetchall()]

    def verify_chain_integrity(self) -> tuple[bool, list[str]]:
        """Walk the chain in sequence order. Returns (valid, list_of_broken_entry_ids)."""
        cur = self.conn.execute(
            "SELECT entry_id, timestamp, action, orchestrator, query, paths_accessed, "
            "data_returned, bytes_returned, consent_id, pii_redactions_applied, "
            "hook_decision, provenance_id, severity, sequence_num, hash_chain "
            "FROM audit ORDER BY sequence_num ASC"
        )
        prev_hash = GENESIS_HASH
        broken: list[str] = []
        for row in cur.fetchall():
            partial = {
                "entry_id": row["entry_id"],
                "timestamp": row["timestamp"],
                "action": row["action"],
                "orchestrator": row["orchestrator"],
                "query": row["query"],
                "paths_accessed": json.loads(row["paths_accessed"] or "[]"),
                "data_returned": row["data_returned"],
                "bytes_returned": row["bytes_returned"],
                "consent_id": row["consent_id"],
                "pii_redactions_applied": row["pii_redactions_applied"],
                "hook_decision": row["hook_decision"],
                "provenance_id": row["provenance_id"],
                "severity": row["severity"],
                "sequence_num": row["sequence_num"],
            }
            expected = self._compute_hash(prev_hash, partial)
            if expected != row["hash_chain"]:
                broken.append(row["entry_id"])
            prev_hash = row["hash_chain"]
        return (len(broken) == 0, broken)

    # -- internals --

    def _last_hash(self) -> str:
        cur = self.conn.execute(
            "SELECT hash_chain FROM audit ORDER BY sequence_num DESC LIMIT 1"
        )
        row = cur.fetchone()
        return row["hash_chain"] if row else GENESIS_HASH

    def _next_sequence(self) -> int:
        cur = self.conn.execute("SELECT MAX(sequence_num) AS m FROM audit")
        row = cur.fetchone()
        return (row["m"] or 0) + 1

    @staticmethod
    def _compute_hash(prev_hash: str, partial: dict) -> str:
        canonical = json.dumps(partial, sort_keys=True, ensure_ascii=True, default=str)
        h = hashlib.sha256()
        h.update(prev_hash.encode("ascii"))
        h.update(b"\x1f")  # unit separator — defends against ambiguous concatenation
        h.update(canonical.encode("utf-8"))
        return h.hexdigest()


def _row_to_entry(row) -> AuditEntry:
    return AuditEntry(
        entry_id=row["entry_id"],
        timestamp=row["timestamp"],
        action=row["action"],
        orchestrator=row["orchestrator"],
        query=row["query"],
        paths_accessed=json.loads(row["paths_accessed"] or "[]"),
        data_returned=row["data_returned"],
        bytes_returned=row["bytes_returned"],
        consent_id=row["consent_id"],
        pii_redactions_applied=row["pii_redactions_applied"],
        hook_decision=row["hook_decision"],
        provenance_id=row["provenance_id"],
        hash_chain=row["hash_chain"],
        severity=row["severity"],
    )
