"""WP-3.1/3.2 acceptance: versioned ingest + the watch loop, end to end.

A watched directory drives the full lifecycle front door: cycle rows, the
no-fetch revision no-op, the debounce window, a changed file becoming a new
VERSION of its lineage (the full chain runs on it, the old version
superseded), and source deletion tombstoning the lineage — loud, recorded.
"""

from collections.abc import Iterator
import os
from pathlib import Path
import time
from uuid import UUID

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.adapters.selfhost import LocalDirectoryWatcher
from ultimate_memory.adapters.selfhost import LocalFSObjectStore
from ultimate_memory.core import ConversionRouter
from ultimate_memory.core import MarkdownPassthroughConverter
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import ProcessingLane
from ultimate_memory.model import RunResultOutcome
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import DocumentCatalog
from ultimate_memory.spine import SyncCatalog
from ultimate_memory.spine import WorkLedger
from ultimate_memory.spine import WorkLedgerSettings
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import ConvertHandler
from ultimate_memory.workers import HandlerRegistry
from ultimate_memory.workers import StructureHandler
from ultimate_memory.workers import SyncCycleRunner
from ultimate_memory.workers import SyncSettings
from ultimate_memory.workers import UploadIngestor
from ultimate_memory.workers import Worker

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("c1000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL integration engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real PostgreSQL watch proofs")
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
    """A fresh deployment per proof."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="watch-test",
            name="Watch loop proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )


class _WatchRig:
    """A watched directory + the E0 chain + the cycle runner."""

    def __init__(self, *, engine: Engine, root: Path) -> None:
        """Compose the watcher, ingest path, and the convert/structure chain."""
        self.engine = engine
        self.source_dir = root / "watched"
        self.watcher = LocalDirectoryWatcher(root=self.source_dir)
        raw_store = LocalFSObjectStore(root=root / "raw")
        artifact_store = LocalFSObjectStore(root=root / "artifacts")
        catalog = DocumentCatalog(engine=engine)
        self.runner = SyncCycleRunner(
            catalog=SyncCatalog(engine=engine),
            ingestor=UploadIngestor(catalog=catalog, raw_store=raw_store),
            settings=SyncSettings(debounce_quiet_seconds=0.0),
        )
        registry = HandlerRegistry()
        registry.register(
            stage=PipelineStage.CONVERT,
            handler=ConvertHandler(
                catalog=catalog,
                raw_store=raw_store,
                artifact_store=artifact_store,
                router=ConversionRouter(
                    routes={"text/markdown": MarkdownPassthroughConverter()}
                ),
            ),
        )
        registry.register(
            stage=PipelineStage.STRUCTURE,
            handler=StructureHandler(catalog=catalog, artifact_store=artifact_store),
        )
        self.worker = Worker(
            ledger=WorkLedger(
                engine=engine,
                settings=WorkLedgerSettings(
                    retry_backoff_base_s=0.0, retry_backoff_max_s=0.0
                ),
            ),
            registry=registry,
        )

    def cycle(self):
        """One recorded poll pass."""
        return self.runner.run_cycle(
            deployment_id=_DEPLOYMENT_ID,
            source_kind="watched_directory",
            source=self.watcher,
        )

    def drain_e0(self) -> None:
        """Run convert + structure until idle."""
        for stage in (PipelineStage.CONVERT, PipelineStage.STRUCTURE):
            while (
                self.worker.run_one(
                    deployment_id=_DEPLOYMENT_ID,
                    stage=stage,
                    lane=ProcessingLane.STEADY,
                ).outcome
                is not RunResultOutcome.NO_WORK
            ):
                pass

    def write(self, *, name: str, content: str, mtime_offset: float = -300.0) -> None:
        """Write a source file, backdated past the debounce window."""
        path = self.source_dir / name
        path.write_text(content)
        stamp = time.time() + mtime_offset
        os.utime(path, (stamp, stamp))


@pytest.fixture()
def rig(database_engine: Engine, tmp_path: Path) -> _WatchRig:
    """A fresh watched rig per proof."""
    return _WatchRig(engine=database_engine, root=tmp_path)


def test_edit_becomes_a_new_version_of_the_same_lineage(rig: _WatchRig) -> None:
    """The D55 heart: same source_ref across edits = one lineage, two
    versions; the chain runs on each; the old version is superseded when
    the new becomes current; no-op cycles ingest nothing."""
    rig.write(name="roster.md", content="# Roster\n\nAlice leads the team.\n")
    first = rig.cycle()
    assert len(first.ingested) == 1
    rig.drain_e0()

    # an unchanged poll: revision no-op — nothing fetched, nothing ingested
    second = rig.cycle()
    assert second.ingested == ()
    assert second.unchanged == 1

    rig.write(name="roster.md", content="# Roster\n\nBob leads the team.\n")
    third = rig.cycle()
    assert len(third.ingested) == 1
    rig.drain_e0()

    with rig.engine.connect() as connection:
        lineages = connection.execute(
            text(
                "SELECT count(*) FROM documents WHERE deployment_id = :d"
                " AND source_kind = 'watched_directory'"
            ),
            {"d": _DEPLOYMENT_ID},
        ).scalar_one()
        versions = (
            connection.execute(
                text(
                    "SELECT version_no, status::text AS status, superseded_at,"
                    " sync_cycle_id, source_modified_at"
                    " FROM document_versions ORDER BY version_no"
                )
            )
            .mappings()
            .all()
        )
        mode = connection.execute(
            text(
                "SELECT versioning_mode::text FROM documents WHERE source_kind ="
                " 'watched_directory'"
            )
        ).scalar_one()
        current = connection.execute(
            text(
                "SELECT v.version_no FROM documents d"
                " JOIN document_versions v ON v.version_id = d.current_version_id"
                " WHERE d.source_kind = 'watched_directory'"
            )
        ).scalar_one()
    assert lineages == 1  # one lineage across the edit
    assert [row["version_no"] for row in versions] == [1, 2]
    assert versions[0]["superseded_at"] is not None  # v1 superseded
    assert versions[1]["superseded_at"] is None
    assert all(row["status"] == "ready" for row in versions)
    assert all(row["sync_cycle_id"] is not None for row in versions)
    assert all(row["source_modified_at"] is not None for row in versions)
    assert mode == "living"  # the edit-in-place heuristic
    assert current == 2


def test_debounce_coalesces_active_edits(rig: _WatchRig) -> None:
    """A freshly modified file waits out the quiet window."""
    rig.runner._settings = SyncSettings(debounce_quiet_seconds=3600.0)  # noqa: SLF001
    rig.write(name="live.md", content="editing right now\n", mtime_offset=-1.0)
    summary = rig.cycle()
    assert summary.debounced == 1
    assert summary.ingested == ()
    # once quiet long enough, the next cycle ingests exactly one version:
    rig.write(name="live.md", content="editing right now\n", mtime_offset=-7200.0)
    settled = rig.cycle()
    assert len(settled.ingested) == 1


def test_source_deletion_tombstones_the_lineage(rig: _WatchRig) -> None:
    """Delete observed → the lineage is tombstoned (audit-visible), and the
    observation is idempotent across cycles."""
    rig.write(name="gone.md", content="short-lived\n")
    rig.cycle()
    (rig.source_dir / "gone.md").unlink()
    removal = rig.cycle()
    assert len(removal.deletions_observed) == 1
    again = rig.cycle()
    assert again.deletions_observed == ()  # already tombstoned: no re-fire
    with rig.engine.connect() as connection:
        deleted_at = connection.execute(
            text("SELECT deleted_at FROM documents WHERE source_ref = 'gone.md'")
        ).scalar_one()
        cycles = connection.execute(
            text(
                "SELECT count(*) FROM connector_sync_cycles"
                " WHERE completed_at IS NOT NULL"
            )
        ).scalar_one()
    assert deleted_at is not None
    assert cycles >= 3  # every pass recorded and completed
