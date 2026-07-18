"""Transactional operations on the D67 work ledger (processing_state + cost_ledger).

The ledger is the sole work-truth (D12/D67): enqueue is idempotent on the
(deployment, target, stage, component version) key; claiming uses SKIP LOCKED
over the (deployment, stage, lane) route; attempts count handler executions that
actually began; failures keep their full traceback; the DLQ is
status='dead_letter' rows; billed calls copy their attribution from the locked
running row and callers can never supply it.
"""

from datetime import datetime
from uuid import UUID
from uuid import uuid4

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from sqlalchemy import bindparam
from sqlalchemy import Connection
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import RowMapping

from ultimate_memory.model import ClaimedWork
from ultimate_memory.model import EnqueueOutcome
from ultimate_memory.model import EnqueueWork
from ultimate_memory.model import LaneRouteError
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import ProcessingLane
from ultimate_memory.model import RecordCall
from ultimate_memory.model import WorkNotFoundError
from ultimate_memory.model import WorkNotRunningError
from ultimate_memory.spine.catalog_contract import lane_is_valid


class WorkLedgerSettings(BaseSettings):
    """Retry-backoff configuration for failed handler attempts (D67 starting points)."""

    model_config = SettingsConfigDict(env_prefix="UGM_WORK_", extra="ignore")

    retry_backoff_base_s: float = 2.0
    retry_backoff_max_s: float = 60.0


class WorkLedger:
    """The spine's typed gateway to processing_state and cost_ledger (D12/D67)."""

    def __init__(self, *, engine: Engine, settings: WorkLedgerSettings) -> None:
        """Bind the ledger to an explicit engine and explicit settings."""
        self._engine = engine
        self._settings = settings

    def enqueue(self, *, work: EnqueueWork) -> EnqueueOutcome:
        """Insert one unit of work idempotently and return what happened.

        A duplicate of an existing (deployment, target, stage, version) key never
        creates a second unit of work. A steady enqueue promotes a pending/failed
        backfill duplicate to the steady lane (live work keeps its freshness
        guarantee); a backfill enqueue can never demote steady work (D67).
        """
        _require_valid_lane(stage=work.stage, lane=work.lane)
        with self._engine.begin() as connection:
            return _enqueue_on(connection=connection, work=work)

    def claim_one(
        self, *, deployment_id: UUID, stage: PipelineStage, lane: ProcessingLane | None
    ) -> ClaimedWork | None:
        """Claim the next due row on one route, or return None when nothing is due.

        Claiming locks the row (SKIP LOCKED), clears any defer reason, moves it to
        running, and increments attempts exactly once immediately before the
        handler begins — delivery wake-ups without a claim never consume attempts.
        """
        _require_valid_lane(stage=stage, lane=lane)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    _CLAIM_SELECT,
                    {"deployment_id": deployment_id, "stage": stage, "lane": lane},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            started = (
                connection.execute(
                    _CLAIM_START, {"processing_id": row["processing_id"]}
                )
                .mappings()
                .one()
            )
            return _claimed_work(row=started)

    def complete(
        self, *, processing_id: UUID, follow_up: tuple[EnqueueWork, ...] = ()
    ) -> tuple[EnqueueOutcome, ...]:
        """Mark a running attempt succeeded and enqueue its chain follow-ups atomically.

        The chain rule (a completing stage enqueues the next stage for its target)
        commits in the same transaction as the success mark, so a crash can never
        record success without the follow-up work existing.
        """
        for work in follow_up:
            _require_valid_lane(stage=work.stage, lane=work.lane)
        with self._engine.begin() as connection:
            updated = connection.execute(
                _COMPLETE, {"processing_id": processing_id}
            ).rowcount
            if updated == 0:
                raise WorkNotRunningError(
                    f"processing row {processing_id} is not running; cannot complete"
                )
            return tuple(
                _enqueue_on(connection=connection, work=work) for work in follow_up
            )

    def fail(self, *, processing_id: UUID, error: str, retryable: bool) -> bool:
        """Record a failed attempt with its full traceback; never bury it (core value 6).

        A retryable failure with attempts remaining schedules a retry backoff
        (status failed, defer_reason retry_backoff, not_before in the future) and
        returns True. A failure at the attempt limit, or a non-retryable one,
        dead-letters the row and returns False.
        """
        with self._engine.begin() as connection:
            row = (
                connection.execute(_SELECT_FOR_FAIL, {"processing_id": processing_id})
                .mappings()
                .first()
            )
            if row is None:
                raise WorkNotFoundError(
                    f"processing row {processing_id} does not exist"
                )
            if row["status"] != "running":
                raise WorkNotRunningError(
                    f"processing row {processing_id} is not running; cannot fail it"
                )
            attempts, max_attempts = int(row["attempts"]), int(row["max_attempts"])
            if retryable and attempts < max_attempts:
                backoff_s = min(
                    self._settings.retry_backoff_base_s * 2 ** (attempts - 1),
                    self._settings.retry_backoff_max_s,
                )
                connection.execute(
                    _FAIL_RETRY,
                    {
                        "processing_id": processing_id,
                        "error": error,
                        "backoff_s": backoff_s,
                    },
                )
                return True
            connection.execute(
                _FAIL_DEAD_LETTER, {"processing_id": processing_id, "error": error}
            )
            return False

    def park_for_budget(self, *, processing_id: UUID, resume_at: datetime) -> None:
        """Park healthy pending work until its budget window rolls (D67).

        Parking happens at claim-time pre-flight, before an attempt starts: it
        applies only to pending rows (a running attempt is never parked — that
        would allow a second concurrent claim), sets defer_reason budget with a
        future not_before, consumes no attempt, and touches no error state, so
        it can never cause dead-lettering.
        """
        with self._engine.begin() as connection:
            updated = connection.execute(
                _PARK_BUDGET, {"processing_id": processing_id, "resume_at": resume_at}
            ).rowcount
            if updated == 0:
                raise WorkNotRunningError(
                    f"processing row {processing_id} is not pending; only queued "
                    "work can be budget-parked"
                )

    def record_call(self, *, call: RecordCall) -> bool:
        """Attribute one billed call to the running attempt; idempotent per call key.

        Stage, lane, attempt, and target attribution are copied from the locked
        running row (D67) — a caller or delivery envelope can never choose them.
        Returns False when the (processing, attempt, call_key) row already exists,
        so an acknowledged-late retry cannot double-bill.
        """
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    _SELECT_FOR_COST, {"processing_id": call.processing_id}
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkNotFoundError(
                    f"processing row {call.processing_id} does not exist"
                )
            if row["status"] != "running":
                raise WorkNotRunningError(
                    f"processing row {call.processing_id} is not running; "
                    "cost attribution requires a running attempt"
                )
            inserted = connection.execute(
                _INSERT_COST,
                {
                    "cost_id": uuid4(),
                    "deployment_id": row["deployment_id"],
                    "processing_id": call.processing_id,
                    "stage": row["stage"],
                    "lane": row["lane"],
                    "target_kind": row["target_kind"],
                    "target_id": row["target_id"],
                    "component_version": row["component_version"],
                    "attempt": row["attempts"],
                    "call_key": call.call_key,
                    "model_name": call.model_name,
                    "tier": call.tier,
                    "tokens_in": call.tokens_in,
                    "tokens_out": call.tokens_out,
                    "cost_usd": call.cost_usd,
                    "latency_ms": call.latency_ms,
                },
            ).rowcount
            return inserted == 1


def _require_valid_lane(*, stage: PipelineStage, lane: ProcessingLane | None) -> None:
    """Reject a lane value that is illegal for the stage's route (D67 pairing)."""
    if not lane_is_valid(stage=stage, lane=None if lane is None else lane.value):
        raise LaneRouteError(
            f"stage {stage} does not accept lane {lane!r}: plane-E stages require "
            "steady or backfill; scheduled K/P stages must be unlaned"
        )


def _enqueue_on(*, connection: Connection, work: EnqueueWork) -> EnqueueOutcome:
    """Run the idempotent insert (+ steady-promotion rule) on an open transaction."""
    inserted = (
        connection.execute(
            _INSERT_WORK,
            {
                "processing_id": uuid4(),
                "deployment_id": work.deployment_id,
                "target_kind": work.target_kind,
                "target_id": work.target_id,
                "stage": work.stage,
                "component_version": work.component_version,
                "content_hash": work.content_hash,
                "lane": work.lane,
                "payload": work.payload,
                "not_before": work.not_before,
            },
        )
        .mappings()
        .first()
    )
    if inserted is not None:
        return EnqueueOutcome(
            processing_id=inserted["processing_id"],
            created=True,
            promoted_to_steady=False,
        )
    existing = (
        connection.execute(
            _SELECT_EXISTING,
            {
                "deployment_id": work.deployment_id,
                "target_kind": work.target_kind,
                "target_id": work.target_id,
                "stage": work.stage,
                "component_version": work.component_version,
            },
        )
        .mappings()
        .one()
    )
    promoted = False
    if (
        work.lane is ProcessingLane.STEADY
        and existing["lane"] == ProcessingLane.BACKFILL.value
        and existing["status"] in ("pending", "failed")
    ):
        promoted = (
            connection.execute(
                _PROMOTE_TO_STEADY, {"processing_id": existing["processing_id"]}
            ).rowcount
            == 1
        )
    return EnqueueOutcome(
        processing_id=existing["processing_id"],
        created=False,
        promoted_to_steady=promoted,
    )


def _claimed_work(*, row: RowMapping) -> ClaimedWork:
    """Build the typed claimed-work record from a returned ledger row."""
    return ClaimedWork(
        processing_id=row["processing_id"],
        deployment_id=row["deployment_id"],
        target_kind=row["target_kind"],
        target_id=row["target_id"],
        stage=row["stage"],
        component_version=row["component_version"],
        content_hash=row["content_hash"],
        lane=None if row["lane"] is None else ProcessingLane(row["lane"]),
        attempt=int(row["attempts"]),
        payload=row["payload"],
    )


_INSERT_WORK = text(
    """
    INSERT INTO processing_state (
        processing_id, deployment_id, target_kind, target_id, stage,
        component_version, content_hash, lane, payload, not_before
    ) VALUES (
        :processing_id, :deployment_id, :target_kind, :target_id, :stage,
        :component_version, :content_hash, :lane,
        :payload, COALESCE(:not_before, now())
    )
    ON CONFLICT (deployment_id, target_kind, target_id, stage, component_version)
    DO NOTHING
    RETURNING processing_id
    """
).bindparams(bindparam("payload", type_=JSON))

_SELECT_EXISTING = text(
    """
    SELECT processing_id, lane, status
    FROM processing_state
    WHERE deployment_id = :deployment_id
      AND target_kind = :target_kind
      AND target_id = :target_id
      AND stage = :stage
      AND component_version = :component_version
    """
)

_PROMOTE_TO_STEADY = text(
    """
    UPDATE processing_state
    SET lane = 'steady'
    WHERE processing_id = :processing_id
      AND lane = 'backfill'
      AND status IN ('pending', 'failed')
    """
)

_CLAIM_SELECT = text(
    """
    SELECT processing_id
    FROM processing_state
    WHERE deployment_id = :deployment_id
      AND stage = :stage
      AND lane IS NOT DISTINCT FROM :lane
      AND status IN ('pending', 'failed')
      AND not_before <= now()
      AND attempts < max_attempts
    ORDER BY not_before, enqueued_at, processing_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
    """
)

_CLAIM_START = text(
    """
    UPDATE processing_state
    SET status = 'running',
        defer_reason = NULL,
        attempts = attempts + 1,
        started_at = now()
    WHERE processing_id = :processing_id
    RETURNING processing_id, deployment_id, target_kind, target_id, stage,
              component_version, content_hash, lane, attempts, payload
    """
)

_COMPLETE = text(
    """
    UPDATE processing_state
    SET status = 'succeeded', finished_at = now()
    WHERE processing_id = :processing_id AND status = 'running'
    """
)

_SELECT_FOR_FAIL = text(
    """
    SELECT status, attempts, max_attempts
    FROM processing_state
    WHERE processing_id = :processing_id
    FOR UPDATE
    """
)

_FAIL_RETRY = text(
    """
    UPDATE processing_state
    SET status = 'failed',
        defer_reason = 'retry_backoff',
        not_before = now() + make_interval(secs => :backoff_s),
        last_error = :error
    WHERE processing_id = :processing_id
    """
)

_FAIL_DEAD_LETTER = text(
    """
    UPDATE processing_state
    SET status = 'dead_letter',
        defer_reason = NULL,
        last_error = :error,
        finished_at = now()
    WHERE processing_id = :processing_id
    """
)

_PARK_BUDGET = text(
    """
    UPDATE processing_state
    SET defer_reason = 'budget', not_before = :resume_at
    WHERE processing_id = :processing_id AND status = 'pending'
    """
)

_SELECT_FOR_COST = text(
    """
    SELECT deployment_id, status, stage, lane, attempts,
           target_kind, target_id, component_version
    FROM processing_state
    WHERE processing_id = :processing_id
    FOR UPDATE
    """
)

_INSERT_COST = text(
    """
    INSERT INTO cost_ledger (
        cost_id, deployment_id, processing_id, stage, lane, target_kind,
        target_id, component_version, attempt, call_key, model_name, tier,
        tokens_in, tokens_out, cost_usd, latency_ms
    ) VALUES (
        :cost_id, :deployment_id, :processing_id, :stage, :lane, :target_kind,
        :target_id, :component_version, :attempt, :call_key, :model_name, :tier,
        :tokens_in, :tokens_out, :cost_usd, :latency_ms
    )
    ON CONFLICT (deployment_id, processing_id, attempt, call_key) DO NOTHING
    """
)
