"""WP-6.4 deterministic writer-bundle and completeness proofs."""

from datetime import datetime
from datetime import UTC
from uuid import UUID

from rememberstack.core import cap_knowledge_writer_bundle
from rememberstack.core import knowledge_writer_coverage
from rememberstack.core import render_knowledge_writer_bundle
from rememberstack.model import KnowledgeCitation
from rememberstack.model import KnowledgeClaimFingerprint
from rememberstack.model import KnowledgeEvidenceRole
from rememberstack.model import KnowledgeEvidenceTarget
from rememberstack.model import KnowledgeFactFingerprint
from rememberstack.model import KnowledgeFactSheetFact
from rememberstack.model import KnowledgeFactSheetSnapshot
from rememberstack.model import KnowledgeInputSnapshot
from rememberstack.model import KnowledgeWriterBundle
from rememberstack.model import KnowledgeWriterClaim
from rememberstack.model import KnowledgeWriterClaimGroup
from rememberstack.model import KnowledgeWriterFactReference

_ARTIFACT_ID = UUID("64000000-0000-0000-0000-000000000001")
_DEPLOYMENT_ID = UUID("64000000-0000-0000-0000-000000000002")
_RELATION_ID = UUID("64000000-0000-0000-0000-000000000011")
_OBSERVATION_ID = UUID("64000000-0000-0000-0000-000000000012")
_AS_OF = datetime(2026, 7, 20, tzinfo=UTC)


def _group(
    *, suffix: int, reference: KnowledgeWriterFactReference | None = None
) -> KnowledgeWriterClaimGroup:
    """Build one stable D54 coordinate with one current claim body."""
    doc_id = UUID(f"64000000-0000-0000-0001-{suffix:012d}")
    claim_id = UUID(f"64000000-0000-0000-0002-{suffix:012d}")
    return KnowledgeWriterClaimGroup(
        lineage_id=doc_id,
        chunk_content_hash=f"chunk-{suffix}",
        claims=(
            KnowledgeWriterClaim(
                claim_id=claim_id,
                lineage_id=doc_id,
                chunk_content_hash=f"chunk-{suffix}",
                claim_text=f"Claim {suffix}",
                source_span=f"Source {suffix}",
                document_title=f"Document {suffix}",
                source_kind="upload",
                fact_references=() if reference is None else (reference,),
            ),
        ),
    )


def _bundle() -> KnowledgeWriterBundle:
    """Return two facts, two evidence groups, and two residue groups."""
    facts = (
        KnowledgeFactSheetFact(
            kind="relation",
            fact_id=_RELATION_ID,
            label="Alice works for Acme",
            ingested_at=_AS_OF,
            evidence_count=4,
            contradict_count=0,
        ),
        KnowledgeFactSheetFact(
            kind="observation",
            fact_id=_OBSERVATION_ID,
            label="Revenue was five million",
            ingested_at=_AS_OF,
            evidence_count=2,
            contradict_count=0,
        ),
    )
    groups = (
        _group(
            suffix=1,
            reference=KnowledgeWriterFactReference(
                kind="relation", fact_id=_RELATION_ID, stance="supports"
            ),
        ),
        _group(
            suffix=2,
            reference=KnowledgeWriterFactReference(
                kind="observation", fact_id=_OBSERVATION_ID, stance="supports"
            ),
        ),
        _group(suffix=3),
        _group(suffix=4),
    )
    snapshot = KnowledgeInputSnapshot(
        facts=tuple(
            KnowledgeFactFingerprint(
                kind=fact.kind,
                fact_id=fact.fact_id,
                evidence_count=fact.evidence_count,
                contradict_count=fact.contradict_count,
            )
            for fact in facts
        ),
        claims=tuple(
            KnowledgeClaimFingerprint(
                lineage_id=group.lineage_id, chunk_content_hash=group.chunk_content_hash
            )
            for group in groups
        ),
        writer_version="writer-test",
    )
    return KnowledgeWriterBundle(
        fact_sheet=KnowledgeFactSheetSnapshot(
            artifact_id=_ARTIFACT_ID,
            deployment_id=_DEPLOYMENT_ID,
            evidence_as_of=_AS_OF,
            input_snapshot=snapshot,
            facts=facts,
        ),
        claim_groups=groups,
        claim_candidate_count=4,
        claims_cut_count=0,
    )


def test_cap_keeps_all_facts_and_records_every_omitted_claim_coordinate() -> None:
    """Fact skeletons stay complete while settings cap only hydrated claim groups."""
    bundle = _bundle()

    capped = cap_knowledge_writer_bundle(
        bundle=bundle, exclusions=(), residue_claim_limit=1, evidence_claims_per_fact=1
    )

    assert capped.fact_sheet.facts == bundle.fact_sheet.facts
    assert [group.chunk_content_hash for group in capped.claim_groups] == [
        "chunk-1",
        "chunk-2",
        "chunk-3",
    ]
    assert capped.claim_candidate_count == 4
    assert capped.claims_cut_count == 1


def test_excluded_evidence_is_neither_offered_nor_leaked_by_bundle_rendering() -> None:
    """Curation exclusions shrink the offering before the writer sees any IDs or text."""
    bundle = _bundle()
    excluded_relation = KnowledgeEvidenceTarget(relation_id=_RELATION_ID)
    excluded_group = bundle.claim_groups[2]

    capped = cap_knowledge_writer_bundle(
        bundle=bundle,
        exclusions=(
            excluded_relation,
            KnowledgeEvidenceTarget(
                claim_lineage_id=excluded_group.lineage_id,
                claim_chunk_content_hash=excluded_group.chunk_content_hash,
            ),
        ),
        residue_claim_limit=5,
        evidence_claims_per_fact=5,
    )
    rendered = render_knowledge_writer_bundle(bundle=capped)

    assert _RELATION_ID not in {fact.fact_id for fact in capped.fact_sheet.facts}
    assert str(_RELATION_ID) not in rendered
    assert str(excluded_group.claims[0].claim_id) not in rendered
    assert "chunk-1" not in rendered
    assert "Claim 1" not in rendered
    assert all(
        reference.fact_id != _RELATION_ID
        for group in capped.claim_groups
        for claim in group.claims
        for reference in claim.fact_references
    )


def test_coverage_credits_observation_only_through_supporting_claim_evidence() -> None:
    """Observation completeness uses schema-supported claim citations, never invented IDs."""
    capped = cap_knowledge_writer_bundle(
        bundle=_bundle(),
        exclusions=(),
        residue_claim_limit=1,
        evidence_claims_per_fact=1,
    )
    observation_group = capped.claim_groups[1]

    coverage = knowledge_writer_coverage(
        bundle=capped,
        citations=(
            KnowledgeCitation(
                role=KnowledgeEvidenceRole.SUPPORTS, relation_id=_RELATION_ID
            ),
            KnowledgeCitation(
                role=KnowledgeEvidenceRole.SUPPORTS,
                claim_lineage_id=observation_group.lineage_id,
                claim_chunk_content_hash=observation_group.chunk_content_hash,
            ),
        ),
    )

    assert coverage.candidate_count == 5
    assert coverage.cited_candidate_count == 3
    assert coverage.uncited_count == 2
