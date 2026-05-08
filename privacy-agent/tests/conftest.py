"""Shared pytest fixtures for privacy-agent."""
from __future__ import annotations

from pathlib import Path

import pytest

from privacy_agent import db


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(tmp_db_path: Path):
    """Open an in-tmp SQLite connection (no encryption — fast unit tests)."""
    c = db.open_db(tmp_db_path)
    yield c
    db.close_db(c)


@pytest.fixture
def fixture_text_file(tmp_path: Path) -> Path:
    """A small plain-text file with mixed normal text and PII-shaped strings."""
    p = tmp_path / "sample.txt"
    p.write_text(
        "Quarterly report draft.\n"
        "Contact: jane@example.com or call 555-867-5309.\n"
        "Account balance for 4111-1111-1111-1111 is $1,234.56.\n"
        "SSN 123-45-6789 verified.\n"
        "End of report.\n"
    )
    return p
