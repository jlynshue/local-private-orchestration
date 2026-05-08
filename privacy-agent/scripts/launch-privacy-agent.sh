#!/usr/bin/env bash
# ===========================================================================
# MCP Launcher: privacy-agent
# ===========================================================================
# Modeled on the existing launch-ebay.sh pattern (single source of truth for
# how to start a Python MCP server in this monorepo). The orchestrator name
# is required so per-orchestrator profiles (M2) apply correctly.
#
# Usage (Claude Code):
#   set as `command` in plugin.json's mcpServers entry; PRIVACY_AGENT_ORCHESTRATOR
#   defaults to "claude_code" via the plugin's env block.
#
# Usage (Codex CLI):
#   set in ~/.codex/config.toml with PRIVACY_AGENT_ORCHESTRATOR=codex
#
# Usage (Goose):
#   `goose configure` add an stdio extension pointing here, with
#   PRIVACY_AGENT_ORCHESTRATOR=goose
#
# Optional environment variables:
#   PRIVACY_AGENT_CONFIG    path to a TOML config (default: bundled default.toml)
#   PRIVACY_AGENT_DB        path to SQLite DB (default: ~/.privacy-agent/db.sqlite)
#   PRIVACY_AGENT_DB_KEY    SQLCipher key (H5; falls back to plain SQLite if libsqlcipher missing)
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

: "${PRIVACY_AGENT_ORCHESTRATOR:=claude_code}"
export PRIVACY_AGENT_ORCHESTRATOR

# Default config = bundled default.toml unless overridden.
if [[ -z "${PRIVACY_AGENT_CONFIG:-}" && -f "$REPO_ROOT/config/default.toml" ]]; then
  export PRIVACY_AGENT_CONFIG="$REPO_ROOT/config/default.toml"
fi

# Default DB key from macOS Keychain if available and not overridden.
if [[ -z "${PRIVACY_AGENT_DB_KEY:-}" ]]; then
  if command -v security >/dev/null 2>&1; then
    if KEY=$(security find-generic-password -a "$USER" -s "privacy-agent-db" -w 2>/dev/null); then
      export PRIVACY_AGENT_DB_KEY="$KEY"
    fi
  fi
fi

# Pick interpreter: prefer the project venv if it exists, else system python3.
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PY="$REPO_ROOT/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

exec "$PY" -m privacy_agent.server
