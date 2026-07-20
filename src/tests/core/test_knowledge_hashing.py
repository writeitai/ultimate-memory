"""D45/D54 property tests for the canonical Plane-K input hash."""

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from datetime import UTC
from uuid import uuid4

from pydantic import ValidationError
import pytest

from ultimate_memory.core import knowledge_inputs_hash
from ultimate_memory.model import EntityRuleParams
from ultimate_memory.model import KnowledgeCandidateLayer
from ultimate_memory.model import KnowledgeClaimFingerprint
from ultimate_memory.model import KnowledgeFactFingerprint
from ultimate_memory.model import KnowledgeInputSnapshot
from ultimate_memory.model import KnowledgeRuleConfiguration
from ultimate_memory.model import KnowledgeRuleKind


def _snapshot() -> KnowledgeInputSnapshot:
    """Return one complete hash input with both evidence grains."""
    return KnowledgeInputSnapshot(
        facts=(
            KnowledgeFactFingerprint(
                kind="relation",
                fact_id=uuid4(),
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                evidence_count=2,
                contradict_count=0,
            ),
            KnowledgeFactFingerprint(
                kind="observation",
                fact_id=uuid4(),
                evidence_count=1,
                contradict_count=1,
                contradiction_group=uuid4(),
            ),
        ),
        claims=(
            KnowledgeClaimFingerprint(lineage_id=uuid4(), chunk_content_hash="chunk-a"),
        ),
        rules=(
            KnowledgeRuleConfiguration(
                rule_id=uuid4(),
                kind=KnowledgeRuleKind.ENTITY,
                params={"entity_id": str(uuid4()), "layers": ["relations"]},
            ),
        ),
        curation_hash="curation-a",
        child_summary_hashes=("child-a", "child-b"),
        shared_model_summary_hash="model-a",
        writer_version="writer-a",
    )


def test_inputs_hash_is_order_independent_and_uses_set_union() -> None:
    """Candidate/rule order and duplicate rule IDs are administrative noise."""
    original = _snapshot()
    duplicate_config = original.rules[0].model_copy(update={"rule_id": uuid4()})
    permuted = original.model_copy(
        update={
            "facts": tuple(reversed(original.facts)) + (original.facts[0],),
            "claims": original.claims + original.claims,
            "rules": (duplicate_config, *original.rules),
            "child_summary_hashes": tuple(reversed(original.child_summary_hashes)),
        }
    )
    assert knowledge_inputs_hash(snapshot=original) == knowledge_inputs_hash(
        snapshot=permuted
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("valid_until", datetime(2026, 2, 1, tzinfo=UTC)),
        ("invalidated_at", datetime(2026, 2, 2, tzinfo=UTC)),
        ("evidence_count", 9),
        ("contradict_count", 4),
        ("contradiction_group", uuid4()),
    ),
)
def test_inputs_hash_tracks_every_fact_state_fingerprint(
    field: str, value: object
) -> None:
    """A candidate fact's validity, currency counts, or conflict state is load-bearing."""
    original = _snapshot()
    changed_fact = original.facts[0].model_copy(update={field: value})
    changed = original.model_copy(update={"facts": (changed_fact, original.facts[1])})
    assert knowledge_inputs_hash(snapshot=original) != knowledge_inputs_hash(
        snapshot=changed
    )


def test_fact_fingerprint_requires_utc_state_times() -> None:
    """Hash-visible timestamps cannot vary with an implicit or non-UTC timezone."""
    with pytest.raises(ValidationError):
        KnowledgeFactFingerprint(
            kind="relation",
            fact_id=uuid4(),
            valid_from=datetime(2026, 1, 1),
            evidence_count=1,
            contradict_count=0,
        )
    with pytest.raises(ValidationError):
        KnowledgeFactFingerprint(
            kind="relation",
            fact_id=uuid4(),
            valid_from=datetime(2026, 1, 1, tzinfo=timezone(offset=timedelta(hours=1))),
            evidence_count=1,
            contradict_count=0,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("curation_hash", "curation-b"),
        ("child_summary_hashes", ("child-a", "child-c")),
        ("shared_model_summary_hash", "model-b"),
        ("writer_version", "writer-b"),
    ),
)
def test_inputs_hash_tracks_every_non_evidence_compile_input(
    field: str, value: object
) -> None:
    """Sidecars, child/model summaries, and writer version each stale a page."""
    original = _snapshot()
    changed = original.model_copy(update={field: value})
    assert knowledge_inputs_hash(snapshot=original) != knowledge_inputs_hash(
        snapshot=changed
    )


def test_inputs_hash_tracks_rule_configuration_but_not_rule_identity() -> None:
    """Rule semantics stale a page; replacing an identical row UUID does not."""
    original = _snapshot()
    same_config = original.model_copy(
        update={"rules": (original.rules[0].model_copy(update={"rule_id": uuid4()}),)}
    )
    changed_config = original.model_copy(
        update={
            "rules": (
                original.rules[0].model_copy(
                    update={"params": {"entity_id": str(uuid4())}}
                ),
            )
        }
    )
    assert knowledge_inputs_hash(snapshot=original) == knowledge_inputs_hash(
        snapshot=same_config
    )
    assert knowledge_inputs_hash(snapshot=original) != knowledge_inputs_hash(
        snapshot=changed_config
    )


def test_set_valued_rule_params_have_one_semantic_hash() -> None:
    """Predicate/layer ordering and duplicates are not routing-rule changes."""
    entity_id = uuid4()
    first = EntityRuleParams(
        entity_id=entity_id,
        predicates=("works_on", "works_for", "works_on"),
        layers=(
            KnowledgeCandidateLayer.CLAIMS,
            KnowledgeCandidateLayer.RELATIONS,
            KnowledgeCandidateLayer.CLAIMS,
        ),
    )
    second = EntityRuleParams(
        entity_id=entity_id,
        predicates=("works_for", "works_on"),
        layers=(KnowledgeCandidateLayer.RELATIONS, KnowledgeCandidateLayer.CLAIMS),
    )
    snapshots = tuple(
        KnowledgeInputSnapshot(
            writer_version="writer",
            rules=(
                KnowledgeRuleConfiguration(
                    rule_id=uuid4(),
                    kind=params.kind,
                    params=params.model_dump(mode="json", exclude={"kind"}),
                ),
            ),
        )
        for params in (first, second)
    )
    assert knowledge_inputs_hash(snapshot=snapshots[0]) == knowledge_inputs_hash(
        snapshot=snapshots[1]
    )


def test_claim_fingerprint_is_only_lineage_and_chunk_content() -> None:
    """Raw extraction IDs cannot enter the D54 claim-grain staleness key."""
    lineage_id = uuid4()
    coordinate = KnowledgeClaimFingerprint(
        lineage_id=lineage_id, chunk_content_hash="same-testimony"
    )
    first = KnowledgeInputSnapshot(writer_version="writer", claims=(coordinate,))
    second = KnowledgeInputSnapshot(
        writer_version="writer",
        claims=(
            KnowledgeClaimFingerprint(
                lineage_id=lineage_id, chunk_content_hash="same-testimony"
            ),
        ),
    )
    assert knowledge_inputs_hash(snapshot=first) == knowledge_inputs_hash(
        snapshot=second
    )
    with pytest.raises(ValidationError):
        KnowledgeClaimFingerprint.model_validate(
            {
                "lineage_id": lineage_id,
                "chunk_content_hash": "same-testimony",
                "claim_id": uuid4(),
            }
        )


def test_claim_coordinate_and_child_multiplicity_are_hash_visible() -> None:
    """A new testimony coordinate or an added identical child changes the manifest."""
    original = _snapshot()
    moved_claim = original.model_copy(
        update={
            "claims": (
                original.claims[0].model_copy(update={"chunk_content_hash": "chunk-b"}),
            )
        }
    )
    extra_child = original.model_copy(
        update={"child_summary_hashes": (*original.child_summary_hashes, "child-a")}
    )
    assert knowledge_inputs_hash(snapshot=original) != knowledge_inputs_hash(
        snapshot=moved_claim
    )
    assert knowledge_inputs_hash(snapshot=original) != knowledge_inputs_hash(
        snapshot=extra_child
    )
