"""Public readiness is derived from exact work and projection rows."""

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

from rememberstack.model import DeploymentBootstrapInput
from rememberstack.model import PipelineStage
from rememberstack.spine import DeploymentBootstrapper
from rememberstack.spine import PipelineReadinessCatalog
from rememberstack.spine import ProjectionCatalog
from rememberstack.spine.settings import load_database_settings

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("59000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head against the real PostgreSQL acceptance database."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("REMEMBERSTACK_DATABASE_URL is required for readiness proofs")
    config = Config(str(_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config=config, revision="base")
    command.upgrade(config=config, revision="head")
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def ready_rows(database_engine: Engine) -> tuple[Engine, UUID]:
    """One version with two exact succeeded generations and fresh P2/P3."""
    with database_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="readiness",
            name="Readiness",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )
    version_id = uuid4()
    finished = datetime.now(tz=UTC) - timedelta(minutes=1)
    with database_engine.begin() as connection:
        for stage, component in (("convert", "convert-v1"), ("structure", "struct-v1")):
            connection.execute(
                text(
                    "INSERT INTO processing_state (processing_id, deployment_id,"
                    " target_kind, target_id, stage, component_version, content_hash,"
                    " lane, status, attempts, finished_at)"
                    " VALUES (:p, :d, 'document_version', :v,"
                    " CAST(:s AS pipeline_stage), :c, 'hash', 'steady',"
                    " 'succeeded', 1, :finished)"
                ),
                {
                    "p": uuid4(),
                    "d": _DEPLOYMENT_ID,
                    "v": version_id,
                    "s": stage,
                    "c": component,
                    "finished": finished,
                },
            )
        for plane in ("P2_graph", "P3_corpusfs"):
            connection.execute(
                text(
                    "INSERT INTO projection_snapshots (snapshot_id, deployment_id,"
                    " plane, version, gcs_uri, status, is_latest, published_at)"
                    " VALUES (:p, :d, CAST(:plane AS projection_plane), 'v1',"
                    " 'mem://snapshot', 'published', true, now())"
                ),
                {"p": uuid4(), "d": _DEPLOYMENT_ID, "plane": plane},
            )
    return database_engine, version_id


def test_exact_terminal_stages_and_fresh_projections_are_ready(
    ready_rows: tuple[Engine, UUID],
) -> None:
    engine, version_id = ready_rows
    report = PipelineReadinessCatalog(
        engine=engine,
        expected_components={
            PipelineStage.CONVERT: "convert-v1",
            PipelineStage.STRUCTURE: "struct-v1",
        },
        projections=ProjectionCatalog(engine=engine),
        model_bindings={"claim_extraction": "model-v1"},
    ).inspect(
        deployment_id=_DEPLOYMENT_ID,
        version_ids=(version_id,),
        require_projections=True,
    )

    assert report.ready is True
    assert report.versions[0].ready is True
    assert all(projection.ready for projection in report.projections)
    assert report.model_bindings == {"claim_extraction": "model-v1"}


def test_a_missing_exact_generation_is_not_ready(
    ready_rows: tuple[Engine, UUID],
) -> None:
    engine, version_id = ready_rows
    report = PipelineReadinessCatalog(
        engine=engine,
        expected_components={
            PipelineStage.CONVERT: "convert-v1",
            PipelineStage.STRUCTURE: "different-generation",
        },
        projections=ProjectionCatalog(engine=engine),
    ).inspect(
        deployment_id=_DEPLOYMENT_ID,
        version_ids=(version_id,),
        require_projections=True,
    )

    assert report.ready is False
    assert report.versions[0].stages[1].status == "missing"


def test_a_projection_started_before_terminal_work_is_not_fresh(
    ready_rows: tuple[Engine, UUID],
) -> None:
    engine, version_id = ready_rows
    with engine.begin() as connection:
        terminal_at = connection.execute(
            text(
                "SELECT max(finished_at) FROM processing_state"
                " WHERE deployment_id = :deployment_id AND target_id = :version_id"
            ),
            {"deployment_id": _DEPLOYMENT_ID, "version_id": version_id},
        ).scalar_one()
        connection.execute(
            text(
                "UPDATE projection_snapshots SET built_at = :built_at,"
                " published_at = now()"
                " WHERE deployment_id = :deployment_id AND plane = 'P2_graph'"
            ),
            {
                "built_at": terminal_at - timedelta(seconds=1),
                "deployment_id": _DEPLOYMENT_ID,
            },
        )

    report = PipelineReadinessCatalog(
        engine=engine,
        expected_components={
            PipelineStage.CONVERT: "convert-v1",
            PipelineStage.STRUCTURE: "struct-v1",
        },
        projections=ProjectionCatalog(engine=engine),
    ).inspect(
        deployment_id=_DEPLOYMENT_ID,
        version_ids=(version_id,),
        require_projections=True,
    )

    assert report.ready is False
    assert report.projections[0].plane == "P2_graph"
    assert report.projections[0].ready is False


def test_terminal_status_without_a_completion_timestamp_fails_closed(
    ready_rows: tuple[Engine, UUID],
) -> None:
    """Projection freshness requires a timestamp from every terminal stage."""
    engine, version_id = ready_rows
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE processing_state SET finished_at = NULL"
                " WHERE deployment_id = :deployment_id"
                " AND target_id = :version_id AND stage = 'structure'"
            ),
            {"deployment_id": _DEPLOYMENT_ID, "version_id": version_id},
        )

    report = PipelineReadinessCatalog(
        engine=engine,
        expected_components={
            PipelineStage.CONVERT: "convert-v1",
            PipelineStage.STRUCTURE: "struct-v1",
        },
        projections=ProjectionCatalog(engine=engine),
    ).inspect(
        deployment_id=_DEPLOYMENT_ID,
        version_ids=(version_id,),
        require_projections=True,
    )

    assert report.ready is False
    assert report.versions[0].ready is False
    assert report.versions[0].stages[1].status == "succeeded"
    assert report.versions[0].stages[1].finished_at is None
