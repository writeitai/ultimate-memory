"""A deterministic in-memory model provider for behavior tests (no network)."""

import hashlib

from ultimate_memory.model import EmbeddingRequest
from ultimate_memory.model import EmbeddingResponse
from ultimate_memory.model import ModelRequest
from ultimate_memory.model import StructuredResponseModel

_EMBEDDING_DIMENSION = 8


class FakeModelProvider:
    """Deterministic embeddings and canned structured generations for proofs."""

    def __init__(self, *, generate_payload: dict[str, object]) -> None:
        """Bind the canned payload every generate call validates and returns."""
        self._generate_payload = generate_payload
        self.embedded_texts: list[str] = []
        self.generated_prompts: list[str] = []

    def generate[ResponseT: StructuredResponseModel](
        self, *, request: ModelRequest, response_type: type[ResponseT]
    ) -> ResponseT:
        """Return the canned payload validated as the caller's declared type."""
        self.generated_prompts.append(request.prompt)
        return response_type.model_validate(self._generate_payload)

    def embed(self, *, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return one deterministic content-derived vector per input text."""
        self.embedded_texts.extend(request.texts)
        return EmbeddingResponse(
            vectors=tuple(_vector_for(text=text) for text in request.texts)
        )


def _vector_for(*, text: str) -> tuple[float, ...]:
    """Derive a stable pseudo-vector from the text content."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return tuple(byte / 255.0 for byte in digest[:_EMBEDDING_DIMENSION])
