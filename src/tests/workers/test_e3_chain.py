"""WP-1.4 acceptance: claims normalize into facts — same fact twice = one row,
evidence_count = 1 (lineage-distinct, D54). Full chain, deterministic fakes."""

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
from ultimate_memory.core import chunker_version
from ultimate_memory.core import ChunkerParams
from ultimate_memory.core import ConversionRouter
from ultimate_memory.core import MarkdownPassthroughConverter
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.model import DocumentUpload
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import ProcessingLane
from ultimate_memory.model import RunResultOutcome
from ultimate_memory.spine import ChunkCatalog
from ultimate_memory.spine import ClaimCatalog
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import DocumentCatalog
from ultimate_memory.spine import EntityRegistry
from ultimate_memory.spine import FactCatalog
from ultimate_memory.spine import WorkLedger
from ultimate_memory.spine import WorkLedgerSettings
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import ChunkHandler
from ultimate_memory.workers import ConvertHandler
from ultimate_memory.workers import E1Settings
from ultimate_memory.workers import E2Settings
from ultimate_memory.workers import E3Settings
from ultimate_memory.workers import EmbedChunksHandler
from ultimate_memory.workers import EmbedClaimsHandler
from ultimate_memory.workers import ExtractClaimsHandler
from ultimate_memory.workers import HandlerRegistry
from ultimate_memory.workers import LabelFactsHandler
from ultimate_memory.workers import NormalizeRelationsHandler
from ultimate_memory.workers import P1Settings
from ultimate_memory.workers import StructureHandler
from ultimate_memory.workers import UploadIngestor
from ultimate_memory.workers import Worker

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("90000000-0000-0000-0000-000000000001")
_PARAMS = ChunkerParams(token_budget=400)

_SOURCE = (
    "Alice Novak joined Acme in 2024. Alice Novak works for Acme as an engineer.\n"
)

_SELECTION_PAYLOAD: dict[str, object] = {
    "candidates": [
        {"source_span": "Alice Novak joined Acme in 2024.", "verdict": "keep"},
        {
            "source_span": "Alice Novak works for Acme as an engineer.",
            "verdict": "keep",
        },
    ]
}

_CLAIMIFY_PAYLOAD: dict[str, object] = {
    "claims": [
        {
            "claim_text": "Alice Novak joined Acme in 2024.",
            "source_span": "Alice Novak joined Acme in 2024.",
            "entailment_self_verdict": True,
        },
        {
            "claim_text": "Alice Novak works for Acme.",
            "source_span": "Alice Novak works for Acme as an engineer.",
            "entailment_self_verdict": True,
        },
    ]
}

# The SAME normalizer output for BOTH claims — the D2/D54 collapse proof: one
# relation row, two evidence links, ONE lineage-distinct count. Plus one
# candidate with an invented predicate and one failing the D18 signature gate,
# both of which must be dropped, and one observation (a value about Acme).
_NORMALIZATION_PAYLOAD: dict[str, object] = {
    "relations": [
        {
            "subject": {"name": "Alice Novak", "type": "Person"},
            "predicate": "works_for",
            "object": {"name": "Acme", "type": "Organization"},
        },
        {
            "subject": {"name": "Alice Novak", "type": "Person"},
            "predicate": "invented_predicate",
            "object": {"name": "Acme", "type": "Organization"},
        },
        {
            "subject": {"name": "Quarterly Report", "type": "Document"},
            "predicate": "works_for",
            "object": {"name": "Acme", "type": "Organization"},
        },
    ],
    "observations": [
        {
            "subject": {"name": "Acme", "type": "Organization"},
            "statement": "Acme employs Alice Novak as an engineer.",
        }
    ],
}

_E3_TABLES = (
    "chunks",
    "chunk_claims",
    "claims",
    "claim_extraction_decisions",
    "mentions",
    "resolution_decisions",
    "relation_evidence",
    "observation_evidence",
    "observation_adjudications",
    "observations",
    "relations",
    "aliases",
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
    """Give every proof a fresh deployment and empty fact tables."""
    with database_engine.begin() as connection:
        for table in _E3_TABLES:
            connection.execute(statement=text(f"TRUNCATE TABLE {table} CASCADE"))
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="e3-chain-test",
            name="E3 chain proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )


class _E3Rig:
    """The composed walking-skeleton chain through normalization."""

    def __init__(self, *, engine: Engine, root: Path) -> None:
        """Compose E0 + E1 + E2 + E3 with canned payloads."""
        self.engine = engine
        raw_store = LocalFSObjectStore(root=root / "raw")
        artifact_store = LocalFSObjectStore(root=root / "artifacts")
        self.provider = FakeModelProvider(
            generate_payloads={
                "ContextPrefix": {"prefix": "Sits in the staffing note."},
                "SelectionResponse": _SELECTION_PAYLOAD,
                "ClaimifyResponse": _CLAIMIFY_PAYLOAD,
                "NormalizationResponse": _NORMALIZATION_PAYLOAD,
                "FactLabelResponse": {"label": "Alice Novak works for Acme."},
            }
        )
        document_catalog = DocumentCatalog(engine=engine)
        chunk_catalog = ChunkCatalog(engine=engine)
        claim_catalog = ClaimCatalog(engine=engine)
        ledger = WorkLedger(
            engine=engine,
            settings=WorkLedgerSettings(
                retry_backoff_base_s=0.0, retry_backoff_max_s=0.0
            ),
        )
        self.ingestor = UploadIngestor(catalog=document_catalog, raw_store=raw_store)
        self.normalize_handler = NormalizeRelationsHandler(
            claim_catalog=claim_catalog,
            chunk_catalog=chunk_catalog,
            registry=EntityRegistry(engine=engine),
            facts=FactCatalog(engine=engine),
            model_provider=self.provider,
            settings=E3Settings(),
            chunker_version=chunker_version(params=_PARAMS),
        )
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
                catalog=chunk_catalog, artifact_store=artifact_store, params=_PARAMS
            ),
        )
        registry.register(
            stage=PipelineStage.EMBED_CHUNK,
            handler=EmbedChunksHandler(
                catalog=chunk_catalog,
                artifact_store=artifact_store,
                model_provider=self.provider,
                chunk_index=LanceChunkIndex(root=root / "lance"),
                settings=E1Settings(),
                params=_PARAMS,
            ),
        )
        registry.register(
            stage=PipelineStage.EXTRACT_CLAIMS,
            handler=ExtractClaimsHandler(
                catalog=claim_catalog,
                chunk_catalog=chunk_catalog,
                artifact_store=artifact_store,
                model_provider=self.provider,
                settings=E2Settings(),
                chunker_version=chunker_version(params=_PARAMS),
            ),
        )
        registry.register(
            stage=PipelineStage.NORMALIZE_RELATIONS, handler=self.normalize_handler
        )
        self.lance = LanceChunkIndex(root=root / "lance")
        registry.register(
            stage=PipelineStage.EMBED_CLAIM,
            handler=EmbedClaimsHandler(
                claim_catalog=claim_catalog,
                chunk_catalog=chunk_catalog,
                model_provider=self.provider,
                claim_index=self.lance,
                settings=P1Settings(),
                chunker_version=chunker_version(params=_PARAMS),
            ),
        )
        self.label_handler = LabelFactsHandler(
            facts=FactCatalog(engine=engine),
            model_provider=self.provider,
            fact_index=self.lance,
            settings=P1Settings(),
        )
        registry.register(
            stage=PipelineStage.LABEL_RELATION, handler=self.label_handler
        )
        self.worker = Worker(ledger=ledger, registry=registry)

    def run_chain(self) -> None:
        """Drive one document through the full six-stage chain."""
        for stage in (
            PipelineStage.CONVERT,
            PipelineStage.STRUCTURE,
            PipelineStage.CHUNK,
            PipelineStage.EMBED_CHUNK,
            PipelineStage.EXTRACT_CLAIMS,
            PipelineStage.NORMALIZE_RELATIONS,
            PipelineStage.EMBED_CLAIM,
            PipelineStage.LABEL_RELATION,
        ):
            outcome = self.worker.run_one(
                deployment_id=_DEPLOYMENT_ID, stage=stage, lane=ProcessingLane.STEADY
            ).outcome
            assert outcome is RunResultOutcome.SUCCEEDED, stage


@pytest.fixture()
def rig(database_engine: Engine, tmp_path: Path) -> _E3Rig:
    """A fresh composed chain per proof."""
    return _E3Rig(engine=database_engine, root=tmp_path)


def test_same_fact_twice_is_one_relation_with_lineage_distinct_count(
    rig: _E3Rig,
) -> None:
    """The WP-1.4 acceptance: D2 collapse + D54 counting + the D18 gates."""
    rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="staffing.md",
            mime="text/markdown",
            content=_SOURCE.encode("utf-8"),
        ),
    )
    rig.run_chain()

    with rig.engine.connect() as connection:
        relations = (
            connection.execute(
                text(
                    "SELECT relation_id, predicate, evidence_count, status"
                    " FROM relations"
                )
            )
            .mappings()
            .all()
        )
        evidence = connection.execute(
            text("SELECT count(*) FROM relation_evidence")
        ).scalar_one()
        entities = (
            connection.execute(
                text("SELECT canonical_name, type FROM entities ORDER BY type")
            )
            .mappings()
            .all()
        )
        new_decisions = connection.execute(
            text("SELECT count(*) FROM resolution_decisions WHERE is_new_entity")
        ).scalar_one()
        observations = (
            connection.execute(
                text("SELECT statement, evidence_count FROM observations")
            )
            .mappings()
            .all()
        )
        adjudications = (
            connection.execute(
                text("SELECT outcome, method FROM observation_adjudications")
            )
            .mappings()
            .all()
        )

    # both claims asserted the same fact: ONE relation, TWO evidence links,
    # and evidence_count counts DISTINCT LINEAGES = 1 (D54) — never rows:
    (relation,) = relations
    assert relation["predicate"] == "works_for"
    assert relation["status"] == "active"
    assert evidence == 2
    assert relation["evidence_count"] == 1

    # the invented predicate and the signature-violating candidate never
    # landed (only works_for exists); T0 minted each entity exactly once:
    assert [(e["canonical_name"], e["type"]) for e in entities] == [
        ("Acme", "Organization"),
        ("Alice Novak", "Person"),
    ]
    assert new_decisions == 2

    # the observation landed once with collapsed evidence and its novelty-gate
    # adjudication (D43/D4):
    (observation,) = observations
    assert observation["statement"] == "Acme employs Alice Novak as an engineer."
    assert observation["evidence_count"] == 1
    assert [dict(a) for a in adjudications] == [
        {"outcome": "add", "method": "novelty_gate"}
    ]


def test_rerunning_normalization_replays_without_model_calls(rig: _E3Rig) -> None:
    """D7 replay: a second normalize pass reads mentions and never re-calls."""
    rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="staffing.md",
            mime="text/markdown",
            content=_SOURCE.encode("utf-8"),
        ),
    )
    rig.run_chain()
    calls_after_first = len(rig.provider.generated_prompts)

    with rig.engine.connect() as connection:
        representation, version = connection.execute(
            text("SELECT current_representation_id, version_id FROM document_versions")
        ).one()

    from ultimate_memory.model import ClaimedWork
    from ultimate_memory.model import ProcessingTarget
    from ultimate_memory.workers import E3_NORMALIZER_VERSION

    rig.normalize_handler.handle(
        work=ClaimedWork(
            processing_id=version,
            deployment_id=_DEPLOYMENT_ID,
            target_kind=ProcessingTarget.DOCUMENT,
            target_id=version,
            stage=PipelineStage.NORMALIZE_RELATIONS,
            component_version=E3_NORMALIZER_VERSION,
            content_hash="sha256:replay",
            lane=ProcessingLane.STEADY,
            attempt=2,
            payload={
                "version_id": str(version),
                "representation_id": str(representation),
            },
        )
    )
    assert len(rig.provider.generated_prompts) == calls_after_first
    with rig.engine.connect() as connection:
        relation_count = connection.execute(
            text("SELECT count(*) FROM relations")
        ).scalar_one()
    assert relation_count == 1


def test_signature_gate_binds_on_resolved_stored_types(rig: _E3Rig) -> None:
    """Codex review: T0 may map an emitted name onto a differently-typed
    entity — the D18 gate must re-check the RESOLVED types, not the emitted."""
    from uuid import uuid4 as _uuid4

    person_acme = _uuid4()
    with rig.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO entities (entity_id, deployment_id, type,"
                " canonical_name, normalized_name)"
                " VALUES (:e, :d, 'Person', 'Acme', 'acme')"
            ),
            {"e": person_acme, "d": _DEPLOYMENT_ID},
        )
        connection.execute(
            text(
                "INSERT INTO aliases (alias_id, deployment_id, entity_id,"
                " alias_text, normalized_lemma, provenance)"
                " VALUES (:a, :d, :e, 'Acme', 'acme', 'llm_canonical')"
            ),
            {"a": _uuid4(), "d": _DEPLOYMENT_ID, "e": person_acme},
        )

    rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="staffing.md",
            mime="text/markdown",
            content=_SOURCE.encode("utf-8"),
        ),
    )
    rig.run_chain()

    with rig.engine.connect() as connection:
        relations = connection.execute(
            text("SELECT count(*) FROM relations")
        ).scalar_one()
        observation_subject = connection.execute(
            text("SELECT subject_entity_id FROM observations")
        ).scalar_one()
    # works_for(Person -> Person-typed Acme) violates the signature: no
    # relation lands; the observation still anchors on the resolved entity:
    assert relations == 0
    assert observation_subject == person_acme


def test_t0_never_resolves_to_a_merged_entity(rig: _E3Rig) -> None:
    """Codex review: merged entities never become endpoints — T0 filters on
    active status (redirect-following arrives with the merge machinery)."""
    from uuid import uuid4 as _uuid4

    from ultimate_memory.model import ClaimForNormalization
    from ultimate_memory.model import EntityRef
    from ultimate_memory.spine import EntityRegistry as _Registry

    survivor, merged = _uuid4(), _uuid4()
    with rig.engine.begin() as connection:
        for entity_id, name, lemma in ((survivor, "Beta Corp", "beta corp"),):
            connection.execute(
                text(
                    "INSERT INTO entities (entity_id, deployment_id, type,"
                    " canonical_name, normalized_name)"
                    " VALUES (:e, :d, 'Organization', :n, :l)"
                ),
                {"e": entity_id, "d": _DEPLOYMENT_ID, "n": name, "l": lemma},
            )
        connection.execute(
            text(
                "INSERT INTO entities (entity_id, deployment_id, type,"
                " canonical_name, normalized_name, status, merged_into)"
                " VALUES (:e, :d, 'Organization', 'Gamma Ltd', 'gamma ltd',"
                " 'merged', :m)"
            ),
            {"e": merged, "d": _DEPLOYMENT_ID, "m": survivor},
        )
        connection.execute(
            text(
                "INSERT INTO aliases (alias_id, deployment_id, entity_id,"
                " alias_text, normalized_lemma, provenance)"
                " VALUES (:a, :d, :e, 'Gamma Ltd', 'gamma ltd', 'llm_canonical')"
            ),
            {"a": _uuid4(), "d": _DEPLOYMENT_ID, "e": merged},
        )

    resolved = _Registry(engine=rig.engine).resolve_t0(
        deployment_id=_DEPLOYMENT_ID,
        reference=EntityRef(name="Gamma Ltd", type="Organization"),
        claim=ClaimForNormalization(
            claim_id=_uuid4(),
            doc_id=_uuid4(),
            chunk_id=_uuid4(),
            claim_text="Gamma Ltd exists.",
            is_attributed=False,
        ),
    )
    assert resolved.created
    assert resolved.entity_id != merged


def test_p1_channels_carry_claims_and_labeled_facts(rig: _E3Rig) -> None:
    """WP-1.5 acceptance: the claims channel (with the current-testimony
    default-filter scalar) and the labeled facts channel land in Lance, and
    the PG rows carry their refs and generations (D8)."""
    ingested = rig.ingestor.ingest(
        deployment_id=_DEPLOYMENT_ID,
        upload=DocumentUpload(
            filename="staffing.md",
            mime="text/markdown",
            content=_SOURCE.encode("utf-8"),
        ),
    )
    rig.run_chain()

    assert rig.lance.table_count(table="claims") == 2
    assert rig.lance.table_count(table="facts") == 2  # relation + observation

    with rig.engine.connect() as connection:
        stamped = connection.execute(
            text(
                "SELECT count(*) FROM claims WHERE embedding_ref IS NOT NULL"
                " AND embedding_version = 'qwen/qwen3-embedding-8b'"
            )
        ).scalar_one()
        relation = (
            connection.execute(
                text(
                    "SELECT fact_label, fact_label_version,"
                    " fact_label_embedding_ref FROM relations"
                )
            )
            .mappings()
            .one()
        )
        observation_version = connection.execute(
            text("SELECT obs_label_version FROM observations")
        ).scalar_one()
    assert stamped == 2
    assert relation["fact_label"] == "Alice Novak works for Acme."
    assert relation["fact_label_version"] is not None
    assert relation["fact_label_embedding_ref"] is not None
    assert observation_version is not None

    # replay: a second label pass finds nothing unlabeled — zero new calls:
    calls = len(rig.provider.generated_prompts)
    from uuid import uuid4 as _uuid4

    from ultimate_memory.model import ClaimedWork
    from ultimate_memory.model import ProcessingTarget
    from ultimate_memory.workers import FACT_LABEL_VERSION

    rig.label_handler.handle(
        work=ClaimedWork(
            processing_id=_uuid4(),
            deployment_id=_DEPLOYMENT_ID,
            target_kind=ProcessingTarget.DOCUMENT,
            target_id=_uuid4(),
            stage=PipelineStage.LABEL_RELATION,
            component_version=FACT_LABEL_VERSION,
            content_hash="sha256:replay",
            lane=ProcessingLane.STEADY,
            attempt=2,
            payload={"doc_id": str(ingested.doc_id)},
        )
    )
    assert len(rig.provider.generated_prompts) == calls
