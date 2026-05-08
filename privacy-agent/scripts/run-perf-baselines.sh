#!/usr/bin/env bash
# ===========================================================================
# Run the perf baseline suite N times (default 3) and write the median to
# bench/baseline.json. Compensates for run-to-run noise — sub-millisecond
# metrics in particular swing wildly with GC/fsync/scheduler jitter.
#
# Usage:
#   bash scripts/run-perf-baselines.sh           # 3 runs (default)
#   bash scripts/run-perf-baselines.sh 5         # 5 runs
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNS="${1:-3}"

PY="${PY:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$PY" ]] || PY="$(command -v python3)"

TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

cd "$REPO_ROOT"
echo "==> running perf baseline ${RUNS} times"

inputs=()
for i in $(seq 1 "$RUNS"); do
  out="$TMP/run_${i}.json"
  echo "==> run ${i}/${RUNS}"
  PERF_BASELINE_OUTPUT="$out" "$PY" -m pytest tests/perf/ -q -s 2>&1 | grep -E "^\[perf\]" || true
  inputs+=("$out")
done

echo "==> merging via median"
"$PY" "$SCRIPT_DIR/merge_baselines.py" "${inputs[@]}" -o "$REPO_ROOT/bench/baseline.json"

echo
echo "==> diff vs committed baseline"
"$PY" "$SCRIPT_DIR/compare_baselines.py" "$REPO_ROOT/bench/baseline.json" || true
