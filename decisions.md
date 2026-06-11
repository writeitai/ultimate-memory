# Architecture Decision Log

Decisions made during requirements/design exploration (June 2026), with context and rationale.
Companion docs: `plan/requirements/requirements_v3.md` (what),
`plan/designs/p2_graph_design.md` (graph how), `plan/analysis/concepts.md` (data-model
explainer), `plan/analysis/ladybug_capabilities.md` (verified DB facts), `questions.md`
(open). Naming note: D1–D13 predate the E/K/P plane naming (D14) and keep their original
L-numbers as historical record.

---

## D1. Split source of truth: Postgres vs. the git repo

**Decision.** Postgres is authoritative for L0–L2 and L6 — everything deterministically
derivable. The L3–L5 git repo is *itself* a source of truth (backed up independently);
Postgres holds only its provenance and triggers.

**Context.** v1 required "the entire system rebuildable from Postgres" while also making
L3–L5 LLM-derived git-tracked layers. LLM output is non-deterministic — those layers are not
reproducible from Postgres unless model+prompt+inputs are pinned, and even then re-runs differ.
The two requirements contradicted each other.

**Consequences.** Rebuild guarantees apply to L0–L2+L6 only. The repo needs its own backup
discipline. Postgres records prompt/model/embedding versions per derived artifact so partial
reproducibility is still auditable.

---

## D2. Claims and relations are distinct concepts (many-to-many)

**Decision.** L2 claims are atomic *natural-language assertions* (identity =
assertion-by-a-source; immutable, append-only). A separate normalization step maps eligible
claims onto **relation** records `(subject_entity, predicate, object_entity)` (identity = the
fact itself). Join table `relation_evidence(relation_id, claim_id, stance)` connects them.

**Context.** An earlier draft stamped `claim_id` directly on graph edges, silently assuming
claims ≅ triplets 1:1. They aren't: one claim can yield several facts; one fact can be asserted
by hundreds of documents; many claims (opinions, n-ary, single-entity attributes) yield none.

**Consequences.**
- Corpus redundancy collapses: N documents asserting the same fact = one relation with N
  evidence rows, not N parallel edges. `evidence_count` becomes a free confidence/salience
  signal (and a candidate filter for L5 core beliefs).
- Graph edge count scales with distinct facts, not corpus size.
- Full reasoning in `plan/analysis/concepts.md`.

---

## D3. Supersession/contradiction adjudication operates at the relation level

**Decision.** "Alice left Acme" closes the validity window of the relation
`(alice, works_at, acme)` — one row update. Claims are never marked superseded; they remain
true as records of what sources asserted.

**Context.** Claim-level supersession would require finding and flagging every assertion that
ever implied the old fact (hundreds of records, inevitable misses → zombie facts in
retrieval). Mirrors how Graphiti invalidates edges, not episodes.

**Consequences.** Two clocks with different semantics: claim timestamps (asserted/ingested)
never change; relation windows (valid_from/valid_until + ingested_at/invalidated_at) are
revisable adjudications over evidence. Both time-travel questions ("was it true at T?" /
"what did we believe at T?") stay answerable.

---

## D4. Supersession detection via entity-keyed blocking + cheap-first cascade

**Decision.** Candidate conflicts are found by blocking on `(entity_id, predicate)` over the
relations table (small — distinct facts only), then escalating: exact → fuzzy → embedding
similarity → small model → frontier LLM only for the residue. A novelty gate (similarity
thresholds) routes clear ADD/NOOP cases past the LLM entirely.

**Context.** O(N) vector-similarity scans per write are both unaffordable at millions of
claims and imprecise (they surface compatible-but-related statements, forcing wasted LLM
judgments). Convergent recommendation of both external reviews. Blocking requires a predicate
— which raw NL claims don't have — making the relations table (D2) the enabling index.

**Consequences.** Write-side LLM cost scales with ambiguity, not volume. Entity-resolution
quality becomes make-or-break (false negatives in resolution = missed supersessions) →
invest in the registry early; coreference resolution runs before claim extraction.

---

## D5. Predicate vocabulary is governed, not emergent

**Decision.** A Postgres predicate registry (name, description, synonyms, status). Extraction
is constrained to the registry with an `other:<freetext>` escape; a periodic job reviews and
promotes/maps frequent `other:` values. Start strict (high precision, smaller graph).

**Context.** Free-text predicates fragment ("works_at"/"employed_by"/"is employee of"),
silently breaking both `(entity_id, predicate)` blocking and graph queries.

**Consequences.** Ontology evolves by review, not accretion. Because the graph rebuilds (D7),
vocabulary cleanups apply retroactively for free. Loosening later is cheap; tightening a noisy
vocabulary later is not — hence strict-first.

---

## D6. The graph (L6) is a derived projection, never an authority

**Decision.** LadybugDB holds a read-optimized projection of Postgres facts. It makes no
decisions, stores no unique state, holds **no embeddings**, and can be deleted and rebuilt at
any time. Validity metadata has exactly one home: Postgres.

**Context.** The strongest finding from the external supersession review: replicated
invalidation state across vector/graph stores drifts (documented Mem0 desync bug class).
Deliberate divergence from Graphiti, which adjudicates inside the graph at write time — we
already paid for adjudication at L2; a second authority would only create disagreement.

**Consequences.** The graph writer is dumb and deterministic. Graph corruption is a
non-event (rebuild). All cross-store consistency questions reduce to "how stale is the
projection," bounded by rebuild cadence.

---

## D7. Rebuild-first sync; immutable GCS snapshots; read-only readers

**Decision.** The L6 worker periodically rebuilds the entire graph from a Postgres → Parquet
export (`COPY FROM` bulk load), validates, and publishes an immutable versioned snapshot to
GCS (write-then-pointer-swap). Readers download the `latest` snapshot, open READ_ONLY, and
hot-swap on updates. Incremental event application is Phase 2, only if sub-hour freshness is
ever actually needed.

**Context.** LadybugDB's verified concurrency model is one READ_WRITE process XOR many
READ_ONLY processes — snapshot serving is the intended usage, not a workaround. Sizing at the
1M-doc target (distinct relations, few GB, minutes to bulk-load) makes full rebuilds cheap.

**Consequences.**
- Drift between Postgres and graph is impossible beyond one cycle — no reconciliation jobs.
- Entity merges (nightmare incrementally — re-pointing thousands of edges) are no-ops.
- "Rebuildable from Postgres" is exercised every cycle instead of rotting as a DR script.
- Old snapshots are free point-in-time debugging artifacts.
- Freshness SLA = rebuild cadence (start 6-hourly; tighten if missed).

---

## D8. Relation fact-label embeddings live in LanceDB, not in the graph

**Decision.** Each relation gets a canonical fact label ("Alice Novak works at Acme as VP of
Engineering") embedded in a Lance `relations` table keyed by `relation_id`, with scalar
columns (subject_id, predicate, object_id, validity window, evidence_count) for filtered
hybrid search. No vectors in the LadybugDB snapshot.

**Context.** Challenged ("is Lance really the best place?") and then verified against the
vendored LadybugDB source + official docs. Findings (detail in
`plan/analysis/ladybug_capabilities.md`):

1. **Hard blocker**: LadybugDB's HNSW vector index and BM25 FTS index support **node-table
   properties only** — relationship properties cannot be indexed. In-graph fact search would
   require reifying every relation as a node, roughly doubling the graph and contorting
   traversals.
2. **Snapshot economics**: 5–15M fact embeddings at 1024–1536 dims fp32 ≈ 20–90 GB inside
   every snapshot (vs. a few GB without) plus a full HNSW build per rebuild cycle — destroys
   the rebuild-and-ship model (D7).
3. **Lance exists regardless** for L1 chunks and L2 claims; one vector estate, one embedding
   pipeline, one index-maintenance regime.
4. **The avoided join is cheap**: top-k (~100s) relation_ids from Lance → ID-keyed
   expansion/BFS in the snapshot.

**Consequences.** Division of labor: Lance = entry (semantic + BM25 + scalar-filtered
candidate generation); LadybugDB = structure (expansion, paths, distance reranking, as-of
traversal). Revisit only if D7 changes *and* the node-only limitation disappears upstream.
The Lance relations table is derived state, rebuilt with the same guarantees as the snapshot.
Fact labels add a small write-side LLM cost (one sentence per relation, only on material
adjudication changes).

---

## D9. Search architecture: Graphiti-inspired, zero LLM calls on the query path

**Decision.** Parallel retrieval channels (semantic over Lance relations + claims, BM25,
lexical PG FTS, structured scalar lookups, registry entity resolution) fused with **RRF**;
reranked by **graph distance from focal entities** (native SHORTEST/BFS in the snapshot) and
**evidence count**; optional cross-encoder as a flagged final stage. Composable primitives
plus named **search recipes** (`relation_hybrid_rrf`, `relation_near_entity`,
`claims_verbatim`, …). Hard rule: no LLM calls in the core search path.

**Context.** Graphiti's search stack (edge-fact embeddings + BM25 + graph traversal, RRF
default, node-distance/episode-mentions/MMR/cross-encoder rerankers, canned recipes, no
query-time LLM — how Zep reaches ~300ms P95), adapted to our store layout: their edge-fact
embedding relocates to Lance (D8); their episode-mentions reranker is our `evidence_count`,
free from D2.

**Consequences.** Query latency is bounded by retrieval+rerank, not generation. Agents pick
strategies instead of assembling plumbing. Center-node reranking requires focal-entity
resolution first — the registry is on the hot path.

---

## D10. As-of traversal via projected graphs

**Decision.** Bi-temporal filtering during graph traversal is implemented with
`PROJECT_GRAPH_CYPHER` relationship predicates over the four temporal columns (project the
graph down to edges valid at `$as_of`, then traverse), since LadybugDB has no native temporal
query semantics.

**Context.** Verified: projected graphs accept rel-level Cypher predicates; nothing else in
the engine understands time.

---

## D11. Community detection runs externally (Phase 3)

**Decision.** LadybugDB's algo extension ships PageRank, K-Core, and connected components but
**no Louvain/Leiden** (verified in `src/extension/extension_entries.cpp`). Community detection
runs as an external pass (igraph/graspologic) over the same Parquet export that feeds the
rebuild; results (community assignments, centrality) are written back to **Postgres**, keeping
the graph a projection (D6). Communities then serve as L3 refresh triggers ("claims in
community C changed") and salience priors.

---

## D12. Trigger model: per-document chain ends at L2; aggregates are debounced

**Decision.** L0→L1→L2 chain per document (Cloud Tasks). L3–L6 are *aggregate* layers
triggered by windows/debounce ("N new claims or T minutes"), with the rolling-window-delay
worker for hot files (index.md). Cloud Tasks: max 2 retries + dead-letter into Postgres;
idempotent workers keyed by content hash + processing version.

**Context.** "Trigger next layer when previous finishes" (v1) maps cleanly only to
per-document layers. L3+ summarize *across* documents; per-doc triggering of a serial
git-editing layer was the design's scaling bottleneck.

---

## D13. LadybugDB accepted as the L6 engine (P2 after D14)

**Decision.** LadybugDB (maintained community successor of Kuzu after Kuzu Inc. was acquired
by Apple and open-source development stopped, October 2025) is the L6 base: embedded,
columnar, Cypher, native paths, Parquet/Arrow interop, read-only multi-process mode.

**Context.** Confirmed via web research and a survey of the vendored source tree
(`plan/analysis/ladybug_capabilities.md`). Risks accepted: young fork; vector/FTS/algo extension
implementations live in a separate repo (not vendored) — irrelevant to our usage since
vectors/FTS stay in Lance (D8) and the engine features we depend on (COPY FROM, paths,
projected graphs, read-only mode) are core, verified in source.

---

## D14. Naming: three planes (E/K/P) replace the L0–L6 ladder

**Decision.** The system is described as three planes, each with its own internal sequence,
because the plane — not the number — determines the operational rules (trigger model, source
of truth, mutability, rebuild semantics):

- **Plane E — Evidence** (per-document processing writing into global ledgers; Postgres is
  truth): **E0 files, E1 chunks, E2 claims, E3 relations**; plus the **entity and predicate
  registries** as explicit cross-cutting substrate (layers *transform*, registries
  *canonicalize*).
- **Plane K — Knowledge** (aggregate, LLM-compiled, debounced; git is truth): **K1 general,
  K2 special-purpose scopes, K3 core beliefs**.
- **Plane P — Projections** (derived, no authority, rebuilt on schedule, immutable
  snapshots): **P1 search indexes** (Lance), **P2 graph** (LadybugDB).

Mapping: L0→E0, L1→E1, L2→E2, L3→K1, L4→K2, L5→K3, L6→P2. Relations (E3) and the Lance
indexes (P1) previously had no name at all. L-numbers survive as colloquial shorthand;
"(formerly LX)" annotations are kept for one doc generation.

**Context.** Accepted objection O1 (`plan/analysis/objections.md`). The ladder implied a
single cascade of same-kind layers; in reality P2 is a projection of E3, not a level above
K3, and relations — the most load-bearing artifact — had no slot. Every recurring design
confusion was a plane-boundary violation: `claim_id`-on-edges (E3 vs P2), "each layer
triggers the next" (E rules applied to K), "is the graph rebuildable" (P semantics asked of
K). The asymmetry that the graph projection had a layer number while the vector indexes
didn't was a symptom of the same conflation.

**Consequences.** `requirements_v3` and `overall_design` reframed around planes;
`l6_graph_design.md` renamed `p2_graph_design.md`; future per-layer designs named by plane
(e2_claims, k_layers, …). O2 (collapsing K1–K3), if later accepted, becomes a change local to
plane K. Decision texts D1–D13 keep their original L-naming as historical record; the mapping
above translates.

---

## D15. Ontology: universal core + anchored extensions, on the registries

**Decision.** Users define their own ontology per problem; the system ships a small
best-effort core. Both live in the existing registries (D5) — ontology is content, not new
machinery:

- **Universal core, borrowed not invented**: ~8 entity types and ~10–15 predicates aligned
  with schema.org naming (extraction LLMs have strong priors on that vocabulary — familiar
  names are a quality lever, not aesthetics).
- **Extension rule — extend, never fork**: every user-defined type declares a core parent
  (`ResearchPaper ⊂ Document`); predicates may too. This keeps blocking, graph queries, and
  cross-scope retrieval working at the core level over any custom domain.
- **Domain/range constraints** on predicates (`works_at: Person → Organization`) —
  lightweight typed columns that mechanically reject a class of extraction hallucinations.
- **Prompts render from the registry** (types/predicates/descriptions/examples): defining a
  scope = editing rows, not prompt engineering; prompt-version tracking (D12) captures
  ontology changes.
- **Deliberately not OWL**: parent-links + domain/range replicate most benefits without
  permanent reasoner/tooling cost. User-supplied OWL can be imported into the registry.

**Context.** Multiple K2 scopes are domain ontologies in disguise; a fixed universal ontology
either bloats or strangles them. Cognee's ontology-anchoring informed the external-authority
idea (tier 0 of resolution); the `other:` escape (D5) becomes the discovery/promotion funnel.
Three speeds, one registry: core (slow, each element a commitment) → scope extensions (fast,
each an experiment) → `other:` (ungoverned, monitored). Analysis:
`plan/analysis/entity_registry.md`.

**Consequences.** Adding types/predicates = inserting rows. Retyping is retroactively clean
in P2 thanks to rebuilds (D7). Only splitting heavily-used types/predicates is expensive —
hence the small core. Seed lists and constraint tables go to `registries_design.md`.

---

## D16. One graph, many lenses: scopes never get their own graph

**Decision.** Multiple K2 scopes (projects, team profiling, …) share one P2 graph and one
entity space. Scopes get, in increasing order of weight: (1) **ontology extensions** (D15) —
their vocabulary as a footprint in the shared graph; (2) **query-time scope views** via
`PROJECT_GRAPH_CYPHER` (verified LadybugDB capability), declared in the registry as
scope → predicate/type lists; (3) **materialized filtered snapshots** only if performance or
access isolation ever demands — emitted by the same P2 rebuild from the same Postgres export,
a second projection of the same truth, never a second graph.

**Context.** Separate per-domain graphs would re-fragment identity — the exact disease the
registry cures — and kill cross-scope queries ("which team members worked on projects
connected to X?"), which are the point of having a graph. Plane discipline: K2 scopes are
consumers of plane E, not owners; a scope owns its compiled markdown, never facts.

**Consequences.** New scope = git directory + registry rows (types/predicates + scope-view
definition) + extraction interests; never a new database. Rule of thumb: **scopes multiply;
truth doesn't.** Access-sensitive scopes (e.g. people profiles) are handled by filtered
snapshots + API-level authorization, not by forking storage.
