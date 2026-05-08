# Design background

The three documents in this directory are the locked-in design artifacts that
the Phase 1 implementation was built against. They were produced through a
sequence of synthesis tasks; this directory captures the snapshot at the
moment Phase 1 went into build.

## Read in this order

1. **`architecture-impact-analysis.md`** — synthesis of the two source plans
   (`title-privacy-preserving-orchestration-robust-moth.md` and a competing
   `implementation_plan.md`) into a single merged architecture, with conflict
   resolutions surfaced explicitly.
2. **`enhancement-proposals.md`** — twelve enhancements (H1–H7 high, M1–M6
   medium, L1–L3 exploratory) that go beyond what either source plan covered.
3. **`integrated-phased-plan.md`** — the canonical roadmap. Slots every
   enhancement into Phase 1 (Crawl) / Phase 2 (Walk) / Phase 3 (Run) with
   sequencing principles, sub-milestones, exit criteria, and gate reviews.

## Where these came from vs. where they live

In an active Conductor workspace, in-flight design discussion happens in the
workspace's `.context/` directory (gitignored). Once a design is locked in
and ready to drive build, the relevant artifacts get copied here and treated
as immutable snapshots — newer design discussions belong back in `.context/`
on a fresh workspace.

## Quick reference

- The 8-layer defense is documented in `architecture-impact-analysis.md` §5.
- The 14 NFRs the Phase 1 build honors live in `architecture-impact-analysis.md` §6.
- The 17 open questions (Q-1 through Q-10 + Q-A through Q-G) are in
  `architecture-impact-analysis.md` §9 and `integrated-phased-plan.md` §6.
- The phase-mapping reverse-index table (which enhancement → which phase, why)
  is `integrated-phased-plan.md` §5.
