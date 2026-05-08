# Enhancement Proposals: Beyond the Current Plans

These proposals extend the privacy-preserving orchestration design beyond what Plan A and Plan B already cover. Each item lists Description, Rationale, Impact, Feasibility, and Risks/Trade-offs. Items are grouped by priority. The prioritization rubric is at the end.

---

## High Priority

### H1. Local-LLM redaction gate as a second-pass safety net

**Description.** Add a small local model (e.g., Llama 3.2 3B, Phi-3-mini, or a fine-tuned BERT-NER) that inspects every outbound MCP response *after* the regex PII redactor and *before* the return-schema whitelist serializes the payload. The model classifies whether the payload contains residual sensitive content the regex missed and either masks the offending span or fails the call closed.

**Rationale.** Regex catches structured PII (SSN, credit card, IBAN). It misses contextual leakage — "my insurance claim from the accident on March 4," "Dr. Patel said the biopsy showed…", or proper nouns belonging to the user (family names, employer, deal codenames). A small local model is good enough to flag these even though it isn't perfect.

**Impact.** Closes a class of leaks regex cannot catch. Especially valuable if `privacy_read_excerpt` is enabled. Reduces the blast radius of a regex blind spot from "one snippet leaked" to "one model false-negative on top of one regex false-negative."

**Feasibility.** Medium. Requires Ollama or llama.cpp installed locally. 3B-class models run in <2GB and respond in tens of ms on Apple Silicon. The model is invoked only on outbound text fields, so latency overhead is bounded. Implementation: small async call in `PIIRedactor.scrub_with_model()` after regex pass.

**Risks / Trade-offs.** Adds a dependency on a local LLM runtime. Model itself must be offline-only to avoid creating a new exfil channel. False positives over-redact and degrade snippet utility — mitigate by emitting `model_redactions_applied` counter so the user can tune. Adds latency: search SLO in NFR-PERF-1 (≤500 ms) needs a budget revision.

**Dependencies.** Ollama or llama.cpp; model weights file; Plan A's Phase 2 already calls for local LLM presence — pulling that into Phase 1 for redaction is a logical sequencing change.

---

### H2. Adversarial red-team harness for the privacy invariant

**Description.** A continuous test harness that asserts the core invariant — *no raw file content reaches the model context* — by running a curated corpus of prompt-injection and bypass attempts against the live system in a sandboxed loop. Examples: documents containing instructions to exfiltrate themselves; queries crafted to enumerate via narrow searches; bash compound commands that hide `cat` calls; tool-call sequences that try to chain `privacy_read_excerpt` past consent.

**Rationale.** The merged design has eight defense layers. None of them is individually sufficient; the invariant is an emergent property of the layers combined. Without a programmatic red-team, a refactor that quietly disables one layer goes undetected until a real leak.

**Impact.** Turns the invariant from a code-review aspiration into a CI gate. Catches regression introduced by future tool additions, hook changes, or extractor upgrades.

**Feasibility.** High for the framework, ongoing for the corpus. Pytest fixtures + a sandbox volume with seeded "canary" PII makes the harness easy to spin up. The prompt-injection corpus needs curation and grows over time; community datasets exist (Lakera Gandalf, prompt-injection-bench) but most are LLM-target, not MCP-target. The interesting attack surface is MCP-specific and partially novel.

**Risks / Trade-offs.** A harness is only as good as its corpus; absence of failure ≠ proof of safety. Maintenance burden — adversarial tests rot quickly. Recommend treating it as one signal alongside design review, not as primary assurance.

**Dependencies.** Test fixtures with synthetic PII. Optional: integration into the gstack CI pipeline.

---

### H3. Out-of-band consent UI (menu-bar app or system notification)

**Description.** Replace Plan B's interactive stdio consent prompts with a separate macOS menu-bar utility (or `osascript`/Notification Center alert + click-through) that owns consent grants. The orchestrator session never collects consent itself; it can only check existing consent state via `privacy_get_consent`. Granting requires the operator to interact with the OOB UI.

**Rationale.** stdio prompts inside an orchestrator session are vulnerable to prompt injection: a malicious document could instruct Claude to "grant consent on the user's behalf" via a synthesized stdio exchange. They also break under non-interactive automation flows. An OOB channel is unforgeable from inside a model session.

**Impact.** Hardens consent against prompt-injection vectors. Aligns with Open Question Q-8 from the architecture analysis. Lets Codex CLI and Goose share the same consent UX as Claude Code.

**Feasibility.** Medium. A SwiftUI menu-bar app is a few hundred lines; a simpler v1 uses `osascript display dialog` triggered via local IPC. The privacy-agent server posts a consent request to a local UNIX socket; the UI process responds with an attestation.

**Risks / Trade-offs.** Adds a second process to maintain. UX has to be discoverable — easy to miss a notification and assume the system is broken. Requires accessibility permissions (which themselves prompt). Cross-platform story is harder; Linux/Windows need different UI primitives, deferring portability.

**Dependencies.** Apple Developer signing (for Notification Center entitlements at minimum). IPC protocol between privacy-agent and the UI app.

---

### H4. Reversible pseudonymization with stable, per-session tokens

**Description.** Instead of replacing PII with `[REDACTED]`, replace it with stable, deterministic tokens scoped to a session — e.g., `Acct-A1`, `Acct-A2`, `Person-P3`. Build a server-side dictionary (`token → real value`) that never crosses the boundary. The orchestrator can reason about relationships ("compare Acct-A1's transactions to Acct-A2") without ever seeing real numbers. When the session ends, the dictionary is destroyed.

**Rationale.** Plain redaction destroys analytic usefulness — Claude can't tell whether `[ACCT]` and `[ACCT]` in two snippets are the same account. Stable tokens preserve relational structure, which is often the actual question the user wants answered.

**Impact.** Substantial uplift in usefulness for finance/legal/medical workflows where relationships across documents matter. Particularly valuable in Phase 2 with semantic search, where multiple results need to be reasoned about jointly.

**Feasibility.** High for the redaction logic; medium for the de-reference UX. The server already needs to read content for FTS5 indexing — assigning stable tokens at index time is straightforward. The harder part is letting the user *act on* a result (e.g., "open Acct-A1 in my bank app") which needs a local de-reference command.

**Risks / Trade-offs.** Tokens are still information. Five tokens reveal a count even if values are hidden. Token assignment must be session-scoped so different sessions don't see consistent labels (which would re-create a fingerprint). Increases server-side state.

**Dependencies.** Per-session dictionary store (in-memory, optionally persisted under encryption); a small CLI for de-reference.

---

### H5. Encrypted-at-rest index from day 1 (not Phase 2)

**Description.** Encrypt the SQLite FTS5 database from the first release using SQLCipher or page-level AES with a key from macOS Keychain. Plan B defers this to Phase 2.

**Rationale.** The index DB *contains the very content we are trying to protect* — extracted text from sensitive PDFs, financial CSVs, medical docs. An attacker who reads the unencrypted file recovers the corpus that the cloud API was specifically denied. FileVault helps when the disk is offline, but offers nothing against a malicious local process or backup leakage. Treating this as "Phase 2" leaves a foundational asset unprotected during the highest-risk window (early adoption, before the threat model is widely understood).

**Impact.** Closes one of the two highest-impact risks in the analysis (R-2). Reduces blame for index DB leaving the host via Time Machine, iCloud Desktop sync, or backup tools.

**Feasibility.** Medium. SQLCipher is a drop-in replacement for SQLite with a Python binding; encryption keys via Keychain are well-trodden on macOS. FTS5 still works inside SQLCipher. Costs a small write throughput penalty (5–15%) which is invisible at indexing speeds we care about.

**Risks / Trade-offs.** Key loss = index loss. Need a re-index path. SQLCipher adds a non-stdlib dependency and complicates packaging. Phase 3's Linux story needs an equivalent (LUKS at the FS level, or libsodium-based per-row).

**Dependencies.** SQLCipher, Keychain integration, tested key-rotation procedure.

---

### H6. Egress firewall integration (Little Snitch / pf rules)

**Description.** Bundle a recommended Little Snitch rule set or `pf` configuration that denies network egress from the privacy-agent process and any Claude Code / Codex / Goose subprocess that interacts with sensitive paths. Rule profiles ship with the plugin and can be applied via a setup step.

**Rationale.** Even with all the in-process defenses, a future bug or supply-chain compromise (in an extractor library, for instance) might exfiltrate via a direct HTTP request rather than via MCP. Network-layer enforcement is the last line of defense; orthogonal to all the controls inside the agent.

**Impact.** Defense in depth at a layer the orchestrator cannot influence. Particularly valuable for paranoid deployments and as a regulatory talking point ("network segmentation").

**Feasibility.** Medium. Little Snitch is a paid app most privacy-conscious users already run. `pf` is built into macOS but configuration is finicky. The plugin can ship a config and a setup script; full automation requires admin privileges.

**Risks / Trade-offs.** Misconfigured rules break legitimate connectivity. The orchestrator processes themselves *do* need internet (to talk to their respective LLM APIs) — rules need to be path/pattern aware, not blanket. May confuse users who don't run Little Snitch and don't understand pf.

**Dependencies.** Optional integration; not a hard requirement. Documentation matters more than code here.

---

### H7. Honeytoken / canary documents

**Description.** Plant decoy "sensitive" files in user directories with unique, syntactically PII-shaped markers (e.g., a fake SSN like `999-67-CANARY-001` that no real document would contain). The privacy-agent monitors its own outbound payloads and the audit log for those markers. If a marker ever appears in an outbound MCP response or — even better — surfaces in cloud telemetry the user can inspect (Anthropic conversation history export, OpenAI logs), the user has high-confidence evidence that the privacy boundary was breached.

**Rationale.** Detection is cheap; prevention is hard. Canary tokens give a *signal* that something leaked, which is the only way to discover a defense failure that none of the layered controls caught. Tripwires are a well-established pattern for sensitive systems.

**Impact.** Forensic value far exceeding the implementation cost. A single canary catch is enough to justify the entire investigation — "we found `CANARY-007` in our Anthropic API request logs" is unambiguous.

**Feasibility.** High. A setup script seeds canary files; the redactor monitors for canary patterns; the audit log flags canary appearances as `severity=critical`. ~150 lines of Python.

**Risks / Trade-offs.** Canaries pollute the corpus — search results for "ssn" might surface them, confusing the user. Mitigate with a `canary` classification tier that's hidden from default searches. Canary markers in the API request log only help if the operator actually checks; needs a recurring task.

**Dependencies.** None hard. Optional integration with the local SIEM dashboard (M3 below).

---

## Medium Priority

### M1. Single-use capability tokens for excerpt reads

**Description.** When `privacy_read_excerpt` is requested, the server issues a short-lived (e.g., 60-second) one-time-use token bound to `(orchestrator_session_id, volume_id, relative_path, byte_range)`. The orchestrator must present the token to actually receive the excerpt; the token is invalidated on use. A second read of the same file requires either fresh consent or a re-issued token.

**Rationale.** Plan B's per-file consent persists for the consent's lifetime, so once granted, an orchestrator can re-read the file repeatedly without further checks. Capability tokens narrow the window during which a leaked consent is exploitable, and create unforgeable per-read audit anchors.

**Impact.** Tighter access semantics for the highest-risk operation. Limits replay attacks and accidental re-reads.

**Feasibility.** Medium. Simple HMAC or random-nonce token store on the server. Requires a two-call protocol (request → present), which is ergonomic friction for the orchestrator.

**Risks / Trade-offs.** More round-trips, more state. Too aggressive with TTL = annoying UX. Worth doing only if `enable_excerpt_tool = true` is the common configuration.

**Dependencies.** Token store (in-memory is fine), audit-log integration.

---

### M2. Per-orchestrator policy profiles

**Description.** Allow different policy profiles for Claude Code vs Codex CLI vs Goose. For example: Goose (which executes autonomous multi-step plans) runs against a stricter profile — `enable_excerpt_tool` forced to `false`, classification cap of `internal`, no `privacy_read_excerpt`. Claude Code runs against the user-chosen default.

**Rationale.** Different orchestrators have different risk profiles. Goose's strength — long-running autonomy — is also its weakness for privacy: harder to monitor, more chained tool calls. Plan B supports all three orchestrators uniformly; that's a trust assumption, not a design choice.

**Impact.** Lets the operator say "I trust Claude Code with my taxes; I don't trust an autonomous agent with the same access." Aligns enforcement with operator trust model.

**Feasibility.** High. The `orchestrator` field is already in the audit dataclass. Server-side: load a profile keyed on the orchestrator id; merge with global defaults.

**Risks / Trade-offs.** Operator confusion if "the same query works in Claude but not in Codex." Document clearly. Profile divergence creates a maintenance surface — keep profiles small, additive only.

**Dependencies.** Config schema extension; orchestrator-id detection (process inspection or self-identifying handshake).

---

### M3. Local SIEM-style audit dashboard

**Description.** A small local web UI (served by privacy-agent on `localhost:<port>` or via a Mac app) that presents the audit log: search activity, consent grants/revocations, hook blocks, redactor catches, canary hits. Includes filters, weekly summaries, and anomaly highlights ("unusual burst of restricted queries on Sunday at 3 AM").

**Rationale.** Audit logs are write-once, read-rarely unless something looks wrong. Operators won't check JSONL by hand. A dashboard surfaces the *meaningful* signal — protections that fired, anomalies, consent expirations — and turns "we have a hash chain" from a checkbox into a workflow.

**Impact.** Makes the privacy controls visible and actionable. Supports operator decision-making (e.g., "I should add Medical to the deny list — there were 14 search hits last week").

**Feasibility.** Medium. SQLite already stores the audit chain. A FastAPI + lightweight frontend (HTMX or a single React page) is a weekend's work. Real value comes from query/aggregation logic, not UI polish.

**Risks / Trade-offs.** Adds another process. UI has to be local-only; do not let it serve over the network. Surface-level dashboards risk creating false confidence ("look, no alerts!"). Treat as one signal among many.

**Dependencies.** Audit-log query interface (already specified in Plan B); local web framework.

---

### M4. User-corpus NER for personal proper nouns

**Description.** Train a tiny NER model on the user's own indexed corpus (offline, batch, monthly) to identify proper nouns specific to them — family names, employer, project codenames, addresses, recurring contacts — then add those as redaction patterns. Rebuild as the corpus changes.

**Rationale.** Generic PII regex catches universally sensitive patterns. It cannot know that "Aunt Marge" or "Project Helios" is sensitive *to this user*. A user-corpus model catches identity-specific leakage that the standard catalog misses.

**Impact.** Materially better redaction for the long tail of personal data that rules can't anticipate.

**Feasibility.** Medium. Bootstrappable with spaCy + custom NER training; can also lean on the local LLM (H1) for zero-shot extraction. Periodic retraining is a cron job. Quality depends on corpus volume and diversity.

**Risks / Trade-offs.** Trained model now contains a fingerprint of the user; protect it like the index DB itself. Over-redaction risk — masking too many proper nouns kills snippet utility. False sense of completeness — the model is best-effort, not a guarantee.

**Dependencies.** spaCy or transformers; the local LLM (overlaps with H1).

---

### M5. Time-windowed consent ("session leases")

**Description.** Consent grants accept an explicit time-window argument: "search my Tax folder for the next 30 minutes." After the window, consent auto-revokes. Plan B has a default 7-day expiry; this is finer-grained, intentional-use scoping.

**Rationale.** A 7-day grant covers a single "I need to do my taxes today" task and then sits unused for 6 days as latent attack surface. Time-window leases match the actual unit of intent.

**Impact.** Reduces the temporal exposure of any given consent grant by an order of magnitude for typical workflows.

**Feasibility.** High. The `ConsentRecord` already has `expires_at`; just expose it as a tunable on `privacy_get_consent`.

**Risks / Trade-offs.** Workflow friction if windows are too short. Operators may default to longer windows out of habit. Pair with the OOB consent UI (H3) so the cost of re-granting is low.

**Dependencies.** None new.

---

### M6. Provenance tracking on returned data

**Description.** Stamp every payload that leaves the privacy-agent with a `provenance_id` linking it to (a) the audit entry that authorized it, (b) the source files it derived from, and (c) the orchestrator session it went to. Embed `provenance_id` in the response. If a leak is later suspected, the audit log lets the operator trace which session received which data from which file.

**Rationale.** When a leak is discovered (canary fires, customer reports), the question is always: which file, which query, which session. Provenance embedded at issuance makes that trace deterministic.

**Impact.** Forensic clarity. Critical for any incident-response capability and for compliance investigation.

**Feasibility.** High. UUID stamped at response build; retained in audit. Cost is bytes in the audit log.

**Risks / Trade-offs.** Provenance IDs are themselves data; ensure they don't encode sensitive info (use UUIDv4, not deterministic hashes of paths).

**Dependencies.** None new — audit log already exists.

---

## Exploratory / Lower Priority

### L1. iOS / iPadOS companion for OOB consent

**Description.** A small companion app that receives consent prompts via Continuity / Push and lets the operator approve/deny from another device. Particularly powerful when the Mac is being used by an autonomous agent and the user is not in front of it.

**Rationale.** Pushes consent off the working machine entirely — strongest possible isolation between "the LLM session asking" and "the human approving."

**Impact.** Highest-trust consent UX. Aligns with how banks handle MFA.

**Feasibility.** Low for v1. Apple Developer Program + APNs setup, Continuity APIs, iOS app distribution. Months of work for what H3 (menu-bar) approximates in a week.

**Risks / Trade-offs.** Heavy investment. Network round-trip via APNs is ironic in a privacy-first architecture (consent prompts touch Apple's infrastructure). May require certificate pinning to prevent middleboxes from sniffing prompt content.

**Dependencies.** Apple Developer account, APNs, iOS toolchain.

---

### L2. macOS XPC service isolation instead of stdio subprocess

**Description.** Run privacy-agent as an XPC service with a Sandbox profile that restricts entitlements (only specific filesystem reads, no network, no IPC except to declared peers). Replaces the stdio subprocess pattern.

**Rationale.** XPC + sandbox is a stronger OS-enforced trust boundary than process separation. The agent literally cannot access files outside its declared entitlements, even if compromised.

**Impact.** Cryptographically-grounded process isolation, not "we promise we don't `os.open()` outside the allowlist."

**Feasibility.** Low. Requires Swift/Objective-C wrapper around the Python core (or a full Swift rewrite); Apple Developer signing; entitlement declarations; loss of cross-platform Python ergonomics.

**Risks / Trade-offs.** Substantial complexity for a constraint that matters most in adversarial multi-tenant scenarios — overkill for single-user macOS. Becomes more compelling in a Phase 3 enterprise context.

**Dependencies.** Swift wrapper or rewrite; Apple Developer Program.

---

### L3. Cleanroom / synthetic-corpus mode for prompt prototyping

**Description.** Generate a synthetic corpus from index statistics (file counts, types, classification distribution, but no real content) so users can prototype prompts and skills against fake data, then graduate to real data once the prompt is validated. Adds a `mode = "synthetic"` flag.

**Rationale.** Most prompt iteration involves trial and error with the model — and every iteration on real data is a privacy risk. A synthetic mode lets the iteration happen on harmless content.

**Impact.** Reduces real-data exposure during the most error-prone phase of any new workflow.

**Feasibility.** Medium. Synthetic data generation is bounded; quality affects the realism of prompt testing. Could lean on the local LLM to generate plausible synthetic documents per classification tier.

**Risks / Trade-offs.** Synthetic and real may diverge enough that a prompt validated on synthetic still fails on real (false confidence). Generation itself takes time and compute.

**Dependencies.** Local LLM (overlaps with H1).

---

## Prioritization Rubric

Items were ranked on three axes: **impact on the privacy invariant**, **feasibility within Phase 1–2**, and **alignment with the merged design's existing primitives**.

| Tier | Rationale |
|---|---|
| **High** (H1–H7) | Each closes a concrete gap not covered by either source plan, with feasibility inside Phase 1–2 and clear hooks in the existing architecture. H5 is foundational (don't build on unencrypted index). H1, H2, H7 address the highest-impact risk: the invariant could fail silently. H3 closes Open Question Q-8. H4, H6 deliver outsized value for moderate cost. |
| **Medium** (M1–M6) | Operationally valuable but assume the High tier is in place. M3 and M6 turn the audit chain into something users will actually use. M2 acknowledges a real trust difference between orchestrators. M4 deals with the long tail of personal PII the catalog can't enumerate. |
| **Exploratory** (L1–L3) | Big ideas with disproportionate investment cost or that solve problems the merged design might never face. Worth keeping in the backlog for Phase 3 or for users with the highest threat models. |

### Conflict resolution among proposals

Two pairs of proposals overlap in non-trivial ways:

- **H1 (LLM redaction gate) and M4 (user-corpus NER).** Both use a local model to extend redaction beyond regex. *Resolution:* build H1 first as a generic gate, then M4 as a corpus-specific specialization that feeds into H1's pipeline. They share the local-LLM dependency and don't duplicate work if sequenced correctly.
- **H3 (menu-bar consent UI) and L1 (iOS companion).** Both deliver out-of-band consent. *Resolution:* H3 is the v1 — local, low-cost, addresses the prompt-injection vector. L1 is the v3 — remote, high-trust, addresses unattended-machine scenarios. They are not competitors; they target different threat assumptions.

### Notes on dependencies and resources

- H1, M4, L3 all benefit from a local LLM runtime (Ollama or llama.cpp) — sequencing one of them lets the others ride for free.
- H3 and L1 require an OOB UI surface — H3 is local IPC + AppKit/Swift menu-bar app; L1 needs Apple Developer + APNs.
- H5 introduces SQLCipher — minimal new ground but worth doing once and well.
- H7 needs no dependencies but its value is unlocked only if the user (or an automated job) periodically inspects cloud telemetry — pair with M3 dashboard's "canary watch" view.

### What is *not* proposed here, and why

- **Federated / multi-machine sync of the index.** Out of scope for the privacy-first single-user model; explicitly Phase 3 territory.
- **Differential-privacy noise on aggregate counts.** Considered; the threat (counts revealing existence of files) is real but small relative to the snippet-content surface. Not worth the user-perceivable accuracy loss in early phases.
- **Public hash-chain anchoring** (e.g., posting roots to a public timestamp service). Cryptographically interesting, operationally overkill for a single-user audit need.
- **Remote attestation / TEE-backed signing.** Stronger than H5's Keychain key but disproportionate for the assumed threat model.

These were considered and dropped to keep the proposal grounded in what materially changes the privacy posture rather than what is theoretically possible.
