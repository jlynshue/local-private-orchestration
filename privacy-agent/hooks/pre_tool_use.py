#!/usr/bin/env python3
"""Claude Code PreToolUse hook — defense-in-depth for the privacy-agent plugin.

Reads a JSON event from stdin and writes a JSON decision to stdout. Two
classes of decisions:

1. ``block`` for any Bash command or Read invocation that targets a
   configured sensitive path. The plugin's ``settings.json`` already denies
   these patterns at the permission layer; this hook adds regex-based
   inspection that catches compound commands like
   ``echo x | strings - && cat /Volumes/Backup/Tax/...``.

2. ``allow`` for everything else. This hook never grants new permissions —
   the orchestrator's normal allow/deny rules still apply.

The set of sensitive-path patterns is read from
``$PRIVACY_AGENT_PLUGIN_ROOT/sensitive_paths.txt`` (or the bundled default).
The hook deliberately is read-only — no DB writes, no audit log entries.
Audit events for blocks are emitted by the post-tool-use hook because the
PreToolUse hook can be invoked many times per second and writing to the
audit chain on every call would dominate latency.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_SENSITIVE_PATTERNS = [
    r"/Volumes/[^/\s]+/(Tax|Legal|Medical|Finance)",
    r"~?/Documents/(Tax|Legal|Medical|Finance)",
    r"\.privacy-agent/canaries",
]

# Bash commands that bypass the MCP server and read content directly.
BANNED_BASH = re.compile(
    r"\b(?:cat|head|tail|less|more|strings|xxd|hexdump|base64|open|"
    r"plutil|file|unzip|tar)\b"
)


def _load_sensitive_patterns() -> list[re.Pattern]:
    plugin_root = os.getenv("PRIVACY_AGENT_PLUGIN_ROOT")
    if plugin_root:
        path = Path(plugin_root) / "sensitive_paths.txt"
        if path.exists():
            patterns = [
                line.strip()
                for line in path.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            ]
            return [re.compile(p) for p in patterns]
    return [re.compile(p) for p in DEFAULT_SENSITIVE_PATTERNS]


def _decide(event: dict[str, Any]) -> dict[str, Any]:
    tool_name = event.get("tool_name") or event.get("toolName") or ""
    tool_input = event.get("tool_input") or event.get("toolInput") or {}
    sensitive = _load_sensitive_patterns()

    if tool_name == "Bash":
        cmd = str(tool_input.get("command", ""))
        # Only block if the command both references a sensitive path AND
        # contains one of the banned content-reading verbs. Either alone is
        # fine (`ls /Volumes/Backup/Tax` is read-only metadata; `cat /tmp/x`
        # is harmless). The combination is the bypass we care about.
        path_hit = any(p.search(cmd) for p in sensitive)
        verb_hit = bool(BANNED_BASH.search(cmd))
        if path_hit and verb_hit:
            return {
                "decision": "block",
                "reason": (
                    "privacy-agent: Bash command attempts to read content from "
                    "a sensitive path. Use the privacy_search / "
                    "privacy_file_summary MCP tools instead."
                ),
            }

    if tool_name == "Read":
        target = str(tool_input.get("file_path", ""))
        if any(p.search(target) for p in sensitive):
            return {
                "decision": "block",
                "reason": (
                    "privacy-agent: Read against a sensitive path. Use "
                    "privacy_file_summary or privacy_read_excerpt (when "
                    "enabled) instead."
                ),
            }

    return {"decision": "allow"}


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        # Defensive: empty stdin → fail open, since blocking with no context
        # is more disruptive than continuing without inspection.
        json.dump({"decision": "allow"}, sys.stdout)
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        json.dump({"decision": "allow"}, sys.stdout)
        return 0

    decision = _decide(event)
    json.dump(decision, sys.stdout)
    return 1 if decision["decision"] == "block" else 0


if __name__ == "__main__":
    sys.exit(main())
