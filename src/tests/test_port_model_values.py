"""Meaningful invariants on shared immutable provider-boundary values."""

from decimal import Decimal

from pydantic import BaseModel
from pydantic import SecretBytes
from pydantic import ValidationError
import pytest

from rememberstack.model import EmbeddingResponse
from rememberstack.model import GeneratedResponse
from rememberstack.model import ObjectKey
from rememberstack.model import PerimeterCredential
from rememberstack.model import ProviderCallUsage
from rememberstack.model import PublishedMounts
from rememberstack.model import SelectionDropReason
from rememberstack.model import SelectionResponse


class _Output(BaseModel):
    """Small structured output used to prove response/usage pairing."""

    answer: str


def test_generated_response_keeps_exact_decimal_provider_cost() -> None:
    """Carry provider accounting beside a validated structured output."""
    response = GeneratedResponse(
        output=_Output(answer="ok"),
        usage=ProviderCallUsage(
            model_name="generation-model",
            tokens_in=7,
            tokens_out=2,
            cost_usd=Decimal("0.000123"),
            latency_ms=4,
        ),
    )

    assert response.output.answer == "ok"
    assert response.usage.cost_usd == Decimal("0.000123")


def test_embedding_response_rejects_mixed_dimensions() -> None:
    """Reject malformed provider batches before vectors reach application logic."""
    with pytest.raises(ValidationError):
        EmbeddingResponse(
            vectors=((1.0, 2.0), (3.0,)),
            usage=ProviderCallUsage(
                model_name="embedding-model",
                tokens_in=1,
                tokens_out=0,
                cost_usd=Decimal(0),
                latency_ms=0,
            ),
        )


def test_object_key_is_non_empty_and_frozen() -> None:
    """Keep immutable storage identity explicit at the byte/object-key boundary."""
    key = ObjectKey(root="snapshots/valid/revision")

    with pytest.raises(ValidationError):
        ObjectKey(root="")

    with pytest.raises(ValidationError):
        key.root = "replacement"  # type: ignore[misc]


def test_published_mounts_cannot_claim_a_writable_view() -> None:
    """Make the D51 read-only mount invariant a validated boundary value."""
    with pytest.raises(ValidationError):
        PublishedMounts.model_validate(
            {
                "deployment_id": "00000000-0000-0000-0000-000000000001",
                "p3": "mount://p3",
                "artifacts": "mount://artifacts",
                "raw": "mount://raw",
                "knowledge": "mount://knowledge",
                "read_only": False,
            }
        )


def test_perimeter_credential_redacts_secret_bytes() -> None:
    """Keep credential bytes out of model reprs at the auth boundary."""
    credential = PerimeterCredential(
        scheme="api-key", value=SecretBytes(b"must-not-appear")
    )

    assert "must-not-appear" not in repr(credential)


def test_selection_drop_reason_matches_the_database_vocabulary() -> None:
    """Reject provider prose before a selection decision reaches PostgreSQL."""
    valid = SelectionResponse.model_validate(
        {
            "candidates": [
                {
                    "source_span": "How are you?",
                    "verdict": "drop",
                    "drop_reason": "question",
                    "protected_class": None,
                }
            ]
        }
    )

    assert valid.candidates[0].drop_reason is SelectionDropReason.QUESTION
    with pytest.raises(ValidationError):
        SelectionResponse.model_validate(
            {
                "candidates": [
                    {
                        "source_span": "How are you?",
                        "verdict": "drop",
                        "drop_reason": "question (the speaker asks a question)",
                        "protected_class": None,
                    }
                ]
            }
        )


@pytest.mark.parametrize(
    ("verdict", "drop_reason"),
    (("drop", None), ("keep", "question"), ("keep_flagged", "advice")),
)
def test_selection_drop_reason_is_present_only_for_drops(
    verdict: str, drop_reason: str | None
) -> None:
    """Keep the decision transcript complete without attaching false drop reasons."""
    with pytest.raises(ValidationError):
        SelectionResponse.model_validate(
            {
                "candidates": [
                    {
                        "source_span": "A statement.",
                        "verdict": verdict,
                        "drop_reason": drop_reason,
                        "protected_class": None,
                    }
                ]
            }
        )
