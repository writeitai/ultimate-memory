"""Lifecycle values (D54/D55): currency transitions and the reconciliation delta."""

from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict


class CurrencyTransition(BaseModel):
    """One testimony-currency ledger event to append (D54).

    Bookkeeping, never validity: nothing about the claim itself changes.
    ``reason`` is a `currency_reason` enum value; the from_* fields name the
    superseded coordinate (generation or version) for the audit trail.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: UUID
    doc_id: UUID
    became_current: bool
    reason: str
    from_extractor_version: str | None = None
    from_version_id: UUID | None = None


class ReconciliationDelta(BaseModel):
    """The fact-level outcome of one reconciliation run (lifecycle §5).

    Fact IDs and outcomes only — never raw claim IDs (the K stale-storm
    guard); this is the `evidence_changed` payload shape.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reconciliation_id: UUID
    transitions: int = 0
    recounted_relations: tuple[UUID, ...] = ()
    recounted_observations: tuple[UUID, ...] = ()
    relations_closed: tuple[UUID, ...] = ()
    observations_closed: tuple[UUID, ...] = ()
    flags_raised: tuple[UUID, ...] = ()
