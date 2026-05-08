# ADR-0001 — Cap excerpt at `confidential`; never excerpt `restricted`

**Status:** Accepted
**Resolves:** Q-A (`integrated-phased-plan.md` §6)
**Date:** 2026-05-08

## Context

When `enable_excerpt_tool` flips on in Phase 2, the `privacy_read_excerpt`
tool will return raw file content (≤ 2000 chars, post-redaction, with
per-file consent). The four-level classification ladder is:

```
public < internal < confidential < restricted
```

The question: at what level does excerpt become structurally impossible?

## Decision

**Excerpt is capped at `confidential`. The `privacy_read_excerpt` tool
returns `ClassificationBlocked` for any file classified `restricted`,
regardless of consent state, profile cap, or operator overrides.**

The cap is enforced server-side as a hard architectural barrier — there is
no config flag to lift it.

## Reasoning

1. **Categorical risk.** `restricted` is reserved in our default
   classification rules for medical (`*/medical/*`) and would extend to
   attorney-client privileged content. Leakage is not "minor incident" —
   it's HIPAA exposure or legal-privilege breach with categorical legal
   consequences.
2. **The ladder is the answer.** A four-level classification system exists
   precisely so that the most sensitive tier gets a *structural* barrier,
   not a procedural one. Reducing every level to "consent + redaction" is
   reducing the ladder to a single tier.
3. **Workaround exists.** An operator who genuinely needs to read a
   `restricted` file can do so through native tools (Preview, vim, Pages)
   outside the orchestration loop. That's the right tool for the job —
   the agent isn't.
4. **Defense in depth has limits.** The 8-layer defense reduces residual
   risk; it doesn't eliminate it. The right way to get residual risk to
   zero on the most sensitive content is to keep it out of the agent.

## Alternatives considered

- **Cap at `internal`.** Too restrictive — confidential (tax docs, financial)
  is the most common use case; locking it out kills utility.
- **No cap; rely on consent.** Rejected per Reasoning #2. Consent is a
  procedural gate that erodes under fatigue; the structural cap doesn't.
- **Cap with operator override** (e.g., a `--unsafe-excerpt-restricted`
  flag). Rejected because the override would normalize over time. The point
  of an architectural barrier is that it's not a knob.

## Consequences

**Enables:**
- Clear messaging: "the agent does not read medical/privileged content;
  use a native tool"
- Simpler threat model — `restricted` files have a guaranteed path-of-no-
  return through this agent
- Reduces blast radius of any future redactor regression

**Costs:**
- Operators occasionally want to query medical content through Claude.
  Documented workaround: open in Preview/vim and copy-paste the relevant
  portion (which is itself an audit-able operator action, not an
  agent action).
- Path-based classification mistakes that mark non-medical content as
  `restricted` will block excerpt access until reclassified. The
  `privacy_classify` tool exists for this; it's a known operator workflow.

## Implementation pointer

Enforced in `agent.handle_read_excerpt` via `classification_rank()` check
against `ORDERED_LEVELS.index("confidential")`. Test:
`tests/test_agent.py::test_excerpt_blocks_restricted_when_enabled`.
