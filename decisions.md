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

**Refined by D46.** "Not reproducible" was over-scoped: LLM non-determinism blocks *byte*
reproducibility, not *semantic* reproducibility. Compiled K pages are semantically regenerable
from the spine plus their recorded compile inputs; the git repo's **irreducible** source-of-truth
core — what backups genuinely protect — is human-authored content (authored pages + curation
sidecars).

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

**Refined by D41.** Claims additionally carry an *immutable* source-asserted validity interval
(testimony about temporal extent). It never becomes revisable and never introduces claim-level
supersession — the adjudicated window stays relation-only; this strengthens, not weakens, D3.

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
invest in the registry early. Coreference is a *guarantee* (no claim leaves E2 with a dangling
pronoun), not necessarily a discrete prior stage — its topology is set by D19. Tier thresholds
mentioned here are placeholders superseded by D17 (per-type, golden-set-tuned).

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

**Refined by D41.** Claim-grain asserted-validity is *evidence*, not a second validity home: it is
immutable and many-valued, lives in Postgres only, and the `claims_as_of` recipe is barred from
answering current-belief — so validity-as-current-belief still has exactly one home.

---

## D7. Rebuild-first sync; immutable GCS snapshots; read-only readers

**Decision.** The L6 worker periodically rebuilds the entire graph from a Postgres → Parquet
export (`COPY FROM` bulk load), validates, and publishes an immutable versioned snapshot to
GCS (write-then-pointer-swap). Readers download the `latest` snapshot, open READ_ONLY, and
hot-swap on updates. Incremental event application is a **deliberate non-goal** — rebuild-first
is the design; incremental is a documented alternative (`p2_graph_design.md` §5) we would adopt
only if sub-hour graph freshness ever became a hard requirement.

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

## D11. Community detection runs externally

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

**Refined by D45.** The hot-file rolling-window-delay worker is superseded: the K compile driver
is the repo's only automated committer and compiles in dependency order, so hot files (the root
`index.md`) are simply the last DAG target, compiled once per cycle. The debounce/window trigger
model itself is unchanged.

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
  with schema.org naming — *familiar, schema.org-aligned names + registry-rendered
  descriptions/examples* (LLMs interpret labels by pretrained semantics, so meaningful names
  beat arbitrary ones; **no measured schema.org-vs-good-synonym delta is claimed**). Concrete
  seed core fixed in D18.
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
either bloats or strangles them. The `other:` escape (D5) becomes the discovery/promotion
funnel. (An external-authority resolution tier was considered and later dropped — see D20.)
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
snapshots + API-level authorization, not by forking storage. Scope-sharing applies *within*
one deployment only — separate deployments (assistant, agency, client projects, …) are fully
independent instances with separate entity spaces (`registries_design.md` §1, deployment
model).

---

> **D17–D30 provenance.** D17–D24 formalize the entity-registry research
> (`plan/analysis/registry_research/SYNTHESIS.md`, objection O5); **D25 records the rejection of the
> value-gate mechanism** (O3 premise accepted, gate-as-answer rejected —
> `plan/analysis/value_gate_research/SYNTHESIS.md` + `plan/analysis/claimify_research/SYNTHESIS.md`);
> **D26–D30 are withdrawn-in-place** (folded into D25). Both
> efforts read 12 systems at source + literature, with adversarial fact-checkers. Where a
> number is involved it is a **placeholder to be measured on a golden set / corpus slice**, not
> a committed constant — the spikes are listed in each SYNTHESIS §5.

## D17. Canonical resolution tier cascade (T0–T4), block-loose / decide-tight

**Decision.** One authoritative entity-resolution cascade, replacing the scattered/folklore
thresholds: **T0** exact match on the LLM-emitted canonical name form (§5/D19) → **T1** fuzzy
*blocking* (`pg_trgm` GIN, recall-first low floor — candidate generation, NOT a decision) →
**T2** phonetic (Daitch-Mokotoff, **not** Soundex) → **T3** embedding similarity (Lance, residue
only) → **T4** LLM adjudication (small→frontier) on the ambiguous middle band → human review for
high blast-radius. **Registry-self-contained — no 3rd-party external-authority tier (D20).** Each
tier's accept/reject bands are **per-type, golden-set-measured, versioned config** stamped with
`resolver_version`. No threshold ships without a per-type precision/recall curve.

**Context.** JW≥0.92 / cosine≥0.88 were folklore: JW 0.92 is Splink's per-field Bayes *evidence
level*, not an accept bar; benchmark spread (Magellan 98.4 clean vs 43.6 textual) proves no
global constant works. Graphiti independently arrived at the same block-loose/decide-tight shape.
(R2; refines D4.)

**Consequences.** LLM cost scales with ambiguity. Blocking sets a hard recall ceiling, so cheap
tiers *escalate* near-misses, never auto-reject. Feeds O6 (every threshold needs the golden set).

## D18. Ontology seed core — 8 types + 14 predicates, schema.org-anchored, domain/range not OWL

**Decision.** Seed core: 8 entity types (`Person, Organization, Place, Document⊂CreativeWork,
Event, Concept, Project, Product`) + 14 predicates with `subject_type`/`object_type` columns
(`works_for, member_of, affiliated_with, located_in, part_of, authored, created, about,
knows_about, knows, participated_in, works_on, founded, related_to`). `related_to` is the
predicate-side core parent for extend-never-fork (D15). Time is bi-temporal edge metadata, never a
predicate or Date-node. Enforce domain/range exactly as Graphiti's `edge_type_map[(src,tgt)→[rel]]`
— the only structural ontology gate any surveyed production system ships. Schema.org property
mappings get a spot-check before freezing.

**Context.** Concretizes D15. Graphiti's `edge_type_map` is the validated mechanism; Cognee loads
OWL but enforces no domain/range. The "familiar names help extraction" claim is true in spirit
(pretrained semantics) but no measured schema.org-vs-synonym delta is asserted. (R5.)

**Consequences.** Work-shaped concepts (Task/Decision/Goal) stay out of the core but ship as a
system-provided **extension pack**, enabled per deployment — full entity status without a core
commitment; `Decision` standing rides on bi-temporal relations, so reversals are ordinary
supersession (`registries_design.md` §4, extension packs).

**Scope clarification (D41).** "Time is never a predicate or Date-node" governs the **relation/graph**
representation of time. A claim's immutable asserted-validity interval (D41) is *claim metadata*, not
a relation object/predicate or a Date-node, so it is fully compatible — D18 is unchanged.

## D19. Coref is satisfied inside the E2 extraction call (no dedicated model)

**Decision.** Coref is the guarantee that no claim leaves E2 with a dangling pronoun — satisfied
**inside the E2 extraction call, for all languages** (the LLM reads the chunk/document and writes
claims with referents resolved). **No dedicated coref model or pre-pass** (CorPipe/CorefUD).
Rationale: the extraction LLM is already called, so coref — a per-mention understanding task —
rides that call at ~zero marginal cost; a separate model would be a separate pass, separate
infra, and (CorPipe) a CC BY-NC-SA licensing exposure, to do something the LLM already does.

**Context.** Same family of decisions as entity typing (`registries_design.md` §4): per-mention
understanding (typing, coref, name-canonicalization) is free with extraction; only *at-scale
matching against the registry* (fuzzy/phonetic/embedding) needs non-LLM tiers. 6/6 surveyed
systems do coref in-call. The earlier "dedicated coref beats LLM by ~13 CoNLL F1" finding
compared older/constrained LLMs, not a frontier model extracting with full context; Czech and
other inflected languages are well-served by frontier LLMs in-context. (R1, R3; refines D4.)

**Consequences.** Cross-*document* coref ("the CEO" referring to an entity introduced in another
document) remains an open recall gap — it is not solved by intra-document coref of any kind
(LLM or model). If a *future* deployment's language is genuinely poorly served by frontier LLMs
(a low-resource language — not Czech), a specialized model could be reconsidered as a
per-deployment alternative — a documented option, not part of the system.

## D20. No 3rd-party external-authority tier — resolution is registry-self-contained

**Decision.** Entity resolution does **not** depend on 3rd-party external registries (Wikidata,
OpenAlex, DOI, ORCID, LEI, …). Identity is resolved entirely from the system's own data via the
T0–T4 cascade (D17). The earlier "tier-0 authority" idea is **dropped from scope.**

**Context.** Two reasons. (1) **Coverage:** public registries only know publicly-notable entities
(listed companies, published researchers, papers) — near-zero coverage for the actual target
deployments, whose data is internal/private/domain-specific (a manufacturer's internal systems,
a personal assistant's contacts, statutes, internal projects). (2) **Dependency:** they put an
external, rate-limited, license-encumbered service on a core write path for little return. The
research (R4) recommended them as an *optional, never-gating accelerator*; for these deployments
that accelerator rarely fires, so the simplicity of dropping it wins.

**Consequences.** The cascade starts at T0 = exact match on the LLM-emitted canonical name form.
The genuinely valuable "authority" case is **internal/domain authoritative IDs** (a source
system's own keys, legal citations) — *not* 3rd-party registries; that is a **future
per-deployment connector** (a documented alternative, not part of the system), which would attach such IDs as aliases (never as the
canonical `entity_id`). No `external_ids` table ships now.

## D21. Clustering algorithm + incremental procedure + reversibility records

**Decision.** Decision clustering = **connected-components-to-gather** (with a black-hole guard:
raise threshold + repartition above component size T) → **HAC distance-cut inside each blob**
(never bare transitive closure; never Louvain/Leiden for ER — that's D11 community detection).
Write-path incremental = max-both assignment + **nDR n=1** (re-cluster only the 1-hop neighborhood;
order-independent; n=2 only when a hub is touched). Reversibility state lives **only in Postgres**:
`resolution_decisions` (append-only, `superseded_by`), `merge_events` (append-only, pre-merge
membership snapshot), `merged_into` redirect chain, optional negative/exclusion edges. A
generic-identifier guard (Senzing) down-weights + re-evaluates an alias that suddenly links many.
P2 rebuild (D7) re-points edges on merge/un-merge for free.

**Context.** No OSS system (Splink/dedupe/Zingg/Graphiti) ships un-merge — building it in Postgres
is correct, not over-engineering. dedupe uses exactly HAC `linkage(centroid)`+`fcluster(distance)`
+ a `max_components` guard. (R8.)

## D22. Golden-set + evaluation plan

**Decision.** Two **separate** assets: a **golden EVAL set** (unbiased, measures P/R, tunes
thresholds) and a **training set** (built only if a learned matcher is ever added; AL-sampled,
biased, never used to measure). The eval set: ~200 human-verified labeled pairs/type (~100 hard
positives incl. synthetic father/son/inflection/married-name + ~100 hard negatives; ~400/type for
auto-merge-critical types), blocking-stratified positive over-sampling, **Wilson** CIs, per-tier
metrics, and a canary regression harness re-run per `resolver_version`. **Break the circularity:**
the cascade/LLM may *propose* candidate pairs, but measurement labels must be **human-adjudicated**.
The eval plan also covers the **retrieval half of O6** (recall@k per search recipe, rerank-weight
tuning, contradiction-detection precision). A learned matcher + active-learning training loop are
a documented **optional extension** of the cascade (D17), kept strictly separate from the eval
set — the core design resolves with the deterministic + LLM tiers, not a learned matcher.

**Context.** Closes O6's ER half concretely; the same eval set also seeds E2 Selection's
claim-verifiability golden set (D25 — junk-control moved to in-call Selection, not a salience gate).
(R7, O6.)

## D23. Registry scale & schema

**Decision.** RANGE-partition the three ~10⁸ append-only tables (`mentions`,
`resolution_decisions`, `relation_evidence`) by ingest month (`pg_partman`); **btree-only** on
those hot tables (cap write-amplification). Do **not** partition `entities`/`aliases` (the blocking
targets, ≤10⁷). GIN `gin_trgm_ops` + GIN `daitch_mokotoff(name)` on `aliases.normalized_name`;
btree composite `(subject_entity_id, predicate[, object])` on `relations`. Supersession + tiers
T0–T2 run in Postgres; embedding tier T3 in Lance (D8); HNSW never in OLTP. Load-test a
representative corpus slice before locking partition/index choices. **Row counts are contingent on
the value gate (D25) — size against *gated* volume.**

**Context.** Only the 10⁸ tables are huge and they're never fuzzy-scanned (queried by id/doc_id).
(R9.)

## D24. Review tooling — build a thin Postgres-backed cluster-review queue

**Decision.** **Build** (don't adopt as system-of-record) a thin CLI cluster-review queue over
Postgres; no OSS tool offers cluster-queue + append-only reversible verdicts + provenance +
blast-radius gating. Review **clusters, not pairs** (pairwise is quadratic); route only the
`expected_impact = blast_radius × (1 − confidence)` middle band to humans; high-degree hub merges
never auto-accept. Borrow Splink's waterfall (evidence panel), Zingg's 3-way verdict (ergonomics),
OpenRefine's cluster-card-with-exclude (interaction). Every action appends a reversible,
provenance-stamped, redirect-preserving record (D21). The design is the CLI queue; a web UI /
Argilla is an optional addition if review volume ever justifies it, not part of the core design.
(R10.)

## D25. No pre-extraction value/salience gate — junk-control is in-call at E2 Selection + D2

**Decision.** There is **no E1.5 stage and no value/salience gate**. Plane E is `E0 → E1 → E2 → E3`;
every document that survives chunking is fully extracted. Junk-control moves to where junk is cheapest
and safest to identify: **E2 Selection** (Claimify proposition-level verifiability KEEP/REWRITE/DROP,
in-call, zero marginal LLM calls — the ablation-proven highest-leverage stage, element-coverage
macro-F1 83.7→54.4 when removed) and **D2** (corpus redundancy collapses into one relation +
`evidence_count`, so duplicate *facts* cost nothing in the graph). Exact-content-hash dedup remains as
the **D12/D7 idempotency** mechanism (a `content_hash` short-circuit at the worker boundary), never as a
value tier. The E0 **PageIndex section path/role is fed into the E2 call** so Selection can drop
references/boilerplate/intro/conclusion at proposition grain (the structural signal is *absorbed into*
extraction, not used as a binary pre-skip).

**Context.** O3's *premise* (most raw content is low-value; junk poisons downstream) is **accepted**;
its proposed *mechanism* (a pre-extraction gate) is **rejected**. The only "value" rung (a distilled
salience classifier) is unbuilt and golden-set-dependent; the novelty rung is a corpus-scale ANN at 10⁸
claims (the gate's own #1 self-defeat risk — it becomes a new fleet-scale stage); the honest cost lever
is ~1.5–2×, not 10×, and the 10× lived entirely in the DEFERRED tier whose two Postgres state tables +
transactional outbox + `SKIP LOCKED` queue + heartbeat reconciler + four promotion triggers are pure
complexity for that 1.5–2×. Claimify's Selection ablation makes the in-call verifiability filter the
highest-leverage junk control and it is free; D2 already neutralizes redundant-fact cost. The gate also
concentrated the system's highest-severity correctness risk (the zombie-fact / supersession-skip case —
silently withholding the only superseding evidence) and the circular never-defer-by-predicate problem;
extracting every section removes that failure mode at its root. (O3 premise; value_gate_research V1–V6;
claimify_research C4/C8.)

**Consequences.**
- Plane E reverts to `E0→E1→E2→E3` (`overall_design.md` §4). Paying E2 on everything is the ~1.5–2× the
  gate would have saved; Selection's in-call precision means that spend buys *clean* claims.
- **R9 / D23 re-stamp:** the three 10⁸ tables (`mentions` / `resolution_decisions` /
  `relation_evidence`) are sized against **full extraction** again (`f_full = 1`); the favorable gate
  shrink is withdrawn and R9's partition/index load-test plans against ungated volume.
- The E1.5 design doc is retired; `plan/designs/e2_e3_claims_relations_design.md` §4 records the
  non-goal (why there is no value gate) and what handles junk instead.
- The recall-conservative discipline (defer-don't-DROP) relocates one grain down, to E2 Selection (the
  claim-layer D35 proposal): conservative KEEP bias, never-drop lexical classes, `kept_flagged` (no hard
  delete), DROP ledger, per-fact canary CI.
- **Future option (documented, not built):** if a corpus slice ever shows extraction cost is dominated
  by structurally-skippable sections, a *trivial deterministic* section filter
  (`pageindex_node_type NOT IN {references, bibliography, nav, boilerplate, legal}` on E2 entry — no
  classifier, no ANN, no defer machinery) is the cheap add-back, gated on a measured break-even. This is
  explicitly **not** a smart gate.

## D26. *(withdrawn — folded into D25)*

Was "the gate is a nested cheap-first cascade" (T-dup → T-struct → T-novel → T-salience). Withdrawn
with the gate (D25). The cheap-first philosophy survives unchanged in D4 (supersession) and D17
(resolution). Exact-content-hash dedup survives as plain D12/D7 idempotency, not a value tier.

## D27. *(withdrawn — folded into D25)*

Was "defer decision is durable, versioned Postgres state." There is no defer decision; the
`gate_decisions` / `document_extraction_state` / `salience_gate_versions` tables are not built.

## D28. *(withdrawn — folded into D25)*

Was "lazy promotion triggers." No DEFERRED tier, so no promotion. K2 scope-interest (D16) remains a
query/compile-time selection over fully-extracted facts, never a promotion trigger.

## D29. *(withdrawn — folded into D25)*

Was "defer-don't-DROP recall envelope." The recall-conservative discipline relocates one grain down to
E2 Selection (the claim-layer D35 proposal): conservative KEEP bias, never-drop lexical classes,
`kept_flagged` (no hard delete), an append-only DROP ledger, per-fact canary CI — defer-don't-DROP at
the proposition grain, where junk is actually identifiable.

## D30. *(withdrawn — folded into D25)*

Was "gate cost & break-even discipline." No gate to cost. The break-even discipline survives as a
property of E2 spend (the claimify cost model) and of the documented trivial structural-skip add-back
(D25, future option).

---

> **D31–D35 provenance.** D31–D35 formalize the Claimify E2 research
> (`plan/analysis/claimify_research/SYNTHESIS.md`, the de-contextualization + claim-level-selection
> effort); the binding design is `plan/designs/e2_e3_claims_relations_design.md`. Numbers/thresholds
> are placeholders to be measured on a golden set / corpus slice (see that SYNTHESIS §4 spikes).

## D31. E2 is a Claimify-staged extractor over a context bundle (two calls)

**Decision.** Claim extraction runs over a **context bundle** (target chunk + document header +
PageIndex section path + the E1 context prefix + ±N same-section neighbour chunks + entity hints),
never a bare chunk. The model does three jobs: **Selection** (keep only specific, verifiable
propositions; drop opinion / advice / hypothetical / generic / intro-conclusion / lack-of-info; keep
only the verifiable span of a mixed sentence), **Disambiguation/decontextualization** (resolve
references from the bundle and *only* the bundle; add the minimum context; discard when there is no
confident reading; coref in-call per D19), and **Decomposition** (atomic, attribution-preserving
claims). It runs as **two calls** (Selection separate from a fused decontextualize + decompose + ground
call); a one-call collapse is permitted only after an ablation. The literal three-calls-per-sentence
loop is not used at scale.

**Context.** Refines D4 (cheap-first) and realizes D19 (coref in-call). Selection is split out because
it is the highest-leverage stage and carries the opposite instruction to decontextualization. Design +
worked example: `plan/designs/e2_e3_claims_relations_design.md`. (C1–C8.)

## D32. Claim grounding is layered and dual-field, not verbatim-substring

**Decision.** A claim stores both a standalone `claim_text` and a verbatim `source_span` + character
offsets, plus an `added_context[]` list naming each added substring's bundle source. Acceptance layers,
cheapest first: (1) deterministic **anchor** — the source span is a real slice of the chunk; (2)
deterministic **window-membership** — every added substring verbatim-exists in its declared bundle
source (rejects fabrication); (3) an in-call **entailment self-verdict** (incl. the "*X said* Y entails
*X said Y*, not *Y*" rule); (4) a **sampled independent** entailment audit (never per-claim). Replaces
the verbatim-substring gate, which is incompatible with decontextualization. No external knowledge.

**Context.** A decontextualized claim is a rewrite, so it is never a verbatim substring; grounding must
be provenance + entailment, as every surveyed decompose-then-verify system does. (C6.)

## D33. E2 selection-drops and decontextualization edits are append-only, versioned state

**Decision.** Every Selection drop (with reason) and every decontextualization edit is written to an
append-only, version-stamped `claim_extraction_decisions` table. Rebuild reads stored claims +
decisions and never re-calls the model (the LLM rungs are replay-from-storage, like any
non-deterministic stage — D7); the per-chunk worker is idempotent on content-hash + extractor version
(D12). Drops become auditable and recoverable (a better prompt re-examines only the drop set), and the
eval metrics come for free.

**Context.** The same durable-state discipline the resolution and supersession layers use, applied to
the extraction transcript. (C8.)

## D34. E2 Selection is the value filter — there is no pre-extraction value gate

**Decision.** Junk-control lives at the **proposition grain**, in-call: Selection (D31) decides
**verifiability** — not relevance (handled by K2 scope views, D16) and not ambiguity (the
disambiguation step). Together with **D2** redundancy-collapse (duplicate facts → one relation +
`evidence_count`) and exact-content-hash idempotency (D12), this replaces the pre-extraction value/
salience gate, which is **not built** (D25). Selection's metrics stand alone.

**Context.** The chunk-level value gate (former D26–D30) was over-engineered for a ~1.5–2× lever and
concentrated the worst correctness risk; the in-call verifiability filter is cheaper, safer, and
ablation-proven. (D25; value_gate_research; claimify_research C4.)

## D35. Selection recall envelope (defer-don't-DROP, one grain down)

**Decision.** Because a Selection drop is a hard delete with no second-copy net for a uniquely-attested
fact, Selection biases **conservative KEEP**; protects **never-drop classes** (quantities, dates,
named-entity + predicate, change-of-state language) regardless of phrasing; offers a low-confidence
**`kept_flagged`** outcome (mark-for-review, not delete); records all drops in the D33 ledger for
version-filtered re-examination; and is tuned against **per-fact** false-drop (canary CI), never a
corpus average.

**Context.** Mirrors the recall-conservative discipline the dropped gate carried (former D29), relocated
to the grain where junk is actually identifiable. (C4; D33.)

---

> **D36–D40 provenance.** D36–D40 formalize the E0 (document layer) + corpus-filesystem analysis
> (`_feature_planning/e0/` — Claude + Codex). Binding design: `plan/designs/e0_files_design.md`.
> Numbers/choices are starting points to measure (CLAUDE.md), not committed constants.

## D36. E0 is the document layer — a chain of idempotent sub-workers, not a renumber

**Decision.** E0 stays a single product layer (*files / structured document*) implemented as a short
chain of separately-idempotent, separately-observable sub-workers: **ingest** (store raw + hash) →
**convert** (raw → Markdown) → **structure** (PageIndex tree + roles + spans + summaries + placement
hint) → **crossref** (citations / document links). PageIndex post-processing is **not** promoted to a
top-level stage; E1/E2/E3 are **not** renumbered.

**Context.** The E-numbers name *product layers* (files → chunks → claims → relations); PageIndex
structure is metadata *about the document*, before chunking, so it belongs to E0. Renumbering would
churn every doc that references E1–E3 for no architectural gain (the L→E rename cost is the cautionary
precedent). Each sub-worker keys idempotency on `content_hash + its own version` (D12) so a single
config change doesn't rerun the whole chain.

**Consequences.** E0's output contract is unchanged (durable artifacts + queryable structure, ready
for E1). Operational complexity is handled by decomposition, not numbering.

## D37. E0 storage split — GCS holds bodies, Postgres holds the index; ID-addressed; mount-ready

**Decision.** Two GCS buckets per deployment: a **raw** bucket (immutable originals, cold, strict
IAM, **never mounted**) and an **artifacts** bucket (Markdown + `pageindex.json` + conversion
sidecars, standard storage, reachable from the mounted corpus filesystem). Canonical objects are
**ID-addressed** (`doc_id` + `content_hash`), never title-addressed. **Postgres never stores document
body/Markdown text** — only compact query-critical metadata (identity, versions, state, artifact
URIs, hashes, costs, and the section index: titles/paths/roles/spans/summaries). `content_hash`
(sha256 of raw bytes) is the idempotency key (D12) and the only surviving dedup (idempotency, not a
value tier — D25).

**Context.** Postgres is the E-plane ledger; GCS is the blob store. Storing 1M document bodies in
Postgres bloats it for nothing and puts text where agents can't mount it. The precise rule (bodies in GCS, queryable metadata in Postgres) keeps the spine queryable while the
text lives where it can be mounted.

**Consequences.** Postgres stays lean; the artifact store is mount-friendly (D40); a converter
change re-converts by version (D7).

## D38. Configurable raw → Markdown conversion module

**Decision.** A pluggable, **configurable** conversion module (a reusable open-source library):
interface `convert(bytes, mime, hints) -> { markdown, blocks[] }` where `blocks` carry **page +
character offsets back to the source** (load-bearing for E2 grounding D32, chunking, PageIndex). A
**router** selects a converter by input type per-deployment config (digital PDF → text extract;
scanned/complex PDF + images → OCR e.g. Mistral OCR; office/html/email → markitdown; text →
passthrough). **Versioned** (`converter_version`): a converter/routing change re-converts affected
docs and rebuilds downstream.

**Context.** Conversion quality gates the whole pipeline, so it is pinned and reprocessable.
Generalizes common practice (Mistral OCR for PDFs, markitdown elsewhere) into a routing table. (User
proposal.)

## D39. PageIndex provides per-document structure — sidecar + PG index, structure-only, summaries kept, placement-hint-extended

**Decision.** PageIndex builds a per-document hierarchical tree (`node_id`, `title`, `summary`,
nested nodes, spans). It is used as **structure, not a retrieval engine** (we keep chunk + embed +
graph, D8/D9). Stored **both** as a `pageindex.json` sidecar (artifact) **and** a Postgres
`document_sections` index (queryable path/role/span per chunk for E1/E2). **Per-section summaries are
kept** (cheap, per-section) as **context never facts** — feeding E1 prefixes, navigation, and
selection-explainability; the corpus's *global* high-level picture remains the K plane's job, so it
never depends on summary quality. The PageIndex output is **extended with a `placement` hint**: a
proposed path for the document (and key sections) in the corpus's hypothetical directory tree —
advisory input to the P3 projection (D40), not a commitment.

**Context.** Structure is load-bearing (section-aware chunk boundaries + the E2 role signal); summaries
are cheap polish worth measuring, not deleting on intuition. The placement hint lets E0 seed the
corpus filesystem (P3, D40) — a per-document path guess produced where the document is freshly
understood, reconciled into a coherent tree by the projection.

## D40. P3 — the corpus filesystem: a mountable, rebuildable projection

**Decision.** The system builds a **canonical corpus filesystem** (a published navigable view, no source-of-truth): a materialized **GCS bucket
laid out as a directory tree** organizing the whole corpus for agent navigation, **mounted read-only**
to agentic workers (`gcsfuse`). It is a **P-plane projection** (P3) — derived, holds no
source-of-truth, **rebuilt from Postgres + document artifacts**, like P1/P2. A projection worker
materializes/maintains the tree from the **placement hints** (D39) + entities/relations + the K-plane
structure: folders by topic/source/time/entity, leaves linking to per-document artifacts, a generated
`_index.md` / `llms.txt` at each level. K (compiled understanding) and P3 (navigable index over
sources) cross-link and compose; they are not duplicates.

**Context.** Agentic consumers need to browse the memory as a filesystem, which requires a navigable
corpus tree. Cross-document organization is a function of evolving knowledge, so it must be a
**rebuildable projection** (P3), not E0 state — per-document structure is E0 (intrinsic), corpus
organization is P3 (derived). Realizes the "extend PageIndex with placement → projection materializes
a mounted bucket tree" design.

**Consequences.** Agents browse a stable, navigable hierarchy and drill into raw sources; the tree
reorganizes as the corpus grows without touching truth (placement hints are inputs). New projection in
plane P alongside P1 (search) and P2 (graph).

---

## D41. Claims carry an immutable, source-asserted validity interval (asserted vs. adjudicated time)

**Decision.** A claim gains a structured **world-time interval as the source asserted it** —
`claim_valid_from` / `claim_valid_until`, plus a `claim_valid_precision` (year/quarter/day/…/open/
unknown) and a `claim_valid_kind` (proposition-validity vs. event-time vs. measurement-period). It is
the structured form of the date decontextualization already resolves into the claim text ("launched
*in 2024*"), emitted in the same E2 call and **grounded** by the existing window-membership check (the
date must verbatim-exist in the bundle, D32). It is **evidence about *when***, epistemically identical
to `claim_text` (evidence about *what*) and `source_span` (evidence about *where in the source*).
Adjudicated, current-belief validity stays **exclusively on relations** (`valid_from`/`valid_until` +
`invalidated_at`, D3).

**Why this is not a second validity authority** (stated so a future reader need not re-derive it).
Three *mechanical* properties — not the `_asserted_` naming — keep claim-validity from competing with
the relation window:

1. **Immutable** — no `UPDATE` path, no `invalidated_at`, no `status`, no `superseded_by`. A column
   that cannot be revised cannot be "current belief."
2. **Many-valued per fact** — N sources may assert N different, even contradictory, windows and *all
   stand forever*. Many-valued-by-source is the signature of *evidence* (like `evidence_count`'s N
   rows); a belief authority is single-valued-by-fact.
3. **No fact-identity** — keyed only by `claim_id`, never addressable as "the validity of fact F," so
   it structurally cannot answer "fact F is true at T."

So D3's "absurd task" never returns: a contradicting source makes a **new** claim with its own
immutable window; nothing ever closes an existing claim's window. The relation adjudicator **may
consult** `claim_valid_*` as one evidence input (better than re-parsing claim text) but the relation
window stays its *computed, recorded, monotonic* verdict — never a reduction over claim columns, never
read back to override the verdict, never reopened by a late-arriving retrospective.

**Context.** World-validity windows previously lived only on relations, but **many claims yield no
relation by design** (D2: n-ary facts; single-entity / attribute facts; literal- or quantity-object
facts like "revenue was \$5M in FY2023" — objects must be entities and time is never a value, D18). For
those, the fact's world-time survived only inside NL claim text, unqueryable. An immutable asserted
interval on the claim closes that gap without a Date-node, a literal-object relation, or claim
supersession. Converged recommendation of an independent Codex analysis, a four-angle internal design
workflow, and an adversarial "amend-the-decisions" review — the last of which, tasked to argue *for*
restructuring, concluded the claim/relation split, D6, and relation-only supersession should all stay.

**Consequences.**
- New evidence-grain retrieval: a `claims_as_of(t)` search recipe answers "what did sources assert held
  over T," over Lance scalar columns, zero LLM (D9). Belief-as-of stays relations-only (D10); the recipe
  registry/linter **bars** `claims_as_of` from answering "currently true."
- The relation adjudicator gets structured temporal inputs (a claim "Alice joined in March 2024" can
  seed `works_for.valid_from`; "Alice left in January 2026" can seed closure) instead of re-parsing
  text — with a monotonicity guard so a late retrospective cannot move an adjudicated window.
- **Refines D3 and D6 in wording, not substance**: claims may carry an *immutable* interval, never a
  *revisable* one; validity-as-current-belief still has exactly one home. **Compatible with D18** —
  the interval lives on the claim, not as a relation object/predicate or Date-node (D18 governs
  relation/edge time and is untouched).
- **Residual non-goal (documented):** two sources asserting *incompatible* windows for a
  **non-relational** fact both stand as evidence with no relation to host a contradiction/verdict;
  retrieval surfaces both. Structured *supersession of non-relational restatements* is **not** in the
  claims plane — a fact that needs an adjudicated current value is promoted to a relation (the D5
  `other:` funnel), or a future "E3 proposition-fact layer" is added. Recurrence ("every Q4") and
  un-datable anchor-events ("as of the merger") are out of the single-interval model; the documented
  upgrade is an expressivity child table (btree-indexed, D23-restamped), built only on measured demand.
  Full detail: `e2_e3_claims_relations_design.md` §5/§7, `postgres_schema_design.md` §8/§15/§17.

---

## D42. E0 records document origin at ingestion (external vs. system-generated)

**Decision.** Every input gets an immutable `origin` stamped at **E0 ingest** — at minimum
distinguishing **external** (came from outside the system boundary) from **self/system-generated**
(produced by this deployment's own agents or workers — e.g. an email an operating agent sent).
Capture only; no consuming logic is built now.

**Context.** Provenance — "did this document come from the world, or from us?" — is knowable *only*
at the moment of ingestion; once a document is chunked → claimed (E2) → related (E3), self-generated
and external assertions are indistinguishable. The motivating case is a closed agent-driven loop where
the system's own outputs are re-ingested: without an origin stamp, an agent's own assertions inflate
`evidence_count` (D2) and entrench beliefs (K3) as if independently corroborated — a silent
self-confirmation loop that corrupts the corpus's headline confidence signal. This is the one piece of
that scenario with a **capture-now-or-lose-it** asymmetry; everything else it raises (operational-state
scopes, an E→K signal/interrupt channel, decision↔evidence-snapshot links) is additive later and is
**deliberately deferred** until an agent-operations loop is actually built.

**Consequences.** A small, mandatory E0 metadata field (extensible to richer origin classes and
per-action lineage grouping when needed). The intended first consumer — confidence/belief math that
counts *independent external* evidence rather than raw `evidence_count`, discounting self-generated
echoes — is a **documented non-goal for now**, unblocked by this capture. No change to D2/D3/D6.

**Refined by D45–D47 (the K trigger surface).** One of the deferred items — the **E→K
signal/interrupt channel** — is now designed, its condition met (an agent-operated deployment is a
named target): routing-rule **subscriptions** with a **dispatch** consequence invoke registered
agentic workflows with debounced, delta-carrying payloads; page-level watches serve authored
consumers (`k_layers_design.md` §5). Origin capture itself is unchanged, and it is what keeps the
resulting loop non-circular — a re-ingested plan is stamped system-generated and never counts as
independent external evidence. The other deferred items (operational-state scopes,
decision↔evidence-snapshot links) remain non-goals.

---

## D43. Two canonical layers — typed relations for the graph, an untyped entity-anchored observation layer for non-graph facts; supersession by entity-blocking + adjudication

**Decision.** Plane E keeps **two** canonical fact layers, split by what they *are*, not merged:

1. **Relations** (unchanged, D2–D5/D18) — distinct **entity→entity** facts with a *governed predicate*.
   Typed because a graph needs typed edges; this is the only layer that projects to P2 (the graph).
2. **Observations** (new) — facts asserted about **one entity** whose object is a *value or a statement*,
   not another entity ("Acme's headcount is 600", "Acme's FY2023 revenue was \$5M"). An observation is
   **anchored to a resolved entity** and is **not typed by any governed attribute vocabulary**. It
   carries the same **bi-temporal** validity windows as a relation, so non-relational facts finally get
   first-class temporal validity and supersession (the gap relations-only left).

**The slot is found, not declared.** Supersession/contradiction among observations reuses the exact
pattern relations already use — *blocking + cheap-first adjudication* (D4) — but blocks on the
**resolved entity** (an exact key) instead of a `(subject, predicate)` pair: a new value-claim about
entity *E* → fetch *E*'s live observations (indexed; exhaustive for that entity) → for a hub entity with
many, narrow by **semantic similarity** over the observation label (P1/Lance) → the adjudicator decides
per candidate (each gated on a **positive same-thing match** judged *semantically* from the `statement` —
same property, and for a period figure same period and value-compatibility — exactly as relations judge
"same predicate", with **no typed value/period column**): **supersede** (cap the prior `valid_until` at
the new `valid_from`), **contradict/coexist** (same property + same period, incompatible value → both
stand, shared `contradiction_group`), **evidence** (same property + value → add evidence, collapse
redundancy), or **new**. The **no-cap rule** carries the period distinction without a column:
`valid_from`/`valid_until` is the **world-validity of the belief**, and only a **changing effective
state** (headcount/balance/status) is ever capped; a **measurement / fixed-period figure** ("FY2023
revenue") is **never** capped — it doesn't stop being true at period-end, its window stays open, and a
conflicting same-period figure coexists. The conflict slot is `entity + same-property + same-period`, all
matched semantically (FY2023 *revenue* \$5M vs \$7M conflict; FY2023 revenue vs FY2023 *profit*, or FY2023
vs Q1-2023, do not). The "never silently resolve" property is a
**binding adjudicator contract** (supersede only on a positively-matched prior above an explicit margin,
with a persisted reason; otherwise coexist) **plus an eval gate** — not a schema invariant. The design is
explicit that this is policy, and that it fails toward *duplicate coexisting rows*, never silent
overwrite.

**Context.** Non-relational facts (values, measures, single-entity properties) need temporal validity
and supersession — relations couldn't hold them (a relation's object must be an entity), and surfacing
them statelessly is information-lossy. Two fuller alternatives were explored and **rejected** (their
work is preserved in closed PRs, not on main):
- *A unified, typed `facts` table* (one table for entity- and literal-object facts, supersession gated
  by a registered relationship type + a governed `value_domain`/`cardinality` vocabulary). Rejected:
  it merges graph and non-graph data under one roof — a heavy mental model — and the per-attribute
  typing (`value_domain`, `unit_dimension`, `cardinality`) must be LLM-inferred, is brittle, and adds
  registry-maintenance cost. The typing existed only to make literal supersession *schema-enforced*; if
  supersession is adjudicated (as relations always have been), the typing is unnecessary.
- *Mutating claims to carry validity.* Rejected (D3): it destroys the immutable evidence record and
  faces the "absurd task" of closing every prior claim. The observation row is the right unit of
  supersession — one window closes, N immutable claims stay as evidence.

The **D6 "one belief home"** objection does **not** apply to two tables here: a relation and an
observation can never represent the *same* belief (entity-object vs value-object are disjoint), so they
cannot drift against each other the way a relation and a duplicate "proposition-fact" could. Two
disjoint canonical layers, not one polymorphic table, is the simpler correct shape.

**Consequences.**
- **Relations are untouched** — typed, governed, graph-projected, with their existing `(s,p,o)` blocking
  and overlap-EXCLUDE.
- **Observations are deliberately lean** — entity-anchored, bi-temporal, evidence-linked. The value and
  any reporting period live in the NL `statement` (matched semantically); there is **no governed
  attribute registry, no `value_domain`/`unit_dimension`/`cardinality`, no structured value/period
  column, and no typed EXCLUDE.** Supersession is the adjudicator's job (CI-gated), not a schema
  invariant. (A structured `value` for cross-entity numeric range scans is an additive change if that
  need ever becomes real — deliberately omitted now.)
- **No semantic-clustering recall hole.** Because observations are anchored to a *resolved entity*
  (exact key), every prior observation about that entity is found by the exact block — semantic search
  only *ranks* candidates for a hub entity; it never gates membership. The only residual fuzziness is
  the supersede-vs-coexist *judgment*, which fails safe to coexist.
- **Retrieval is through projections** (D9): observations are embedded in P1/Lance (semantic + value
  search; entity-anchored timelines); they **never** enter the P2 graph (D18 holds — a value is not a
  node). The canonical layer is storage; projections serve queries.
- **Claims stay immutable** (D2/D3), entity-linked (mentions), with asserted validity (D41) feeding an
  observation's initial window.
- The "never silently resolve" guarantee moves from a (would-be) schema gate to an **adjudicator
  fail-safe + eval gate** — the rigor lives in E3/eval, not the DDL.

Design: `plan/designs/observations_design.md`. Schema: `postgres_schema_design.md` §9.A. Normalization:
`e2_e3_claims_relations_design.md` §5. Open items (qualitative/opinion belief — still an *upstream* E2
question; the enforcement dial) tracked in `questions.md`.

---

## D44. The P2 projection contract — Postgres `v_graph_*` views are the LadybugDB COPY boundary; merge-redirect + keep-retracted + casts live in Postgres

**Decision.** The Postgres→LadybugDB (P2) projection is defined by a set of read-only **Postgres views**
(`v_graph_entities`, `v_graph_documents`, `v_graph_relates`, `v_graph_mentioned_in`, `v_graph_crossref`,
`v_graph_is_document`, + the shared `v_graph_survivor`) — `postgres_schema_design.md` §10.A. The LadybugDB
side is then a trivial `COPY <T> FROM SQL_QUERY('pg', 'SELECT * FROM v_graph_<t>')` (or the same view via
the Parquet hop). The graph model is **one `Entity` node + one `Document` node**, and **one generic
`RELATES` rel table with `predicate` as a property** (+ structural `MENTIONED_IN`, `DOC_CROSSREF`,
`IS_DOCUMENT`) — *not* per-type node tables or per-predicate rel tables (the vocabulary is governed,
extensible registry data, not DDL; D5/D15/D18). Entity ids stay native **`UUID`** primary keys.

**Context.** A full multi-agent analysis (Codex + Antigravity, both source-verified against the LadybugDB
tree, + an internal multi-angle workflow, both review rounds) confirmed the Postgres structures transfer
**cleanly** *because* the graph is a dumb projection (D6): it inherits outcomes (a believed
`(subject, predicate, object)` fact + validity windows), never constraints — so generated columns, EXCLUDE
arms, composite FKs, and the D18 domain/range signatures correctly **stay in Postgres**. The transfer
reduces to three mechanical transforms (cast `timestamptz` → naive UTC; cast Postgres ENUM → text; drop
graph-irrelevant columns) — which belong in the **views**, the single auditable boundary. Full record:
`plan/analysis/ladybug_translation_research/SYNTHESIS.md`.

**Consequences.**
- **Two correctness rules the projection MUST obey** (a naive `WHERE status='active'` projection is
  *wrong*): (1) **merge-redirect** — `entities.merged_into` is a redirect, not a rewrite, and relations
  are not re-pointed in PG, so endpoints must be recursively resolved to their surviving entity (cycle-safe;
  a pre-snapshot validation gate aborts on cycles/dangling endpoints) or every edge touching a merged
  entity is silently dropped; (2) **keep retracted edges** within a retention window for *transaction-time*
  as-of (not `invalidated_at IS NULL`), while **aligning node/edge retention** — an edge whose endpoint was
  retired/forgotten (§13) is dropped (its endpoint can't be a node). Parallel edges (distinct `relation_id`)
  are preserved, never blind-`DISTINCT`-collapsed (same-(s,p,o) collapse is E3's job, D43).
- **`observations` and claims never project** (D43/D18): a value is not a node, and a LadybugDB REL
  endpoint must be a node table — the engine rule and the design rule are the same constraint.
- **As-of (refines D10).** LadybugDB has no native temporal semantics, **and you cannot `MATCH`-traverse a
  projected graph** — `PROJECT_GRAPH[_CYPHER]` feeds GDS algorithms only (it is `(STRING,STRING)`; there is
  no `MATCH … IN GRAPH`). As-of is therefore **inline path-predicate filtering** (`WHERE all(r IN rels(p)
  …)`) for correctness, or a **materialized persistent `CREATE GRAPH`/`USE GRAPH`** for heavy/repeat
  analytics. D10's "as-of via projected graphs" holds for *algorithms*, not path traversal — note added.
- **Transport.** `COPY <Node|Rel> FROM SQL_QUERY('pg', …)` is verified, but the **committed transport
  stays the Parquet hop (D7)** until cross-DB attach throughput at 10⁷–10⁸ rows is measured; both
  transports consume the same views. Graph-derived metrics (`pagerank`/`graph_degree`) are computed
  post-load (D11), never reprojected.
- **Spikes** (none blocking): UUID-PK smoke test on the deployed build; attach scan-pushdown/throughput;
  the merge-recursion cycle gate; inline multi-hop path-filter performance. Tracked in `questions.md`.

---

> **D45–D47 provenance.** D45–D47 formalize the plane-K design (July 2026), triggered by the
> second step-back review (`plan/analysis/design_review_2026_07.md`, F1) and the K-plane design
> discussion it opened; they **accept objections O2 and O4** (`plan/analysis/objections.md`).
> Binding design: `plan/designs/k_layers_design.md`. Numbers/thresholds are placeholders to be
> measured (CLAUDE.md).

## D45. Plane K compilation is planned and manifest-driven — planner / writer / driver replace free agent sessions

**Decision.** The K plane is produced by a compile system with three roles: a **planner** (LLM)
that owns *structure* — which pages exist and each page's **routing rules**, recorded as
append-only `knowledge_plan_decisions`; **writers** (LLM — Codex/OpenCode, optionally full agent
sessions with retrieval tools) that own *content* — one writer per page per cycle, full creative
latitude; and a deterministic **driver** that computes staleness, schedules writers in dependency
order (a scope's shared model page first, children before parents, the root index last), validates
outputs, and is the repo's **only automated committer**. Routing rules are **mechanical** — a
closed kind set (`entity`, `entity_subtree`, `predicate_beat`, `community`, `doc_set`,
`scope_interests`, `manual`) evaluated by SQL over keys plane E already produces (canonical
entities, governed predicates, D11 communities, document metadata) via an inverted key index; an
LLM never decides routing at evidence-arrival time. **Citations are a binding writer output**
(recorded in `knowledge_artifact_evidence`, uncited candidates counted). **Staleness is
mechanical**: a page is stale iff its recorded `inputs_hash` (candidate evidence IDs + validity
fingerprints + curation + child summaries + prompt/model version) no longer matches — computed,
never guessed. In-session merge-conflict retry and the hot-file rolling-window worker are
**removed** (refines D12); the semantic linter is demoted from staleness detection to prose
quality assurance.

**Context.** The prior mechanism (concurrent sessions editing shared files) left the two
load-bearing steps — routing new evidence to pages (`knowledge_refresh_queue.artifact_id` NULL =
"decide which at processing time") and deciding which pages exist — as unrecorded, per-cycle LLM
improvisation, then added contention machinery to survive its consequences. It also made "is this
page stale?", "which pages does this deletion touch?", and "is coverage complete?" undecidable,
because the compile's read set was never recorded. Plane K was the only non-deterministic stage
whose decisions were not durable state — this applies D33's ledger discipline (extraction ledger,
adjudication transcripts, resolution decisions) to the last holdout. Routing rides on E-plane
labels, so it costs no new intelligence and zero LLM calls (the D9 rule, applied to the routing
path). **Accepts O4** (input manifests / semantic regenerability).

**Consequences.** Staleness, deletion reach, and incremental refresh become SQL ("recompile only
summaries whose referenced claims changed" is now exact); contention is structurally impossible
(disjoint writes + one committer); every compiled page carries freshness provenance (feeds the
mixed-freshness story); K cost scales with dirty pages; planner structure decisions are
reviewable, blast-radius-gated state (D24 pattern). New control-plane tables in
`postgres_schema_design.md` §11. Full design: `k_layers_design.md`.

## D46. Two page kinds — compiled vs authored; the ownership contract narrows K's precious surface to human-authored content

**Decision.** Every K artifact is one of two kinds. **Compiled** pages are evidence-derived:
machine-owned body, regenerated by their writer when stale. **Authored** pages are first-class
human/agent-authored content (target states, designs, decisions, position papers): **never
auto-regenerated**; when evidence they cite changes they receive a **review flag**, not a
rewrite. Both kinds carry citations; authored pages declare them (plus optional **watch rules**
— routing rules whose consequence is a flag) in frontmatter the driver syncs to Postgres. Human
input to compiled pages lives in a per-page **curation sidecar** (pins, exclusions, corrections,
guidance) — a first-class compile input whose enforceable subset is enforced mechanically. A
direct human edit to a compiled body is detected (`content_hash` mismatch) and **quarantined**
into a proposed sidecar entry — never silently overwritten, never silently absorbed.

**Context.** Two forces. (1) Not all knowledge is derivable from evidence: a to-be architecture
or a mapping decision *is not compiled from claims* — it is authored content that must still know
what evidence it stood on (the migration deployment's as-is/to-be case). (2) D1's "the git repo
is not reproducible" over-scoped the precious surface: compiled pages are semantically
regenerable from the spine + recorded inputs; only human words are irreducible.

**Consequences.** Backup criticality concentrates on authored pages + sidecars (refines D1). The
deletion cascade reaches K mechanically: compiled pages recompile without removed evidence,
authored pages flag for the author (the system never rewrites human words, even to forget); the
hard-forget residual is git *history* erasure, named in `k_layers_design.md` §10. Authored
decisions get automatic invalidation alerts when the ground under them moves — "contradictions
are surfaced, never silently resolved" extended to the knowledge plane.

## D47. One compilation mechanism, N scopes — K1 is the default scope, K3 is the belief tier (accepts O2)

**Decision.** Plane K runs **one mechanism**; K1/K2/K3 survive as *content tiers*, not separate
machinery. **K1** = the default scope (entity pages, topic/community pages, source digests, the
root index). **K2** = additional purpose scopes — each a git subtree + registry rows (D16),
each with a **shared model page** (vocabulary + domain shape) that is a declared compile input of
every page in the scope (cross-page coherence). **K3** = the belief tier: compiled pages under
stricter configuration — rules select only settled evidence (`evidence_count ≥ N`, no live
`contradiction_group`; N is a placeholder to measure), updates are evidence-gated (never
timer-driven), and every belief cites supporting **and** contradicting evidence. The separate
`k3_beliefs_design.md` is folded into `k_layers_design.md`.

**Context.** Objection O2: by mechanism, K1/K2/K3 were one thing (compile evidence → git
markdown) wearing three names, and a layer must earn its existence with a distinct mechanism.
The belief tier's distinctness is *configuration* (evidence gating, mandatory dual-role
citations), not machinery — exactly O2's "curated view seeded from high-evidence,
zero-contradiction relations", now with a defined update rule. The "whose beliefs are these"
question stays open (`questions.md` #5) — the mechanism is agnostic to its answer; the answer
will configure it, not replace it.

**Consequences.** One pipeline to build and operate; "general" is just a scope; new scope = a
subtree + registry rows + rules (never new machinery). Dedicated K3 machinery would be justified
only by a use case the belief-tier configuration provably cannot express — a documented
alternative, not a plan. The tier layout itself is **configuration, not contract**: K1–K3 is the
shipped default; a deployment — including any user of the open-source library — may reshape,
rename, drop, or invent scopes and tiers freely. What is *not* configurable is the framework
contract: page kinds + ownership (D46), binding citations (D45), the single automated committer,
and the trigger surface's acyclicity ("knowledge structure is configuration, not machinery" —
the D15 principle one plane up; `k_layers_design.md` §2).
