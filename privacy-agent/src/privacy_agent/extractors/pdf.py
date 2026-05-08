"""PDF extractor via pymupdf. Optional dependency."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import fitz  # type: ignore[import-not-found]  # pymupdf

from ..types import ExtractedContent
from .base import ExtractorError


class PdfExtractor:
    EXTENSIONS = (".pdf",)

    def extract(self, path: Path, max_chars: Optional[int] = None) -> ExtractedContent:
        try:
            doc = fitz.open(str(path))
        except Exception as e:  # pymupdf raises various exceptions
            raise ExtractorError(f"failed to open PDF {path}: {e}") from e

        try:
            pages: list[str] = []
            for page in doc:
                try:
                    pages.append(page.get_text("text"))
                except Exception as e:  # pragma: no cover
                    pages.append(f"[page-extract-error: {e}]")
            text = "\n".join(pages)
            page_count = doc.page_count
        finally:
            doc.close()

        if max_chars is not None and len(text) > max_chars:
            text = text[:max_chars]

        return ExtractedContent(
            text=text,
            title=path.stem,
            file_type="pdf",
            page_count=page_count,
        )

    def extract_excerpt(
        self,
        path: Path,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        page: Optional[int] = None,
        max_chars: int = 500,
    ) -> str:
        doc = fitz.open(str(path))
        try:
            if page is not None:
                p = doc[page - 1] if 1 <= page <= doc.page_count else None
                if p is None:
                    return ""
                return p.get_text("text")[:max_chars]
            return doc[0].get_text("text")[:max_chars]
        finally:
            doc.close()
