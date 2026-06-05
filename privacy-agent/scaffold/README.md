# Scaffold: Generate a new domain-specific MCP agent

This scaffold generates a self-contained MCP agent project using the
privacy-agent's reusable infrastructure: SHA-256 audit chain, consent
gates, per-orchestrator profiles, config loader, CLI, and test harness.

## Quick start

```bash
cd privacy-agent

python scaffold/generate.py \
    --name "secrets-scanner" \
    --description "Detects leaked API keys and credentials in codebases" \
    --output ~/projects/secrets-scanner \
    --orchestrators claude_code,codex,goose,cline
```

Output is a complete, installable, testable Python project. Tests pass
immediately on the scaffold (no domain logic wired yet).

```bash
cd ~/projects/secrets-scanner
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/  # all green from the start
```

## What you get

| Layer | File | What it does |
|---|---|---|
| Server | `src/<name>/server.py` | FastMCP stdio entry point |
| Core | `src/<name>/agent.py` | Wires audit, config, profiles |
| **Your domain** | `src/<name>/tools.py` | **Stub — fill this in** |
| Audit | `src/<name>/audit.py` | SHA-256 hash chain (ported) |
| DB | `src/<name>/db.py` | SQLite + WAL + 0600 |
| Config | `src/<name>/config.py` | TOML loader + validation |
| CLI | `src/<name>/cli.py` | `audit verify`, `audit recent` |
| Tests | `tests/test_scaffold.py` | Infra tests that pass immediately |
| Launch | `scripts/launch.sh` | Per-orchestrator MCP launcher |
| Config | `config/default.toml` | Profile entries pre-filled |

## What you fill in

1. **`tools.py`** — your MCP tools (the business logic)
2. **`config/default.toml`** — domain-specific config sections
3. **`tests/redteam/`** — domain-specific invariant corpus (H2 equivalent)
4. **Hooks** (optional) — if you want Claude-Code-specific bypass prevention

## Supported orchestrators

Any orchestrator that speaks MCP stdio:

| Orchestrator | Setup doc |
|---|---|
| Claude Code | plugin.json or `.mcp.json` |
| Codex CLI | `docs/codex-setup.md` |
| Goose | `docs/goose-setup.md` |
| Cline (VS Code / VSCodium) | `docs/cline-setup.md` |
| Continue.dev | `docs/continue-dev-setup.md` |
| Zed | `docs/zed-setup.md` |
| Cursor | same pattern as Cline |
| Aider | experimental MCP — test before deploying |

## Architecture inherited from privacy-agent

The scaffold carries forward the architectural decisions that worked:

- **Fail-closed by default** — missing consent, config errors, or audit-chain
  breaks result in tools being blocked, not data being exposed
- **Per-orchestrator trust profiles** — Goose (autonomous) gets the strictest
  cap; Claude Code (interactive, hooked) gets the most permissive
- **Schema enforcement** — frozen dataclasses are the return-type whitelist
- **Audit chain is mandatory** — every tool call is logged; tamper is detectable
- **stdio only** — no network bind; the daemon lives on the local pipe

What it does NOT carry forward (domain-specific, you rebuild):

- PII regex patterns
- File extractors
- Classification path rules
- Canary/honeytoken subsystem
- FTS5 search index
- The privacy-specific MCP tools

## Example domains that fit this pattern

- **Code-secrets DLP** — scan repos for leaked keys/tokens
- **Compliance checker** — validate code/config against policy rules
- **Local knowledge search** — index Obsidian vaults or note systems
- **Customer-data gateway** — consent-gated CRM data access
- **Test-data generator** — consent-gated access to prod schemas for synthetic data
- **Internal-doc Q&A** — privilege-aware document search
