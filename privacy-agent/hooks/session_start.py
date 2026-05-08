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

        # T-5: file-hash manifest verification. Skips silently if no manifest
        # is installed yet (graceful first-run); fails loud on mismatch.
        manifest_valid = _verify_manifest(agent, orchestrator)

        agent.consent.cleanup_expired()

        active = agent.consent.list_active()
        excerpt_state = "ON" if agent._excerpt_enabled() else "off"
        sys.stderr.write(
            f"[privacy-agent] orchestrator={orchestrator} "
            f"excerpt_tool={excerpt_state} "
            f"active_consents={len(active)} "
            f"audit_chain={'OK' if valid else 'BROKEN'} "
            f"manifest={'OK' if manifest_valid else 'MISMATCH'}\n"
        )
    finally:
        agent.conn.close()

    # Echo a small JSON status for downstream consumers (e.g., status line).
    json.dump(
        {
            "privacy_agent": {
                "audit_chain": "ok" if valid else "broken",
                "manifest": "ok" if manifest_valid else "mismatch",
            }
        },
        sys.stdout,
    )
    return 0


def _verify_manifest(agent, orchestrator: str) -> bool:
    """Return True if manifest verification passes (or is skipped gracefully)."""
    if os.getenv("PRIVACY_AGENT_SKIP_MANIFEST") == "1":
        return True
    try:
        from pathlib import Path
        from privacy_agent import manifest

        path = Path(
            os.getenv(
                "PRIVACY_AGENT_MANIFEST",
                "~/.privacy-agent/manifest.sha256",
            )
        ).expanduser()
        if not path.exists():
            sys.stderr.write(
                "[privacy-agent] WARNING: no manifest installed at "
                f"{path}. Run `privacy-cli manifest install` to enable T-5 "
                "file-hash verification.\n"
            )
            return True  # graceful first-run; not a mismatch
        ok, mismatches = manifest.verify(path)
        if not ok:
            sys.stderr.write(
                "[privacy-agent] CRITICAL: manifest verification FAILED. "
                f"{len(mismatches)} mismatch(es): {', '.join(mismatches[:5])}"
                f"{'...' if len(mismatches) > 5 else ''}\n"
                "Run `privacy-cli manifest verify` for full output, then "
                "either roll back the modified files or "
                "`privacy-cli manifest install` to accept them.\n"
            )
            agent.audit.log(
                "manifest_mismatch",
                orchestrator=orchestrator,
                severity="critical",
                data_returned="metadata_only",
                bytes_returned=len(mismatches),
            )
        return ok
    except Exception as e:
        sys.stderr.write(
            f"[privacy-agent] WARNING: manifest verification errored: {e}\n"
        )
        return True  # don't block on infrastructure failure


if __name__ == "__main__":
    sys.exit(main())
