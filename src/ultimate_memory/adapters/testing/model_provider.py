"""A deterministic in-memory model provider for behavior tests (no network)."""

import hashlib

from ultimate_memory.model import EmbeddingRequest
from ultimate_memory.model import EmbeddingResponse
from ultimate_memory.model import ModelRequest
from ultimate_memory.model import StructuredResponseModel

_EMBEDDING_DIMENSION = 8


class FakeModelProvider:
    """Deterministic embeddings and canned structured generations for proofs."""

    def __init__(
        self,
        *,
        generate_payload: dict[str, object] | None = None,
        generate_payloads: dict[str, dict[str, object]] | None = None,
    ) -> None:
        """Bind canned payloads: one default, or one per response-type name."""
        self._generate_payload = generate_payload
        self._generate_payloads = generate_payloads or {}
        self.embedded_texts: list[str] = []
        self.generated_prompts: list[str] = []

    def generate[ResponseT: StructuredResponseModel](
        self, *, request: ModelRequest, response_type: type[ResponseT]
    ) -> ResponseT:
        """Return the canned payload validated as the caller's declared type."""
        self.generated_prompts.append(request.prompt)
        payload = self._generate_payloads.get(
            response_type.__name__, self._generate_payload
        )
        if payload is None:
            raise AssertionError(f"no canned payload for {response_type.__name__}")
        return response_type.model_validate(payload)

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
