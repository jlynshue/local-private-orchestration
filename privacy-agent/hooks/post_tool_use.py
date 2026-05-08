#!/usr/bin/env python3
"""Claude Code PostToolUse hook — PII safety-net + canary watch.

Reads tool result, scans for canary markers and any PII the upstream
redactor might have missed, and writes an outcome JSON. A canary hit
results in a critical audit log entry. The hook does NOT mutate the tool
result — by the time PostToolUse runs, the model has already received the
data. This hook is a *signal*, not a *gate*.

The PreToolUse hook is the gate. The job here is to detect and record so
that the operator (or M3 dashboard, in Phase 2) can investigate.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any


def _walk_strings(obj: Any):
    """Yield every string leaf in an arbitrarily nested structure."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)


def _scan(payload_text: str) -> dict[str, int]:
    """Run the redactor on a payload and return counts.

    Lazy-imported so this hook works without the privacy_agent package on
    PYTHONPATH for environments that wire the hooks via raw scripts.
    """
    try:
        from privacy_agent.redactor import default_redactor

        r = default_redactor()
        result = r.scrub(payload_text)
        return {
            "pii_redactions": result.redactions_applied,
            "canary_hits": result.canary_hits,
        }
    except Exception:
        return {"pii_redactions": 0, "canary_hits": 0}


def _audit(action: str, severity: str, count: int, orchestrator: str) -> None:
    """Best-effort write to the privacy-agent audit log."""
    try:
        from privacy_agent.agent import build_agent

        agent = build_agent(orchestrator=orchestrator or "claude_code")
        try:
            agent.audit.log(
                action,
                orchestrator=orchestrator or "claude_code",
                severity=severity,
                data_returned="redacted",
                bytes_returned=count,
                hook_decision="warn" if action != "canary_hit" else "alert",
            )
        finally:
            agent.conn.close()
    except Exception:
        # Silent failure — the hook must never block the tool flow.
        pass


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    tool_name = event.get("tool_name") or event.get("toolName") or ""
    tool_result = event.get("tool_result") or event.get("toolResult") or event.get("result")

    payload_text = "\n".join(_walk_strings(tool_result))
    if not payload_text:
        return 0

    stats = _scan(payload_text)
    orchestrator = os.getenv("PRIVACY_AGENT_ORCHESTRATOR", "claude_code")

    if stats["canary_hits"] > 0:
        _audit("canary_hit", "critical", stats["canary_hits"], orchestrator)
        # Print a visible warning so the operator can see it in the chat.
        sys.stderr.write(
            f"[privacy-agent] CRITICAL: canary marker detected in {tool_name} response. "
            "Investigate immediately.\n"
        )
    elif stats["pii_redactions"] > 0:
        _audit("pii_safety_net", "warning", stats["pii_redactions"], orchestrator)

    return 0


if __name__ == "__main__":
    sys.exit(main())
