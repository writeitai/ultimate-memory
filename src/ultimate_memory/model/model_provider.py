"""Typed, provider-neutral model and embedding call values for the LLM boundary."""

from typing import Annotated
from typing import Self
from typing import TypeAlias

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

_NonEmptyText = Annotated[str, Field(min_length=1)]
_EmbeddingVector = Annotated[tuple[float, ...], Field(min_length=1)]
StructuredResponseModel: TypeAlias = BaseModel


class ModelRequest(BaseModel):
    """A rendered prompt and configured model identifier ready for invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: _NonEmptyText
    prompt: _NonEmptyText


class EmbeddingRequest(BaseModel):
    """One non-empty batch for a configured embedding model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: _NonEmptyText
    texts: Annotated[tuple[_NonEmptyText, ...], Field(min_length=1)]


class EmbeddingResponse(BaseModel):
    """A non-empty embedding batch whose vectors share one dimension."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vectors: Annotated[tuple[_EmbeddingVector, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_one_dimension(self) -> Self:
        """Reject provider responses that mix embedding dimensions."""
        expected_dimension = len(self.vectors[0])
        if any(len(vector) != expected_dimension for vector in self.vectors[1:]):
            raise ValueError("all embedding vectors must have the same dimension")
        return self
