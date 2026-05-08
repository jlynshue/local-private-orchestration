"""JSON / JSONL extractor — flattens to searchable key-value text."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Optional

from ..types import ExtractedContent
from .base import ExtractorError


class JsonExtractor:
    EXTENSIONS = (".json", ".jsonl")

    def extract(self, path: Path, max_chars: Optional[int] = None) -> ExtractedContent:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise ExtractorError(f"failed to read {path}: {e}") from e

        flattened: list[str] = []
        if path.suffix.lower() == ".jsonl":
            for i, line in enumerate(raw.splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    flattened.append(f"[line {i}] {line}")
                    continue
                flattened.extend(_flatten(obj))
        else:
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ExtractorError(f"invalid JSON in {path}: {e}") from e
            flattened.extend(_flatten(obj))

        text = "\n".join(flattened)
        if max_chars is not None and len(text) > max_chars:
            text = text[:max_chars]

        return ExtractedContent(
            text=text,
            title=path.stem,
            file_type="json",
            line_count=len(flattened),
        )

    def extract_excerpt(
        self,
        path: Path,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        page: Optional[int] = None,
        max_chars: int = 500,
    ) -> str:
        # For JSON, treat lines of the flattened representation.
        content = self.extract(path).text
        lines = content.splitlines()
        if start_line is None:
            return content[:max_chars]
        s = max(0, start_line - 1)
        e = end_line if end_line is not None else len(lines)
        return "\n".join(lines[s:e])[:max_chars]


def _flatten(obj: Any, prefix: str = "") -> Iterator[str]:
    """Yield ``key: value`` lines from arbitrarily nested JSON."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_prefix = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                yield from _flatten(v, new_prefix)
            else:
                yield f"{new_prefix}: {v}"
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_prefix = f"{prefix}[{i}]"
            if isinstance(item, (dict, list)):
                yield from _flatten(item, new_prefix)
            else:
                yield f"{new_prefix}: {item}"
    else:
        yield f"{prefix}: {obj}" if prefix else str(obj)
