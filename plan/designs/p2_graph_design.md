# P2 Graph Layer — Design (formerly L6)

Drill-down of the P2 (graph) requirements from `../requirements/requirements_v3.md`. Inspirations: Graphiti/Zep
(bi-temporal edges, episode provenance, communities) and the supersession-architecture review
(graph restricted to entity adjacency, single source of truth for validity, no replicated
invalidation state).

For a worked explanation of the claims / relations / evidence model and bi-temporality, see
`../analysis/concepts.md`.

## 1. Role: a derived projection, never an authority

The single most important decision. The graph is a **read-optimized projection of facts that
already live in Postgres**. It makes no decisions, holds no state of its own, and can be
deleted and rebuilt at any time without data loss.

Concretely:

- **Validity is decided upstream.** Supersession, contradiction, and entity merges all happen
  in the E2 pipeline and are recorded in Postgres. The graph mirrors the outcome. (Graphiti
  runs LLM-driven edge invalidation at graph-write time; we deliberately don't — that judgment
  already happened at E2. The graph writer is dumb and deterministic.)
- **No embeddings in the graph.** Semantic entry points come from LanceDB/Postgres. Storing
  vectors in two places is how stores drift apart (documented Mem0 failure mode). The graph's
  job starts when you already have an entity ID.
- **No supersession blocking in the graph.** `(entity_id, predicate)` blocking runs on Postgres
  scalar indexes — transactional, cheap, and available even when the graph is mid-rebuild.

What the graph IS for:

| Query | Example |
|---|---|
| Neighborhood expansion | "everything we know about entity X" — typed, time-filtered adjacency |
| Relationship lookup | "how are X and Y connected?" (1–2 hops) |
| As-of reconstruction | "what did we believe about X on 2025-03-01?" |
| Structural navigation | citation chains, person↔org affiliations, doc↔entity mentions |
| graph analytics | communities, PageRank, paths — feeding K1 topic hints (§7) |

## 2. Ontology and schema

LadybugDB is schema-full (typed node/rel tables), which conflicts with "evolve the ontology
over time" if every predicate becomes its own table. Resolution: **structural relations get
dedicated tables; semantic relations share one generic table with `predicate` as a property.**
Promoting a hot predicate to its own table later is a cheap migration (graph is rebuildable).

```cypher
// Nodes
CREATE NODE TABLE Entity(
  id UUID PRIMARY KEY,          // canonical ID from the Postgres entity registry
  name STRING,
  type STRING,                  // enum from registry: person | organization | paper_concept |
                                //   project | place | product | event | other
  summary STRING,               // short registry-maintained blurb (optional)
  created_at TIMESTAMP
);

CREATE NODE TABLE Document(
  id UUID PRIMARY KEY,          // E0 input ID
  title STRING,
  source_uri STRING,
  published_at DATE
);

// Semantic edges — projections of RELATIONS (normalized facts), not of claims directly
CREATE REL TABLE RELATES(
  FROM Entity TO Entity,
  predicate STRING,             // normalized vocabulary, see §3
  relation_id UUID,             // provenance — hydrate relation + evidence claims from Postgres
  fact STRING,                  // short human-readable label, NOT the full claim text
  evidence_count INT64,         // number of supporting claims (cheap salience signal)
  valid_from TIMESTAMP,         // ┐
  valid_until TIMESTAMP,        // │ bi-temporal, inherited verbatim
  ingested_at TIMESTAMP,        // │ from the relation record
  invalidated_at TIMESTAMP,     // ┘
  confidence DOUBLE
);

// Structural edges — from E0/E1 metadata, not claims
CREATE REL TABLE MENTIONED_IN(FROM Entity TO Document, mention_count INT64, first_seen TIMESTAMP);
CREATE REL TABLE CITES(FROM Document TO Document, context STRING);
```

### Relations vs. claims — distinct concepts, distinct records

Claims (E2) and graph edges are NOT the same thing, and the mapping is many-to-many:

- a **claim** is a verifiable natural-language assertion as made by a source — possibly n-ary,
  qualified, an opinion or prediction; many claims flatten to no triplet at all
- a **relation** is a normalized binary fact `(subject_entity, predicate, object_entity)` —
  its identity is the fact itself, independent of who asserted it
- one claim can yield several relations; one relation can be evidenced by many claims

So Postgres holds a first-class **`facts`** table (the unified verdict layer — D43) with its
bi-temporal fields, plus `fact_evidence(fact_id, claim_id, stance: supports | contradicts)`.
**Relations** — facts whose object is another entity — are the `object_kind='entity'` subset,
exposed as a `relations` view `(subject_id, predicate, object_id, …)`; those are exactly the rows
the graph projects. (Literal-object facts live in the same table but never become graph rows — see
§5.) A **relation-normalization step** in the E2 pipeline (after claim extraction + entity
resolution) maps eligible claims onto facts against the governed-relationship registry:

- `(s, p, o)` already exists with compatible validity → claim added as **evidence**
  (confidence up, no new fact — ten papers asserting the same affiliation = one edge)
- conflict detected → supersession/contradiction adjudication runs **at the relation level**
  ("Alice left Acme" supersedes the fact, not one sentence in one paper)

Rules:

- **Only canonical entities enter the graph.** Alias resolution and `same_as` merging happen in
  the Postgres registry before projection. The graph never contains two nodes for one entity.
- **Edges project relations, not claims.** Edge count scales with distinct facts, not corpus
  redundancy. Attribute claims ("X was founded in 1998") and non-normalizable claims stay
  E2-only — retrievable via Lance/Postgres. This keeps the graph lean (rough sizing at 1M
  docs: ~50M claims → far fewer distinct relations → graph of a few GB, comfortably embedded).
- **Contradictions project too**: an unresolved contradiction between relations becomes two
  live edges with a shared `contradiction_group` property, so retrieval can surface both sides.
- This matches Graphiti's actual model: their edges are facts with episode lists as
  provenance — episodes ≈ our claims, edge ≈ our relation.

## 3. Predicate vocabulary governance

Free-text predicates explode ("works_at" / "employed_by" / "is employee of") and silently break
both entity-keyed blocking and graph queries. So:

- A **predicate registry table in Postgres**: `predicate, description, synonyms[], status`.
- E2 extraction is constrained to the registry vocabulary, with an `other:<freetext>` escape
  hatch.
- A periodic job reviews frequent `other:` values and promotes them (or maps them to existing
  predicates). The ontology evolves by governance, not by accretion.
- Seed vocabulary: `works_at, member_of, authored, cites, located_in, part_of, collaborates_with,
  founded, advises, related_to` — extend per K2 domains.

## 4. Bi-temporality and as-of queries

Edges carry the same four timestamps as E2 claims (Graphiti/Zep model):

- `valid_from` / `valid_until` — when the fact was true in the world
- `ingested_at` / `invalidated_at` — when the system learned it / learned it was superseded

Default retrieval filter (current beliefs):

```cypher
MATCH (a:Entity {id: $id})-[r:RELATES]-(b:Entity)
WHERE r.invalidated_at IS NULL
  AND (r.valid_until IS NULL OR r.valid_until > $now)
RETURN a, r, b;
```

Time-travel (`as_of` on both axes — "what was true at T as we knew it at T"):

```cypher
WHERE r.ingested_at <= $as_of
  AND (r.invalidated_at IS NULL OR r.invalidated_at > $as_of)
  AND r.valid_from <= $as_of
  AND (r.valid_until IS NULL OR r.valid_until > $as_of)
```

Supersession never deletes an edge — adjudication closes the **relation's** window in
Postgres, the projection mirrors it into the edge's `valid_until`/`invalidated_at`. The
evidence claims keep their own bi-temporal record (when asserted / when ingested) — two
clocks, two purposes: claims record what sources said and when; relations record what the
system currently holds true. History stays queryable forever.

## 5. Sync architecture: rebuild-first, snapshots for readers

LadybugDB's concurrency model (verified): **one READ_WRITE process XOR many READ_ONLY
processes** on the same database files. Don't fight this — design around it.

### The writer: periodic full rebuild

Instead of incremental event application, the P2 worker **rebuilds the whole graph from
Postgres on every cycle**. The projection reads **directly** from Postgres via LadybugDB's
`ATTACH … (dbtype postgres)` extension — no Parquet staging hop:

1. `ATTACH` the Postgres database read-only, then `COPY <node/rel table> FROM SQL_QUERY('pg',
   '…')` once per LadybugDB table. Each query is the projection's contract with the E-plane
   (D43):
   - **Nodes** are canonical **entities**.
   - **Edges** are facts where **`object_kind = 'entity'`** — the relational subset of the
     unified `facts` verdict layer (D18/D43). Literal facts (balances, revenues, headcounts)
     are deliberately **not** projected as graph rows; they never become nodes or edges. They
     reach the graph only as scalar **node properties** when a reader needs them (HNSW/FTS and
     properties are node-only in LadybugDB), sourced from the same `facts` table.
   - The query carries the validity fields (`valid_from`/`valid_until`), evidence counts,
     mentions and citations, and applies two mechanical casts LadybugDB requires: Postgres
     `timestamptz` → naive UTC `timestamp` (`… AT TIME ZONE 'UTC'`, because LadybugDB has no
     `timestamptz`), and UUID PKs → `STRING` (UUID is not a valid node-key type). As-of query
     parameters must use the same UTC-naive convention.
2. LadybugDB streams the rows straight into the fresh database (its bulk path; tens of
   millions of rows load in minutes). `ATTACH`-direct removes the export/serialize/parse round
   trip and keeps a single source of truth for the row set: the SQL query *is* the schema map.
3. Checkpoint, validate (row counts per table vs. Postgres counts), upload to GCS as an
   **immutable versioned snapshot**: `gs://…/graph/snapshots/<timestamp>/`, then update a
   `latest` pointer.

Why rebuild-first instead of incremental:

- **Zero drift by construction.** The "rebuildable from Postgres" requirement isn't a dusty
  disaster-recovery script — it's exercised every cycle. Consistency checking, merge
  handling, and out-of-order event headaches all disappear.
- **Entity merges become trivial.** A merge that re-points thousands of edges is a nightmare
  incrementally and a no-op in a rebuild.
- **It fits the trigger model.** P2 is a debounced aggregate layer anyway (requirements v2) —
  nobody needs second-level graph freshness; the cadence (start: hourly) is the freshness SLA.
- **Cheap at our scale.** A few GB rebuilt in minutes on one Cloud Run job. Only when rebuild
  time outgrows the cadence does incremental application pay for itself — and the watermark
  machinery can then be added without changing readers at all.

### The readers: read-only snapshot copies

The retrieval API/CLI never touch the writer's files. Each API instance:

- downloads the `latest` snapshot to local disk at startup,
- opens it `READ_ONLY` (multiple processes allowed — this is exactly the supported mode),
- polls the `latest` pointer and hot-swaps to a new snapshot when it appears.

This gives horizontally scalable reads, zero lock contention, cross-cloud friendliness
(Hetzner Postgres never serves graph queries), and free point-in-time debugging — old
snapshots ARE the graph as-of their timestamp.

### Alternative (a deliberate non-goal): incremental between rebuilds

Rebuild-first is the design. Incremental application is documented here only as the alternative
we would adopt **if** sub-hour graph freshness ever became a hard requirement — it is *not* part
of the current design. The shape, for the record: keep the periodic full rebuild as the anchor,
and between rebuilds apply claim events from a Postgres outbox (`graph_events`, watermark stored
in Postgres) to a working copy, publishing micro-snapshots; the rebuild still bounds drift to
one cycle. At the target scale, rebuild-first is sufficient (§5).

## 5b. Verified LadybugDB capabilities (source tree + official docs)

Surveyed from the vendored source (`../../_additional_context/ladybug`) and docs.ladybugdb.com:

| Capability | Status |
|---|---|
| Vector index | HNSW extension (cosine/l2/l2sq/dotproduct), **node-table properties ONLY** — rel/edge properties cannot be vector-indexed |
| Filtered vector search | yes, via projected graphs (`PROJECT_GRAPH`, `PROJECT_GRAPH_CYPHER`) |
| FTS | BM25 + stemming (28 languages) extension, **node-table STRING properties ONLY**; stopword changes require index rebuild |
| Paths / BFS | native Cypher: `*min..max`, `SHORTEST`, `ALL_SHORTEST`, `WEIGHTED_SHORTEST`, TRAIL/ACYCLIC modes |
| Projected graphs | rel- and node-level Cypher predicates → enables **as-of filtering during traversal** (project the graph to edges valid at `$as_of`, then traverse) |
| Graph algorithms | PageRank, K-Core, WCC/SCC — **no Louvain/Leiden** (community detection needs an external pass) |
| Bulk load | multi-threaded `COPY FROM` Parquet/Arrow/CSV/NPY; `ATTACH` DuckDB/Postgres/SQLite |
| Concurrency | confirmed: one READ_WRITE process XOR many READ_ONLY processes; in-memory mode; WAL + checkpointing |
| Serving | embedded only — no REST server; Python/Node/Rust/Java/WASM bindings |

Two design touch-ups this verification forces:

- **As-of traversal**: implemented via projected graphs (rel predicates on the temporal
  columns), since there are no native temporal query semantics.
- **Communities**: Louvain/Leiden are not shipped. Run community detection externally
  (e.g. igraph/graspologic over the same Parquet export that feeds the rebuild) and write
  assignments to Postgres; PageRank/K-Core/WCC can run natively in LadybugDB.

## 6. Retrieval flow — each store does one job

"No embeddings in the graph" means no vectors inside the LadybugDB snapshot — it does NOT mean
relations aren't semantically searchable. The semantic index for relations lives in **Lance,
keyed by `relation_id`**.

### Decision record: why relation vectors live in Lance, not LadybugDB

Considered and rejected: putting fact-label embeddings + HNSW into the graph snapshot for
one-engine hybrid search. Four reasons:

1. **Hard blocker — node-only indexes.** LadybugDB cannot vector- or FTS-index relationship
   properties. Indexing facts in-graph would require reifying every relation as a node
   (Entity→RelationNode→Entity), roughly doubling graph size and contorting every traversal.
2. **Snapshot economics.** 5–15M fact embeddings at 1024–1536 dims fp32 ≈ 20–90 GB inside
   every snapshot (vs. a few GB without), plus a full HNSW build per rebuild cycle (hours, not
   minutes). This kills the rebuild-first + ship-to-readers model that the rest of the design
   depends on.
3. **Lance exists regardless.** E1 chunks and E2 claims are not graph objects; their vectors
   must live in Lance anyway. Splitting the vector estate across two engines means two
   embedding pipelines, two index-maintenance regimes, two sets of failure modes.
4. **The join we avoid is cheap.** Vector search returns top-k (~100s) relation_ids; the graph
   then does ID-keyed expansion/BFS on them. That cross-store hop is microseconds of ID
   lookups — not worth an architecture to eliminate.

Division of labor: **Lance = entry** (semantic + BM25 + scalar-filtered candidate generation),
**LadybugDB = structure** (expansion, paths, graph-distance reranking, as-of traversal via
projected graphs). Revisit only if the snapshot model itself changes (e.g. an incremental
writer makes in-graph HNSW maintenance plausible) — and even then, reason #1 must first
disappear upstream.

### The relations search table (Lance)

One row per distinct fact: `relation_id`, a canonical **fact label** ("Alice Novak works at
Acme as VP of Engineering") with its embedding, plus scalar columns `subject_id, predicate,
object_id, valid_from, valid_until, invalidated_at, evidence_count`. The label is regenerated
when adjudication materially changes the relation (one short sentence — cheap).

This is Graphiti's edge-fact search relocated to the designated vector store. Searching
distinct facts instead of raw claims shrinks the search space ~5–10× and stops high-redundancy
facts from crowding the result list; scalar columns give filtered hybrid search (predicate,
entity scope, as-of windows) before the vector stage.

### Search paths by query shape

| Query shape | Path |
|---|---|
| "How are A and B related?" | entity resolution → graph adjacency (no vectors) |
| "Who works at Acme?" | structured: relations `object=acme, predicate=works_at` (scalar only) |
| "Alice's career changes?" | semantic+BM25 over Lance relations, scoped to subject=alice, RRF-fused |
| vague / no clear entity | semantic over relations AND claims; claim hits join to relations via evidence |
| "what did source X say" | claim/chunk search (E1/E2); relations hydrate *down* to evidence |

### Pipeline

```
query ──► entry points ──────────► expansion + rerank ──► hydration
          Lance relations          LadybugDB              Postgres
          (semantic + BM25)        neighborhood, paths,   relation → evidence
          Lance claims/chunks      as-of filtering,       claims → sources,
          PG FTS (lexical)         graph-distance         validity metadata,
          PG registry (entity      reranking from         GCS pointers
          name/alias lookup)       focal entities
```

### Reranking (Graphiti-inspired, zero LLM calls at query time)

- **RRF fusion** of the lexical/semantic/structured channels — default
- **graph-distance reranker**: BFS distance in the snapshot from the agent's focal entities
  ("facts near Alice") — the highest-value idea in Graphiti's search stack
- **evidence-count boost** (≈ Graphiti's episode-mentions reranker) — free from
  `evidence_count`
- optional **cross-encoder** as a flagged final stage for quality-over-latency calls
- hard rule: the core search path makes **no LLM calls** (this is how Zep hits ~300ms P95)

The API exposes composable primitives (entity lookup, `neighborhood(entity_id, predicates?,
as_of?, hops?)`, `path(a, b, max_hops)`, relation/claim search with filters) **plus named
search recipes** (`relation_hybrid_rrf`, `relation_near_entity`, `claims_verbatim`, …) so
agents pick a strategy instead of assembling plumbing per call.

## 7. Communities and K1 hints

LadybugDB ships some graph algorithms natively (PageRank, K-Core, connected components). Run
them on the snapshot after rebuild, write results **back to Postgres** (community assignments,
centrality scores) — the graph stays a projection. Uses, in priority order:

Note: Louvain/Leiden are NOT shipped in LadybugDB's algo extension (verified) — community
detection runs as an external pass (igraph/graspologic) over the rebuild's Parquet export;
PageRank/K-Core/WCC run natively on the snapshot.

1. **K1 compile hints**: communities ≈ candidate topics; "claims in community C changed" is a
   better incremental-refresh trigger for K1 summaries than per-file signals (Zep uses
   communities exactly this way).
2. **Entity importance**: PageRank as a salience prior for retrieval ranking and K3 candidate
   filtering.
3. **Registry hygiene**: tiny disconnected components often indicate entity-resolution misses.

## 8. Failure modes

| Failure | Handling |
|---|---|
| Snapshot corruption / bad rebuild | Validation gate before `latest` pointer moves; readers never see it; previous snapshot stays serving |
| Writer crash mid-cycle | Snapshot upload is atomic (write-then-pointer-swap); next cycle just reruns — rebuilds are idempotent by construction |
| PG↔graph drift | Impossible beyond one cycle (rebuild) — no reconciliation jobs needed |
| Graph size growth | Invalidated edges older than N months can be excluded from the *hot* snapshot (PG keeps everything; deep time-travel falls back to PG or an archive snapshot) |
| Predicate explosion | Registry governance (§3); rebuild makes vocabulary cleanups retroactive for free |

## 9. Open questions

1. Rebuild cadence to start — hourly or every 6h? (Cost is one Cloud Run job + a few GB of GCS
   traffic per cycle.)
2. Do `MENTIONED_IN` edges link to documents only, or also to PageIndex nodes (finer-grained,
   bigger graph)?
3. Should attribute claims ever project into the graph (as entity properties), or stay
   E2-only? (Current call: E2-only.)
4. Where do retrieval API readers run — same Cloud Run service as the rest of the API, with
   snapshot on local SSD? Snapshot size will decide.
