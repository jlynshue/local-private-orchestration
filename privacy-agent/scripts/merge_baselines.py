#!/usr/bin/env python3
"""Merge multiple perf baseline JSONs into a single median baseline.

Usage:
    python scripts/merge_baselines.py run1.json run2.json run3.json -o merged.json

For each numeric metric in the input files, the output contains the median
across runs. Non-numeric fields (host, captured_at, version) are taken from
the last input. Use ``run-perf-baselines.sh`` for the standard 3-run flow.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any


def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(_flatten(v, key))
        else:
            flat[key] = v
    return flat


def _unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(".")
        cur = out
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value
    return out


def merge(payloads: list[dict]) -> dict:
    if not payloads:
        raise ValueError("no payloads supplied")

    flats = [_flatten(p["metrics"]) for p in payloads]
    keys = set()
    for f in flats:
        keys.update(f)

    merged: dict[str, Any] = {}
    for k in keys:
        values = [f[k] for f in flats if k in f]
        if not values:
            continue
        if all(isinstance(v, (int, float)) for v in values):
            merged[k] = statistics.median(values)
        else:
            # Non-numeric: take the most recent value.
            merged[k] = values[-1]

    last = payloads[-1]
    return {
        "version": last.get("version", "unknown"),
        "captured_at": last.get("captured_at"),
        "host": last.get("host"),
        "merge": {
            "method": "median",
            "input_count": len(payloads),
            "input_captured_at": [p.get("captured_at") for p in payloads],
        },
        "metrics": _unflatten(merged),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path, help="perf baseline JSON files")
    parser.add_argument("-o", "--output", type=Path, required=True, help="merged output path")
    args = parser.parse_args(argv)

    payloads = []
    for path in args.inputs:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 2
        payloads.append(json.loads(path.read_text()))

    merged = merge(payloads)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, indent=2))
    print(f"merged {len(payloads)} runs → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
