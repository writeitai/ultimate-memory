"""The P2 projection catalog (D7/D44): snapshot registry + the export reads.

Spine-owned SQL for the rebuild-first graph pipeline (p2 §5). The
`projection_snapshots` registry is the pointer readers follow (`is_latest`,
one per deployment/plane — the object store holds only immutable snapshot
bytes, never a mutable pointer). The export executes the spike battery's
bound strategy: the survivor map materializes ONCE into an indexed temp
table per export connection, and every edge read joins against it — the
`v_graph_*` views remain the semantic contract, the catalog owns the
execution shape (`plan/analysis/p2_spike_battery.md`, finding 2).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final
from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy import TextClause
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine
from sqlalchemy.engine import Row

GRAPH_NODE_TABLES: Final = ("Entity", "Document")
GRAPH_REL_TABLES: Final = ("RELATES", "MENTIONED_IN", "DOC_CROSSREF", "IS_DOCUMENT")
"""Load order is binding: every node table before any rel table (COPY-REL
resolves endpoints against node PKs and throws on a missing endpoint)."""


class GraphExport:
    """One export pass over a single connection with the survivor map ready."""

    def __init__(self, *, connection: Connection) -> None:
        """Bind to the export connection (the temp survivor table exists)."""
        self._connection = connection

    def rows(self, *, table: str) -> Iterator[Row]:
        """Stream one graph table's rows (server-side cursor)."""
        statement = _EXPORT_SQL[table]
        return iter(
            self._connection.execution_options(yield_per=10_000).execute(statement)
        )

    def count(self, *, table: str) -> int:
        """The export-side row count (the validation gate's expectation)."""
        statement = _EXPORT_SQL[table]
        return int(
            self._connection.execute(
                text(f"SELECT count(*) FROM ({statement.text}) export")  # noqa: S608
            ).scalar_one()
        )

    def unresolved_survivors(self) -> tuple[UUID, ...]:
        """The abort-before-snapshot gate (spike c): entities whose survivor
        is still merged — a merge cycle or a corrupt redirect chain. Any row
        aborts the snapshot; the offenders are recorded for the operator."""
        return tuple(self._connection.execute(_SELECT_UNRESOLVED_SURVIVORS).scalars())


class ProjectionCatalog:
    """Snapshot registry rows and the graph export reads."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the catalog to the spine database."""
        self._engine = engine

    @contextmanager
    def graph_export(self) -> Iterator[GraphExport]:
        """One consistent export pass (single transaction, survivor map once).

        Everything the snapshot reads happens inside one REPEATABLE READ
        transaction — the snapshot is a consistent cut of Postgres, and the
        indexed temp survivor table keeps every edge join linear.
        """
        with self._engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            connection.execute(_CREATE_SURVIVOR_MAP)
            connection.execute(_INDEX_SURVIVOR_MAP)
            try:
                yield GraphExport(connection=connection)
            finally:
                connection.rollback()  # temp table + snapshot cut end together

    def open_snapshot(
        self, *, deployment_id: UUID, plane: str, version: str, store_prefix: str
    ) -> UUID:
        """Register one building snapshot."""
        snapshot_id = uuid4()
        with self._engine.begin() as connection:
            connection.execute(
                _INSERT_SNAPSHOT,
                {
                    "snapshot_id": snapshot_id,
                    "deployment_id": deployment_id,
                    "plane": plane,
                    "version": version,
                    "gcs_uri": store_prefix,
                },
            )
        return snapshot_id

    def mark_failed(self, *, snapshot_id: UUID, validation: dict[str, object]) -> None:
        """Record an aborted snapshot with its validation report (loudly)."""
        with self._engine.begin() as connection:
            connection.execute(
                _MARK_FAILED, {"snapshot_id": snapshot_id, "validation": validation}
            )

    def publish(
        self,
        *,
        deployment_id: UUID,
        snapshot_id: UUID,
        plane: str,
        row_counts: dict[str, int],
        validation: dict[str, object],
        built_from_watermark: object,
    ) -> None:
        """Validation passed: publish and swap the latest pointer atomically."""
        with self._engine.begin() as connection:
            connection.execute(
                _CLEAR_LATEST, {"deployment_id": deployment_id, "plane": plane}
            )
            connection.execute(
                _PUBLISH_SNAPSHOT,
                {
                    "snapshot_id": snapshot_id,
                    "row_counts": row_counts,
                    "validation": validation,
                    "built_from_watermark": built_from_watermark,
                },
            )

    def latest_snapshot(
        self, *, deployment_id: UUID, plane: str
    ) -> dict[str, object] | None:
        """The published snapshot readers should serve, if any."""
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    _SELECT_LATEST, {"deployment_id": deployment_id, "plane": plane}
                )
                .mappings()
                .one_or_none()
            )
        return dict(row) if row is not None else None

    def ingestion_watermark(self) -> object:
        """The max ingested_at the snapshot covers (staleness bound, D7)."""
        with self._engine.connect() as connection:
            return connection.execute(_SELECT_WATERMARK).scalar_one_or_none()


_CREATE_SURVIVOR_MAP = text(
    """
    CREATE TEMP TABLE graph_survivor ON COMMIT DROP AS
    SELECT * FROM v_graph_survivor
    """
)

_INDEX_SURVIVOR_MAP = text("CREATE INDEX ON graph_survivor (entity_id)")

_EXPORT_SQL: Final[dict[str, TextClause]] = {
    "Entity": text(
        """
        SELECT id, type, name, normalized_name, summary, created_at
        FROM v_graph_entities
        """
    ),
    "Document": text(
        """
        SELECT id, title, source_uri, published_at FROM v_graph_documents
        """
    ),
    "RELATES": text(
        """
        SELECT s1.survivor AS from_id, s2.survivor AS to_id,
               r.relation_id, r.predicate, r.fact_label AS fact,
               r.evidence_count::bigint AS evidence_count,
               r.contradict_count::bigint AS contradict_count,
               r.confidence::float8 AS confidence, r.contradiction_group,
               (r.valid_from AT TIME ZONE 'UTC') AS valid_from,
               (r.valid_until AT TIME ZONE 'UTC') AS valid_until,
               (r.ingested_at AT TIME ZONE 'UTC') AS ingested_at,
               (r.invalidated_at AT TIME ZONE 'UTC') AS invalidated_at
        FROM relations r
        JOIN graph_survivor s1 ON s1.entity_id = r.subject_entity_id
        JOIN graph_survivor s2 ON s2.entity_id = r.object_entity_id
        JOIN entities e1 ON e1.entity_id = s1.survivor AND e1.status = 'active'
        JOIN entities e2 ON e2.entity_id = s2.survivor AND e2.status = 'active'
        """
    ),
    "MENTIONED_IN": text(
        """
        SELECT s.survivor AS from_id, m.doc_id AS to_id,
               COUNT(*)::bigint AS mention_count,
               (MIN(m.created_at) AT TIME ZONE 'UTC') AS first_seen
        FROM mentions m
        JOIN resolution_decisions rd
          ON rd.mention_id = m.mention_id AND rd.superseded_by IS NULL
        JOIN graph_survivor s ON s.entity_id = rd.entity_id
        JOIN entities e ON e.entity_id = s.survivor AND e.status = 'active'
        WHERE EXISTS (SELECT 1 FROM documents d
                      WHERE d.doc_id = m.doc_id AND d.deleted_at IS NULL)
        GROUP BY s.survivor, m.doc_id
        """
    ),
    "DOC_CROSSREF": text(
        """
        SELECT "from" AS from_id, "to" AS to_id, kind, context
        FROM v_graph_crossref
        """
    ),
    "IS_DOCUMENT": text(
        """
        SELECT s.survivor AS from_id, d.doc_id AS to_id
        FROM documents d
        JOIN graph_survivor s ON s.entity_id = d.document_entity_id
        JOIN entities e ON e.entity_id = s.survivor AND e.status = 'active'
        WHERE d.document_entity_id IS NOT NULL AND d.deleted_at IS NULL
        """
    ),
}

_SELECT_UNRESOLVED_SURVIVORS = text(
    """
    SELECT s.entity_id FROM graph_survivor s
    JOIN entities e ON e.entity_id = s.survivor
    WHERE e.merged_into IS NOT NULL
    """
)

_INSERT_SNAPSHOT = text(
    """
    INSERT INTO projection_snapshots (
        snapshot_id, deployment_id, plane, version, gcs_uri, status
    ) VALUES (
        :snapshot_id, :deployment_id, CAST(:plane AS projection_plane),
        :version, :gcs_uri, 'building'
    )
    """
)

_MARK_FAILED = text(
    """
    UPDATE projection_snapshots
    SET status = 'failed', validation = :validation
    WHERE snapshot_id = :snapshot_id
    """
).bindparams(bindparam("validation", type_=JSON))

_CLEAR_LATEST = text(
    """
    UPDATE projection_snapshots
    SET is_latest = false, status = 'superseded'
    WHERE deployment_id = :deployment_id
      AND plane = CAST(:plane AS projection_plane)
      AND is_latest
    """
)

_PUBLISH_SNAPSHOT = text(
    """
    UPDATE projection_snapshots
    SET status = 'published', is_latest = true, row_counts = :row_counts,
        validation = :validation, built_from_watermark = :built_from_watermark,
        published_at = now()
    WHERE snapshot_id = :snapshot_id
    """
).bindparams(bindparam("row_counts", type_=JSON), bindparam("validation", type_=JSON))

_SELECT_LATEST = text(
    """
    SELECT snapshot_id, version, gcs_uri, row_counts, built_at, published_at
    FROM projection_snapshots
    WHERE deployment_id = :deployment_id
      AND plane = CAST(:plane AS projection_plane)
      AND is_latest
    """
)

_SELECT_WATERMARK = text(
    """
    SELECT max(ingested_at) FROM relations
    """
)
