"""D52/D61 substrate seam for typed model and embedding provider calls."""

from typing import Protocol
from typing import runtime_checkable
from typing import TypeVar

from rememberstack.model import EmbeddingRequest
from rememberstack.model import EmbeddingResponse
from rememberstack.model import GeneratedResponse
from rememberstack.model import ModelRequest
from rememberstack.model import StructuredResponseModel

ResponseT = TypeVar("ResponseT", bound=StructuredResponseModel)


@runtime_checkable
class ModelProviderPort(Protocol):
    """Invoke configured models without owning prompts, cascades, or domain logic."""

    def generate(
        self, *, request: ModelRequest, response_type: type[ResponseT]
    ) -> GeneratedResponse[ResponseT]:
        """Return validated output plus the provider-reported usage for this call."""
        ...

    def embed(self, *, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return same-dimension embeddings for one caller-declared batch."""
        ...
