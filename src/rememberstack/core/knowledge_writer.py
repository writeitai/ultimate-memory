"""Deterministic bundle capping, rendering, and completeness accounting."""

from collections.abc import Collection
import json
from uuid import UUID

from rememberstack.model import KnowledgeCitation
from rememberstack.model import KnowledgeEvidenceRole
from rememberstack.model import KnowledgeEvidenceTarget
from rememberstack.model import KnowledgeWriterBundle
from rememberstack.model import KnowledgeWriterClaimGroup
from rememberstack.model import KnowledgeWriterCoverage


def cap_knowledge_writer_bundle(
    *,
    bundle: KnowledgeWriterBundle,
    exclusions: Collection[KnowledgeEvidenceTarget],
    residue_claim_limit: int,
    evidence_claims_per_fact: int,
) -> KnowledgeWriterBundle:
    """Filter curation exclusions and cap D54 claim coordinates deterministically."""
    if residue_claim_limit < 0 or evidence_claims_per_fact < 0:
        raise ValueError("writer claim limits must be non-negative")
    excluded_relations = {
        item.relation_id for item in exclusions if item.relation_id is not None
    }
    excluded_claim_coordinates = {
        (item.claim_lineage_id, item.claim_chunk_content_hash)
        for item in exclusions
        if item.claim_lineage_id is not None
    }
    excluded_docs = {item.doc_id for item in exclusions if item.doc_id is not None}
    facts = tuple(
        fact
        for fact in bundle.fact_sheet.facts
        if fact.kind != "relation" or fact.fact_id not in excluded_relations
    )
    fact_keys = {(fact.kind, fact.fact_id) for fact in facts}
    groups: list[KnowledgeWriterClaimGroup] = []
    for group in bundle.claim_groups:
        if (
            group.lineage_id in excluded_docs
            or _claim_group_key(group) in excluded_claim_coordinates
        ):
            continue
        claims = []
        for claim in group.claims:
            references = tuple(
                reference
                for reference in claim.fact_references
                if (reference.kind, reference.fact_id) in fact_keys
            )
            if claim.fact_references and not references:
                # Evidence for an excluded fact must not silently re-enter as
                # uncategorized residue after its fact reference is stripped.
                continue
            claims.append(claim.model_copy(update={"fact_references": references}))
        if claims:
            groups.append(group.model_copy(update={"claims": tuple(claims)}))

    ordered = tuple(sorted(groups, key=_claim_group_key))
    by_fact: dict[tuple[str, UUID], list[KnowledgeWriterClaimGroup]] = {}
    residue: list[KnowledgeWriterClaimGroup] = []
    for group in ordered:
        references = {
            (reference.kind, reference.fact_id)
            for claim in group.claims
            for reference in claim.fact_references
        }
        if not references:
            residue.append(group)
        for reference in references:
            by_fact.setdefault(reference, []).append(group)

    selected: dict[tuple[UUID, str], KnowledgeWriterClaimGroup] = {
        _claim_group_key(group): group for group in residue[:residue_claim_limit]
    }
    for fact in sorted(
        facts, key=lambda item: (-item.evidence_count, item.kind, str(item.fact_id))
    ):
        for group in by_fact.get((fact.kind, fact.fact_id), ())[
            :evidence_claims_per_fact
        ]:
            selected[_claim_group_key(group)] = group
    offered = tuple(selected[key] for key in sorted(selected, key=_sortable_group_key))
    return KnowledgeWriterBundle(
        fact_sheet=bundle.fact_sheet.model_copy(update={"facts": facts}),
        claim_groups=offered,
        claim_candidate_count=len(ordered),
        claims_cut_count=len(ordered) - len(offered),
    )


def render_knowledge_writer_bundle(*, bundle: KnowledgeWriterBundle) -> str:
    """Render only offered evidence into stable JSON with citation IDs inline."""
    payload = {
        "artifact_id": str(bundle.fact_sheet.artifact_id),
        "deployment_id": str(bundle.fact_sheet.deployment_id),
        "evidence_as_of": bundle.fact_sheet.evidence_as_of.isoformat(),
        "facts": [item.model_dump(mode="json") for item in bundle.fact_sheet.facts],
        "claim_groups": [item.model_dump(mode="json") for item in bundle.claim_groups],
        "ledger": {
            "fact_candidates_offered": len(bundle.fact_sheet.facts),
            "claim_candidates_offered": len(bundle.claim_groups),
            "claim_candidates_cut": bundle.claims_cut_count,
        },
    }
    return f"{json.dumps(payload, sort_keys=True, indent=2)}\n"


def knowledge_writer_coverage(
    *, bundle: KnowledgeWriterBundle, citations: tuple[KnowledgeCitation, ...]
) -> KnowledgeWriterCoverage:
    """Count direct and support-claim coverage without trusting writer-reported totals."""
    cited_relations = {
        item.relation_id for item in citations if item.relation_id is not None
    }
    cited_claims = {
        (item.claim_lineage_id, item.claim_chunk_content_hash)
        for item in citations
        if item.claim_lineage_id is not None
    }
    cited_docs = {item.doc_id for item in citations if item.doc_id is not None}
    supporting_claims = {
        (item.claim_lineage_id, item.claim_chunk_content_hash)
        for item in citations
        if item.claim_lineage_id is not None
        and item.role in (KnowledgeEvidenceRole.SUPPORTS, KnowledgeEvidenceRole.CITES)
    }
    supporting_docs = {
        item.doc_id
        for item in citations
        if item.doc_id is not None
        and item.role in (KnowledgeEvidenceRole.SUPPORTS, KnowledgeEvidenceRole.CITES)
    }

    cited_groups: set[tuple[UUID, str]] = set()
    supported_facts: set[tuple[str, UUID]] = set()
    for group in bundle.claim_groups:
        coordinate = _claim_group_key(group)
        group_used = group.lineage_id in cited_docs or coordinate in cited_claims
        for claim in group.claims:
            if coordinate in supporting_claims or claim.lineage_id in supporting_docs:
                supported_facts.update(
                    (reference.kind, reference.fact_id)
                    for reference in claim.fact_references
                    if reference.stance == "supports"
                )
        if group_used:
            cited_groups.add(_claim_group_key(group))

    cited_facts = {
        (fact.kind, fact.fact_id)
        for fact in bundle.fact_sheet.facts
        if (fact.kind == "relation" and fact.fact_id in cited_relations)
        or (fact.kind, fact.fact_id) in supported_facts
    }
    candidate_count = len(bundle.fact_sheet.facts) + len(bundle.claim_groups)
    cited_candidate_count = len(cited_facts) + len(cited_groups)
    return KnowledgeWriterCoverage(
        candidate_count=candidate_count,
        cited_candidate_count=cited_candidate_count,
        uncited_count=candidate_count - cited_candidate_count,
    )


def _claim_group_key(group: KnowledgeWriterClaimGroup) -> tuple[UUID, str]:
    """Return one D54 coordinate in its typed form."""
    return group.lineage_id, group.chunk_content_hash


def _sortable_group_key(key: tuple[UUID, str]) -> tuple[str, str]:
    """Convert one D54 coordinate to a stable total-order key."""
    return str(key[0]), key[1]
