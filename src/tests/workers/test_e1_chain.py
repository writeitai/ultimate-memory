"""WP-1.2 acceptance: structure → chunk → embed, chunks in Postgres and in Lance.

The full walking-skeleton chain runs against real PostgreSQL, a local-FS
artifact store, an embedded Lance dataset, and the deterministic fake model
provider (the ports are the seam — no network).
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.adapters.selfhost import LanceChunkIndex
from ultimate_memory.adapters.selfhost import LocalFSObjectStore
from ultimate_memory.adapters.testing import FakeModelProvider
from ultimate_memory.core import CHUNKER_VERSION
from ultimate_memory.core import ChunkerParams
from ultimate_memory.core import ConversionRouter
from ultimate_memory.core import MarkdownPassthroughConverter
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.model import DocumentUpload
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import ProcessingLane
from ultimate_memory.model import RunResultOutcome
from ultimate_memory.spine import ChunkCatalog
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import DocumentCatalog
from ultimate_memory.spine import WorkLedger
from ultimate_memory.spine import WorkLedgerSettings
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import ChunkHandler
from ultimate_memory.workers import ConvertHandler
from ultimate_memory.workers import E1Settings
from ultimate_memory.workers import EmbedChunksHandler
from ultimate_memory.workers import HandlerRegistry
from ultimate_memory.workers import StructureHandler
from ultimate_memory.workers import UploadIngestor
from ultimate_memory.workers import Worker

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("70000000-0000-0000-0000-000000000001")

_SOURCE = "\n\n".join(
    f"Paragraph {index} states a distinct fact about subsystem {index}."
    for index in range(30)
)


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL integration engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real PostgreSQL chain proofs")
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
    """Give every proof a fresh deployment (all E-plane rows FK onto it)."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
        connection.execute(statement=text("TRUNCATE TABLE chunks"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="e1-chain-test",
            name="E1 chain proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )


class _E1Rig:
    """The composed walking-skeleton chain through the embed stage."""

    def __init__(self, *, engine: Engine, root: Path) -> None:
        """Compose E0 + E1 over one database, one store root, and the fakes."""
        self.engine = engine
        raw_store = LocalFSObjectStore(root=root / "raw")
        artifact_store = LocalFSObjectStore(root=root / "artifacts")
        self.chunk_index = LanceChunkIndex(root=root / "lance")
        self.provider = FakeModelProvider(
            generate_payload={"prefix": "Sits early in the test document."}
        )
        document_catalog = DocumentCatalog(engine=engine)
        self.chunk_catalog = ChunkCatalog(engine=engine)
        ledger = WorkLedger(
            engine=engine,
            settings=WorkLedgerSettings(
                retry_backoff_base_s=0.0, retry_backoff_max_s=0.0
            ),
        )
        self.ingestor = UploadIngestor(catalog=document_catalog, raw_store=raw_store)
        registry = HandlerRegistry()
        registry.register(
            stage=PipelineStage.CONVERT,
            handler=ConvertHandler(
                catalog=document_catalog,
                raw_store=raw_store,
                artifact_store=artifact_store,
                router=ConversionRouter(
                    routes={"text/markdown": MarkdownPassthroughConverter()}
                ),
            ),
        )
        registry.register(
            stage=PipelineStage.STRUCTURE,
            handler=StructureHandler(
                catalog=document_catalog, artifact_store=artifact_store
            ),
        )
        registry.register(
            stage=PipelineStage.CHUNK,
            handler=ChunkHandler(
                catalog=self.chunk_catalog,
                artifact_store=artifact_store,
                params=ChunkerParams(token_budget=40),
            ),
        )
        registry.register(
            stage=PipelineStage.EMBED_CHUNK,
            handler=EmbedChunksHandler(
                catalog=self.chunk_catalog,
                artifact_store=artifact_store,
                model_provider=self.provider,
                chunk_index=self.chunk_index,
                settings=E1Settings(),
            ),
        )
        self.worker = Worker(ledger=ledger, registry=registry)

    def run(self, *, stage: PipelineStage) -> RunResultOutcome:
        """Run at most one unit of the stage on the steady lane."""
        return self.worker.run_one(
            deployment_id=_DEPLOYMENT_ID, stage=stage, lane=ProcessingLane.STEADY
        ).outcome

    def run_chain(self) -> None:
        """Drive one document through convert → structure → chunk → embed."""
        for stage in (
            PipelineStage.CONVERT,
            PipelineStage.STRUCTURE,
            PipelineStage.CHUNK,
            PipelineStage.EMBED_CHUNK,
        ):
            assert self.run(stage=stage) is RunResultOutcome.SUCCEEDED, stage


@pytest.fixture()
def rig(database_engine: Engine, tmp_path: Path) -> _E1Rig:
    """A fresh composed chain per proof."""
    return _E1Rig(engine=database_engine, root=tmp_path)


def test_document_reaches_lance_with_prefixed_embeddings(rig: _E1Rig) -> None:
    """The WP-1.2 acceptance: deterministic repack keys in PG, chunks in Lance."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="skeleton.md",
            mime="text/markdown",
            content=_SOURCE.encode("utf-8"),
        ),
    )
    rig.run_chain()

    with rig.engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT ordinal, block_start, block_end, token_count,"
                    " chunk_content_hash, extraction_input_hash, chunker_version,"
                    " context_prefix, prefixer_version, embedding_ref,"
                    " embedding_version, char_start, char_end"
                    " FROM chunks WHERE version_id = :version_id ORDER BY ordinal"
                ),
                {"version_id": ingested.version_id},
            )
            .mappings()
            .all()
        )
    assert len(rows) > 1
    covered: list[int] = []
    for row in rows:
        covered.extend(range(row["block_start"], row["block_end"] + 1))
        assert row["chunker_version"] == CHUNKER_VERSION
        assert row["context_prefix"] == "Sits early in the test document."
        assert row["embedding_ref"] is not None
        assert row["embedding_version"] == "qwen/qwen3-embedding-8b"
        assert _SOURCE[row["char_start"] : row["char_end"]].strip()
    assert covered == list(range(covered[-1] + 1))  # gap-free partition

    assert rig.chunk_index.row_count() == len(rows)
    # the embedded text is prefix + verbatim chunk body (conventional mode, D63):
    assert all(
        embedded.startswith("Sits early in the test document.\n\n")
        for embedded in rig.provider.embedded_texts
    )
    assert len(rig.provider.generated_prompts) == len(rows)


def test_rerunning_the_chunk_stage_replays_the_stored_packing(
    rig: _E1Rig, tmp_path: Path
) -> None:
    """D7 replay: a second chunk run for the version keeps rows and re-chains."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="skeleton.md",
            mime="text/markdown",
            content=_SOURCE.encode("utf-8"),
        ),
    )
    rig.run_chain()
    first_ids = rig.chunk_catalog.existing_chunk_ids(
        version_id=ingested.version_id, chunker_version=CHUNKER_VERSION
    )

    representation = None
    with rig.engine.connect() as connection:
        representation = connection.execute(
            text(
                "SELECT current_representation_id FROM document_versions"
                " WHERE version_id = :version_id"
            ),
            {"version_id": ingested.version_id},
        ).scalar_one()

    from ultimate_memory.model import ClaimedWork
    from ultimate_memory.model import ProcessingTarget
    from ultimate_memory.workers import E1_CHUNK_VERSION

    handler = ChunkHandler(
        catalog=rig.chunk_catalog,
        # an empty store: any artifact read would raise, proving pure replay
        artifact_store=LocalFSObjectStore(root=tmp_path / "empty-store"),
        params=ChunkerParams(token_budget=40),
    )
    replay = handler.handle(
        work=ClaimedWork(
            processing_id=ingested.version_id,
            deployment_id=_DEPLOYMENT_ID,
            target_kind=ProcessingTarget.DOCUMENT,
            target_id=ingested.doc_id,
            stage=PipelineStage.CHUNK,
            component_version=E1_CHUNK_VERSION,
            content_hash=ingested.content_hash,
            lane=ProcessingLane.STEADY,
            attempt=1,
            payload={
                "version_id": str(ingested.version_id),
                "representation_id": str(representation),
            },
        )
    )
    # the replay never re-read artifacts (nonexistent store) and kept the rows:
    assert replay.follow_up[0].stage is PipelineStage.EMBED_CHUNK
    second_ids = rig.chunk_catalog.existing_chunk_ids(
        version_id=ingested.version_id, chunker_version=CHUNKER_VERSION
    )
    assert second_ids == first_ids


def test_empty_document_chains_through_with_nothing_to_index(rig: _E1Rig) -> None:
    """An empty upload completes the whole chain without a degenerate chunk."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(filename="empty.md", mime="text/markdown", content=b""),
    )
    rig.run_chain()
    with rig.engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM chunks WHERE version_id = :version_id"),
            {"version_id": ingested.version_id},
        ).scalar_one()
    assert count == 0
    assert rig.chunk_index.row_count() == 0
