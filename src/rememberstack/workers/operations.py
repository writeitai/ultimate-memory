"""Thin operational services that compose spine truth with delivery ports."""

from datetime import datetime
from uuid import UUID

from rememberstack.model import DeadLetterReplayResult
from rememberstack.model import ProcessingLane
from rememberstack.ports.queue import TaskQueuePort
from rememberstack.spine.work_ledger import WorkLedger


class DeadLetterReplayer:
    """Replay one row through the ledger, then announce its committed route."""

    def __init__(self, *, ledger: WorkLedger, queue: TaskQueuePort) -> None:
        """Bind authoritative mutation and non-authoritative delivery."""
        self._ledger = ledger
        self._queue = queue

    def replay(
        self,
        *,
        deployment_id: UUID,
        processing_id: UUID,
        attempt_allowance: int = 1,
        lane: ProcessingLane | None = None,
        not_before: datetime | None = None,
    ) -> DeadLetterReplayResult:
        """Commit one explicit replay transition, then wake its returned route."""
        replayed = self._ledger.replay_dead_letter(
            deployment_id=deployment_id,
            processing_id=processing_id,
            attempt_allowance=attempt_allowance,
            lane=lane,
            not_before=not_before,
        )
        self._queue.announce(
            processing_id=replayed.processing_id,
            route_snapshot=replayed.route,
            not_before_snapshot=replayed.not_before,
        )
        return replayed
