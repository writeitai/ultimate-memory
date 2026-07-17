"""D52/D61 substrate seam for typed model and embedding provider calls."""

from typing import Protocol
from typing import runtime_checkable
from typing import TypeVar

from ultimate_memory.model import EmbeddingRequest
from ultimate_memory.model import EmbeddingResponse
from ultimate_memory.model import ModelRequest
from ultimate_memory.model import StructuredResponseModel

ResponseT = TypeVar("ResponseT", bound=StructuredResponseModel)


@runtime_checkable
class ModelProviderPort(Protocol):
    """Invoke configured models without owning prompts, cascades, or domain logic."""

    def generate(
        self, *, request: ModelRequest, response_type: type[ResponseT]
    ) -> ResponseT:
        """Return a response validated as the caller's declared structured type."""
        ...

    def embed(self, *, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return same-dimension embeddings for one caller-declared batch."""
        ...
