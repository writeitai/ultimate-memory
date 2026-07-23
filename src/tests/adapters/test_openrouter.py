"""Provider-accounting proofs for the shipped OpenRouter adapter."""

from decimal import Decimal

import pytest

from rememberstack.adapters.openrouter import _usage
from rememberstack.model import ProviderAccountingError


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
