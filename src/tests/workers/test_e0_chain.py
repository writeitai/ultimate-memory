"""WP-1.1 acceptance: one document end to end through the minimal E0 chain.

Upload → ingest (raw bytes + rows + convert work, atomically) → convert
(document.md + blocks.json + representation) → structure (synthetic root +
currency flip). Proven against real PostgreSQL and a local-FS object store.
"""

from collections.abc import Iterator
import json
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.adapters import MarkitdownConverter
from ultimate_memory.adapters.selfhost import LocalFSObjectStore
from ultimate_memory.adapters.testing import FakeModelProvider
from ultimate_memory.core import blockize
from ultimate_memory.core import ConversionRouter
from ultimate_memory.core import MarkdownPassthroughConverter
from ultimate_memory.model import ClaimedWork
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.model import DocumentUpload
from ultimate_memory.model import ObjectKey
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import ProcessingLane
from ultimate_memory.model import ProcessingTarget
from ultimate_memory.model import RunResultOutcome
from ultimate_memory.model import SectionTreeRecord
from ultimate_memory.model import SnappedSection
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import DocumentCatalog
from ultimate_memory.spine import WorkLedger
from ultimate_memory.spine import WorkLedgerSettings
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import ConvertHandler
from ultimate_memory.workers import E0_CONVERT_VERSION
from ultimate_memory.workers import HandlerRegistry
from ultimate_memory.workers import StructureHandler
from ultimate_memory.workers import StructurerSettings
from ultimate_memory.workers import UploadIngestor
from ultimate_memory.workers import Worker

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("60000000-0000-0000-0000-000000000001")

_MARKDOWN_SOURCE = "# Quarterly report\n\nRevenue grew nine percent.\n\n- steady\n"


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
    """Give every proof a fresh deployment (all E0 rows FK onto it)."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="e0-chain-test",
            name="E0 chain proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )


class _E0Rig:
    """One composed E0 chain: ingestor, worker, stores, and the spine handles."""

    def __init__(self, *, engine: Engine, root: Path) -> None:
        """Compose the full minimal chain over one database and one store root."""
        self.engine = engine
        self.raw_store = LocalFSObjectStore(root=root / "raw")
        self.artifact_store = LocalFSObjectStore(root=root / "artifacts")
        self.catalog = DocumentCatalog(engine=engine)
        self.ledger = WorkLedger(
            engine=engine,
            settings=WorkLedgerSettings(
                retry_backoff_base_s=0.0, retry_backoff_max_s=0.0
            ),
        )
        self.ingestor = UploadIngestor(catalog=self.catalog, raw_store=self.raw_store)
        router = ConversionRouter(
            routes={
                "text/markdown": MarkdownPassthroughConverter(),
                "text/plain": MarkdownPassthroughConverter(),
                "text/html": MarkitdownConverter(),
            }
        )
        registry = HandlerRegistry()
        registry.register(
            stage=PipelineStage.CONVERT,
            handler=ConvertHandler(
                catalog=self.catalog,
                raw_store=self.raw_store,
                artifact_store=self.artifact_store,
                router=router,
            ),
        )
        registry.register(
            stage=PipelineStage.STRUCTURE,
            handler=StructureHandler(
                catalog=self.catalog, artifact_store=self.artifact_store
            ),
        )
        self.worker = Worker(ledger=self.ledger, registry=registry)

    def run(self, *, stage: PipelineStage) -> RunResultOutcome:
        """Run at most one unit of the stage on the steady lane."""
        return self.worker.run_one(
            deployment_id=_DEPLOYMENT_ID, stage=stage, lane=ProcessingLane.STEADY
        ).outcome

    def row(self, *, sql: str, params: dict[str, object]) -> dict[str, object]:
        """Fetch exactly one row as a plain dict."""
        with self.engine.connect() as connection:
            return dict(connection.execute(text(sql), params).mappings().one())


@pytest.fixture()
def rig(database_engine: Engine, tmp_path: Path) -> _E0Rig:
    """A fresh composed chain per proof."""
    return _E0Rig(engine=database_engine, root=tmp_path)


def test_markdown_document_end_to_end(rig: _E0Rig) -> None:
    """The WP-1.1 acceptance: doc → document.md + blocks.json + rows, all ready."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="report.md",
            mime="text/markdown",
            content=_MARKDOWN_SOURCE.encode("utf-8"),
        ),
    )
    assert ingested.created

    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.SUCCEEDED
    assert rig.run(stage=PipelineStage.STRUCTURE) is RunResultOutcome.SUCCEEDED

    version = rig.row(
        sql="SELECT * FROM document_versions WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    assert version["status"] == "ready"
    assert version["current_representation_id"] is not None

    representation = rig.row(
        sql="SELECT * FROM document_representations WHERE representation_id = :rid",
        params={"rid": version["current_representation_id"]},
    )
    assert representation["status"] == "ready"
    assert representation["route"] == "passthrough"

    markdown = rig.artifact_store.read_bytes(
        key=ObjectKey(str(representation["markdown_uri"]))
    ).decode("utf-8")
    assert markdown == _MARKDOWN_SOURCE

    blocks_doc = json.loads(
        rig.artifact_store.read_bytes(key=ObjectKey(str(representation["blocks_uri"])))
    )
    expected = blockize(document_md=_MARKDOWN_SOURCE)
    assert blocks_doc["block_count"] == len(expected)
    assert [b["block_hash"] for b in blocks_doc["blocks"]] == [
        block.block_hash for block in expected
    ]

    section = rig.row(
        sql="SELECT * FROM document_sections WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    assert section["role"] == "body"
    assert section["node_path"] == "0"
    assert section["char_start"] == 0
    assert section["char_end"] == len(_MARKDOWN_SOURCE)
    assert section["block_end"] == len(expected) - 1

    lineage = rig.row(
        sql="SELECT * FROM documents WHERE doc_id = :doc_id",
        params={"doc_id": ingested.doc_id},
    )
    assert lineage["current_version_id"] == ingested.version_id
    assert lineage["title"] == "report"

    raw = rig.raw_store.read_bytes(
        key=ObjectKey(f"{ingested.doc_id}/{ingested.content_hash}/original.md")
    )
    assert raw == _MARKDOWN_SOURCE.encode("utf-8")


def test_identical_bytes_reingested_are_a_no_op(rig: _E0Rig) -> None:
    """The D55 content-hash no-op: same bytes → same lineage, version, and work."""
    upload = DocumentUpload(
        filename="report.md",
        mime="text/markdown",
        content=_MARKDOWN_SOURCE.encode("utf-8"),
    )
    first = rig.ingestor.ingest(deployment_id=_DEPLOYMENT_ID, upload=upload)
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.SUCCEEDED
    assert rig.run(stage=PipelineStage.STRUCTURE) is RunResultOutcome.SUCCEEDED

    second = rig.ingestor.ingest(deployment_id=_DEPLOYMENT_ID, upload=upload)
    assert not second.created
    assert second.doc_id == first.doc_id
    assert second.version_id == first.version_id

    counts = rig.row(
        sql="""
        SELECT (SELECT count(*) FROM documents) AS lineages,
               (SELECT count(*) FROM document_versions) AS versions,
               (SELECT count(*) FROM document_representations) AS representations
        """,
        params={},
    )
    assert counts == {"lineages": 1, "versions": 1, "representations": 1}
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.NO_WORK


def test_html_document_converts_through_markitdown(rig: _E0Rig) -> None:
    """The markitdown route: html in, clean Markdown out, route recorded."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="notes.html",
            mime="text/html",
            content=b"<html><body><h1>Atlas kickoff</h1><p>Notes body.</p></body></html>",
        ),
    )
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.SUCCEEDED
    assert rig.run(stage=PipelineStage.STRUCTURE) is RunResultOutcome.SUCCEEDED

    version = rig.row(
        sql="SELECT * FROM document_versions WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    representation = rig.row(
        sql="SELECT * FROM document_representations WHERE representation_id = :rid",
        params={"rid": version["current_representation_id"]},
    )
    assert representation["route"] == "markitdown"
    markdown = rig.artifact_store.read_bytes(
        key=ObjectKey(str(representation["markdown_uri"]))
    ).decode("utf-8")
    assert "# Atlas kickoff" in markdown
    assert "Notes body." in markdown


def test_unroutable_mime_dead_letters_without_retries(rig: _E0Rig) -> None:
    """No route for the MIME type is deterministic — one attempt, dead-lettered."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="blob.bin", mime="application/x-unknown", content=b"\x00\x01\x02"
        ),
    )
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.DEAD_LETTERED

    work = rig.row(
        sql="""
        SELECT status, attempts, last_error FROM processing_state
        WHERE target_id = :version_id AND stage = 'convert'
        """,
        params={"version_id": ingested.version_id},
    )
    assert work["status"] == "dead_letter"
    assert work["attempts"] == 1
    assert "application/x-unknown" in str(work["last_error"])

    version = rig.row(
        sql="SELECT status, error FROM document_versions WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    assert version["status"] == "failed"
    assert "application/x-unknown" in str(version["error"])


def test_retried_convert_replays_the_stored_representation(rig: _E0Rig) -> None:
    """Codex review: D65 replay-not-regenerate — a retry never re-converts."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="report.md",
            mime="text/markdown",
            content=_MARKDOWN_SOURCE.encode("utf-8"),
        ),
    )
    handler = ConvertHandler(
        catalog=rig.catalog,
        raw_store=rig.raw_store,
        artifact_store=rig.artifact_store,
        router=ConversionRouter(
            routes={"text/markdown": MarkdownPassthroughConverter()}
        ),
    )
    work = ClaimedWork(
        processing_id=ingested.version_id,
        deployment_id=_DEPLOYMENT_ID,
        target_kind=ProcessingTarget.DOCUMENT,
        target_id=ingested.doc_id,
        stage=PipelineStage.CONVERT,
        component_version=E0_CONVERT_VERSION,
        content_hash=ingested.content_hash,
        lane=ProcessingLane.STEADY,
        attempt=1,
        payload={"version_id": str(ingested.version_id)},
    )
    first = handler.handle(work=work)
    replay = handler.handle(work=work)  # the retried attempt
    assert replay.follow_up[0].payload == first.follow_up[0].payload

    count = rig.row(
        sql="SELECT count(*) AS representations FROM document_representations",
        params={},
    )
    assert count == {"representations": 1}


def test_stale_structure_never_overwrites_the_live_representation(rig: _E0Rig) -> None:
    """Codex review: the pointer swap is first-writer-wins — sections and the
    live-reading pointer can never disagree about the coordinate system."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="report.md",
            mime="text/markdown",
            content=_MARKDOWN_SOURCE.encode("utf-8"),
        ),
    )
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.SUCCEEDED
    assert rig.run(stage=PipelineStage.STRUCTURE) is RunResultOutcome.SUCCEEDED
    version = rig.row(
        sql="SELECT current_representation_id FROM document_versions"
        " WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    live = version["current_representation_id"]

    from uuid import uuid4

    from ultimate_memory.model import SyntheticRootRecord
    from ultimate_memory.workers import E0_STRUCTURE_VERSION

    stale_rep = uuid4()
    with rig.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO document_representations (representation_id,"
                " deployment_id, version_id, route, status)"
                " VALUES (:rid, :dep, :vid, 'passthrough', 'structuring')"
            ),
            {"rid": stale_rep, "dep": _DEPLOYMENT_ID, "vid": ingested.version_id},
        )
    rig.catalog.record_synthetic_root(
        record=SyntheticRootRecord(
            deployment_id=_DEPLOYMENT_ID,
            doc_id=ingested.doc_id,
            version_id=ingested.version_id,
            representation_id=stale_rep,
            block_count=3,
            markdown_chars=len(_MARKDOWN_SOURCE),
            title="stale",
            structurer_version=E0_STRUCTURE_VERSION,
        )
    )
    after = rig.row(
        sql="SELECT current_representation_id FROM document_versions"
        " WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    assert after["current_representation_id"] == live
    section = rig.row(
        sql="SELECT representation_id FROM document_sections"
        " WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    assert section["representation_id"] == live


def test_empty_document_gets_an_empty_root_span(rig: _E0Rig) -> None:
    """Codex review: zero blocks persist as the empty inclusive range 0..-1."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(filename="empty.md", mime="text/markdown", content=b""),
    )
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.SUCCEEDED
    assert rig.run(stage=PipelineStage.STRUCTURE) is RunResultOutcome.SUCCEEDED
    section = rig.row(
        sql="SELECT block_start, block_end, char_start, char_end, role"
        " FROM document_sections WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    assert section == {
        "block_start": 0,
        "block_end": -1,
        "char_start": 0,
        "char_end": 0,
        "role": "body",
    }


_STRUCTURED_SOURCE = "\n\n".join(
    (
        "# Field report",
        "The survey covered twelve sites.",
        "Each site was visited twice.",
        "## Findings",
        "Nine sites showed erosion.",
        "Three sites were stable.",
        "## Recommendations",
        "Revisit eroded sites yearly.",
        "Publish the dataset.",
    )
)


def _structure_worker(rig: _E0Rig, provider: object) -> Worker:
    """A worker whose structure stage runs the full LLM route."""
    registry = HandlerRegistry()
    registry.register(
        stage=PipelineStage.STRUCTURE,
        handler=StructureHandler(
            catalog=rig.catalog,
            artifact_store=rig.artifact_store,
            model_provider=provider,  # type: ignore[arg-type]
            settings=StructurerSettings(min_blocks_for_llm=3),
        ),
    )
    return Worker(ledger=rig.ledger, registry=registry)


def test_full_structure_route_persists_the_snapped_tree(rig: _E0Rig) -> None:
    """WP-3.3: the LLM proposal lands as a snapped multi-section tree — rows
    with parent links and sanitized roles, placement on the root, and the
    pageindex.json sidecar next to document.md."""
    findings = _STRUCTURED_SOURCE.index("## Findings")
    recommendations = _STRUCTURED_SOURCE.index("## Recommendations")
    provider = FakeModelProvider(
        generate_payloads={
            "StructureResponse": {
                "placement": "/surveys/field-reports/",
                "sections": [
                    {
                        "title": "Findings",
                        "role": "results",
                        "char_start": findings,
                        "char_end": recommendations,
                        "summary": "What the survey found.",
                    },
                    {
                        "title": "Recommendations",
                        "role": "ACTION_ITEMS",  # invented: must degrade to body
                        "char_start": recommendations,
                        "char_end": len(_STRUCTURED_SOURCE),
                    },
                ],
            }
        }
    )
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="survey.md",
            mime="text/markdown",
            content=_STRUCTURED_SOURCE.encode("utf-8"),
        ),
    )
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.SUCCEEDED
    worker = _structure_worker(rig, provider)
    outcome = worker.run_one(
        deployment_id=_DEPLOYMENT_ID,
        stage=PipelineStage.STRUCTURE,
        lane=ProcessingLane.STEADY,
    ).outcome
    assert outcome is RunResultOutcome.SUCCEEDED

    with rig.engine.connect() as connection:
        sections = (
            connection.execute(
                text(
                    "SELECT node_path, parent_section_id, section_id, title,"
                    " role::text AS role, block_start, block_end, placement_path"
                    " FROM document_sections WHERE version_id = :version_id"
                    " ORDER BY ordinal"
                ),
                {"version_id": ingested.version_id},
            )
            .mappings()
            .all()
        )
        structurer = connection.execute(
            text(
                "SELECT structurer_name FROM document_representations"
                " WHERE version_id = :version_id"
            ),
            {"version_id": ingested.version_id},
        ).scalar_one()
    assert [row["node_path"] for row in sections] == ["0", "0.0", "0.1"]
    root, first, second = sections
    assert root["placement_path"] == "/surveys/field-reports/"
    assert first["parent_section_id"] == root["section_id"]
    assert second["parent_section_id"] == root["section_id"]
    assert first["role"] == "results"
    assert second["role"] == "body"  # the invented role degraded
    assert first["block_end"] == second["block_start"] - 1  # tiled partition
    assert structurer == "pageindex_llm"

    representation = rig.row(
        sql="SELECT blocks_uri FROM document_representations"
        " WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    sidecar_key = str(representation["blocks_uri"]).rsplit("/", 1)[0]
    sidecar = json.loads(
        rig.artifact_store.read_bytes(key=ObjectKey(f"{sidecar_key}/pageindex.json"))
    )
    assert sidecar["placement"] == "/surveys/field-reports/"
    assert len(sidecar["sections"]) == 3


def test_failed_structurer_degrades_to_the_synthetic_root(rig: _E0Rig) -> None:
    """A dead model seat never fails a document — the root serves it."""

    class _DeadProvider:
        def generate(self, *, request: object, response_type: object) -> object:
            raise ConnectionError("model gateway down")

        def embed(self, *, request: object) -> object:
            raise NotImplementedError

    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="survey.md",
            mime="text/markdown",
            content=_STRUCTURED_SOURCE.encode("utf-8"),
        ),
    )
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.SUCCEEDED
    worker = _structure_worker(rig, _DeadProvider())
    outcome = worker.run_one(
        deployment_id=_DEPLOYMENT_ID,
        stage=PipelineStage.STRUCTURE,
        lane=ProcessingLane.STEADY,
    ).outcome
    assert outcome is RunResultOutcome.SUCCEEDED
    section = rig.row(
        sql="SELECT node_path, role::text AS role FROM document_sections"
        " WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    assert section == {"node_path": "0", "role": "body"}


def test_retried_tree_write_returns_the_first_attempts_truth(rig: _E0Rig) -> None:
    """Codex review: a retry whose (fresher) LLM proposal differs must not
    win — rows keep the first tree, the catalog returns it, and the sidecar
    is derived from that persisted truth."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="report.md",
            mime="text/markdown",
            content=_STRUCTURED_SOURCE.encode("utf-8"),
        ),
    )
    assert rig.run(stage=PipelineStage.CONVERT) is RunResultOutcome.SUCCEEDED
    representation = rig.row(
        sql="SELECT representation_id FROM document_representations"
        " WHERE version_id = :version_id",
        params={"version_id": ingested.version_id},
    )
    representation_id = representation["representation_id"]

    def _record(title: str) -> SectionTreeRecord:
        return SectionTreeRecord(
            deployment_id=_DEPLOYMENT_ID,
            doc_id=ingested.doc_id,
            version_id=ingested.version_id,
            representation_id=representation_id,  # type: ignore[arg-type]
            sections=(
                SnappedSection(
                    node_path="0",
                    parent_path=None,
                    title=title,
                    role="body",
                    block_start=0,
                    block_end=8,
                    char_start=0,
                    char_end=len(_STRUCTURED_SOURCE),
                    summary="",
                    ordinal=0,
                ),
            ),
            placement_path=f"/{title}/",
            structurer_name="pageindex_llm",
            structurer_version="test-structurer",
        )

    first = rig.catalog.record_section_tree(record=_record("first"))
    retry = rig.catalog.record_section_tree(record=_record("second"))
    assert first.sections[0].title == "first"
    assert retry.sections[0].title == "first"  # the first attempt's row won
    assert retry.placement_path == "/first/"
