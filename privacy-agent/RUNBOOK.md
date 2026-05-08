# Operator Runbook — privacy-agent Phase 1

Day-to-day procedures for running, monitoring, and maintaining the privacy-agent.

## First-run setup

```bash
cd /path/to/privacy-agent

# Python venv with deps
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,extractors]"

# (Optional but recommended) install SQLCipher for at-rest encryption (H5)
brew install sqlcipher
pip install sqlcipher3-binary    # if a wheel exists for your Python version

# Generate a DB encryption key and store in macOS Keychain
security add-generic-password -a "$USER" -s "privacy-agent-db" \
    -w "$(openssl rand -hex 32)"

# Plant canary tripwires (H7)
.venv/bin/privacy-cli canary seed --dir ~/.privacy-agent/canaries --count 3

# Verify the audit chain initializes cleanly
.venv/bin/privacy-cli audit verify

# Merge the deny rules into your Claude Code settings (review first!)
cat .claude-plugin/settings-fragment.json
# manually merge the "permissions" block into ~/.claude/settings.json
```

After setup the directory layout is:

```
~/.privacy-agent/
├── db.sqlite           # FTS5 index + consent + audit (0600)
├── db.sqlite-wal       # WAL journal
└── canaries/           # H7 honeytokens (0600 each)
```

## Daily / weekly tasks

### Weekly canary watch (H7)

Until Phase 2 lands the M3 dashboard, the operator manually runs:

```bash
.venv/bin/privacy-cli audit recent
```

…and looks for `severity=critical` entries with `action=canary_hit`. Any
hit is the strongest signal that a privacy-boundary failure occurred — the
canary marker reached an outbound payload that crossed the boundary. If
seen:

1. Immediately stop using the affected orchestrator session.
2. Note the `provenance_id` of the canary_hit row.
3. Run `privacy-cli audit recent` and trace which tool call produced it.
4. Inspect the orchestrator's conversation history (Anthropic / OpenAI
   request log export) for the marker — if it's there, the leak left the
   host.
5. Open an incident, rotate canaries (`privacy-cli canary seed`), and
   review the relevant code path.

### Monthly canary rotation

```bash
# Remove old canaries
rm ~/.privacy-agent/canaries/*.txt
# Re-seed with fresh IDs
.venv/bin/privacy-cli canary seed --dir ~/.privacy-agent/canaries --count 3
# Re-index any volume that contained them so the index reflects the rotation
.venv/bin/privacy-cli index ~/Documents/SomeIndexedDir --force
```

This cycles the markers so an attacker who exfiltrated the old canary
catalog can't avoid tripping the new ones.

### Audit chain verification

```bash
.venv/bin/privacy-cli audit verify
```

Returns `{"valid": true, "broken_entry_ids": []}` on a healthy chain.
Anything else means tampering or a write was interrupted; investigate
before continuing to use the daemon.

## Granting and revoking consent

```bash
# Grant volume-level search consent (default 7-day expiry)
.venv/bin/privacy-cli consent grant \
    --path /Volumes/Backup --scope search --granularity volume

# Grant index consent
.venv/bin/privacy-cli consent grant \
    --path /Volumes/Backup --scope index --granularity volume

# Time-window lease (M5) — narrow window for sensitive runs
.venv/bin/privacy-cli consent grant \
    --path /Volumes/Backup/Tax --scope search --granularity directory \
    --window-seconds 1800  # 30 minutes

# List active consents
.venv/bin/privacy-cli consent list

# Revoke
.venv/bin/privacy-cli consent revoke --id <consent_id>

# Prune expired records
.venv/bin/privacy-cli consent cleanup
```

Phase 2's H3 menu-bar UI replaces these CLI flows with a notification-driven
approval path. For now, the CLI is the only out-of-band channel.

## Indexing a volume

```bash
.venv/bin/privacy-cli index /Volumes/Backup \
    --volume-id vol_backup \
    --exclude '**/.DS_Store' \
    --exclude '**/node_modules/**'
```

The CLI auto-grants a 5-minute index consent for the duration of the run,
then the consent expires. You still need a *separate* search consent before
`privacy_search` returns results.

To force re-index (e.g., after rotating canaries):

```bash
.venv/bin/privacy-cli index /Volumes/Backup --force
```

## Recovery procedures

### Audit chain broken

If `privacy-cli audit verify` reports broken entries:

1. The session-start hook will warn on every Claude Code session start.
2. Capture the broken entry IDs.
3. Decide: tampering vs corruption. If tampering is suspected, treat as a
   security incident.
4. To repair: there is no in-place repair (intentional — repair would
   defeat tamper detection). The only path is to:
   - Export current audit rows (`privacy-cli audit recent`)
   - Re-initialize the audit table by deleting it (loses history)
   - Investigate the cause before resuming

### DB corruption

```bash
# WAL replay
sqlite3 ~/.privacy-agent/db.sqlite "PRAGMA wal_checkpoint(TRUNCATE);"
.venv/bin/privacy-cli audit verify
```

If integrity is still broken, restore from backup or re-index from sources.
The DB doesn't contain anything that can't be regenerated — every file in
the index has its source on disk.

### SQLCipher key loss

The DB becomes unreadable. There is no recovery short of:

1. Delete `~/.privacy-agent/db.sqlite`.
2. Generate a new key, store in Keychain (see "First-run setup").
3. Re-index volumes from source.

This is by design: the inability to recover an encrypted DB without the key
is the property that makes encryption-at-rest meaningful.

## Health checks

Quick smoke test that everything still works:

```bash
# 1. Audit chain healthy
.venv/bin/privacy-cli audit verify

# 2. CLI loads agent without errors
.venv/bin/privacy-cli consent list

# 3. Test suite passes (run after upgrades)
.venv/bin/pytest tests/ -q

# 4. Red-team harness still green (run after any policy/code change)
.venv/bin/pytest tests/redteam/ -q
```

## Logs and where to look

- Audit log: SQLite table `audit` in `~/.privacy-agent/db.sqlite`
- Daemon stdout/stderr: captured by the orchestrator (Claude Code, Codex,
  Goose); usually visible in those tools' debug logs
- SessionStart hook stderr: shown in Claude Code's status notifications

## Phase 2 entry soak

Phase 2 begins only after a 30-day soak window with four gates green
(per `docs/adr/` plus Q-G in `design/integrated-phased-plan.md`). Use
`scripts/soak-check.sh` to instrument it.

### Start the soak

```bash
.venv/bin/privacy-cli manifest install         # T-5 baseline
bash scripts/soak-check.sh --start             # records start timestamp
```

### Daily check (cron-friendly)

```bash
bash scripts/soak-check.sh                     # daily: audit + canary + usage
```

Wire into launchd or cron, e.g. daily at 09:00:

```
0 9 * * * /usr/bin/env bash /path/to/scripts/soak-check.sh
```

### Weekly check (adds the harness)

```bash
bash scripts/soak-check.sh --weekly            # same plus tests/redteam/
```

### Status check

```bash
bash scripts/soak-check.sh --summary           # GO / NOGO decision
```

The summary reports days elapsed, audit-chain status, canary hits since
start, usage days (≥10 non-manual searches required), and last harness
run. Phase 2 entry requires all four gates green AND ≥30 days elapsed.

### What "GO" means

When the summary prints `DECISION: GO ✓ ready for Phase 2`:

1. The audit chain has been verified valid every day with zero broken entries
2. No canary marker has appeared in any audit row since the soak began
3. The system has actually carried real workload (not idle): ≥10 days with
   at least one search from a non-`manual` orchestrator
4. The red-team harness has re-passed in the recent run

At that point you can begin Phase 2 M2.1 work (H1 local-LLM redaction gate).

### What "NOGO" means

Keep the soak running. Common reasons for NOGO:

- **Audit chain broken** — incident, investigate immediately
- **Canary hit** — the strongest signal of privacy-boundary failure;
  start incident response
- **Insufficient usage** — the system's been idle. Either use it more,
  or accept that the soak metric is checking the wrong thing for your
  workflow and document the deviation
- **Harness regression** — likely a dependency upgrade broke something;
  re-run, investigate, fix, re-pass

## Upgrade path to Phase 2

When you're ready to enable the excerpt tool:

1. Install Phase 2 dependencies (Ollama for H1; Swift toolchain for H3).
2. Verify the M2 prerequisites: 30+ days clean Phase 1 soak, no canary
   hits, no audit chain breaks.
3. Build the H1 redactor, H3 consent UI, and M1 capability tokens (per
   `../.context/integrated-phased-plan.md` §2.1).
4. Run the full red-team harness with the excerpt-tool flag flipped on
   (`tests/redteam/`).
5. Flip `enable_excerpt_tool = true` in `default.toml`.

Until all four steps are done, leave `enable_excerpt_tool = false`.
