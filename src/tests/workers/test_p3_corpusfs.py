"""WP-4.5 acceptance: the P3 corpus filesystem (e0 §6, D40).

The tree rebuilds whole, publishes as an immutable snapshot, and satisfies
the two contracts that make it worth having: **Tier-1 paths never move
across rebuilds** (S44's durable targets), and **one `_index.md` read tells
an agent what every file in the directory is about** — navigation cheaper
than search, with zero LLM inside the builder.
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
from ultimate_memory.model import ObjectKey
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import ProjectionCatalog
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import CorpusFsBuilder
from ultimate_memory.workers import CorpusFsSettings

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("45000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real corpus-fs proofs")
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
    """A small corpus with summaries, placements, entities, and mentions."""

    def __init__(self, *, engine: Engine) -> None:
        """Seed documents (with root-section summaries) and one entity."""
        self.engine = engine
        self.docs: dict[str, UUID] = {}
        self.entity_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO entities (entity_id, deployment_id, type,"
                    " canonical_name, normalized_name, profile_summary,"
                    " mention_count)"
                    " VALUES (:e, :d, 'Organization', 'Acme', 'acme',"
                    " 'A manufacturer of anvils.', 3)"
                ),
                {"e": self.entity_id, "d": _DEPLOYMENT_ID},
            )
            for title, placement, summary in (
                (
                    "Annual Report",
                    "/finance/annual-reports/2023/",
                    "Acme's 2023 results.",
                ),
                ("Design Note", "/research/anvils/", "How the anvil is shaped."),
                ("Loose Memo", None, "An unfiled memo."),
            ):
                self.docs[title] = self._document(
                    connection, title=title, placement=placement, summary=summary
                )

    def _document(
        self, connection: object, *, title: str, placement: str | None, summary: str
    ) -> UUID:
        """One lineage with a ready version, representation, and root section."""
        doc_id, version_id, representation_id = uuid4(), uuid4(), uuid4()
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO documents (doc_id, deployment_id, source_kind,"
                " source_ref, title) VALUES (:doc, :d, 'upload', :ref, :title)"
            ),
            {"doc": doc_id, "d": _DEPLOYMENT_ID, "ref": title.lower(), "title": title},
        )
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO content_objects (deployment_id, content_hash, mime,"
                " byte_size, raw_uri) VALUES (:d, :h, 'text/markdown', 10, :uri)"
                " ON CONFLICT DO NOTHING"
            ),
            {"d": _DEPLOYMENT_ID, "h": f"hash-{title}", "uri": f"raw/{doc_id}"},
        )
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO document_versions (version_id, deployment_id, doc_id,"
                " content_hash, version_no, status, source_modified_at)"
                " VALUES (:v, :d, :doc, :h, 1, 'ready', :modified)"
            ),
            {
                "v": version_id,
                "d": _DEPLOYMENT_ID,
                "doc": doc_id,
                "h": f"hash-{title}",
                "modified": datetime(2024, 3, 15, tzinfo=UTC),
            },
        )
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO document_representations (representation_id,"
                " deployment_id, version_id, route, converter_name,"
                " converter_version, blockizer_version, markdown_uri, blocks_uri,"
                " conversion_uri, meta_uri, markdown_hash, manifest_hash, status)"
                " VALUES (:r, :d, :v, 'markdown', 'passthrough', '1', '1',"
                " :md, 'b', 'c', 'm', 'mh', 'sh', 'ready')"
            ),
            {
                "r": representation_id,
                "d": _DEPLOYMENT_ID,
                "v": version_id,
                "md": f"{doc_id}/document.md",
            },
        )
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO document_sections (section_id, deployment_id, doc_id,"
                " version_id, representation_id, node_path, block_start, block_end,"
                " title, role, char_start, char_end, ordinal, summary,"
                " placement_path, structurer_version)"
                " VALUES (:s, :d, :doc, :v, :r, '0', 0, 1, :title, 'body', 0, 10,"
                " 0, :summary, :placement, 'test')"
            ),
            {
                "s": uuid4(),
                "d": _DEPLOYMENT_ID,
                "doc": doc_id,
                "v": version_id,
                "r": representation_id,
                "title": title,
                "summary": summary,
                "placement": placement,
            },
        )
        connection.execute(  # type: ignore[attr-defined]
            text(
                "UPDATE document_versions SET current_representation_id = :r"
                " WHERE version_id = :v"
            ),
            {"r": representation_id, "v": version_id},
        )
        connection.execute(  # type: ignore[attr-defined]
            text("UPDATE documents SET current_version_id = :v WHERE doc_id = :doc"),
            {"v": version_id, "doc": doc_id},
        )
        mention_id = uuid4()
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO mentions (mention_id, deployment_id, surface_form,"
                " normalized_lemma, doc_id) VALUES (:m, :d, 'Acme', 'acme', :doc)"
            ),
            {"m": mention_id, "d": _DEPLOYMENT_ID, "doc": doc_id},
        )
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO resolution_decisions (decision_id, deployment_id,"
                " mention_id, entity_id, method, confidence, resolver_version)"
                " VALUES (:id, :d, :m, :e, 'T0', 1.0, 'test')"
            ),
            {"id": uuid4(), "d": _DEPLOYMENT_ID, "m": mention_id, "e": self.entity_id},
        )
        return doc_id


@pytest.fixture()
def corpus(database_engine: Engine) -> _Corpus:
    """A fresh deployment carrying the seeded corpus."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
        for table in ("mentions", "resolution_decisions"):
            connection.execute(statement=text(f"TRUNCATE TABLE {table} CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="p3-test",
            name="P3 corpus filesystem proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )
    return _Corpus(engine=database_engine)


class _Tree:
    """Read a published snapshot the way an agent's mount would."""

    def __init__(self, *, store: LocalFSObjectStore, prefix: str) -> None:
        """Bind to one snapshot's prefix."""
        self._store = store
        self._prefix = prefix

    def read(self, path: str) -> str:
        """`cat` one file."""
        return self._store.read_bytes(key=ObjectKey(f"{self._prefix}/{path}")).decode()

    def paths(self) -> set[str]:
        """Every file in the snapshot (from its manifest)."""
        import json

        manifest = json.loads(self.read("MANIFEST.json"))
        return set(manifest["files"])


def _build(corpus: _Corpus, tmp_path: Path, **kwargs: object) -> tuple[_Tree, dict]:
    """Build one snapshot and return a reader plus the build result."""
    catalog = ProjectionCatalog(engine=corpus.engine)
    store = LocalFSObjectStore(root=tmp_path / "corpusfs")
    builder = CorpusFsBuilder(
        catalog=catalog,
        snapshot_store=store,
        settings=CorpusFsSettings(**kwargs),  # type: ignore[arg-type]
    )
    result = builder.build(deployment_id=_DEPLOYMENT_ID)
    latest = catalog.latest_snapshot(deployment_id=_DEPLOYMENT_ID, plane="P3_corpusfs")
    assert latest is not None
    return _Tree(store=store, prefix=str(latest["gcs_uri"])), result


def test_the_navigation_ladder_is_walkable(corpus: _Corpus, tmp_path: Path) -> None:
    """S44: root orientation → facet → directory member table → stub, each
    step one `cat`, and the member table tells an agent what every file is
    about without opening one."""
    tree, result = _build(corpus, tmp_path)
    assert result["published"] is True

    root = tree.read("llms.txt")
    assert "documents/" in root and "entities/" in root  # the durable tiers
    assert "by-source/" in root  # a view facet

    facet = tree.read("by-source/_index.md")
    assert "by-source/upload" in facet

    directory = tree.read("by-source/upload/_index.md")
    assert "3 document(s)" in directory
    # the load-bearing property: every member's meaning is IN the index
    assert "Acme's 2023 results." in directory
    assert "How the anvil is shaped." in directory
    assert "An unfiled memo." in directory

    stub_name = next(
        path.rsplit("/", 1)[1]
        for path in tree.paths()
        if path.startswith("by-source/upload/")
        and path.endswith(".md")
        and "annual-report" in path
    )
    stub = tree.read(f"by-source/upload/{stub_name}")
    assert "canonical_path: documents/" in stub  # every view stub names Tier 1
    assert "document.md" in stub  # and points at the artifact


def test_tier_one_paths_survive_rebuilds(corpus: _Corpus, tmp_path: Path) -> None:
    """The path contract (F6): canonical document and entity leaves never
    move across rebuilds — even when the corpus grows and views reshuffle."""
    first, _ = _build(corpus, tmp_path)
    canonical = {
        path for path in first.paths() if path.startswith(("documents/", "entities/"))
    }
    assert f"documents/{corpus.docs['Annual Report']}/_index.md" in canonical
    assert any(str(corpus.entity_id) in path for path in canonical)

    with corpus.engine.begin() as connection:  # the corpus grows
        connection.execute(
            text(
                "INSERT INTO entities (entity_id, deployment_id, type,"
                " canonical_name, normalized_name)"
                " VALUES (:e, :d, 'Person', 'Wile E', 'wile e')"
            ),
            {"e": uuid4(), "d": _DEPLOYMENT_ID},
        )
    second, _ = _build(corpus, tmp_path / "again")
    assert canonical <= second.paths()  # every old Tier-1 path still there


def test_placement_hints_drive_topic_views(corpus: _Corpus, tmp_path: Path) -> None:
    """The structurer's placement hint (D39) becomes a topic view — and a
    document without one is still fully navigable."""
    tree, _ = _build(corpus, tmp_path)
    paths = tree.paths()
    assert any(
        path.startswith("by-topic/finance/annual-reports/2023/") for path in paths
    )
    assert any(path.startswith("by-topic/research/anvils/") for path in paths)
    # the unplaced memo appears in the source and time views regardless
    memo_stubs = [
        path for path in paths if "loose-memo" in path and path.endswith(".md")
    ]
    assert any(path.startswith("by-source/") for path in memo_stubs)
    assert any(path.startswith("by-time/2024/03/") for path in memo_stubs)


def test_entity_pages_carry_their_evidencing_documents(
    corpus: _Corpus, tmp_path: Path
) -> None:
    """`entities/<type>/<id>/_index.md`: profile plus the documents that
    mention it — the evidence side of understanding ↔ evidence."""
    tree, _ = _build(corpus, tmp_path)
    page = tree.read(f"entities/organization/{corpus.entity_id}/_index.md")
    assert "# Acme" in page
    assert "A manufacturer of anvils." in page
    assert "3 mention(s)" in page
    assert "annual-report" in page  # the member table lists its documents


def test_oversized_directories_shard_deterministically(
    corpus: _Corpus, tmp_path: Path
) -> None:
    """Bounded fan-out: a directory under the threshold stays flat, one
    above it shards — and a rebuild puts each document in the same shard."""
    flat, _ = _build(corpus, tmp_path / "flat")
    assert "by-source/upload/_index.md" in flat.paths()  # 3 members: no shards

    with corpus.engine.begin() as connection:  # grow past a low threshold
        for index in range(6):
            corpus._document(  # noqa: SLF001 — the fixture's own seeder
                connection,
                title=f"Bulk {index}",
                placement=None,
                summary=f"Bulk document {index}.",
            )
    sharded, _ = _build(corpus, tmp_path / "sharded", shard_threshold=4)
    shard_indexes = {
        path
        for path in sharded.paths()
        if path.startswith("by-source/upload/") and path.endswith("/_index.md")
    }
    assert len(shard_indexes) > 1  # the oversized view split
    again, _ = _build(corpus, tmp_path / "again", shard_threshold=4)
    assert sharded.paths() == again.paths()  # same document, same shard


def test_the_builder_calls_no_model(corpus: _Corpus, tmp_path: Path) -> None:
    """The projection builder is fully deterministic: two builds of an
    unchanged corpus render byte-identical trees (a directory-level LLM
    summary is a rejected alternative — that is a K page's job)."""
    first, _ = _build(corpus, tmp_path)
    second, _ = _build(corpus, tmp_path / "again")
    assert first.paths() == second.paths()
    for path in sorted(first.paths()):
        assert first.read(path) == second.read(path)
