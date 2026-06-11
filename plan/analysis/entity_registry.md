# Entity Registry & Ontology — Analysis

Deep-dive behind objection O5 (`objections.md`). Decisions logged from here: **D15**
(ontology: universal core + anchored extensions), **D16** (one graph, scope views). This
analysis seeds the future `../designs/registries_design.md`.

## 1. Why entity resolution is existential in this architecture

Entity resolution (ER) answers: *do these two mentions refer to the same real-world thing?*
It is load-bearing in three places:

- **The blocking key.** Supersession detection blocks on `(entity_id, predicate)` (D4). If
  "A. Novak" and "Alice Novak" resolve to different IDs, the supersession that should fire
  *silently doesn't* — no error, just a stale fact served as current.
- **Evidence aggregation.** Relations dedupe by `(s, p, o)` identity (D2). Split entities →
  split evidence → artificially low confidence everywhere.
- **The graph.** Split entities fragment neighborhoods; over-merged entities create false
  hubs that poison graph-distance reranking (D9).

**The asymmetry:** under-merging degrades quality gradually; over-merging poisons it
catastrophically (two people fused = every fact about either attributed to both; untangling
requires knowing which evidence belonged to whom). The discipline therefore tilts
conservative everywhere.

## 2. Field survey

| System | Approach | Lesson for us |
|---|---|---|
| **Cognee** | LLM extraction → fuzzy match (~80% cutoff) against user-provided OWL ontology → canonicalize to URI forms, `ontology_valid` flags, subclass enrichment; similarity-threshold dedup during `cognify()` | **Anchor outward**: match against curated authority sets, not only previously-seen entities. Cross-document ER itself is shallow there — threshold similarity only |
| **Graphiti / Zep** | At ingest: candidate retrieval (fulltext + embedding over entity names/summaries) → LLM adjudicates same-or-new; entity summaries evolve and improve future matching | Right *shape* (cheap candidates, expensive judgment last) but LLM-per-entity-per-episode is unaffordable at our scale and non-deterministic decisions are hard to audit/replay |
| **Senzing** (industry ER gold standard) | Principle-based, deterministic-first; incremental (new record resolves in real time); every merge records *why*; **reversible — un-merge on new evidence** | The three principles to adopt wholesale: incremental, explainable, reversible |
| **splink / dedupe** | Probabilistic record linkage (Fellegi–Sunter weights), batch | Good for backfill campaigns; wrong as the primary online mechanism |
| **Wikidata** | Persistent QIDs **never reused**; merge leaves a **redirect** (dead ID forever resolves to survivor); constraint-violation review queues | The governance model: IDs are promises; merges are redirects, not rewrites |
| **OpenAlex / Semantic Scholar** (author disambiguation) | Feature clustering (name+affiliation+coauthorship), persistent IDs, correction workflows | At millions of entities, errors are a permanent *operating condition* — design the correction workflow up front |

## 3. The registry moves over time — three kinds of movement, three mechanisms

Do not conflate these; the boundary errors are the most common KG corruption:

1. **Resolution drift** — *our knowledge of identity* improves: two records discovered to be
   one person (**merge**) or one record discovered to be two (**split**). Changes the
   registry, not the world.
2. **Alias drift** — surface forms evolve: nicknames, transliterations, married names,
   tickers. *Adds aliases* to an unchanged entity.
3. **World change** — Twitter renames to X; a startup gets acquired. **NOT a registry
   operation** — it's a *relation* (`renamed_to`, `acquired_by`) with a bi-temporal window
   in E3. The classic botch: "merging" Instagram into Meta because of the acquisition — they
   remain distinct entities forever; the acquisition is a fact *about* them.

Boundary rule: **the registry tracks identity; relations track history.** Rename is the
boundary case: same entity, new alias (registry) *plus* a rename-event relation (E3) — both.

## 4. Mechanism: the transcript/verdict pattern, again

Resolution decisions are adjudications — the same epistemological split as claims/relations
(D2/D3) applies verbatim:

```
mentions (immutable — the transcript)        entities (the registry)
  mention_id, surface_form, context,           entity_id  ← NEVER reused
  claim_id/chunk_id, doc_id                    type, canonical_name, status
        │                                      merged_into → redirect chain
        ▼                                      profile summary + embedding
resolution_decisions (append-only — the verdict)
  mention_id → entity_id, method (tier 0–5),
  confidence, resolver_version, decided_at, superseded_by

aliases: alias → entity, provenance, confidence, first/last seen
merge_events (append-only): survivor, absorbed, evidence,
  pre-merge membership snapshot  ← what makes UN-merge possible
```

Properties this buys, mapped to existing decisions:

- **Mentions never edited; resolution re-decidable.** A better resolver later = new decision
  rows superseding old ones (same versioning mechanics as embeddings, D12). Re-resolution
  campaigns are batch jobs, not migrations.
- **Merge = redirect, not rewrite** (Wikidata-style). Absorbed entity keeps its ID with
  `merged_into`; everything downstream that stored the old ID still resolves.
- **P2 rebuild synergy (D7):** merges and retypings become retroactively clean in the graph
  for free — the nightmare operation of incremental graph systems is a no-op here.
- **Un-merge is possible**: merge events snapshot pre-merge membership; per-mention decisions
  survive; who-belonged-where is replayable.
- **Single authority (D6):** all of this lives in Postgres only; Lance/Ladybug receive
  canonical IDs.

Resolution pipeline = D4's tiers plus one addition at the front:

- **Tier 0 — external authority match** (per entity type: DOI, ORCID, company registries,
  ISBN…): the cheapest *and* most reliable tier when it applies (Cognee's lesson,
  generalized).
- Tiers 1–5 as designed: exact → fuzzy (FTS-blocked) → phonetic → embedding → adjudication
  (small model, then frontier; humans for high blast radius).

## 5. Ontology: universal core + anchored extensions (D15)

Users define their own ontology per problem; the system ships a best-effort starting set.
Both ride the same registry machinery (D5) — the ontology is *content, not new machinery*.

- **Universal core, borrowed not invented**: ~8 entity types (`Person, Organization,
  Document, Place, Event, Concept, Project, Product`) and ~10–15 predicates, aligned with
  schema.org naming. Not aesthetic: **extraction LLMs have strong priors on schema.org
  vocabulary** — familiar names are a quality lever.
- **Extension rule — extend, never fork**: every user type declares a core parent
  (`ResearchPaper ⊂ Document`); predicates may too (`advises ⊂ related_to`). This one
  constraint keeps universal machinery working across custom domains: queries/blocking fall
  back to the core level; scopes ignorant of each other's types still see core parents;
  cross-scope queries don't fragment.
- **Domain/range constraints** on predicates (`works_at: Person → Organization`) — two type
  columns, not OWL — mechanically reject a whole class of LLM extraction hallucinations
  before they pollute E3, and sharpen blocking.
- **Prompts generated from the registry**: extraction/normalization prompts render from
  types + predicates + descriptions + examples. Defining a new scope = editing registry
  rows, not prompt engineering; prompt-version tracking (D12) captures ontology changes
  automatically.
- **Three speeds, one registry**: core (small, slow-moving, every element a commitment) →
  scope extensions (fast-moving, every element an experiment) → `other:<freetext>` escape
  (ungoverned, monitored — the promotion funnel; frequent `other:` predicates are the system
  reporting an ontology gap).
- **Deliberately not OWL**: reasoners, property chains, cardinality axioms add permanent
  tooling/mental cost; parent-links + domain/range replicate most benefits. An OWL ontology
  a user brings can be *imported into* the registry; we don't need to *be* OWL.
- Evolution costs under D7: adding types/predicates = inserting rows; retyping entities =
  retroactively clean in P2 after rebuild; only *splitting* heavily-used types/predicates is
  genuinely expensive — hence the small core.

## 6. Scopes and the graph: one graph, many lenses (D16)

Multiple K2 scopes (e.g. project tracking, team-member profiling) do **not** get their own
graphs. Separate graphs would re-fragment identity — the exact disease the registry cures —
and kill the cross-scope queries that justify a graph at all ("which team members worked on
projects connected to X?" spans both scopes).

Plane discipline: **K2 scopes are consumers of plane E, not owners of it.** A scope is a
perspective over shared evidence; it owns its compiled markdown, not facts.

What scopes get instead, in increasing order of weight:

1. **Ontology extensions** (D15): the scope's vocabulary is its *footprint in the shared
   graph* — predicates/types registered per scope, edges in the same `RELATES` table.
2. **Query-time scope views**: `PROJECT_GRAPH_CYPHER` (verified LadybugDB capability) builds
   the scope's filtered subgraph in-engine — one registry-declared view definition
   (scope → predicate/type list) per scope, zero extra infrastructure, always consistent
   with shared truth.
3. **Materialized per-scope snapshots** — *only if* a scope becomes hot enough that
   query-time filtering measurably hurts, or needs access isolation (team profiles are
   plausibly sensitive). Because P2 is rebuild-first (D7), this is trivial: the same rebuild
   emits an additional filtered snapshot. A second projection of the same truth — never a
   second graph.

Rule of thumb: **scopes multiply; truth doesn't.** New scope = git directory + registry rows
(types/predicates + scope-view definition) + extraction interests. Never = new database.

## 7. Quality processes (the boring, proven machinery)

1. **Labeled golden set before tuning anything** — a few hundred mention-pairs per entity
   type incl. *hard* negatives (same-name father/son). Every tier threshold tuned against
   measured precision/recall. (Where O5 meets O6.)
2. **Three confidence bands; only the middle costs money**: auto-accept / review queue (LLM,
   humans for high blast radius) / auto-reject. Band boundaries are versioned config.
3. **Review clusters, not pairs; never trust transitive closure** — A≈B, B≈C does not make
   A=C; use clustering that cuts weak edges; cluster-level review scales, pairwise queues
   don't.
4. **Blast-radius rule**: never auto-merge entities above a degree/evidence threshold.
   Wrongly merging two long-tail entities is a scratch; two hubs, a catastrophe.
5. **Continuous health metrics**: cluster-size distribution (emerging giant cluster =
   over-merge in progress), singleton rate per type (under-merge), unresolved-mention rate,
   merge-proposal acceptance rate (drift = thresholds drifting), alias-per-entity growth.
6. **Sampled human audits + canary entities** (known-tricky cases re-run per resolver
   version as regression tests).
7. **Reversibility as an invariant, not a feature**: every automated decision undoable by
   replaying lineage; anything that can't be undone goes through the review queue. At
   million-doc scale some fraction of decisions will be wrong forever — design for living
   with that.

Summary: **mentions are evidence, entities are verdicts, resolution is re-adjudicable,
merges are redirects, and quality is a measured pipeline property — not an extraction-time
hope.**

## 8. Open questions for `registries_design.md`

1. Exact seed core: final type list, predicate list, domain/range table.
2. Tier thresholds + band boundaries (needs the golden set first — O6 dependency).
3. Review tooling: CLI-first? Simple web queue? Where do merge proposals surface?
4. External authorities per type (tier 0): which ones at launch (DOI? ORCID? none?).
5. Multilingual aliases and transliteration handling.
6. Scope-view definition format in the registry (predicate list vs. Cypher fragment).
7. Coreference resolution engine choice (runs before extraction, feeds mentions).

## Sources

[Cognee ontologies docs](https://docs.cognee.ai/core-concepts/further-concepts/ontologies) ·
[Cognee ontology deep-dive](https://www.cognee.ai/blog/deep-dives/ontology-ai-memory) ·
[Keeping knowledge graphs clean](https://www.decodingai.com/p/keep-knowledge-graph-clean) ·
[Entity-resolved knowledge graphs](https://towardsdatascience.com/entity-resolved-knowledge-graphs-6b22c09a1442/) ·
[ER at scale: dedup strategies](https://medium.com/graph-praxis/entity-resolution-at-scale-deduplication-strategies-for-knowledge-graph-construction-7499a60a97c3) ·
[The rise of semantic entity resolution](https://blog.graphlet.ai/the-rise-of-semantic-entity-resolution-45c48d5eb00a) ·
[Neo4j: what is entity resolution](https://neo4j.com/blog/graph-database/what-is-entity-resolution/) ·
[Incremental multi-source ER](https://pmc.ncbi.nlm.nih.gov/articles/PMC7250616/) ·
[RudderStack: ER best practices](https://www.rudderstack.com/blog/what-is-entity-resolution/)
