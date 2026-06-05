#!/usr/bin/env bash
# MCP launcher for ${AGENT_NAME_HUMAN}
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

: "${AGENT_ORCHESTRATOR:=claude_code}"
export AGENT_ORCHESTRATOR
export AGENT_NAME="${AGENT_NAME_KEBAB}"
export AGENT_ENV_PREFIX="AGENT"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PY="$REPO_ROOT/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

exec "$PY" -m __AGENT_NAME_SNAKE__.server
