"""Provider-accounting proofs for the shipped OpenRouter adapter."""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel
from pydantic import Field
import pytest

from rememberstack.adapters import OpenRouterModelProvider
from rememberstack.adapters import OpenRouterProviderError
from rememberstack.adapters import OpenRouterSettings
from rememberstack.adapters.openrouter import _usage
from rememberstack.model import EmbeddingRequest
from rememberstack.model import ModelRequest
from rememberstack.model import ProviderAccountingError


class _Answer(BaseModel):
    """Minimal structured response for adapter-only temperature tests."""

    answer: Annotated[str, Field(min_length=1)]


def test_usage_keeps_exact_cost_and_defaults_embedding_output_tokens() -> None:
    """Parse required accounting without introducing float rounding."""
    usage = _usage(
        body={
            "model": "resolved/provider-model",
            "usage": {"prompt_tokens": 17, "cost": "0.000123"},
        },
        requested_model="requested/model",
        latency_ms=9,
    )

    assert usage.model_name == "resolved/provider-model"
    assert usage.tokens_in == 17
    assert usage.tokens_out == 0
    assert usage.cost_usd == Decimal("0.000123")
    assert usage.latency_ms == 9


@pytest.mark.parametrize(
    "body",
    (
        {},
        {"usage": {"prompt_tokens": 1}},
        {"usage": {"prompt_tokens": 1, "cost": "not-a-number"}},
    ),
)
def test_usage_fails_closed_when_required_accounting_is_unusable(
    body: dict[str, object],
) -> None:
    """Never let a worker interpret absent or malformed provider cost as zero."""
    with pytest.raises(ProviderAccountingError):
        _usage(body=body, requested_model="requested/model", latency_ms=1)


@pytest.mark.parametrize(("temperature", "present"), ((None, False), (0.0, True)))
def test_generation_forwards_temperature_only_when_declared(
    monkeypatch: pytest.MonkeyPatch, temperature: float | None, present: bool
) -> None:
    """Protocol calls freeze temperature without changing existing callers."""
    provider = OpenRouterModelProvider(settings=OpenRouterSettings(api_key="test-key"))
    observed: dict[str, object] = {}

    def post(*, path: str, payload: dict[str, object]) -> dict[str, object]:
        observed.update(payload)
        assert path == "/chat/completions"
        return {
            "model": "openai/gpt-4o-mini",
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "cost": "0"},
            "choices": [{"message": {"content": '{"answer":"Prague"}'}}],
        }

    monkeypatch.setattr(provider, "_post", post)
    try:
        provider.generate(
            request=ModelRequest(
                model="openai/gpt-4o-mini", prompt="Where?", temperature=temperature
            ),
            response_type=_Answer,
        )
    finally:
        provider._client.close()

    assert ("temperature" in observed) is present
    if present:
        assert observed["temperature"] == 0.0


def test_generation_preserves_usage_on_structured_output_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A billable invalid schema carries its already parsed provider usage."""
    provider = OpenRouterModelProvider(settings=OpenRouterSettings(api_key="test-key"))

    def post(*, path: str, payload: dict[str, object]) -> dict[str, object]:
        assert path == "/chat/completions"
        assert payload
        return {
            "model": "openai/gpt-4o-mini",
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "cost": "0"},
            "choices": [{"message": {"content": '{"answer":""}'}}],
        }

    monkeypatch.setattr(provider, "_post", post)
    try:
        with pytest.raises(OpenRouterProviderError) as raised:
            provider.generate(
                request=ModelRequest(
                    model="openai/gpt-4o-mini", prompt="Where?", temperature=0
                ),
                response_type=_Answer,
            )
    finally:
        provider._client.close()

    assert raised.value.usage is not None
    assert raised.value.usage.tokens_in == 3
    assert raised.value.usage.tokens_out == 1


def test_embedding_preserves_usage_when_the_vector_body_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed billable embedding remains attributable to its worker."""
    provider = OpenRouterModelProvider(settings=OpenRouterSettings(api_key="test-key"))

    def post(*, path: str, payload: dict[str, object]) -> dict[str, object]:
        assert path == "/embeddings"
        assert payload
        return {
            "model": "qwen/qwen3-embedding-8b",
            "usage": {"prompt_tokens": 4, "cost": "0.000004"},
            "data": [{"index": 0, "embedding": []}],
        }

    monkeypatch.setattr(provider, "_post", post)
    try:
        with pytest.raises(OpenRouterProviderError) as raised:
            provider.embed(
                request=EmbeddingRequest(
                    model="qwen/qwen3-embedding-8b", texts=("memory",)
                )
            )
    finally:
        provider._client.close()

    assert raised.value.usage is not None
    assert raised.value.usage.tokens_in == 4
    assert raised.value.usage.cost_usd == Decimal("0.000004")
