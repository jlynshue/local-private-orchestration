# Compliance Mapping — privacy-agent Phase 1

This document maps Phase 1 controls to the relevant requirements in HIPAA,
PCI-DSS, and GDPR/CCPA. It is not a substitute for a formal audit; it is a
working artifact for an operator preparing for one.

## HIPAA (covered entity / business associate scenarios)

| Requirement | Control | Implementation |
|---|---|---|
| §164.312(a)(2)(i) Unique user identification | M2 per-orchestrator attribution | `audit.orchestrator` field; `PRIVACY_AGENT_ORCHESTRATOR` env binds the identifier at process start |
| §164.312(a)(2)(iv) Encryption | H5 SQLCipher (when installed) + FileVault dependency | `db.open_db(encryption_key=...)`; key from macOS Keychain |
| §164.312(b) Audit controls | NFR-AUD-1 hash-chain audit | `audit.AuditLogger` with mandatory SHA-256 chain; verifiable via `privacy-cli audit verify` |
| §164.312(c)(1) Integrity | NFR-AUD-1 + T-5 manifest | `verify_chain_integrity()` flags audit-log tampering; `privacy_agent.manifest.verify()` flags source-code tampering at SessionStart |
| §164.312(d) Person/entity authentication | Out-of-band consent grants | `privacy-cli consent grant` requires shell access; not granted via the orchestrator session |
| §164.502(b) "Minimum necessary" | NFR-PRIV-1 + NFR-PRIV-3 + classification filter | Snippet-only by default; PII redacted at index *and* search time; classification cap blocks `restricted` for Goose/Codex |
| §164.514(b)(2) De-identification | PIIRedactor | SSN, account numbers, phone, email, IP, large dollar amounts removed before any data leaves the daemon |
| §164.530(j) Documentation retention | `audit.retention_days = 365` | Default 1-year retention; configurable in `default.toml` |

**HIPAA gap (Phase 2 to address).** The "minimum necessary" determination
currently uses path-based classification + regex redaction. The H1 local-LLM
gate in Phase 2 strengthens this for cases where the regex catalog misses
contextual PHI (e.g., narrative descriptions of a condition).

## PCI-DSS v4.0

| Requirement | Control | Implementation |
|---|---|---|
| 3.5.1 Render PAN unreadable | PIIRedactor `CC` rule | Both 16-digit bare and grouped (4-4-4-4) credit card formats redacted before any cross-boundary egress |
| 3.5.2 Restrict access to cryptographic keys | H5 Keychain key source | `encryption.keychain_account = "privacy-agent-db"` — no plaintext keys on disk |
| 7.2 Need-to-know access | Consent gates per scope (`search`, `index`, `read`) | A search consent does not satisfy a read consent; tested |
| 8.6 Use of system/application accounts | `PRIVACY_AGENT_ORCHESTRATOR` attribution | Per-orchestrator profiles; audit logs the originating process tier |
| 10.1 Audit logs | NFR-AUD-1 | All tool invocations + hook decisions land in the same chained log |
| 10.2.1 All access events recorded | `agent.handle_*` always emits an audit row | Even blocked attempts (`hook_decision="block"`) get logged |
| 10.5.1 Limit access to audit trails | `db.sqlite` chmod 0600 | `db.open_db()` enforces; `~/.privacy-agent/` recommended chmod 700 in runbook |
| 10.5.5 File-integrity monitoring on logs | Hash chain + T-5 manifest | Audit tampering via `verify_chain_integrity()`; source/hook tampering via `manifest.verify()`; both checked at session start |

**PCI-DSS gap (Phase 2 to address).** Network segmentation (Req. 1) is
currently "stdio only / no network bind" — this is *strong* segmentation but
relies on no other process on the host having egress for the daemon's
output. H6 (egress firewall) in Phase 2 makes this enforceable at the OS
level.

## GDPR (data subject is the operator) and CCPA

| Article / Right | Control | Implementation |
|---|---|---|
| GDPR Art. 5(1)(b) Purpose limitation | Per-scope consent | Consent grants are scoped to `search` / `index` / `read`; one does not imply another |
| GDPR Art. 5(1)(c) Data minimization | NFR-PRIV-1 + snippet cap | Default snippet 200 chars; metadata-only by default; `enable_excerpt_tool = false` |
| GDPR Art. 5(1)(e) Storage limitation | M5 time-window leases + audit retention | Excerpt leases default 30 min; audit retention 365 days, configurable |
| GDPR Art. 7 Conditions for consent | Out-of-band CLI grants | Consent is freely given via deliberate action; revocable via `privacy-cli consent revoke` |
| GDPR Art. 7(3) Right to withdraw consent | `consent.revoke()` | Immediate effect — verified by `test_revoked_consent_immediately_takes_effect` |
| GDPR Art. 17 Right to erasure | Audit retention + index purge | `audit.retention_days` + `privacy_index_volume(force_reindex=True)` overwrites stale rows; full erasure = delete `~/.privacy-agent/db.sqlite` |
| GDPR Art. 25 Privacy by design | Phase 1 architecture | Every layer fails closed; defaults are restrictive; opt-in for higher access |
| GDPR Art. 30 Records of processing | NFR-AUD-1 | Hash-chain audit doubles as records of processing |
| GDPR Art. 32 Security of processing | Layered defense (8 controls) | Documented in `THREAT_MODEL.md` |
| CCPA §1798.100(b) Notice at collection | Operator-managed | `RUNBOOK.md` covers what's collected and where |
| CCPA §1798.105 Right to delete | Same as GDPR Art. 17 | DB deletion + canary rotation |
| CCPA §1798.110 Right to know | `privacy_audit_log` + `privacy-cli audit recent` | Operator can query their own access history end-to-end |

**GDPR gap (Phase 2 to address).** Art. 32 expects *appropriate* technical
measures. The Phase 2 additions (H1 LLM redaction, H3 OOB consent UI, H6
egress firewall) all materially strengthen this posture; Phase 1 meets the
bar but Phase 2 is where the controls become demonstrably appropriate
against contemporary threats.

## Cross-jurisdictional notes

- **EU IBAN, UK National Insurance, foreign passport patterns**: not in the
  default PII catalog. Open Question Q-5 (architecture analysis) tracks
  jurisdiction expansion. Operators in non-US jurisdictions should extend
  `config/default_pii_patterns.yaml`.
- **Data residency**: trivially satisfied — the daemon runs on the host,
  never makes network egress, and the index is encrypted at rest. Whatever
  jurisdiction the host is in, the data is in.

## Audit-readiness checklist

At any point, an operator can produce these artifacts for a compliance review:

- [ ] `privacy-cli audit verify` → audit-chain integrity attestation
- [ ] `privacy-cli manifest verify` → source-code integrity attestation (T-5)
- [ ] `privacy-cli audit recent` → recent access log with attribution
- [ ] `privacy-cli consent list` → active consents and their expiry
- [ ] `privacy-cli canary list` → currently-seeded tripwires
- [ ] `THREAT_MODEL.md` → layered defense status
- [ ] `COMPLIANCE.md` (this file) → requirements mapping
- [ ] `RUNBOOK.md` → operational procedures
