#!/usr/bin/env bash
# ===========================================================================
# Local CI runner — same checks as .github/workflows/ci.yml, on the dev box.
# ===========================================================================
# Usage:
#   bash scripts/ci.sh            # full pass: lint + tests + redteam + perf + smoke
#   bash scripts/ci.sh fast       # skip perf
#   bash scripts/ci.sh redteam    # only the M1.9 invariant gate
#
# Exit code: non-zero on any failure. Suitable for `pre-push` git hook.
# ===========================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="${1:-full}"

PY="${PY:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

PYTEST="$PY -m pytest"

run_lint() {
  if "$PY" -c "import ruff" 2>/dev/null; then
    echo "==> ruff lint"
    "$PY" -m ruff check src/ tests/ hooks/
  else
    echo "==> ruff not installed; skipping lint"
  fi
}

run_unit() {
  echo "==> unit + integration tests"
  $PYTEST tests/ -q --ignore=tests/redteam --ignore=tests/perf
}

run_redteam() {
  echo "==> red-team harness (M1.9 invariant gate)"
  $PYTEST tests/redteam/ -q
}

run_perf() {
  echo "==> perf baselines"
  $PYTEST tests/perf/ -q -s
  if [[ -f bench/baseline.json ]]; then
    echo "==> baseline comparison"
    "$PY" scripts/compare_baselines.py bench/baseline.json || true
  fi
}

run_smoke() {
  echo "==> CLI smoke"
  "$PY" -m privacy_agent.cli audit verify
  TMP=$(mktemp -d)
  trap "rm -rf $TMP" EXIT
  "$PY" -m privacy_agent.cli canary seed --dir "$TMP/canaries" --count 2 >/dev/null
  "$PY" -m privacy_agent.cli canary list --dir "$TMP/canaries" >/dev/null
  echo "  ✓ canary seed/list"
}

case "$MODE" in
  full)
    run_lint
    run_unit
    run_redteam
    run_perf
    run_smoke
    ;;
  fast)
    run_lint
    run_unit
    run_redteam
    run_smoke
    ;;
  redteam)
    run_redteam
    ;;
  perf)
    run_perf
    ;;
  smoke)
    run_smoke
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    echo "Usage: $0 [full|fast|redteam|perf|smoke]" >&2
    exit 2
    ;;
esac

echo
echo "✓ CI ($MODE) passed"
