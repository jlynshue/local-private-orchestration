# ADR-0003 — `osascript` for the H3 out-of-band consent UI v1

**Status:** Accepted
**Resolves:** Q-C (`integrated-phased-plan.md` §6)
**Date:** 2026-05-08

## Context

H3 (Phase 2) replaces stdio consent prompts with an out-of-band UI to
close the prompt-injection vector against consent. Three implementation
candidates were considered:

- `osascript display dialog` — built into macOS, zero install cost
- SwiftUI menu-bar app — best UX but weeks of work
- Electron — cross-platform but heavyweight

## Decision

**Phase 2 v1 uses `osascript display dialog` for OOB consent. SwiftUI
menu-bar app is deferred to Phase 3 (after operator demand justifies the
investment). Electron is not on the roadmap.**

The privacy-agent shells out to `osascript` via a thin wrapper module
(`privacy_agent.consent_ui`) that the `privacy_get_consent(request=true)`
flow invokes when no active consent exists.

## Reasoning

1. **Threat model fit.** H3's purpose is closing the prompt-injection
   vector. `osascript` runs in the user's window-server session — it
   cannot be forged by the model writing JSON to stdio. That's the entire
   security property H3 needs.
2. **Cost.** Zero install. Ships in macOS. Phase 2 has a 7-week budget;
   spending 2 of those on a menu-bar app would crowd out H1 and M3.
3. **Experimental signal.** Until operators actually use OOB consent, we
   don't know what UX problems matter. `osascript` lets us learn cheaply.
   When real friction shows up, that drives the SwiftUI work.
4. **Reversibility.** Replacing `osascript` with a SwiftUI app is local
   to one module. The privacy-agent's contract is unchanged.

## Alternatives considered

- **SwiftUI menu-bar app.** Better long-term UX (persistent, queueable
  pending requests, status indicator). Costs: Apple Developer Program
  signing, distribution mechanism, ongoing maintenance. Defer until Phase
  3, gated on real operator demand.
- **Electron.** Cross-platform pitch is real but the runtime cost (~100 MB,
  separate Chromium per app) contradicts the privacy-agent's lean ethos.
  And cross-platform isn't a Phase 2 goal (we're macOS-only until Phase 3).
- **Notification Center via `terminal-notifier`.** Display-only — no input
  channel. Fails the "operator must approve" requirement.
- **Web UI on localhost.** Adds an HTTP server and a browser-tab dependency.
  Worse threat model than `osascript` because it routes through the
  WebKit/Chrome/Safari layer which has its own attack surface.

## Consequences

**Enables:**
- Phase 2 H3 ships on schedule
- The privacy-agent stays a single Python process — no second app to install
- Cross-shell compatibility (works from Claude Code, terminal, scripts)

**Costs:**
- Modal dialog UX — operator sees a system dialog mid-session. Can't queue
  multiple pending requests; one at a time. Documented as "interrupt-driven
  consent for Phase 2."
- macOS-only. Phase 3 cross-platform work (linux: zenity, windows: COM)
  would need a different abstraction.
- `osascript` requires accessibility permissions for some flows; documented
  in RUNBOOK.

## Implementation pointer

Phase 2 work:

```python
# privacy_agent/consent_ui.py
def request_consent_via_dialog(path: str, scope: str, granularity: str) -> bool:
    """Show macOS dialog, return True iff operator approved."""
    script = f"""
        display dialog "privacy-agent: grant {scope} consent for {path!r}?" \\
            buttons {{"Deny", "Grant"}} \\
            default button "Deny" \\
            with icon caution
    """
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return "Grant" in result.stdout
```

Wired into `agent.handle_get_consent(request=True)` so an MCP request for
consent triggers the OOB dialog. The grant — if approved — is signed with
a Keychain-stored key so the daemon can verify the operator clicked rather
than something else faked stdout.
