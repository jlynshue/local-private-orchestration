"""CSV / TSV extractor — header-aware row flattening."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from ..types import ExtractedContent
from .base import ExtractorError


class CsvExtractor:
    EXTENSIONS = (".csv", ".tsv")

    def extract(self, path: Path, max_chars: Optional[int] = None) -> ExtractedContent:
        try:
            with open(path, newline="", encoding="utf-8", errors="replace") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample)
                except csv.Error:
                    dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
                reader = csv.reader(f, dialect)
                rows = list(reader)
        except OSError as e:
            raise ExtractorError(f"failed to read {path}: {e}") from e

        if not rows:
            return ExtractedContent(text="", title=path.stem, file_type="csv", line_count=0)

        header = rows[0]
        flattened: list[str] = []
        for row_num, row in enumerate(rows[1:], start=2):
            for i, cell in enumerate(row):
                col = header[i] if i < len(header) else f"col{i}"
                flattened.append(f"row{row_num}.{col}: {cell}")

        text = "\n".join(flattened)
        if max_chars is not None and len(text) > max_chars:
            text = text[:max_chars]

        return ExtractedContent(
            text=text,
            title=path.stem,
            file_type="csv",
            line_count=len(rows),
        )

    def extract_excerpt(
        self,
        path: Path,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        page: Optional[int] = None,
        max_chars: int = 500,
    ) -> str:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            try:
                dialect = csv.Sniffer().sniff(f.read(4096))
                f.seek(0)
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            rows = list(reader)
        if not rows:
            return ""
        s = (start_line or 1) - 1
        e = end_line if end_line is not None else len(rows)
        excerpt = "\n".join(",".join(r) for r in rows[s:e])
        return excerpt[:max_chars]
