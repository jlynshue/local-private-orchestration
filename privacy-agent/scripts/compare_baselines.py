#!/usr/bin/env python3
"""Compare a freshly-captured perf baseline against a committed one.

Usage:
    python scripts/compare_baselines.py NEW_BASELINE.json [REFERENCE.json]

If REFERENCE is omitted, uses ``bench/baseline.committed.json`` (the file
checked into the repo as the Phase 1 reference). When the committed file
doesn't exist yet (early Phase 1) the script prints the new numbers and
exits 0 — the first run establishes the reference.

Phase 1 behavior: print the diff, exit 0 (informational).
Phase 2 toggles a regression-fail mode via env ``PERF_FAIL_ON_REGRESSION=1``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = REPO_ROOT / "bench" / "baseline.committed.json"

# Per-metric ratio thresholds. Sub-ms p99 metrics swing 10x between runs from
# GC/fsync/scheduler noise alone; the global 1.20 was wrong for them. Tighten
# where the absolute number matters; loosen where one bad sample dominates.
#
# Pattern → ratio. First match wins. Patterns are simple substrings.
THRESHOLD_RULES: list[tuple[str, float]] = [
    # Sub-millisecond p99 metrics are hopelessly noisy at this scale.
    ("audit_write_latency_ms.p99", 4.0),
    ("audit_write_latency_ms.p95", 2.5),
    ("search_latency_ms.p99", 2.0),
    ("chain_verify_ms.elapsed_ms", 1.5),
    # Throughput / mean latency are stable signal — tight bound.
    ("files_per_sec", 1.15),
    ("bytes_per_sec", 1.15),
    ("search_latency_ms.mean", 1.15),
    ("search_latency_ms.p50", 1.20),
    ("search_latency_ms.p95", 1.30),
    ("redactor.ms_per_kb", 1.20),
    ("redactor.us_per_call", 1.20),
    # Identity-style metrics — should never change.
    (".n", 1.001),
    (".entries", 1.001),
    (".files", 1.001),
    (".total_bytes", 1.001),
]
DEFAULT_THRESHOLD = 1.30


def _threshold_for(metric: str) -> float:
    for substr, ratio in THRESHOLD_RULES:
        if substr in metric:
            return ratio
    return DEFAULT_THRESHOLD


def _flatten(metrics: dict, prefix: str = "") -> dict[str, float]:
    flat: dict[str, float] = {}
    for k, v in metrics.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict):
            flat.update(_flatten(v, key))
        elif isinstance(v, (int, float)):
            flat[key] = float(v)
    return flat


def _is_higher_is_better(name: str) -> bool:
    # Throughput-style metrics: bigger = better
    return any(s in name for s in ("per_sec", "throughput.files", "throughput.bytes"))


def _diff_pct(new: float, ref: float) -> float:
    if ref == 0:
        return 0.0
    return ((new - ref) / ref) * 100


def _verdict(name: str, new: float, ref: float) -> str:
    pct = _diff_pct(new, ref)
    if abs(pct) < 5:
        return "≈"
    higher_better = _is_higher_is_better(name)
    if higher_better:
        return "↑" if pct > 0 else "↓"
    return "↓" if pct < 0 else "↑"


def _is_regression(name: str, new: float, ref: float) -> bool:
    threshold = _threshold_for(name)
    higher_better = _is_higher_is_better(name)
    if higher_better:
        return new < ref / threshold
    return new > ref * threshold


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: compare_baselines.py NEW.json [REFERENCE.json]", file=sys.stderr)
        return 2

    new_path = Path(argv[1])
    ref_path = Path(argv[2]) if len(argv) >= 3 else DEFAULT_REFERENCE

    if not new_path.exists():
        print(f"new baseline file not found: {new_path}", file=sys.stderr)
        return 2

    new = json.loads(new_path.read_text())
    new_flat = _flatten(new["metrics"])

    print(f"baseline captured at: {new['captured_at']}")
    print(f"host: {new['host']['platform']} python={new['host']['python']}")
    print()

    if not ref_path.exists():
        print(f"no reference at {ref_path} — printing new values only:")
        for k, v in sorted(new_flat.items()):
            print(f"  {k:40s}  {v:>12.4f}")
        print()
        print("(commit this file as bench/baseline.committed.json to lock in.)")
        return 0

    ref = json.loads(ref_path.read_text())
    ref_flat = _flatten(ref["metrics"])

    print(f"comparing against: {ref_path.name} (captured {ref['captured_at']})")
    print(f"{'metric':40s}  {'reference':>12s}  {'new':>12s}  {'Δ%':>8s}  v")
    print("-" * 86)

    regressions: list[str] = []
    for k in sorted(set(new_flat) | set(ref_flat)):
        ref_val = ref_flat.get(k)
        new_val = new_flat.get(k)
        if ref_val is None or new_val is None:
            print(f"{k:40s}  {'-' if ref_val is None else f'{ref_val:.4f}':>12s}  "
                  f"{'-' if new_val is None else f'{new_val:.4f}':>12s}  -")
            continue
        pct = _diff_pct(new_val, ref_val)
        verdict = _verdict(k, new_val, ref_val)
        flag = " REGR" if _is_regression(k, new_val, ref_val) else ""
        print(f"{k:40s}  {ref_val:>12.4f}  {new_val:>12.4f}  {pct:>+7.1f}%  {verdict}{flag}")
        if flag:
            regressions.append(k)

    print()
    if regressions:
        print(f"⚠  {len(regressions)} regression(s) detected: {', '.join(regressions)}")
        if os.getenv("PERF_FAIL_ON_REGRESSION") == "1":
            return 1
        print("   (PERF_FAIL_ON_REGRESSION not set — informational only)")
    else:
        print("✓ no regressions beyond per-metric thresholds")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
