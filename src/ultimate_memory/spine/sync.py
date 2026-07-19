"""Sync-cycle catalog (lifecycle §2/§5, F8): the poll pass as explicit state.

One `connector_sync_cycles` row per pass, every ingested version stamped with
its cycle — the retract-timing barrier reconciliation reads. `completed_at`
is the poll pass ending; `finalized_at` belongs to the reconciliation
finalization job.
"""

from uuid import UUID
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine


class SyncCatalog:
    """Cycle rows, known revisions, and deletion tombstones."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the catalog to the spine database."""
        self._engine = engine

    def open_cycle(self, *, deployment_id: UUID, source_kind: str) -> UUID:
        """Record the start of one poll pass."""
        cycle_id = uuid4()
        with self._engine.begin() as connection:
            connection.execute(
                _OPEN_CYCLE,
                {
                    "cycle_id": cycle_id,
                    "deployment_id": deployment_id,
                    "source_kind": source_kind,
                },
            )
        return cycle_id

    def complete_cycle(self, *, cycle_id: UUID, observed: int) -> None:
        """The poll pass ended (finalization is reconciliation's job)."""
        with self._engine.begin() as connection:
            connection.execute(
                _COMPLETE_CYCLE, {"cycle_id": cycle_id, "observed": observed}
            )

    def known_revisions(
        self, *, deployment_id: UUID, source_kind: str
    ) -> dict[str, str]:
        """Each live lineage's last ingested revision (the no-fetch key)."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                _KNOWN_REVISIONS,
                {"deployment_id": deployment_id, "source_kind": source_kind},
            ).all()
        return {source_ref: revision or "" for source_ref, revision in rows}

    def observe_deletion(
        self, *, deployment_id: UUID, source_kind: str, source_ref: str
    ) -> UUID | None:
        """Tombstone a source-deleted lineage (loud, recorded, idempotent).

        The downstream cascade (claims currency, fact closure per mode,
        artifact removal) is the delete worker's job.
        """
        with self._engine.begin() as connection:
            return connection.execute(
                _TOMBSTONE_LINEAGE,
                {
                    "deployment_id": deployment_id,
                    "source_kind": source_kind,
                    "source_ref": source_ref,
                },
            ).scalar_one_or_none()


_OPEN_CYCLE = text(
    """
    INSERT INTO connector_sync_cycles (cycle_id, deployment_id, source_kind)
    VALUES (:cycle_id, :deployment_id, :source_kind)
    """
)

_COMPLETE_CYCLE = text(
    """
    UPDATE connector_sync_cycles
    SET completed_at = now(), observed_lineages = :observed
    WHERE cycle_id = :cycle_id
    """
)

_KNOWN_REVISIONS = text(
    """
    SELECT d.source_ref, v.source_version_ref
    FROM documents d
    LEFT JOIN document_versions v ON v.version_id = d.current_version_id
    WHERE d.deployment_id = :deployment_id
      AND d.source_kind = :source_kind
      AND d.deleted_at IS NULL
      AND d.source_ref IS NOT NULL
    """
)

_TOMBSTONE_LINEAGE = text(
    """
    UPDATE documents SET deleted_at = now()
    WHERE deployment_id = :deployment_id
      AND source_kind = :source_kind
      AND source_ref = :source_ref
      AND deleted_at IS NULL
    RETURNING doc_id
    """
)
