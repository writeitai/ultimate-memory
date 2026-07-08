# LadybugDB Query Semantics — Traversal-Time Filtering, SHORTEST, and the Query Rulebook

An investigation into **when LadybugDB evaluates predicates on variable-length paths** —
during traversal, or after a path is found — and the binding conclusions for how every query
in this system must be written. Triggered by a suspected correctness bug in the multi-hop
as-of example (`p2_graph_design.md` §4): if the temporal filter runs *after* `SHORTEST` picks
a path, an as-of query can silently return nothing although a valid (longer) path existed at
that time. Verified against the vendored source (`../../_additional_context/ladybug`), its
test suite, and docs.ladybugdb.com. **Verdict up front: the engine is sound — it has exactly
the right mechanism — but the two query forms look interchangeable and are not, and our own
docs used the wrong one.** The rulebook in §4 is the part future agents should read before
writing any LadybugDB query.

## 1. The question

Cypher offers two ways to constrain a variable-length path:

```cypher
-- Form A: OUTER path filter (looks natural, reads like standard Cypher)
MATCH p = (a)-[rs:RELATES* SHORTEST 1..3]-(b)
WHERE all(r IN rels(p) WHERE r.ingested_at <= $as_of ...)

-- Form B: INLINE recursive predicate (LadybugDB-specific syntax)
MATCH p = (a)-[rs:RELATES* SHORTEST 1..3 (r, _ | WHERE r.ingested_at <= $as_of ...)]-(b)
```

If Form A is evaluated *after* matching, then `SHORTEST` searches the **unfiltered** graph,
finds today's shortest path, the filter rejects it — and the query returns **nothing**, even
though a longer path satisfying the predicate existed. That is not "slow", it is **wrong**:
an as-of query that silently under-reports connectivity.

## 2. Evidence (source, tests, docs)

| # | Fact | Evidence |
|---|---|---|
| 1 | The inline form `(r, n \| WHERE …)` is first-class: bound into dedicated `RecursiveInfo.relPredicate` / `nodePredicate` slots | `src/include/binder/expression/rel_expression.h:20–41`; `src/binder/bind/bind_graph_pattern.cpp:401–434` |
| 2 | The **rel predicate is evaluated per edge during neighbor scanning** — inside the graph iterator the recursive-join (GDS) algorithms consume. A failing edge never enters the BFS frontier | `src/graph/on_disk_graph.cpp:116` (evaluator compiled), `:308` (`currentIter->next(relPredicateEvaluator.get(), …)`) |
| 3 | The **node predicate becomes a pre-computed semi-mask** — traversal only passes through satisfying nodes | `src/planner/plan/plan_node_semi_mask.cpp`; `src/planner/plan/append_extend.cpp:115–117` |
| 4 | **No optimizer rule pushes an outer `WHERE all(r IN rels(p) …)` into the traversal** — the only writers of `relPredicate`/`nodePredicate` are the inline syntax; `filter_push_down_optimizer.cpp` has no recursive/path handling. The outer form plans as a plain Filter over matched paths | `src/optimizer/filter_push_down_optimizer.cpp` (absence); repo-wide grep for `relPredicate` |
| 5 | The inline form **composes with SHORTEST** and reshapes the search: with `(r, n \| WHERE n.ID <> 0)`, the 3→1 query returns the *detour* `[3,2,1]` — a shortest-satisfying path was *found*, not a shorter unfiltered path found-then-rejected | `test/test_files/shortest_path/all_shortest_path_tinysnb.test:28` |
| 6 | Docs constraint: inline predicates must be **node-only or rel-only conjuncts** ("n.age > 45 AND r.since < 2022" ok; "n.age > 45 OR r.since < 2022" not supported) | docs.ladybugdb.com, MATCH page |
| 7 | `PROJECT_GRAPH` / `PROJECT_GRAPH_CYPHER` are standalone CALL table functions consumed by GDS algorithms via a graph entry; **no path into `MATCH` planning** (re-confirms D44) | `src/include/function/table/standalone_call_function.h:15,21`; `src/function/gds/gds.cpp:191` |
| 8 | **No upstream test exercises a parameter (`$x`) inside an inline recursive predicate** — binding should be ordinary expression binding, but it is unverified | grep over `test/test_files/` (absence) |

## 3. Findings

1. **Form B (inline) filters during traversal.** `SHORTEST`/`ALL SHORTEST` compute shortest
   paths **in the filtered subgraph** — the correct as-of semantics (evidence 2, 3, 5).
2. **Form A (outer) filters after matching.** With any `SHORTEST` variant this is a
   **correctness bug** (silently missing/empty results); with plain `*1..k` enumeration it is
   semantically correct but does wasted work — every path is materialized then discarded
   (evidence 4).
3. **Our docs had it backwards in the example.** `p2_graph_design.md` §4 said "inline
   filtering is the working mechanism" but the code block showed Form A with `SHORTEST`; the
   translation SYNTHESIS (§7 spike 4) claimed inline filtering "can't push the predicate into
   traversal" — true only of Form A. Both corrected (see §5).
4. **The engine is not the problem.** LadybugDB implements traversal-time edge predicates at
   the storage-iterator level plus node semi-masks, composing with all path modes — this is
   *exactly* the mechanism a bi-temporal as-of graph needs, and it is tested and documented.
   The hazard is that the standard-Cypher-looking form silently means something else. That is
   an LLM/agent trap (the same failure pattern as LanceDB filter-vs-post-filter): **both forms
   parse, both run, one is wrong** — nothing errors.

## 4. THE RULEBOOK — how to write LadybugDB queries in this system

**Read this before writing any query against the P2 graph. If a query you are about to write
violates a rule here, the query is wrong even if it runs and returns plausible results.**

**R1 — Single-hop: plain `WHERE` is fine.** No recursion → no trap:

```cypher
MATCH (a:Entity {id: $id})-[r:RELATES]-(b:Entity)
WHERE r.invalidated_at IS NULL AND (r.valid_until IS NULL OR r.valid_until > $now)
RETURN a, r, b;
```

**R2 — Any filtered variable-length pattern: put the predicate INSIDE the brackets.** The
inline recursive predicate `(r, _ | WHERE …)` is the only form evaluated during traversal:

```cypher
-- ✅ CORRECT: as-of shortest path (filter reshapes the search)
MATCH p = (a:Entity {id:$id})
    -[rs:RELATES* SHORTEST 1..3 (r, _ | WHERE
          r.ingested_at <= $as_of
      AND (r.invalidated_at IS NULL OR r.invalidated_at > $as_of)
      AND (r.valid_from  IS NULL OR r.valid_from  <= $as_of)
      AND (r.valid_until IS NULL OR r.valid_until >  $as_of))]-
    (b:Entity)
RETURN p;
```

**R3 — NEVER combine `SHORTEST`/`ALL SHORTEST`/`WEIGHTED_SHORTEST` with an outer
`WHERE all(r IN rels(p) …)`.**

```cypher
-- ❌ WRONG: parses, runs, silently returns wrong/empty results.
-- SHORTEST searches the UNFILTERED graph; the filter then rejects the found path;
-- a longer path valid at $as_of is never considered.
MATCH p = (a)-[rs:RELATES* SHORTEST 1..3]-(b)
WHERE all(r IN rels(p) WHERE r.ingested_at <= $as_of ...)
```

For plain (non-shortest) `*1..k` the outer form is legal-but-wasteful; still prefer R2.

**R4 — Inline predicate constraints.** Only **rel-only or node-only conjuncts**: `(r, n |
WHERE r.x = 1 AND n.y = 2)` is fine (each conjunct touches one variable); a single predicate
mixing both (`r.x = 1 OR n.y = 2`) is rejected. All our temporal filters are rel-only
conjunctive — they fit. Use `_` for the unused variable: `(r, _ | WHERE …)`.

**R5 — Parameters inside inline predicates are unverified upstream** (evidence 8). Before the
first as-of implementation ships, add a one-line test that `$as_of` binds inside `(r, _ |
WHERE r.ingested_at <= $as_of)`; the fallback is literalizing the timestamp into the query
string (already the documented pattern for `PROJECT_GRAPH` predicate strings).

**R6 — Projected graphs are inputs to algorithms, never to `MATCH`.**
`PROJECT_GRAPH[_CYPHER]` feeds GDS calls (PageRank, components, path *functions*); you cannot
`MATCH`-traverse one, `PROJECT_GRAPH_CYPHER` takes exactly `(STRING, STRING)` (no parameter
map — literalize), and there is no `MATCH … IN GRAPH` syntax. For heavy/repeated as-of
analytics, materialize a persistent graph at rebuild (`CREATE GRAPH` + load the filtered edge
set, then `USE GRAPH`).

**R7 — Liveness is derived, never stored.** The graph carries no `status` column (D6 —
deliberately not projected). Current belief = `r.invalidated_at IS NULL AND (r.valid_until IS
NULL OR r.valid_until > $now)`. Do not invent or look for a status/active property.

**R8 — No semantic search inside the graph.** Vector (HNSW) and FTS (BM25) indexes exist for
**node-table properties only** — relationship properties can never be vector/FTS-indexed.
Semantic entry to relations happens in **Lance, keyed by `relation_id`** (p2 §6); the graph's
job starts when you already hold IDs. Never design a query that "searches edges by meaning"
in-graph.

**R9 — Know which algorithms exist.** Native: PageRank, K-Core, WCC/SCC, and Cypher-level
`SHORTEST`/`ALL SHORTEST`/`WEIGHTED_SHORTEST` with TRAIL/ACYCLIC modes. **Not shipped:
Louvain/Leiden** — community detection is an external pass (igraph/graspologic) over the
Parquet export.

**R10 — Concurrency: one READ_WRITE process XOR many READ_ONLY.** Readers always open
snapshots `READ_ONLY`; the writer builds a fresh database and publishes by pointer swap
(p2 §5). Never open a serving copy for write.

**R11 — Bulk-load order: all node tables before any rel table.** `COPY` of a rel table
resolves endpoints against node PKs at copy time — a missing endpoint throws and aborts the
load.

**R12 — LadybugDB is not Neo4j.** No `shortestPath()` function syntax, no APOC, a different
projected-graph model, and the inline recursive predicate `(r, n | WHERE …)` has no Neo4j
equivalent. Do not port Neo4j idioms from memory — check the grammar
(`src/antlr4/Cypher.g4`) or the test corpus (`test/test_files/`) in the vendored source when
in doubt; the tests are the most reliable statement of what actually works.

**R13 — Traverse undirected by default.** `RELATES` edges are stored subject→object, but
relevance rarely follows assertion direction; retrieval recipes use `-[r:RELATES]-`
(undirected) unless the predicate's semantics genuinely require direction.

## 5. Corrections this investigation forced

- `p2_graph_design.md` §4 — multi-hop as-of example rewritten to Form B (inline); explicit
  warning added against Form A + `SHORTEST`; §5b stale rows fixed ("as-of during traversal
  via projected graphs" → inline predicates); parameter-binding check added to §9.
- `ladybug_translation_research/SYNTHESIS.md` §4(a) example rewritten to Form B; §7 spike 4's
  "can't push the predicate into traversal" corrected (true only of the outer form).
- The performance spike is re-aimed: measure traversal-time predicate evaluation (Form B) at
  corpus scale — per-edge evaluator cost, not "post-filter everything".

## 6. What stays open

1. **Parameter binding in inline predicates** (R5) — one-line test at implementation time.
2. **Form-B evaluation cost at scale** — the evaluator runs per scanned edge; measure on a
   corpus-sized graph (expected fine — it replaces materialize-then-discard — but measure).
3. This document covers **query semantics**; capability inventory lives in
   `ladybug_capabilities.md` (partially superseded, see SYNTHESIS §4 note) and
   `p2_graph_design.md` §5b (current).

## References

Vendored source: `_additional_context/ladybug` (binder: `bind_graph_pattern.cpp`; execution:
`on_disk_graph.cpp`, `plan_node_semi_mask.cpp`, `append_extend.cpp`; tests:
`test/test_files/shortest_path/`). Docs: docs.ladybugdb.com (MATCH / recursive
relationships). Adjacent: `p2_graph_design.md` §4–§6, `ladybug_translation_research/SYNTHESIS.md`
§4/§7, `ladybug_capabilities.md`. Decisions: D10 (refined), D44.
