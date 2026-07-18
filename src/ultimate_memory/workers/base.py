"""The handler-registration model and the worker runner (WP-0.3, D12/D52/D67).

A stage handler transforms one claimed unit of work and names its chain
follow-ups; the runner is the single exception boundary (core value 6): a
handler failure is logged with its full traceback, recorded on the row, and
either retried with backoff or dead-lettered — it never disappears.
"""

import logging
import traceback
from typing import Protocol
from typing import runtime_checkable
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict

from ultimate_memory.model import ClaimedWork
from ultimate_memory.model import EnqueueWork
from ultimate_memory.model import HandlerAlreadyRegisteredError
from ultimate_memory.model import NonRetryableHandlerError
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import ProcessingLane
from ultimate_memory.model import RunResultOutcome
from ultimate_memory.model import UnknownStageHandlerError
from ultimate_memory.spine.work_ledger import WorkLedger

_logger = logging.getLogger(__name__)


class HandlerOutcome(BaseModel):
    """What a successful handler produced: the chain follow-ups to enqueue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    follow_up: tuple[EnqueueWork, ...] = ()


@runtime_checkable
class StageHandler(Protocol):
    """One stage's transformation over one claimed unit of work."""

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Process the claimed work and return its chain follow-ups.

        Raise `NonRetryableHandlerError` for permanent failures (the work
        dead-letters immediately); any other exception is a retryable failure.
        """
        ...


class RunResult(BaseModel):
    """What one runner pass did: which row it ran and how the attempt ended."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    processing_id: UUID | None
    outcome: RunResultOutcome


class HandlerRegistry:
    """Exactly one handler per stage; registration conflicts are typed errors."""

    def __init__(self) -> None:
        """Start empty; stages register at composition time (profiles own wiring)."""
        self._handlers: dict[PipelineStage, StageHandler] = {}

    def register(self, *, stage: PipelineStage, handler: StageHandler) -> None:
        """Bind a handler to a stage; a second binding for the stage is an error."""
        if stage in self._handlers:
            raise HandlerAlreadyRegisteredError(
                f"stage {stage} already has a registered handler"
            )
        self._handlers[stage] = handler

    def handler_for(self, *, stage: PipelineStage) -> StageHandler:
        """Return the stage's handler; an unregistered stage is a typed error."""
        handler = self._handlers.get(stage)
        if handler is None:
            raise UnknownStageHandlerError(f"no handler registered for stage {stage}")
        return handler


class Worker:
    """Claims due work on one route and runs its handler behind one error boundary."""

    def __init__(self, *, ledger: WorkLedger, registry: HandlerRegistry) -> None:
        """Bind the runner to its ledger and its handler registry."""
        self._ledger = ledger
        self._registry = registry

    def run_one(
        self, *, deployment_id: UUID, stage: PipelineStage, lane: ProcessingLane | None
    ) -> RunResult:
        """Claim and run at most one due unit of work on the route.

        This is the worker's single catch-to-log boundary (core value 6): the
        full traceback is logged and recorded on the row; a
        `NonRetryableHandlerError` dead-letters immediately, anything else
        retries with backoff until the attempt limit dead-letters it.
        """
        claimed = self._ledger.claim_one(
            deployment_id=deployment_id, stage=stage, lane=lane
        )
        if claimed is None:
            return RunResult(processing_id=None, outcome=RunResultOutcome.NO_WORK)
        handler = self._registry.handler_for(stage=claimed.stage)
        try:
            outcome = handler.handle(work=claimed)
        except NonRetryableHandlerError:
            _logger.exception(
                "non-retryable failure in stage %s for %s",
                claimed.stage,
                claimed.processing_id,
            )
            self._ledger.fail(
                processing_id=claimed.processing_id,
                error=traceback.format_exc(),
                retryable=False,
            )
            return RunResult(
                processing_id=claimed.processing_id,
                outcome=RunResultOutcome.DEAD_LETTERED,
            )
        except Exception:
            _logger.exception(
                "retryable failure in stage %s for %s",
                claimed.stage,
                claimed.processing_id,
            )
            retry_scheduled = self._ledger.fail(
                processing_id=claimed.processing_id,
                error=traceback.format_exc(),
                retryable=True,
            )
            return RunResult(
                processing_id=claimed.processing_id,
                outcome=RunResultOutcome.RETRY_SCHEDULED
                if retry_scheduled
                else RunResultOutcome.DEAD_LETTERED,
            )
        self._ledger.complete(
            processing_id=claimed.processing_id, follow_up=outcome.follow_up
        )
        return RunResult(
            processing_id=claimed.processing_id, outcome=RunResultOutcome.SUCCEEDED
        )
