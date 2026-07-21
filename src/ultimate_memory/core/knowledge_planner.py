"""Pure Plane-K planning hashes, trigger selection, and D24-style banding."""

from decimal import Decimal
import hashlib
import json

from ultimate_memory.model import KnowledgeConvertKindProposal
from ultimate_memory.model import KnowledgePageKind
from ultimate_memory.model import KnowledgePlanBand
from ultimate_memory.model import KnowledgePlanningSnapshot
from ultimate_memory.model import KnowledgePlanProposal
from ultimate_memory.model import KnowledgePlanRunKind
from ultimate_memory.model import KnowledgePlanTrigger


def knowledge_planning_input_hash(*, snapshot: KnowledgePlanningSnapshot) -> str:
    """Hash one canonical planning snapshot for replay and cost attribution."""
    payload = json.dumps(
        snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def primary_knowledge_plan_trigger(
    *, snapshot: KnowledgePlanningSnapshot, run_kind: KnowledgePlanRunKind
) -> KnowledgePlanTrigger:
    """Choose one stable ledger trigger while retaining every input in the snapshot."""
    if run_kind is KnowledgePlanRunKind.REFLECTION:
        return KnowledgePlanTrigger.REFLECTION
    if snapshot.orphan_aggregates:
        return KnowledgePlanTrigger.ORPHAN_EVIDENCE
    if snapshot.overflow_artifact_ids:
        return KnowledgePlanTrigger.SIZE_OVERFLOW
    if snapshot.community_ids:
        return KnowledgePlanTrigger.COMMUNITY_CHANGE
    if snapshot.writer_suggestions:
        return KnowledgePlanTrigger.WRITER_SUGGESTION
    return KnowledgePlanTrigger.HUMAN


def route_knowledge_plan(
    *,
    proposal: KnowledgePlanProposal,
    run_kind: KnowledgePlanRunKind,
    blast_radius: int,
    auto_apply_max_expected_impact: Decimal,
) -> tuple[KnowledgePlanBand, Decimal]:
    """Route a proposal mechanically from impact, with the two binding exceptions."""
    if blast_radius < 0:
        raise ValueError("blast_radius must be non-negative")
    if auto_apply_max_expected_impact < 0:
        raise ValueError("auto-apply threshold must be non-negative")
    expected_impact = Decimal(blast_radius) * (Decimal("1") - proposal.confidence)
    requires_author_confirmation = (
        isinstance(proposal, KnowledgeConvertKindProposal)
        and proposal.to_kind is KnowledgePageKind.COMPILED
    )
    if (
        run_kind is KnowledgePlanRunKind.REFLECTION
        or requires_author_confirmation
        or expected_impact > auto_apply_max_expected_impact
    ):
        return KnowledgePlanBand.REVIEW, expected_impact
    return KnowledgePlanBand.AUTO_APPLY, expected_impact
