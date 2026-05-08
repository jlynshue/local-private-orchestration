"""Phase 1 perf baselines (NFR-PERF-1).

Captures:
- Search latency p50 / p95 over the perf_query_terms corpus
- Index throughput (files/sec) on the 200-file synthetic corpus
- Redactor overhead per kilobyte
- Audit-log write latency
- DB open + chain-verify cost on a populated chain

Writes ``bench/baseline.json`` next to the test root. Phase 2 perf runs
compare against this file via ``scripts/compare_baselines.py``.
"""
from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from privacy_agent.agent import PrivacyAgent
from privacy_agent.audit import AuditLogger
from privacy_agent.config import (
    ClassificationConfig,
    ClassificationRuleConfig,
    Config,
    ConsentConfig,
)
from privacy_agent.db import open_db
from privacy_agent.redactor import default_redactor


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = REPO_ROOT / "bench"
BASELINE_PATH = BENCH_DIR / "baseline.json"

ITERATIONS_SEARCH = 200
ITERATIONS_AUDIT = 500


def _percentile(values: list[float], p: float) -> float:
    """Sorted-array percentile, interpolating between samples."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = (p / 100) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


@pytest.fixture(scope="session")
def populated_agent(perf_corpus, tmp_path_factory):
    """Index the perf corpus once per session and return a ready PrivacyAgent."""
    db_path = tmp_path_factory.mktemp("perf_db") / "perf.db"
    conn = open_db(db_path)

    cfg = Config()
    cfg.consent = ConsentConfig(
        default_expiry_hours=168,
        excerpt_lease_minutes=30,
        require_per_volume_consent=True,
    )
    cfg.classification = ClassificationConfig(
        default_level="internal",
        rules=[
            ClassificationRuleConfig("*/tax/*", "confidential"),
            ClassificationRuleConfig("*/medical/*", "restricted"),
        ],
    )
    agent = PrivacyAgent(conn, cfg, orchestrator="claude_code")
    agent.consent.grant(str(perf_corpus), "index", "volume")
    agent.consent.grant(str(perf_corpus), "search", "volume")

    # Time the indexing run for the throughput metric.
    t0 = time.perf_counter()
    stats = agent.handle_index_volume(
        volume_path=str(perf_corpus), volume_id="vol_perf"
    ).payload
    elapsed = time.perf_counter() - t0

    yield agent, perf_corpus, stats, elapsed

    conn.close()


def test_search_latency(populated_agent, perf_query_terms):
    agent, corpus, _, _ = populated_agent
    samples_ms: list[float] = []

    # Warm up
    for q in perf_query_terms[:3]:
        agent.handle_search(query=q, scope=str(corpus))

    rng = __import__("random").Random(42)
    for _ in range(ITERATIONS_SEARCH):
        q = rng.choice(perf_query_terms)
        t0 = time.perf_counter()
        agent.handle_search(query=q, scope=str(corpus))
        samples_ms.append((time.perf_counter() - t0) * 1000)

    p50 = _percentile(samples_ms, 50)
    p95 = _percentile(samples_ms, 95)
    p99 = _percentile(samples_ms, 99)
    mean = statistics.mean(samples_ms)
    print(
        f"\n[perf] search latency over {ITERATIONS_SEARCH} queries: "
        f"p50={p50:.2f}ms p95={p95:.2f}ms p99={p99:.2f}ms mean={mean:.2f}ms"
    )

    _record(
        "search_latency_ms",
        {"p50": p50, "p95": p95, "p99": p99, "mean": mean, "n": ITERATIONS_SEARCH},
    )

    # Phase 1 sanity bound — far above any reasonable real-world baseline.
    # Phase 2 sets the tighter SLO (≤ 500ms p95 per integrated-phased-plan §4.6).
    assert p95 < 1000, f"search p95 {p95:.2f}ms exceeds Phase 1 sanity bound"


def test_index_throughput(populated_agent):
    _, _, stats, elapsed = populated_agent
    files = stats["indexed_files"]
    assert files > 0
    rate = files / max(elapsed, 1e-6)
    bytes_per_sec = stats["total_indexed_bytes"] / max(elapsed, 1e-6)
    print(
        f"\n[perf] index throughput: {files} files in {elapsed:.2f}s "
        f"= {rate:.1f} files/s ({bytes_per_sec / 1024:.1f} KB/s)"
    )
    _record(
        "index_throughput",
        {
            "files": files,
            "elapsed_s": elapsed,
            "files_per_sec": rate,
            "bytes_per_sec": bytes_per_sec,
        },
    )
    # Phase 1 sanity bound — anything below 5 files/s on this corpus is a
    # serious regression signal.
    assert rate >= 5, f"index throughput {rate:.2f} files/s below sanity floor"


def test_redactor_throughput():
    redactor = default_redactor()
    test_strings = [
        "Contact jane@example.com or 555-867-5309. SSN 123-45-6789. " * (k + 1)
        for k in range(100)
    ]
    sizes = [len(s.encode("utf-8")) for s in test_strings]
    total_bytes = sum(sizes)

    t0 = time.perf_counter()
    for s in test_strings:
        redactor.scrub(s)
    elapsed = time.perf_counter() - t0
    elapsed_ms = elapsed * 1000

    per_kb_ms = elapsed_ms / max(total_bytes / 1024, 1e-6)
    per_call_us = (elapsed * 1e6) / len(test_strings)
    print(
        f"\n[perf] redactor: {len(test_strings)} payloads totalling "
        f"{total_bytes/1024:.1f} KB in {elapsed_ms:.2f}ms "
        f"= {per_kb_ms:.3f} ms/KB ({per_call_us:.1f} µs/call)"
    )
    _record(
        "redactor",
        {
            "total_bytes": total_bytes,
            "elapsed_ms": elapsed_ms,
            "ms_per_kb": per_kb_ms,
            "us_per_call": per_call_us,
        },
    )


def test_audit_write_latency(tmp_db_path):
    conn = open_db(tmp_db_path)
    try:
        logger = AuditLogger(conn)
        samples_ms: list[float] = []
        for i in range(ITERATIONS_AUDIT):
            t0 = time.perf_counter()
            logger.log(
                "search",
                "claude_code",
                query=f"q{i}",
                paths_accessed=[f"/x/{i}"],
                data_returned="snippet",
                bytes_returned=200,
                pii_redactions_applied=2,
            )
            samples_ms.append((time.perf_counter() - t0) * 1000)
        p50 = _percentile(samples_ms, 50)
        p95 = _percentile(samples_ms, 95)
        p99 = _percentile(samples_ms, 99)
        print(
            f"\n[perf] audit write over {ITERATIONS_AUDIT} entries: "
            f"p50={p50:.2f}ms p95={p95:.2f}ms p99={p99:.2f}ms"
        )
        _record(
            "audit_write_latency_ms",
            {"p50": p50, "p95": p95, "p99": p99, "n": ITERATIONS_AUDIT},
        )
    finally:
        conn.close()


def test_chain_verify_cost(tmp_db_path):
    """Time how long verify_chain_integrity takes on a 1000-entry chain."""
    conn = open_db(tmp_db_path)
    try:
        logger = AuditLogger(conn)
        for i in range(1000):
            logger.log("search", "claude_code", query=f"q{i}")
        t0 = time.perf_counter()
        valid, broken = logger.verify_chain_integrity()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert valid is True
        assert broken == []
        print(
            f"\n[perf] verify_chain_integrity on 1000 entries: {elapsed_ms:.2f}ms"
        )
        _record(
            "chain_verify_ms",
            {"entries": 1000, "elapsed_ms": elapsed_ms},
        )
    finally:
        conn.close()


# -- baseline writer --

_results: dict[str, dict] = {}


def _record(metric: str, value: dict) -> None:
    _results[metric] = value


@pytest.fixture(scope="session", autouse=True)
def _flush_baseline_at_session_end():
    yield
    BENCH_DIR.mkdir(exist_ok=True)
    payload = {
        "version": "0.1.0-alpha",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "machine": platform.machine(),
        },
        "metrics": _results,
    }
    # PERF_BASELINE_OUTPUT lets the multi-run orchestrator write each run to
    # a distinct file; default behavior matches single-run usage.
    import os
    output_env = os.getenv("PERF_BASELINE_OUTPUT")
    output_path = Path(output_env) if output_env else BASELINE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    try:
        rel = output_path.relative_to(REPO_ROOT)
    except ValueError:
        rel = output_path
    print(f"\n[perf] baseline written → {rel}")
