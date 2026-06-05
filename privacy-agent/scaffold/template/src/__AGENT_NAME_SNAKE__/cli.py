"""CLI for out-of-band operations (consent, audit, manifest)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .agent import build_agent


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="${AGENT_NAME_KEBAB}-cli")
    p.add_argument("--config", type=Path)
    p.add_argument("--db", type=Path)
    sub = p.add_subparsers(dest="cmd", required=True)

    audit = sub.add_parser("audit")
    asub = audit.add_subparsers(dest="action", required=True)
    asub.add_parser("verify")
    asub.add_parser("recent")

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "audit":
        agent = build_agent(db_path=args.db, config_path=args.config)
        try:
            if args.action == "verify":
                valid, broken = agent.audit.verify_chain_integrity()
                print(json.dumps({"valid": valid, "broken_entry_ids": broken}))
                return 0 if valid else 1
            if args.action == "recent":
                cur = agent.conn.execute(
                    "SELECT * FROM audit ORDER BY sequence_num DESC LIMIT 20"
                )
                rows = [dict(r) for r in cur.fetchall()]
                print(json.dumps(rows, indent=2, default=str))
                return 0
        finally:
            agent.conn.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())
