"""Typed records for the D67 work ledger: enqueue, claim, attempt, and cost rows."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from ultimate_memory.model.queue import PipelineStage
from ultimate_memory.model.queue import ProcessingLane
from ultimate_memory.model.queue import UTCDateTime


class ProcessingTarget(StrEnum):
    """Exact values of the binding Postgres ``processing_target`` enum."""

    DOCUMENT = "document"
    DOCUMENT_VERSION = "document_version"
    DOCUMENT_SECTION = "document_section"
    CHUNK = "chunk"
    CLAIM = "claim"
    RELATION = "relation"
    OBSERVATION = "observation"
    ENTITY = "entity"
    SNAPSHOT = "snapshot"
    KNOWLEDGE_ARTIFACT = "knowledge_artifact"


class ProcessingStatus(StrEnum):
    """Exact values of the binding Postgres ``processing_status`` enum."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    SKIPPED = "skipped"


class DeferReason(StrEnum):
    """Exact values of the binding Postgres ``processing_defer_reason`` enum (D67)."""

    SCHEDULED = "scheduled"
    RETRY_BACKOFF = "retry_backoff"
    BUDGET = "budget"


class EnqueueWork(BaseModel):
    """One unit of work to insert into ``processing_state`` (D12 idempotency key)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    target_kind: ProcessingTarget
    target_id: UUID
    stage: PipelineStage
    component_version: str
    content_hash: str
    lane: ProcessingLane | None
    payload: dict[str, object] | None = None
    not_before: UTCDateTime | None = None


class EnqueueOutcome(BaseModel):
    """What an enqueue did: created a row, promoted its lane, or found it existing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    processing_id: UUID
    created: bool
    promoted_to_steady: bool


class ClaimedWork(BaseModel):
    """A claimed ``processing_state`` row, running its ``attempt``-th handler execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    processing_id: UUID
    deployment_id: UUID
    target_kind: ProcessingTarget
    target_id: UUID
    stage: PipelineStage
    component_version: str
    content_hash: str
    lane: ProcessingLane | None
    attempt: int = Field(ge=1)
    payload: dict[str, object] | None


class RecordCall(BaseModel):
    """One billed model/provider call to attribute to the claimed row's attempt.

    Attribution fields (stage, lane, attempt) are copied from the locked
    ``processing_state`` row by the spine and can never be supplied here (D67).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    processing_id: UUID
    call_key: str
    model_name: str | None = None
    tier: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None


class RunResultOutcome(StrEnum):
    """How one worker pass ended for the row it claimed (or that none was due)."""

    NO_WORK = "no_work"
    SUCCEEDED = "succeeded"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"


class WorkLedgerError(Exception):
    """Base error for work-ledger operations."""


class LaneRouteError(WorkLedgerError):
    """A lane value that is illegal for the stage's route (D67 pairing rule)."""


class WorkNotFoundError(WorkLedgerError):
    """A ``processing_id`` that does not exist in ``processing_state``."""


class WorkNotRunningError(WorkLedgerError):
    """An operation that requires a running attempt hit a non-running row."""


class NonRetryableHandlerError(Exception):
    """A handler failure classified as permanent: the work dead-letters immediately."""


class HandlerAlreadyRegisteredError(Exception):
    """A second handler registration for a stage that already has one."""


class UnknownStageHandlerError(Exception):
    """A claimed stage with no registered handler."""
