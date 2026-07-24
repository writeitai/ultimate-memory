"""The OpenRouter model-provider adapter (D63/D70): the shipped default binding."""

from decimal import Decimal
from decimal import InvalidOperation
import json
import time
from typing import Any
from typing import Literal
from typing import TypeVar

import httpx
from pydantic import Field
from pydantic import field_validator
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from rememberstack.model import EmbeddingRequest
from rememberstack.model import EmbeddingResponse
from rememberstack.model import GeneratedResponse
from rememberstack.model import ModelRequest
from rememberstack.model import ProviderAccountingError
from rememberstack.model import ProviderCallError
from rememberstack.model import ProviderCallUsage
from rememberstack.model import StructuredResponseModel

ResponseT = TypeVar("ResponseT", bound=StructuredResponseModel)


class OpenRouterSettings(BaseSettings):
    """The OpenRouter binding: key and endpoint, per deployment (D61)."""

    model_config = SettingsConfigDict(env_prefix="REMEMBERSTACK_OPENROUTER_")

    api_key: str = Field(min_length=1)
    base_url: str = Field(default="https://openrouter.ai/api/v1")
    timeout_s: float = Field(default=120.0, gt=0)
    embedding_provider: str | None = None
    reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None
    ) = None

    @field_validator("embedding_provider", "reasoning_effort", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: object) -> object:
        """Treat Compose's empty optional values as unset."""
        if not isinstance(value, str):
            return value
        return value.strip() or None


class OpenRouterProviderError(ProviderCallError):
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
    ) -> GeneratedResponse[ResponseT]:
        """One chat completion constrained to the caller's declared JSON schema."""
        started_ns = time.monotonic_ns()
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_type.__name__,
                    "strict": True,
                    "schema": _strict_json_schema(response_type),
                },
            },
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if self._settings.reasoning_effort is not None:
            payload["reasoning"] = {"effort": self._settings.reasoning_effort}
        body = self._post(path="/chat/completions", payload=payload)
        usage = _usage(
            body=body,
            requested_model=request.model,
            latency_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
        )
        try:
            content = body["choices"][0]["message"]["content"]
            decoded = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as err:
            raise OpenRouterProviderError(
                f"unusable completion body for {response_type.__name__}", usage=usage
            ) from err
        try:
            output = response_type.model_validate(decoded)
        except ValidationError as error:
            raise OpenRouterProviderError(
                f"completion body failed {response_type.__name__} validation",
                usage=usage,
            ) from error
        return GeneratedResponse(output=output, usage=usage)

    def embed(self, *, request: EmbeddingRequest) -> EmbeddingResponse:
        """One embeddings call for the caller's batch."""
        started_ns = time.monotonic_ns()
        payload: dict[str, object] = {
            "model": request.model,
            "input": list(request.texts),
        }
        if self._settings.embedding_provider:
            payload["provider"] = {
                "only": [self._settings.embedding_provider],
                "allow_fallbacks": False,
            }
        body = self._post(path="/embeddings", payload=payload)
        usage = _usage(
            body=body,
            requested_model=request.model,
            latency_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
        )
        try:
            ordered = sorted(body["data"], key=lambda item: item["index"])
            return EmbeddingResponse(
                vectors=tuple(tuple(item["embedding"]) for item in ordered), usage=usage
            )
        except (KeyError, TypeError, ValueError) as err:
            raise OpenRouterProviderError(
                "unusable embeddings body", usage=usage
            ) from err

    def _post(self, *, path: str, payload: dict[str, object]) -> dict[str, Any]:
        """POST one JSON request; non-2xx responses become typed errors."""
        response = self._client.post(path, json=payload)
        if response.status_code >= 400:
            raise OpenRouterProviderError(
                f"OpenRouter {path} returned {response.status_code}: "
                f"{response.text[:500]}"
            )
        return response.json()


def _strict_json_schema(response_type: type[StructuredResponseModel]) -> dict[str, Any]:
    """Adapt Pydantic defaults to the strict schema subset used by OpenAI routes."""
    schema = response_type.model_json_schema()
    _require_all_object_properties(schema)
    return schema


def _require_all_object_properties(node: object) -> None:
    """Make every declared property required and remove unsupported defaults."""
    if isinstance(node, list):
        for item in node:
            _require_all_object_properties(item)
        return
    if not isinstance(node, dict):
        return

    node.pop("default", None)
    properties = node.get("properties")
    if isinstance(properties, dict):
        node["required"] = list(properties)
        node["additionalProperties"] = False
    for value in node.values():
        _require_all_object_properties(value)


def _usage(
    *, body: dict[str, Any], requested_model: str, latency_ms: int
) -> ProviderCallUsage:
    """Validate OpenRouter accounting; missing usage must not silently disable budgets."""
    raw = body.get("usage")
    if not isinstance(raw, dict):
        raise ProviderAccountingError("OpenRouter response carries no usage accounting")
    model_name = body.get("model", requested_model)
    try:
        return ProviderCallUsage(
            model_name=model_name,
            tokens_in=raw["prompt_tokens"],
            tokens_out=raw.get("completion_tokens", 0),
            cost_usd=Decimal(str(raw["cost"])),
            latency_ms=latency_ms,
        )
    except (InvalidOperation, KeyError, TypeError, ValueError) as err:
        raise ProviderAccountingError(
            "OpenRouter response carries invalid usage accounting"
        ) from err
