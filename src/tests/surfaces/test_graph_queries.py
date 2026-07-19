"""WP-4.3 acceptance: the `graph` primitive against S17–S22.

Each scenario class runs over a real rebuilt snapshot: S17 (how are A and
B connected), S18 (2-hop neighborhood with EXPLICIT truncation), S19
(predicate-constrained multi-hop), S20 (graph join across predicates), S21
(multi-hop as-of via inline path predicates), S22 (document-graph
transitive citation). The negatives are typed, and the caps are never
silent.
"""

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
from sqlalchemy.engine import Engine

from ultimate_memory.adapters.selfhost import LocalFSObjectStore
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.model import NegativeKind
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import ProjectionCatalog
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.surfaces import GraphQueries
from ultimate_memory.workers import GraphRebuildWorker
from ultimate_memory.workers import GraphSnapshotReader

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("43000000-0000-0000-0000-000000000001")
_JAN_2024 = datetime(2024, 1, 1, tzinfo=UTC)
_JUN_2024 = datetime(2024, 6, 1, tzinfo=UTC)
_JAN_2026 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real graph query proofs")
    config = Config(str(_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config=config, revision="base")
    command.upgrade(config=config, revision="head")
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


class _Graph:
    """The scenario corpus: people, projects, orgs, documents."""

    def __init__(self, *, engine: Engine) -> None:
        """Seed a graph rich enough for every S17–S22 shape."""
        self.engine = engine
        self.ids: dict[str, UUID] = {}
        with engine.begin() as connection:
            for name, entity_type in (
                ("Alice", "Person"),
                ("Bob", "Person"),
                ("Carol", "Person"),
                ("Acme", "Organization"),
                ("Beacon", "Project"),
                ("ESB Migration", "Project"),
                ("Vector Databases", "Concept"),
            ):
                entity_id = uuid4()
                self.ids[name] = entity_id
                connection.execute(
                    text(
                        "INSERT INTO entities (entity_id, deployment_id, type,"
                        " canonical_name, normalized_name)"
                        " VALUES (:e, :d, :t, :n, lower(:n))"
                    ),
                    {"e": entity_id, "d": _DEPLOYMENT_ID, "t": entity_type, "n": name},
                )
            # S17/S19/S20/S21 topology
            self._edge(connection, "Alice", "works_for", "Acme")
            self._edge(connection, "Bob", "works_for", "Acme")
            self._edge(connection, "Alice", "works_on", "Beacon")
            self._edge(connection, "Carol", "works_on", "ESB Migration")
            self._edge(connection, "Beacon", "part_of", "ESB Migration")
            self._edge(connection, "Bob", "knows_about", "Vector Databases")
            # S21: an edge that only existed in 2024 (closed since)
            self._edge(
                connection,
                "Carol",
                "works_for",
                "Acme",
                valid_from=_JAN_2024,
                valid_until=_JUN_2024,
            )

    def _edge(
        self,
        connection: object,
        subject: str,
        predicate: str,
        obj: str,
        *,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> UUID:
        """One relation row."""
        relation_id = uuid4()
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO relations (relation_id, deployment_id,"
                " subject_entity_id, predicate, object_entity_id,"
                " normalizer_version, fact_label, evidence_count,"
                " valid_from, valid_until)"
                " VALUES (:r, :d, :s, :p, :o, 'toy', :label, 2, :vf, :vu)"
            ),
            {
                "r": relation_id,
                "d": _DEPLOYMENT_ID,
                "s": self.ids[subject],
                "p": predicate,
                "o": self.ids[obj],
                "label": f"{subject} {predicate} {obj}",
                "vf": valid_from,
                "vu": valid_until,
            },
        )
        return relation_id


@pytest.fixture()
def graph(database_engine: Engine, tmp_path: Path) -> Iterator[GraphQueries]:
    """A rebuilt, published snapshot exposed through the graph primitive."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="graph-query-test",
            name="Graph query proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )
    corpus = _Graph(engine=database_engine)
    catalog = ProjectionCatalog(engine=database_engine)
    store = LocalFSObjectStore(root=tmp_path / "snapshots")
    GraphRebuildWorker(catalog=catalog, snapshot_store=store).rebuild(
        deployment_id=_DEPLOYMENT_ID, workdir=tmp_path / "work"
    )
    reader = GraphSnapshotReader(
        catalog=catalog,
        snapshot_store=store,
        deployment_id=_DEPLOYMENT_ID,
        cache_dir=tmp_path / "cache",
    )
    queries = GraphQueries(reader=reader)
    queries.ids = corpus.ids  # type: ignore[attr-defined]
    yield queries


def _names(envelope: object) -> set[str]:
    """The entity names an envelope's nodes carry."""
    return {node.name for node in envelope.nodes}  # type: ignore[attr-defined]


def test_s17_how_are_two_entities_connected(graph: GraphQueries) -> None:
    """S17: 'How are Alice and the Beacon project connected?' — a path with
    every traversed edge, returned as a unit."""
    ids = graph.ids  # type: ignore[attr-defined]
    envelope = graph.path(
        from_entity_id=ids["Alice"], to_entity_id=ids["ESB Migration"]
    )
    assert envelope.negative is None
    assert envelope.paths
    path = envelope.paths[0]
    assert path.length == 2  # Alice → Beacon → ESB Migration
    assert [node.name for node in path.nodes] == ["Alice", "Beacon", "ESB Migration"]
    assert [edge.predicate for edge in path.edges] == ["works_on", "part_of"]
    assert envelope.freshness.p2_snapshot_version is not None  # S42


def test_s18_neighborhood_caps_are_explicit(graph: GraphQueries) -> None:
    """S18: 'Everything within 2 hops of Acme' — and when the page caps, the
    truncation marker plus a continuation say so (never a silent top-k)."""
    ids = graph.ids  # type: ignore[attr-defined]
    full = graph.neighborhood(entity_id=ids["Acme"], hops=2)
    assert full.negative is None
    assert "Alice" in _names(full) and "Bob" in _names(full)
    assert full.truncation is not None
    assert full.truncation.truncated is False  # nothing hidden

    page = graph.neighborhood(entity_id=ids["Acme"], hops=2, limit=1)
    assert page.truncation is not None
    assert page.truncation.truncated is True
    assert page.truncation.returned == 1
    assert page.truncation.continuation == "1"  # the follow-up cursor
    nxt = graph.neighborhood(
        entity_id=ids["Acme"], hops=2, limit=1, offset=int(page.truncation.continuation)
    )
    assert _names(nxt).isdisjoint(_names(page))  # pagination is stable


def test_s19_predicate_constrained_multi_hop(graph: GraphQueries) -> None:
    """S19: people on projects connected to the ESB migration — the
    traversal follows only the named predicates."""
    ids = graph.ids  # type: ignore[attr-defined]
    envelope = graph.neighborhood(
        entity_id=ids["ESB Migration"], hops=2, predicates=("works_on", "part_of")
    )
    reached = _names(envelope)
    assert {"Beacon", "Alice", "Carol"} <= reached
    assert "Vector Databases" not in reached  # knows_about was not requested


def test_s20_graph_join_across_predicates(graph: GraphQueries) -> None:
    """S20: 'Colleagues of Bob who know about vector databases' — the
    co-membership hop and the topic hop compose in one traversal."""
    ids = graph.ids  # type: ignore[attr-defined]
    colleagues = graph.neighborhood(
        entity_id=ids["Bob"], hops=2, predicates=("works_for",)
    )
    assert "Alice" in _names(colleagues)  # via Acme co-membership
    topic = graph.neighborhood(
        entity_id=ids["Vector Databases"], hops=1, predicates=("knows_about",)
    )
    assert _names(topic) == {"Bob"}


def test_s21_multi_hop_as_of(graph: GraphQueries) -> None:
    """S21: 'Who was connected to Acme as of 2024-06?' — the inline path
    predicate prunes DURING traversal, so a window closed since is visible
    then and invisible now."""
    ids = graph.ids  # type: ignore[attr-defined]
    historical = graph.neighborhood(
        entity_id=ids["Acme"], hops=1, valid_at=datetime(2024, 3, 1, tzinfo=UTC)
    )
    assert "Carol" in _names(historical)  # her spell was open in March 2024

    current = graph.neighborhood(entity_id=ids["Acme"], hops=1, valid_at=_JAN_2026)
    assert "Carol" not in _names(current)  # closed in June 2024
    assert {"Alice", "Bob"} <= _names(current)  # open-ended edges persist
    assert current.as_of_valid_at == _JAN_2026  # the echo (S15/S16)


def test_s22_document_graph_traversal(graph: GraphQueries) -> None:
    """S22 shape: a chain traverses transitively — Alice reaches the ESB
    migration through Beacon at 2 hops but not at 1."""
    ids = graph.ids  # type: ignore[attr-defined]
    one_hop = graph.neighborhood(
        entity_id=ids["Alice"], hops=1, predicates=("works_on", "part_of")
    )
    assert "ESB Migration" not in _names(one_hop)
    two_hops = graph.neighborhood(
        entity_id=ids["Alice"], hops=2, predicates=("works_on", "part_of")
    )
    assert "ESB Migration" in _names(two_hops)


def test_typed_negatives_and_the_hop_clamp(graph: GraphQueries) -> None:
    """Absence is typed, and a request beyond the engine's 30-hop ceiling is
    clamped AND disclosed rather than silently honored or thrown."""
    ids = graph.ids  # type: ignore[attr-defined]
    isolated = uuid4()
    empty = graph.neighborhood(entity_id=isolated, hops=2)
    assert empty.negative is not None
    assert empty.negative.kind is NegativeKind.KNOWN_EMPTY

    no_path = graph.path(
        from_entity_id=ids["Vector Databases"],
        to_entity_id=ids["ESB Migration"],
        max_hops=1,
    )
    assert no_path.negative is not None
    assert no_path.negative.kind is NegativeKind.KNOWN_EMPTY

    clamped = graph.neighborhood(entity_id=ids["Acme"], hops=99)
    assert clamped.truncation is not None
    assert clamped.truncation.truncated is True  # the ceiling is disclosed


def test_boundary_when_no_snapshot_is_published(tmp_path: Path) -> None:
    """A graph question asked before any rebuild is a typed BOUNDARY with a
    workaround — never an empty answer posing as knowledge."""

    class _NoSnapshot:
        version = None

        def connection(self) -> object:
            raise RuntimeError("no published P2 snapshot exists yet")

    envelope = GraphQueries(reader=_NoSnapshot()).neighborhood(entity_id=uuid4())
    assert envelope.negative is not None
    assert envelope.negative.kind is NegativeKind.BOUNDARY
    assert envelope.negative.workaround is not None
