"""D61 seam for the P1 search indexes: chunks, claims, facts (D8)."""

from typing import Protocol
from typing import runtime_checkable

from ultimate_memory.model import P1ChunkRow
from ultimate_memory.model import P1ClaimRow
from ultimate_memory.model import P1FactRow


@runtime_checkable
class ChunkIndexPort(Protocol):
    """Write the P1 chunk table without exposing vector-store types."""

    def upsert_chunks(self, *, rows: tuple[P1ChunkRow, ...]) -> None:
        """Insert or replace rows by chunk_id; re-runs are idempotent."""
        ...


@runtime_checkable
class ClaimIndexPort(Protocol):
    """Write the P1 claims channel — the needle index (D58)."""

    def upsert_claims(self, *, rows: tuple[P1ClaimRow, ...]) -> None:
        """Insert or replace rows by claim_id; re-runs are idempotent."""
        ...


@runtime_checkable
class FactIndexPort(Protocol):
    """Write the P1 facts channel — relation/observation labels (D8)."""

    def upsert_facts(self, *, rows: tuple[P1FactRow, ...]) -> None:
        """Insert or replace rows by fact_id; re-runs are idempotent."""
        ...
