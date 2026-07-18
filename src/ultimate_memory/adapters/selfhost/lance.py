"""The embedded-LanceDB P1 chunk index: one table of text + vectors (D8)."""

from pathlib import Path

import lancedb

from ultimate_memory.model import P1ChunkRow
from ultimate_memory.model import P1ClaimRow
from ultimate_memory.model import P1FactRow

_CHUNK_TABLE = "chunks"
_CLAIM_TABLE = "claims"
_FACT_TABLE = "facts"


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
        if _CLAIM_TABLE not in self._connection.table_names():
            return ()
        query = (
            self._connection.open_table(_CLAIM_TABLE)
            .search(list(vector))
            .where(
                f"deployment_id = '{deployment_id}'"
                + (" AND is_current_testimony" if current_only else "")
            )
            .limit(k)
        )
        return tuple(row["claim_id"] for row in query.to_list())

    def search_facts(
        self, *, deployment_id: str, vector: tuple[float, ...], k: int, kind: str | None
    ) -> tuple[str, ...]:
        """Nominate fact ids (relations/observations) by label similarity."""
        if _FACT_TABLE not in self._connection.table_names():
            return ()
        where = f"deployment_id = '{deployment_id}'"
        if kind is not None:
            where += f" AND kind = '{kind}'"
        query = (
            self._connection.open_table(_FACT_TABLE)
            .search(list(vector))
            .where(where)
            .limit(k)
        )
        return tuple(row["fact_id"] for row in query.to_list())

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

    def row_count(self) -> int:
        """Total rows in the chunk table (0 before the first write)."""
        if _CHUNK_TABLE not in self._connection.table_names():
            return 0
        return self._connection.open_table(_CHUNK_TABLE).count_rows()
