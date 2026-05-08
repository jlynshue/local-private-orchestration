"""Tests for the indexer."""
from __future__ import annotations

from pathlib import Path

import pytest

from privacy_agent.classifier import Classifier
from privacy_agent.config import (
    ClassificationConfig,
    ClassificationRuleConfig,
    ExtractorsConfig,
)
from privacy_agent.extractors import ExtractorRegistry
from privacy_agent.indexer import Indexer
from privacy_agent.redactor import default_redactor


@pytest.fixture
def make_indexer(conn):
    def _factory(rules=None):
        cfg = ClassificationConfig(
            default_level="internal",
            rules=[ClassificationRuleConfig(p, lvl) for p, lvl in (rules or [])],
        )
        return Indexer(
            conn=conn,
            registry=ExtractorRegistry(),
            classifier=Classifier(cfg),
            redactor=default_redactor(),
            cfg=ExtractorsConfig(),
        )

    return _factory


def _seed_volume(root: Path) -> None:
    """Build a small fixture volume."""
    (root / "notes.txt").write_text("Quarterly report draft. Contact 555-867-5309.")
    (root / "config.json").write_text('{"port": 8080, "user": "admin"}')
    (root / "data.csv").write_text("name,balance\nAlice,100\nBob,200\n")
    nested = root / "tax"
    nested.mkdir()
    (nested / "2024.txt").write_text("Federal tax return — SSN 123-45-6789, $5,000.00 due.")
    # Should be skipped: extension not in registry.
    (root / "ignored.bin").write_bytes(b"\x00\x01")


def test_indexes_supported_files(tmp_path: Path, make_indexer, conn):
    _seed_volume(tmp_path)
    idx = make_indexer()
    stats = idx.index_volume(tmp_path, "vol_test")

    assert stats.indexed_files == 4
    assert stats.failed_files == 0
    assert "txt" in stats.file_type_counts
    assert "json" in stats.file_type_counts

    rows = conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()
    assert rows["c"] == 4


def test_redacts_content_at_index_time(tmp_path: Path, make_indexer, conn):
    """Plan invariant: index never contains raw PII."""
    _seed_volume(tmp_path)
    idx = make_indexer()
    idx.index_volume(tmp_path, "vol_test")

    cur = conn.execute("SELECT content FROM files_fts")
    all_indexed = "\n".join(row["content"] or "" for row in cur.fetchall())
    assert "123-45-6789" not in all_indexed
    assert "555-867-5309" not in all_indexed
    assert "[REDACTED:SSN]" in all_indexed
    assert "[REDACTED:PHONE]" in all_indexed


def test_classification_applied(tmp_path: Path, make_indexer, conn):
    _seed_volume(tmp_path)
    idx = make_indexer(rules=[("*/tax/*", "confidential")])
    idx.index_volume(tmp_path, "vol_test")

    cur = conn.execute(
        "SELECT classification FROM files WHERE relative_path LIKE 'tax/%'"
    )
    row = cur.fetchone()
    assert row is not None
    assert row["classification"] == "confidential"


def test_incremental_indexing(tmp_path: Path, make_indexer, conn):
    _seed_volume(tmp_path)
    idx = make_indexer()
    stats1 = idx.index_volume(tmp_path, "vol_test")
    assert stats1.indexed_files == 4

    # Re-index without changes — should index zero new files.
    stats2 = idx.index_volume(tmp_path, "vol_test")
    assert stats2.indexed_files == 0
    assert stats2.total_files == 4  # still walked, just skipped


def test_force_reindex(tmp_path: Path, make_indexer, conn):
    _seed_volume(tmp_path)
    idx = make_indexer()
    idx.index_volume(tmp_path, "vol_test")
    stats = idx.index_volume(tmp_path, "vol_test", force_reindex=True)
    assert stats.indexed_files == 4


def test_exclude_patterns(tmp_path: Path, make_indexer, conn):
    _seed_volume(tmp_path)
    idx = make_indexer()
    stats = idx.index_volume(tmp_path, "vol_test", exclude_patterns=["tax/*"])
    # Tax dir excluded.
    cur = conn.execute("SELECT COUNT(*) AS c FROM files WHERE relative_path LIKE 'tax/%'")
    assert cur.fetchone()["c"] == 0
    assert stats.indexed_files == 3


def test_size_cap_skips_oversize_files(tmp_path: Path, conn):
    big = tmp_path / "huge.txt"
    big.write_text("x" * (2 * 1024 * 1024))  # 2 MB
    cfg = ExtractorsConfig(max_file_size_mb=1)  # 1 MB cap
    idx = Indexer(
        conn,
        ExtractorRegistry(),
        Classifier(ClassificationConfig()),
        default_redactor(),
        cfg,
    )
    stats = idx.index_volume(tmp_path, "vol_test")
    assert stats.indexed_files == 0


def test_volume_path_missing_raises(tmp_path: Path, make_indexer):
    idx = make_indexer()
    with pytest.raises(FileNotFoundError):
        idx.index_volume(tmp_path / "nope", "vol_test")
