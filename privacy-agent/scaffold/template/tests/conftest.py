"""Shared fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from __AGENT_NAME_SNAKE__ import db


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(tmp_db_path: Path):
    c = db.open_db(tmp_db_path)
    yield c
    c.close()
