# ${AGENT_NAME_HUMAN}

${AGENT_DESCRIPTION}

Generated from the [privacy-agent scaffold](https://github.com/jlynshue/local-private-orchestration).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/
```

## Layout

```
src/${AGENT_NAME_SNAKE}/
├── server.py       MCP stdio entry point
├── agent.py        Application core (audit, profiles)
├── tools.py        YOUR DOMAIN TOOLS GO HERE
├── audit.py        SHA-256 hash-chain audit log
├── config.py       TOML config loader
├── db.py           SQLite (WAL, 0600)
└── cli.py          Out-of-band CLI
```

## Wiring to orchestrators

| Orchestrator | How |
|---|---|
| Claude Code | `.claude-plugin/plugin.json` or `.mcp.json` entry |
| Codex CLI | `~/.codex/config.toml` entry |
| Goose | `goose configure` → stdio extension |
| Cline (VSCodium/VS Code) | `.vscode/mcp.json` or global settings |
| Continue.dev | `~/.continue/config.json` MCP block |
| Zed | `~/.config/zed/settings.json` MCP block |
| Cursor | `.cursor/mcp.json` entry |

All use the same pattern:
```json
{
  "command": "/absolute/path/to/scripts/launch.sh",
  "args": [],
  "env": { "AGENT_ORCHESTRATOR": "<orchestrator_name>" }
}
```

## Reusable infrastructure (inherited from privacy-agent)

- SHA-256 hash-chain audit log (tamper-evident)
- Per-orchestrator policy profiles (caps, tool gates)
- SQLite + WAL + 0600 perms
- Config loader with validation (stdio-only enforcement)
- CLI for out-of-band operations

## What to build

1. **`src/${AGENT_NAME_SNAKE}/tools.py`** — your domain's MCP tools
2. **`config/default.toml`** — extend with domain-specific sections
3. **`tests/redteam/`** — attack corpus for your domain's invariant
4. **Hooks** (optional) — if targeting Claude Code with bypass prevention
