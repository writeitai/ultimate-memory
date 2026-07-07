# LanceDB Indexing & Maintenance — Nothing Is Automatic (Analysis + Rulebook)

How LanceDB OSS actually behaves around indexes — **no index exists unless you create it, no
index covers new data unless you maintain it, and everything keeps working without them** —
and the binding rules for how this system's P1 code must be written. This is the LanceDB
counterpart of `ladybug_query_semantics.md`, and it documents the same *class* of trap: the
API accepts the naive usage, returns correct results, and the failure is silent — here it
surfaces as latency and storage-operations **cost**, not wrong answers, which makes it the
kind of bug that ships. LLM-written LanceDB integrations get this wrong with remarkable
reliability, because the naive code *works* on dev-sized data — the rulebook in §3 exists so
future agents don't re-learn it in production. Grounded in the official documentation
(docs.lancedb.com — pages cited inline); cost/latency magnitudes in §2 are illustrative
arithmetic from the documented access patterns.

## 1. Three facts everything else follows from (official docs)

1. **OSS creates and updates no index on its own.** "You will have to create the vector index
   manually, by calling `table.create_index()`, and updating the index as new data arrives"
   (`indexing/vector-index`). Scalar and FTS indexes likewise. (LanceDB *Enterprise*
   auto-indexes on write — `indexing/reindexing` — which is exactly why examples and LLM
   priors trained on mixed docs get OSS behavior wrong.)
2. **New rows are unindexed until `optimize()` runs.** Until then "LanceDB will combine
   results from the existing index with exhaustive/flat search on the new data", and "the
   more data that you add without reindexing, the impact on latency (due to exhaustive
   search) can be noticeable" (`indexing/reindexing`). `optimize()` does three jobs at once:
   compacts fragments, prunes old versions, and "adds newly-ingested data to existing vector,
   scalar, and FTS indexes".
3. **Every write commits a fragment and a version.** "Each call commits a new version and a
   new fragment, so a per-row loop pays that per-call overhead at every row"; "many small
   fragments build up as you write, slowing down queries that have to scan across more files"
   (`performance`). Versions accumulate storage until pruned (`cleanup_older_than`, default
   retention ~7 days).

Corollary: **a LanceDB deployment is not "a table plus queries" — it is a table, its full
index set, and a maintenance loop.** Omit the third and the system degrades without ever
erroring.

## 2. The failure archetypes — how this goes wrong in the field

Each of these is a pattern repeatedly observed in real LanceDB deployments, and each is the
*default* output of an LLM asked to "set up a LanceDB table":

**A. The zero-index table.** Generated code calls `create_table()` and `search()` — and no
`create_index()` anywhere. Everything works in development: at a few thousand rows,
brute-force kNN is fast *and exact*. In production the same code is an exhaustive flat scan
of every vector on every query. The arithmetic that makes this a cost incident and not just a
latency one: on an object-store-backed table (GCS/S3), a flat scan reads **every data
fragment as an object GET** — a table that has accreted ~20k small fragments costs ~20k
storage reads *per query*; at even modest query rates that is hundreds of dollars a day in
storage operations, before anyone notices latency. A ~200k-row table of 4096-dim float32
vectors is ~3 GB of vector data scanned per query — tens of seconds warm. Adding the proper
index set turns this into milliseconds: **three to four orders of magnitude**, from one
setup step the happy path never forced.

**B. The missing scalar indexes.** The vector index exists, but the `.where()` filter columns
have none — and "without a scalar index, LanceDB evaluates the `where(...)` predicate on
every row" (`performance`). Filters *look* declarative, so generated code assumes
database-like behavior; LanceDB gives it only if the index exists. The docs are unambiguous:
"**index every column used for filtering or join operations**." Join keys matter doubly:
"`merge_insert()` is significantly slower than `add()`" and needs scalar indexes on its join
columns to avoid a full scan per batch.

**C. The unbounded unindexed tail.** Indexes were created once — at initial build or a
rebuild — while steady-state writes keep appending. Every appended row lands in the unindexed
tail (fact 2) and every small write adds a fragment (fact 3), so ANN/FTS queries flat-scan a
growing remainder on top of the index, forever. This is the *gradual* variant of archetype A:
no error, no step change, just a latency and cost curve that climbs until someone asks why.
Incremental-write paths (a projector, an inline-writing pipeline — exactly our P1 shape) hit
this by construction unless maintenance runs on a trigger.

**D. Index creation on a path that may never run.** Building indexes as a side effect of a
happy-path worker step ("after the batch completes, ensure indexes") means one failed or
never-completed run leaves the table index-less — silently, since queries still work
(archetype A). Index-ensuring must be an **explicit, idempotent operation on its own
trigger** (deploy-time step + schedule), with verification (`index_stats()` →
`num_unindexed_rows ≈ 0`), never only a tail-call of data processing.

**E. The frozen minimum-rows gate.** Vector index training needs data ("at least a few
thousand rows" — `indexing/vector-index`), so setup code reasonably gates index creation on
row count. The bug is checking the gate **once**: a table that crosses the threshold *after*
that check never gets its index — archetype A with a delay fuse. The gate must be
re-evaluated by the maintenance loop, not only at creation.

**F. Query anti-patterns.** Loading a whole table (`to_pandas()`) to implement keyword
search or ID lookup; omitting `select()`/`limit()` (docs: "always pass both"); expecting
post-filtering to behave like pre-filtering (postfilter applies *after* top-k, so results can
silently come back fewer-than-limit); not knowing BM25 is token-based — a term appearing only
as a substring of a compound token is invisible to FTS (mitigations: the FM-index scalar type
for `contains()` substring lookups, or a bounded substring-scan union when needed).

**G. The retry amplifier.** A slow-because-unindexed query sitting behind an aggressive task
queue (default retry counts, high concurrency) turns a performance bug into a cost storm —
hundreds of retries × thousands of object reads each. Performance hygiene and bounded retries
(our orchestration design's queue rules) protect *each other*.

## 3. THE RULEBOOK — how P1/Lance code must be written

**Read before writing any LanceDB table, ingestion path, or query. The theme: if you didn't
create it, it doesn't exist; if you didn't schedule it, it doesn't happen.**

**R1 — A table setup is not finished until its full index set exists.** Vector index on every
embedding column that will be ANN-searched; **a scalar index on every column that ever
appears in a `.where()` or as a `merge_insert` join key**; FTS index on every BM25-searched
text column. Review rule for generated code: diff the set of filtered columns against the set
of indexed columns — it must be empty.

**R2 — Choose scalar index types by cardinality** (`indexing/scalar-index`): `BTREE` for
high-cardinality columns (ids, timestamps, names); `BITMAP` for low-cardinality (< ~1,000
distinct: status, kind, type, boolean flags); `LABEL_LIST` for list columns queried with
`array_contains_*`; FM-index for `contains()` substring lookups. Nested struct fields index
via dotted paths; UUIDs index as `FixedSizeBinary(16)`.

**R3 — Choose the vector index by size and dimension** (`indexing/vector-index`,
`performance`): under ~100K vectors brute force is acceptable (but see R5 — plan for
crossing); `IVF_PQ` as the general default (`num_partitions ≈ rows // 4096`,
`num_sub_vectors ≈ dim // 8`); `IVF_RQ` for high-dimensional vectors; `IVF_HNSW_SQ` where
recall/latency justify the memory. **Same distance metric at index build and at query.**

**R4 — The maintenance loop is a first-class worker, not an afterthought.** Run
`table.optimize(cleanup_older_than=…)` on a **dual trigger**: unindexed rows ≥ N *or* small
fragments ≥ M — both, because frequent small `merge_insert`s accrete fragments faster than
rows. One `optimize()` folds new rows into **all** index kinds, compacts fragments, and
prunes versions. Fresh tables must be a no-op (don't rebuild the world on every cycle).

**R5 — Ensure-indexes is an explicit, idempotent, independently-triggered operation.**
Deploy-time step plus schedule; re-evaluates the min-rows gate (R3/archetype E) so tables
that grew into indexability get their index; verified by `index_stats()` with an alert when
`num_unindexed_rows` drifts. Never *only* a side effect of a data-processing run (archetype
D).

**R6 — Write in batches, never per row.** Each `add()` is a version + fragment (fact 3);
accumulate and write bounded batches; use iterator ingestion for streams. Prefer `add()` to
`merge_insert()` where append semantics suffice; when merging, index the join keys first.

**R7 — Query hygiene.** Always `select()` + `limit()`; `prefilter=True` is the default posture
(postfilter may return fewer than `limit` — acceptable only when explicitly chosen); tune
`nprobes` / `refine_factor` (quantized) or `ef` (HNSW) against a recall target; never
`to_pandas()` a table to filter in Python; when something is slow, `analyze_plan()` before
guessing.

**R8 — Know BM25's blindness.** Token-based FTS cannot match substrings of compound tokens.
Where substring matching matters, add an FM-index and use `contains()`, or run a bounded
substring-scan union alongside FTS. Skip `with_position=True` unless phrase queries are
needed (index cost).

**R9 — Version and storage hygiene.** MVCC versions accumulate storage until pruned;
`optimize(cleanup_older_than=…)` with a deliberate retention window (days, not forever;
compaction temporarily *increases* space before old versions delete). On object storage,
watch **storage-operation counts** as a first-class metric — an unindexed scan on GCS/S3 is a
billing event per fragment, and cost regression often precedes visible latency regression
(archetype A).

**R10 — Cap retries around Lance queries.** Anything that queries Lance behind a task queue
inherits archetype G: bound retry counts and concurrency (the orchestration design's queue
rules apply), so a performance regression stays a performance regression.

**R11 — Dev ≠ prod, in both directions.** Brute force is *exact*; ANN is *approximate* — the
moment the index appears, results can change subtly (recall < 100%). Test retrieval quality
with the index in place and sized realistically, not against the exact-but-doomed indexless
table.

## 4. What this binds for P1 (our design)

- **P1's inline-write pattern is archetype C by construction** (E-plane workers write
  chunks/claims/labels as they land — `overall_design.md` §4). The maintenance worker the
  designs already name (`p1_batch_rebuild` + compaction, `plan/analysis/workers.md` §6.3;
  "Lance compaction schedule", `overall_design.md` §8) is therefore **load-bearing, not
  hygiene**: it owns the R4 optimize loop with the dual trigger, the R5 ensure-indexes +
  `index_stats()` verification, and the R9 retention window. Its absence is a slow-motion
  production incident, not a missed nicety.
- **The P1 table designs (e1/P1 design, planned) must enumerate the index set per table** as
  part of the schema, not leave it to implementation: every scalar filter column
  (deployment/tenant scoping, `relation_id`/`subject_id`/`object_id`, `predicate`,
  the validity timestamps, `doc_id`, `evidence_count`) with its R2 type, the vector index
  params per embedding column, and the FTS columns. "The schema is done when the index set is
  written down" is the review bar (R1) — this is where generated code fails by default.
- **D9's zero-LLM query path depends on this**: the scalar-filtered hybrid search that makes
  recipes fast (`p2_graph_design.md` §6: "scalar columns give filtered hybrid search") is
  only real if those scalar columns are indexed and the unindexed tail is bounded.

## 5. Sources

Official documentation (docs.lancedb.com): `indexing/reindexing` (OSS vs Enterprise, the
unindexed tail, `optimize()`'s three jobs), `indexing/vector-index` (types, parameters,
training minimums, manual-update statement), `indexing/scalar-index` (BTREE/BITMAP/
LABEL_LIST/FM-index, update-on-write requirement), `performance` (fragments/versions,
batching, `merge_insert` costs, "index every column used for filtering", query hygiene,
`analyze_plan`/`index_stats`). Magnitudes in §2 are illustrative arithmetic from these
documented access patterns. Companion rulebook for the graph engine:
`ladybug_query_semantics.md`.
