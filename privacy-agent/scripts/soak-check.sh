#!/usr/bin/env bash
# ===========================================================================
# Phase 2 entry soak monitor.
#
# Runs the four gates from Q-G (decided in ADR-context):
#   1. privacy-cli audit verify      → chain integrity
#   2. canary-hit count              → tripwire signal
#   3. usage day                     → at least one search today
#   4. red-team harness (weekly)     → invariant gate still green
#
# Result appended as a JSON line to ~/.privacy-agent/soak.log; exit 0 if
# all gates green for today, non-zero otherwise (cron-friendly for alerts).
#
# Usage:
#   bash scripts/soak-check.sh                # daily check (subset of gates)
#   bash scripts/soak-check.sh --weekly       # full check including harness
#   bash scripts/soak-check.sh --summary      # print soak status; no run
#   bash scripts/soak-check.sh --start        # mark today as soak start
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOAK_LOG="${PRIVACY_AGENT_SOAK_LOG:-$HOME/.privacy-agent/soak.log}"
SOAK_START_FILE="$HOME/.privacy-agent/soak.start"
PY="${PY:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$PY" ]] || PY="$(command -v python3)"

mkdir -p "$(dirname "$SOAK_LOG")"

MODE="${1:-daily}"
TODAY=$(date -u +%Y-%m-%d)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log_event() {
  local type="$1"
  local payload="$2"
  echo "{\"ts\": \"$TS\", \"date\": \"$TODAY\", \"type\": \"$type\", $payload}" >> "$SOAK_LOG"
}

green=0; red=0
hdr() { echo; echo "── $1 ──"; }
ok()  { echo "  ✓ $1"; green=$((green+1)); }
bad() { echo "  ✗ $1"; red=$((red+1)); }

# -- start --
if [[ "$MODE" == "--start" ]]; then
  echo "$TS" > "$SOAK_START_FILE"
  echo "soak started at $TS — log: $SOAK_LOG"
  log_event "soak_start" "\"start\": \"$TS\""
  exit 0
fi

# -- summary --
if [[ "$MODE" == "--summary" ]]; then
  if [[ ! -f "$SOAK_START_FILE" ]]; then
    echo "soak hasn't been started — run \`bash scripts/soak-check.sh --start\`"
    exit 1
  fi
  start=$(cat "$SOAK_START_FILE")
  start_epoch=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$start" +%s 2>/dev/null || echo 0)
  now_epoch=$(date -u +%s)
  days_elapsed=$(( (now_epoch - start_epoch) / 86400 ))

  echo "Soak started: $start"
  echo "Days elapsed: $days_elapsed / 30"

  # Truth source: the audit DB. The soak.log is a check-history record but
  # the live state for canaries / usage / chain comes from the DB itself.
  "$PY" - <<EOF
import json
from pathlib import Path
from privacy_agent.agent import build_agent

soak_start = "$start"
days_elapsed = $days_elapsed
log_path = Path("$SOAK_LOG")

# Soak.log gives us the day-by-day history for audit_verify and harness runs.
events = []
if log_path.exists():
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
audit_events = [e for e in events if e["type"] == "audit_verify"]
audit_pass = sum(1 for e in audit_events if e.get("valid"))
audit_fail = sum(1 for e in audit_events if not e.get("valid"))
audit_days = len({e["date"] for e in audit_events if e.get("valid")})

harness_events = [e for e in events if e["type"] == "harness"]
harness_last = harness_events[-1] if harness_events else None

# Live audit DB for canary count and real usage days.
agent = build_agent(orchestrator="manual")
canary_rows = agent.audit.query(since=soak_start, action_filter="canary_hit", limit=500)
canary_count = len(canary_rows)
search_rows = agent.audit.query(since=soak_start, action_filter="search", limit=500)
real_searches = [r for r in search_rows if r.orchestrator != "manual"]
usage_days = len({r.timestamp[:10] for r in real_searches})
agent.conn.close()

print(f"Audit checks: {audit_pass} valid / {audit_fail} broken (across {audit_days} unique days)")
print(f"Canary hits since soak start: {canary_count}")
print(f"Usage days (≥1 non-manual search): {usage_days} / 10 required")
if harness_last:
    print(f"Harness last run: {harness_last['ts']}, passed={harness_last.get('passed')}")
else:
    print("Harness last run: never (run \`bash scripts/soak-check.sh --weekly\`)")

gates = [
    ("audit chain valid every day", audit_days >= 30 and audit_fail == 0),
    ("zero canary hits", canary_count == 0),
    ("≥10 usage days", usage_days >= 10),
    ("harness re-passed", harness_last is not None and harness_last.get("passed")),
]
print()
print("Phase 2 entry gates:")
for name, ok in gates:
    print(f"  {'✓' if ok else '✗'} {name}")
print()
all_green = all(ok for _, ok in gates) and days_elapsed >= 30
print(f"DECISION: {'GO ✓ ready for Phase 2' if all_green else 'NOGO — keep soaking'}")
EOF
  exit 0
fi

# -- daily / weekly checks --
hdr "audit chain"
if "$PY" -m privacy_agent.cli audit verify >/tmp/soak_audit.json 2>&1; then
  ok "audit verify clean"
  log_event "audit_verify" "\"valid\": true"
else
  bad "audit verify FAILED — investigate immediately"
  log_event "audit_verify" "\"valid\": false"
fi

hdr "canary watch"
# Count canary_hit events since soak start (not all-time — earlier CLI smoke
# tests legitimately produce canary_hit rows during development).
SINCE="$(cat "$SOAK_START_FILE" 2>/dev/null || echo "1970-01-01T00:00:00Z")"
canary_count=$("$PY" -c "
from privacy_agent.agent import build_agent
agent = build_agent(orchestrator='manual')
rows = agent.audit.query(since='$SINCE', action_filter='canary_hit', limit=500)
print(len(rows))
agent.conn.close()
" 2>/dev/null || echo "?")
if [[ "$canary_count" == "0" ]]; then
  ok "no canary hits since soak start"
  log_event "canary_check" "\"count\": 0"
else
  bad "canary hits detected: $canary_count — incident response required"
  log_event "canary_check" "\"count\": $canary_count"
fi

hdr "usage signal"
usage_today=$("$PY" -c "
from privacy_agent.agent import build_agent
agent = build_agent(orchestrator='manual')
rows = agent.audit.query(since='${TODAY}T00:00:00Z', action_filter='search', limit=500)
# Filter to non-manual orchestrators — manual usage is dev/test, not real signal.
real = [r for r in rows if r.orchestrator != 'manual']
print(len(real))
agent.conn.close()
" 2>/dev/null || echo 0)
if [[ "$usage_today" -gt 0 ]]; then
  ok "$usage_today search action(s) today"
else
  echo "  - no searches today (this is fine occasionally; the gate is ≥10 days total)"
fi
log_event "usage" "\"count\": $usage_today"

if [[ "$MODE" == "--weekly" ]]; then
  hdr "red-team harness (weekly)"
  if (cd "$REPO_ROOT" && "$PY" -m pytest tests/redteam/ -q >/tmp/soak_harness.log 2>&1); then
    ok "harness 25/25 green"
    log_event "harness" "\"passed\": true, \"tests\": 25"
  else
    bad "harness FAILED — investigate before continuing soak"
    tail -20 /tmp/soak_harness.log
    log_event "harness" "\"passed\": false"
  fi
fi

hdr "summary"
echo "  ✓ $green green / ✗ $red red"
echo "  log: $SOAK_LOG"
[[ $red -eq 0 ]] && exit 0 || exit 1
