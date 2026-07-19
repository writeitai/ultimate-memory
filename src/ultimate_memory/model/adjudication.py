"""Supersession-adjudication values (D3/D4): verdicts and transcript entries."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from ultimate_memory.model.queue import UTCDateTime


class SupersessionOutcome(StrEnum):
    """The adjudicator's three answers about a blocked pair (D4)."""

    SUPERSEDE = "supersede"  # the world changed: close the old window
    COEXIST = "coexist"  # both hold simultaneously: no change
    CONTRADICT = "contradict"  # same period, incompatible: both stand, grouped


class SupersessionVerdict(BaseModel):
    """The adjudication call's structured output for one blocked pair."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: SupersessionOutcome
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    rationale: str | None = None


class RelationUpsert(BaseModel):
    """What one relation upsert did: the row and whether it was new."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation_id: UUID
    created: bool


class TranscriptEntry(BaseModel):
    """One append-only decision record, as the `transcript` primitive returns it.

    The audit trail is uniform across the four subjects a decision can be
    about (S8/S32/S35): a supersession-adjudicated relation or observation,
    a resolved/merged entity, or a compiled K page. `subject_kind` says
    which, and `related_id` points at the counterpart the decision paired
    the subject with — the other relation/observation in a supersede pair,
    the entity absorbed in a merge, or the compilation's artifact — so an
    agent can walk from any decision to what it acted on.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_kind: str  # relation | observation | entity | k_page
    outcome: str
    method: str
    confidence: float | None
    related_id: UUID | None
    decided_by: str
    decided_at: UTCDateTime
    features: dict[str, object] | None


class ObservationOutcome(StrEnum):
    """The observation adjudicator's answers about a blocked pair (D43)."""

    EVIDENCE = "evidence"  # same property + value: collapse onto the prior
    SUPERSEDE = "supersede"  # a changing state moved on: cap the prior
    CONTRADICT = "contradict"  # same property + period, incompatible: both stand
    NEW = "new"  # different property/period/thing: no interaction


class ObservationVerdict(BaseModel):
    """The observation adjudication call's structured output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ObservationOutcome
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    rationale: str | None = None


class ReviewItem(BaseModel):
    """One open review-queue item as the CLI lists it (D24)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: UUID
    item_kind: str
    candidate: dict[str, object]
    blast_radius: int
    confidence: float
    expected_impact: float
    status: str
    created_at: UTCDateTime


class ReviewDecisionError(Exception):
    """A verdict that does not fit the item (wrong kind, closed, unknown)."""
