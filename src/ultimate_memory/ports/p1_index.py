"""D61 seam for the P1 chunk index: text + vectors + filter scalars (D8)."""

from typing import Protocol
from typing import runtime_checkable

from ultimate_memory.model import P1ChunkRow


@runtime_checkable
class ChunkIndexPort(Protocol):
    """Write the P1 chunk table without exposing vector-store types."""

    def upsert_chunks(self, *, rows: tuple[P1ChunkRow, ...]) -> None:
        """Insert or replace rows by chunk_id; re-runs are idempotent."""
        ...
