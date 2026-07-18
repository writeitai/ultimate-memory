"""Real-PostgreSQL proofs for the D67 work ledger and the WP-0.3 no-op worker chain."""

from collections.abc import Iterator
from datetime import datetime
from datetime import timedelta
from datetime import UTC
from pathlib import Path
from uuid import UUID
from uuid import uuid4

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.model import ClaimedWork
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.model import EnqueueWork
from ultimate_memory.model import LaneRouteError
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import ProcessingLane
from ultimate_memory.model import ProcessingTarget
from ultimate_memory.model import RecordCall
from ultimate_memory.model import WorkNotRunningError
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import WorkLedger
from ultimate_memory.spine import WorkLedgerSettings
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import HandlerOutcome
from ultimate_memory.workers import HandlerRegistry
from ultimate_memory.workers import Worker

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("30000000-0000-0000-0000-000000000001")
_VERSION = "worker-test-2026-07"


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL integration engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real PostgreSQL ledger proofs")

    config = Config(str(_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config=config, revision="base")
    command.upgrade(config=config, revision="head")

    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def bootstrapped_deployment(database_engine: Engine) -> None:
    """Give every proof a fresh deployment (processing rows FK onto it)."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="worker-test",
            name="Worker ledger proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )


@pytest.fixture()
def ledger(database_engine: Engine) -> WorkLedger:
    """A ledger with zero retry backoff so retries are immediately claimable."""
    return WorkLedger(
        engine=database_engine,
        settings=WorkLedgerSettings(retry_backoff_base_s=0.0, retry_backoff_max_s=0.0),
    )


def _work(
    *,
    stage: PipelineStage = PipelineStage.EXTRACT_CLAIMS,
    lane: ProcessingLane | None = ProcessingLane.STEADY,
    target_id: UUID | None = None,
) -> EnqueueWork:
    """One enqueueable unit of work with a stable default shape."""
    return EnqueueWork(
        deployment_id=_DEPLOYMENT_ID,
        target_kind=ProcessingTarget.CHUNK,
        target_id=target_id or uuid4(),
        stage=stage,
        component_version=_VERSION,
        content_hash="sha256:test",
        lane=lane,
    )


def test_enqueue_is_idempotent_and_promotes_backfill_to_steady(
    ledger: WorkLedger,
) -> None:
    """The D12 key admits one unit of work; steady promotes a pending backfill row."""
    target_id = uuid4()
    first = ledger.enqueue(
        work=_work(lane=ProcessingLane.BACKFILL, target_id=target_id)
    )
    duplicate = ledger.enqueue(
        work=_work(lane=ProcessingLane.BACKFILL, target_id=target_id)
    )
    promoted = ledger.enqueue(
        work=_work(lane=ProcessingLane.STEADY, target_id=target_id)
    )

    assert first.created and not first.promoted_to_steady
    assert not duplicate.created and not duplicate.promoted_to_steady
    assert not promoted.created and promoted.promoted_to_steady
    assert promoted.processing_id == first.processing_id

    demote_attempt = ledger.enqueue(
        work=_work(lane=ProcessingLane.BACKFILL, target_id=target_id)
    )
    assert not demote_attempt.created and not demote_attempt.promoted_to_steady
    claimed = ledger.claim_one(
        deployment_id=_DEPLOYMENT_ID,
        stage=PipelineStage.EXTRACT_CLAIMS,
        lane=ProcessingLane.STEADY,
    )
    assert claimed is not None and claimed.processing_id == first.processing_id


def test_lane_pairing_is_enforced_at_enqueue_and_claim(ledger: WorkLedger) -> None:
    """The D67 pairing rule rejects laned K/P work and unlaned plane-E work."""
    with pytest.raises(LaneRouteError):
        ledger.enqueue(work=_work(stage=PipelineStage.EXTRACT_CLAIMS, lane=None))
    with pytest.raises(LaneRouteError):
        ledger.enqueue(
            work=_work(
                stage=PipelineStage.COMPILE_KNOWLEDGE, lane=ProcessingLane.STEADY
            )
        )
    with pytest.raises(LaneRouteError):
        ledger.claim_one(
            deployment_id=_DEPLOYMENT_ID,
            stage=PipelineStage.COMPILE_KNOWLEDGE,
            lane=ProcessingLane.BACKFILL,
        )


def test_cost_attribution_is_copied_from_the_running_row(
    database_engine: Engine, ledger: WorkLedger
) -> None:
    """A billed call copies stage/lane/attempt from the claimed row, idempotently."""
    ledger.enqueue(work=_work())
    claimed = ledger.claim_one(
        deployment_id=_DEPLOYMENT_ID,
        stage=PipelineStage.EXTRACT_CLAIMS,
        lane=ProcessingLane.STEADY,
    )
    assert claimed is not None

    call = RecordCall(
        processing_id=claimed.processing_id, call_key="selection", cost_usd=0.01
    )
    assert ledger.record_call(call=call) is True
    assert ledger.record_call(call=call) is False  # ack-lost retry cannot double-bill

    with database_engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT stage, lane, attempt FROM cost_ledger"
                    " WHERE processing_id = :processing_id"
                ),
                {"processing_id": claimed.processing_id},
            )
            .mappings()
            .one()
        )
    assert row["stage"] == PipelineStage.EXTRACT_CLAIMS.value
    assert row["lane"] == ProcessingLane.STEADY.value
    assert row["attempt"] == 1

    ledger.complete(processing_id=claimed.processing_id)
    with pytest.raises(WorkNotRunningError):
        ledger.record_call(
            call=RecordCall(processing_id=claimed.processing_id, call_key="late")
        )


def test_budget_parking_consumes_no_attempt_and_keeps_no_error(
    database_engine: Engine, ledger: WorkLedger
) -> None:
    """Parking is pending + defer_reason budget + future not_before, nothing else."""
    enqueued = ledger.enqueue(work=_work())
    ledger.park_for_budget(
        processing_id=enqueued.processing_id,
        resume_at=datetime.now(tz=UTC) + timedelta(hours=1),
    )
    with database_engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT status, defer_reason, attempts, last_error"
                    " FROM processing_state WHERE processing_id = :processing_id"
                ),
                {"processing_id": enqueued.processing_id},
            )
            .mappings()
            .one()
        )
    assert row["status"] == "pending"
    assert row["defer_reason"] == "budget"
    assert row["attempts"] == 0
    assert row["last_error"] is None
    assert (
        ledger.claim_one(
            deployment_id=_DEPLOYMENT_ID,
            stage=PipelineStage.EXTRACT_CLAIMS,
            lane=ProcessingLane.STEADY,
        )
        is None
    )  # parked work is not due


def test_running_work_can_never_be_budget_parked(ledger: WorkLedger) -> None:
    """Parking a running attempt would allow a second concurrent claim — refused."""
    ledger.enqueue(work=_work())
    claimed = ledger.claim_one(
        deployment_id=_DEPLOYMENT_ID,
        stage=PipelineStage.EXTRACT_CLAIMS,
        lane=ProcessingLane.STEADY,
    )
    assert claimed is not None
    with pytest.raises(WorkNotRunningError):
        ledger.park_for_budget(
            processing_id=claimed.processing_id,
            resume_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )


class _ChainingNoOpHandler:
    """The demo no-op handler: succeeds and chains the next stage for its target."""

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Produce the chain follow-up without doing any real work."""
        return HandlerOutcome(
            follow_up=(
                EnqueueWork(
                    deployment_id=work.deployment_id,
                    target_kind=work.target_kind,
                    target_id=work.target_id,
                    stage=PipelineStage.EMBED_CHUNK,
                    component_version=work.component_version,
                    content_hash=work.content_hash,
                    lane=work.lane,
                ),
            )
        )


class _AlwaysFailingHandler:
    """A handler whose every execution raises — exercising retry then dead-letter."""

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Fail unconditionally with a real traceback."""
        raise RuntimeError(f"deliberate failure for {work.processing_id}")


def test_demo_no_op_worker_chain_retry_and_dead_letter(
    database_engine: Engine, ledger: WorkLedger
) -> None:
    """WP-0.3 acceptance: enqueue → run → state row + chain → retry → dead-letter."""
    registry = HandlerRegistry()
    registry.register(
        stage=PipelineStage.EXTRACT_CLAIMS, handler=_ChainingNoOpHandler()
    )
    registry.register(stage=PipelineStage.EMBED_CHUNK, handler=_AlwaysFailingHandler())
    worker = Worker(ledger=ledger, registry=registry)

    target_id = uuid4()
    ledger.enqueue(work=_work(target_id=target_id))

    success = worker.run_one(
        deployment_id=_DEPLOYMENT_ID,
        stage=PipelineStage.EXTRACT_CLAIMS,
        lane=ProcessingLane.STEADY,
    )
    assert success.outcome == "succeeded"

    outcomes = [
        worker.run_one(
            deployment_id=_DEPLOYMENT_ID,
            stage=PipelineStage.EMBED_CHUNK,
            lane=ProcessingLane.STEADY,
        ).outcome
        for _ in range(4)
    ]
    assert outcomes == [
        "retry_scheduled",
        "retry_scheduled",
        "dead_lettered",
        "no_work",
    ]

    with database_engine.connect() as connection:
        rows = {
            row["stage"]: row
            for row in connection.execute(
                text(
                    "SELECT stage, status, attempts, last_error"
                    " FROM processing_state WHERE target_id = :target_id"
                ),
                {"target_id": target_id},
            ).mappings()
        }
    assert rows["extract_claims"]["status"] == "succeeded"
    dead = rows["embed_chunk"]
    assert dead["status"] == "dead_letter"
    assert dead["attempts"] == 3  # initial + two retries (D12/D67)
    assert "RuntimeError: deliberate failure" in dead["last_error"]
    assert "Traceback" in dead["last_error"]  # full traceback, never trimmed (value 6)
