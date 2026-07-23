"""WP-4.2 acceptance: the P2 rebuild pipeline on a toy corpus.

Rebuild → validate → snapshot → publish → reader hot-swap, against real
PostgreSQL and the real embedded graph engine. The two correctness rules
ride the export by construction and are asserted in the LOADED graph:
merge-redirect (an edge recorded under an absorbed entity attaches to its
survivor) and keep-retracted (invalidated edges project; liveness derives
inline). The validation gate aborts on a planted merge cycle without
touching the published pointer.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID
from uuid import uuid4

from alembic import command
from alembic.config import Config
import ladybug
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine

from rememberstack.adapters.selfhost import LocalFSObjectStore
from rememberstack.model import DeploymentBootstrapInput
from rememberstack.spine import DeploymentBootstrapper
from rememberstack.spine import ProjectionCatalog
from rememberstack.spine.settings import load_database_settings
from rememberstack.workers import GraphRebuildWorker
from rememberstack.workers import GraphSnapshotReader
from rememberstack.workers import SnapshotValidationError

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("42000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL integration engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip(
            "REMEMBERSTACK_DATABASE_URL is required for real PostgreSQL rebuild proofs"
        )
    config = Config(str(_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config=config, revision="base")
    command.upgrade(config=config, revision="head")
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


class _Corpus:
    """The toy corpus: a merge chain, live and retracted edges, one document."""

    def __init__(self, *, engine: Engine) -> None:
        """Seed the canonical toy graph."""
        self.engine = engine
        self.alice = uuid4()  # active
        self.acme = uuid4()  # active
        self.absorbed = uuid4()  # merged → mid → alice
        self.mid = uuid4()
        self.doc_id = uuid4()
        self.doc_entity = uuid4()  # Document-typed entity bridged to doc_id
        self.live_relation = uuid4()  # recorded under the ABSORBED endpoint
        self.retracted_relation = uuid4()
        with engine.begin() as connection:
            for entity_id, name in (
                (self.alice, "Alice Novak"),
                (self.acme, "Acme"),
                (self.doc_entity, "Quarterly Report"),
            ):
                _seed_entity(connection, entity_id=entity_id, name=name)
            _seed_entity(
                connection,
                entity_id=self.mid,
                name="A. Novak",
                status="merged",
                merged_into=self.alice,
            )
            _seed_entity(
                connection,
                entity_id=self.absorbed,
                name="Novakova",
                status="merged",
                merged_into=self.mid,
            )
            connection.execute(
                text(
                    "INSERT INTO documents (doc_id, deployment_id, source_kind,"
                    " source_ref, title, document_entity_id)"
                    " VALUES (:doc, :d, 'upload', 'toy-ref', 'Quarterly Report',"
                    " :bridge)"
                ),
                {"doc": self.doc_id, "d": _DEPLOYMENT_ID, "bridge": self.doc_entity},
            )
            connection.execute(
                text(
                    "INSERT INTO relations (relation_id, deployment_id,"
                    " subject_entity_id, predicate, object_entity_id,"
                    " normalizer_version, fact_label)"
                    " VALUES (:r, :d, :subject, 'works_for', :object, 'toy',"
                    " 'Alice works for Acme')"
                ),
                {
                    "r": self.live_relation,
                    "d": _DEPLOYMENT_ID,
                    "subject": self.absorbed,  # the merge-redirect proof
                    "object": self.acme,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO relations (relation_id, deployment_id,"
                    " subject_entity_id, predicate, object_entity_id,"
                    " normalizer_version, fact_label, invalidated_at)"
                    " VALUES (:r, :d, :subject, 'works_for', :object, 'toy',"
                    " 'Alice worked for Initech', now())"
                ),
                {
                    "r": self.retracted_relation,
                    "d": _DEPLOYMENT_ID,
                    "subject": self.alice,
                    "object": self.acme,
                },
            )
            mention_id = uuid4()
            connection.execute(
                text(
                    "INSERT INTO mentions (mention_id, deployment_id,"
                    " surface_form, normalized_lemma, doc_id)"
                    " VALUES (:m, :d, 'Novakova', 'novakova', :doc)"
                ),
                {"m": mention_id, "d": _DEPLOYMENT_ID, "doc": self.doc_id},
            )
            connection.execute(
                text(
                    "INSERT INTO resolution_decisions (decision_id,"
                    " deployment_id, mention_id, entity_id, method, confidence,"
                    " resolver_version)"
                    " VALUES (:id, :d, :m, :entity, 'T0', 1.0, 'toy')"
                ),
                {
                    "id": uuid4(),
                    "d": _DEPLOYMENT_ID,
                    "m": mention_id,
                    "entity": self.absorbed,  # resolves via the survivor chain
                },
            )
            second_doc = uuid4()
            connection.execute(
                text(
                    "INSERT INTO documents (doc_id, deployment_id, source_kind,"
                    " source_ref, title) VALUES (:doc, :d, 'upload', 'other',"
                    " 'Cited Note')"
                ),
                {"doc": second_doc, "d": _DEPLOYMENT_ID},
            )
            connection.execute(
                text(
                    "INSERT INTO document_crossrefs (crossref_id, deployment_id,"
                    " from_doc_id, to_doc_id, kind, resolved)"
                    " VALUES (:c, :d, :from_doc, :to_doc, 'cites', true)"
                ),
                {
                    "c": uuid4(),
                    "d": _DEPLOYMENT_ID,
                    "from_doc": self.doc_id,
                    "to_doc": second_doc,
                },
            )


def _seed_entity(
    connection: object,
    *,
    entity_id: UUID,
    name: str,
    status: str = "active",
    merged_into: UUID | None = None,
) -> None:
    """One entity row with the minimum the projection reads."""
    connection.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO entities (entity_id, deployment_id, type,"
            " canonical_name, normalized_name, status, merged_into)"
            " VALUES (:e, :d, 'Person', :n, lower(:n),"
            " CAST(:s AS entity_status), :m)"
        ),
        {"e": entity_id, "d": _DEPLOYMENT_ID, "n": name, "s": status, "m": merged_into},
    )


@pytest.fixture()
def corpus(database_engine: Engine) -> _Corpus:
    """A fresh deployment carrying the toy corpus."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
        for table in ("mentions", "resolution_decisions"):
            connection.execute(statement=text(f"TRUNCATE TABLE {table} CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="p2-rebuild-test",
            name="P2 rebuild proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )
    return _Corpus(engine=database_engine)


def _rig(
    engine: Engine, root: Path
) -> tuple[GraphRebuildWorker, GraphSnapshotReader, ProjectionCatalog]:
    """A worker + reader over one snapshot store."""
    catalog = ProjectionCatalog(engine=engine)
    store = LocalFSObjectStore(root=root / "snapshots")
    worker = GraphRebuildWorker(catalog=catalog, snapshot_store=store)
    reader = GraphSnapshotReader(
        catalog=catalog,
        snapshot_store=store,
        deployment_id=_DEPLOYMENT_ID,
        cache_dir=root / "reader-cache",
    )
    return worker, reader, catalog


def _scalar(connection: ladybug.Connection, query: str) -> object:
    """One scalar from the graph."""
    result = connection.execute(query)
    assert isinstance(result, ladybug.QueryResult)
    return cast("list[object]", result.get_next())[0]


def test_rebuild_publishes_a_validated_snapshot(
    corpus: _Corpus, tmp_path: Path
) -> None:
    """The full cycle lands: counts recorded, registry pointer set, manifest
    shipped — and the loaded graph carries both correctness rules."""
    worker, reader, catalog = _rig(corpus.engine, tmp_path)
    result = worker.rebuild(deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work")
    counts = cast("dict[str, int]", result["row_counts"])
    assert counts["Entity"] == 3  # merged entities are not nodes
    assert counts["Document"] == 2
    assert counts["RELATES"] == 2  # live + retracted both project (D69)
    assert counts["MENTIONED_IN"] == 1
    assert counts["DOC_CROSSREF"] == 1
    assert counts["IS_DOCUMENT"] == 1
    latest = catalog.latest_snapshot(deployment_id=_DEPLOYMENT_ID, plane="P2_graph")
    assert latest is not None
    assert latest["version"] == result["version"]

    reader.refresh()
    graph = reader.connection()
    # merge-redirect: the edge recorded under the ABSORBED entity attaches
    # to the terminal survivor (two redirect hops away)
    redirected = _scalar(
        graph,
        "MATCH (a:Entity {name: 'Alice Novak'})-[r:RELATES]->"
        "(b:Entity {name: 'Acme'}) RETURN count(*)",
    )
    assert redirected == 2  # both edges landed on the survivor
    # keep-retracted: the invalidated edge projects; liveness derives inline
    live = _scalar(
        graph, "MATCH ()-[r:RELATES]->() WHERE r.invalidated_at IS NULL RETURN count(*)"
    )
    assert live == 1
    mentioned = _scalar(
        graph,
        "MATCH (a:Entity {name: 'Alice Novak'})-[m:MENTIONED_IN]->(d:Document)"
        " RETURN m.mention_count",
    )
    assert mentioned == 1  # the mention resolved through the survivor chain
    bridged = _scalar(graph, "MATCH ()-[b:IS_DOCUMENT]->() RETURN count(*)")
    assert bridged == 1


def test_validation_gate_aborts_on_a_merge_cycle(
    corpus: _Corpus, tmp_path: Path
) -> None:
    """A planted merge cycle aborts the snapshot loudly — the failed row
    records the offenders and the published pointer never moves."""
    worker, _, catalog = _rig(corpus.engine, tmp_path)
    first = worker.rebuild(deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work")

    x, y = uuid4(), uuid4()
    with corpus.engine.begin() as connection:
        _seed_entity(connection, entity_id=x, name="cyc-x")
        _seed_entity(
            connection, entity_id=y, name="cyc-y", status="merged", merged_into=x
        )
        connection.execute(
            text(
                "UPDATE entities SET status = 'merged', merged_into = :y"
                " WHERE entity_id = :x"
            ),
            {"x": x, "y": y},
        )
    with pytest.raises(SnapshotValidationError, match="survivor"):
        worker.rebuild(deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work")
    latest = catalog.latest_snapshot(deployment_id=_DEPLOYMENT_ID, plane="P2_graph")
    assert latest is not None
    assert latest["version"] == first["version"]  # the pointer never moved
    with corpus.engine.connect() as connection:
        failed = connection.execute(
            text(
                "SELECT validation ->> 'gate' FROM projection_snapshots"
                " WHERE status = 'failed'"
            )
        ).scalar_one()
    assert failed == "unresolved_survivors"


def test_reader_hot_swaps_to_a_newer_snapshot(corpus: _Corpus, tmp_path: Path) -> None:
    """The reader serves v1, keeps serving through a rebuild, and swaps to
    v2 on refresh — old snapshots remain point-in-time artifacts."""
    worker, reader, _ = _rig(corpus.engine, tmp_path)
    first = worker.rebuild(deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work")
    assert reader.refresh() is True
    assert reader.version == first["version"]
    assert reader.refresh() is False  # nothing newer: no churn

    with corpus.engine.begin() as connection:  # the corpus grows
        _seed_entity(connection, entity_id=uuid4(), name="Newcomer")
    second = worker.rebuild(deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work")
    assert reader.version == first["version"]  # stable until asked
    assert reader.refresh() is True
    assert reader.version == second["version"]
    nodes = _scalar(reader.connection(), "MATCH (e:Entity) RETURN count(*)")
    assert nodes == 4  # the newcomer arrived with the swap


def test_out_of_order_publish_never_regresses_the_pointer(
    corpus: _Corpus, tmp_path: Path
) -> None:
    """Codex review: a slow OLD rebuild finishing after a newer one must not
    take the pointer back — it lands as superseded, readers never regress."""
    worker, _, catalog = _rig(corpus.engine, tmp_path)
    slow_id = catalog.open_snapshot(  # the older cut, registered first…
        deployment_id=_DEPLOYMENT_ID,
        plane="P2_graph",
        version="v-old-slow",
        store_prefix="graph/snapshots/test/v-old-slow",
    )
    fresh = worker.rebuild(  # …and the newer rebuild completes first
        deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work"
    )
    took_pointer = catalog.publish(
        deployment_id=_DEPLOYMENT_ID,
        snapshot_id=slow_id,
        plane="P2_graph",
        row_counts={},
        validation={"gate": "passed"},
        built_from_watermark=None,
    )
    assert took_pointer is False  # the late old snapshot never wins
    latest = catalog.latest_snapshot(deployment_id=_DEPLOYMENT_ID, plane="P2_graph")
    assert latest is not None
    assert latest["version"] == fresh["version"]
    with corpus.engine.connect() as connection:
        status = connection.execute(
            text(
                "SELECT status::text FROM projection_snapshots WHERE snapshot_id = :s"
            ),
            {"s": slow_id},
        ).scalar_one()
    assert status == "superseded"


def test_load_failures_are_recorded_never_stranded(
    corpus: _Corpus, tmp_path: Path
) -> None:
    """Codex review: a COPY that throws (a crossref to a document absent
    from the emitted nodes) lands as a recorded FAILED snapshot with the
    error, never an eternally 'building' row — and the pointer is safe."""
    worker, _, catalog = _rig(corpus.engine, tmp_path)
    first = worker.rebuild(deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work")
    ghost = uuid4()
    with corpus.engine.begin() as connection:  # crossref → soon-deleted doc
        connection.execute(
            text(
                "INSERT INTO documents (doc_id, deployment_id, source_kind,"
                " source_ref, title, deleted_at)"
                " VALUES (:doc, :d, 'upload', 'ghost', 'Ghost', now())"
            ),
            {"doc": ghost, "d": _DEPLOYMENT_ID},
        )
        connection.execute(
            text(
                "INSERT INTO document_crossrefs (crossref_id, deployment_id,"
                " from_doc_id, to_doc_id, kind, resolved)"
                " VALUES (:c, :d, :from_doc, :to_doc, 'cites', true)"
            ),
            {
                "c": uuid4(),
                "d": _DEPLOYMENT_ID,
                "from_doc": corpus.doc_id,
                "to_doc": ghost,
            },
        )
    with pytest.raises(Exception, match="(?i)copy|not found|exist"):
        worker.rebuild(deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work")
    with corpus.engine.connect() as connection:
        gate = connection.execute(
            text(
                "SELECT validation ->> 'gate' FROM projection_snapshots"
                " WHERE status = 'failed' ORDER BY built_at DESC LIMIT 1"
            )
        ).scalar_one()
        stuck = connection.execute(
            text("SELECT count(*) FROM projection_snapshots WHERE status = 'building'")
        ).scalar_one()
    assert gate == "exception"
    assert stuck == 0  # nothing stranded
    latest = catalog.latest_snapshot(deployment_id=_DEPLOYMENT_ID, plane="P2_graph")
    assert latest is not None
    assert latest["version"] == first["version"]  # the pointer is safe
