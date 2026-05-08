---
name: privacy-index
description: Crawl and index a local volume into the privacy-agent's FTS5 index. Required before any privacy-search call against that volume. Index is encrypted at rest (when SQLCipher is installed) and content is PII-redacted before storage. Use when the user mounts a new external drive or first onboards a sensitive directory.
---

# privacy-index

Drive privacy-agent's indexer. Indexing reads files locally, redacts PII, and stores only the redacted text in an encrypted FTS5 index. Raw content never leaves the host.

## When to use this skill

- The user mounted a new external drive and wants its content searchable
- The user added a new sensitive directory (e.g., `~/Documents/Medical`)
- A previously-indexed volume's content has changed and needs re-indexing

## When NOT to use this skill

- You can already search what the user asked about. Re-indexing without reason is wasteful.
- The user only wants metadata about an existing volume — use `privacy_list_volumes` instead.

## Available tools

- `privacy_index_volume(volume_path, volume_id?, include_patterns?, exclude_patterns?, force_reindex?)` — primary
- `privacy_list_volumes()` — confirm what's already indexed before starting

## Workflow

1. Confirm the volume isn't already indexed (or is stale) via `privacy_list_volumes()`.
2. Confirm the operator has granted index consent: try `privacy_get_consent(path=<volume>, scope="index")`. If status is `denied`, surface the exact `privacy-cli` command for the operator to run.
3. Call `privacy_index_volume(volume_path=<absolute mount point>)`. Optionally narrow with `include_patterns` / `exclude_patterns` (glob, relative to volume root).
4. Report the returned `IndexStats`: `indexed_files`, `failed_files`, `total_indexed_bytes`, `file_type_counts`. Do NOT report individual file paths back to the user — the indexer audit log captures them locally; the orchestrator response is metadata-only.

## Consent model

Index consent is required and is granted out-of-band:

```
privacy-cli consent grant --path /Volumes/Backup --scope index --granularity volume
```

Index consent does NOT imply search consent. The user must also grant search consent before `privacy-search` will return results.

## Failure modes

- `ConsentRequired`: relay the CLI command. Do not attempt to grant consent yourself.
- `FileNotFoundError`: the volume isn't mounted or the path is wrong. Ask the user to verify.
- High `failed_files` count: report the count to the user. The audit log has per-file error detail; surface that they can run `privacy-cli audit recent` to see what failed.

## Example invocation

```
privacy_index_volume(
  volume_path="/Volumes/Backup",
  volume_id="vol_backup",
  exclude_patterns=["**/.DS_Store", "**/node_modules/**", "**/*.iso"],
  force_reindex=False
)
```

Indexes `/Volumes/Backup` with sensible exclusions, skipping anything already indexed and unchanged.
