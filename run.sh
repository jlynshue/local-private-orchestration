#!/usr/bin/env bash
# ===========================================================================
# Conductor workspace runner.
#
# Wire in Conductor → Run tab → "Add run script" using one of:
#
#   bash run.sh              # default = fast unit + integration tests
#   bash run.sh server       # start the MCP stdio server
#   bash run.sh watch        # poll for changes; re-run tests on save
#   bash run.sh redteam      # M1.9 invariant gate (canary + PII proofs)
#   bash run.sh full         # full CI (lint + tests + redteam + perf + smoke)
#
# Run any mode manually from the terminal too. ``./run.sh help`` lists modes.
# ===========================================================================
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$WORKSPACE_ROOT/privacy-agent"
VENV="$PROJECT_ROOT/.venv"

# ANSI color helpers — silent if not a TTY.
if [[ -t 1 ]]; then
  C_HDR="\033[1;34m"; C_OK="\033[0;32m"; C_WARN="\033[1;33m"; C_DIM="\033[2m"; C_OFF="\033[0m"
else
  C_HDR=""; C_OK=""; C_WARN=""; C_DIM=""; C_OFF=""
fi
hdr() { echo -e "\n${C_HDR}━━━ $* ━━━${C_OFF}"; }
ok()  { echo -e "${C_OK}✓${C_OFF} $*"; }
warn(){ echo -e "${C_WARN}⚠${C_OFF} $*"; }
dim() { echo -e "${C_DIM}$*${C_OFF}"; }

ensure_venv() {
  if [[ ! -x "$VENV/bin/python" ]]; then
    hdr "First-run: bootstrapping virtualenv"
    bash "$WORKSPACE_ROOT/setup.sh"
  fi
}

cd "$PROJECT_ROOT"
ensure_venv
PY="$VENV/bin/python"

MODE="${1:-test}"

run_test() {
  hdr "Unit + integration tests"
  "$PY" -m pytest tests/ -q --ignore=tests/redteam --ignore=tests/perf
}

run_redteam() {
  hdr "Red-team harness (M1.9 invariant gate)"
  "$PY" -m pytest tests/redteam/ -q
}

run_perf() {
  hdr "Perf baselines"
  "$PY" -m pytest tests/perf/ -q -s
  if [[ -f bench/baseline.json && -f bench/baseline.committed.json ]]; then
    hdr "Baseline comparison"
    "$PY" scripts/compare_baselines.py bench/baseline.json || true
  fi
}

run_all() {
  hdr "Full test suite"
  "$PY" -m pytest tests/ tests/redteam/ tests/perf/ -q
}

run_lint() {
  hdr "ruff lint"
  "$PY" -m ruff check src/ tests/ hooks/
}

run_smoke() {
  hdr "CLI smoke"
  "$PY" -m privacy_agent.cli audit verify
  local tmp; tmp=$(mktemp -d); trap "rm -rf $tmp" EXIT RETURN
  "$PY" -m privacy_agent.cli canary seed --dir "$tmp/canaries" --count 2 >/dev/null
  "$PY" -m privacy_agent.cli canary list --dir "$tmp/canaries" >/dev/null
  ok "canary seed/list ok"
}

run_server() {
  hdr "Starting privacy-agent MCP server (stdio)"
  warn "stdio servers expect a single MCP client on stdin/stdout."
  warn "For manual poking, pipe newline-delimited JSON-RPC requests in."
  warn "Press Ctrl-C to stop."
  echo
  : "${PRIVACY_AGENT_ORCHESTRATOR:=manual}"
  export PRIVACY_AGENT_ORCHESTRATOR
  : "${PRIVACY_AGENT_CONFIG:=$PROJECT_ROOT/config/default.toml}"
  export PRIVACY_AGENT_CONFIG
  exec "$PY" -m privacy_agent.server
}

run_watch() {
  hdr "Watch mode — re-running unit tests on file change"
  warn "Polls every 2s. Ctrl-C to stop."
  echo
  local last=""
  while true; do
    # Hash modtimes of source + test files. Cheap, dep-free.
    local cur
    cur=$(find src tests hooks config \
      -type f \( -name "*.py" -o -name "*.toml" -o -name "*.yaml" \) \
      -not -path "*/__pycache__/*" -exec stat -f "%m %N" {} + 2>/dev/null | sort | shasum)
    if [[ "$cur" != "$last" ]]; then
      clear || true
      echo -e "${C_DIM}$(date '+%H:%M:%S')${C_OFF}"
      "$PY" -m pytest tests/ -q --ignore=tests/redteam --ignore=tests/perf \
        --tb=short -x 2>&1 | tail -30 || true
      last="$cur"
    fi
    sleep 2
  done
}

run_ci()   { bash "$PROJECT_ROOT/scripts/ci.sh" fast; }
run_full() { bash "$PROJECT_ROOT/scripts/ci.sh" full; }

run_help() {
  cat <<'EOF'
Conductor run-script modes:

  test       (default) unit + integration suite, fast feedback
  watch      poll src/ + tests/, re-run unit tests on save
  redteam    M1.9 invariant gate (canary + PII proofs)
  perf       NFR-PERF-1 baselines + comparison
  all        every test in the project
  lint       ruff check
  smoke      privacy-cli audit verify + canary seed/list
  server     start the MCP stdio server for manual poking
  ci         scripts/ci.sh fast (lint + tests + redteam + smoke)
  full       scripts/ci.sh full (adds perf)
  help       this message

Set the Conductor "Add run script" field to one of:
  bash run.sh              ← default fast feedback
  bash run.sh watch        ← long-lived; concurrent mode
  bash run.sh server       ← MCP daemon
EOF
}

case "$MODE" in
  test)     run_test ;;
  redteam)  run_redteam ;;
  perf)     run_perf ;;
  all)      run_all ;;
  watch)    run_watch ;;
  lint)     run_lint ;;
  smoke)    run_smoke ;;
  server)   run_server ;;
  ci)       run_ci ;;
  full)     run_full ;;
  help|-h|--help) run_help ;;
  *)
    warn "unknown mode: $MODE"
    run_help
    exit 2
    ;;
esac

ok "run.sh ($MODE) finished"
