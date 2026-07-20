"""WP-6.1 acceptance: live K control plane, routing, and exact staleness."""

from collections.abc import Iterator
from datetime import datetime
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
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine

from ultimate_memory.core import knowledge_inputs_hash
from ultimate_memory.model import CommunityRuleParams
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.model import DocSetRuleParams
from ultimate_memory.model import EntityRuleParams
from ultimate_memory.model import EntitySubtreeRuleParams
from ultimate_memory.model import KnowledgeArtifactCreate
from ultimate_memory.model import KnowledgeCitation
from ultimate_memory.model import KnowledgeCompilationWrite
from ultimate_memory.model import KnowledgeCompileContext
from ultimate_memory.model import KnowledgeEvidenceDelta
from ultimate_memory.model import KnowledgeEvidenceRole
from ultimate_memory.model import KnowledgeLayer
from ultimate_memory.model import KnowledgePageKind
from ultimate_memory.model import KnowledgePageRuleCreate
from ultimate_memory.model import KnowledgePlanAction
from ultimate_memory.model import KnowledgePlanDecisionCreate
from ultimate_memory.model import KnowledgePlanStatus
from ultimate_memory.model import KnowledgePlanTrigger
from ultimate_memory.model import ManualRuleParams
from ultimate_memory.model import PredicateBeatRuleParams
from ultimate_memory.model import ScopeInterestsRuleParams
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import KnowledgeCompilationError
from ultimate_memory.spine import KnowledgeControlPlane
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import KnowledgeRoutingDriver

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("61000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 7, 20, tzinfo=UTC)


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real Plane-K proofs")
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
def corpus(database_engine: Engine) -> "_Corpus":
    """Give each proof a fresh deployment and compact cross-layer corpus."""
    with database_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="k-control",
            name="K control proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
            knowledge_repo_uri="mem://knowledge.git",
        )
    )
    return _Corpus(engine=database_engine)


class _Corpus:
    """Small authoritative state that distinguishes every routing-rule kind."""

    def __init__(self, *, engine: Engine) -> None:
        """Seed entities, facts, stable claim coordinates, scope, and community."""
        self.engine = engine
        self.control = KnowledgeControlPlane(engine=engine)
        self.driver = KnowledgeRoutingDriver(control_plane=self.control)
        self.scope_id = uuid4()
        self.community_id = uuid4()
        self.entities = {
            "root": uuid4(),
            "child": uuid4(),
            "acme": uuid4(),
            "outside": uuid4(),
        }
        self.docs = {"drive": uuid4(), "email": uuid4()}
        self.chunks = {"drive": uuid4(), "email": uuid4()}
        self.claims = {"drive": uuid4(), "email": uuid4()}
        self.relations = {"part_of": uuid4(), "root": uuid4(), "outside": uuid4()}
        self.observations = {"root": uuid4(), "child": uuid4()}
        with engine.begin() as connection:
            self._seed_registry(connection=connection)
            self._seed_evidence(connection=connection)
            self._seed_community(connection=connection)

    def page(
        self,
        *,
        params: object,
        slug: str,
        page_kind: KnowledgePageKind = KnowledgePageKind.COMPILED,
    ) -> UUID:
        """Register one artifact and its typed, plan-authorized rule."""
        artifact_id = uuid4()
        decision_id = uuid4()
        self.control.record_plan_decision(
            decision=KnowledgePlanDecisionCreate(
                decision_id=decision_id,
                deployment_id=_DEPLOYMENT_ID,
                action=KnowledgePlanAction.CREATE_PAGE,
                payload={"git_path": f"k/{slug}.md"},
                trigger=KnowledgePlanTrigger.HUMAN,
                planner_version="planner-test",
                status=KnowledgePlanStatus.APPLIED,
            )
        )
        self.control.create_artifact(
            artifact=KnowledgeArtifactCreate(
                artifact_id=artifact_id,
                deployment_id=_DEPLOYMENT_ID,
                layer=KnowledgeLayer.K1,
                page_kind=page_kind,
                git_path=f"k/{slug}.md",
                curation_path=(
                    f"k/{slug}.curation.md"
                    if page_kind is KnowledgePageKind.COMPILED
                    else None
                ),
                writer_version=(
                    "writer-test" if page_kind is KnowledgePageKind.COMPILED else None
                ),
            )
        )
        self.control.add_page_rule(
            rule=KnowledgePageRuleCreate.model_validate(
                {
                    "rule_id": uuid4(),
                    "deployment_id": _DEPLOYMENT_ID,
                    "artifact_id": artifact_id,
                    "plan_decision_id": decision_id,
                    "params": params,
                }
            )
        )
        return artifact_id

    def compile(self, *, artifact_id: UUID) -> KnowledgeCompileContext:
        """Record the artifact's current manifest as a successful compile."""
        context = KnowledgeCompileContext(
            curation_hash="curation-test", writer_version="writer-test"
        )
        snapshot = self.control.input_snapshot(artifact_id=artifact_id, context=context)
        compilation = KnowledgeCompilationWrite(
            compilation_id=uuid4(),
            deployment_id=_DEPLOYMENT_ID,
            artifact_id=artifact_id,
            inputs_hash=knowledge_inputs_hash(snapshot=snapshot),
            candidate_count=len(snapshot.facts) + len(snapshot.claims),
            uncited_count=len(snapshot.facts) + len(snapshot.claims),
            citations=(),
            writer_version="writer-test",
            page_summary="A compiled test page.",
            content_hash="content-test",
        )
        self.control.record_pending_compilation(compilation=compilation)
        self.control.commit_compilation(
            compilation=compilation, git_commit=f"commit-{compilation.compilation_id}"
        )
        return context

    def _seed_registry(self, *, connection: Connection) -> None:
        """Seed the scope and canonical entities used by routing."""
        connection.execute(
            text(
                "INSERT INTO scopes (scope_id, deployment_id, slug, name, git_path)"
                " VALUES (:s, :d, 'work', 'Work', 'k/work')"
            ),
            {"s": self.scope_id, "d": _DEPLOYMENT_ID},
        )
        for name, entity_id, entity_type in (
            ("Root", self.entities["root"], "Project"),
            ("Child", self.entities["child"], "Project"),
            ("Acme", self.entities["acme"], "Organization"),
            ("Outside", self.entities["outside"], "Person"),
        ):
            connection.execute(
                text(
                    "INSERT INTO entities (entity_id, deployment_id, type,"
                    " canonical_name, normalized_name)"
                    " VALUES (:e, :d, :t, :n, lower(:n))"
                ),
                {"e": entity_id, "d": _DEPLOYMENT_ID, "t": entity_type, "n": name},
            )
        for interest_type, value in (
            ("predicate", "works_for"),
            ("keyword", "deadline"),
        ):
            connection.execute(
                text(
                    "INSERT INTO scope_interests (interest_id, deployment_id,"
                    " scope_id, interest_type, value)"
                    " VALUES (:i, :d, :s, :t, :v)"
                ),
                {
                    "i": uuid4(),
                    "d": _DEPLOYMENT_ID,
                    "s": self.scope_id,
                    "t": interest_type,
                    "v": value,
                },
            )

    def _seed_evidence(self, *, connection: Connection) -> None:
        """Seed two lineages, stable chunks/claims, facts, and entity mentions."""
        for source, source_kind in (("drive", "google_drive"), ("email", "email")):
            connection.execute(
                text(
                    "INSERT INTO documents (doc_id, deployment_id, source_kind,"
                    " source_ref, origin, title)"
                    " VALUES (:doc, :d, :source, :ref, 'external', :title)"
                ),
                {
                    "doc": self.docs[source],
                    "d": _DEPLOYMENT_ID,
                    "source": source_kind,
                    "ref": f"{source}-ref",
                    "title": source,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO chunks (chunk_id, deployment_id, doc_id,"
                    " version_id, representation_id, ordinal, block_start, block_end,"
                    " chunk_content_hash, extraction_input_hash, char_start, char_end,"
                    " created_at) VALUES (:ch, :d, :doc, :v, :rep, 0, 0, 0,"
                    " :hash, :input, 0, 20, :at)"
                ),
                {
                    "ch": self.chunks[source],
                    "d": _DEPLOYMENT_ID,
                    "doc": self.docs[source],
                    "v": uuid4(),
                    "rep": uuid4(),
                    "hash": f"chunk-{source}",
                    "input": f"input-{source}",
                    "at": _NOW,
                },
            )
            claim_text = (
                "Root works for Acme."
                if source == "drive"
                else "Outside owns the deadline."
            )
            connection.execute(
                text(
                    "INSERT INTO claims (claim_id, deployment_id, doc_id, chunk_id,"
                    " claim_text, source_span, char_start, char_end, anchor_ok,"
                    " window_membership_ok, extractor_version, ingested_at)"
                    " VALUES (:c, :d, :doc, :ch, :body, :body, 0, 20, true,"
                    " true, 'extractor-test', :at)"
                ),
                {
                    "c": self.claims[source],
                    "d": _DEPLOYMENT_ID,
                    "doc": self.docs[source],
                    "ch": self.chunks[source],
                    "body": claim_text,
                    "at": _NOW,
                },
            )
        self._seed_facts(connection=connection)
        self._seed_mention(
            connection=connection,
            claim_id=self.claims["drive"],
            doc_id=self.docs["drive"],
            entity_id=self.entities["root"],
            surface="Root",
        )
        self._seed_mention(
            connection=connection,
            claim_id=self.claims["email"],
            doc_id=self.docs["email"],
            entity_id=self.entities["outside"],
            surface="Outside",
        )

    def _seed_facts(self, *, connection: Connection) -> None:
        """Seed subtree, candidate, unrelated, and observation fact state."""
        for relation_id, subject, predicate, object_id, count in (
            (
                self.relations["part_of"],
                self.entities["child"],
                "part_of",
                self.entities["root"],
                1,
            ),
            (
                self.relations["root"],
                self.entities["root"],
                "works_for",
                self.entities["acme"],
                1,
            ),
            (
                self.relations["outside"],
                self.entities["outside"],
                "works_on",
                self.entities["acme"],
                1,
            ),
        ):
            connection.execute(
                text(
                    "INSERT INTO relations (relation_id, deployment_id,"
                    " subject_entity_id, predicate, object_entity_id,"
                    " normalizer_version, evidence_count, ingested_at)"
                    " VALUES (:r, :d, :s, :p, :o, 'normalizer-test', :count, :at)"
                ),
                {
                    "r": relation_id,
                    "d": _DEPLOYMENT_ID,
                    "s": subject,
                    "p": predicate,
                    "o": object_id,
                    "count": count,
                    "at": _NOW,
                },
            )
        for observation_id, entity_id, statement in (
            (self.observations["root"], self.entities["root"], "Root is active."),
            (self.observations["child"], self.entities["child"], "Child is active."),
        ):
            connection.execute(
                text(
                    "INSERT INTO observations (observation_id, deployment_id,"
                    " subject_entity_id, statement, normalizer_version,"
                    " evidence_count, ingested_at) VALUES (:o, :d, :e, :body,"
                    " 'normalizer-test', 1, :at)"
                ),
                {
                    "o": observation_id,
                    "d": _DEPLOYMENT_ID,
                    "e": entity_id,
                    "body": statement,
                    "at": _NOW,
                },
            )
        connection.execute(
            text(
                "INSERT INTO relation_evidence (deployment_id, relation_id, claim_id,"
                " doc_id, stance, normalizer_version) VALUES"
                " (:d, :r, :c, :doc, 'supports', 'normalizer-test')"
            ),
            {
                "d": _DEPLOYMENT_ID,
                "r": self.relations["root"],
                "c": self.claims["drive"],
                "doc": self.docs["drive"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO relation_evidence (deployment_id, relation_id, claim_id,"
                " doc_id, stance, normalizer_version) VALUES"
                " (:d, :r, :c, :doc, 'supports', 'normalizer-test')"
            ),
            {
                "d": _DEPLOYMENT_ID,
                "r": self.relations["outside"],
                "c": self.claims["email"],
                "doc": self.docs["email"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO observation_evidence (deployment_id, observation_id,"
                " claim_id, doc_id, stance, normalizer_version) VALUES"
                " (:d, :o, :c, :doc, 'supports', 'normalizer-test')"
            ),
            {
                "d": _DEPLOYMENT_ID,
                "o": self.observations["root"],
                "c": self.claims["drive"],
                "doc": self.docs["drive"],
            },
        )

    def _seed_mention(
        self,
        *,
        connection: Connection,
        claim_id: UUID,
        doc_id: UUID,
        entity_id: UUID,
        surface: str,
    ) -> None:
        """Attach one current claim mention to its resolved canonical entity."""
        mention_id = uuid4()
        connection.execute(
            text(
                "INSERT INTO mentions (mention_id, deployment_id, surface_form,"
                " normalized_lemma, claim_id, doc_id, created_at)"
                " VALUES (:m, :d, :surface, lower(:surface), :c, :doc, :at)"
            ),
            {
                "m": mention_id,
                "d": _DEPLOYMENT_ID,
                "surface": surface,
                "c": claim_id,
                "doc": doc_id,
                "at": _NOW,
            },
        )
        connection.execute(
            text(
                "INSERT INTO resolution_decisions (decision_id, deployment_id,"
                " mention_id, entity_id, method, confidence, resolver_version,"
                " decided_at) VALUES (:x, :d, :m, :e, 'T3', 0.9,"
                " 'resolver-test', :at)"
            ),
            {
                "x": uuid4(),
                "d": _DEPLOYMENT_ID,
                "m": mention_id,
                "e": entity_id,
                "at": _NOW,
            },
        )

    def _seed_community(self, *, connection: Connection) -> None:
        """Seed one P2 community and its two member keys."""
        snapshot_id = uuid4()
        connection.execute(
            text(
                "INSERT INTO projection_snapshots (snapshot_id, deployment_id,"
                " plane, version, gcs_uri, status, is_latest) VALUES"
                " (:s, :d, 'P2_graph', 'test', 'mem://graph', 'published', true)"
            ),
            {"s": snapshot_id, "d": _DEPLOYMENT_ID},
        )
        connection.execute(
            text(
                "INSERT INTO communities (community_id, deployment_id, snapshot_id,"
                " label, size, algorithm) VALUES (:c, :d, :s, 'root', 2, 'louvain')"
            ),
            {"c": self.community_id, "d": _DEPLOYMENT_ID, "s": snapshot_id},
        )
        for entity_id in (self.entities["root"], self.entities["child"]):
            connection.execute(
                text(
                    "INSERT INTO entity_graph_metrics (deployment_id, entity_id,"
                    " snapshot_id, community_id) VALUES (:d, :e, :s, :c)"
                ),
                {
                    "d": _DEPLOYMENT_ID,
                    "e": entity_id,
                    "s": snapshot_id,
                    "c": self.community_id,
                },
            )


def test_all_seven_rules_materialize_and_evaluate(corpus: _Corpus) -> None:
    """Every closed D45 rule kind has typed params and exact candidate SQL."""
    pages = {
        "entity": corpus.page(
            params=EntityRuleParams(entity_id=corpus.entities["root"]), slug="entity"
        ),
        "subtree": corpus.page(
            params=EntitySubtreeRuleParams(root_entity_id=corpus.entities["root"]),
            slug="subtree",
        ),
        "predicate": corpus.page(
            params=PredicateBeatRuleParams(predicate="works_for"), slug="predicate"
        ),
        "community": corpus.page(
            params=CommunityRuleParams(community_id=corpus.community_id),
            slug="community",
        ),
        "doc_set": corpus.page(
            params=DocSetRuleParams(source_kind="google_drive"), slug="doc-set"
        ),
        "scope": corpus.page(
            params=ScopeInterestsRuleParams(scope_id=corpus.scope_id), slug="scope"
        ),
        "manual": corpus.page(
            params=ManualRuleParams(
                entity_ids=(corpus.entities["outside"],),
                relation_ids=(corpus.relations["outside"],),
                observation_ids=(corpus.observations["root"],),
                claim_ids=(corpus.claims["email"],),
            ),
            slug="manual",
        ),
    }
    context = KnowledgeCompileContext(writer_version="writer-test")
    snapshots = {
        name: corpus.control.input_snapshot(artifact_id=page, context=context)
        for name, page in pages.items()
    }
    assert corpus.relations["root"] in {
        fact.fact_id for fact in snapshots["entity"].facts
    }
    assert corpus.observations["child"] in {
        fact.fact_id for fact in snapshots["subtree"].facts
    }
    assert {fact.fact_id for fact in snapshots["predicate"].facts} == {
        corpus.relations["root"]
    }
    assert corpus.observations["child"] in {
        fact.fact_id for fact in snapshots["community"].facts
    }
    assert corpus.relations["root"] in {
        fact.fact_id for fact in snapshots["doc_set"].facts
    }
    assert corpus.relations["root"] in {
        fact.fact_id for fact in snapshots["scope"].facts
    }
    assert corpus.relations["outside"] in {
        fact.fact_id for fact in snapshots["scope"].facts
    }
    assert corpus.relations["outside"] in {
        fact.fact_id for fact in snapshots["manual"].facts
    }
    assert corpus.observations["root"] in {
        fact.fact_id for fact in snapshots["manual"].facts
    }
    with corpus.engine.connect() as connection:
        keys = {
            (row["rule_kind"], row["key_kind"], row["key_value"])
            for row in connection.execute(
                text(
                    "SELECT r.rule_kind::text, k.key_kind::text, k.key_value"
                    " FROM knowledge_rule_keys k"
                    " JOIN knowledge_page_rules r ON r.rule_id = k.rule_id"
                )
            ).mappings()
        }
    assert ("entity", "entity", str(corpus.entities["root"])) in keys
    assert ("entity_subtree", "entity", str(corpus.entities["child"])) in keys
    assert ("predicate_beat", "predicate", "works_for") in keys
    assert ("community", "community", str(corpus.community_id)) in keys
    assert ("doc_set", "doc_source", "google_drive") in keys
    assert ("scope_interests", "predicate", "works_for") in keys
    assert ("manual", "entity", str(corpus.entities["outside"])) in keys


def test_stale_set_is_exact_and_claim_reextraction_is_stable(corpus: _Corpus) -> None:
    """Only candidate-state drift stales; raw claim churn at one coordinate does not."""
    page = corpus.page(
        params=EntityRuleParams(entity_id=corpus.entities["root"]), slug="stale-exact"
    )
    doc_page = corpus.page(
        params=DocSetRuleParams(source_kind="google_drive"), slug="stale-doc-set"
    )
    corpus.page(
        params=EntityRuleParams(entity_id=corpus.entities["root"]),
        slug="authored",
        page_kind=KnowledgePageKind.AUTHORED,
    )
    context = corpus.compile(artifact_id=page)
    doc_context = corpus.compile(artifact_id=doc_page)
    contexts = {page: context, doc_page: doc_context}

    with corpus.engine.begin() as connection:
        connection.execute(
            text("UPDATE relations SET evidence_count = 7 WHERE relation_id = :r"),
            {"r": corpus.relations["outside"]},
        )
    assert (
        corpus.driver.mark_all_manifest_drift(
            deployment_id=_DEPLOYMENT_ID, contexts=contexts
        )
        == ()
    )

    replacement_claim = uuid4()
    with corpus.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO claims (claim_id, deployment_id, doc_id, chunk_id,"
                " claim_text, source_span, char_start, char_end, anchor_ok,"
                " window_membership_ok, extractor_version, ingested_at)"
                " VALUES (:c, :d, :doc, :ch, 'rewritten extraction',"
                " 'rewritten extraction', 0, 20, true, true, 'extractor-new', :at)"
            ),
            {
                "c": replacement_claim,
                "d": _DEPLOYMENT_ID,
                "doc": corpus.docs["drive"],
                "ch": corpus.chunks["drive"],
                "at": _NOW,
            },
        )
        corpus._seed_mention(
            connection=connection,
            claim_id=replacement_claim,
            doc_id=corpus.docs["drive"],
            entity_id=corpus.entities["root"],
            surface="Root",
        )
    assert (
        corpus.driver.mark_all_manifest_drift(
            deployment_id=_DEPLOYMENT_ID, contexts=contexts
        )
        == ()
    )

    with corpus.engine.begin() as connection:
        connection.execute(
            text("UPDATE relations SET evidence_count = 3 WHERE relation_id = :r"),
            {"r": corpus.relations["root"]},
        )
    assert set(
        corpus.driver.route_and_mark_stale(
            deployment_id=_DEPLOYMENT_ID,
            delta=KnowledgeEvidenceDelta(relation_ids=(corpus.relations["root"],)),
            contexts=contexts,
        )
    ) == {page, doc_page}
    context = corpus.compile(artifact_id=page)
    doc_context = corpus.compile(artifact_id=doc_page)

    with corpus.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE observations SET valid_until = '2026-07-19+00'"
                " WHERE observation_id = :o"
            ),
            {"o": corpus.observations["root"]},
        )
    assert set(
        corpus.driver.route_and_mark_stale(
            deployment_id=_DEPLOYMENT_ID,
            delta=KnowledgeEvidenceDelta(
                observation_ids=(corpus.observations["root"],)
            ),
            contexts={page: context, doc_page: doc_context},
        )
    ) == {page, doc_page}


def test_subtree_membership_rematerializes_before_routing(corpus: _Corpus) -> None:
    """A new part_of edge expands keys and stales the affected subtree page."""
    page = corpus.page(
        params=EntitySubtreeRuleParams(root_entity_id=corpus.entities["root"]),
        slug="subtree-refresh",
    )
    context = corpus.compile(artifact_id=page)
    grandchild = uuid4()
    membership = uuid4()
    observation = uuid4()
    with corpus.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO entities (entity_id, deployment_id, type,"
                " canonical_name, normalized_name) VALUES"
                " (:e, :d, 'Project', 'Grandchild', 'grandchild')"
            ),
            {"e": grandchild, "d": _DEPLOYMENT_ID},
        )
        connection.execute(
            text(
                "INSERT INTO relations (relation_id, deployment_id,"
                " subject_entity_id, predicate, object_entity_id,"
                " normalizer_version, evidence_count) VALUES"
                " (:r, :d, :s, 'part_of', :o, 'normalizer-test', 1)"
            ),
            {
                "r": membership,
                "d": _DEPLOYMENT_ID,
                "s": grandchild,
                "o": corpus.entities["child"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO observations (observation_id, deployment_id,"
                " subject_entity_id, statement, normalizer_version, evidence_count)"
                " VALUES (:o, :d, :e, 'Grandchild is new.', 'normalizer-test', 1)"
            ),
            {"o": observation, "d": _DEPLOYMENT_ID, "e": grandchild},
        )
    assert corpus.driver.route_and_mark_stale(
        deployment_id=_DEPLOYMENT_ID,
        delta=KnowledgeEvidenceDelta(relation_ids=(membership,)),
        contexts={page: context},
    ) == (page,)
    with corpus.engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM knowledge_rule_keys k"
                " JOIN knowledge_page_rules r ON r.rule_id = k.rule_id"
                " WHERE r.artifact_id = :a AND k.key_kind = 'entity'"
                " AND k.key_value = :e)"
            ),
            {"a": page, "e": str(grandchild)},
        ).scalar_one()


def test_new_rule_immediately_stales_a_compiled_owner(corpus: _Corpus) -> None:
    """A rule-config trigger cannot leave its previously compiled owner active."""
    page = corpus.page(
        params=EntityRuleParams(entity_id=corpus.entities["root"]),
        slug="rule-adjustment",
    )
    corpus.compile(artifact_id=page)
    decision_id = uuid4()
    corpus.control.record_plan_decision(
        decision=KnowledgePlanDecisionCreate(
            decision_id=decision_id,
            deployment_id=_DEPLOYMENT_ID,
            action=KnowledgePlanAction.ADJUST_RULE,
            payload={"artifact_id": str(page)},
            trigger=KnowledgePlanTrigger.HUMAN,
            planner_version="planner-test",
            status=KnowledgePlanStatus.APPLIED,
        )
    )
    corpus.control.add_page_rule(
        rule=KnowledgePageRuleCreate(
            rule_id=uuid4(),
            deployment_id=_DEPLOYMENT_ID,
            artifact_id=page,
            plan_decision_id=decision_id,
            params=PredicateBeatRuleParams(predicate="works_on"),
        )
    )
    with corpus.engine.connect() as connection:
        status = connection.execute(
            text("SELECT status::text FROM knowledge_artifacts WHERE artifact_id = :a"),
            {"a": page},
        ).scalar_one()
    assert status == "stale"


def test_compilation_replaces_binding_citations_and_records_deltas(
    corpus: _Corpus,
) -> None:
    """Compilation, citations, counts, and artifact state commit atomically."""
    page = corpus.page(
        params=EntityRuleParams(entity_id=corpus.entities["root"]),
        slug="compile-ledger",
    )
    context = KnowledgeCompileContext(writer_version="writer-test")
    snapshot = corpus.control.input_snapshot(artifact_id=page, context=context)
    first = KnowledgeCompilationWrite(
        compilation_id=uuid4(),
        deployment_id=_DEPLOYMENT_ID,
        artifact_id=page,
        inputs_hash=knowledge_inputs_hash(snapshot=snapshot),
        candidate_count=len(snapshot.facts) + len(snapshot.claims),
        uncited_count=len(snapshot.facts) + len(snapshot.claims) - 2,
        citations=(
            KnowledgeCitation(
                role=KnowledgeEvidenceRole.SUPPORTS,
                relation_id=corpus.relations["root"],
            ),
            KnowledgeCitation(
                role=KnowledgeEvidenceRole.CITES, claim_id=corpus.claims["drive"]
            ),
        ),
        writer_version="writer-test",
        page_summary="First summary.",
        content_hash="first-content",
    )
    corpus.control.record_pending_compilation(compilation=first)
    corpus.control.commit_compilation(compilation=first, git_commit="commit-first")
    second = first.model_copy(
        update={
            "compilation_id": uuid4(),
            "citations": (
                KnowledgeCitation(
                    role=KnowledgeEvidenceRole.CITES, doc_id=corpus.docs["drive"]
                ),
            ),
            "page_summary": "Second summary.",
            "content_hash": "second-content",
            "uncited_count": first.candidate_count,
        }
    )
    corpus.control.record_pending_compilation(compilation=second)
    with corpus.engine.connect() as connection:
        live_before_push = (
            connection.execute(
                text(
                    "SELECT claim_id, relation_id, doc_id"
                    " FROM knowledge_artifact_evidence WHERE artifact_id = :a"
                    " ORDER BY claim_id NULLS LAST, relation_id NULLS LAST"
                ),
                {"a": page},
            )
            .mappings()
            .all()
        )
        pending_commit = connection.execute(
            text(
                "SELECT git_commit FROM knowledge_compilations"
                " WHERE compilation_id = :c"
            ),
            {"c": second.compilation_id},
        ).scalar_one()
    assert len(live_before_push) == 2
    assert all(row["doc_id"] is None for row in live_before_push)
    assert pending_commit is None
    corpus.control.commit_compilation(compilation=second, git_commit="commit-second")
    corpus.control.commit_compilation(compilation=second, git_commit="commit-second")
    with corpus.engine.connect() as connection:
        citations = (
            connection.execute(
                text(
                    "SELECT claim_id, relation_id, doc_id"
                    " FROM knowledge_artifact_evidence WHERE artifact_id = :a"
                ),
                {"a": page},
            )
            .mappings()
            .all()
        )
        transcript = (
            connection.execute(
                text(
                    "SELECT cited_count, uncited_count, evidence_added, evidence_removed"
                    " FROM knowledge_compilations WHERE compilation_id = :c"
                ),
                {"c": second.compilation_id},
            )
            .mappings()
            .one()
        )
    assert citations == [
        {"claim_id": None, "relation_id": None, "doc_id": corpus.docs["drive"]}
    ]
    assert transcript["cited_count"] == 1
    assert transcript["uncited_count"] == second.uncited_count
    assert transcript["evidence_added"] == 1
    assert transcript["evidence_removed"] == 2

    invalid = second.model_copy(
        update={
            "compilation_id": uuid4(),
            "citations": (
                KnowledgeCitation(role=KnowledgeEvidenceRole.CITES, doc_id=uuid4()),
            ),
        }
    )
    with pytest.raises(KnowledgeCompilationError):
        corpus.control.record_pending_compilation(compilation=invalid)
