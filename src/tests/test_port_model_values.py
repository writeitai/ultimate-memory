"""Meaningful invariants on shared immutable provider-boundary values."""

from pydantic import SecretBytes
from pydantic import ValidationError
import pytest

from ultimate_memory.model import EmbeddingResponse
from ultimate_memory.model import ObjectKey
from ultimate_memory.model import PerimeterCredential
from ultimate_memory.model import PublishedMounts


def test_embedding_response_rejects_mixed_dimensions() -> None:
    """Reject malformed provider batches before vectors reach application logic."""
    with pytest.raises(ValidationError):
        EmbeddingResponse(vectors=((1.0, 2.0), (3.0,)))


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
