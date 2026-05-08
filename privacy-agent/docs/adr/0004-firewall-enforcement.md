# ADR-0004 — Firewall (H6) ships as optional, never mandatory

**Status:** Accepted
**Resolves:** Q-D (`integrated-phased-plan.md` §6)
**Date:** 2026-05-08

## Context

H6 adds network-layer egress control for the privacy-agent process. Two
delivery options:

1. **Mandatory** — setup.sh applies firewall rules; refuses to install
   without them.
2. **Optional** — privacy-agent ships rule templates (Little Snitch profile,
   pf config); operator opts in.

## Decision

**H6 is optional in all phases.** The privacy-agent ships:

- A Little Snitch `.lsrules` profile under `firewall/little-snitch.lsrules`
- A pf config snippet under `firewall/pf.conf.snippet`
- Documentation in `docs/firewall-setup.md` explaining when and why to
  install them

`setup.sh` does not apply firewall rules. Adoption is the operator's call.

## Reasoning

1. **Cost barrier.** Little Snitch is paid software (~$50). Mandating it
   would exclude users for whom the privacy-agent is a security upgrade.
2. **`pf` complexity.** Built into macOS but configuration is finicky and
   easy to misapply. A misconfigured pf rule can break legitimate
   connectivity in confusing ways. Forcing it on operators who don't
   understand it shifts a problem from "leak risk" to "broken laptop."
3. **Adequate primary defense.** The 8-layer in-process defense
   (settings.json deny + hooks + consent + classification + schema +
   redactor + safety net + audit) is *sufficient* for the threat model in
   `THREAT_MODEL.md`. Firewall is defense-in-depth, not a primary line.
4. **Honest framing.** Documenting "without H6, the daemon's other 7
   controls are your only line" gives operators a real choice with real
   tradeoffs. Mandating creates a false sense of security ("I have a
   firewall therefore I'm safe") that erodes attention to the primary
   defenses.

## Alternatives considered

- **Mandate Little Snitch.** Excludes price-sensitive users; doesn't help
  enterprise deployments (which have their own firewall).
- **Mandate pf.** Misconfiguration risk exceeds the marginal security gain.
  pf rules at the host level interact with VPN clients, container runtimes,
  and Docker Desktop in ways that are hard to predict.
- **Both (Little Snitch primary, pf fallback).** Same problems as above,
  doubled.
- **No firewall guidance at all.** Leaves a real defense-in-depth control
  on the table. We can ship it as opt-in with low cost.

## Consequences

**Enables:**
- Privacy-agent installs cleanly for any operator
- Documented "high-trust deployment" path (turn on H6) for compliance
  scenarios that need it
- Phase 3 enterprise work can require H6 via a separate `enterprise-setup.sh`
  without affecting single-user installs

**Costs:**
- Without H6, a future bug or supply-chain compromise in an extractor
  library (e.g., pymupdf SSRF) could exfiltrate via a direct HTTP request.
  Mitigation: `THREAT_MODEL.md` documents this as **R-3 partial** for
  non-mandatory H6.
- Two firewall configs to maintain (Little Snitch + pf). Mitigation: keep
  them simple; both deny outbound from the daemon process by default and
  allowlist nothing.

## Implementation pointer

To be built in Phase 2 M2.9. Repo additions:

```
firewall/
├── little-snitch.lsrules     # importable Little Snitch profile
├── pf.conf.snippet           # paste-into-pf.conf fragment
└── README.md                 # what to install, why, consequences
```

`docs/firewall-setup.md` covers the operator-facing how-to: when to install,
what each rule does, how to verify the privacy-agent process can no longer
make outbound TCP connections, and the rollback path.
