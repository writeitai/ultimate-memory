"""The embedded-LanceDB P1 chunk index: one table of text + vectors (D8)."""

from pathlib import Path

import lancedb

from ultimate_memory.model import P1ChunkRow

_CHUNK_TABLE = "chunks"


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
        if _CHUNK_TABLE not in self._connection.table_names():
            self._connection.create_table(_CHUNK_TABLE, data=payload)
            return
        table = self._connection.open_table(_CHUNK_TABLE)
        (
            table.merge_insert("chunk_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(payload)
        )

    def row_count(self) -> int:
        """Total rows in the chunk table (0 before the first write)."""
        if _CHUNK_TABLE not in self._connection.table_names():
            return 0
        return self._connection.open_table(_CHUNK_TABLE).count_rows()
