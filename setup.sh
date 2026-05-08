#!/usr/bin/env bash
# ===========================================================================
# Conductor workspace setup. Idempotent — safe to re-run.
#
# Wire in Conductor → Setup tab → "Setup script" using:
#
#   bash setup.sh
#
# What it does:
#   1. Ensure privacy-agent/.venv exists
#   2. Install package + dev + extractors deps
#   3. (Optional) install sqlcipher3 if libsqlcipher is on the host
#   4. Run a smoke check so the workspace is known-good before run.sh starts
# ===========================================================================
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$WORKSPACE_ROOT/privacy-agent"
VENV="$PROJECT_ROOT/.venv"

if [[ -t 1 ]]; then
  C_HDR="\033[1;34m"; C_OK="\033[0;32m"; C_WARN="\033[1;33m"; C_OFF="\033[0m"
else
  C_HDR=""; C_OK=""; C_WARN=""; C_OFF=""
fi
hdr() { echo -e "\n${C_HDR}━━━ $* ━━━${C_OFF}"; }
ok()  { echo -e "${C_OK}✓${C_OFF} $*"; }
warn(){ echo -e "${C_WARN}⚠${C_OFF} $*"; }

cd "$PROJECT_ROOT"

# ---- 1. venv ----
if [[ ! -x "$VENV/bin/python" ]]; then
  hdr "Creating virtualenv"
  python3 -m venv .venv
  ok "venv created"
else
  ok "venv already exists"
fi

PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

# ---- 2. core deps ----
hdr "Installing package + dev + extractors"
"$PIP" install --upgrade pip --quiet
"$PIP" install -e ".[dev,extractors]" --quiet
ok "deps installed"

# ---- 3. optional encryption ----
if "$PY" -c "import sqlcipher3" 2>/dev/null; then
  ok "sqlcipher3 already available (H5 encryption-at-rest active)"
else
  if command -v brew >/dev/null && brew list sqlcipher >/dev/null 2>&1; then
    hdr "Trying to install sqlcipher3 (libsqlcipher detected)"
    if "$PIP" install sqlcipher3-binary --quiet 2>/dev/null; then
      ok "sqlcipher3 installed"
    else
      warn "sqlcipher3 wheel not available for this Python — falling back to plain SQLite"
      warn "(DB still works; encryption-at-rest depends on FileVault)"
    fi
  else
    warn "libsqlcipher not installed; \`brew install sqlcipher\` to enable H5 at-rest encryption"
    warn "(plain SQLite is used as fallback; FileVault is the interim mitigation)"
  fi
fi

# ---- 4. T-5 manifest install ----
hdr "Installing T-5 file-hash manifest"
"$PY" -m privacy_agent.cli manifest install >/dev/null && ok "manifest installed at ~/.privacy-agent/manifest.sha256"

# ---- 5. smoke check ----
hdr "Smoke check"
"$PY" -m privacy_agent.cli audit verify >/dev/null && ok "audit chain initializes cleanly"
"$PY" -m privacy_agent.cli manifest verify >/dev/null && ok "manifest verifies cleanly"
"$PY" -c "from privacy_agent.server import register_tools" && ok "server module imports"

hdr "Done"
echo
echo "Next: bash run.sh           (default = unit + integration tests)"
echo "Or:   bash run.sh watch     (long-lived; re-run on save)"
echo "Or:   bash run.sh server    (start the MCP stdio server)"
echo "Or:   bash run.sh help      (full mode list)"
