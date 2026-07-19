"""The local-directory watched source: watch a folder on the self-host tier.

The genuinely useful self-host connector (and the lifecycle machinery's test
double with real semantics): source_ref = the file's relative path, revision
= mtime+size, deletion = the file is gone. Cloud connectors (Drive) implement
the same port behind their provider adapters.
"""

from collections.abc import Mapping
from datetime import datetime
from datetime import UTC
from pathlib import Path

from ultimate_memory.model import SourceItem

_MIME_BY_SUFFIX = {".md": "text/markdown", ".txt": "text/plain", ".html": "text/html"}


class LocalDirectoryWatcher:
    """Watch one directory tree of text documents."""

    def __init__(self, *, root: Path) -> None:
        """Bind the watcher to its directory (created if absent)."""
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def poll(self, *, known: Mapping[str, str]) -> tuple[SourceItem, ...]:
        """Every current file, plus deletion markers for vanished refs."""
        items: list[SourceItem] = []
        seen: set[str] = set()
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.suffix not in _MIME_BY_SUFFIX:
                continue
            ref = path.relative_to(self._root).as_posix()
            seen.add(ref)
            stat = path.stat()
            items.append(
                SourceItem(
                    source_ref=ref,
                    revision=f"{stat.st_mtime_ns}:{stat.st_size}",
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                    filename=path.name,
                    mime=_MIME_BY_SUFFIX[path.suffix],
                )
            )
        for ref in sorted(set(known) - seen):
            items.append(
                SourceItem(
                    source_ref=ref,
                    revision="deleted",
                    modified_at=datetime.now(tz=UTC),
                    deleted=True,
                )
            )
        return tuple(items)

    def fetch(self, *, source_ref: str) -> bytes:
        """The file's current bytes."""
        return (self._root / source_ref).read_bytes()
