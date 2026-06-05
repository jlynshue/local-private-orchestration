# Continue.dev setup

Continue.dev supports MCP stdio servers via its `config.json`. The privacy-agent provides the same 8-tool surface it exposes to Claude Code/Codex/Goose, with server-side enforcement.

## Configure MCP server

Edit `~/.continue/config.json`:

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "/absolute/path/to/privacy-agent/scripts/launch-privacy-agent.sh",
          "args": [],
          "env": {
            "PRIVACY_AGENT_ORCHESTRATOR": "continue_dev"
          }
        }
      }
    ]
  }
}
```

## Default profile

```toml
[profiles.continue_dev]
enable_excerpt_tool = false
classification_cap = "confidential"
```

Same semantics as Cline and Codex — `restricted` content blocked, excerpts disabled.

## Verify

Open a Continue chat. Ask it to list available tools — `privacy_search` and peers should appear. Test with `privacy_list_volumes`.

## Hook asymmetry (R-3)

Continue.dev does not execute Claude Code hooks. Server-side controls only. Same caveat as Codex/Goose/Cline: if Continue has its own file-read context provider, it can bypass the privacy-agent.

## Troubleshooting

- **Server not starting**: ensure the path in `config.json` is absolute. Relative paths fail in Continue's subprocess spawn.
- **No tools visible**: check Continue's version supports `experimental.modelContextProtocolServers` — this was added ~2024-Q4. Update to latest stable.
- **`ConsentRequired`**: run `privacy-cli consent grant` out-of-band.
