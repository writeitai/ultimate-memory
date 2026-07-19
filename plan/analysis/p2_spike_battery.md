# P2 engine spike battery (WP-4.1, question #20a, D44)

**Question.** Six verify-on-the-deployed-engine spikes before building the rebuild
worker: (a) UUID-as-node-PK, (b) ATTACH vs Parquet transport, (c) merge-redirect
recursion + validation gate, (d) inline as-of path performance + parameter binding,
(e) invalidated-edge retention cost, (f) NULL-`TIMESTAMP` through Parquet.

**Method.** Executable: `src/tests/spikes/test_p2_engine_spikes.py` runs every spike
against the packaged engine (`ladybug` 0.18.2 from PyPI, embedded) and real
PostgreSQL. CI runs the battery at small scale as a **capability canary** — if a
future engine version changes a verdict, a test flips. The numbers below are from a
local run at `UGM_SPIKE_SCALE=200000` (Apple-silicon laptop; shapes, not SLAs — D22).

## Verdicts

| Spike | Verdict |
|---|---|
| (a) UUID PK | **Confirmed on the deployed build.** Native `UUID` works as node PK and round-trips through rel endpoints and parameters. No STRING fallback needed. |
| (b) transport | **ATTACH-direct is dead on capability grounds, not throughput.** The postgres scanner fails to ATTACH any database containing a **custom enum type** (`Binder Error: Schema with name "pg_catalog" not found`) — bisected to exactly that trigger (bare DBs, partitioned tables, and pg_partman all attach fine; one `CREATE TYPE … AS ENUM` breaks it). Our schema is enum-heavy by design. The committed Parquet baseline (D44) is confirmed before throughput even enters the argument; the battery keeps an expected-failure test as the canary for future versions. |
| (b2) Parquet throughput | PG view export 200k rows ≈ **0.36 s**; `COPY` into the graph ≈ **0.44 s** (~450k rows/s per stage, single-threaded client). Extrapolated: 10⁷ rows ≈ tens of seconds, 10⁸ ≈ minutes — comfortably inside a scheduled-rebuild budget; `COPY FROM` Parquet is multi-threaded server-side, so this is an upper bound. |
| (c) merge recursion + gate | `v_graph_survivor` **terminates on a planted merge cycle** (the depth-64 guard caps the walk) and the validation-gate query names every endpoint whose survivor is still merged — the planted 2-cycle is caught loudly, the legitimate a→b→c chain resolves cleanly. The gate SQL is ready for WP-4.2's abort-before-snapshot step. |
| (d) inline as-of | **Parameter binding works inside the inline `(r, n \| WHERE …)` form** (the upstream-untested case), the predicate filters during traversal, and it composes with `SHORTEST`. A 30-hop as-of traversal over a 200k-node chain: **0.16 s**. One new engine limit recorded: the recursive upper bound is **capped at 30 hops** (`1..40` is a binder error) — irrelevant for the design's 1–3-hop neighborhood queries, but a hard wall for pathological path queries; the retrieval primitive should clamp its bound. |
| (e) retention | Invalidated edges **project by default** (D69 confirmed in the view) and the current-belief default derives inline (`invalidated_at IS NULL`). At 40 % invalidated, 20k edges: copy 0.08 s, 2.2 MB Parquet — retention cost is linear and small. **No evidence justifies replacing D69's unbounded projection with a finite hot-snapshot horizon** at foreseeable scale; revisit only if snapshot size ever dominates rebuild time (measure per D22, don't pre-commit). |
| (f) NULL timestamps | **NULL `TIMESTAMP` survives** Parquet → `COPY`, and the `IS NULL OR …` guards keep SQL three-valued semantics inside Cypher filters — the as-of and current-belief defaults are safe. |

## Transport decision (confirmed)

**Postgres `v_graph_*` views → Parquet export → multi-threaded `COPY` into a fresh
graph database → validate → snapshot → reader hot-swap.** ATTACH-direct is not
merely slower — it cannot connect to the production schema at all on the deployed
engine (spike b). The Parquet hop also gives the rebuild a free durable artifact
(the export doubles as the community-detection input, p2 §7) and a natural
validation point between export and load.

## Carried into WP-4.2

- The validation gate: abort the snapshot when any `v_graph_survivor` row resolves
  to a still-merged survivor (spike c's query), or when a `COPY REL` endpoint is
  missing from the emitted node set.
- Clamp retrieval's variable-length bounds to the engine's max of 30 hops.
- The ATTACH canary test stays in CI; if it flips, re-run spike b2 at 10⁷ before
  reconsidering the transport.
