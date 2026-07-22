"""Canonical D74 source-identity hashing proofs."""

from uuid import UUID

from ultimate_memory.core import source_identity_hash


def test_source_identity_hash_is_stable_unambiguous_and_deployment_scoped() -> None:
    """Keep exact connector identity guards stable without delimiter collisions."""
    deployment_id = UUID("74000000-0000-0000-0000-000000000001")
    other_deployment_id = UUID("74000000-0000-0000-0000-000000000002")

    first = source_identity_hash(
        deployment_id=deployment_id, source_kind="drive:a", source_ref="b"
    )
    repeated = source_identity_hash(
        deployment_id=deployment_id, source_kind="drive:a", source_ref="b"
    )
    delimiter_variant = source_identity_hash(
        deployment_id=deployment_id, source_kind="drive", source_ref="a:b"
    )
    other_deployment = source_identity_hash(
        deployment_id=other_deployment_id, source_kind="drive:a", source_ref="b"
    )

    assert first == repeated
    assert first != delimiter_variant
    assert first != other_deployment
    assert len(first) == 64
