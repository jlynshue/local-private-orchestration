"""Tests for content extractors."""
from __future__ import annotations

from pathlib import Path

import pytest

from privacy_agent.extractors import (
    CsvExtractor,
    ExtractorRegistry,
    JsonExtractor,
    TextExtractor,
)


def test_text_extractor(fixture_text_file: Path):
    e = TextExtractor()
    out = e.extract(fixture_text_file)
    assert "Quarterly report" in out.text
    assert out.title == "sample"
    assert out.line_count >= 4


def test_text_extractor_max_chars(fixture_text_file: Path):
    e = TextExtractor()
    out = e.extract(fixture_text_file, max_chars=20)
    assert len(out.text) == 20


def test_text_excerpt_lines(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("line1\nline2\nline3\nline4\nline5\n")
    out = TextExtractor().extract_excerpt(p, start_line=2, end_line=4)
    assert out == "line2\nline3\nline4"


def test_json_extractor_flattens(tmp_path: Path):
    p = tmp_path / "obj.json"
    p.write_text('{"user": {"name": "Alice", "age": 30}, "active": true}')
    out = JsonExtractor().extract(p)
    assert "user.name: Alice" in out.text
    assert "user.age: 30" in out.text
    assert "active: True" in out.text


def test_jsonl_extractor(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    p.write_text('{"event": "click"}\n{"event": "scroll"}\n')
    out = JsonExtractor().extract(p)
    assert out.text.count("event:") == 2


def test_json_extractor_invalid_raises(tmp_path: Path):
    from privacy_agent.extractors.base import ExtractorError

    p = tmp_path / "bad.json"
    p.write_text("{not valid")
    with pytest.raises(ExtractorError):
        JsonExtractor().extract(p)


def test_csv_extractor_header_aware(tmp_path: Path):
    p = tmp_path / "data.csv"
    p.write_text("name,balance\nAlice,100\nBob,200\n")
    out = CsvExtractor().extract(p)
    assert "row2.name: Alice" in out.text
    assert "row2.balance: 100" in out.text
    assert "row3.balance: 200" in out.text


def test_csv_extractor_empty(tmp_path: Path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    out = CsvExtractor().extract(p)
    assert out.text == ""


def test_registry_dispatches_by_extension(tmp_path: Path):
    reg = ExtractorRegistry()
    txt = tmp_path / "a.txt"
    txt.write_text("x")
    js = tmp_path / "b.json"
    js.write_text("{}")
    csv_path = tmp_path / "c.csv"
    csv_path.write_text("a,b\n1,2\n")

    assert isinstance(reg.get(txt), TextExtractor)
    assert isinstance(reg.get(js), JsonExtractor)
    assert isinstance(reg.get(csv_path), CsvExtractor)


def test_registry_returns_none_for_unsupported(tmp_path: Path):
    reg = ExtractorRegistry()
    binary = tmp_path / "image.bin"
    binary.write_bytes(b"\x00\x01\x02")
    assert reg.get(binary) is None


def test_registry_register_custom():
    reg = ExtractorRegistry()
    reg.register(".myx", TextExtractor())
    assert reg.get(Path("/x/a.myx")) is not None
