"""The embedded-LanceDB P1 chunk index: one table of text + vectors (D8)."""

from datetime import timedelta
import math
from pathlib import Path
from typing import cast
from typing import Final
from uuid import UUID

import lancedb
from lancedb.index import Bitmap
from lancedb.index import BTree
from lancedb.index import IvfFlat
from lancedb.query import LanceVectorQueryBuilder
from lancedb.table import Table

from ultimate_memory.model import P1ChunkRow
from ultimate_memory.model import P1ClaimRow
from ultimate_memory.model import P1EntityRow
from ultimate_memory.model import P1FactRow

_CHUNK_TABLE = "chunks"
_CLAIM_TABLE = "claims"
_FACT_TABLE = "facts"
_ENTITY_TABLE = "entities"

LANCE_TARGET_PARTITION_ROWS: Final = 8_192
"""WP-5.6 IVF_FLAT target: one vector partition per roughly 8k rows."""

LANCE_NPROBES: Final = 20
"""WP-5.6 query probe count for filtered ANN reads."""

_MIN_VECTOR_INDEX_ROWS: Final = 256


class LanceChunkIndex:
    """The self-host P1 chunk table in an embedded Lance dataset directory."""

    def __init__(self, *, root: Path) -> None:
        """Bind the index to its dataset directory, creating it if absent."""
        self._connection = lancedb.connect(str(root))

    def upsert_chunks(self, *, rows: tuple[P1ChunkRow, ...]) -> None:
        """Insert or replace rows by chunk_id; re-runs are idempotent."""
        if not rows:
            return
        payload = [
            {
                "chunk_id": str(row.chunk_id),
                "deployment_id": str(row.deployment_id),
                "doc_id": str(row.doc_id),
                "version_id": str(row.version_id),
                "section_role": row.section_role,
                "text": row.text,
                "vector": list(row.vector),
            }
            for row in rows
        ]
        self._upsert(table=_CHUNK_TABLE, key="chunk_id", payload=payload)

    def chunk_vectors(
        self, *, deployment_id: str, chunk_ids: tuple[str, ...]
    ) -> dict[str, tuple[float, ...]]:
        """Stored vectors for the requested ids (absent ids are omitted)."""
        deployment_id = str(UUID(deployment_id))
        if not chunk_ids or _CHUNK_TABLE not in self._connection.table_names():
            return {}
        ids = ", ".join(f"'{UUID(item)}'" for item in chunk_ids)
        rows = (
            self._connection.open_table(_CHUNK_TABLE)
            .search()
            .where(f"deployment_id = '{deployment_id}' AND chunk_id IN ({ids})")
            .limit(len(chunk_ids))
            .to_list()
        )
        return {row["chunk_id"]: tuple(row["vector"]) for row in rows}

    def upsert_claims(self, *, rows: tuple[P1ClaimRow, ...]) -> None:
        """Insert or replace claims-channel rows by claim_id; idempotent."""
        self._upsert(
            table=_CLAIM_TABLE,
            key="claim_id",
            payload=[
                {
                    "claim_id": str(row.claim_id),
                    "deployment_id": str(row.deployment_id),
                    "doc_id": str(row.doc_id),
                    "chunk_id": str(row.chunk_id),
                    "text": row.text,
                    "is_current_testimony": row.is_current_testimony,
                    "is_attributed": row.is_attributed,
                    "vector": list(row.vector),
                }
                for row in rows
            ],
        )

    def upsert_facts(self, *, rows: tuple[P1FactRow, ...]) -> None:
        """Insert or replace facts-channel rows by fact_id; idempotent."""
        self._upsert(
            table=_FACT_TABLE,
            key="fact_id",
            payload=[
                {
                    "fact_id": str(row.fact_id),
                    "deployment_id": str(row.deployment_id),
                    "kind": row.kind,
                    "label": row.label,
                    "status": row.status,
                    "vector": list(row.vector),
                }
                for row in rows
            ],
        )

    def search_claims(
        self,
        *,
        deployment_id: str,
        vector: tuple[float, ...],
        k: int,
        current_only: bool,
    ) -> tuple[str, ...]:
        """Nominate claim ids by vector similarity (D48: nomination, not truth).

        The DEFAULT claims channel filters to current testimony via the
        stored scalar (retrieval §5); hydration against the spine confirms.
        """
        deployment_id = str(UUID(deployment_id))  # refuse filter injection
        if _CLAIM_TABLE not in self._connection.table_names():
            return ()
        query = (
            cast(
                "LanceVectorQueryBuilder",
                self._connection.open_table(_CLAIM_TABLE)
                .search(list(vector))
                .where(
                    f"deployment_id = '{deployment_id}'"
                    + (" AND is_current_testimony" if current_only else ""),
                    prefilter=True,
                ),
            )
            .nprobes(LANCE_NPROBES)
            .limit(k)
        )
        return tuple(row["claim_id"] for row in query.to_list())

    def search_facts(
        self, *, deployment_id: str, vector: tuple[float, ...], k: int, kind: str | None
    ) -> tuple[str, ...]:
        """Nominate fact ids (relations/observations) by label similarity."""
        deployment_id = str(UUID(deployment_id))  # refuse filter injection
        if kind is not None and kind not in ("relation", "observation"):
            raise ValueError(f"unknown facts-channel kind {kind!r}")
        if _FACT_TABLE not in self._connection.table_names():
            return ()
        where = f"deployment_id = '{deployment_id}'"
        if kind is not None:
            where += f" AND kind = '{kind}'"
        query = (
            cast(
                "LanceVectorQueryBuilder",
                self._connection.open_table(_FACT_TABLE)
                .search(list(vector))
                .where(where, prefilter=True),
            )
            .nprobes(LANCE_NPROBES)
            .limit(k)
        )
        return tuple(row["fact_id"] for row in query.to_list())

    def build_search_indexes(self) -> None:
        """Build the measured scalar + IVF_FLAT indexes after a bulk load.

        This is explicit rather than hidden in every upsert: index construction
        is a maintenance/backfill operation, while inline P1 writes must stay
        cheap. Lance still searches unindexed tail fragments after the build.
        """
        available = set(self._connection.list_tables().tables or ())
        if _CLAIM_TABLE in available:
            claims = self._connection.open_table(_CLAIM_TABLE)
            claims.create_index("deployment_id", config=BTree())
            claims.create_index("is_current_testimony", config=Bitmap())
            self._build_vector_index(table=claims)
        if _FACT_TABLE in available:
            facts = self._connection.open_table(_FACT_TABLE)
            facts.create_index("deployment_id", config=BTree())
            facts.create_index("kind", config=Bitmap())
            self._build_vector_index(table=facts)

    @staticmethod
    def _build_vector_index(*, table: Table) -> None:
        """Build one vector index when the table is large enough to train it."""
        rows = table.count_rows()
        if rows < _MIN_VECTOR_INDEX_ROWS:
            return
        table.create_index(
            "vector",
            config=IvfFlat(
                distance_type="l2",
                num_partitions=max(1, math.ceil(rows / LANCE_TARGET_PARTITION_ROWS)),
                target_partition_size=LANCE_TARGET_PARTITION_ROWS,
            ),
        )

    def upsert_entities(self, *, rows: tuple[P1EntityRow, ...]) -> None:
        """Insert or replace entity-profile rows by entity_id; idempotent."""
        self._upsert(
            table=_ENTITY_TABLE,
            key="entity_id",
            payload=[
                {
                    "entity_id": str(row.entity_id),
                    "deployment_id": str(row.deployment_id),
                    "type": row.type,
                    "canonical_name": row.canonical_name,
                    "vector": list(row.vector),
                }
                for row in rows
            ],
        )

    def entity_vectors(
        self, *, deployment_id: str, entity_ids: tuple[str, ...]
    ) -> dict[str, tuple[float, ...]]:
        """Profile vectors for the requested ids (absent ids are omitted)."""
        deployment_id = str(UUID(deployment_id))
        if not entity_ids or _ENTITY_TABLE not in self._connection.table_names():
            return {}
        ids = ", ".join(f"'{UUID(item)}'" for item in entity_ids)
        rows = (
            self._connection.open_table(_ENTITY_TABLE)
            .search()
            .where(f"deployment_id = '{deployment_id}' AND entity_id IN ({ids})")
            .limit(len(entity_ids))
            .to_list()
        )
        return {row["entity_id"]: tuple(row["vector"]) for row in rows}

    def purge_rows(
        self,
        *,
        deployment_id: UUID,
        chunk_ids: tuple[UUID, ...],
        claim_ids: tuple[UUID, ...],
        fact_ids: tuple[UUID, ...],
        entity_ids: tuple[UUID, ...],
    ) -> None:
        """Delete exact deployment-owned rows and prune obsolete Lance versions."""
        for table, key, ids in (
            (_CHUNK_TABLE, "chunk_id", chunk_ids),
            (_CLAIM_TABLE, "claim_id", claim_ids),
            (_FACT_TABLE, "fact_id", fact_ids),
            (_ENTITY_TABLE, "entity_id", entity_ids),
        ):
            self._purge_table_rows(
                table=table, key=key, deployment_id=deployment_id, ids=ids
            )

    def table_count(self, *, table: str) -> int:
        """Total rows in one P1 table (0 before its first write)."""
        if table not in self._connection.table_names():
            return 0
        return self._connection.open_table(table).count_rows()

    def _upsert(
        self, *, table: str, key: str, payload: list[dict[str, object]]
    ) -> None:
        """Create-or-merge one table's rows by its key column."""
        if not payload:
            return
        if table not in self._connection.table_names():
            self._connection.create_table(table, data=payload)
            return
        (
            self._connection.open_table(table)
            .merge_insert(key)
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(payload)
        )

    def _purge_table_rows(
        self, *, table: str, key: str, deployment_id: UUID, ids: tuple[UUID, ...]
    ) -> None:
        """Delete one exact UUID set and physically prune its obsolete versions."""
        if not ids or table not in self._connection.table_names():
            return
        rendered_ids = ", ".join(f"'{item}'" for item in ids)
        lance_table = self._connection.open_table(table)
        lance_table.delete(
            f"deployment_id = '{deployment_id}' AND {key} IN ({rendered_ids})"
        )
        lance_table.optimize(cleanup_older_than=timedelta(0), delete_unverified=True)

    def row_count(self) -> int:
        """Total rows in the chunk table (0 before the first write)."""
        if _CHUNK_TABLE not in self._connection.table_names():
            return 0
        return self._connection.open_table(_CHUNK_TABLE).count_rows()
