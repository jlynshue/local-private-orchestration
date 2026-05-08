#!/usr/bin/env python3
"""Claude Code SessionStart hook — verify privacy-agent posture.

On every session start (or resume/clear/compact), this hook:

1. Verifies the audit-log hash chain integrity (NFR-AUD-1). A broken chain
   means tamper has occurred or a write was interrupted; the hook prints a
   prominent warning and adds a critical audit entry. It does NOT block the
   session — the operator may need access to ``privacy_audit_log`` to
   investigate. The block decision is the operator's.

2. Cleans up any expired consent records (cosmetic — ``consent.check`` is
   already expiry-aware, but pruning keeps the table small).

3. Reports a one-line summary to stderr that surfaces in Claude Code's
   notification area: orchestrator, excerpt-tool state, active consent count.
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    raw = sys.stdin.read()  # event payload is unused for now; reserved for future use
    _ = raw

    orchestrator = os.getenv("PRIVACY_AGENT_ORCHESTRATOR", "claude_code")

    try:
        from privacy_agent.agent import build_agent

        agent = build_agent(orchestrator=orchestrator)
    except Exception as e:
        sys.stderr.write(f"[privacy-agent] WARNING: failed to load agent on session start: {e}\n")
        return 0

    try:
        valid, broken = agent.audit.verify_chain_integrity()
        if not valid:
            sys.stderr.write(
                f"[privacy-agent] CRITICAL: audit chain integrity check FAILED. "
                f"{len(broken)} broken entries. Run `privacy-cli audit verify` "
                "and investigate before continuing.\n"
            )
            agent.audit.log(
                "audit_chain_broken",
                orchestrator=orchestrator,
                severity="critical",
                data_returned="metadata_only",
                bytes_returned=len(broken),
            )

        agent.consent.cleanup_expired()

        active = agent.consent.list_active()
        excerpt_state = "ON" if agent._excerpt_enabled() else "off"
        sys.stderr.write(
            f"[privacy-agent] orchestrator={orchestrator} "
            f"excerpt_tool={excerpt_state} "
            f"active_consents={len(active)} "
            f"audit_chain={'OK' if valid else 'BROKEN'}\n"
        )
    finally:
        agent.conn.close()

    # Echo a small JSON status for downstream consumers (e.g., status line).
    json.dump(
        {"privacy_agent": {"audit_chain": "ok" if valid else "broken"}},
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
