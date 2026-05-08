---
name: privacy-search
description: Search indexed local volumes for sensitive content via the privacy-agent MCP server. Returns ranked metadata + redacted snippets only. Use when the user asks to find content on external drives or sensitive directories ("find my tax docs", "what's on my backup drive about X"). Never returns raw file content.
---

# privacy-search

Search the privacy-agent's local FTS5 index. Results are ranked by BM25 and stripped of PII before return.

## When to use this skill

- The user asks to find files or content on a local drive or sensitive directory
- The user wants to enumerate what's available before deciding whether to read further
- The user asks "what tax / legal / medical documents do I have"

## When NOT to use this skill

- The user wants to read raw file content. The excerpt tool is disabled by default in Phase 1; ask the user to use `privacy-cli` or wait for Phase 2 H3 consent UI.
- The data is already in the conversation context — re-searching is wasteful.

## Available tools

- `privacy_search(query, scope?, max_results?, classification_filter?, file_types?)` — primary search
- `privacy_list_volumes()` — see what's indexed
- `privacy_file_summary(volume_id, relative_path)` — sanitized metadata + summary for a specific file
- `privacy_classify(path, set_level?)` — read or set sensitivity classification for a path

## Workflow

1. If you don't yet know what volumes are indexed, call `privacy_list_volumes()`.
2. Issue `privacy_search(query=..., scope=<volume_path>)`. The scope argument is required when consent is enforced at the volume level (default config).
3. Surface results to the user with `volume_id`, `relative_path`, `classification`, and the redacted snippet. Never paraphrase the snippet in a way that reverses the redaction.
4. If the user wants more on a particular file, call `privacy_file_summary(volume_id, relative_path)` rather than trying to read the file directly.

## Consent model

Consent is granted out-of-band via `privacy-cli consent grant --path <volume> --scope search --granularity volume`. If the user asks you to search and the call returns `ConsentRequired`, surface the exact CLI command to run and stop. Do not attempt to grant consent yourself.

## Failure modes

- `ConsentRequired`: relay the CLI command to the user; do not retry.
- `ClassificationBlocked`: the file's classification exceeds your orchestrator profile's cap. Surface the cap and ask the user whether they want to elevate the profile or open a separate session under a more permissive orchestrator.
- Empty results: confirm the volume is actually indexed (`privacy_index_volume` first if needed; that also requires consent).

## Example invocation

```
privacy_search(
  query="2024 tax return",
  scope="/Volumes/Backup",
  max_results=5,
  classification_filter=["confidential"],
  file_types=["pdf", "txt"]
)
```

Returns up to 5 results, all confidential, all PDFs/TXTs, all under `/Volumes/Backup`.
