# Performance baselines (NFR-PERF-1)

Two files live here:

- **`baseline.committed.json`** — the *reference* baseline checked into the
  repo. Phase 2 PRs are compared against this. Update it deliberately when
  performance work intentionally improves a number, or when hardware
  changes invalidate it.
- **`baseline.json`** — *gitignored*. Written by every `pytest tests/perf/`
  run on the local box. Comparison script reads this and prints diffs.

## Capturing a fresh baseline

```bash
.venv/bin/pytest tests/perf/ -q -s
.venv/bin/python scripts/compare_baselines.py bench/baseline.json
```

## Promoting a new reference

Only do this when you mean to:

```bash
cp bench/baseline.json bench/baseline.committed.json
git add bench/baseline.committed.json
git commit -m "perf: refresh baseline reference (intent: <reason>)"
```

The commit message should record *why* the new reference was promoted —
new hardware, intentional optimization, etc. — so future investigators
can reconstruct what changed.

## Phase 1 reference numbers

These are the numbers committed for the Phase 1 reference. Anything
≥20% worse will trip the comparison script's regression flag (Phase 2
will fail CI on regression; Phase 1 is informational).

| Metric | Reference |
|---|---|
| Search p50 / p95 / p99 (ms) | 3.24 / 7.03 / 11.61 |
| Search mean (ms, n=200) | 3.27 |
| Index throughput | 1155 files/s, 2.7 MB/s on a 200-file synthetic corpus |
| Redactor | 0.21 ms/KB, 602 µs/call |
| Audit write p50 / p95 / p99 (ms, n=500) | 0.06 / 0.16 / 0.25 |
| Chain verify (1000-entry chain) | 12.55 ms |

Hardware: macOS / arm64 / Python 3.14.3.

## Phase 2 SLOs to defend

Per `../.context/integrated-phased-plan.md` §4.6:

- Search p95 ≤ 700 ms (Phase 2, with hybrid + H1 redactor)
- Index throughput ≥ 100 files/s baseline
- Regex redactor < 5 ms/snippet
- H1 model redactor < 200 ms p95

The current Phase 1 numbers leave generous headroom for Phase 2's
additions (LLM redaction will dominate; the rest is essentially free).
