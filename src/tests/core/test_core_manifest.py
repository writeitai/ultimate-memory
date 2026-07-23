"""Integrity checks for the immutable normative core-v1 manifest."""

from dataclasses import FrozenInstanceError

import pytest

from rememberstack.core import CORE_MANIFEST


def test_core_manifest_has_exact_version_counts_order_and_unique_keys() -> None:
    """Lock the executable core-v1 identity, cardinality, order, and uniqueness."""
    entity_keys = tuple(entity.type for entity in CORE_MANIFEST.entity_types)
    predicate_keys = tuple(
        predicate.predicate for predicate in CORE_MANIFEST.predicates
    )
    signature_keys = tuple(
        (signature.predicate, signature.subject_type, signature.object_type)
        for signature in CORE_MANIFEST.predicate_signatures
    )

    assert CORE_MANIFEST.manifest_version == "core-v1"
    assert len(entity_keys) == len(set(entity_keys)) == 8
    assert len(predicate_keys) == len(set(predicate_keys)) == 16
    assert len(signature_keys) == len(set(signature_keys)) == 116
    assert predicate_keys[0] == "related_to"


def test_core_manifest_has_eight_roots_and_external_document_anchor() -> None:
    """Keep Document a root anchored externally without a ninth registry type."""
    entities = {entity.type: entity for entity in CORE_MANIFEST.entity_types}

    assert all(entity.parent_type is None for entity in CORE_MANIFEST.entity_types)
    assert entities["Document"].schema_org_ref == "https://schema.org/CreativeWork"
    assert "CreativeWork" not in entities


def test_core_manifest_is_deeply_immutable() -> None:
    """Prevent runtime changes to the manifest or any behavior-bearing row."""
    with pytest.raises(FrozenInstanceError):
        CORE_MANIFEST.manifest_version = "replacement"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        CORE_MANIFEST.entity_types[0].description = "replacement"  # type: ignore[misc]


def test_signature_expansion_is_behaviorally_correct() -> None:
    """Verify the derived signatures against the design's own domain/range rules."""
    signatures = {
        (signature.predicate, signature.subject_type, signature.object_type)
        for signature in CORE_MANIFEST.predicate_signatures
    }
    core_types = {entity.type for entity in CORE_MANIFEST.entity_types}

    assert ("works_for", "Person", "Organization") in signatures
    assert ("works_for", "Organization", "Organization") not in signatures
    assert ("uses", "Person", "Product") in signatures
    assert ("reports_to", "Person", "Person") in signatures

    part_of_rows = {s for s in signatures if s[0] == "part_of"}
    assert part_of_rows == {("part_of", t, t) for t in core_types}

    about_objects = {s[2] for s in signatures if s[0] == "about"}
    assert about_objects == core_types

    related_to_rows = {s for s in signatures if s[0] == "related_to"}
    assert len(related_to_rows) == len(core_types) ** 2
