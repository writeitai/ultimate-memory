"""WP-4.1: the D44 spike battery against the DEPLOYED LadybugDB engine.

Question #20a's six spikes, executable. Each runs CI-sized for correctness;
the perf-shaped ones scale with ``UGM_SPIKE_SCALE`` (rows) for the recorded
local measurements in `plan/analysis/p2_spike_battery.md`. The battery
doubles as a capability canary: if a future engine version changes a
verdict (say, ATTACH starts working against enum-bearing schemas), a test
flips and tells us to revisit the transport decision.
"""

from collections.abc import Iterator
from datetime import datetime
from datetime import UTC
from pathlib import Path
import time
from typing import cast
from uuid import UUID
from uuid import uuid4

from alembic import command
from alembic.config import Config
import ladybug
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import Field
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine.settings import load_database_settings

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("f2000000-0000-0000-0000-000000000001")


class _SpikeSettings(BaseSettings):
    """The battery's scale knob (rows); bump locally for the recorded run."""

    model_config = SettingsConfigDict(env_prefix="UGM_SPIKE_")

    scale: int = Field(default=2000, ge=100)


_SCALE = _SpikeSettings().scale


def _result(raw: object) -> ladybug.QueryResult:
    """Narrow the driver's `QueryResult | list[QueryResult]` union."""
    assert isinstance(raw, ladybug.QueryResult)
    return raw


def _next_row(raw: object) -> list[object]:
    """The next row of a single-statement result, as a plain list."""
    return cast("list[object]", _result(raw).get_next())


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL integration engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real PostgreSQL spike runs")
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
def graph_connection(tmp_path: Path) -> ladybug.Connection:
    """A fresh embedded LadybugDB per spike."""
    return ladybug.Connection(ladybug.Database(str(tmp_path / "graph")))


@pytest.fixture()
def seeded_deployment(database_engine: Engine) -> Engine:
    """A fresh deployment with the base registry (works_for etc.)."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="p2-spikes",
            name="P2 spike battery",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )
    return database_engine


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


def test_spike_a_uuid_pk_smoke(graph_connection: ladybug.Connection) -> None:
    """(a) UUID as node PK and rel endpoint on the deployed build — no
    STRING fallback needed."""
    conn = graph_connection
    conn.execute("CREATE NODE TABLE Entity(id UUID, name STRING, PRIMARY KEY (id))")
    conn.execute("CREATE REL TABLE RELATES(FROM Entity TO Entity, predicate STRING)")
    left, right = uuid4(), uuid4()
    conn.execute(
        "CREATE (:Entity {id: $l, name: 'a'}), (:Entity {id: $r, name: 'b'})",
        {"l": left, "r": right},
    )
    conn.execute(
        "MATCH (x:Entity {id: $l}), (y:Entity {id: $r})"
        " CREATE (x)-[:RELATES {predicate: 'works_for'}]->(y)",
        {"l": left, "r": right},
    )
    result = _next_row(
        conn.execute("MATCH (x:Entity)-[r:RELATES]->(y:Entity) RETURN x.id, y.id")
    )
    assert result == [left, right]  # native UUIDs round-trip both ends


def test_spike_f_null_timestamp_parquet_roundtrip(
    graph_connection: ladybug.Connection, tmp_path: Path
) -> None:
    """(f) NULL TIMESTAMP survives Parquet → COPY, and the `IS NULL OR …`
    as-of guards keep SQL 3-valued semantics inside Cypher filters."""
    table = pa.table(
        {
            "id": pa.array(["open-window", "unknown-start", "closed"]),
            "valid_from": pa.array(
                [datetime(2024, 1, 1), None, datetime(2020, 1, 1)],
                type=pa.timestamp("us"),
            ),
            "valid_until": pa.array(
                [None, None, datetime(2021, 1, 1)], type=pa.timestamp("us")
            ),
        }
    )
    path = tmp_path / "windows.parquet"
    pq.write_table(table, str(path))
    conn = graph_connection
    conn.execute(
        "CREATE NODE TABLE W(id STRING, valid_from TIMESTAMP,"
        " valid_until TIMESTAMP, PRIMARY KEY (id))"
    )
    conn.execute(f"COPY W FROM '{path}'")
    asof = _result(
        conn.execute(
            "MATCH (w:W) WHERE (w.valid_from IS NULL OR w.valid_from <= $t)"
            " AND (w.valid_until IS NULL OR w.valid_until > $t)"
            " RETURN w.id ORDER BY w.id",
            {"t": datetime(2024, 6, 1)},
        )
    )
    visible = []
    while asof.has_next():
        visible.append(_next_row(asof)[0])
    # the closed window is out; NULL bounds behave as open/unknown
    assert visible == ["open-window", "unknown-start"]


def test_spike_d_inline_asof_predicate(graph_connection: ladybug.Connection) -> None:
    """(d) the inline recursive-pattern predicate: parameter binding works
    inside the `(r, n | WHERE …)` form, it filters DURING traversal, and it
    composes with SHORTEST. Timed at UGM_SPIKE_SCALE for the report."""
    conn = graph_connection
    conn.execute("CREATE NODE TABLE E(eid INT64, PRIMARY KEY (eid))")
    conn.execute("CREATE REL TABLE L(FROM E TO E, since TIMESTAMP, until TIMESTAMP)")
    chain = max(_SCALE, 100)
    conn.execute("UNWIND range(0, $n) AS i CREATE (:E {eid: i})", {"n": chain})
    # a long chain whose second half only exists after 2025
    conn.execute(
        "MATCH (a:E), (b:E) WHERE b.eid = a.eid + 1 AND a.eid < $half"
        " CREATE (a)-[:L {since: TIMESTAMP('2020-01-01'), until: NULL}]->(b)",
        {"half": chain // 2},
    )
    conn.execute(
        "MATCH (a:E), (b:E) WHERE b.eid = a.eid + 1 AND a.eid >= $half"
        " CREATE (a)-[:L {since: TIMESTAMP('2025-01-01'), until: NULL}]->(b)",
        {"half": chain // 2},
    )
    started = time.perf_counter()
    result = _result(
        conn.execute(
            "MATCH (a:E {eid: 0})-[e:L* 1..30"
            " (r, n | WHERE r.since <= $asof"
            " AND (r.until IS NULL OR r.until > $asof))]->(b:E)"
            " RETURN count(*)",
            {"asof": datetime(2022, 6, 1, tzinfo=UTC).replace(tzinfo=None)},
        )
    )
    reachable = _next_row(result)[0]
    elapsed = time.perf_counter() - started
    assert reachable == 30  # the post-2025 half is invisible as-of 2022
    # NB: the engine caps the recursive upper bound at 30 (a 1..40 pattern
    # is a binder error) — a real limit for deep multi-hop as-of queries,
    # recorded in the report
    shortest = _next_row(
        conn.execute(
            "MATCH p = (a:E {eid: 0})-[e:L* SHORTEST 1..30"
            " (r, n | WHERE r.since <= $asof)]->(b:E {eid: 20}) RETURN length(p)",
            {"asof": datetime(2022, 6, 1).replace(tzinfo=None)},
        )
    )[0]
    assert shortest == 20  # SHORTEST composes with the inline form
    print(f"\nSPIKE-D chain={chain} asof_30hop_s={elapsed:.4f}")  # noqa: T201 — recorded in the report


def test_spike_b_attach_capability_gate(seeded_deployment: Engine) -> None:
    """(b) ATTACH-direct against the production schema is NOT viable on the
    deployed engine: the postgres scanner fails to attach any database
    containing a custom enum type (`Schema with name "pg_catalog" not
    found`), and our schema is enum-heavy. This test is the capability
    canary — if a future version fixes it, the expected failure stops
    failing and the transport decision deserves a re-measure. Until then
    the committed Parquet baseline (D44) is confirmed on capability
    grounds, before throughput even enters."""
    settings = load_database_settings()
    url = settings.sqlalchemy_url()
    # crude DSN derivation from the SQLAlchemy URL for the scanner
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    dsn = (
        f"host={parsed.host} port={parsed.port} dbname={parsed.database}"
        f" user={parsed.username} password={parsed.password}"
    )
    conn = ladybug.Connection(ladybug.Database(":memory:"))
    conn.execute("INSTALL postgres")
    conn.execute("LOAD postgres")
    with pytest.raises(RuntimeError, match="pg_catalog"):
        conn.execute(f"ATTACH '{dsn}' AS pg (dbtype postgres)")


def test_spike_b2_parquet_transport_throughput(
    seeded_deployment: Engine, graph_connection: ladybug.Connection, tmp_path: Path
) -> None:
    """(b) the committed transport: Postgres view → Parquet → COPY. Timed at
    UGM_SPIKE_SCALE; correctness = every exported row lands."""
    nodes = _SCALE
    ids = [uuid4() for _ in range(nodes)]
    with seeded_deployment.begin() as connection:
        for index, entity_id in enumerate(ids):
            _seed_entity(connection, entity_id=entity_id, name=f"person-{index}")
    started = time.perf_counter()
    with seeded_deployment.connect() as connection:
        rows = connection.execute(
            text("SELECT id, type, name FROM v_graph_entities")
        ).all()
    export_s = time.perf_counter() - started
    table = pa.table(
        {
            "id": pa.array([str(row[0]) for row in rows]),
            "type": pa.array([row[1] for row in rows]),
            "name": pa.array([row[2] for row in rows]),
        }
    )
    path = tmp_path / "entities.parquet"
    pq.write_table(table, str(path))
    conn = graph_connection
    conn.execute(
        "CREATE NODE TABLE Entity(id STRING, type STRING, name STRING,"
        " PRIMARY KEY (id))"
    )
    started = time.perf_counter()
    conn.execute(f"COPY Entity FROM '{path}'")
    copy_s = time.perf_counter() - started
    loaded = _next_row(conn.execute("MATCH (e:Entity) RETURN count(*)"))[0]
    assert loaded == nodes
    print(  # noqa: T201 — recorded in the report
        f"\nSPIKE-B2 rows={nodes} pg_export_s={export_s:.3f} copy_s={copy_s:.3f}"
    )


def test_spike_c_merge_recursion_and_validation_gate(seeded_deployment: Engine) -> None:
    """(c) v_graph_survivor terminates on a planted merge CYCLE (the depth
    guard), and the WP-4.2 validation-gate query catches every endpoint
    that fails to resolve to exactly one active survivor — the clean chain
    passes, the cycle members are named."""
    a, b, c = uuid4(), uuid4(), uuid4()
    x, y = uuid4(), uuid4()
    with seeded_deployment.begin() as connection:
        _seed_entity(connection, entity_id=c, name="survivor")
        _seed_entity(
            connection, entity_id=b, name="mid", status="merged", merged_into=c
        )
        _seed_entity(
            connection, entity_id=a, name="old", status="merged", merged_into=b
        )
        # a planted 2-cycle: schema does not enforce acyclicity (design note)
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
    with seeded_deployment.connect() as connection:
        survivors = {
            row[0]: row[1]
            for row in connection.execute(
                text("SELECT entity_id, survivor FROM v_graph_survivor")
            ).all()
        }  # terminates: the depth guard caps the cycle walk
        assert survivors[a] == c
        assert survivors[b] == c
        # the validation gate (rebuild aborts the snapshot on any row):
        offenders = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT s.entity_id FROM v_graph_survivor s"
                    " JOIN entities e ON e.entity_id = s.survivor"
                    " WHERE e.merged_into IS NOT NULL"
                )
            ).all()
        }
    assert x in offenders and y in offenders  # the cycle is caught, loudly
    assert a not in offenders and b not in offenders  # the chain passes


def test_spike_e_invalidated_edge_retention(
    seeded_deployment: Engine, graph_connection: ladybug.Connection, tmp_path: Path
) -> None:
    """(e) D69's default: invalidated edges are RETAINED in the projection
    (transaction-time as-of needs them). Measures the retention overhead at
    UGM_SPIKE_SCALE for the horizon decision — recorded, not gated."""
    people = max(_SCALE // 10, 50)
    ids = [uuid4() for _ in range(people)]
    with seeded_deployment.begin() as connection:
        for index, entity_id in enumerate(ids):
            _seed_entity(connection, entity_id=entity_id, name=f"node-{index}")
        connection.execute(
            text(
                "INSERT INTO relations (relation_id, deployment_id,"
                " subject_entity_id, predicate, object_entity_id,"
                " normalizer_version, invalidated_at)"
                " SELECT gen_random_uuid(), :d, s.entity_id, 'works_for',"
                " o.entity_id, 'spike',"
                " CASE WHEN random() < 0.4 THEN now() END"
                " FROM (SELECT entity_id, row_number() OVER () AS rn"
                "       FROM entities) s"
                " JOIN (SELECT entity_id, row_number() OVER () AS rn"
                "       FROM entities) o ON o.rn = (s.rn % :n) + 1"
            ),
            {"d": _DEPLOYMENT_ID, "n": people},
        )
    with seeded_deployment.connect() as connection:
        rows = connection.execute(
            text(
                'SELECT "from", "to", relation_id, invalidated_at FROM v_graph_relates'
            )
        ).all()
    retained = sum(1 for row in rows if row[3] is not None)
    assert retained > 0  # invalidated edges project by default (D69)
    table = pa.table(
        {
            "from": pa.array([str(row[0]) for row in rows]),
            "to": pa.array([str(row[1]) for row in rows]),
            "relation_id": pa.array([str(row[2]) for row in rows]),
            "invalidated_at": pa.array(
                [row[3].replace(tzinfo=None) if row[3] else None for row in rows],
                type=pa.timestamp("us"),
            ),
        }
    )
    path = tmp_path / "relates.parquet"
    pq.write_table(table, str(path))
    conn = graph_connection
    conn.execute("CREATE NODE TABLE Entity(id STRING, PRIMARY KEY (id))")
    conn.execute(
        "CREATE REL TABLE RELATES(FROM Entity TO Entity, relation_id STRING,"
        " invalidated_at TIMESTAMP)"
    )
    node_table = pa.table({"id": pa.array([str(e) for e in ids])})
    node_path = tmp_path / "nodes.parquet"
    pq.write_table(node_table, str(node_path))
    conn.execute(f"COPY Entity FROM '{node_path}'")
    started = time.perf_counter()
    conn.execute(f"COPY RELATES FROM '{path}'")
    copy_s = time.perf_counter() - started
    live = _next_row(
        conn.execute(
            "MATCH ()-[r:RELATES]->() WHERE r.invalidated_at IS NULL RETURN count(*)"
        )
    )[0]
    total = cast(
        "int", _next_row(conn.execute("MATCH ()-[r:RELATES]->() RETURN count(*)"))[0]
    )
    assert total == len(rows)
    assert live == total - retained  # current-belief default derives inline
    parquet_kb = path.stat().st_size / 1024
    print(  # noqa: T201 — recorded in the report
        f"\nSPIKE-E edges={total} invalidated={retained}"
        f" copy_s={copy_s:.3f} parquet_kb={parquet_kb:.0f}"
    )
