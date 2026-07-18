"""The E1 chunk catalog: chunk-row writes and stage loads (D56/D58 keys in PG).

Chunk text and vectors never land here (D37/D8): Postgres stores offsets,
section links, version stamps, and the reuse keys; bodies stay in the
artifacts store and vectors in the P1 index.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.model import ChunkForEmbedding
from ultimate_memory.model import ChunkRecord
from ultimate_memory.model import ChunkSource
from ultimate_memory.model import ChunkSourceNotFoundError
from ultimate_memory.model import EmbeddingUpdate


class ChunkCatalog:
    """E1 row writes and stage loads over an explicitly composed engine."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the catalog to the spine database."""
        self._engine = engine

    def chunk_source(self, *, representation_id: UUID) -> ChunkSource:
        """Load what the chunk stage needs about one representation."""
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    _SELECT_CHUNK_SOURCE, {"representation_id": representation_id}
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ChunkSourceNotFoundError(
                    f"document representation {representation_id} does not exist"
                )
            sections = (
                connection.execute(
                    _SELECT_SECTIONS, {"representation_id": representation_id}
                )
                .mappings()
                .all()
            )
        return ChunkSource.model_validate(
            {**dict(row), "sections": tuple(dict(section) for section in sections)}
        )

    def existing_chunk_ids(
        self, *, version_id: UUID, chunker_version: str
    ) -> tuple[UUID, ...]:
        """Chunks this chunker generation already packed for the version (D7 replay)."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                _SELECT_EXISTING_CHUNKS,
                {"version_id": version_id, "chunker_version": chunker_version},
            ).scalars()
            return tuple(rows)

    def record_chunks(self, *, records: tuple[ChunkRecord, ...]) -> None:
        """Insert one packing run's chunk rows in one transaction."""
        if not records:
            return
        with self._engine.begin() as connection:
            for record in records:
                connection.execute(_INSERT_CHUNK, record.model_dump(mode="json"))

    def chunks_for_embedding(
        self, *, version_id: UUID
    ) -> tuple[ChunkForEmbedding, ...]:
        """Load the version's chunk rows with their section signals."""
        with self._engine.connect() as connection:
            rows = (
                connection.execute(_SELECT_FOR_EMBEDDING, {"version_id": version_id})
                .mappings()
                .all()
            )
        return tuple(ChunkForEmbedding.model_validate(dict(row)) for row in rows)

    def record_embeddings(self, *, updates: tuple[EmbeddingUpdate, ...]) -> None:
        """Write the embed stage's refs, prefixes, and version stamps back."""
        if not updates:
            return
        with self._engine.begin() as connection:
            for update in updates:
                connection.execute(_UPDATE_EMBEDDING, update.model_dump(mode="json"))


_SELECT_CHUNK_SOURCE = text(
    """
    SELECT r.deployment_id, v.doc_id, r.version_id, r.representation_id,
           r.markdown_uri, r.blocks_uri, d.title, d.source_kind,
           v.source_modified_at, v.published_at, v.language,
           r.structurer_version
    FROM document_representations r
    JOIN document_versions v ON v.version_id = r.version_id
    JOIN documents d ON d.doc_id = v.doc_id
    WHERE r.representation_id = :representation_id
    """
)

_SELECT_SECTIONS = text(
    """
    SELECT section_id, node_path, role, block_start, block_end
    FROM document_sections
    WHERE representation_id = :representation_id
    ORDER BY node_path
    """
)

_SELECT_EXISTING_CHUNKS = text(
    """
    SELECT chunk_id FROM chunks
    WHERE version_id = :version_id AND chunker_version = :chunker_version
    ORDER BY ordinal
    """
)

_INSERT_CHUNK = text(
    """
    INSERT INTO chunks (
        chunk_id, deployment_id, doc_id, version_id, representation_id,
        section_id, ordinal, block_start, block_end, chunk_content_hash,
        extraction_input_hash, char_start, char_end, token_count,
        chunker_version
    ) VALUES (
        :chunk_id, :deployment_id, :doc_id, :version_id, :representation_id,
        :section_id, :ordinal, :block_start, :block_end, :chunk_content_hash,
        :extraction_input_hash, :char_start, :char_end, :token_count,
        :chunker_version
    )
    """
)

_SELECT_FOR_EMBEDDING = text(
    """
    SELECT c.chunk_id, c.doc_id, c.version_id, c.ordinal,
           c.char_start, c.char_end,
           s.role AS section_role, s.node_path AS section_path
    FROM chunks c
    JOIN document_sections s ON s.section_id = c.section_id
    WHERE c.version_id = :version_id
    ORDER BY c.ordinal
    """
)

_UPDATE_EMBEDDING = text(
    """
    UPDATE chunks
    SET embedding_ref = :embedding_ref,
        embedding_version = :embedding_version,
        context_prefix = :context_prefix,
        prefixer_version = :prefixer_version
    WHERE chunk_id = :chunk_id
    """
)
