---
name: privacy-manage
description: Inspect and manage the privacy-agent's audit log, consent records, and classification rules. Use when the user asks "what searches happened recently", "who/what accessed X", "show me the audit trail", "verify integrity", or wants to check or change classification levels. Surfaces management functionality in-session; mutations still happen out-of-band via privacy-cli.
---

# privacy-manage

Read-side inspection of privacy-agent's operational state. Mutations (granting consent, seeding canaries, force-rotating keys) happen out-of-band via `privacy-cli` to keep them resistant to prompt-injection.

## When to use this skill

- The user wants to see what searches/reads happened recently
- The user is investigating a suspected leak ("did anything ever return our SSN?")
- The user wants the current classification of a path
- The user wants to verify the audit chain hasn't been tampered with
- The user is preparing the weekly canary-watch review (Phase 2 will automate this in the M3 dashboard)

## Available tools

- `privacy_audit_log(since?, until?, action_filter?, severity_filter?, limit?)` — query audit
- `privacy_get_consent(path, scope, request?)` — inspect consent state for a path
- `privacy_classify(path, set_level?, reason?)` — read or set classification

## Workflow — audit review

1. To review recent activity: `privacy_audit_log(limit=50)`. The response excludes `paths_accessed` (NFR-PRIV-2); the operator can run `privacy-cli audit recent` for full detail.
2. To investigate suspected leak: `privacy_audit_log(severity_filter="critical")`. Any `canary_hit` entry warrants immediate operator attention.
3. To verify integrity: tell the operator to run `privacy-cli audit verify`. The chain is also re-verified at every session start (SessionStart hook surfaces a warning if it breaks).

## Workflow — consent inspection

1. `privacy_get_consent(path, scope)` returns `granted` / `denied` / `pending`.
2. To request a new grant, return the `instructions` string verbatim — it includes the exact `privacy-cli consent grant` command. Do not attempt to grant consent yourself.

## Workflow — classification

1. `privacy_classify(path)` returns the current classification.
2. `privacy_classify(path, set_level=...)` adds an override rule. Levels: `public`, `internal`, `confidential`, `restricted`. The classifier ratchets up only — a `set_level="public"` against a path already matching a `restricted` rule will be ignored.
3. New rules apply at next index time. Existing already-indexed files are NOT re-classified retroactively unless `privacy_index_volume(force_reindex=True)`.

## CLI escape hatches

For operator-only actions, surface the relevant command:

| Need | Command |
|---|---|
| Grant consent | `privacy-cli consent grant --path <p> --scope <s> --granularity <g>` |
| Revoke consent | `privacy-cli consent revoke --id <consent_id>` |
| List active consents | `privacy-cli consent list` |
| Verify audit chain | `privacy-cli audit verify` |
| Recent audit detail | `privacy-cli audit recent` |
| Seed canaries | `privacy-cli canary seed --dir ~/.privacy-agent/canaries --count 3` |
| List canaries | `privacy-cli canary list --dir ~/.privacy-agent/canaries` |

## Example invocation

```
privacy_audit_log(severity_filter="warning", limit=20)
```

Returns the last 20 warning-level events: hook blocks, PII safety-net catches, expired-consent attempts. A burst of warnings in a small time window is a signal to investigate.
