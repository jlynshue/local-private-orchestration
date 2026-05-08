"""Tests for the FTS5-backed search engine."""
from __future__ import annotations

from pathlib import Path

import pytest

from privacy_agent.classifier import Classifier
from privacy_agent.config import (
    AgentConfig,
    ClassificationConfig,
    ClassificationRuleConfig,
    ExtractorsConfig,
)
from privacy_agent.extractors import ExtractorRegistry
from privacy_agent.indexer import Indexer
from privacy_agent.redactor import default_redactor
from privacy_agent.search import SearchEngine


@pytest.fixture
def populated(conn, tmp_path: Path):
    """Index a fixture volume with mixed classifications."""
    (tmp_path / "public_notes.txt").write_text(
        "Quarterly report draft. Quarterly numbers look good. "
        "Public release scheduled."
    )
    (tmp_path / "memo.txt").write_text("Internal memo about the quarterly review process.")
    tax = tmp_path / "tax"
    tax.mkdir()
    (tax / "2024.txt").write_text(
        "Federal tax return for 2024 quarterly filing. SSN 123-45-6789. Total $5,000."
    )
    medical = tmp_path / "medical"
    medical.mkdir()
    (medical / "labs.txt").write_text("Lab results from the quarterly checkup.")

    # Note: classifier ratchets *up* only — a "public" rule against the
    # internal default would be ignored. Public files just stay at default.
    cls_cfg = ClassificationConfig(
        default_level="internal",
        rules=[
            ClassificationRuleConfig("*/tax/*", "confidential"),
            ClassificationRuleConfig("*/medical/*", "restricted"),
        ],
    )
    idx = Indexer(
        conn,
        ExtractorRegistry(),
        Classifier(cls_cfg),
        default_redactor(),
        ExtractorsConfig(),
    )
    idx.index_volume(tmp_path, "vol_test")
    return conn


def test_search_returns_relative_path_not_absolute(populated):
    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    results = eng.search("quarterly")
    assert len(results) >= 1
    for r in results:
        assert not r.relative_path.startswith("/")
        assert r.volume_id == "vol_test"


def test_search_snippet_redacted(populated):
    """SSN must not appear in snippet even though FTS5 might naively highlight it."""
    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    results = eng.search("quarterly")
    # Find the tax result.
    tax = next((r for r in results if "tax" in r.relative_path), None)
    assert tax is not None
    assert "123-45-6789" not in tax.snippet
    # Either redacted at index time (the marker survives in the snippet) OR
    # not present in the snippet at all — both are acceptable.


def test_search_provenance_id_present(populated):
    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    results = eng.search("quarterly")
    assert all(r.provenance_id for r in results)
    # Each result has a unique provenance_id.
    ids = {r.provenance_id for r in results}
    assert len(ids) == len(results)


def test_classification_filter(populated):
    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    results = eng.search("quarterly", classification_filter=["confidential"])
    assert len(results) >= 1
    assert all(r.classification == "confidential" for r in results)
    # Inverse: filtering to a level no file matches returns empty.
    none = eng.search("quarterly", classification_filter=["public"])
    assert none == []


def test_classification_cap_blocks_restricted(populated):
    """Cap at 'confidential' must hide medical (restricted)."""
    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    capped = eng.search("quarterly", classification_cap="confidential")
    assert all(r.classification != "restricted" for r in capped)


def test_max_results_respected(populated):
    eng = SearchEngine(populated, default_redactor(), AgentConfig(max_results_per_query=2))
    results = eng.search("quarterly")
    assert len(results) <= 2


def test_empty_query_returns_empty(populated):
    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    assert eng.search("") == []
    assert eng.search("   ") == []


def test_query_with_special_chars_doesnt_crash(populated):
    """FTS5 special characters in user input must be sanitized, not blow up."""
    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    results = eng.search('"quarterly" OR (something)')
    # We accept any result count; just must not raise.
    assert isinstance(results, list)


def test_scope_volume_filters(populated, conn, tmp_path: Path):
    """Index a second volume; scope_volume must isolate."""
    other = tmp_path / "other"
    other.mkdir()
    (other / "x.txt").write_text("quarterly elsewhere")
    idx = Indexer(
        conn,
        ExtractorRegistry(),
        Classifier(ClassificationConfig()),
        default_redactor(),
        ExtractorsConfig(),
    )
    idx.index_volume(other, "vol_other")

    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    only_test = eng.search("quarterly", scope_volume="vol_test")
    assert all(r.volume_id == "vol_test" for r in only_test)
    only_other = eng.search("quarterly", scope_volume="vol_other")
    assert all(r.volume_id == "vol_other" for r in only_other)


def test_file_type_filter(populated):
    eng = SearchEngine(populated, default_redactor(), AgentConfig())
    results = eng.search("quarterly", file_types=["txt"])
    assert all(r.file_type == "txt" for r in results)
