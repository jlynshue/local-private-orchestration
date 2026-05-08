"""File-system crawler and indexer.

The indexer is the *write* path into the corpus. By design, it redacts
extracted content *before* writing to the FTS5 index. This means the index
DB never contains raw PII even if exfiltrated. Search-time redaction is then
a defense-in-depth safety net rather than the primary control.

Consent enforcement is the caller's responsibility (server handler), not the
indexer's. The indexer trusts the volume_path it's given.
"""
from __future__ import annotations

import fnmatch
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .classifier import Classifier
from .config import ExtractorsConfig
from .extractors import ExtractorRegistry
from .extractors.base import ExtractorError
from .redactor import PIIRedactor
from .types import FileEntry, IndexStats, utc_now_iso

logger = logging.getLogger(__name__)


class Indexer:
    def __init__(
        self,
        conn,
        registry: ExtractorRegistry,
        classifier: Classifier,
        redactor: PIIRedactor,
        cfg: ExtractorsConfig,
    ):
        self.conn = conn
        self.registry = registry
        self.classifier = classifier
        self.redactor = redactor
        self.cfg = cfg
        self._max_bytes = cfg.max_file_size_mb * 1024 * 1024

    # -- public API --

    def index_volume(
        self,
        volume_path: Path,
        volume_id: str,
        include_patterns: Optional[Iterable[str]] = None,
        exclude_patterns: Optional[Iterable[str]] = None,
        force_reindex: bool = False,
    ) -> IndexStats:
        if not volume_path.exists():
            raise FileNotFoundError(f"volume_path does not exist: {volume_path}")

        includes = tuple(include_patterns) if include_patterns else ()
        excludes = tuple(exclude_patterns) if exclude_patterns else ()

        total = 0
        indexed = 0
        failed = 0
        type_counts: dict[str, int] = {}
        total_bytes = 0

        for entry in self._walk(volume_path, volume_id, includes, excludes):
            total += 1
            try:
                if not force_reindex and self._already_indexed(entry):
                    continue
                self._index_one(entry)
                indexed += 1
                type_counts[entry.file_type] = type_counts.get(entry.file_type, 0) + 1
                total_bytes += entry.size_bytes
            except (ExtractorError, OSError) as e:
                failed += 1
                logger.warning("indexing failed for %s: %s", entry.relative_path, e)

        return IndexStats(
            total_files=total,
            indexed_files=indexed,
            failed_files=failed,
            last_indexed_at=utc_now_iso(),
            file_type_counts=type_counts,
            total_indexed_bytes=total_bytes,
        )

    # -- internals --

    def _walk(
        self,
        root: Path,
        volume_id: str,
        includes: tuple[str, ...],
        excludes: tuple[str, ...],
    ) -> Iterator[FileEntry]:
        root_str = str(root)
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                abs_path = Path(dirpath) / name
                rel = os.path.relpath(abs_path, root_str)

                if includes and not any(fnmatch.fnmatch(rel, p) for p in includes):
                    continue
                if any(fnmatch.fnmatch(rel, p) for p in excludes):
                    continue

                ext = abs_path.suffix.lower()
                if not self.registry.get(abs_path):
                    continue  # no extractor for this type

                try:
                    st = abs_path.stat()
                except OSError:
                    continue

                if st.st_size > self._max_bytes:
                    logger.debug("skip oversized file %s (%d bytes)", rel, st.st_size)
                    continue
                if st.st_size == 0:
                    continue

                yield FileEntry(
                    abs_path=str(abs_path),
                    volume_id=volume_id,
                    relative_path=rel,
                    size_bytes=st.st_size,
                    modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                    file_type=ext.lstrip(".") or "unknown",
                )

    def _already_indexed(self, entry: FileEntry) -> bool:
        cur = self.conn.execute(
            "SELECT modified_at FROM files WHERE abs_path = ?",
            (entry.abs_path,),
        )
        row = cur.fetchone()
        return row is not None and row["modified_at"] == entry.modified_at

    def _index_one(self, entry: FileEntry) -> None:
        path = Path(entry.abs_path)
        extractor = self.registry.get(path)
        if extractor is None:
            return  # filtered earlier; defensive

        content = extractor.extract(path)
        # Redact BEFORE storing — index never contains raw PII.
        scrubbed = self.redactor.scrub(content.text)
        title_scrubbed = self.redactor.scrub(content.title)

        classification = self.classifier.classify_path(entry.abs_path)
        indexed_at = utc_now_iso()

        self.conn.execute(
            "INSERT OR REPLACE INTO files (abs_path, volume_id, relative_path, "
            "title, file_type, size_bytes, modified_at, indexed_at, classification, "
            "pii_redactions_applied) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                entry.abs_path,
                entry.volume_id,
                entry.relative_path,
                title_scrubbed.text,
                entry.file_type,
                entry.size_bytes,
                entry.modified_at,
                indexed_at,
                classification,
                scrubbed.redactions_applied + title_scrubbed.redactions_applied,
            ),
        )
        # Drop any previous FTS rows for this path before re-inserting.
        self.conn.execute("DELETE FROM files_fts WHERE abs_path = ?", (entry.abs_path,))
        self.conn.execute(
            "INSERT INTO files_fts (abs_path, title, content, file_type, volume_id) "
            "VALUES (?,?,?,?,?)",
            (
                entry.abs_path,
                title_scrubbed.text,
                scrubbed.text,
                entry.file_type,
                entry.volume_id,
            ),
        )
        self.conn.commit()
