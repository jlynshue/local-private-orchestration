# Integrated Phased Plan: Privacy-Preserving Orchestration (Crawl → Walk → Run)

This plan supersedes the milestone plan in §8 of `architecture-impact-analysis.md` and integrates the twelve enhancements from `enhancement-proposals.md`. It is the canonical roadmap.

References:
- Source plans: `title-privacy-preserving-orchestration-robust-moth.md`, `implementation_plan.md`
- Merged architecture: `architecture-impact-analysis.md`
- Enhancement catalog: `enhancement-proposals.md` (H1–H7, M1–M6, L1–L3)

---

## 0. Sequencing Principles

Three rules govern what slots into which phase:

1. **Foundational protections ship early, even if labeled "Phase 2" in the source plans.** The index DB *is* the sensitive corpus. Encryption (H5) and tripwires (H7) are not advanced features — they are the floor.
2. **The invariant gate ("no raw content out") graduates from manual review to automated gate at Phase 1 exit.** H2 (red-team harness) is non-negotiable infrastructure, not a polish item.
3. **The excerpt tool stays off until its compensating controls are present.** `privacy_read_excerpt` ships in Phase 1's code but is hard-defaulted off; it only flips on once Phase 2's local-LLM redactor (H1), capability tokens (M1), and OOB consent UI (H3) are in place.

These rules drive the placement decisions below.

---

## 1. Phase 1 — Crawl (Weeks 1–7)

**Theme:** Single-user, single-host, metadata-and-redacted-snippets only. Establish the daemon, the index, and the eight-layer defense. Excerpt tool present but disabled.

**Orchestrators in scope:** Claude Code (with full hook stack), Codex CLI (server-side controls only), Goose (server-side controls only).

### 1.1 What ships

From the merged architecture (architecture-impact-analysis.md §3):

- `privacy-agent` daemon with 8 tools (`privacy_search`, `privacy_index_volume`, `privacy_read_excerpt` *(default off)*, `privacy_list_volumes`, `privacy_get_consent`, `privacy_audit_log`, `privacy_classify`, `get_file_summary`)
- SQLite FTS5 index, 4-level classification, content extractors (text/PDF/DOCX/JSON/CSV)
- PII regex redactor + return-schema whitelist
- Three Claude Code hooks (PreToolUse, PostToolUse, SessionStart)
- `settings.json` deny rules
- Hash-chain audit log (mandatory)
- Three gstack skills (`/privacy-search`, `/privacy-index`, `/privacy-manage`)
- MCP registration for all three orchestrators

**Pulled forward from later phases (per Sequencing Principle 1):**

- **H5 — Encrypted-at-rest index from day 1** *(Plan B placed at Phase 2)*. SQLCipher + Keychain-stored key. The index is the sensitive corpus.
- **H7 — Honeytoken / canary documents** *(new)*. Cheap, foundational tripwire. Deploy a seeded canary corpus during initial setup.
- **H2 — Adversarial red-team harness** *(new)*. CI gate on the privacy invariant.
- **M5 — Time-windowed consent leases** *(new, trivial extension)*. Consent grants accept explicit window argument.
- **M6 — Provenance tracking** *(new, low cost)*. Every response stamped with `provenance_id`; audit log links payload → query → source files → session.
- **M2 — Per-orchestrator policy profiles** *(new)*. Goose defaults to stricter profile from the moment it's registered.

### 1.2 Sub-milestones

#### M1.1 — Foundation (Week 1)

- Scaffold `conductor/repos/privacy-agent/` (Plan B layout)
- `types.py` with merged dataclasses including `provenance_id`, `pii_redactions_applied`, time-window consent fields *(integrates M5, M6)*
- `config.py` (TOML loader, defaults, validation, `enable_excerpt_tool = false` hard default)
- `db.py` with **SQLCipher** instead of plain SQLite, key from Keychain, FTS5 + WAL + 0600 perms *(integrates H5)*

**Exit:** `pytest tests/test_db.py` green against an encrypted DB; key rotation procedure documented.

#### M1.2 — Privacy primitives (Week 2)

- `PIIRedactor` (regex engine, configurable `pii_patterns.yaml`)
- `Classifier` (4-level + path rules)
- `ConsentManager` with **time-window leases** *(M5)*: grant accepts `window_seconds`; default falls back to config 7-day; auto-revoke on expiry
- `AuditLogger` with mandatory SHA-256 hash chain, `verify_chain_integrity()` on startup, **provenance linkage** *(M6)*

**Exit:** PII fixture corpus caught; consent lease expires deterministically; tamper-detection test green; provenance round-trip works.

#### M1.3 — Extraction, search, indexing (Week 3)

- `extractors/` registry (text/PDF/DOCX/JSON/CSV), each post-extraction PII redaction before storage
- `Indexer` with crawl/index/incremental, exclude patterns, file-size cap
- `SearchEngine` with FTS5 + BM25 + snippet generation; snippet always passes through PIIRedactor *(NFR-PRIV-3)*

**Exit:** index a fixture volume of mixed files (including seeded canaries); search returns redacted snippets; classification filter blocks `restricted`.

#### M1.4 — Honeytokens (Week 3, parallel with M1.3)

- **H7 — Canary subsystem.** `honeytoken/seed.py` plants canary files (`canary_$ID.txt`, `canary_$ID.pdf`) with synthetic-but-recognizable PII patterns under user-selected directories
- Canary patterns added to PIIRedactor as a separate severity tier: detection here is `severity=critical` and triggers an audit entry tagged `canary_hit`
- Canaries live in their own `canary` classification tier — hidden from default search results so they don't pollute legitimate queries

**Exit:** simulating leakage (manually constructed payload containing a canary marker) triggers a critical audit entry within one PostToolUse cycle.

#### M1.5 — MCP server (Week 4)

- `server.py` with all 8 tools wired to the privacy primitives
- `privacy_read_excerpt` implemented but feature-flagged off via `[agent] enable_excerpt_tool = false`
- Return-schema whitelist enforced in serialization layer (no field outside the dataclass schema can ship)
- All responses include `provenance_id`

**Exit:** `pytest tests/test_server.py` green; MCP inspector shows 8 tools; `privacy_read_excerpt` returns "tool disabled" error in default config.

#### M1.6 — Per-orchestrator policy profiles (Week 4, parallel with M1.5)

- **M2 — Profile system.** Config schema extended with `[profiles.<orchestrator>]` blocks; defaults provided for `claude_code`, `codex`, `goose`
- Goose default profile: `enable_excerpt_tool = false`, `classification_cap = "internal"`, no `privacy_read_excerpt` even if globally enabled
- Orchestrator identification via initial handshake (request includes self-declared `orchestrator` field; spoofing is a known limitation, documented in threat model addendum)

**Exit:** same MCP request from each orchestrator returns appropriately-scoped results; profile mismatch logged.

#### M1.7 — Claude Code hook layer (Week 5)

- PreToolUse, PostToolUse, SessionStart hooks per the merged architecture
- `settings.json` deny rules (Plan A list)
- Plugin manifest, launch scripts (modeled on `launch-ebay.sh`)
- Hooks forward events to privacy-agent's audit log via local IPC, not separate files (one chain to verify)

**Exit:** Claude Code session with plugin enabled; bypass attempts (`Bash cat`, `Read /Volumes/...`) blocked; happy-path search works.

#### M1.8 — Multi-orchestrator + skills (Week 6)

- Codex CLI MCP registration via `~/.codex/config.toml`
- Goose registration via `goose configure`
- Gstack skills + resolver `privacy.ts`
- All orchestrators verified end-to-end against the canary corpus

**Exit:** all three orchestrators successfully invoke `privacy_search`; canary integrity preserved across orchestrators.

#### M1.9 — Adversarial red-team harness (Week 7)

- **H2 — Red-team CI gate.** Curated corpus of injection attempts:
  - Documents that contain instructions to exfiltrate themselves
  - Bash compound commands disguising `cat`/`strings`/`xxd`
  - Tool-call sequences that try to chain past consent or re-use stale tokens
  - Path-traversal attempts in `volume_id`/`relative_path` arguments
  - Prompt injections embedded in file content asking the model to ignore the schema
- Harness runs as `pytest tests/redteam/` and as a CI job
- Pass criterion: zero canary patterns ever appear in any captured outbound payload across the full corpus

**Exit:** harness green on full corpus; documented baseline (number of attacks attempted, all blocked); harness wired into CI as a required gate.

#### M1.10 — Documentation, compliance, acceptance (Week 7, parallel with M1.9)

- README + setup guide
- Threat model document (formalizes architecture-impact-analysis.md §5)
- Compliance mapping (HIPAA / PCI-DSS / GDPR controls table)
- Operator runbook (canary-watch checklist, audit verification cadence)
- E2E acceptance: index a real external drive, search, audit-log review, attempt bypasses against all three orchestrators

**Phase 1 exit:** all NFRs from architecture-impact-analysis.md §6 verified; H2 harness green; H5/H7 operating; M2/M5/M6 in place; sign-off checklist complete; `enable_excerpt_tool` remains `false`.

### 1.3 What does NOT ship in Phase 1

Deliberately deferred to Phase 2:

- `privacy_read_excerpt` enabled in default config (gated until H1+M1+H3 land)
- Local LLM redaction gate (H1)
- ChromaDB / semantic search (Plan B Phase 2)
- Out-of-band consent UI (H3)
- Reversible pseudonymization (H4)
- Single-use capability tokens (M1)
- User-corpus NER (M4)
- Audit dashboard (M3)
- Egress firewall integration (H6)

### 1.4 Phase 1 risk register (deltas from architecture analysis)

| Risk | Mitigation in this phase |
|---|---|
| Encrypted DB key loss = corpus loss | Documented re-index recovery procedure; key escrow guidance in operator runbook |
| Canary tier confuses operator searches | `canary` classification hidden from default queries; surfaced only in `/privacy-manage` audit views |
| Red-team corpus drifts / rots | M3 dashboard (Phase 2) tracks harness coverage; quarterly corpus refresh on backlog |
| Orchestrator self-declares wrong profile | Documented limitation; M2 spoofing is detectable post-hoc via audit-log behavior anomalies (Phase 2 M3 dashboard) |

---

## 2. Phase 2 — Walk (Weeks 8–14)

**Theme:** Bring local intelligence online. Local LLM redaction, semantic search, OOB consent, dashboard. Excerpt tool gated-on with full compensating controls. Network-layer defense added.

**Trigger to start Phase 2:** Phase 1 exit criteria met AND operator has been running Phase 1 for ≥30 days with zero unresolved canary hits, audit-chain breaks, or harness regressions.

### 2.1 What ships

#### M2.1 — Local LLM runtime + redaction gate (Weeks 8–9)

- **H1 — Local-LLM redaction gate.** Ollama or llama.cpp runtime; ship with a recommended small model (Llama 3.2 3B or Phi-3-mini)
- `PIIRedactor.scrub_with_model()` post-regex pass; flags or masks contextual leakage
- Latency budget: outbound response time +200 ms p95; if exceeded, fall back to regex-only with audit-log warning
- Model itself constrained to local-only via egress firewall rules (sets up H6)

**Exit:** redaction recall improves on a held-out test set vs regex-only baseline; latency SLO met.

#### M2.2 — User-corpus NER (Week 9, parallel)

- **M4 — Personal NER.** Monthly batch job trains/refines a spaCy NER model on the indexed corpus to identify proper nouns specific to the operator
- Output adds patterns to PIIRedactor (treated as one more layer; never replaces regex or H1)
- Model file protected with same key as the index DB

**Exit:** NER catches operator-specific proper nouns from a held-out subset; trained model passes the H2 harness without regression.

#### M2.3 — Semantic search (Weeks 9–10)

- ChromaDB vector store (Plan B Phase 2)
- Local embeddings via `sentence-transformers` (CPU-only sufficient on Apple Silicon)
- Hybrid search via reciprocal rank fusion (FTS5 + vector)
- Embeddings DB encrypted-at-rest using same Keychain key as FTS5 DB

**Exit:** hybrid search outperforms FTS5-only on a labeled query set; memory/disk footprint within budget.

#### M2.4 — Out-of-band consent UI (Weeks 10–11)

- **H3 — Menu-bar consent app.** Swift/SwiftUI menu-bar app; receives consent requests via local UNIX socket from privacy-agent
- All `privacy_get_consent(request=true)` flows redirect to the OOB UI; stdio prompts deprecated
- Grant attestation signed with a key in Keychain, verified by privacy-agent; fail-closed on signature mismatch
- Time-window picker in the UI surfaces M5's leases prominently (default 30 min for excerpts, 7 days for searches)

**Exit:** OOB UI receives, displays, and signs consent grants; stdio consent removed; H2 harness updated with attempts to forge stdio consent (must all fail).

#### M2.5 — Capability tokens for excerpt reads (Week 11, parallel)

- **M1 — Single-use capability tokens.** When `privacy_read_excerpt` is requested, server issues a 60-second token bound to `(orchestrator_session_id, volume_id, relative_path, byte_range)`
- Token presented on actual read; invalidated on use
- Re-read requires fresh consent OR a re-issued token
- Tokens logged with provenance linkage

**Exit:** excerpt reads require two-call protocol; replayed token rejected; token-replay attempts in H2 harness all fail.

#### M2.6 — Reversible pseudonymization (Week 12)

- **H4 — Stable session tokens.** Indexer assigns deterministic session-scoped tokens (`Acct-A1`, `Person-P3`) to detected entities at index time
- Per-session dictionary (`token → real value`) stored in encrypted memory; destroyed at session end
- Optional persistence under per-user encryption for cross-session continuity (off by default)
- `privacy-cli deref <token>` for local de-reference (e.g., "open Acct-A1 in my bank app")

**Exit:** snippets returned with stable tokens preserve relational structure; no real values cross the boundary; `deref` works for active session tokens.

#### M2.7 — Excerpt tool flip-on path (Week 12, parallel with M2.6)

- With H1, H3, M1 in place, `enable_excerpt_tool` becomes operator-flippable
- Default remains `false` — flipping is an explicit opt-in via `/privacy-manage configure`
- Flipping triggers an audit-log event; H2 harness re-runs with the tool enabled

**Exit:** excerpt tool can be safely enabled; harness still green; classification cap (`restricted` blocked) and per-file consent enforced end-to-end.

#### M2.8 — Local SIEM dashboard (Week 13)

- **M3 — Audit dashboard.** Local-only web UI on `127.0.0.1:<port>` (refuse non-localhost binds)
- Views: search activity, consent grants/expirations, hook blocks, redactor catches (regex / H1 model / NER / canary), provenance browser
- Weekly summary digest delivered via the menu-bar UI (H3)
- "Canary watch" view for H7 — surfaces any canary marker that appeared in audit logs

**Exit:** dashboard rendering audit data; weekly digest fires; canary-watch view exercised against simulated leak.

#### M2.9 — Egress firewall integration (Week 14)

- **H6 — Network-layer defense.** Ship recommended Little Snitch profile and `pf` config
- Setup script applies rules with operator confirmation; rules deny network egress from privacy-agent and from any process accessing `/Volumes/*` paths
- Operator's chosen orchestrator endpoints (Anthropic API, OpenAI API, Gemini, etc.) added to allowlist via `/privacy-manage allow-endpoint`
- Documentation covers manual installation for users without Little Snitch

**Exit:** privacy-agent process cannot make outbound TCP connections; orchestrator processes can reach declared API endpoints only; bypass attempts in H2 harness fail at network layer.

#### M2.10 — Phase 2 acceptance (Week 14)

- H2 harness re-run with all Phase 2 features enabled
- Performance regression suite (search latency, indexing throughput, redaction overhead)
- Compliance addendum: document Phase 2 control deltas (H1, H3, M1, M3, H6) against HIPAA/PCI-DSS/GDPR mapping

**Phase 2 exit:** Phase 1 exit criteria still hold; H1+M4 redaction layered atop regex+canary; H3 OOB consent operating; M1 capability tokens enforced; H4 pseudonymization usable; M3 dashboard operating; H6 firewall in place; excerpt tool safely flippable.

### 2.2 What does NOT ship in Phase 2

- Multi-user / RBAC (Phase 3)
- Docker deployment (Phase 3)
- SIEM export to external systems (Phase 3)
- iOS companion (Phase 3)
- XPC sandbox isolation (Phase 3)
- Cleanroom synthetic mode (Phase 3)
- Cross-platform (Linux/Windows) parity (Phase 3+)

---

## 3. Phase 3 — Run (Months 4+)

**Theme:** Multi-user, multi-host, enterprise. Stronger isolation primitives. Operator-facing prototyping aids.

**Trigger to start Phase 3:** Phase 2 has run for ≥60 days with no canary hits and a clean H2 harness across all features. A concrete enterprise or team use case exists (Phase 3 should not be built speculatively).

### 3.1 What ships

#### M3.1 — Multi-user RBAC (Plan B Phase 3)

- Per-user consent profiles, audit attribution, classification visibility scopes
- Centralized policy server (optional) for fleet management

#### M3.2 — Docker / containerized deployment (Plan B Phase 3)

- Sandboxed daemon image with explicit volume mounts
- Reproducible builds; image signing (Sigstore/cosign)

#### M3.3 — SIEM audit export (Plan B Phase 3)

- JSONL/CEF export to Splunk, Elastic, Datadog, etc.
- Hash-chain integrity preserved across export boundary; downstream verification tooling

#### M3.4 — Network share scoping (Plan B Phase 3)

- NFS / SMB volume support with appropriate consent semantics
- Path normalization for cross-mount provenance

#### M3.5 — XPC + Sandbox isolation *(L2)*

- Swift wrapper around the Python core; XPC service with declared filesystem entitlements
- Sandbox profile prevents agent from accessing files outside declared allowlist even if compromised
- Worth the engineering cost only at Phase 3 trust boundaries (multi-tenant or fleet)

#### M3.6 — iOS / iPadOS companion *(L1)*

- Companion app for OOB consent on a separate device
- Continuity / APNs delivery; consent grants signed and verified end-to-end
- Pair with H3's menu-bar UI as the Mac-local fallback

#### M3.7 — Cleanroom synthetic mode *(L3)*

- Generate synthetic corpus from index statistics for prompt prototyping
- `mode=synthetic` switch on every search tool; results clearly labeled
- Useful for new-skill development and operator onboarding without risking real data exposure

#### M3.8 — Cross-platform parity

- Linux: equivalent to Keychain (libsecret), `pf` (nftables), volume detection (udev)
- Windows: DPAPI, Windows Filtering Platform, drive enumeration
- Cleanly factored OS abstraction layer in privacy-agent

**Phase 3 exit:** depends on the specific enterprise use case driving the phase; success criteria defined per deployment.

---

## 4. Cross-Cutting Concerns

These run continuously across all phases and have no single owner phase.

### 4.1 H2 red-team corpus maintenance

- New attack vector discovered in production → corpus update within one sprint
- New tool added to MCP surface → corresponding harness coverage required before merge
- Quarterly corpus refresh; published changelog

### 4.2 Canary hygiene (H7)

- Operator-led: weekly check that no canary ever appeared in audit logs
- M3 dashboard's canary-watch view automates this once Phase 2 is live
- Canary corpus rotated every 6 months (rotate IDs to prevent attacker pre-knowledge)

### 4.3 Threat-model evolution

- Threat model document is a living artifact; changes per phase
- Phase entry/exit reviews include a threat-model diff
- New enhancement → threat-model implications documented before code

### 4.4 Compliance posture

- HIPAA / PCI-DSS / GDPR mapping refreshed per phase
- Phase 1: standard mapping; Phase 2: extended with H1/H3/M1/H6 controls; Phase 3: enterprise additions (multi-user, SIEM)

### 4.5 Operator runbook

- Must stay current with phase capabilities
- Includes: canary-watch cadence, audit-chain verification, consent hygiene, recovery procedures (key loss, DB corruption, harness regression)

### 4.6 Performance budgets

- **Search latency p95**: ≤500 ms (Phase 1), ≤700 ms (Phase 2 with hybrid search + H1 redaction), tracked per phase
- **Index throughput**: ≥100 files/sec text/PDF baseline
- **Redaction overhead**: regex < 5 ms/snippet; H1 model < 200 ms p95; user-corpus NER batch only
- Performance regression suite runs at each phase exit

---

## 5. Phase Mapping of Enhancements

A reverse-index summary — which enhancement lands in which phase, and why.

| Enhancement | Phase | Rationale |
|---|---|---|
| **H1** Local-LLM redaction gate | 2 | Requires local LLM runtime; pairs with semantic search for which the runtime is also installed. |
| **H2** Red-team harness | 1 | Foundational; the invariant must be programmatically verifiable from day one. |
| **H3** OOB consent UI | 2 | Replaces stdio prompts; must be in place before excerpt tool is flipped on. |
| **H4** Reversible pseudonymization | 2 | Depends on richer redaction (H1, M4) for entity detection; needs in-process token store. |
| **H5** Encrypted-at-rest index | 1 | Foundational; index *is* the corpus. Pulled from Plan B's Phase 2. |
| **H6** Egress firewall | 2 | Pairs with local LLM runtime arrival (more outbound surface to constrain); rules apply to the privacy-agent's network access. |
| **H7** Honeytokens / canaries | 1 | Cheap, foundational tripwire. Operates alongside the index from initial setup. |
| **M1** Capability tokens | 2 | Only relevant when excerpt tool is enabled, which is a Phase 2 milestone. |
| **M2** Per-orchestrator profiles | 1 | Required as soon as Codex/Goose register; can't ship multi-orchestrator without it. |
| **M3** Audit dashboard | 2 | Audit log accumulates meaningful data after Phase 1 ends; dashboard becomes valuable then. |
| **M4** User-corpus NER | 2 | Needs accumulated indexed corpus and local LLM (overlaps with H1 dependency). |
| **M5** Time-windowed consent | 1 | Trivial extension of consent already specified; ship with the consent manager. |
| **M6** Provenance tracking | 1 | Low-cost, foundational. Forensic capability matters from day one. |
| **L1** iOS companion | 3 | High-effort OOB UX; Phase 2's menu-bar UI is the v1 equivalent. |
| **L2** XPC sandbox isolation | 3 | Major rewrite; payoff only at multi-tenant/enterprise scale. |
| **L3** Cleanroom synthetic mode | 3 | Onboarding/training tool; needs accumulated index for synthetic generation. |

---

## 6. Open Questions That Must Resolve Before Phase 2

Resolution required at Phase 1 exit; carrying these into Phase 2 unresolved is a risk.

1. **Q-A (excerpt policy ceiling):** When `enable_excerpt_tool` flips to `true`, what is the absolute maximum classification level allowed (`confidential`? never `restricted`?). `[FILL: operator policy]`
2. **Q-B (local LLM choice):** Llama 3.2 3B vs Phi-3-mini vs a custom-fine-tuned BERT-NER. Tradeoff: redaction recall vs latency vs disk footprint. Decide before M2.1. `[FILL: model selection]`
3. **Q-C (consent UI delivery):** Menu-bar Swift app vs `osascript` v1 vs Electron. Decide based on operator's tolerance for native install vs cross-platform debt. `[FILL: H3 implementation choice]`
4. **Q-D (firewall coupling):** Mandatory Little Snitch profile vs optional pf-only documentation. Affects packaging and onboarding friction. `[FILL: H6 enforcement strength]`
5. **Q-E (canary rotation):** How often, and who initiates. Operator-driven vs scheduled job. `[FILL: canary lifecycle policy]`
6. **Q-F (orchestrator self-identification trust):** M2 currently trusts the orchestrator's self-declared identity. Worth investing in process inspection / handshake signing? `[FILL: attribution strength target]`
7. **Q-G (Phase 2 entry trigger):** "30 days clean" is a heuristic. Is there a more rigorous criterion (e.g., N searches executed, M canaries dormant, harness coverage threshold)? `[FILL: phase-gate criteria]`

Open Questions Q-1 through Q-10 from `architecture-impact-analysis.md` §9 also remain open and should be tracked in the same register.

---

## 7. Phase Effort Summary

Order-of-magnitude estimates only; actual effort depends on operator availability for testing and per-week hours.

| Phase | Calendar | Engineering effort | Net new artifacts |
|---|---|---|---|
| Phase 1 (Crawl) | ~7 weeks | ~6 person-weeks | privacy-agent daemon (8 tools), 3 hooks, 3 skills, encrypted index, canary subsystem, red-team harness |
| Phase 2 (Walk) | ~7 weeks | ~7 person-weeks | local LLM redactor, semantic search, OOB consent UI, capability tokens, pseudonymization, audit dashboard, egress firewall integration |
| Phase 3 (Run) | months, demand-driven | scoped per use case | RBAC, Docker, SIEM export, XPC isolation, iOS companion, synthetic mode, cross-platform parity |

---

## 8. Decision Points Requiring Operator Sign-Off

Each phase ends with an explicit go/no-go review. These are the questions to answer at each gate:

**Phase 1 → Phase 2:**
- All NFRs met? H2 harness green? H5 encryption key escrowed? Canary corpus seeded? Operator runbook published?
- 30-day soak completed without unresolved canary hits or chain breaks?
- Operator wants the local LLM dependency that Phase 2 introduces?

**Phase 2 → Phase 3:**
- Concrete enterprise or team use case identified? (Don't build Phase 3 speculatively.)
- 60-day soak with all Phase 2 features active and clean?
- Resourcing for sustained Phase 3 maintenance (RBAC, SIEM, cross-platform)?

**Excerpt tool flip-on (mid-Phase 2):**
- H1, H3, M1 all live? Per-file consent UX validated? Classification cap policy resolved (Q-A)?
- H2 harness updated to cover excerpt-enabled state and green?

These reviews are not ceremony — each is a real decision with a defensible rationale recorded in the audit log.
