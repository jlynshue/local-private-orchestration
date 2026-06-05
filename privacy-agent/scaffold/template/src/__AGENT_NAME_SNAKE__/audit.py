"""Append-only SHA-256 hash-chain audit log — ported from privacy-agent."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional


GENESIS_HASH = "0" * 64


class AuditLogger:
    def __init__(self, conn):
        self.conn = conn

    def log(self, action: str, orchestrator: str, **kwargs) -> dict:
        prev_hash = self._last_hash()
        seq = self._next_sequence()
        entry_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        partial = {
            "entry_id": entry_id,
            "timestamp": timestamp,
            "action": action,
            "orchestrator": orchestrator,
            "sequence_num": seq,
            **{k: v for k, v in kwargs.items() if v is not None},
        }
        chain = self._compute_hash(prev_hash, partial)

        self.conn.execute(
            "INSERT INTO audit (entry_id, timestamp, action, orchestrator, "
            "hash_chain, sequence_num, payload) VALUES (?,?,?,?,?,?,?)",
            (entry_id, timestamp, action, orchestrator, chain, seq, json.dumps(kwargs)),
        )
        self.conn.commit()
        return {"entry_id": entry_id, "hash_chain": chain}

    def verify_chain_integrity(self) -> tuple[bool, list[str]]:
        cur = self.conn.execute(
            "SELECT entry_id, timestamp, action, orchestrator, hash_chain, "
            "sequence_num, payload FROM audit ORDER BY sequence_num ASC"
        )
        prev_hash = GENESIS_HASH
        broken: list[str] = []
        for row in cur.fetchall():
            partial = {
                "entry_id": row["entry_id"],
                "timestamp": row["timestamp"],
                "action": row["action"],
                "orchestrator": row["orchestrator"],
                "sequence_num": row["sequence_num"],
                **json.loads(row["payload"] or "{}"),
            }
            expected = self._compute_hash(prev_hash, partial)
            if expected != row["hash_chain"]:
                broken.append(row["entry_id"])
            prev_hash = row["hash_chain"]
        return (len(broken) == 0, broken)

    def _last_hash(self) -> str:
        cur = self.conn.execute("SELECT hash_chain FROM audit ORDER BY sequence_num DESC LIMIT 1")
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
        h.update(b"\x1f")
        h.update(canonical.encode("utf-8"))
        return h.hexdigest()
