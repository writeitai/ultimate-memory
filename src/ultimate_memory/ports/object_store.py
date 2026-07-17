"""D61 byte/object-key seam for immutable raw inputs, artifacts, and snapshots."""

from typing import Protocol
from typing import runtime_checkable

from ultimate_memory.model import ObjectKey


@runtime_checkable
class ObjectStorePort(Protocol):
    """Read and create immutable objects without exposing storage-provider types."""

    def read_bytes(self, *, key: ObjectKey) -> bytes:
        """Read all bytes stored under an existing object key."""
        ...

    def write_bytes(self, *, key: ObjectKey, content: bytes) -> None:
        """Create immutable bytes, failing rather than replacing an occupied key."""
        ...
