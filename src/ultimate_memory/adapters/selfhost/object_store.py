"""Local-filesystem object store adapter: immutable bytes under one root (D61/D62)."""

from pathlib import Path

from ultimate_memory.model import ObjectKey


class ObjectKeyEscapesRootError(Exception):
    """An object key that would resolve outside the store root — refused."""


class ObjectAlreadyExistsError(Exception):
    """A write to an occupied key — objects are immutable, never replaced."""


class LocalFSObjectStore:
    """The self-host object store: one directory tree of immutable objects."""

    def __init__(self, *, root: Path) -> None:
        """Bind the store to its root directory, creating it if absent."""
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def read_bytes(self, *, key: ObjectKey) -> bytes:
        """Read all bytes stored under an existing object key."""
        return self._path_for(key=key).read_bytes()

    def write_bytes(self, *, key: ObjectKey, content: bytes) -> None:
        """Create immutable bytes, failing rather than replacing an occupied key."""
        path = self._path_for(key=key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open(mode="xb") as handle:
                handle.write(content)
        except FileExistsError as err:
            raise ObjectAlreadyExistsError(
                f"object key {key.root!r} is already occupied; objects are immutable"
            ) from err

    def _path_for(self, *, key: ObjectKey) -> Path:
        """Resolve a key to a path strictly inside the root (no traversal)."""
        candidate = (self._root / key.root).resolve()
        if not candidate.is_relative_to(self._root):
            raise ObjectKeyEscapesRootError(
                f"object key {key.root!r} escapes the store root"
            )
        return candidate
