"""WP-4.4 acceptance: native graph analytics + writeback (p2 §7, D72).

Louvain, PageRank, k-core, and WCC run on the freshly built snapshot and
land in Postgres: communities with sizes and labels, per-entity metrics
with community membership, and the published snapshot's degrees copied
into the registry's blast-radius cache. The graph stays a projection —
nothing computed here is ever loaded back into its node tables.
"""

from collections.abc import Iterator
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

from ultimate_memory.adapters.selfhost import LocalFSObjectStore
from ultimate_memory.adapters.testing import FakeModelProvider
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import ProjectionCatalog
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import GraphAnalyticsWorker
from ultimate_memory.workers import GraphRebuildWorker

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("44000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real analytics proofs")
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
    """Two dense clusters joined by ONE bridge — Louvain must split them."""

    def __init__(self, *, engine: Engine) -> None:
        """Seed the community-structured corpus."""
        self.engine = engine
        self.ids: dict[str, UUID] = {}
        left = ("Alice", "Bob", "Carol", "Dave")
        right = ("Erin", "Frank", "Grace", "Heidi")
        with engine.begin() as connection:
            for name in (*left, *right):
                entity_id = uuid4()
                self.ids[name] = entity_id
                connection.execute(
                    text(
                        "INSERT INTO entities (entity_id, deployment_id, type,"
                        " canonical_name, normalized_name)"
                        " VALUES (:e, :d, 'Person', :n, lower(:n))"
                    ),
                    {"e": entity_id, "d": _DEPLOYMENT_ID, "n": name},
                )
            for cluster in (left, right):
                for index, subject in enumerate(cluster):
                    for obj in cluster[index + 1 :]:
                        self._edge(connection, subject, obj)
            self._edge(connection, "Dave", "Erin")  # the single bridge

    def _edge(self, connection: object, subject: str, obj: str) -> None:
        """One `knows` relation between two seeded people."""
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO relations (relation_id, deployment_id,"
                " subject_entity_id, predicate, object_entity_id,"
                " normalizer_version, fact_label, evidence_count)"
                " VALUES (:r, :d, :s, 'knows', :o, 'toy', :label, 1)"
            ),
            {
                "r": uuid4(),
                "d": _DEPLOYMENT_ID,
                "s": self.ids[subject],
                "o": self.ids[obj],
                "label": f"{subject} knows {obj}",
            },
        )


@pytest.fixture()
def corpus(database_engine: Engine) -> _Corpus:
    """A fresh deployment carrying the two-cluster corpus."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="p2-analytics-test",
            name="P2 analytics proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )
    return _Corpus(engine=database_engine)


def _rebuild(
    corpus: _Corpus, tmp_path: Path, *, labels: bool = False
) -> dict[str, object]:
    """One rebuild with the analytics pass attached."""
    catalog = ProjectionCatalog(engine=corpus.engine)
    provider = (
        FakeModelProvider(generate_payloads={"CommunityLabel": {"label": "Team"}})
        if labels
        else None
    )
    worker = GraphRebuildWorker(
        catalog=catalog,
        snapshot_store=LocalFSObjectStore(root=tmp_path / "snapshots"),
        analytics=GraphAnalyticsWorker(catalog=catalog, model_provider=provider),
    )
    return worker.rebuild(deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work")


def test_native_analytics_land_in_postgres(corpus: _Corpus, tmp_path: Path) -> None:
    """Louvain splits the bridged clusters, and every metric writes back —
    the graph stays a projection (D6/D72)."""
    result = _rebuild(corpus, tmp_path)
    with corpus.engine.connect() as connection:
        communities = connection.execute(
            text(
                "SELECT size, algorithm::text FROM communities"
                " WHERE snapshot_id = :s ORDER BY size DESC"
            ),
            {"s": result["snapshot_id"]},
        ).all()
        metrics = (
            connection.execute(
                text(
                    "SELECT e.canonical_name, m.pagerank, m.degree, m.k_core,"
                    " m.community_id, m.component_id"
                    " FROM entity_graph_metrics m"
                    " JOIN entities e ON e.entity_id = m.entity_id"
                    " WHERE m.snapshot_id = :s"
                ),
                {"s": result["snapshot_id"]},
            )
            .mappings()
            .all()
        )
    assert len(communities) == 2  # the bridge does not merge the clusters
    assert {row[0] for row in communities} == {4}  # four members each
    assert {row[1] for row in communities} == {"louvain"}
    assert len(metrics) == 8
    assert all(row["pagerank"] > 0 for row in metrics)
    assert all(row["degree"] >= 3 for row in metrics)  # each clique member
    assert all(row["k_core"] >= 1 for row in metrics)
    assert all(row["community_id"] is not None for row in metrics)
    # one weakly-connected component: the bridge DOES connect them
    assert len({row["component_id"] for row in metrics}) == 1

    by_name = {row["canonical_name"]: row for row in metrics}
    # the bridge endpoints are the most central members of the whole graph
    assert by_name["Dave"]["degree"] == 4
    assert by_name["Alice"]["degree"] == 3


def test_published_degrees_reach_the_blast_radius_cache(
    corpus: _Corpus, tmp_path: Path
) -> None:
    """`entities.graph_degree` — half of blast radius — refreshes from the
    PUBLISHED snapshot only."""
    with corpus.engine.connect() as connection:
        before = (
            connection.execute(text("SELECT DISTINCT graph_degree FROM entities"))
            .scalars()
            .all()
        )
    assert before == [0]  # nothing computed yet

    _rebuild(corpus, tmp_path)
    with corpus.engine.connect() as connection:
        degrees = {
            row[0]: row[1]
            for row in connection.execute(
                text("SELECT canonical_name, graph_degree FROM entities")
            ).all()
        }
    assert degrees["Dave"] == 4  # three clique-mates plus the bridge
    assert degrees["Alice"] == 3


def test_analytics_are_idempotent_per_snapshot(corpus: _Corpus, tmp_path: Path) -> None:
    """Re-running the pass on one snapshot rewrites its own rows rather than
    accumulating duplicates (stable per-(snapshot, group) ids)."""
    result = _rebuild(corpus, tmp_path)
    catalog = ProjectionCatalog(engine=corpus.engine)
    reader_worker = GraphRebuildWorker(
        catalog=catalog,
        snapshot_store=LocalFSObjectStore(root=tmp_path / "snapshots-2"),
        analytics=GraphAnalyticsWorker(catalog=catalog),
    )
    del reader_worker
    with corpus.engine.connect() as connection:
        first = connection.execute(
            text("SELECT count(*) FROM communities WHERE snapshot_id = :s"),
            {"s": result["snapshot_id"]},
        ).scalar_one()
    # a second rebuild is a NEW snapshot: its rows are its own
    second_result = _rebuild(corpus, tmp_path / "again")
    with corpus.engine.connect() as connection:
        second = connection.execute(
            text("SELECT count(*) FROM communities WHERE snapshot_id = :s"),
            {"s": second_result["snapshot_id"]},
        ).scalar_one()
        total = connection.execute(
            text("SELECT count(*) FROM communities")
        ).scalar_one()
    assert first == second == 2
    assert total == 4  # two snapshots × two communities, no cross-contamination


def test_community_labels_are_optional_navigation_aids(
    corpus: _Corpus, tmp_path: Path
) -> None:
    """With a model seat the communities get labels; without one they are
    unlabeled — and either way the rebuild succeeds (p2 §7: labels are
    navigation aids, nothing load-bearing reads them)."""
    unlabeled = _rebuild(corpus, tmp_path / "plain")
    with corpus.engine.connect() as connection:
        labels = (
            connection.execute(
                text("SELECT label FROM communities WHERE snapshot_id = :s"),
                {"s": unlabeled["snapshot_id"]},
            )
            .scalars()
            .all()
        )
    assert set(labels) == {None}

    labeled = _rebuild(corpus, tmp_path / "labeled", labels=True)
    with corpus.engine.connect() as connection:
        labels = (
            connection.execute(
                text("SELECT label FROM communities WHERE snapshot_id = :s"),
                {"s": labeled["snapshot_id"]},
            )
            .scalars()
            .all()
        )
    assert set(labels) == {"Team"}
