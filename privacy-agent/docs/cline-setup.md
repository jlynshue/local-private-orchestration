# Cline (VS Code / VSCodium) setup

Cline supports MCP via stdio since v3. The privacy-agent's server-side controls (consent, classification cap, PII redaction, audit chain) apply to Cline exactly as they do to Codex/Goose.

## Configure MCP server

Add to your project's `.vscode/mcp.json` (or global VS Code settings):

```json
{
  "servers": {
    "privacy-agent": {
      "command": "/absolute/path/to/privacy-agent/scripts/launch-privacy-agent.sh",
      "args": [],
      "env": {
        "PRIVACY_AGENT_ORCHESTRATOR": "cline"
      }
    }
  }
}
```

Or in VS Code's `settings.json`:

```json
{
  "cline.mcpServers": {
    "privacy-agent": {
      "command": "/absolute/path/to/privacy-agent/scripts/launch-privacy-agent.sh",
      "args": [],
      "env": {
        "PRIVACY_AGENT_ORCHESTRATOR": "cline"
      }
    }
  }
}
```

## Default profile

Per M2, Cline ships with:

```toml
[profiles.cline]
enable_excerpt_tool = false
classification_cap = "confidential"
```

This means:
- No raw file excerpts (excerpt tool disabled)
- `restricted` content blocked from search results
- `confidential` and below are visible in metadata + redacted snippets

## Verify

Open a Cline chat. You should see the privacy-agent tools in the tool list:
`privacy_search`, `privacy_index_volume`, `privacy_list_volumes`,
`privacy_get_consent`, `privacy_audit_log`, `privacy_classify`,
`privacy_file_summary`.

`privacy_read_excerpt` is registered but blocked by the profile.

## Hook asymmetry (R-3)

Same as Codex/Goose: Cline does not execute `.claude-plugin/hooks.json`.
All enforcement for Cline is server-side. If Cline has its own file-read
tools that bypass the privacy-agent, the operator must disable those tools
or confine sensitive workflows to Claude Code (which has the hook stack).

## Troubleshooting

- **Tools don't appear**: check the launch script path is absolute and executable (`chmod +x`). Restart Cline extension after saving `mcp.json`.
- **`ConsentRequired` on every call**: grant consent via `privacy-cli consent grant --path <volume> --scope search --granularity volume`.
- **Cline version too old**: MCP support was added in Cline v3.0. Update if you're on v2.x.
