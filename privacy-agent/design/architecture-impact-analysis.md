# Architecture Impact Analysis: Privacy-Preserving Local Orchestration

**Sources reviewed**

- Plan A — `/Users/jonathanlyn-shue/.claude/plans/title-privacy-preserving-orchestration-robust-moth.md`
- Plan B — `/Users/jonathanlyn-shue/code-projects/projects/conductor/implementation_plan.md`

---

## 1. Executive Summary

The two plans target the same problem — letting an LLM orchestrator search sensitive files on local and external drives without leaking content to a cloud API — but make materially different architectural choices. They are complementary in places and directly conflicting in others.

| Dimension | Plan A ("robust-moth") | Plan B ("implementation_plan") |
|---|---|---|
| Scope of orchestrators | Claude Code only | Claude Code + Codex CLI + Goose |
| Component shape | Plugin with **2 MCP servers** + **3 hooks** | Single **MCP server** (`privacy-agent`) with **7 tools**; no hooks specified |
| Search backend | Live filesystem walk per query | Persistent **SQLite FTS5 index** (vector search in Phase 2) |
| Content returned to orchestrator | Metadata + sanitized summary, **never raw content** | Metadata + 200-char **snippets** + on-demand **excerpts** (per-file consent) |
| PII redaction layer | **Required** — regex engine + return-schema whitelist + PostToolUse safety net | Not specified |
| Permissions / deny rules | Explicit `Bash(cat:*)`, `Read(/Volumes/*)`, etc. deny entries | Not specified |
| Audit log | Append-only JSONL, optional hash chain | **SQLite + mandatory SHA-256 hash chain** with verification |
| Distribution surface | Claude Code plugin in `~/code-projects/projects/active/` | Conductor repo + **gstack skills** (`/privacy-search`, `/privacy-index`, `/privacy-manage`) via resolver/preamble build system |
| Phasing | 1 metadata → 2 Ollama summaries → 3 hybrid interactive | 1 FTS5 → 2 ChromaDB semantic + at-rest encryption → 3 multi-user RBAC, Docker, SIEM |

**Recommended target architecture:** adopt Plan B's `privacy-agent` server, **persistent FTS5 index**, **gstack skills**, and **multi-orchestrator** model as the spine; layer Plan A's **PII redaction engine, deny-rules, hooks, and "no raw content by default"** posture on top as enforced policy. The combined design retains Plan B's reach and ergonomics while inheriting Plan A's defense-in-depth.

---

## 2. Architecture Implications

### 2.1 Confirmed shared decisions (no change needed)

These decisions are present in both plans and should be locked in:

- **Local-only execution.** stdio MCP transport, no network bind. (Plan A explicit; Plan B `bind = "stdio"` with explicit "never tcp".)
- **Consent-gated access.** A consent record/file is required before any sensitive read. Failure mode is fail-closed.
- **Path/scope-based classification.** Sensitive directories are tagged (Plan A's "sensitivity classification" / Plan B's `public|internal|confidential|restricted` rules with glob patterns).
- **Audit logging on every tool invocation.** Append-only, hash chain optional → recommended mandatory (see §6).
- **Crawl → Walk → Run phasing.** Both plans converge on this trajectory; Plan B's Phase 2 (semantic search, encryption at rest) and Plan A's Phase 2 (Ollama summarization) are non-conflicting and both belong on the roadmap.
- **External-drive scoping.** `/Volumes/*` is the primary external surface; both plans assume macOS-first.

### 2.2 Architectural changes (Plan B preferred over Plan A)

**B-over-A: Single MCP server with multiple tools, not two separate MCP servers.**
- *Rationale:* Plan B's seven tools cover Plan A's six tools plus `privacy_read_excerpt`, `privacy_get_consent`, `privacy_audit_log`, and `privacy_classify` — observability and management surface that Plan A lacks. Operating one daemon with one DB simplifies state, lifecycle, and audit-chain integrity.
- *Trade-off:* loses Plan A's clean "two-server" boundary that maps to two conceptual concerns (local docs vs external drives). Mitigated by tool-name namespacing — `privacy_search`, `privacy_index_volume`, `privacy_list_volumes` already encode the split.

**B-over-A: Persistent SQLite FTS5 index instead of per-query filesystem walks.**
- *Rationale:* Indexed search scales to large drives, supports BM25 ranking, snippet generation, and (in Phase 2) hybrid retrieval. Plan A's "walk on every query" approach degrades on multi-TB external drives and gives no relevance ordering.
- *Trade-off:* index storage is now a sensitive asset (it contains extracted content). Mitigation: encryption at rest in Phase 2 via macOS Keychain key, consent gates around the index DB itself, no plaintext content fields exposed in MCP responses unless excerpt explicitly requested.

**B-over-A: Multi-orchestrator support (Claude Code, Codex CLI, Goose).**
- *Rationale:* Plan A scopes to Claude Code; Plan B explicitly registers via `~/.codex/config.toml` and Goose. Same daemon serves all three — economy of scale and a single audit trail.
- *Trade-off:* Plan A's hook-based enforcement does not apply to Codex or Goose. Server-side enforcement (data minimization, consent, classification filtering) becomes the **only** enforcement boundary for non-Claude-Code orchestrators. This raises the bar on server-side controls.

**B-over-A: Gstack skill packaging.**
- *Rationale:* Plan B's `/privacy-search`, `/privacy-index`, `/privacy-manage` skills with template/resolver pattern give natural, discoverable invocation. Plan A relies on prompt-only discovery.
- *Trade-off:* gstack build coupling. The resolver `privacy.ts` and preamble registration become required artifacts.

### 2.3 Architectural additions (Plan A preferred over Plan B)

**A-over-B: PreToolUse / PostToolUse / SessionStart hooks.**
- *Rationale:* Plan B has no hooks. Hooks are the only mechanism to:
  - Block raw `Bash(cat:*)`, `Read(~/Documents/Tax/*)`, etc., that bypass the MCP server entirely.
  - Run a PII safety-net scan on tool *output* before it reaches the model context.
  - Validate consent at session start and force fail-closed behavior on hook failure.
- *Trade-off:* hooks are Claude Code-specific. They cannot enforce against Codex or Goose. Document this asymmetry: Claude Code gets defense-in-depth; Codex/Goose rely on server-side controls only.

**A-over-B: PII redaction library + return-schema whitelist.**
- *Rationale:* Plan B can return content excerpts and snippets from indexed text. Without an explicit redaction layer, an SSN inside a `restricted` PDF that gets indexed will appear in the snippet and flow to the API. The classification filter blocks the *file* but not the *content already pulled into the snippet pipeline*. Plan A's three-layer defense (return-schema whitelist → PII regex → PostToolUse safety net) closes this gap.
- *Trade-off:* false positives in regex redaction can damage useful snippets. Mitigation: redact rather than reject; emit a `pii_redacted: true` flag in results.

**A-over-B: Permission deny rules in `settings.json`.**
- *Rationale:* Plan A enumerates `Bash(cat:*)`, `Bash(head:*)`, `Bash(strings:*)`, `Bash(xxd:*)`, `Bash(open:*)`, `Read(/Volumes/*)`, `Read(~/Documents/{Tax,Legal,Medical,Finance}/*)`. Plan B does not. Without these, a Claude Code session can read files directly via Read or Bash, bypassing the MCP server entirely.
- *Trade-off:* explicit allowlists are brittle and need maintenance as the user adds sensitive directories.

**A-over-B: Mandatory "no raw content by default" posture.**
- *Rationale:* Plan B's `privacy_read_excerpt` (max 2000 chars) returns raw file content under per-file consent. This is more permissive than Plan A's strict metadata-only stance. Recommendation: **keep `privacy_read_excerpt` but disable by default** via a config flag (`[agent] enable_excerpt_tool = false`) and require explicit user enablement plus per-file consent. See §3 for conflict resolution.

### 2.4 Net architecture (recommended)

```
┌────────────────────────────────────────────────────────────────────┐
│                       User's macOS host                            │
│                                                                    │
│  Orchestrators (any of):                                           │
│    Claude Code  ──┐                                                │
│    Codex CLI    ──┼── stdio MCP ──► privacy-agent (Python daemon)  │
│    Goose        ──┘                                                │
│                                  │                                 │
│                                  ├── ConsentManager                │
│                                  ├── AuditLogger (SQLite + hash)   │
│                                  ├── SearchEngine (FTS5 + BM25)    │
│                                  ├── Indexer (volumes, extractors) │
│                                  ├── Classifier (path rules)       │
│                                  └── PIIRedactor      ◄── NEW      │
│                                                                    │
│  Claude Code only:                                                 │
│    PreToolUse hook  ──► Policy enforcer (path scope, consent,      │
│                          rate limit, Bash deny)                    │
│    PostToolUse hook ──► Audit log forwarder + PII safety-net scan  │
│    SessionStart     ──► Consent verification, fail-closed if       │
│                          missing/expired                           │
│                                                                    │
│  Filesystem-level:                                                 │
│    ~/.privacy-agent/db.sqlite        (FTS5 + audit + consent)      │
│    ~/.privacy-agent/config.toml      (config)                      │
│    ~/.privacy-agent/policy.yaml      (allowed/denied paths, PII    │
│                                       patterns)                    │
└────────────────────────────────────────────────────────────────────┘
                              │
                              │ MCP responses contain ONLY:
                              │   metadata, classification, snippet
                              │   (post-redaction), sanitized summary
                              ▼
                       Anthropic / OpenAI / etc. API
```

---

## 3. Component Mapping (merged design)

Each row identifies the source plan and the resolution where they conflict.

| Component | Source | Resolution |
|---|---|---|
| `privacy-agent` MCP server (stdio) | B | Adopt as-is. Located per Plan B at `conductor/repos/privacy-agent/`. |
| Tool: `privacy_search` | B | Adopt. Returns ranked results with snippets ≤ 200 chars. |
| Tool: `privacy_index_volume` | B | Adopt. Volume consent required. |
| Tool: `privacy_read_excerpt` | B | **Adopt with gating.** Disabled by default via `[agent] enable_excerpt_tool = false`. When enabled, requires per-file consent + classification ≤ `confidential` (no `restricted` excerpts unless user explicitly elevates). All excerpts pass through PII redactor. |
| Tool: `privacy_list_volumes` | B | Adopt. |
| Tool: `privacy_get_consent` | B | Adopt. |
| Tool: `privacy_audit_log` | B | Adopt. |
| Tool: `privacy_classify` | B | Adopt. |
| Tool: `get_file_summary` | A | **Add to Plan B's tool set** — returns sanitized natural-language summary built from extracted content; useful before pulling an excerpt. Honors `restricted` filter. |
| `Database` (SQLite, FTS5, WAL) | B | Adopt. |
| `ConsentManager` | B | Adopt. Granularity: file/directory/volume per Plan B. |
| `AuditLogger` (SHA-256 hash chain) | B | Adopt. Promote hash chain from Plan A's "optional" to **mandatory**. |
| `SearchEngine` | B | Adopt. |
| `Classifier` (4-level: public/internal/confidential/restricted) | B | Adopt. Plan A's looser "sensitivity" string is subsumed. |
| `Indexer` + extractors (text/pdf/docx/json/csv) | B | Adopt. |
| `PIIRedactor` | A | **Add to Plan B.** Imported by `SearchEngine.generate_snippet`, `extractors/*` (post-extract), and `read_excerpt` handler. Uses configurable `pii_patterns.yaml`. |
| Return-schema whitelisting | A | **Add to Plan B.** Each tool's response is validated against an explicit dataclass before serialization — fields not in the schema are dropped, not silently passed through. |
| Hook: PreToolUse policy enforcer | A | **Claude Code only.** Validates consent, scope, rate limit; blocks `Bash` regex-matching sensitive paths. |
| Hook: PostToolUse audit/PII safety net | A | **Claude Code only.** Forwards events to `privacy-agent` audit log; runs second-pass PII scan. |
| Hook: SessionStart consent gate | A | **Claude Code only.** Reads consent state from `privacy-agent`, disables tools if missing/expired. |
| `settings.json` deny rules | A | **Claude Code only.** Standard deny-set: `Bash(cat:*)`, `Bash(head:*)`, `Bash(tail:*)`, `Bash(less:*)`, `Bash(more:*)`, `Bash(strings:*)`, `Bash(xxd:*)`, `Bash(hexdump:*)`, `Bash(base64:*)`, `Bash(open:*)`, `Read(/Volumes/*)`, `Read(~/Documents/{Tax,Legal,Medical,Finance}/*)`. |
| Gstack skills `/privacy-search`, `/privacy-index`, `/privacy-manage` | B | Adopt. Resolver `privacy.ts` per Plan B. |
| MCP registration for Codex / Goose | B | Adopt. |
| Phase 2: Ollama-backed summarization | A | **Add to Plan B's Phase 2.** Optional `summarize_file` tool; LLM runs locally; only the summary crosses to the orchestrator. |
| Phase 2: ChromaDB hybrid search + at-rest encryption | B | Adopt. |
| Phase 3: multi-user RBAC, Docker, SIEM export | B | Adopt. |

### 3.1 Conflict resolution

Three direct conflicts exist between the plans. Per the task's conflict-resolution rule (prioritize stated constraints and do-nots; flag with justification):

**Conflict 1 — Raw content exposure.**
- *Plan A:* "Never returns raw content."
- *Plan B:* `privacy_read_excerpt` returns up to 2000 chars of raw content under per-file consent.
- *Resolution:* honor Plan A's stricter posture as the **default**, retain Plan B's tool as an **opt-in capability**. `enable_excerpt_tool = false` ships off; the user must flip it explicitly. When on, every excerpt passes through the PII redactor and is bounded by classification (`restricted` blocked unless explicitly overridden). This preserves both plans' constraints: Plan A's "never by default" and Plan B's "with consent, when needed."

**Conflict 2 — Returning absolute paths.**
- *Plan A:* "Never returns full absolute paths" (only basenames + directory tree).
- *Plan B:* `SearchResult.path` is "Absolute file path."
- *Resolution:* honor Plan A. Replace `SearchResult.path` with `volume_id` + `relative_path`. The orchestrator never sees the user's home directory layout. The server retains absolute paths internally for the `read_excerpt` flow, dereferenced from a server-side handle.

**Conflict 3 — Snippet content.**
- *Plan A:* implicit — snippets are a summary, not file text.
- *Plan B:* snippet is "content excerpt, max 200 chars" — actual file text.
- *Resolution:* keep Plan B's text snippet but **always pass through the PII redactor** before the snippet leaves `SearchEngine.generate_snippet`. Add a `pii_redactions_applied: int` field to `SearchResult` so downstream tooling knows whether masking occurred.

---

## 4. Data and Control Flows

### 4.1 Indexing flow (write path)

```
User → Claude Code → /privacy-index skill → privacy_index_volume(volume_path)
  │
  └─► PreToolUse hook (Claude Code only):
       ├── consent check via privacy_get_consent
       ├── volume_path ∈ config.volumes.allowed?
       └── ALLOW or BLOCK
  │
  └─► privacy-agent.handle_privacy_index_volume:
       ├── ConsentManager.check_consent(volume_path, "index")  ──► fail-closed
       ├── Indexer.index_volume:
       │    for each file matching include/exclude:
       │      ├── Extractor.extract(path)        # local file content
       │      ├── PIIRedactor.scrub(content)     # NEW: mask PII before storing
       │      ├── Classifier.classify_path(path)
       │      └── Database.upsert_file(...)
       ├── AuditLogger.log_event(action="index", paths_accessed=[...], hash_chain=...)
       └── return IndexStats   # counts only, no paths
  │
  └─► PostToolUse hook: scan response for PII regex (safety net)
```

**What crosses the local→cloud boundary:** `IndexStats` only — counts, file-type distribution, last-indexed timestamp. No filenames, no content.

### 4.2 Search flow (read path, default)

```
User → Claude Code → /privacy-search skill → privacy_search(query, scope, ...)
  │
  └─► PreToolUse hook: consent ✓, scope ✓, rate limit ✓
  │
  └─► privacy-agent.handle_privacy_search:
       ├── ConsentManager.check_consent(scope, "search")
       ├── SearchEngine.search_fts(query, scope, ...)
       │    └── for each hit:
       │         ├── generate_snippet(content, query, max=200)
       │         └── PIIRedactor.scrub(snippet)            # NEW
       ├── filter_by_classification(results, allowed_levels)
       ├── return-schema whitelist: SearchResult dataclass # NEW
       │    fields = [volume_id, relative_path, title, snippet,
       │              score, classification, file_type, size_bytes,
       │              modified_at, indexed_at, pii_redactions_applied]
       ├── AuditLogger.log_event(action="search", query, paths_accessed, ...)
       └── return list[SearchResult]
  │
  └─► PostToolUse hook: PII safety-net scan, audit forward
```

**What crosses the boundary:** snippet (≤ 200 chars, redacted), volume id, relative path, classification, basic metadata. Absolute paths, mount points, raw content, PII — all stay local.

### 4.3 Excerpt flow (opt-in, requires `enable_excerpt_tool = true`)

```
User → asks Claude to read a specific file → privacy_read_excerpt(volume_id, relative_path, page|lines)
  │
  └─► PreToolUse hook:
       ├── enable_excerpt_tool == true?       fail-closed if not
       ├── classification ≤ confidential?     fail-closed if "restricted"
       └── per-file consent ✓?                else trigger interactive consent
  │
  └─► privacy-agent.handle_privacy_read_excerpt:
       ├── resolve volume_id + relative_path → absolute path (server-side)
       ├── Extractor.extract_excerpt(path, start, end | page)
       ├── PIIRedactor.scrub(excerpt)
       ├── truncate to max_chars (default 500, max 2000)
       ├── return-schema whitelist
       ├── AuditLogger.log_event(action="read", paths_accessed=[abs_path],
       │                         data_returned="excerpt", bytes_returned=...)
       └── return {volume_id, relative_path, excerpt, page, redactions_applied}
  │
  └─► PostToolUse hook: PII safety net, audit forward
```

### 4.4 Cross-orchestrator note

Codex CLI and Goose flows skip the Claude Code hooks. **All policy enforcement for those orchestrators is server-side.** This is acceptable because:

1. Server-side controls (consent, classification filter, return-schema whitelist, PII redactor, audit) are sufficient for data minimization.
2. Plan A's `Bash(cat:*)` deny rules are a Claude-Code-specific bypass concern; Codex/Goose have their own permission models that the integration must document.

---

## 5. Privacy and Security Considerations

### 5.1 Layered defense (combined)

| Layer | Plan source | Enforces |
|---|---|---|
| 1. settings.json deny rules | A | Claude Code can't bypass via Bash/Read |
| 2. PreToolUse hook | A | Consent, scope, rate limit, command-pattern checks |
| 3. MCP server consent gate | A + B | Server refuses without active consent record |
| 4. Classification filter | B | `restricted` content blocked unless explicitly elevated |
| 5. Return-schema whitelist | A | Only declared fields can appear in responses |
| 6. PII redactor | A | SSN, card, account, phone, email, IP masked in all text fields |
| 7. PostToolUse safety net | A | Second-pass PII scan on outbound payload |
| 8. Hash-chain audit log | B (mandatory) | Tamper-evident record of every access |

Each layer must fail closed on its own error. No layer trusts the layer above.

### 5.2 Compliance posture (Plan A explicit, applies to merged design)

- **HIPAA "minimum necessary":** server returns metadata + redacted snippets only by default; `read_excerpt` is opt-in.
- **PCI-DSS:** card-number regex applied in PIIRedactor before any data leaves the server; no cardholder data ever in transit to API.
- **GDPR/CCPA:** consent records have explicit expiry; revocation by consent_id; data minimization via classification filter.
- **Encryption at rest:** Phase 2 introduces SQLite encryption via Keychain-stored key (Plan B). Until then, document expectation that the host disk is encrypted (FileVault).

### 5.3 Plan B's threat model with Plan A additions

Plan B's threat table is the baseline. Add these from Plan A:

- *Threat:* Claude reads sensitive files via `Bash cat`/`head` → *Mitigation:* `settings.json` deny + PreToolUse Bash regex match (Claude Code only).
- *Threat:* Malicious MCP server replacement → *Mitigation:* server runs from pinned local path (not `npx` / `uvx`); plugin verifies file hash at startup.
- *Threat:* Consent bypass via crashed hook → *Mitigation:* hook-failure = fail-closed at the Claude Code layer; server-side consent gate is the second line.

---

## 6. Non-Functional Requirements (new or strengthened)

These NFRs surface from comparing the two plans and resolving conflicts:

1. **NFR-PRIV-1 — Default-deny on raw content.** No tool returns raw file content unless the operator has explicitly enabled `enable_excerpt_tool = true` and consent for the specific file is active. *(Strengthened from Plan B's per-file-consent default.)*
2. **NFR-PRIV-2 — No absolute paths in responses.** All MCP responses use `volume_id + relative_path`; absolute paths exist only in the audit log. *(From Plan A; overrides Plan B's `SearchResult.path = absolute`.)*
3. **NFR-PRIV-3 — PII redaction on every text field.** All text fields in any response (snippet, summary, excerpt, title if extracted) pass through the PII redactor before the return-schema whitelist serializes them.
4. **NFR-PRIV-4 — Return-schema whitelist enforced.** No tool may include a field that isn't declared in its dataclass schema. Responses are validated before serialization, not after.
5. **NFR-AUD-1 — Hash chain mandatory.** SHA-256 hash chain on the audit log is non-optional. `verify_chain_integrity()` runs on agent startup; broken chain triggers operator notification and tool block until acknowledged.
6. **NFR-AUD-2 — Audit on all paths.** Every MCP tool call AND every Claude Code hook decision logs an audit event. Hooks forward to `privacy-agent` audit log via local IPC, not directly to a separate file (one chain to verify).
7. **NFR-AUD-3 — Append-only and 0600.** Audit DB and log files chmod 0600; SQLite WAL prevents concurrent-write corruption.
8. **NFR-REL-1 — Fail closed.** Hook failure, server unreachable, consent expired, redactor exception, schema validation error → tool returns block, never partial data.
9. **NFR-REL-2 — Crash safety.** Indexer interruption is recoverable; `force_reindex = false` resumes by skipping already-indexed files.
10. **NFR-PERF-1 — Index responsiveness.** FTS5 search returns ≤ 500 ms for queries against indexes ≤ 1M files. Indexing throughput target: ≥ 100 files/sec on macOS for text/PDF.
11. **NFR-PERF-2 — Snippet bound.** 200-char default, hard cap 500. *(From Plan B; tighter than Plan A's open-ended summary.)*
12. **NFR-PORT-1 — macOS first, document Linux/Windows deltas.** `diskutil`-based volume detection, `/Volumes/*` paths, Keychain-backed encryption are macOS-specific and need explicit alternatives for cross-platform Phase 3.
13. **NFR-OBS-1 — Operator visibility.** `privacy_audit_log` and `privacy_list_volumes` are management surfaces; they must work even if the index is empty.
14. **NFR-COMPAT-1 — Multi-orchestrator parity.** Codex CLI and Goose receive the same server-side controls as Claude Code; only hook-layer controls are Claude-Code-only and must be documented as such.

---

## 7. Risks and Mitigations

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| R-1 | Excerpt tool enabled and used inadvertently leaks `restricted` content | Med | High | Default `enable_excerpt_tool = false`; classification gate blocks `restricted` excerpts; PII redactor; PostToolUse safety net (Claude Code) | Server + Hooks |
| R-2 | Index DB exfiltrated from disk contains plaintext content | Med | High | Phase 2 at-rest encryption (Keychain); document FileVault expectation for Phase 1; chmod 0600 on DB | Indexer / Phase 2 |
| R-3 | Plan A's deny rules don't apply to Codex / Goose, allowing direct `Read` tools to bypass MCP | High | High | Server-side controls are sole enforcement for non-Claude-Code orchestrators; document the asymmetry; recommend Codex/Goose users disable raw filesystem tools | Documentation + Codex/Goose configs |
| R-4 | PII regex false-negatives miss novel formats (foreign IDs, non-US accounts) | Med | High | Configurable `pii_patterns.yaml`; classification-based blocking is primary defense; redaction is secondary | PIIRedactor |
| R-5 | Hash chain breaks due to a write race or corrupt SQLite page | Low | Med | WAL mode + transactional inserts; `verify_chain_integrity()` on startup with operator notification | AuditLogger |
| R-6 | Consent fatigue → user grants blanket volume-level consent and forgets | Med | Med | 7-day default expiry; `privacy_audit_log` summary surfaced to user weekly via `/privacy-manage` | ConsentManager + Skill |
| R-7 | Two plans' field naming differs (`path` vs `volume_id+relative_path`); downstream skills written to one shape break with the other | Med | Low | Pick the merged dataclass before any skill is built; type-check resolver outputs against dataclass | Types module |
| R-8 | Gstack resolver build failures block skill discovery | Low | Med | Resolver unit tests; SKILL.md generation tested in CI before MCP integration test | gstack |
| R-9 | Claude Code permission deny list goes stale as user adds new sensitive directories | Med | Med | `/privacy-manage` skill emits suggested additions to `settings.json`; quarterly review | Skill |
| R-10 | Phase 2 ChromaDB embeddings index also contains content; new asset to protect | Low | High (when realized) | Plan from start: same encryption + access controls as FTS5 DB; co-locate in `~/.privacy-agent/` | Phase 2 |

---

## 8. Implementation Plan with Milestones

The phasing follows Plan B's bottom-up build order, adjusted to slot Plan A's defenses in early.

### Milestone M1 — Foundation (Week 1)

- M1.1 Scaffold `conductor/repos/privacy-agent/` per Plan B §[Files]
- M1.2 Implement `types.py` with **merged dataclasses** (resolves Conflict 2/3 — `volume_id + relative_path`, `pii_redactions_applied`)
- M1.3 Implement `config.py` (TOML loader, defaults, validation, `enable_excerpt_tool = false` default)
- M1.4 Implement `db.py` (SQLite FTS5 + metadata + consent + audit; WAL; 0600 perms)

**Exit criteria:** `pytest tests/test_config.py tests/test_db.py` green.

### Milestone M2 — Privacy primitives (Week 2)

- M2.1 Implement `PIIRedactor` (`lib/privacy_redaction.py` per Plan A) with `pii_patterns.yaml`
- M2.2 Implement `Classifier` (Plan B 4-level + path rules)
- M2.3 Implement `ConsentManager` (grant/check/revoke/expire)
- M2.4 Implement `AuditLogger` with **mandatory** SHA-256 hash chain + `verify_chain_integrity()`

**Exit criteria:** PII fixtures (SSN, CC, account, phone, email) all caught; consent expiry tested; tamper-detection test green.

### Milestone M3 — Extraction and search (Week 3)

- M3.1 `extractors/` registry + text/pdf/docx/json/csv per Plan B
- M3.2 PII redaction integrated into extractor outputs (extract → redact → store)
- M3.3 `Indexer` with crawl/index/incremental support
- M3.4 `SearchEngine` with FTS5 + snippet generation; snippet always passes through PIIRedactor

**Exit criteria:** index a fixture volume; search returns redacted snippets only; classification filter blocks `restricted`.

### Milestone M4 — MCP server + return-schema whitelist (Week 4)

- M4.1 Implement `server.py` with all 7 Plan B tools + Plan A's `get_file_summary`
- M4.2 **Return-schema whitelist** layer: every tool serializes via dataclass, no extra fields possible
- M4.3 Wire `privacy_read_excerpt` behind `enable_excerpt_tool` flag + classification cap
- M4.4 MCP integration tests (start server, exercise each tool, verify response shapes)

**Exit criteria:** `pytest tests/test_server.py` green; manual MCP inspector run shows 8 tools.

### Milestone M5 — Claude Code hooks + permissions (Week 5)

- M5.1 PreToolUse hook (Python): consent + scope + rate-limit + Bash regex against sensitive paths
- M5.2 PostToolUse hook: forward to `privacy-agent` audit log via stdio call; PII safety-net scan
- M5.3 SessionStart hook: consent verification, fail-closed on missing/expired
- M5.4 `settings.json` deny rules (Plan A list)
- M5.5 Plugin manifest (`plugin.json`) and launch scripts modeled on `launch-ebay.sh`

**Exit criteria:** Claude Code session with plugin enabled; bypass attempts (`Bash cat`, `Read /Volumes/...`) blocked at hook layer; happy-path search works.

### Milestone M6 — Multi-orchestrator + skills (Week 6)

- M6.1 Codex CLI MCP registration via `~/.codex/config.toml` and verification
- M6.2 Goose MCP registration via `goose configure` and verification
- M6.3 Gstack templates: `privacy-search/SKILL.md.tmpl`, `privacy-index/SKILL.md.tmpl`, `privacy-manage/SKILL.md.tmpl`
- M6.4 Resolver `privacy.ts` (tool reference table, consent flow doc, setup instructions)
- M6.5 Build SKILL.md files via existing resolver/preamble pipeline

**Exit criteria:** all three orchestrators can call `privacy_search`; skills appear in Claude Code; resolver emits valid SKILL.md.

### Milestone M7 — Documentation, audit review, compliance check (Week 7)

- M7.1 README with setup/consent/operations
- M7.2 Threat model document (formal write-up of §5)
- M7.3 Compliance mapping document (HIPAA / PCI-DSS / GDPR controls table)
- M7.4 E2E acceptance: index real external drive, search, audit-log review, attempt bypasses

**Exit criteria:** all NFRs from §6 verified; sign-off checklist complete.

### Phase 2 (post-M7, time-boxed)

- Local LLM summarization tool (Ollama-backed, Plan A) + ChromaDB hybrid search (Plan B)
- At-rest encryption via Keychain
- Snippet/summary quality regression tests

### Phase 3 (post-Phase 2)

- Multi-user RBAC, Docker image, SIEM export, network share scoping (Plan B)
- Centralized policy server for fleets

---

## 9. Open Questions

1. **Q-1 (excerpt policy):** What's the operator's intent for `privacy_read_excerpt` long-term — keep it opt-in forever, or design a UX that gradually unlocks per-file reads with strong consent UX? *Source of conflict between Plan A's "never raw" and Plan B's `read_excerpt` tool.* `[FILL: operator policy decision]`
2. **Q-2 (Codex/Goose enforcement parity):** Are we accepting that Codex CLI and Goose users get strictly server-side controls (no hook-equivalent), or do we want to build adapter-layer enforcement for those tools? `[FILL: scope decision for non-Claude-Code orchestrators]`
3. **Q-3 (gstack coupling):** Plan B places the project under `conductor/repos/privacy-agent/` and ties skills to the gstack resolver/preamble pipeline. Plan A places it under `~/code-projects/projects/active/privacy-orchestrator/`. Which directory is canonical, and is gstack a hard requirement for skill packaging or merely the preferred path? `[FILL: project home + gstack scope]`
4. **Q-4 (encryption phase):** Phase 2 introduces at-rest encryption. Is FileVault (full-disk) sufficient interim mitigation for Phase 1, or does the index DB itself need encryption from day 1? `[FILL: interim encryption requirement]`
5. **Q-5 (PII pattern catalog):** Plan A enumerates US-centric patterns (SSN, US accounts, etc.). What additional jurisdictions / formats are in scope (UK NI, EU IBAN, foreign passports)? `[FILL: PII catalog scope]`
6. **Q-6 (audit retention):** Plan B specifies 365 days. Are there legal-hold scenarios that require longer retention, and how does that interact with GDPR right-to-erasure for the data subject (the operator)? `[FILL: retention vs erasure policy]`
7. **Q-7 (rate limits):** Plan A mentions a 100/session rate limit. Is this per-tool, per-orchestrator, or aggregate? Need a concrete budget and overflow behavior. `[FILL: rate-limit envelope]`
8. **Q-8 (consent UX surface):** Plan B's `request_consent` uses interactive stdio prompts, which doesn't work cleanly inside an orchestrator session. Is there a separate consent UI (CLI tool, menu-bar app) that the operator interacts with out of band? `[FILL: consent UX channel]`
9. **Q-9 (cross-orchestrator audit attribution):** With three orchestrators sharing one audit log, attribution relies on the `orchestrator` field. Is there a stronger signal (process inspection, separate sessions per orchestrator) we should require? `[FILL: attribution strength requirement]`
10. **Q-10 (deny-list maintenance):** Plan A's `settings.json` deny entries are static. Should `/privacy-manage` actively suggest additions when it detects new sensitive paths in the indexed corpus? `[FILL: dynamic deny-list policy]`

---

## Appendix A — Concrete merged data shapes

```python
# types.py (merged)

@dataclass
class SearchResult:
    volume_id: str                # NFR-PRIV-2: no absolute paths
    relative_path: str
    title: str
    snippet: str                  # ≤200 chars, post-redaction
    score: float
    classification: str           # public | internal | confidential | restricted
    file_type: str
    size_bytes: int
    modified_at: str              # ISO 8601
    indexed_at: str
    pii_redactions_applied: int   # 0 if clean

@dataclass
class ExcerptResult:
    volume_id: str
    relative_path: str
    excerpt: str                  # ≤max_chars, post-redaction, default 500
    page: Optional[int]
    start_line: Optional[int]
    end_line: Optional[int]
    pii_redactions_applied: int
    classification: str

@dataclass
class AuditEntry:
    entry_id: str
    timestamp: str
    action: str                   # search | read | index | classify | consent_grant | consent_revoke | hook_block
    orchestrator: str             # claude_code | codex | goose | manual
    query: Optional[str]
    paths_accessed: list[str]     # absolute paths kept HERE only (not in MCP responses)
    data_returned: str            # snippet | excerpt | metadata_only | full_content | none
    bytes_returned: int
    consent_id: Optional[str]
    pii_redactions_applied: int
    hook_decision: Optional[str]  # allow | block | n/a
    hash_chain: str               # SHA-256, mandatory
```

## Appendix B — Source-attribution map

Every architectural element above traces to one or both source plans. Where neither plan named a control but it is implied by combining both (e.g., "return-schema whitelist must run *after* PII redactor"), the attribution is annotated as a synthesis rather than a new fact.

- Plan A elements: PII redactor, return-schema whitelist, hook trio, settings.json deny rules, "no raw content by default" posture, optional Ollama summarization (Phase 2), MCP server hash-pinning.
- Plan B elements: `privacy-agent` daemon, FTS5 index, 7 tools (incl. `privacy_read_excerpt`), 4-level classification, hash-chain audit, gstack skill packaging, multi-orchestrator support, ChromaDB Phase 2, RBAC/Docker/SIEM Phase 3.
- Synthesis (not introducing new domain facts, only ordering and gating combined): default-disabled excerpt tool, `volume_id + relative_path` instead of absolute path, mandatory (vs optional) hash chain, hook→`privacy-agent` audit forwarding (one chain to verify).

