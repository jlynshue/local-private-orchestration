"""Perf-test fixtures: a synthetic corpus large enough to be representative
but small enough to run inside ~10s on a laptop.

Defaults:
- 200 text files, average 2 KB each (~400 KB corpus)
- ~1 in 4 files contains PII-shaped strings to exercise the redactor
- File names + paths follow the same patterns the classifier expects so a
  realistic mix of internal/confidential/restricted classifications results
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest


WORDS = (
    "quarterly review report draft contract agreement memo budget "
    "filing return invoice billing address account customer subject "
    "lab results notes summary executive division department project"
).split()


def _line(seed: int, with_pii: bool) -> str:
    rnd = random.Random(seed)
    base = " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(8, 16)))
    if with_pii:
        # Salted PII so the redactor has work to do
        ssn = f"{rnd.randint(100, 899)}-{rnd.randint(10, 99)}-{rnd.randint(1000, 9999)}"
        email = f"user{rnd.randint(0, 999)}@example.invalid"
        phone = f"555-{rnd.randint(100, 999)}-{rnd.randint(1000, 9999)}"
        base += f". Contact {email} or {phone}. Ref SSN {ssn}."
    return base


def _make_file(path: Path, file_seed: int, line_count: int = 25) -> None:
    has_pii = (file_seed % 4 == 0)
    body = "\n".join(_line(file_seed * 100 + i, has_pii and i < 3) for i in range(line_count))
    path.write_text(body)


@pytest.fixture(scope="session")
def perf_corpus(tmp_path_factory) -> Path:
    """Build a 200-file corpus once per test session and cache it."""
    root = tmp_path_factory.mktemp("perf_corpus")

    # 100 generic txt files (default classification = internal)
    for i in range(100):
        _make_file(root / f"doc_{i:03d}.txt", i)

    # 50 in /tax/* (will be confidential by default rule)
    tax = root / "tax"
    tax.mkdir()
    for i in range(50):
        _make_file(tax / f"return_{i:03d}.txt", 1000 + i)

    # 50 in /medical/* (will be restricted)
    med = root / "medical"
    med.mkdir()
    for i in range(50):
        _make_file(med / f"labs_{i:03d}.txt", 2000 + i)

    return root


@pytest.fixture(scope="session")
def perf_query_terms() -> list[str]:
    """A representative mix of queries — common words, rare words, multi-word."""
    return [
        "quarterly", "report", "memo", "budget", "executive",
        "subject lab results", "filing return", "draft agreement",
        "invoice", "address", "department project",
        # Long-tail terms unlikely to match much
        "ephemeral", "asymptotic",
        # Two-word phrases
        "quarterly review", "budget filing",
    ]
