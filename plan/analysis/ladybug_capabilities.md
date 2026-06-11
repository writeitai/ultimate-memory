# LadybugDB Capability Findings

Verified June 2026 against (a) the vendored source tree at `../../_additional_context/ladybug`
(git-ignored, ~129 MB, C++ core) and (b) docs.ladybugdb.com. Compiled to ground the L6 design
decisions in `../designs/p2_graph_design.md` and `../../decisions.md` (D7, D8, D10, D11, D13).

**Provenance caveat.** The vector, FTS, algo, and LLM extension *implementations* live in a
separate repo (`github.com/ladybugdb/extensions`, a git submodule not present in the vendored
snapshot). For those, findings come from the extension registry in the core source plus the
official docs — not from reading implementation code. Flagged per section below.

## 1. Vector search

- HNSW index extension; functions `CREATE_VECTOR_INDEX`, `QUERY_VECTOR_INDEX`,
  `DROP_VECTOR_INDEX` (registered in `src/extension/extension_entries.cpp`).
- Metrics: `cosine` (default), `l2`, `l2sq`, `dotproduct`. Vectors are `ARRAY` of
  `FLOAT`/`DOUBLE`.
- Two-layer HNSW (sampled upper layer); tunables: `mu` (upper max degree, 30), `ml` (lower max
  degree, 60), `pu` (upper sampling, 0.05), `efc` (200), `efs` (200), `cache_embeddings`.
- **Filtered vector search**: supported via projected graphs (`PROJECT_GRAPH`,
  `PROJECT_GRAPH_CYPHER`) — combine similarity with Cypher predicates.
- **Hard limitation: node-table properties only.** Relationship/edge properties cannot be
  vector-indexed (docs, explicit). → Decisive for D8 (relation embeddings live in Lance).
- Unknown (extension code not vendored): build time/memory at millions of vectors,
  incremental-insert behavior vs. rebuild-after-insert, quantization, persistence details.

## 2. Full-text search

- BM25 (Okapi) scoring; tunables `K` (1.2), `B` (0.75). Functions `CREATE_FTS_INDEX`,
  `QUERY_FTS_INDEX`, `DROP_FTS_INDEX`, `STEM`.
- Stemming: 28+ languages (English porter default; `none` to disable). Custom stopwords via
  CSV/Parquet/node table; **changing stopwords requires index rebuild**.
- Query modes: disjunctive (default) / conjunctive (`conjunctive := true`); `TOP` k.
- **Hard limitation: node tables' STRING properties only.** Rel properties cannot be
  FTS-indexed. Same consequence as §1.

## 3. Graph algorithms

- Algo extension registry (verified in `src/extension/extension_entries.cpp`):
  `PAGE_RANK`, `K_CORE_DECOMPOSITION`, `STRONGLY_CONNECTED_COMPONENTS` (+ Kosaraju variant),
  `WEAKLY_CONNECTED_COMPONENTS`.
- **No Louvain/Leiden community detection.** → D11: external pass (igraph/graspologic) over
  the rebuild's Parquet export.
- Algorithms run on **projected graphs** (filtered subgraphs) and return results as query
  output (`CALL PAGE_RANK() RETURN *`); persistence via writing results out, no in-place
  write-back observed.

## 4. Cypher / traversal (all native core, verified in source + tests)

- Variable-length patterns `*min..max`; path qualifiers `SHORTEST`, `ALL_SHORTEST`,
  `WEIGHTED_SHORTEST`, `ALL_WEIGHTED_SHORTEST`; traversal modes TRAIL (no repeated edges) /
  ACYCLIC (no repeated nodes); multi-rel-type and bidirectional patterns
  (`src/binder/expression/rel_expression.cpp`, `test/test_files/function/gds/basic.test`,
  `test/test_files/shortest_path/`).
- WHERE on relationship properties *during* variable-length traversal: not observed; filtering
  applies to nodes in-pattern and to path results after traversal.
- **No native temporal query semantics.** Temporal types exist (DATE, TIMESTAMP variants) but
  the engine has no time-travel/validity concept. **As-of traversal is achievable via
  projected graphs with rel-level predicates** on our temporal columns → D10.
- Projected graphs: `PROJECT_GRAPH` (per-table predicate map, incl. rel predicates, e.g.
  `{'knows': 'r.weight > 5'}`) and `PROJECT_GRAPH_CYPHER` (arbitrary pattern-based
  projection).

## 5. Bulk load & interop

- `COPY FROM` CSV / **Parquet** / Arrow / NPY; morsel-driven multi-threaded ingest
  (`src/processor/operator/persistent/copy_rel_batch_insert.cpp`,
  `test/test_files/copy/copy_snap_twitter_parquet.test`). → Feeds D7 (rebuild-first).
- `COPY TO` Parquet for export.
- `ATTACH DATABASE ... (type='postgres'|'duckdb'|'sqlite'|'lbug')`
  (`src/binder/bind/bind_attach_database.cpp`); scanner implementations live in the external
  extensions repo. Potential future shortcut: rebuild directly from attached Postgres instead
  of a Parquet hop.
- Iceberg/Delta extensions registered; an "icebug-disk" read-only Parquet-based table format
  exists (`docs/icebug-disk.md`) supporting `s3://`/`https://` URIs.

## 6. Concurrency & deployment (core, verified in source)

- **One READ_WRITE process XOR many READ_ONLY processes** per database. Multiple read-only
  processes on the same files are explicitly safe (`src/include/main/database.h`). Within a
  single READ_WRITE process: multiple connections, serializable ACID transactions;
  `enableMultiWrites` exists but defaults off.
- In-memory mode (no read-only variant). `maxDBSize` default 8 TB.
- Storage: data file(s) + WAL + serialized catalog; auto-checkpoint at WAL threshold (default
  16 MB) or manual `PRAGMA checkpoint` (`src/storage/checkpointer.cpp`).
- **Embedded only — no REST/HTTP server.** Bindings: C/C++, Python, Node, Rust, Java, WASM.
- No GCS/S3 connector for opening a live database from object storage (HTTPFS/icebug-disk
  cover read-only table access only) → snapshot serving = download to local disk, open
  READ_ONLY. Confirms the D7 reader model.

## 7. Misc

- Morsel-driven parallelism across cores (`docs/morsel_parallelism.md`); prepared statements
  in all bindings.
- LLM extension registered (`CREATE_EMBEDDING`) — implementation external; unused by us
  (embeddings are produced by our pipeline, stored in Lance per D8).
- Project background: fork of Kuzu after Kuzu Inc.'s acquisition by Apple ended open-source
  development (Oct 2025); actively maintained, enterprise-supported. Sources:
  ladybugdb.com, docs.ladybugdb.com, github.com/LadybugDB/ladybug, dbdb.io/db/ladybugdb,
  gdotv.com/blog/kuzu-legacy-embedded-graph-database-landscape.

## Implications for our design (summary)

| Finding | Design consequence |
|---|---|
| Vector/FTS indexes are node-only | Relation embeddings + BM25 live in Lance (D8) |
| Read-only multi-process mode | Snapshot-serving reader architecture is the intended usage (D7) |
| Fast Parquet `COPY FROM` | Rebuild-first sync is cheap at target scale (D7) |
| Projected graphs w/ rel predicates | As-of traversal without native temporal support (D10) |
| Native SHORTEST/BFS, weighted | Graph-distance reranking is native and cheap (D9) |
| No Louvain/Leiden | Community detection external, results to Postgres (D11) |
| No REST server | Graph access only via our API processes holding snapshots |
| Extensions not vendored | Build/persistence details of vector/FTS unverified — acceptable, we don't use them |
