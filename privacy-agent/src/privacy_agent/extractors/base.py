"""Extractor protocol and exceptions."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol

from ..types import ExtractedContent


class ExtractorError(Exception):
    """Raised when extraction fails for a non-system reason (corrupt file, bad encoding)."""


class Extractor(Protocol):
    """All extractors implement this interface."""

    EXTENSIONS: tuple[str, ...]

    def extract(self, path: Path, max_chars: Optional[int] = None) -> ExtractedContent:
        """Read and return the file's textual content. Raises ExtractorError on failure."""
        ...

    def extract_excerpt(
        self,
        path: Path,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        page: Optional[int] = None,
        max_chars: int = 500,
    ) -> str:
        """Return a specific portion of the file."""
        ...
