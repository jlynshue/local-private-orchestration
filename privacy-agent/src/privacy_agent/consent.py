"""Consent manager — grant/check/revoke with M5 time-window leases.

Granularity:
- ``file``: pattern is an absolute file path; matches only that exact path.
- ``directory``: pattern is an absolute directory; matches anything below it.
- ``volume``: pattern is a mount point or volume root; prefix-matches.

M5: ``grant_consent(window_seconds=...)`` issues a short-window lease. When
``window_seconds`` is None, falls back to the config default expiry hours.
For ``read`` scope (excerpt access) the call site should pass the stricter
``excerpt_lease_minutes`` window from config.

Concurrency note: this manager is single-process and trusts the supplied DB
connection. The privacy-agent daemon is single-instance, so this is fine.
Multi-process access (Phase 3) needs a different lock model.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePath
from typing import Optional

from .config import ConsentConfig
from .types import ConsentRecord, utc_now_iso


class ConsentManager:
    VALID_SCOPES = ("index", "read", "search")
    VALID_GRANULARITIES = ("file", "directory", "volume")

    def __init__(self, conn, cfg: ConsentConfig):
        self.conn = conn
        self.cfg = cfg

    # -- mutations --

    def grant(
        self,
        path_pattern: str,
        scope: str,
        granularity: str,
        window_seconds: Optional[int] = None,
    ) -> ConsentRecord:
        if scope not in self.VALID_SCOPES:
            raise ValueError(f"scope must be one of {self.VALID_SCOPES}, got {scope!r}")
        if granularity not in self.VALID_GRANULARITIES:
            raise ValueError(
                f"granularity must be one of {self.VALID_GRANULARITIES}, got {granularity!r}"
            )

        now = datetime.now(timezone.utc)
        expires_at: Optional[str]
        if window_seconds is not None:
            expires_at = (now + timedelta(seconds=window_seconds)).isoformat()
        elif self.cfg.default_expiry_hours and self.cfg.default_expiry_hours > 0:
            expires_at = (
                now + timedelta(hours=self.cfg.default_expiry_hours)
            ).isoformat()
        else:
            expires_at = None  # permanent

        rec = ConsentRecord(
            consent_id=str(uuid.uuid4()),
            path_pattern=str(path_pattern),
            scope=scope,
            granted=True,
            granted_at=now.isoformat(),
            expires_at=expires_at,
            granularity=granularity,
            revoked_at=None,
        )
        self.conn.execute(
            "INSERT INTO consent (consent_id, path_pattern, scope, granted, "
            "granted_at, expires_at, granularity, revoked_at) "
            "VALUES (?, ?, ?, 1, ?, ?, ?, NULL)",
            (
                rec.consent_id,
                rec.path_pattern,
                rec.scope,
                rec.granted_at,
                rec.expires_at,
                rec.granularity,
            ),
        )
        self.conn.commit()
        return rec

    def revoke(self, consent_id: str) -> bool:
        cur = self.conn.execute(
            "UPDATE consent SET revoked_at = ? WHERE consent_id = ? AND revoked_at IS NULL",
            (utc_now_iso(), consent_id),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def cleanup_expired(self) -> int:
        """Mark expired-but-not-revoked records as revoked. Returns count."""
        now = utc_now_iso()
        cur = self.conn.execute(
            "UPDATE consent SET revoked_at = ? "
            "WHERE revoked_at IS NULL AND expires_at IS NOT NULL AND expires_at <= ?",
            (now, now),
        )
        self.conn.commit()
        return cur.rowcount

    # -- queries --

    def check(self, path: str, scope: str) -> Optional[ConsentRecord]:
        """Return the active consent that covers (path, scope), or None.

        "Active" = granted=1, not revoked, not expired. If multiple cover, the
        most recently granted wins (deterministic).
        """
        if scope not in self.VALID_SCOPES:
            raise ValueError(f"scope must be one of {self.VALID_SCOPES}, got {scope!r}")

        now = utc_now_iso()
        cur = self.conn.execute(
            "SELECT * FROM consent WHERE scope = ? AND granted = 1 "
            "AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > ?) "
            "ORDER BY granted_at DESC",
            (scope, now),
        )
        for row in cur.fetchall():
            rec = _row_to_record(row)
            if self._is_path_covered(path, rec):
                return rec
        return None

    def list_active(self) -> list[ConsentRecord]:
        now = utc_now_iso()
        cur = self.conn.execute(
            "SELECT * FROM consent WHERE granted = 1 AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > ?) "
            "ORDER BY granted_at DESC",
            (now,),
        )
        return [_row_to_record(r) for r in cur.fetchall()]

    # -- helpers --

    @staticmethod
    def _is_path_covered(path: str, rec: ConsentRecord) -> bool:
        if rec.granularity == "file":
            return Path(path) == Path(rec.path_pattern)
        if rec.granularity == "directory":
            try:
                PurePath(path).relative_to(rec.path_pattern)
            except ValueError:
                return False
            return True
        if rec.granularity == "volume":
            # Volume scope = path is under (or equal to) the volume's mount.
            mp = str(rec.path_pattern).rstrip("/")
            return path == mp or path.startswith(mp + "/")
        return False


def _row_to_record(row) -> ConsentRecord:
    return ConsentRecord(
        consent_id=row["consent_id"],
        path_pattern=row["path_pattern"],
        scope=row["scope"],
        granted=bool(row["granted"]),
        granted_at=row["granted_at"],
        expires_at=row["expires_at"],
        granularity=row["granularity"],
        revoked_at=row["revoked_at"],
    )
