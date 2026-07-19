# P2 engine spike battery (WP-4.1, question #20a, D44)

**Question.** Six verify-on-the-deployed-engine spikes before building the rebuild
worker: (a) UUID-as-node-PK, (b) ATTACH vs Parquet transport, (c) merge-redirect
recursion + validation gate, (d) inline as-of path performance + parameter binding,
(e) invalidated-edge retention cost, (f) NULL-`TIMESTAMP` through Parquet.

**Method.** Executable: `src/tests/spikes/test_p2_engine_spikes.py` runs every spike
against the packaged engine (`ladybug` 0.18.2 from PyPI, embedded — the battery
prints the version it ran under, so every verdict is attributable) and real
PostgreSQL. CI runs the battery at small scale as a **capability canary**: every
verdict is asserted in a form that FLIPS if a future engine version changes the
behavior — the reproductions heal themselves inside the test, so they cannot pass
for an unrelated reason. The numbers below are from a local run at
`UGM_SPIKE_SCALE=200000` (Apple-silicon laptop; shapes, not SLAs — D22).

## Verdicts

| Spike | Verdict |
|---|---|
| (a) UUID PK | **Confirmed on the deployed build.** Native `UUID` works as node PK, rel endpoints, and parameters; string Parquet columns cast into `UUID` node keys and REL endpoints on `COPY`. No STRING fallback needed. |
| (b) transport | **ATTACH-direct is dead on capability grounds — two independent blockers, each reproduced and healed inside the test:** (1) **pg_partman installed in schema `public`** — exactly our deployment layout — breaks ATTACH itself (`Binder Error: Schema with name "pg_catalog" not found`); (2) even without partman, an **enum-typed column** breaks table replication (`Binder exception: Unsupported duckdb type: ENUM(…)`), and our tables are enum-heavy by design. Either alone kills ATTACH-direct; both must flip before the transport decision deserves a re-measure. The committed Parquet baseline (D44) is confirmed before throughput even enters. *(An earlier draft blamed the enum TYPE alone — that bisect was polluted by a failed `DROP DATABASE` in a multi-statement psql call; the in-test reproduction now isolates each mechanism on a scratch database it creates and destroys itself.)* |
| (b2) Parquet throughput | Measured in the PRODUCTION shape — full column set, `COPY` into a UUID-keyed node table AND a rel table with UUID endpoints, exported via the worker's materialize-once survivor strategy (see the findings below). **200k nodes + 200k edges: PG export 1.8 s, Parquet write 0.7 s, COPY 0.97 s** — linear, extrapolating to minutes at 10⁷–10⁸. **Honest caveat:** the `MENTIONED_IN` aggregation at 10⁷–10⁸ mention rows is *not* covered here — it is the one genuinely scale-bound query, and WP-4.2's rebuild worker must measure it on the first real corpus (D22) before the schedule is tuned. |
| (c) merge recursion + gate | `v_graph_survivor` **terminates on a planted merge cycle** (the depth-64 guard caps the walk) and the validation-gate query names every endpoint whose survivor is still merged — the planted 2-cycle is caught loudly, the legitimate a→b→c chain resolves cleanly. The gate SQL is ready for WP-4.2's abort-before-snapshot step. |
| (d) inline as-of | **Parameter binding works inside the inline `(r, n \| WHERE …)` form** (the upstream-untested case) and the predicate filters DURING traversal — asserted discriminatingly: the temporal boundary sits at edge 15 of a 30-hop bound, so an engine that ignored the predicate would return 30, not 15. `SHORTEST` composes with the filter and refuses to cross the boundary. Per-edge evaluator cost under a real frontier: a hub with **200k edges, every predicate evaluated, half filtered — 0.087 s** (~0.4 µs/edge, linear). One engine limit **asserted as its own canary**: the recursive upper bound is capped at 30 hops (`1..40` is a binder error) — irrelevant for the design's 1–3-hop neighborhoods, but the retrieval primitive must clamp its bound. |
| (e) retention | Invalidated edges **project by default** (D69) — asserted exactly: every seeded relation (every fifth invalidated, deterministically) reaches `v_graph_relates`, retained and live counts match the seed to the row, and the current-belief default derives inline (`invalidated_at IS NULL`). The export carries the full production column set, so the recorded Parquet size and COPY time reflect the real payload. **No evidence justifies replacing D69's unbounded projection with a finite hot-snapshot horizon** at foreseeable scale; revisit only if snapshot size ever dominates rebuild time. |
| (f) NULL timestamps | **NULL `TIMESTAMP` survives** Parquet → `COPY`, and the `IS NULL OR …` guards keep SQL three-valued semantics inside Cypher filters — the as-of and current-belief defaults are safe. |

## Two export-shape findings the battery caught (fixes landed / bound)

1. **The shipped `v_graph_survivor` was quadratic when materialized.** Its survivor
   column was a correlated `(SELECT … ORDER BY depth DESC LIMIT 1)` per output row
   over the un-indexed recursive CTE — invisible to `count(*)` (dead-column
   elimination) but O(n²) for a real export: 0.75 s → 5.8 s → 109 s across
   2k → 8k → 32k. **Fixed in migration `p4_01_0011`**: the
   `DISTINCT ON (entity_id) … ORDER BY depth DESC` form has identical terminal-row
   semantics and materializes in 0.03 s at 32k (three orders of magnitude).
2. **Even the fixed view is join-shape hostile when referenced twice.** A naive
   `SELECT … FROM v_graph_relates` re-plans the survivor resolution per join side
   and nested-loops at scale (>30 min at 200k). **The rebuild worker's bound export
   strategy (WP-4.2): materialize the survivor map ONCE into an indexed temp table
   per rebuild, then join relations/mentions against it** — the 1.8 s figure above
   uses exactly that shape (verified 0.05 s for the join itself at 32k). The
   projection views remain the semantic contract; the worker owns the execution
   shape.

Both are exactly what a spike battery exists to catch: the semantics were right,
the plan shapes were production incidents waiting for the first real corpus.

## Query-shape findings from WP-4.3 (recorded here, canaries in the battery)

Building the `graph` primitive surfaced two further engine constraints that
prior knowledge would get wrong — both bind how every Cypher we write must
be shaped:

3. **A NULL parameter cannot participate in a typed comparison.** Binding
   `$valid_at = None` and writing `($valid_at IS NULL OR r.valid_from <= $valid_at)`
   fails with `Binder exception: Type Mismatch: Cannot compare types TIMESTAMP
   and BOOL` — the engine infers an unbound/None parameter's type as BOOL. The
   "pass NULL and let the guard short-circuit" idiom (correct in SQL) is
   therefore unavailable. **Rule: compose temporal predicates conditionally in
   the caller and bind only the parameters the query actually references.**
4. **A plain variable-length match ENUMERATES paths — use `SHORTEST` for
   reachability.** `MATCH (a)-[r:RELATES* 1..30]-(b)` on a cyclic graph
   never returns: the engine enumerates every distinct path, which explodes
   combinatorially even on a seven-node toy corpus (observed: 100 % CPU,
   no result). `SHORTEST` yields ONE result per reachable node in BFS time
   — which is exactly what a distance-ranked neighborhood is. **Rule:
   `SHORTEST` is load-bearing for neighborhood queries, not an
   optimization**; a plain variable-length match is only safe with a tiny
   bound on an acyclic shape.
5. **List comprehensions over path elements are unsupported.**
   `[x IN nodes(p) | x.name]` fails with `Variable x is not in scope`.
   **Rule: return `nodes(p)` / `rels(p)` directly** (they yield full property
   maps) or use `properties(rels(p), 'predicate')`; read the maps client-side.

## Transport decision (confirmed)

**Postgres `v_graph_*` views → Parquet export → multi-threaded `COPY` into a fresh
graph database → validate → snapshot → reader hot-swap.** ATTACH-direct cannot
connect to the production schema at all on the deployed engine (spike b: partman
layout kills ATTACH, enum columns kill replication). The Parquet hop also gives the
rebuild a free durable artifact (the export doubles as the community-detection
input, p2 §7) and a natural validation point between export and load.

## Carried into WP-4.2

- The validation gate: abort the snapshot when any `v_graph_survivor` row resolves
  to a still-merged survivor (spike c's query), or when a `COPY REL` endpoint is
  missing from the emitted node set.
- The export executes via the materialize-once survivor map (finding 2 above) —
  never by selecting the edge views naively.
- Clamp retrieval's variable-length bounds to the engine's max of 30 hops (the cap
  is asserted; a version that lifts it flips the canary).
- Measure the `MENTIONED_IN` aggregation on the first real corpus before tuning the
  rebuild schedule — the one scale-bound query this battery does not cover.
- The ATTACH reproductions stay in CI; both blockers must heal before
  reconsidering the transport, and then re-measure at 10⁷ first.
