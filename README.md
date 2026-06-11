# Local Private Orchestration

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-173%20passing-brightgreen)](privacy-agent/tests/)
[![MCP](https://img.shields.io/badge/MCP-1.0%2B-purple)](https://modelcontextprotocol.io)

> **Privacy-preserving AI agent that keeps your data local.** Detect and redact PII before AI agents touch your files.

---

## The Problem

Modern AI agents are powerful — until you need them to search your files. The moment you expose raw files to cloud LLMs, you leak:
- **Personally identifiable information** (SSNs, account numbers, phone numbers)
- **Secrets and credentials** (API keys, OAuth tokens, private keys)
- **Sensitive business data** (customer lists, financial records, medical notes)

Existing solutions are all-or-nothing: either lock the AI out entirely, or send everything to the cloud and hope the vendor's privacy policy holds.

**This agent does both.** It indexes your files locally, detects and redacts sensitive data, and exposes only safe excerpts to AI orchestrators via the [Model Context Protocol](https://modelcontextprotocol.io). Your data never leaves your machine.

---

## What It Does

**Privacy-Agent** is a local-first MCP server that sits between your orchestrator (Claude Code, Codex, Goose, etc.) and your files.

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Orchestrator (Claude Code, Codex, Goose, etc.)           │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       │ MCP stdio (local pipe only)
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ Privacy-Agent Daemon                                             │
├──────────────────────────────────────────────────────────────────┤
│ ✓ PII Detector        → regex patterns + canary honeytokens     │
│ ✓ Path Classifier     → 4-level access control (public–private) │
│ ✓ Redactor            → scrubs SSN, API keys, cards, emails     │
│ ✓ FTS5 Search Index   → ranked, snippet-only results            │
│ ✓ Consent Manager     → per-scope time-window leases            │
│ ✓ Audit Logger        → SHA-256 hash chain (tamper-proof)       │
│ ✓ SQLCipher DB        → at-rest encryption + WAL journaling     │
└──────────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  Your Local Filesystem (stays on disk)                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## Key Features

- **🔍 PII Detection & Redaction**  
  YAML-configurable regex patterns detect SSNs, credit cards, API keys, emails, phone numbers, and more. Redaction happens at index time and search time.

- **🎯 Path Classification**  
  Four-level system (public → sensitive → confidential → restricted) with per-orchestrator access controls. Goose sees internal docs; Claude Code sees non-restricted; sensitive files require explicit consent.

- **🔐 Local-Only Indexing**  
  Full-text search with BM25 ranking. No data ever leaves your machine. Snippets are redacted before the MCP server responds.

- **🛡️ Consent Management**  
  Per-scope (search/index/read), time-window leases. A grant for "search" doesn't grant "read". Out-of-band approval via CLI — the orchestrator can't escalate privileges.

- **📝 Tamper-Proof Audit Log**  
  Mandatory SHA-256 hash chain. Detect any alteration to audit trails or source code at session start.

- **🔒 At-Rest Encryption**  
  Optional SQLCipher with Keychain-backed key storage. Database enforces 0600 permissions and WAL journaling.

- **✅ Comprehensive Testing**  
  148+ unit tests, 25 adversarial red-team tests, perf benchmarks, and a threat model validated against HIPAA, PCI-DSS, and GDPR.

---

## Quick Start

### 1. Install

```bash
cd privacy-agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional (at-rest encryption):
```bash
pip install -e ".[encryption]"
```

### 2. Run Tests

```bash
pytest
```

Output:
```
collected 173 items

test_redactor.py ...................... [ 10%]
test_search.py ........................ [ 25%]
test_classifier.py .................... [ 35%]
test_consent.py ....................... [ 45%]
test_audit.py ......................... [ 60%]
redteam/test_invariants.py ............ [100%]

173 passed in 5.21s
```

### 3. Index a Volume

```bash
privacy-cli index ~/Documents --classify sensitive
```

This crawls `~/Documents`, detects PII (redacts it), and seeds the FTS5 index.

### 4. Search Locally

```bash
privacy-cli search "customer contract terms"
```

Returns ranked results with 200-char redacted snippets.

### 5. Audit Access

```bash
privacy-cli audit verify
```

Checks the SHA-256 hash chain. Exits 0 if clean, nonzero if logs were tampered.

### 6. Wire into Your Orchestrator

**Claude Code / Codex / Goose:**
```bash
privacy-agent  # Starts MCP stdio server
```

Then configure your orchestrator's MCP settings to stdio the privacy-agent process.

See `privacy-agent/docs/` for per-orchestrator setup guides.

---

## Architecture

**8 MCP Tools** exposed to orchestrators:

| Tool | Purpose |
|------|---------|
| `privacy_search` | Ranked full-text search with redacted snippets |
| `privacy_index_volume` | Crawl + redact + index a filesystem volume |
| `privacy_list_volumes` | List indexed volumes + metadata |
| `privacy_classify` | Get/set path classification level |
| `privacy_get_consent` | Inspect active consent grants |
| `privacy_audit_log` | Query the audit trail |
| `privacy_file_summary` | Sanitized natural-language summary of a file |
| `privacy_read_excerpt` | Redacted file excerpt (disabled by default — Phase 2) |

**Database:** SQLite (plain or SQLCipher) with FTS5 full-text index, WAL mode, mandatory 0600 permissions.

**Redaction:** Configurable regex patterns (YAML) + honeytoken canaries. Applied at two gates: indexing and MCP response serialization.

**Audit Trail:** Every tool call, hook decision, and policy violation lands in a tamper-proof log with SHA-256 chain linking.

---

## Testing & Validation

### Test Suite
- **137 unit + integration tests** — core logic, database, indexing, search, consent, audit
- **25 red-team adversarial tests** — invariant checking, response-schema validation, tampering detection
- **5 perf benchmarks** — baseline search/index times + comparison tooling
- **All tests green** — run locally before commit, gated in CI

### Threat Model
See `privacy-agent/THREAT_MODEL.md` for:
- Trust boundaries (local pipe vs. cloud API)
- Layered defense controls (settings.json → preToolUse hook → consent gate → redactor → audit)
- Attack scenarios + mitigation status

### Compliance Mapping
See `privacy-agent/COMPLIANCE.md` for:
- HIPAA requirements (audit controls, encryption, "minimum necessary" data minimization)
- PCI-DSS v4.0 (PAN redaction, key management, access logging)
- GDPR/CCPA (data retention, deletion, consent audit trail)

---

## Documentation

| Document | For | Link |
|----------|-----|------|
| **Threat Model** | Security engineers, compliance teams | [`privacy-agent/THREAT_MODEL.md`](privacy-agent/THREAT_MODEL.md) |
| **Compliance Mapping** | Auditors, Legal, Risk teams | [`privacy-agent/COMPLIANCE.md`](privacy-agent/COMPLIANCE.md) |
| **Runbook** | Operators, DevOps | [`privacy-agent/RUNBOOK.md`](privacy-agent/RUNBOOK.md) |
| **Acceptance Checklist** | Project stakeholders | [`privacy-agent/ACCEPTANCE.md`](privacy-agent/ACCEPTANCE.md) |
| **Architecture** | Product/Design | [`privacy-agent/design/`](privacy-agent/design/) |
| **Orchestrator Setup** | Developers | [`privacy-agent/docs/`](privacy-agent/docs/) |

---

## Use Cases

**For engineering leaders:**
- ✅ **Evaluate AI safety**: Does this approach to PII detection scale? What are the gaps?
- ✅ **Assess privacy controls**: Can your org adopt local-first AI tooling without regulatory risk?
- ✅ **Benchmark threat modeling**: How would *your* team approach the same problem?

**For practitioners:**
- ✅ Use `privacy-cli` for ad-hoc redaction verification
- ✅ Run the MCP server as a sidecar to Claude Code / Codex / Goose
- ✅ Extend PII patterns to match your domain-specific data (medical notes, SSN formats, etc.)

**For security/compliance teams:**
- ✅ Audit the hash chain and canary honeytokens
- ✅ Validate the HIPAA/PCI-DSS/GDPR mapping against your audit scope
- ✅ Use as a reference architecture for data-minimization policies

---

## Phases & Roadmap

**Phase 1 (Complete):** Local indexing, PII detection, consent gating, audit trails  
**Phase 1.5 (Complete):** Hardening, threat model validation, compliance mapping, 25 red-team tests  
**Phase 2 (Planned):** Local LLM gate (Claude Opus mini for contextual PHI detection), per-file encryption, deletion workflows  

See [`privacy-agent/design/integrated-phased-plan.md`](privacy-agent/design/integrated-phased-plan.md) for the full roadmap.

---

## Project Status

**All Phase 1 + 1.5 milestones shipped.**

- ✅ 173 tests passing (137 unit + integration, 25 red-team, 5 perf)
- ✅ Threat model validated
- ✅ HIPAA/PCI-DSS/GDPR mapping documented
- ✅ Runbook + first-run setup complete
- ✅ MCP server production-ready

---

## Author

**[Jonathan Lyn-Shue](https://jonathanlynshue.com)**  
*Fractional CIO/CTO | Data & AI Executive*  
Privacy-Agent was built to demonstrate privacy-aware AI orchestration for engineering teams evaluating local-first tooling.

---

## License

MIT — See [LICENSE](LICENSE) for details.

---

## Getting Help

- **Questions about PII detection patterns?** → See `privacy-agent/config/default_pii_patterns.yaml`
- **How do I wire this into my orchestrator?** → See `privacy-agent/docs/`
- **Is this compliant with our standard?** → Start with `privacy-agent/COMPLIANCE.md`
- **Red-team validation approach?** → See `privacy-agent/tests/redteam/`

---

## Contributing

This project is maintained as a demonstration of privacy-aware AI architecture. Feature requests, bug reports, and PRs welcome.

```bash
cd privacy-agent
pytest -v                    # All tests
pytest tests/redteam -v      # Red-team suite only
ruff check src/ tests/       # Lint
```
