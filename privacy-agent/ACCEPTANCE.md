# Phase 1 Acceptance — privacy-agent

The exit criteria from the integrated phased plan (M1.1–M1.10), each backed by
a verifiable artifact (test, file, or runbook step).

## Sub-milestone exit criteria

### M1.1 — Foundation
- [x] `tests/test_db.py` green; encrypted-DB fallback path verified
- [x] DB file is 0600 (`test_db_file_is_0600`)
- [x] WAL journal mode (`test_wal_journal_mode`)
- [x] FTS5 virtual table created (`test_open_creates_file_and_schema`)
- [x] `tests/test_config.py` covers TOML round-trip + validation rules

### M1.2 — Privacy primitives
- [x] PII fixtures (SSN, CC, account, phone, email, IP, amount) all caught (`tests/test_redactor.py`)
- [x] Consent expiry deterministic; M5 short-window leases tested (`test_window_lease_expires`)
- [x] Tamper detection green (`test_tamper_detection_flips_hash`)
- [x] Provenance round-trip verified (`test_provenance_id_round_trip`)

### M1.3 — Extraction, search, indexing
- [x] Indexer writes redacted content to FTS5 — raw PII never present (`test_redacts_content_at_index_time`)
- [x] Classification filter + cap (`test_classification_cap_blocks_restricted`)
- [x] Search snippets pass through redactor (`test_search_snippet_redacted`)
- [x] Provenance UUID stamped per result (`test_search_provenance_id_present`)
- [x] FTS5 query injection sanitized (red-team tests)

### M1.4 — Canary subsystem (H7)
- [x] `seed_canaries` creates 0600 files with unique markers
- [x] Canary in payload yields critical audit event (`test_watcher_logs_critical_on_canary_hit`)
- [x] `list_canaries` recovers metadata
- [x] Redactor masks markers in payloads (`test_canary_redacted_in_payload`)

### M1.5 — MCP server
- [x] `pytest tests/test_server.py` registers all 8 tools on a real FastMCP instance
- [x] Excerpt tool returns `tool disabled` in default config (`test_excerpt_disabled_by_default`)
- [x] All MCP responses route through dataclass serialization; redteam asserts no undeclared fields (`test_search_response_only_contains_declared_fields`)

### M1.6 — Per-orchestrator policy profiles (M2)
- [x] Goose orchestrator gets stricter cap (`test_search_excludes_restricted_under_goose_profile`)
- [x] Unknown orchestrator falls back to strictest profile (`test_unknown_orchestrator_gets_strictest_profile`)
- [x] Claude Code defaults are uncapped (`test_claude_code_profile_inherits_defaults`)

### M1.7 — Claude Code hooks + plugin
- [x] PreToolUse blocks compound-bash bypasses (`test_pre_tool_use_blocks_compound_bash`)
- [x] PreToolUse permits innocuous bash on sensitive paths (`test_pre_tool_use_allows_bash_ls_on_sensitive_path`)
- [x] PreToolUse blocks Read against sensitive dirs (`test_pre_tool_use_blocks_read_against_sensitive_dir`)
- [x] PostToolUse warns on canary in tool result (`test_post_tool_use_warns_on_canary_in_response`)
- [x] SessionStart runs cleanly (`test_session_start_runs_and_exits_zero`)
- [x] `.claude-plugin/plugin.json`, `hooks.json`, `settings-fragment.json` present
- [x] Launch script executable, modeled on `launch-ebay.sh`

### M1.8 — Skills + multi-orchestrator
- [x] Three SKILL.md files written (`privacy-search`, `privacy-index`, `privacy-manage`)
- [x] Codex setup documented (`docs/codex-setup.md`)
- [x] Goose setup documented (`docs/goose-setup.md`)
- [x] Both docs flag the hook-asymmetry caveat (R-3)

### M1.9 — Adversarial red-team harness
- [x] Corpus seeded with PII + canaries + prompt-injection content
- [x] PII never leaks via search (`test_pii_never_leaks_via_search`)
- [x] PII never leaks via file_summary (`test_pii_never_leaks_via_file_summary`)
- [x] Audit log responses exclude paths_accessed (`test_pii_never_leaks_via_audit_log`)
- [x] Prompt-injection content doesn't alter response shape (`test_prompt_injection_in_indexed_file_does_not_alter_response`)
- [x] Restricted blocked under stricter profile (`test_restricted_blocked_under_default_profile`)
- [x] Search/index/excerpt all require their respective consents
- [x] Excerpt tool off by default (`test_excerpt_tool_off_by_default`)
- [x] 7 hostile FTS5 queries sanitized without crash or leak (parameterized)
- [x] 4 hostile path-traversal patterns isolated (parameterized)
- [x] **Pass criterion: zero canary markers in any captured outbound payload across 17+ queries** (`test_no_canary_marker_in_any_outbound_payload`)
- [x] Audit chain breaks on tamper (`test_audit_chain_breaks_on_tamper`)
- [x] Index DB contains no raw PII (`test_indexed_db_does_not_contain_raw_pii`)
- [x] No undeclared fields in MCP responses (`test_search_response_only_contains_declared_fields`)

### M1.10 — Documentation and acceptance
- [x] `THREAT_MODEL.md` — layered defense status, Phase 1 deltas
- [x] `COMPLIANCE.md` — HIPAA / PCI-DSS / GDPR / CCPA mapping
- [x] `RUNBOOK.md` — first-run setup, daily/weekly tasks, recovery procedures
- [x] `README.md` updated with current state
- [x] This `ACCEPTANCE.md` checklist
- [x] Final acceptance test pass

## Quantitative Phase 1 metrics

| Metric | Target | Actual |
|---|---|---|
| Total tests | — | **148 passing**, 1 skipped (sqlcipher absent — fallback verified) |
| Red-team tests | ≥ 20 attack scenarios | **25** |
| Canary leakage in red-team sweep | 0 markers | 0 ✓ |
| PII leakage in red-team sweep | 0 occurrences of corpus PII strings | 0 ✓ |
| Phase 1 milestones | 10 | 10 ✓ |
| NFRs covered | 14 | 11 fully, 3 partial (NFR-PORT-1 macOS-only, NFR-PERF-1 not benchmarked, T-5 hash pinning deferred) |

## Sequencing principles satisfied

1. **Foundational protections shipped early.** ✓ H5 (encryption), H7 (canary), H2 (red-team harness) all in Phase 1 despite source plans putting some in later phases.
2. **Invariant gate automated.** ✓ Red-team harness is a pytest gate; CI integration is a one-liner.
3. **Excerpt tool off by default.** ✓ `enable_excerpt_tool = false` in `default.toml`; the only path to flip it on is editing config explicitly. Two tests verify the gate.

## Open items carried into Phase 2 entry review

These don't block Phase 1 acceptance but must resolve before starting Phase 2:

- **T-5 hardening**: file-hash verification on plugin/server load (deferred)
- **NFR-PERF-1 baselines**: search p95 / index throughput not yet benchmarked
- **Open Questions Q-A through Q-G** (integrated-phased-plan.md §6) plus Q-1 through Q-10 from the architecture analysis
- **30-day soak**: time-based criterion the operator decides on
- **No unresolved canary hits during soak**: operator confirms via runbook

## Sign-off

When the operator is satisfied, the formal sign-off is the operator running:

```bash
.venv/bin/pytest tests/ tests/redteam/ -q
.venv/bin/privacy-cli audit verify
.venv/bin/privacy-cli canary list --dir ~/.privacy-agent/canaries
```

…and confirming all three return clean. Phase 1 is complete when those three
checks pass and the soak period has elapsed without unresolved warnings.
