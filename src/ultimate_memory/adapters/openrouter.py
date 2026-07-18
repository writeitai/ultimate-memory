"""The OpenRouter model-provider adapter (D63/D70): the shipped default binding."""

import json
from typing import Any
from typing import TypeVar

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from ultimate_memory.model import EmbeddingRequest
from ultimate_memory.model import EmbeddingResponse
from ultimate_memory.model import ModelRequest
from ultimate_memory.model import StructuredResponseModel

ResponseT = TypeVar("ResponseT", bound=StructuredResponseModel)


class OpenRouterSettings(BaseSettings):
    """The OpenRouter binding: key and endpoint, per deployment (D61)."""

    model_config = SettingsConfigDict(env_prefix="UGM_OPENROUTER_")

    api_key: str = Field(min_length=1)
    base_url: str = Field(default="https://openrouter.ai/api/v1")
    timeout_s: float = Field(default=120.0, gt=0)


class OpenRouterProviderError(Exception):
    """OpenRouter returned an error or an unusable response body."""


class OpenRouterModelProvider:
    """Structured generations and embeddings over the OpenRouter HTTP API."""

    def __init__(self, *, settings: OpenRouterSettings) -> None:
        """Bind one HTTP client to the configured endpoint and key."""
        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=settings.timeout_s,
        )

    def generate(
        self, *, request: ModelRequest, response_type: type[ResponseT]
    ) -> ResponseT:
        """One chat completion constrained to the caller's declared JSON schema."""
        body = self._post(
            path="/chat/completions",
            payload={
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_type.__name__,
                        "strict": True,
                        "schema": response_type.model_json_schema(),
                    },
                },
            },
        )
        try:
            content = body["choices"][0]["message"]["content"]
            return response_type.model_validate(json.loads(content))
        except (KeyError, IndexError, ValueError) as err:
            raise OpenRouterProviderError(
                f"unusable completion body for {response_type.__name__}"
            ) from err

    def embed(self, *, request: EmbeddingRequest) -> EmbeddingResponse:
        """One embeddings call for the caller's batch."""
        body = self._post(
            path="/embeddings",
            payload={"model": request.model, "input": list(request.texts)},
        )
        try:
            ordered = sorted(body["data"], key=lambda item: item["index"])
            return EmbeddingResponse(
                vectors=tuple(tuple(item["embedding"]) for item in ordered)
            )
        except (KeyError, TypeError, ValueError) as err:
            raise OpenRouterProviderError("unusable embeddings body") from err

    def _post(self, *, path: str, payload: dict[str, object]) -> dict[str, Any]:
        """POST one JSON request; non-2xx responses become typed errors."""
        response = self._client.post(path, json=payload)
        if response.status_code >= 400:
            raise OpenRouterProviderError(
                f"OpenRouter {path} returned {response.status_code}: "
                f"{response.text[:500]}"
            )
        return response.json()
