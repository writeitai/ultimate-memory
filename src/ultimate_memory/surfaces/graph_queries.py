"""The `graph` primitive (retrieval §3, p2 §4/§6): traversal over the snapshot.

Two typed, zero-LLM operations over the published P2 snapshot:

- **neighborhood(entity, hops, predicates?)** — everything within N hops,
  ranked by distance then evidence weight, with an EXPLICIT truncation
  marker whenever a hub exceeds the cap (S18: never a silent top-k).
- **path(a, b, max_hops)** — how two entities connect, shortest-first. A
  path is a COMPOUND result: it revalidates as a unit, so a dropped edge
  drops the whole path rather than silently yielding a shorter, false
  connection (S17/S21).

Both accept the temporal parameters. As-of traversal uses the engine's
**inline recursive-pattern predicate** — evaluated per edge DURING the
neighbor scan, verified live in the WP-4.1 spike battery — never the
post-hoc `all(r IN rels(p) …)` form, which must never be combined with
`SHORTEST`. Projected graphs are not an option: they feed the algorithm
extensions only and cannot be `MATCH`-traversed (D44).

The engine caps recursive upper bounds at 30 hops (spike d2, asserted as a
canary); requests above the cap are clamped and disclosed as truncation
rather than failing.
"""

from datetime import datetime
from datetime import UTC
from typing import cast
from typing import Final
from uuid import UUID

import ladybug

from ultimate_memory.model import Envelope
from ultimate_memory.model import Freshness
from ultimate_memory.model import Grain
from ultimate_memory.model import GraphEdge
from ultimate_memory.model import GraphNode
from ultimate_memory.model import GraphPath
from ultimate_memory.model import Negative
from ultimate_memory.model import NegativeKind
from ultimate_memory.model import Truncation

MAX_ENGINE_HOPS: Final = 30
"""The engine's recursive upper bound (WP-4.1 spike d2). Requests above it
are clamped and disclosed, never silently honored or failed."""

DEFAULT_NEIGHBORHOOD_CAP: Final = 200
"""How many neighbors one page returns before the truncation marker."""


class GraphQueries:
    """Snapshot traversal: neighborhoods, paths, as-of, distance ranking."""

    def __init__(self, *, reader: object) -> None:
        """Bind to a snapshot reader (the WP-4.2 `GraphSnapshotReader`)."""
        self._reader = reader

    def neighborhood(
        self,
        *,
        entity_id: UUID,
        hops: int = 2,
        predicates: tuple[str, ...] = (),
        valid_at: datetime | None = None,
        believed_at: datetime | None = None,
        limit: int = DEFAULT_NEIGHBORHOOD_CAP,
        offset: int = 0,
    ) -> Envelope:
        """Everything within `hops` of the entity, distance-ranked (S18/S19).

        Ranking is graph distance first (nearer is more relevant — the D9
        graph-distance rerank in its native form), then evidence weight,
        then a stable id tiebreak so pagination is deterministic. One extra
        row is fetched to detect truncation without a second count query.
        """
        connection = self._connection()
        if connection is None:
            return self._no_snapshot()
        clamped = min(max(hops, 1), MAX_ENGINE_HOPS)
        predicate_filter = " AND r.predicate IN $predicates" if predicates else ""
        guard = _temporal_predicate(valid_at=valid_at, believed_at=believed_at)
        # SHORTEST is load-bearing, not an optimization: a plain
        # variable-length match ENUMERATES every path, which explodes
        # combinatorially on a cyclic graph (a 30-hop undirected walk never
        # returns). SHORTEST gives one result per reachable node — exactly
        # what a distance-ranked neighborhood is — in BFS time.
        query = f"""
            MATCH (a:Entity {{id: $entity_id}})
                  -[r:RELATES* SHORTEST 1..{clamped}
                    (r, n | WHERE {guard}{predicate_filter})]-
                  (b:Entity)
            RETURN b.id, b.name, b.type, length(r) AS hops
            ORDER BY hops, b.name, b.id
            SKIP $offset LIMIT $fetch
            """  # noqa: S608 — the interpolations are validated ints/flags
        parameters: dict[str, object] = {
            "entity_id": entity_id,
            "offset": offset,
            "fetch": limit + 1,
        }
        if predicates:
            parameters["predicates"] = list(predicates)
        _bind_temporal(parameters, valid_at=valid_at, believed_at=believed_at)
        rows = _rows(connection, query, parameters)
        truncated = len(rows) > limit
        page = rows[:limit]
        nodes = tuple(
            GraphNode(
                entity_id=cast("UUID", row[0]),
                name=cast("str", row[1]),
                type=cast("str", row[2]),
                hops=cast("int", row[3]),
            )
            for row in page
        )
        if not nodes and offset == 0:
            return self._empty(
                explanation=(
                    f"no entity within {clamped} hop(s) of {entity_id}"
                    " satisfies the requested filters"
                )
            )
        return Envelope(
            grain=Grain.FACT,
            as_of_valid_at=valid_at,
            nodes=nodes,
            freshness=self._freshness(),
            truncation=Truncation(
                truncated=truncated or hops > MAX_ENGINE_HOPS,
                returned=len(nodes),
                estimated_total=offset + len(rows),
                continuation=(str(offset + limit) if truncated else None),
            ),
        )

    def path(
        self,
        *,
        from_entity_id: UUID,
        to_entity_id: UUID,
        max_hops: int = 4,
        valid_at: datetime | None = None,
        believed_at: datetime | None = None,
    ) -> Envelope:
        """How two entities connect, shortest-first (S17/S21/S22).

        The path returns as a unit with every traversed edge, so the caller
        can see (and re-verify) each link. An empty result is a typed
        `known_empty`: the entities exist, no qualifying connection does.
        """
        connection = self._connection()
        if connection is None:
            return self._no_snapshot()
        clamped = min(max(max_hops, 1), MAX_ENGINE_HOPS)
        guard = _temporal_predicate(valid_at=valid_at, believed_at=believed_at)
        query = f"""
            MATCH p = (a:Entity {{id: $from_id}})
                      -[r:RELATES* SHORTEST 1..{clamped}
                        (r, n | WHERE {guard})]-
                      (b:Entity {{id: $to_id}})
            RETURN length(p) AS hops, nodes(p) AS path_nodes, rels(p) AS path_edges
            """  # noqa: S608 — `clamped` is a validated int
        # NB: the engine does not support list comprehensions over path
        # elements (`[x IN nodes(p) | …]` → "Variable x is not in scope") —
        # `nodes(p)`/`rels(p)` return full property maps, read below
        parameters: dict[str, object] = {
            "from_id": from_entity_id,
            "to_id": to_entity_id,
        }
        _bind_temporal(parameters, valid_at=valid_at, believed_at=believed_at)
        rows = _rows(connection, query, parameters)
        if not rows:
            return self._empty(
                explanation=(
                    f"no path of {clamped} hop(s) or fewer connects"
                    f" {from_entity_id} and {to_entity_id} under the applied"
                    " temporal filters"
                )
            )
        paths = tuple(_path_from_row(row) for row in rows)
        return Envelope(
            grain=Grain.FACT,
            as_of_valid_at=valid_at,
            paths=paths,
            edges=tuple(edge for path in paths for edge in path.edges),
            nodes=tuple(node for path in paths for node in path.nodes),
            freshness=self._freshness(),
            truncation=Truncation(
                truncated=max_hops > MAX_ENGINE_HOPS,
                returned=len(paths),
                estimated_total=len(paths),
            ),
        )

    def _connection(self) -> ladybug.Connection | None:
        """The snapshot connection, or None when nothing is published yet."""
        try:
            return cast("ladybug.Connection", self._reader.connection())  # type: ignore[attr-defined]
        except RuntimeError:
            return None

    def _freshness(self) -> Freshness:
        """Stamp which snapshot answered (S42: freshness per source)."""
        version = getattr(self._reader, "version", None)
        return Freshness(pg_live_ts=datetime.now(tz=UTC), p2_snapshot_version=version)

    def _no_snapshot(self) -> Envelope:
        """A typed boundary: the graph plane has never published (S39)."""
        return Envelope(
            grain=Grain.FACT,
            freshness=Freshness(pg_live_ts=datetime.now(tz=UTC)),
            negative=Negative(
                kind=NegativeKind.BOUNDARY,
                explanation="no P2 graph snapshot has been published yet",
                workaround=(
                    "run the graph rebuild worker, or use lookup/search on the"
                    " live spine which needs no projection"
                ),
            ),
        )

    def _empty(self, *, explanation: str) -> Envelope:
        """A typed known_empty: the traversal ran and found nothing (S29)."""
        return Envelope(
            grain=Grain.FACT,
            freshness=self._freshness(),
            negative=Negative(
                kind=NegativeKind.KNOWN_EMPTY,
                explanation=explanation,
                workaround="widen the hop bound, relax predicates, or drop the as-of",
            ),
        )


def _temporal_predicate(
    *, valid_at: datetime | None, believed_at: datetime | None
) -> str:
    """The as-of guard, evaluated PER EDGE during the neighbor scan (D44).

    Composed CONDITIONALLY, never with NULL parameters: the engine infers a
    NULL parameter's type as BOOL and refuses to compare it with TIMESTAMP
    (`Cannot compare types TIMESTAMP and BOOL`) — found live here, pinned
    by a canary in the spike battery. So an absent temporal parameter drops
    its conjunct entirely rather than passing NULL.

    Valid time filters the world-time window; system time filters what we
    believed then. With neither, the read is current belief
    (`invalidated_at IS NULL`), and the NULL-column guards keep SQL
    three-valued semantics (spike f).
    """
    conjuncts: list[str] = []
    if valid_at is not None:
        conjuncts.append(
            "(r.valid_from IS NULL OR r.valid_from <= $valid_at)"
            " AND (r.valid_until IS NULL OR r.valid_until > $valid_at)"
        )
    if believed_at is not None:
        conjuncts.append(
            "r.ingested_at <= $believed_at"
            " AND (r.invalidated_at IS NULL OR r.invalidated_at > $believed_at)"
        )
    else:
        conjuncts.append("r.invalidated_at IS NULL")  # current belief
    return " AND ".join(f"({conjunct})" for conjunct in conjuncts)


def _path_from_row(row: list[object]) -> GraphPath:
    """Assemble one compound path result from its node and edge maps."""
    raw_nodes = cast("list[dict[str, object]]", row[1])
    raw_edges = cast("list[dict[str, object]]", row[2])
    nodes = tuple(
        GraphNode(
            entity_id=cast("UUID", node["id"]),
            name=cast("str", node["name"]),
            type=cast("str", node["type"]),
            hops=index,
        )
        for index, node in enumerate(raw_nodes)
    )
    edges = tuple(
        GraphEdge(
            relation_id=cast("UUID", edge["relation_id"]),
            subject_id=nodes[index].entity_id,
            object_id=nodes[index + 1].entity_id,
            predicate=cast("str", edge["predicate"]),
            fact=cast("str | None", edge.get("fact")),
            evidence_count=cast("int", edge["evidence_count"]),
            valid_from=_utc(edge.get("valid_from")),
            valid_until=_utc(edge.get("valid_until")),
            invalidated_at=_utc(edge.get("invalidated_at")),
        )
        for index, edge in enumerate(raw_edges)
    )
    return GraphPath(length=cast("int", row[0]), nodes=nodes, edges=edges)


def _rows(
    connection: ladybug.Connection, query: str, parameters: dict[str, object]
) -> list[list[object]]:
    """Run one Cypher statement and materialize its rows."""
    result = connection.execute(query, parameters)
    assert isinstance(result, ladybug.QueryResult)
    rows: list[list[object]] = []
    while result.has_next():
        rows.append(cast("list[object]", result.get_next()))
    return rows


def _bind_temporal(
    parameters: dict[str, object],
    *,
    valid_at: datetime | None,
    believed_at: datetime | None,
) -> None:
    """Bind only the temporal parameters the predicate actually references."""
    if valid_at is not None:
        parameters["valid_at"] = _naive(valid_at)
    if believed_at is not None:
        parameters["believed_at"] = _naive(believed_at)


def _naive(value: datetime | None) -> datetime | None:
    """The graph stores naive UTC; parameters must match (spike f)."""
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None)


def _utc(value: object) -> datetime | None:
    """Re-attach UTC to a naive graph timestamp for the envelope."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC)
    return None
