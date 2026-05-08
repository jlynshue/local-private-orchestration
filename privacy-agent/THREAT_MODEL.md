# Threat Model — privacy-agent Phase 1

The threat model in §5 of `../.context/architecture-impact-analysis.md` is the
authoritative source. This document records the Phase 1 implementation status
of each control and any deltas introduced during build-out.

## Trust boundaries

```
                            +-------------------------------+
                            |  orchestrator (claude_code,   |
                            |  codex, goose) — Anthropic /  |
                            |  OpenAI / etc cloud APIs      |
                            +--------------+----------------+
                                           | MCP stdio (local pipe)
                                           v
   +-----------------------------------------------------------------+
   |   privacy-agent daemon (Python, single-process, single-user)    |
   |     consent | classifier | redactor | search | indexer | audit  |
   +----+-----------+-------------+----------------+-----------------+
        |           |             |                |
   sqlite/sqlcipher pii_patterns canary corpus    audit log (chain)
   /Volumes/*  ~/Documents/...   ~/.privacy-agent/canaries
```

The privacy boundary is the dotted line: bytes above the daemon flow to a
cloud API; bytes below stay local. Every control's job is to ensure that
crossing the boundary preserves the data-minimization invariant.

## Layered defense, by Phase 1 control

| # | Layer | Status | NFR | Notes |
|---|---|---|---|---|
| 1 | `settings.json` deny rules (Bash bypass / Read sensitive paths) | shipped | — | `.claude-plugin/settings-fragment.json` is merged into operator settings |
| 2 | PreToolUse hook (regex inspection) | shipped | — | `hooks/pre_tool_use.py`, 7 unit tests; covers compound bash like `… \| strings -` |
| 3 | MCP server consent gate | shipped | NFR-REL-1 | `agent.handle_*` raise `ConsentRequired` when no active record covers the path/scope |
| 4 | Classification filter + cap | shipped | NFR-PRIV-1 | Per-orchestrator profile (M2): Goose=internal, Codex=confidential, Claude Code=uncapped |
| 5 | Return-schema whitelist | shipped | NFR-PRIV-4 | All MCP responses serialized via frozen dataclasses; redteam test asserts no undeclared fields |
| 6 | PII redactor (regex pass) | shipped | NFR-PRIV-3 | YAML-configurable patterns; tracked separately from canaries |
| 7 | PostToolUse safety net (PII + canary scan) | shipped | — | `hooks/post_tool_use.py`; signal-only, never blocks |
| 8 | Hash-chain audit log | shipped | NFR-AUD-1 | Mandatory; `verify_chain_integrity()` runs at session start and via `privacy-cli audit verify` |

Every layer fails closed independently. No layer trusts the layer above it.

## Threats and mitigations (Phase 1 status)

### Critical

**T-1. Claude reads sensitive files via Bash `cat`/`head`/`strings`.**
- Mitigation: `settings.json` deny + PreToolUse regex match. *Status: covered for Claude Code only* (Codex, Goose have no hook layer — see asymmetry note below).

**T-2. MCP server bug returns unsanitized content.**
- Mitigation: 3-layer defense — return-schema whitelist (`SearchResult` dataclass), PII regex (`PIIRedactor`), PostToolUse safety net. *Status: covered.* Red-team `test_indexed_db_does_not_contain_raw_pii` proves redaction at index time; `test_pii_never_leaks_via_search` proves it at search time.

**T-3. Canary marker leaks to cloud API.**
- Mitigation: H7 honeytokens + canary detection in redactor + critical audit event. *Status: covered.* Red-team `test_no_canary_marker_in_any_outbound_payload` proves it across 17+ queries.

### High

**T-4. Prompt injection in indexed file content.**
- Mitigation: server treats file content as data, not instructions; search logic is parameterized; redactor runs on extracted text. *Status: covered.* Red-team `test_prompt_injection_in_indexed_file_does_not_alter_response` validates that injection doesn't escape the schema.

**T-5. Malicious MCP server replacement.**
- Mitigation: server runs from a pinned local path (`scripts/launch-privacy-agent.sh`), not `npx`/`uvx`. SHA-256 manifest covers `src/privacy_agent/`, `hooks/`, and the launcher; `privacy_agent.manifest.verify()` runs at SessionStart and on demand via `privacy-cli manifest verify`. Mismatch logs a critical audit event. *Status: covered (Phase 1.5).* Operator workflow in `RUNBOOK.md`; tests in `tests/test_manifest.py`.

**T-6. Argument-level injection (FTS5 syntax, path traversal, control chars).**
- Mitigation: `SearchEngine._sanitize` strips FTS5 operators; path arguments are not used to construct shell commands; relative_path is resolved through the indexed-files table. *Status: covered.* Red-team parameterizes 7 hostile query strings and 4 hostile path strings.

### Medium

**T-7. Claude enumerates directories via many narrow queries.**
- Mitigation: `max_results_per_query` cap; per-session rate limit not yet implemented (deferred to M1 Phase 2 capability tokens for excerpt; for search the audit log is the primary signal). *Status: partial.*

**T-8. Consent bypass via crashed hook.**
- Mitigation: PreToolUse exit code 1 = block; SessionStart hook reports broken audit chain. Server-side consent gate is the second line. *Status: covered.*

**T-9. Audit log tampering.**
- Mitigation: append-only with SHA-256 hash chain; `verify_chain_integrity()` walks the chain. *Status: covered.* Red-team `test_audit_chain_breaks_on_tamper` and unit-test `test_tamper_detection_flips_hash` verify.

**T-10. Index DB exfiltrated from disk.**
- Mitigation: SQLCipher when installed, FileVault dependency otherwise; 0600 perms; redactor runs at index time so the DB itself contains no raw PII. *Status: SQLCipher abstracted but not installed by default* (R-2). Red-team `test_indexed_db_does_not_contain_raw_pii` proves the redaction-at-index behavior.

### Low

**T-11. Data remnants in Anthropic conversation history.**
- Mitigation: only sanitized metadata reaches the API; no PII by design. Phase 2 H1 adds an LLM redaction gate.

## Cross-orchestrator asymmetry

Hook-based controls (#1, #2, #7) only apply to Claude Code. Codex and Goose
rely on server-side controls (#3 through #8) exclusively. This is documented
as **R-3** in the architecture analysis with two mitigation options:

1. Configure those orchestrators to disable raw filesystem read tools.
2. Run sensitive workflows under Claude Code only.

Goose's per-orchestrator profile (M2) caps classification at `internal` and
forces `enable_excerpt_tool=False` to compensate for the missing hook layer.
Codex's profile is similar but with `classification_cap = "confidential"`.

## Out of scope for Phase 1

- TEE-backed signing (L2 territory)
- Federated multi-host index sync (Phase 3)
- Differential privacy on aggregate counts (considered, not built — see
  enhancement-proposals.md "What is not proposed here")
- iOS companion (L1, Phase 3)

## Phase 2 deltas to anticipate

When Phase 2 lands, this threat model gets four new mitigations:

- **H1** local-LLM redaction gate → strengthens T-2 against contextual
  leakage that regex misses
- **H3** OOB consent UI → eliminates the prompt-injection vector against
  consent prompts (currently mitigated by stdio-prompt deprecation)
- **M1** capability tokens → tightens T-7 (rate limiting via per-read tokens)
- **H6** egress firewall → adds a network-layer guard for T-2/T-10
