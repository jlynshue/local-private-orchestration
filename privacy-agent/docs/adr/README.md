# Architecture Decision Records

Short, immutable records of design decisions that resolve open questions
from the design phase. Each ADR locks in *one* call so future investigators
can reconstruct *why* a choice was made — not just what was built.

## Format

We follow [MADR](https://adr.github.io/madr/) (lightweight). Each file:

- **Title** — short imperative
- **Status** — `Proposed` | `Accepted` | `Deprecated` | `Superseded by ADR-NNNN`
- **Context** — the question this answers and the constraints in play
- **Decision** — the call, in one paragraph
- **Reasoning** — why this and not the alternatives
- **Alternatives considered** — what else was on the table and why rejected
- **Consequences** — what becomes possible / impossible / harder

ADRs are immutable once accepted. To change a decision, write a new ADR
that supersedes the old one.

## Index

| # | Title | Status | Resolves |
|---|---|---|---|
| [0001](0001-excerpt-classification-cap.md) | Cap excerpt at confidential | Accepted | Q-A |
| [0002](0002-local-llm-choice.md) | Use Phi-3-mini for redaction gate | Accepted | Q-B |
| [0003](0003-oob-consent-ui.md) | osascript for consent UI v1 | Accepted | Q-C |
| [0004](0004-firewall-enforcement.md) | Optional firewall, never mandatory | Accepted | Q-D |
| [0005](0005-excerpt-policy-permanence.md) | Permanent opt-in for excerpt tool | Accepted | Q-1 |

## Naming

`NNNN-short-kebab-title.md`. Numbers are zero-padded, monotonically increasing,
never reused.
