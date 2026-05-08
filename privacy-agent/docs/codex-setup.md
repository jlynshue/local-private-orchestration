# Codex CLI setup

Wire the privacy-agent MCP server into Codex CLI. Per-orchestrator profile (M2) caps Codex at `confidential` classification by default; `enable_excerpt_tool` is forced off.

## Add the MCP server

Edit `~/.codex/config.toml`:

```toml
[[mcp_servers]]
name = "privacy-agent"
command = "/absolute/path/to/privacy-agent/scripts/launch-privacy-agent.sh"
args = []

[mcp_servers.env]
PRIVACY_AGENT_ORCHESTRATOR = "codex"
```

`PRIVACY_AGENT_ORCHESTRATOR=codex` is the critical line. It tells the daemon which profile in `config/default.toml` to apply for this connection. Without it, the daemon falls back to the strictest profile (Goose), which may surprise.

Alternatively, use `codex mcp add` if your version of Codex supports it:

```
codex mcp add privacy-agent /absolute/path/to/privacy-agent/scripts/launch-privacy-agent.sh
```

…and edit the resulting config to add the `PRIVACY_AGENT_ORCHESTRATOR=codex` env var.

## Verify

Start Codex and ask it to list MCP tools. You should see:

- `privacy_search`
- `privacy_index_volume`
- `privacy_list_volumes`
- `privacy_get_consent`
- `privacy_audit_log`
- `privacy_classify`
- `privacy_file_summary`

`privacy_read_excerpt` is registered but blocked by the Codex profile. If it appears in the visible tool list, either (a) the profile didn't load (check the env var), or (b) the operator explicitly raised `profiles.codex.enable_excerpt_tool` — make sure that was intentional.

## Hook layer asymmetry

Codex does not run the `.claude-plugin/hooks.json` hooks. All policy enforcement for Codex is server-side: consent, classification cap, return-schema whitelist, PII redaction. There are no Bash deny-rules for Codex either.

Practical implication: if Codex has access to its own filesystem-read tools, it can bypass the privacy-agent entirely. This is documented as **R-3** in the architecture analysis. Mitigation:

- Configure Codex to disable raw filesystem read tools, OR
- Run sensitive workflows through Claude Code (which has the full hook stack) instead.

## Troubleshooting

- **Tool list empty**: the launch script likely failed. Check `~/.privacy-agent/server.log` (if logging is configured) or run the launch script manually from a shell to see the startup error.
- **`ConsentRequired` on every search**: grant volume search consent via `privacy-cli consent grant --path <volume> --scope search --granularity volume`.
- **Latency spike**: the Phase 2 H1 local-LLM redactor adds ~200 ms p95 to outbound responses. In Phase 1 this is not yet active, so anything beyond a few hundred ms typically points at indexing — check that `force_reindex=False` and that the index isn't being rebuilt under load.
