# ADR-0005 — Excerpt tool stays opt-in permanently; no progressive auto-unlock

**Status:** Accepted
**Resolves:** Q-1 (`architecture-impact-analysis.md` §9)
**Date:** 2026-05-08

## Context

`enable_excerpt_tool = false` is the Phase 1 default. Two long-term paths:

1. **Permanent opt-in** — operator must consciously flip the flag every
   install, forever
2. **Progressive auto-unlock** — once trust is established (N successful
   sessions, M days clean, etc.), default flips to true

## Decision

**The excerpt tool stays permanently opt-in. Never auto-unlocks. The
default is `false` in every release, every config template, every
operator install — forever.**

The opt-in flip generates a critical-severity audit event so the moment
of risk-acceptance is durably recorded. An optional yearly nudge
(`/privacy-manage` skill suggestion) prompts the operator to re-confirm,
but never changes the default.

## Reasoning

1. **Conscious risk-taking is the point.** The cost of `enable_excerpt_tool
   = false` is *the moment of decision* it forces. Removing that moment
   removes the value.
2. **Drift over time.** A "use it for 30 days, then auto-on" rule looks
   fine in week one. By month six the operator has forgotten the flag
   exists. By year two they don't remember they ever opted in. That's
   not a defended posture; that's defaults shifting over time.
3. **Trust isn't transferable.** The system being clean for 30 days proves
   the system was clean for 30 days. It doesn't prove that the operator
   has thought through the data-minimization trade for *their current
   workflows*. Re-confirmation should be tied to operator intent, not
   system state.
4. **Audit-event on flip is the feature.** When excerpt becomes on, the
   "excerpt_enabled" audit row with timestamp, orchestrator, and operator
   action is *exactly* the artifact a future incident investigator wants.
   "When did this dangerous capability come online?" has an answer.

## Alternatives considered

- **Auto-unlock after N days clean.** Rejected per Reasoning #2 / #3.
- **Operator-initiated unlock with quarterly auto-revert.** Considered but
  adds reverse-direction friction (operator's workflow breaks every 3
  months until they re-flip). Net negative.
- **Unlock per-volume rather than globally.** Could work — `enable_excerpt
  for volume X` instead of a global flag. Adds complexity for a marginal
  gain; revisit if operator demand shows up.

## Consequences

**Enables:**
- Threat model stays simple: "to leak via excerpt, operator must have
  flipped the flag."
- Compliance audits have a clean answer: "excerpt is off by default;
  flipping is logged and timestamped."
- Operator onboarding: "the dangerous tool isn't enabled. If you need it,
  flip it deliberately and the audit log records that."

**Costs:**
- Power users who use excerpt every session live with a one-line config
  edit forever. Mild friction; the audit-log entry confirming flip-on
  amortizes the cost across the entire flip-on period.
- The `/privacy-manage configure --excerpt-tool on` UX needs to be smooth
  enough that operators don't dread it. UX problem, not policy problem.

## Implementation pointer

`config/default.toml` ships `enable_excerpt_tool = false` permanently.
The `/privacy-manage` skill (Phase 2) gains a `configure` mode that can
flip the flag and emits the critical audit event:

```python
# privacy_agent/cli.py — Phase 2 addition
def _cmd_configure_excerpt(args):
    state = "on" if args.enabled else "off"
    agent = build_agent()
    agent.audit.log(
        "config_change",
        orchestrator="manual",
        severity="critical" if args.enabled else "info",
        data_returned="metadata_only",
        bytes_returned=0,
    )
    # update config file...
```

The `excerpt_enabled` audit event is the durable record of intent.
