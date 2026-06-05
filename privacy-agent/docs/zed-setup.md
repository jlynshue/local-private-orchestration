# Zed setup

Zed supports MCP servers via its built-in settings. The privacy-agent integrates as a stdio extension.

## Configure MCP server

Edit `~/.config/zed/settings.json` (or project-level `.zed/settings.json`):

```json
{
  "context_servers": {
    "privacy-agent": {
      "command": {
        "path": "/absolute/path/to/privacy-agent/scripts/launch-privacy-agent.sh",
        "args": [],
        "env": {
          "PRIVACY_AGENT_ORCHESTRATOR": "zed"
        }
      }
    }
  }
}
```

## Default profile

```toml
[profiles.zed]
enable_excerpt_tool = false
classification_cap = "confidential"
```

Same as Cline/Codex/Continue: `restricted` blocked, excerpts disabled.

## Verify

Open Zed's assistant panel. The privacy-agent tools should appear in the
context-server tool list. Test with a simple `privacy_list_volumes` call.

## Hook asymmetry (R-3)

Zed does not execute `.claude-plugin/hooks.json`. Server-side enforcement only. Same caveat as all non-Claude-Code orchestrators.

## Troubleshooting

- **Context server not connecting**: ensure path is absolute. Zed resolves relative to its own binary, not the project root.
- **Missing tools**: check Zed's version. MCP support (under `context_servers`) landed in Zed 0.131+. Update if older.
- **Consent errors**: `privacy-cli consent grant` out-of-band.
