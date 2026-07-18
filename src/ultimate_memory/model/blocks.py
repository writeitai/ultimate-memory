"""Typed block records — the deterministic identity atoms of a document (D57)."""

from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class BlockType(StrEnum):
    """The structural kinds a blockizer emits (e1 §2)."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE = "table"
    LIST_ITEM = "list_item"
    CODE = "code"
    QUOTE = "quote"


class Block(BaseModel):
    """One block: a slice of document.md with its deterministic identity hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int = Field(ge=0)
    type: BlockType
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    block_hash: str
