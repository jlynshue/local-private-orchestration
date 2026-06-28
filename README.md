# Local Private Orchestration

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![CI](https://github.com/jlynshue/local-private-orchestration/actions/workflows/ci.yml/badge.svg)](https://github.com/jlynshue/local-private-orchestration/actions/workflows/ci.yml)
[![MCP](https://img.shields.io/badge/MCP-1.0%2B-purple)](https://modelcontextprotocol.io)

> **Privacy-preserving AI agent that keeps your data local.** Detect and redact PII before AI agents touch your files.

> This repository ships the **Privacy-Agent** module (all code lives under [`privacy-agent/`](privacy-agent/)).

---

## Why This Exists

Modern AI coding agents — Claude Code, Codex, Cursor, Goose — operate by indexing your filesystem and feeding file contents to cloud LLMs. This is powerful, but there is no privacy boundary between the agent's tool calls and your sensitive data. A single `cat ~/.ssh/id_rsa`, an accidental `grep` that matches a tax return, or a search snippet containing an SSN is irreversible the moment it hits a remote API. The data is logged, cached, and potentially trainable. You cannot un-send it.

Existing mitigations are binary: either you exclude entire directories from the agent (crippling its utility) or you trust the vendor's data retention policy and hope nothing sensitive leaks through tool output. Neither option is acceptable when your filesystem contains client contracts, medical records, credentials, or financial documents alongside the code you actually want the AI to help with.

This project implements 8 independent defense layers — from `settings.json` deny rules and pre-tool-use hooks down to PII regex redaction, consent gates, and a tamper-proof audit chain — that sit between the orchestrator and your files. Each layer fails closed independently. The result: AI agents can search and summarize your local documents while PII, secrets, and sensitive content are scrubbed before any byte crosses the local-to-cloud boundary. No utility sacrifice, no trust assumptions.

---

## Example Usage

```bash
$ privacy-cli index ~/Documents
Indexed 2,847 files (1.2 GB) in 4.3s
PII detected: 12 files flagged (SSN: 3, email: 7, phone: 2)

$ privacy-cli search "tax returns 2024"
3 results (redacted snippets):
  1. ~/Documents/taxes/2024-return.pdf — "Federal return for [REDACTED_SSN] filed..."
  2. ~/Documents/taxes/w2-2024.pdf — "Employer: Acme Corp, wages: $[REDACTED]..."
  3. ~/Documents/taxes/1099-2024.pdf — "Non-employee compensation from [REDACTED]..."

$ privacy-cli audit verify
✓ Chain integrity: 847 entries, no gaps
✓ Last verification: 2026-06-11T14:22:00Z
```

### MCP Integration

Add to your orchestrator's MCP config (Claude Code, Codex, Goose, etc.):

```json
{
  "mcpServers": {
    "privacy-agent": {
      "command": "python",
      "args": ["-m", "privacy_agent.server"],
      "env": {
        "PRIVACY_AGENT_DIR": "~/Documents",
        "PRIVACY_AGENT_CONFIG": "~/.privacy-agent/config.toml",
        "PRIVACY_AGENT_DB": "~/.privacy-agent/privacy.db"
      }
    }
  }
}
```

The orchestrator can then call tools like `privacy_search`, `privacy_file_summary`, `privacy_classify` — all responses pass through the 8-layer defense pipeline before reaching the AI model.

### Consent Workflow (Out-of-Band)

Consent grants are managed via the CLI, **never** through the orchestrator session. This prevents prompt-injection attacks from escalating privileges:

```bash
# Grant search access to ~/Documents for 1 hour
$ privacy-cli consent grant --path ~/Documents --scope search --granularity volume --window-seconds 3600
{"granted": "c-7f3a...", "expires_at": "2026-06-11T15:22:00Z"}

# The orchestrator requests consent — gets instructions, not a prompt
$ # (inside MCP session) privacy_get_consent(path="~/Documents", scope="read", request=True)
# → {"status": "denied", "instructions": "Run: privacy-cli consent grant --path ..."}

# Revoke when done
$ privacy-cli consent revoke --id c-7f3a...
{"revoked": true}
```

### Canary Honeytokens

Detect if an orchestrator bypasses the privacy boundary:

```bash
# Plant canary files that look like real sensitive data
$ privacy-cli canary seed --dir ~/.privacy-agent/canaries --count 5
{"seeded": [{"id": "canary-a1b2", "path": "/Users/you/.privacy-agent/canaries/tax_2024.txt"}, ...]}

# If any tool output contains canary markers, the PostToolUse hook fires a
# critical audit entry — proof that the defense perimeter was breached.
```

### Audit Verification

```bash
# Verify the tamper-proof hash chain
$ privacy-cli audit verify
{"valid": true, "broken_entry_ids": []}

# View recent activity
$ privacy-cli audit recent
[
  {"ts": "2026-06-11T14:20:01Z", "action": "search", "orchestrator": "claude-code",
   "severity": "info", "redactions": 3, "bytes": 1847},
  ...
]
```

### Source Integrity Check

```bash
# Generate a SHA-256 manifest of all agent source files
$ privacy-cli manifest install
{"installed": "/Users/you/.privacy-agent/manifest.sha256", "file_count": 42}

# Verify no source files have been tampered with
$ privacy-cli manifest verify --strict
{"valid": true, "mismatches": [], "manifest": "/Users/you/.privacy-agent/manifest.sha256"}
```

---

## Security Model

Every tool call passes through 8 independent, fail-closed layers:

1. **Settings denial** — blocked paths/patterns in `settings.json` never reach the agent
2. **PreToolUse hook** — regex inspection of tool parameters catches compound shell bypasses (e.g., `cat /Volumes/Backup/Tax/...` piped through Bash)
3. **Consent gate** — per-scope, time-windowed leases managed out-of-band via CLI; the orchestrator cannot self-grant
4. **Classification filter** — 4-level path classification (public/sensitive/confidential/restricted) with per-orchestrator access ceilings
5. **Return-schema whitelist** — only approved fields (snippets, metadata, counts) appear in MCP responses; raw file content is never exposed
6. **PII redactor** — YAML-configurable regex + heuristic detection replaces SSNs, credit cards, API keys, emails, and phone numbers with `[REDACTED_*]` tokens
7. **PostToolUse safety net** — scans tool output for canary markers and residual PII; fires critical audit entries on breach detection
8. **Audit chain** — SHA-256 hash-linked, append-only log records every tool call, consent decision, and policy violation with tamper-evident integrity

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
  152 unit + integration tests, 25 adversarial red-team tests, 5 perf benchmarks, and a threat model validated against HIPAA, PCI-DSS, and GDPR.

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

Output (bare `pytest` runs the full suite — unit + integration + red-team + perf):
```
tests/test_redactor.py ..........................          (26)
tests/test_search.py ..........                            (10)
tests/test_classifier.py .......                            (7)
tests/test_consent.py ............                         (12)
tests/test_audit.py .........                               (9)
... (14 unit/integration modules total)
tests/redteam/test_invariants.py .........................  (25)
tests/perf/test_baseline.py .....                            (5)

182 passed, 1 skipped in 8.10s
```

(The 1 skip is `test_sqlcipher_round_trip`, which requires the optional `sqlcipher3-binary` extra.)

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
- **152 unit + integration tests** — core logic, database, indexing, search, consent, audit
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

- ✅ 182 tests passing (152 unit + integration, 25 red-team, 5 perf)
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
