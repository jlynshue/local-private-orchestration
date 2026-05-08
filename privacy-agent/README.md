# privacy-agent

Privacy-preserving local orchestration MCP daemon. Implements Phase 1 (Crawl) of the integrated phased plan in `../.context/integrated-phased-plan.md`.

## Status

**Phase 1 complete** — all 10 sub-milestones (M1.1 through M1.10) shipped. 148 tests passing including a 25-test adversarial red-team harness. Excerpt tool disabled by default (Sequencing Principle 3); flips on only after Phase 2 lands H1+H3+M1.

See `ACCEPTANCE.md` for the per-milestone exit-criteria checklist.

## Layout

```
privacy-agent/
├── src/privacy_agent/
│   ├── agent.py         PrivacyAgent — handler logic for all 8 tools
│   ├── server.py        FastMCP wiring (M1.5)
│   ├── cli.py           privacy-cli for OOB ops (M1.7+)
│   ├── types.py         frozen dataclasses (NFR-PRIV-2/PRIV-4)
│   ├── config.py        TOML loader + validation
│   ├── db.py            SQLite/SQLCipher with FTS5, WAL, 0600 (H5)
│   ├── redactor.py      PII regex + canary detection (M1.2 + H7)
│   ├── classifier.py    4-level path-based classification (M1.2)
│   ├── consent.py       Per-scope, time-window leases (M1.2 + M5)
│   ├── audit.py         SHA-256 hash chain + provenance (M1.2 + M6)
│   ├── canary.py        Honeytoken seeder + watcher (H7)
│   ├── search.py        FTS5 + BM25 + redacted snippets (M1.3)
│   ├── indexer.py       Volume crawler with redact-at-index (M1.3)
│   └── extractors/      text/pdf/docx/json/csv with optional deps
├── hooks/                Claude Code hooks (M1.7)
│   ├── pre_tool_use.py
│   ├── post_tool_use.py
│   └── session_start.py
├── .claude-plugin/
│   ├── plugin.json
│   ├── hooks.json
│   └── settings-fragment.json    Plan A's deny rules
├── skills/               Three SKILL.md files (M1.8)
│   ├── privacy-search/
│   ├── privacy-index/
│   └── privacy-manage/
├── scripts/
│   └── launch-privacy-agent.sh   MCP launcher (per-orchestrator)
├── docs/                 Codex / Goose setup
├── config/
│   ├── default.toml
│   └── default_pii_patterns.yaml
└── tests/
    ├── test_*.py         148 unit + integration tests
    └── redteam/          25 adversarial harness tests (M1.9)
```

## Setup

```bash
cd privacy-agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

For at-rest encryption (H5), additionally install:

```bash
pip install -e ".[encryption]"
```

If sqlcipher3 is not available, `db.open_db()` falls back to plain SQLite with a warning. The DB then depends on FileVault for at-rest protection.

## Documentation

- `ACCEPTANCE.md` — Phase 1 exit-criteria checklist (per sub-milestone)
- `THREAT_MODEL.md` — layered defense status, attack/mitigation table
- `COMPLIANCE.md` — HIPAA / PCI-DSS / GDPR / CCPA mapping
- `RUNBOOK.md` — first-run setup, daily/weekly tasks, recovery procedures
- `docs/codex-setup.md` — wire MCP server into Codex CLI
- `docs/goose-setup.md` — wire MCP server into Goose
- `design/` — locked-in design artifacts (architecture, enhancements,
  phased roadmap) that drove the Phase 1 build

## NFR references

See `../.context/architecture-impact-analysis.md` §6 for the full NFR list. Phase 1 status:

- **NFR-PRIV-1** Default-deny on raw content → `enable_excerpt_tool = false`. Two tests verify.
- **NFR-PRIV-2** No absolute paths in MCP responses → `volume_id + relative_path` everywhere; red-team verifies.
- **NFR-PRIV-3** PII redaction on every text field → applied at index *and* search time.
- **NFR-PRIV-4** Return-schema whitelist → frozen dataclasses; red-team `test_search_response_only_contains_declared_fields` verifies.
- **NFR-AUD-1** SHA-256 hash chain mandatory → `verify_chain_integrity()` runs at session start.
- **NFR-AUD-3** 0600 perms + WAL → applied in `db.open_db()`.
- **NFR-REL-1** Fail closed → every layer raises on policy violation; never partial data.
- **NFR-PERF-2** Snippet ≤ 200 chars default, ≤ 500 hard cap → enforced via config validation.

## Tool surface (8 MCP tools)

- `privacy_search` — ranked search with redacted snippets
- `privacy_index_volume` — crawl + redact + index a volume
- `privacy_read_excerpt` — disabled by default (Phase 1)
- `privacy_list_volumes` — indexed volume metadata
- `privacy_get_consent` — inspect consent state (does not prompt via stdio)
- `privacy_audit_log` — query audit trail
- `privacy_classify` — get/set path classification
- `privacy_file_summary` — sanitized natural-language summary
