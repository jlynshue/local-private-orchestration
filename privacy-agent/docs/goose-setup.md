# Goose setup

Goose runs autonomous multi-step plans, which raises its risk profile. The privacy-agent's M2 default profile reflects this: `classification_cap = "internal"`, `enable_excerpt_tool = False`. Goose cannot return `confidential` or `restricted` content even with consent.

If a Goose workflow legitimately needs higher-classification access, that workflow should run under Claude Code (with the full hook stack) instead. Avoid raising Goose's profile unless you've thought hard about the autonomy/access tradeoff.

## Add the MCP extension

```
goose configure
```

When prompted, add a new extension:

- Type: `stdio`
- Name: `privacy-agent`
- Command: `/absolute/path/to/privacy-agent/scripts/launch-privacy-agent.sh`
- Environment variable: `PRIVACY_AGENT_ORCHESTRATOR=goose`

Or edit Goose's config directly (`~/.config/goose/config.yaml`):

```yaml
extensions:
  privacy-agent:
    type: stdio
    cmd: /absolute/path/to/privacy-agent/scripts/launch-privacy-agent.sh
    args: []
    envs:
      PRIVACY_AGENT_ORCHESTRATOR: goose
```

## Verify

Start a Goose session and inspect available tools. You should see:

- `privacy_search`
- `privacy_index_volume`
- `privacy_list_volumes`
- `privacy_get_consent`
- `privacy_audit_log`
- `privacy_classify`
- `privacy_file_summary`

`privacy_read_excerpt` is registered but the Goose profile blocks it. Searches that touch confidential or restricted content will return zero results — by design — even if consent is granted.

## Why the Goose profile is stricter

Three reasons:
1. **Autonomy.** Goose chains many tool calls without per-step operator confirmation. A leaked grant amplifies further than in an interactive session.
2. **Less visibility.** Long autonomous runs are harder to monitor in real time. The strict cap is a fail-safe.
3. **Different threat model.** Goose may be deployed in headless workflows where the operator isn't watching the audit log; the cap reduces blast radius if something goes wrong.

## Hook layer asymmetry

Like Codex, Goose does not run the `.claude-plugin/hooks.json` hooks. Server-side controls (consent, classification cap, redaction, audit) are the sole enforcement. No Bash deny-rules apply.

If a Goose workflow uses a separate filesystem-read extension, it can bypass the privacy-agent entirely. Either:

- Disable the other read extension when this one is active, OR
- Confine sensitive Goose workflows to volumes that aren't indexed (explicit "not searchable") so the privacy-agent isn't even involved.

## Troubleshooting

- **`ClassificationBlocked` errors everywhere**: this is expected behavior for Goose with `confidential` content. Tell the user to either (a) re-classify the path to `internal` if it doesn't actually need stricter handling, or (b) use Claude Code for that workflow.
- **Tool not found**: check `goose info` lists `privacy-agent` as a connected extension. If not, the launch script likely errored — run it manually from a shell.
