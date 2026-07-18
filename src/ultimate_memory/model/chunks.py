"""E1 chunk-layer values: packing inputs/outputs, catalog records, P1 rows (D58).

Chunks are non-overlapping runs of whole blocks within one section; their
identity is the ordered block-hash sequence, which is what makes reuse (D56)
a sequence comparison instead of a semantic judgment.
"""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from ultimate_memory.model.queue import UTCDateTime

_NonEmpty = Annotated[str, Field(min_length=1)]


class SectionSpan(BaseModel):
    """One section's block range and signals, as the chunker consumes it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: UUID
    node_path: str
    role: str
    block_start: int = Field(ge=0)
    block_end: int = Field(ge=-1)


class ChunkSource(BaseModel):
    """Everything the chunk stage loads about its claimed representation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    doc_id: UUID
    version_id: UUID
    representation_id: UUID
    markdown_uri: str
    blocks_uri: str
    title: str | None
    source_kind: str
    source_modified_at: UTCDateTime | None
    published_at: UTCDateTime | None
    language: str | None
    structurer_version: str
    sections: tuple[SectionSpan, ...]


class PackedChunk(BaseModel):
    """One packed run of whole blocks: the chunker's pure output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int = Field(ge=0)
    section_id: UUID
    block_start: int = Field(ge=0)
    block_end: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    chunk_content_hash: _NonEmpty
    token_count: int = Field(ge=0)


class ChunkRecord(BaseModel):
    """One chunk row for the spine ledger (text and vectors live elsewhere, D37/D8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: UUID
    deployment_id: UUID
    doc_id: UUID
    version_id: UUID
    representation_id: UUID
    section_id: UUID
    ordinal: int = Field(ge=0)
    block_start: int = Field(ge=0)
    block_end: int = Field(ge=0)
    chunk_content_hash: _NonEmpty
    extraction_input_hash: _NonEmpty
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    token_count: int = Field(ge=0)
    chunker_version: _NonEmpty


class ChunkForEmbedding(BaseModel):
    """One chunk row as the embed stage loads it (spans + signals, no body)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: UUID
    doc_id: UUID
    version_id: UUID
    ordinal: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    section_role: str
    section_path: str
    context_prefix: str | None
    prefixer_version: str | None


class EmbeddingUpdate(BaseModel):
    """The embed stage's write-back onto one chunk row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: UUID
    embedding_ref: _NonEmpty
    embedding_version: _NonEmpty
    context_prefix: _NonEmpty
    prefixer_version: _NonEmpty


class ContextPrefix(BaseModel):
    """The structured response of the E1 context-prefix call (D58/D63)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prefix: _NonEmpty


class P1ChunkRow(BaseModel):
    """One row of the P1 chunk table: text + vector + filter scalars (D8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: UUID
    deployment_id: UUID
    doc_id: UUID
    version_id: UUID
    section_role: str
    text: _NonEmpty
    vector: Annotated[tuple[float, ...], Field(min_length=1)]


class ChunkSourceNotFoundError(Exception):
    """The chunk stage referenced a representation the spine does not know."""
