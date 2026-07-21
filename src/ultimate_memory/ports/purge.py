"""D74 erasure capabilities of the already-selected serving stores."""

from typing import Protocol
from typing import runtime_checkable
from uuid import UUID

from ultimate_memory.model import ObjectKey


@runtime_checkable
class ObjectPurgePort(Protocol):
    """Idempotently erase manifest-nominated immutable objects."""

    def purge_objects(
        self, *, keys: tuple[ObjectKey, ...], prefixes: tuple[ObjectKey, ...]
    ) -> None:
        """Delete exact keys and every object below exact prefixes; absence succeeds."""
        ...


@runtime_checkable
class P1PurgePort(Protocol):
    """Idempotently erase manifest-nominated P1 rows by identity."""

    def purge_rows(
        self,
        *,
        deployment_id: UUID,
        chunk_ids: tuple[UUID, ...],
        claim_ids: tuple[UUID, ...],
        fact_ids: tuple[UUID, ...],
        entity_ids: tuple[UUID, ...],
    ) -> None:
        """Delete exact rows and compact affected P1 tables; absence succeeds."""
        ...


@runtime_checkable
class ProjectionPurgePort(Protocol):
    """Erase old P2/P3 durable prefixes and local serving copies."""

    def purge_projections(
        self, *, deployment_id: UUID, prefixes: tuple[ObjectKey, ...]
    ) -> None:
        """Delete every nominated projection copy; absence succeeds."""
        ...


@runtime_checkable
class KGitPurgePort(Protocol):
    """Erase affected Plane-K paths from all reachable Git history."""

    def purge_artifacts(
        self, *, deployment_id: UUID, forget_id: UUID, artifact_ids: tuple[UUID, ...]
    ) -> None:
        """Erase affected history and retain only already-sanitized current files."""
        ...
