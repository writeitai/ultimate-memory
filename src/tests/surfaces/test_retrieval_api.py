"""WP-1.6 acceptance: S1, S2, S5, S39 over the HTTP API + drop-count honesty.

The corpus is built by the full walking-skeleton chain (deterministic fakes);
the API answers through the composed QueryEngine — every result confirmed
against the live spine (D48), every answer carrying the D49 envelope.
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
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
from ultimate_memory.model import ResolverConfig
from ultimate_memory.model import RunResultOutcome
from ultimate_memory.spine import CascadeResolver
from ultimate_memory.spine import ChunkCatalog
from ultimate_memory.spine import ClaimCatalog
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import DocumentCatalog
from ultimate_memory.spine import EntityRegistry
from ultimate_memory.spine import FactCatalog
from ultimate_memory.spine import RESOLVER_VERSION
from ultimate_memory.spine import WorkLedger
from ultimate_memory.spine import WorkLedgerSettings
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.surfaces import build_api
from ultimate_memory.surfaces import QueryEngine
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
_DEPLOYMENT_ID = UUID("a0000000-0000-0000-0000-000000000001")
_PARAMS = ChunkerParams(token_budget=400)

_SOURCE = (
    "Alice Novak joined Acme in 2024. Alice Novak works for Acme as an engineer.\n"
)

_PAYLOADS: dict[str, dict[str, object]] = {
    "ContextPrefix": {"prefix": "Sits in the staffing note."},
    "SelectionResponse": {
        "candidates": [
            {"source_span": "Alice Novak joined Acme in 2024.", "verdict": "keep"},
            {
                "source_span": "Alice Novak works for Acme as an engineer.",
                "verdict": "keep",
            },
        ]
    },
    "ClaimifyResponse": {
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
    },
    "NormalizationResponse": {
        "relations": [
            {
                "subject": {"name": "Alice Novak", "type": "Person"},
                "predicate": "works_for",
                "object": {"name": "Acme", "type": "Organization"},
            }
        ],
        "observations": [
            {
                "subject": {"name": "Acme", "type": "Organization"},
                "statement": "Acme's headcount is 600.",
            }
        ],
    },
    "FactLabelResponse": {"label": "Alice Novak works for Acme."},
}

_TABLES = (
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
        pytest.skip("UGM_DATABASE_URL is required for real PostgreSQL API proofs")
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
        for table in _TABLES:
            connection.execute(statement=text(f"TRUNCATE TABLE {table} CASCADE"))
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="retrieval-api-test",
            name="Retrieval API proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )


class _ApiRig:
    """The full chain plus the HTTP API over the resulting corpus."""

    def __init__(self, *, engine: Engine, root: Path) -> None:
        """Compose the pipeline, run-ready, and the API client."""
        self.engine = engine
        raw_store = LocalFSObjectStore(root=root / "raw")
        artifact_store = LocalFSObjectStore(root=root / "artifacts")
        self.lance = LanceChunkIndex(root=root / "lance")
        self.provider = FakeModelProvider(generate_payloads=_PAYLOADS)
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
        generation = chunker_version(params=_PARAMS)
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
                chunk_index=self.lance,
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
                chunker_version=generation,
            ),
        )
        registry.register(
            stage=PipelineStage.NORMALIZE_RELATIONS,
            handler=NormalizeRelationsHandler(
                claim_catalog=claim_catalog,
                chunk_catalog=chunk_catalog,
                registry=EntityRegistry(engine=engine),
                resolver=CascadeResolver(
                    engine=engine,
                    entity_index=self.lance,
                    model_provider=self.provider,
                    config=ResolverConfig(resolver_version=RESOLVER_VERSION),
                    embedding_model="qwen/qwen3-embedding-8b",
                    small_model="openai/gpt-5.6-luna",
                    frontier_model="openai/gpt-5.6-sol",
                ),
                facts=FactCatalog(engine=engine),
                model_provider=self.provider,
                settings=E3Settings(),
                chunker_version=generation,
            ),
        )
        registry.register(
            stage=PipelineStage.EMBED_CLAIM,
            handler=EmbedClaimsHandler(
                claim_catalog=claim_catalog,
                chunk_catalog=chunk_catalog,
                model_provider=self.provider,
                claim_index=self.lance,
                settings=P1Settings(),
                chunker_version=generation,
            ),
        )
        registry.register(
            stage=PipelineStage.LABEL_RELATION,
            handler=LabelFactsHandler(
                facts=FactCatalog(engine=engine),
                model_provider=self.provider,
                fact_index=self.lance,
                settings=P1Settings(),
            ),
        )
        self.worker = Worker(ledger=ledger, registry=registry)
        self.client = TestClient(
            build_api(
                engine=QueryEngine(
                    engine=engine,
                    search_index=self.lance,
                    model_provider=self.provider,
                    embedding_model=P1Settings().embedding_model,
                ),
                deployment_id=_DEPLOYMENT_ID,
            )
        )

    def build_corpus(self) -> None:
        """Ingest the staffing note and run the whole chain."""
        self.ingestor.ingest(
            deployment_id=_DEPLOYMENT_ID,
            upload=DocumentUpload(
                filename="staffing.md",
                mime="text/markdown",
                content=_SOURCE.encode("utf-8"),
            ),
        )
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
def rig(database_engine: Engine, tmp_path: Path) -> _ApiRig:
    """A fresh corpus + API per proof."""
    built = _ApiRig(engine=database_engine, root=tmp_path)
    built.build_corpus()
    return built


def test_s1_current_employer_via_resolve_and_lookup(rig: _ApiRig) -> None:
    """S1: resolve the person, read the live works_for relation — fact grain,
    zero LLM, labels hydrated."""
    resolved = rig.client.get("/resolve", params={"name": "alice novak"}).json()
    assert resolved["grain"] == "fact"
    (candidate,) = resolved["entities"]
    assert candidate["canonical_name"] == "Alice Novak"

    relations = rig.client.get(
        "/lookup/relations",
        params={"subject_entity_id": candidate["entity_id"], "predicate": "works_for"},
    ).json()
    assert relations["grain"] == "fact"
    (fact,) = relations["facts"]
    assert fact["label"] == "Alice Novak works for Acme."
    assert fact["evidence_count"] == 1
    assert fact["validity"]["invalidated_at"] is None
    assert relations["freshness"]["pg_live_ts"] is not None


def test_s2_headcount_via_semantic_observation_lookup(rig: _ApiRig) -> None:
    """S2: semantic property match over observation statements (D43)."""
    acme = rig.client.get("/resolve", params={"name": "Acme"}).json()["entities"][0]
    answer = rig.client.get(
        "/lookup/observations",
        params={"entity_id": acme["entity_id"], "property_query": "headcount"},
    ).json()
    assert answer["grain"] == "fact"
    (fact,) = answer["facts"]
    assert fact["label"] == "Acme's headcount is 600."
    assert answer["dropped_by_hydration"] == 0


def test_s5_sources_via_the_hydration_chain(rig: _ApiRig) -> None:
    """S5: relation → evidence claims (spans + offsets) → document handles."""
    alice = rig.client.get("/resolve", params={"name": "Alice Novak"}).json()[
        "entities"
    ][0]
    relation = rig.client.get(
        "/lookup/relations", params={"subject_entity_id": alice["entity_id"]}
    ).json()["facts"][0]

    hydrated = rig.client.get(f"/hydrate/relation/{relation['fact_id']}").json()
    assert hydrated["grain"] == "composite"
    assert len(hydrated["evidence"]) == 2  # both asserting claims
    for claim in hydrated["evidence"]:
        assert _SOURCE[claim["char_start"] : claim["char_end"]] == claim["source_span"]
    (source,) = hydrated["sources"]
    assert source["title"] == "staffing"
    assert source["markdown_uri"].endswith("/document.md")


def test_s39_negative_taxonomy_distinguishes_unknown_from_empty(rig: _ApiRig) -> None:
    """S39: unknown entity vs known entity with no facts are typed differently."""
    unknown = rig.client.get("/resolve", params={"name": "Contoso"}).json()
    assert unknown["negative"]["kind"] == "unknown_entity"
    assert unknown["entities"] == []

    acme = rig.client.get("/resolve", params={"name": "Acme"}).json()["entities"][0]
    empty = rig.client.get(
        "/lookup/relations",
        params={"subject_entity_id": acme["entity_id"], "predicate": "reports_to"},
    ).json()
    assert empty["negative"]["kind"] == "known_empty"
    assert empty["facts"] == []


def test_search_claims_is_evidence_grain_with_drop_count_honesty(rig: _ApiRig) -> None:
    """The D48 nominate-then-drop proof: a Lance-nominated claim whose spine row
    lost currency is dropped and counted — never served. Claims answers are
    EVIDENCE grain, never current-fact."""
    first = rig.client.get(
        "/search/claims", params={"query": "Alice Novak employer", "k": 10}
    ).json()
    assert first["grain"] == "evidence"
    assert len(first["evidence"]) == 2
    assert first["dropped_by_hydration"] == 0
    for claim in first["evidence"]:
        assert claim["is_current_testimony"]

    # currency flips on one claim in the spine; Lance still nominates it:
    with rig.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE claims SET is_current_testimony = false"
                " WHERE claim_text = 'Alice Novak joined Acme in 2024.'"
            )
        )
    second = rig.client.get(
        "/search/claims", params={"query": "Alice Novak employer", "k": 10}
    ).json()
    assert len(second["evidence"]) == 1
    assert second["dropped_by_hydration"] == 1  # the honest denominator


def test_expired_valid_window_is_not_a_current_fact(rig: _ApiRig) -> None:
    """Codex review: current means BOTH clocks — a relation whose valid-time
    window closed is never served by the current-fact lookup."""
    alice = rig.client.get("/resolve", params={"name": "Alice Novak"}).json()[
        "entities"
    ][0]
    with rig.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE relations SET valid_from = '2020-01-01+00',"
                " valid_until = '2021-01-01+00'"
            )
        )
    answer = rig.client.get(
        "/lookup/relations", params={"subject_entity_id": alice["entity_id"]}
    ).json()
    assert answer["facts"] == []
    assert answer["negative"]["kind"] == "known_empty"


def test_resolve_follows_merge_redirects_to_the_survivor(rig: _ApiRig) -> None:
    """Codex review / S60: an alias on a merged entity resolves to the
    survivor — current identities, never a dead end."""
    from uuid import uuid4 as _uuid4

    alice = rig.client.get("/resolve", params={"name": "Alice Novak"}).json()[
        "entities"
    ][0]
    merged = _uuid4()
    with rig.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO entities (entity_id, deployment_id, type,"
                " canonical_name, normalized_name, status, merged_into)"
                " VALUES (:e, :d, 'Person', 'A. Novak', 'a. novak', 'merged', :m)"
            ),
            {"e": merged, "d": _DEPLOYMENT_ID, "m": alice["entity_id"]},
        )
        connection.execute(
            text(
                "INSERT INTO aliases (alias_id, deployment_id, entity_id,"
                " alias_text, normalized_lemma, provenance)"
                " VALUES (:a, :d, :e, 'A. Novak', 'a. novak', 'llm_canonical')"
            ),
            {"a": _uuid4(), "d": _DEPLOYMENT_ID, "e": merged},
        )
    resolved = rig.client.get("/resolve", params={"name": "A. Novak"}).json()
    (candidate,) = resolved["entities"]
    assert candidate["entity_id"] == alice["entity_id"]  # the survivor


def test_hydrate_discloses_invalidation_instead_of_hiding_history(rig: _ApiRig) -> None:
    """Hydrate-by-ID is the audit hop: an invalidated relation returns with
    its invalidation disclosed in validity — never refused, never current."""
    alice = rig.client.get("/resolve", params={"name": "Alice Novak"}).json()[
        "entities"
    ][0]
    relation = rig.client.get(
        "/lookup/relations", params={"subject_entity_id": alice["entity_id"]}
    ).json()["facts"][0]
    with rig.engine.begin() as connection:
        connection.execute(text("UPDATE relations SET invalidated_at = now()"))

    hydrated = rig.client.get(f"/hydrate/relation/{relation['fact_id']}").json()
    assert hydrated["facts"][0]["validity"]["invalidated_at"] is not None
    # and the current-fact lookup no longer serves it:
    current = rig.client.get(
        "/lookup/relations", params={"subject_entity_id": alice["entity_id"]}
    ).json()
    assert current["facts"] == []


def test_wp17_skeleton_eval_suite_runs_green_and_blocks_on_breakage(
    rig: _ApiRig,
) -> None:
    """WP-1.7 acceptance: the S-subset + grain contract wired into the D22
    harness as retrieval-suite canaries — green over the corpus, and a broken
    corpus fails the suite (the CI-blocking signal)."""
    from ultimate_memory.eval import EvalHarness
    from ultimate_memory.eval import make_skeleton_evaluator
    from ultimate_memory.eval import seed_skeleton_canaries
    from ultimate_memory.model import EvalSuite
    from ultimate_memory.workers import P1Settings as _P1Settings

    seed_skeleton_canaries(engine=rig.engine, deployment_id=_DEPLOYMENT_ID)
    seed_skeleton_canaries(  # idempotent: re-seeding never duplicates
        engine=rig.engine, deployment_id=_DEPLOYMENT_ID
    )
    query_engine = QueryEngine(
        engine=rig.engine,
        search_index=rig.lance,
        model_provider=rig.provider,
        embedding_model=_P1Settings().embedding_model,
    )
    harness = EvalHarness(engine=rig.engine)
    harness.register_evaluator(
        suite=EvalSuite.RETRIEVAL,
        evaluator=make_skeleton_evaluator(
            query_engine=query_engine, deployment_id=_DEPLOYMENT_ID
        ),
    )
    report = harness.run_suite(
        deployment_id=_DEPLOYMENT_ID,
        suite=EvalSuite.RETRIEVAL,
        component_version="skeleton-2026.07",
    )
    assert report.total_cases == 5
    assert report.passed, [failure.description for failure in report.failures]

    # break the corpus (invalidate the relation): the suite must fail:
    with rig.engine.begin() as connection:
        connection.execute(text("UPDATE relations SET invalidated_at = now()"))
    broken = harness.run_suite(
        deployment_id=_DEPLOYMENT_ID,
        suite=EvalSuite.RETRIEVAL,
        component_version="skeleton-2026.07",
    )
    assert not broken.passed
