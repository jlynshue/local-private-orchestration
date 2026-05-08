"""Content extractor registry.

The registry dispatches by file extension. Phase 1 ships text/PDF/DOCX/JSON/CSV.
Heavy dependencies (pymupdf, python-docx) are optional — if not installed, the
corresponding extractor is registered but raises a helpful error on use.

OCR for scanned PDFs and images is Phase 3 territory (config.extractors.image_ocr_enabled).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Extractor, ExtractorError
from .text import TextExtractor
from .json_extractor import JsonExtractor
from .csv_extractor import CsvExtractor

# Optional extractors — wrapped in try/except so missing deps don't break import.
try:
    from .pdf import PdfExtractor

    _HAS_PDF = True
except ImportError:  # pragma: no cover
    _HAS_PDF = False

try:
    from .docx import DocxExtractor

    _HAS_DOCX = True
except ImportError:  # pragma: no cover
    _HAS_DOCX = False


class ExtractorRegistry:
    def __init__(self):
        self._by_ext: dict[str, Extractor] = {}
        # Register defaults
        text = TextExtractor()
        for ext in TextExtractor.EXTENSIONS:
            self._by_ext[ext] = text
        self._by_ext[".json"] = JsonExtractor()
        self._by_ext[".jsonl"] = JsonExtractor()
        self._by_ext[".csv"] = CsvExtractor()
        self._by_ext[".tsv"] = CsvExtractor()
        if _HAS_PDF:
            self._by_ext[".pdf"] = PdfExtractor()
        if _HAS_DOCX:
            self._by_ext[".docx"] = DocxExtractor()

    def register(self, extension: str, extractor: Extractor) -> None:
        self._by_ext[extension.lower()] = extractor

    def get(self, path: Path) -> Optional[Extractor]:
        return self._by_ext.get(path.suffix.lower())

    def supported_extensions(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_ext))


__all__ = [
    "Extractor",
    "ExtractorError",
    "ExtractorRegistry",
    "TextExtractor",
    "JsonExtractor",
    "CsvExtractor",
]
