"""Plain-text extractor — handles .txt, .md, .log, and similar."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..types import ExtractedContent
from .base import ExtractorError


class TextExtractor:
    EXTENSIONS = (
        ".txt", ".md", ".log", ".ini", ".cfg", ".yaml", ".yml",
        ".toml", ".xml", ".html", ".htm", ".rst", ".sh", ".py",
        ".js", ".ts", ".go", ".rs", ".java", ".sql",
    )

    def extract(self, path: Path, max_chars: Optional[int] = None) -> ExtractedContent:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise ExtractorError(f"failed to read {path}: {e}") from e

        if max_chars is not None and len(text) > max_chars:
            text = text[:max_chars]

        return ExtractedContent(
            text=text,
            title=path.stem,
            file_type=path.suffix.lstrip(".").lower() or "txt",
            line_count=text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        )

    def extract_excerpt(
        self,
        path: Path,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        page: Optional[int] = None,
        max_chars: int = 500,
    ) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if start_line is None and end_line is None:
            return text[:max_chars]
        s = (start_line or 1) - 1
        e = end_line if end_line is not None else len(lines)
        excerpt = "\n".join(lines[s:e])
        return excerpt[:max_chars]
