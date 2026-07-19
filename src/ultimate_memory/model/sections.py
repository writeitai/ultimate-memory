"""Section-structure values (D39/D57): the LLM's proposal and the snapped truth.

Two deliberately different trust levels share this module. `ProposedSection` /
`StructureResponse` are the structurer LLM's raw output — free-hand character
spans that may overlap, gap, nest wrongly, or point outside the document; they
are never persisted. `SnappedSection` is what the deterministic snap
(`core/section_snap.py`) makes of them: a well-formed partition on the block
grid, the only form that reaches `document_sections`.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class ProposedSection(BaseModel):
    """One LLM-proposed section span (pre-snap): untrusted free-hand geometry."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    title: str = ""
    role: str = "body"
    char_start: int = 0
    char_end: int = 0
    summary: str = ""
    children: tuple[ProposedSection, ...] = ()


class StructureResponse(BaseModel):
    """The structurer's structured output: a proposed tree + placement hint."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    sections: tuple[ProposedSection, ...] = ()
    placement: str = ""


class SnappedSection(BaseModel):
    """One well-formed section after the deterministic snap (block coordinates).

    ``block_end`` is inclusive; the empty document's root carries the empty
    range ``0..-1`` on the block grid (D57) with a zero-width char span.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_path: str  # materialized path, e.g. '0.2.1'; the root is '0'
    parent_path: str | None
    title: str
    role: str
    block_start: int = Field(ge=0)
    block_end: int = Field(ge=-1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    summary: str
    ordinal: int = Field(ge=0)


class SectionTreeRecord(BaseModel):
    """The complete write input for one representation's section tree.

    ``sections`` is in depth-first document order with the root first — the
    catalog resolves each row's parent id from the paths as it inserts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    doc_id: UUID
    version_id: UUID
    representation_id: UUID
    sections: tuple[SnappedSection, ...] = Field(min_length=1)
    placement_path: str | None
    structurer_name: str
    structurer_version: str
