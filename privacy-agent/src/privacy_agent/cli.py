"""privacy-cli — out-of-band operator interface.

Used for actions that must NOT happen inside an orchestrator session, mainly:

- ``consent grant``: authorize a path/scope. Plan B's interactive stdio prompts
  are vulnerable to prompt injection; doing this through a separate CLI is the
  Phase 1 substitute for Phase 2's H3 menu-bar UI.
- ``consent revoke``, ``consent list``: lifecycle management.
- ``canary seed``: plant H7 honeytokens.
- ``audit verify``: walk the SHA-256 hash chain and report any breakage.
- ``index volume``: kick off an indexing run from the shell.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from .agent import build_agent
from .canary import list_canaries, seed_canaries

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="privacy-cli")
    p.add_argument("--config", type=Path, help="path to TOML config")
    p.add_argument("--db", type=Path, help="path to SQLite DB")
    sub = p.add_subparsers(dest="cmd", required=True)

    consent = sub.add_parser("consent", help="manage consent records")
    csub = consent.add_subparsers(dest="action", required=True)
    grant = csub.add_parser("grant")
    grant.add_argument("--path", required=True)
    grant.add_argument("--scope", choices=("search", "index", "read"), required=True)
    grant.add_argument(
        "--granularity", choices=("file", "directory", "volume"), required=True
    )
    grant.add_argument("--window-seconds", type=int, default=None)
    revoke = csub.add_parser("revoke")
    revoke.add_argument("--id", required=True)
    csub.add_parser("list")
    csub.add_parser("cleanup")

    canary = sub.add_parser("canary", help="manage canary corpus")
    csub2 = canary.add_subparsers(dest="action", required=True)
    seed = csub2.add_parser("seed")
    seed.add_argument("--dir", type=Path, default=Path("~/.privacy-agent/canaries"))
    seed.add_argument("--count", type=int, default=3)
    csub2.add_parser("list").add_argument(
        "--dir", type=Path, default=Path("~/.privacy-agent/canaries")
    )

    audit = sub.add_parser("audit")
    asub = audit.add_subparsers(dest="action", required=True)
    asub.add_parser("verify")
    asub.add_parser("recent")

    index = sub.add_parser("index")
    index.add_argument("path", type=Path)
    index.add_argument("--volume-id", default=None)
    index.add_argument("--force", action="store_true")
    index.add_argument(
        "--include", action="append", default=None, help="include glob (repeatable)"
    )
    index.add_argument(
        "--exclude", action="append", default=None, help="exclude glob (repeatable)"
    )

    return p


def _agent(args, orchestrator: str = "manual"):
    return build_agent(db_path=args.db, config_path=args.config, orchestrator=orchestrator)


def _cmd_consent(args) -> int:
    a = _agent(args)
    try:
        if args.action == "grant":
            rec = a.consent.grant(
                path_pattern=args.path,
                scope=args.scope,
                granularity=args.granularity,
                window_seconds=args.window_seconds,
            )
            print(json.dumps({"granted": rec.consent_id, "expires_at": rec.expires_at}))
            return 0
        if args.action == "revoke":
            ok = a.consent.revoke(args.id)
            print(json.dumps({"revoked": ok}))
            return 0 if ok else 1
        if args.action == "list":
            recs = a.consent.list_active()
            print(json.dumps([r.__dict__ for r in recs], indent=2, default=str))
            return 0
        if args.action == "cleanup":
            n = a.consent.cleanup_expired()
            print(json.dumps({"expired_revoked": n}))
            return 0
    finally:
        a.conn.close()
    return 2


def _cmd_canary(args) -> int:
    if args.action == "seed":
        seeded = seed_canaries(args.dir, count=args.count)
        print(
            json.dumps(
                {"seeded": [{"id": c.canary_id, "path": c.abs_path} for c in seeded]},
                indent=2,
            )
        )
        return 0
    if args.action == "list":
        listed = list_canaries(args.dir)
        print(
            json.dumps(
                [{"id": c.canary_id, "path": c.abs_path} for c in listed], indent=2
            )
        )
        return 0
    return 2


def _cmd_audit(args) -> int:
    a = _agent(args)
    try:
        if args.action == "verify":
            valid, broken = a.audit.verify_chain_integrity()
            print(json.dumps({"valid": valid, "broken_entry_ids": broken}))
            return 0 if valid else 1
        if args.action == "recent":
            rows = a.audit.query(limit=20)
            print(
                json.dumps(
                    [
                        {
                            "ts": r.timestamp,
                            "action": r.action,
                            "orchestrator": r.orchestrator,
                            "severity": r.severity,
                            "data_returned": r.data_returned,
                            "bytes": r.bytes_returned,
                            "redactions": r.pii_redactions_applied,
                        }
                        for r in rows
                    ],
                    indent=2,
                )
            )
            return 0
    finally:
        a.conn.close()
    return 2


def _cmd_index(args) -> int:
    a = _agent(args)
    try:
        # Auto-grant a manual index consent for CLI-driven runs. The CLI itself
        # is the operator's authorization channel.
        a.consent.grant(
            path_pattern=str(args.path.expanduser()),
            scope="index",
            granularity="volume",
            window_seconds=300,  # 5 minutes — just enough for the run
        )
        resp = a.handle_index_volume(
            volume_path=str(args.path.expanduser()),
            volume_id=args.volume_id,
            include_patterns=args.include,
            exclude_patterns=args.exclude,
            force_reindex=args.force,
        )
        print(json.dumps(resp.payload, indent=2, default=str))
        return 0
    finally:
        a.conn.close()


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.cmd == "consent":
        return _cmd_consent(args)
    if args.cmd == "canary":
        return _cmd_canary(args)
    if args.cmd == "audit":
        return _cmd_audit(args)
    if args.cmd == "index":
        return _cmd_index(args)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
