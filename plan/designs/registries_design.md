# Registries Design — Entity Resolution, Ontology, Governance

The plane-E substrate that canonicalizes entities and predicates. Distills the registry
research (`plan/analysis/registry_research/SYNTHESIS.md`, R1–R10) and the entity-registry
analysis (`plan/analysis/entity_registry.md`) into binding design. Formalizes objection O5;
decisions **D15–D24** (and D4/D5). Numbers here are starting points to be measured on the
golden set (D22) / a corpus slice — not committed constants.

## 1. Role and scope

The registries are **cross-cutting substrate of plane E**, not a layer (D14): layers
*transform* (E0→E3), registries *canonicalize*. Two registries:

- **Entity registry** — maps entity *mentions* to canonical *entity IDs*; the identity
  authority for the whole system.
- **Predicate/type registry** — the governed ontology (D5, D15, D18): entity types, predicates,
  domain/range constraints, synonyms, scope ownership.

Why this is a first-class subsystem with metrics from day one (O5): resolution quality is
load-bearing in three places — the `(entity_id, predicate)` supersession blocking key (D4),
relation evidence aggregation (D2), and graph neighborhood/distance quality (D9). Failure here
is **silent**: a missed merge means a stale fact is served as current with no error. The
asymmetry governs every default — **under-merging degrades gradually; over-merging poisons
catastrophically** — so the system is recall-conservative and reversible throughout.

### Deployment model: one system, N independent instances

The system deploys as **independent instances**, one per problem domain — target deployments
include a personal assistant, the brain of an AI-native agency (development + marketing of
multiple online products), a data-migration project between enterprise systems for a
manufacturing company, and a knowledge engine for a law-related product. Rules:

- **Entity spaces are never shared across deployments.** D16's "one graph, one entity space"
  applies *within* a deployment; separate deployments are separate Postgres
  instances/schemas, separate registries, separate graphs (a client project's data and a
  personal assistant's data must never co-resolve).
- **Each deployment = the universal core (D18) + chosen extension packs (§4) + its own K2
  scopes.** The core is identical everywhere; packs and scopes are per-deployment choices.
- The multi-scope case *within* one deployment (e.g. the agency: multiple products as K2
  scopes over one shared entity space) is exactly D16's "scopes multiply, truth doesn't".
- **Language is a per-deployment property**: a deployment with Czech (or other
  inflected-language) corpora needs the multilingual matching of §5; English-only deployments
  do not.

## 2. Data model (Postgres — the single authority, D6)

The transcript/verdict epistemics of D2/D3 apply to resolution too: mentions are evidence,
entities are verdicts, resolution is re-adjudicable.

```
mentions (immutable — the transcript)        entities (the registry)
  mention_id, surface_form, normalized_lemma,  entity_id        ← NEVER reused
  context, claim_id|chunk_id, doc_id,          type (→ type registry), canonical_name,
  language, char_span                          status, merged_into (redirect chain),
        │                                       profile_summary, profile_embedding_ref
        ▼
resolution_decisions (append-only — the verdict)   aliases
  decision_id, mention_id → entity_id,               alias_id, entity_id, alias_text,
  method (T0–T4), confidence, features jsonb,        normalized_lemma, provenance
  resolver_version, decided_at, superseded_by        (source|llm_canonical),
                                                      confidence, first_seen, last_seen
merge_events (append-only — reversibility)
  merge_id, survivor_id, absorbed_id, evidence,
  pre_merge_membership_snapshot jsonb, decided_at, reversed_by
```

(No `external_ids` table — resolution is registry-self-contained, D20. If a *future*
deployment ingests structured data with its own authoritative keys (internal/domain IDs, not
3rd-party registries), those would attach as aliases or a per-deployment table — out of scope
now.)

Ontology tables:

```
entity_types(type, parent_type → entity_types, description, examples, schema_org_ref, status)
predicates(predicate, parent_predicate, subject_type, object_type, description, examples,
           synonyms[], status ∈ {core,extension,other,deprecated}, scope_id nullable)
scope_interests(scope_id, interest_type ∈ {entity_type,predicate,metadata,keyword}, value)
resolver_versions(resolver_version, tier_config jsonb, thresholds_by_type jsonb, configured_at)
```

Invariants: `entity_id` is **never reused**; a merge is a **redirect** (`merged_into`), never a
rewrite (Wikidata model) — everything downstream that stored the old ID still resolves; P2
rebuild (D7) re-points graph edges on merge/un-merge for free.

## 3. Resolution cascade — T0–T4, block-loose / decide-tight (D17)

One canonical cascade. Stop at the first confident match. **Registry-self-contained — no
3rd-party external-authority tier** (D20).

| Tier | Mechanism | Role | Where |
|---|---|---|---|
| **T0** | exact match on the canonical name form (LLM-emitted, §5) | decision | Postgres |
| **T1** | fuzzy blocking — `pg_trgm` GIN, recall-first low floor | **candidate generation, NOT a decision** | Postgres |
| **T2** | phonetic — Daitch-Mokotoff (`fuzzystrmatch`), **not Soundex** | candidate generation | Postgres |
| **T3** | embedding similarity, residue only | decision (mid band) | Lance (D8) |
| **T4** | LLM adjudication (small→frontier); human review for high blast-radius | decision (ambiguous band) | worker |

- **Thresholds are per-type, golden-set-measured, versioned** (`resolver_versions`), stamped on
  every decision. No threshold ships without a per-type P/R curve (D17, D22). The old JW≥0.92 /
  cosine≥0.88 are placeholders to overwrite.
- Blocking (T1/T2) sets a hard recall ceiling, so cheap tiers **escalate near-misses to T4**,
  never auto-reject — textual recall is mediocre and over-rejection is a silent hole.
- Coreference (D19) is resolved *inside the E2 extraction call* (all languages) so mentions
  arrive with referents already grounded — no dedicated coref model. Likewise, each mention's
  canonical/nominative name form is LLM-emitted at extraction (§5), feeding T0.

## 4. Ontology — universal core + anchored extensions (D15, D18)

- **Seed core (D18):** 8 entity types — `Person, Organization, Place, Document⊂CreativeWork,
  Event, Concept, Project, Product` — and the 14 core predicates below. `related_to` is the
  predicate-side core parent (the extend-never-fork anchor + permissive escape). Time is
  bi-temporal edge metadata, never a predicate/Date-node.

**Core predicates (the authoritative starting set — domain/range is the enforced signature):**

| # | Predicate | Domain → Range | Notes |
|---|---|---|---|
| 1 | `works_for` | Person → Organization | employment — change-prone (supersession) |
| 2 | `member_of` | Person → Organization | membership (boards, teams, clubs) |
| 3 | `affiliated_with` | Person \| Organization → Organization | looser tie — advisor, partner, alumnus |
| 4 | `founded` | Person \| Organization → Organization | origin — near-atemporal |
| 5 | `located_in` | Organization \| Place \| Event → Place | spatial — change-prone for orgs |
| 6 | `part_of` | X → X (same-kind) | mereology — org units, place containment, sub-projects |
| 7 | `authored` | Person \| Organization → Document | authorship — atemporal once true |
| 8 | `created` | Person \| Organization → Product \| Concept | creation beyond documents |
| 9 | `about` | Document \| Event → any | aboutness — what a thing concerns |
| 10 | `knows_about` | Person → Concept | expertise — people-profiling workhorse |
| 11 | `knows` | Person → Person | social graph |
| 12 | `participated_in` | Person \| Organization → Event \| Project | involvement |
| 13 | `works_on` | Person \| Organization → Project \| Product | active engagement — change-prone |
| 14 | `related_to` | any → any | permissive core parent (escape + extend-never-fork anchor) |

Multi-signature predicates list each allowed `(subject_type, object_type)` pair (Graphiti
`edge_type_map` shape); subtypes inherit a parent's signatures (D15). Schema.org property
mappings (the `schema_org_ref` column) get a spot-check before freezing (D18).
- **Extend, never fork:** every user type/predicate declares a core parent → blocking, graph
  queries, and cross-scope retrieval always fall back to the core level.
- **Domain/range enforced** exactly as Graphiti's `edge_type_map[(src,tgt)→[rel]]` — the only
  structural ontology gate any surveyed production system ships. Rejects a class of extraction
  hallucinations mechanically. **Not OWL** (no reasoners/cardinality/property-chains).
- **Prompts render from the registry** (types + predicates + descriptions + examples) — defining
  a scope is editing rows, not prompt engineering; captured by prompt-version (D12).
- **Three speeds, one registry:** core (slow, each element a commitment) → scope extensions
  (fast, each an experiment) → `other:<freetext>` escape (ungoverned, monitored — the promotion
  funnel). Frequent `other:` values are the system reporting an ontology gap.
- **Scopes share one graph and one entity space (D16):** a scope's vocabulary is its footprint
  in the shared graph; scope views are `PROJECT_GRAPH_CYPHER` projections declared in
  `scope_interests`, never separate databases.

### How an entity gets its type

Domain/range enforcement needs entity types, so they must be assigned — but this is *not* a
separate subsystem. Type comes free with extraction:

- **The E2 extractor emits the type** alongside the mention, constrained to the registry's type
  enum (8 core + enabled subtypes) — the same registry-rendered-into-the-prompt mechanism as
  predicates; a free-form type label is not allowed (it would fragment like ungoverned
  predicates).
- **A canonical entity's type = the majority / highest-confidence vote** across its mentions'
  types, stored on `entities.type`. Mentions of one entity almost always agree; no
  voting/metonymy machinery is needed — mentions of one entity almost always agree on type.
- **Domain/range (D18) validates relations against entity types.** A relation that fails is
  dropped — and is **re-derivable from its immutable claim** if the entity is later retyped, so
  no quarantine table is needed (claims are the durable record, D2).
- **Cross-mention type disagreement on the core type is a cheap over-merge signal** (Washington
  person/place ⇒ two referents likely merged) — logged for D24 review; a SELECT, not machinery.
- Low-confidence mentions abstain to the `other:` floor, **never** dumped into `Concept`
  (`Concept` is a positive type, not the unknown bin).

A fuller "typing subsystem" (a cascade with GLiNER/authorities, an append-only type-decision
ledger, a relation-quarantine table, elaborate vote reconciliation) was researched and
**deliberately scoped down** — the extraction LLM is already being called, so a cheap-first
typing cascade avoids a cost we already pay; the heavier options are recorded in
`../analysis/entity_typing_research/SYNTHESIS.md` to revisit only if the golden set (D22)
surfaces a specific failure.

### System-shipped extension packs — the "Work" pack

Extension packs are predefined, system-shipped sets of extension types + predicates a
deployment can enable as a unit. **Extensions are not second-class**: an extension type lives
in the same entity space, graph, ER machinery, and relations as core types — the tier is a
*governance* distinction (stability commitment, golden-set obligation), not a capability one.
Packs let work-shaped concepts be first-class entities from day one without burning core
slots or committing every deployment (e.g. the law engine) to them.

**Work pack** (for assistant / agency / project-management deployments):

| Type | Parent | Notes |
|---|---|---|
| `Task` | ⊂ Event | an intended occurrence with a lifecycle |
| `Decision` | ⊂ Event | a commitment made at a point in time |
| `Goal` | ⊂ Concept | a desired state — held, not occurring |

| Predicate | Domain → Range |
|---|---|
| `blocks` | Task → Task |
| `depends_on` | Task → Task |
| `concerns` | Task \| Decision → any |
| `decided_by` | Decision → Person \| Organization |
| `assigned_to` | Task → Person \| Organization |
| `pursues` | Project \| Organization → Goal |

The payoff for `Decision` is the bi-temporal machinery: a decision is *a fact that holds
until reversed* — its standing rides on relations with validity windows, so reversals are
ordinary supersession, "what was the standing decision on X as of March?" is an ordinary
as-of query, and stale decisions get zombie-fact protection like any other relation. K2
scopes still compile narrative decision-logs/task-boards — referencing these entity IDs (the
usual entities-feed-compilation pattern); the pack provides identity + graph linkage +
temporal validity, K2 provides synthesis. Neither replaces the other.

Anticipated future packs (defined when a deployment needs them, not before): legal
(`Statute/Ruling/Contract ⊂ Document`, `Jurisdiction ⊂ Place`), systems/migration
(`System/Module ⊂ Product`, `Requirement ⊂ Document`, `BusinessProcess ⊂ Concept`).

### Predicate watchlist & promotion rule

These predicates were considered for the core/Work pack and **deliberately held back** —
plausible but not yet proven. The default lives in claims (E2); promotion to a typed predicate
happens **on demonstrated demand, not intuition**: when extraction produces a matching
`other:<freetext>` value at volume (the D5 promotion funnel), the periodic review promotes it
into the appropriate pack with a tight signature. Adding one is a registry row; the cost of a
premature core predicate (prompt space, golden-set coverage, a split if it's wrong) is the
reason to wait.

| Candidate | Tight signature | Future home |
|---|---|---|
| `uses` | Organization \| Person → Product | systems pack |
| `reports_to` | Person → Person | work/HR pack |
| `owns` / `acquired_by` | Organization → Organization \| Product | business pack |
| `lives_in` | Person → Place | personal pack |
| `enables` | Concept → Concept (tight only) | research scope — guardrailed (see below) |

**Excluded on principle — `causes` and `enables` as general relations.** Causal predicates are
**not** admitted to the core, and `enables` only ever as a tightly-typed `Concept → Concept`
scope experiment. Three reasons: (1) **evidence aggregation fails** — causal claims rarely
repeat verbatim, so they produce thousands of `evidence_count=1` edges instead of a few
well-evidenced ones, and the mechanism that makes relations trustworthy never engages; (2)
**no supersession semantics** — a causal assertion isn't *ended* by an event (the bi-temporal
model), it is *contested by argument* and hedged/conditional, which is exactly what the claims
layer (E2) preserves and the relations layer discards; (3) **no domain/range bite** —
`causes: any → any` waves everything through the one structural gate we trust (D18
`edge_type_map`), and LLMs over-read causation ("leads to / drives / thanks to"), producing
hub nodes that poison graph-distance reranking (D9). The causal *content* is not lost — it
lives in claims, fully searchable with its hedges intact (P1); only graph *traversal over
causality* is forgone, which over LLM-extracted causal edges would be confidently wrong.
Admission ticket (if ever): a scope extension with tight domain/range, extraction gated to
causal-classified claims, and **exclusion from graph-distance reranking**.

## 5. Multilingual / inflected names — LLM canonicalization + deterministic matching tiers

Czech (and Slavic generally) declines names across ~7 cases → ~7 surface forms per name
("Jiří Puc" / "Jiřího Puce" / "Jiřímu Pucovi"), a direct attack on `(entity_id, predicate)`
blocking. Following the "per-mention understanding is free with extraction; at-scale matching
needs cheap tiers" principle (§4, D19), this is handled **without specialized ML models**:

- **Canonicalization is LLM-emitted at extraction** (no UDPipe/MorphoDiTa lemmatizer pass). The
  E2 extractor emits each mention's **nominative/canonical name form** alongside the surface
  form — the same free per-mention output as type and coref. The canonical form is stored as a
  first-class alias (`provenance=llm_canonical`); T0 exact match runs on it.
- **Residual variants are caught by the deterministic at-scale tiers** (these are cheap Postgres
  built-ins, not ML, and do what the per-mention LLM cannot — match against millions of existing
  aliases): T1 `unaccent` + `pg_trgm` (GIN), T2 `fuzzystrmatch.daitch_mokotoff` (UTF-8-safe,
  GIN-indexable — catches "Nowak/Novak"-class spelling/transliteration variants). Optional
  app-layer BMPM behind a flag only if D-M recall proves short. Transliteration handling only if
  a corpus is confirmed multi-script.
- **Coref is in the E2 call** for all languages (D19) — no dedicated multilingual model.

**Acceptance test:** measured reduction in missed-supersession rate on inflected-name pairs vs a
surface-form baseline. *(Open spike: whether LLM-emitted canonical forms are consistent enough on
inflected proper nouns, and D-M phonetic recall on declined names — measure on a Czech corpus
slice before trusting the multilingual path; no specialized model to fall back on, so the
deterministic tiers must carry the residual.)*

## 6. Clustering & reversibility (D21)

The resolution cascade (§3) only ever produces *pairwise* guesses — "mention A and mention B
are probably the same entity." This section turns those pairwise guesses into actual entity
*groupings* — cheaply, at scale, without catastrophic over-merging, and reversibly. Every rule
below exists because of one asymmetry: **over-merging (fusing two real entities) is catastrophic
and silent; under-merging (missing a match) is gradual and recoverable** — so the machinery is
deliberately paranoid in one direction.

**Never chain the guesses (no "transitive closure").** If the cascade says A≈B and B≈C, we do
**not** conclude A=C. Example: "Jim Smith"≈"J. Smith" and "J. Smith"≈"James Smith" — but Jim and
James may be two different people both abbreviated to "J. Smith". Each link is individually
reasonable; chaining them merges two real people, and a single weak link can fuse two large
groups. So chaining (the technical term is *transitive closure*) is forbidden — everything below
is how we avoid it.

**Gather loosely, then decide tightly (two stages).** (1) *Gather*: follow the pairwise links to
collect a rough candidate *blob* of mentions that are connected somehow (graph
*connected-components* — just everyone reachable via a match link). (2) *Decide*: inside the
blob, a stricter check looks at how similar the mentions actually are and **splits the blob into
the real entities** — so a Smith blob becomes "Jim Smith" (one entity) and "James Smith"
(another). That tighter check builds a similarity tree of the blob's members and cuts it at a
threshold, so each piece below the cut is one entity (*hierarchical agglomerative clustering
with a distance cut* — in practice dedupe's `linkage(centroid)` + `fcluster(distance)`). The
blob is only ever a *candidate pool*, never automatically one entity. (Community-detection
algorithms like Louvain/Leiden are for topic communities — D11 — and must never be used to
decide identity.)

**Cap runaway blobs (the "black-hole guard").** Occasionally a blob balloons to thousands of
mentions because one bad link or a generic name connected everything — almost always garbage,
and expensive to process. When a blob crosses a size limit, **raise the matching bar and
re-split it** rather than swallow the monster. ("Black hole" = an entity that sucks in
everything; the guard stops it.)

**Place new mentions locally, and independent of arrival order (incremental).** When a new
document adds a mention, we do **not** re-cluster the whole (million-entity) registry. We
re-examine only the small set of existing entities the new mention could plausibly be — its
blocking candidates, i.e. its *neighborhood* — and re-decide just that local pocket. Crucially,
we re-cluster the pocket **jointly**, rather than greedily gluing the new mention to its single
best match — because greedy attachment makes the result depend on **ingestion order**:

> if "R. Klein" arrives *before* "Robert Klein" has been seen, the only Klein in the system might
> be "Rachel Klein", so it wrongly attaches there; had "Robert Klein" arrived first, "R. Klein"
> would have joined Robert. Same documents, different *people*, purely from order.

Re-clustering the local neighborhood as a unit fixes this: when "Robert Klein" later arrives, his
neighborhood already contains "R. Klein", so the pocket is re-decided together and "R. Klein"
moves to Robert. This gives the **bounded cost of a local operation** *and* the **correctness of
a full re-cluster** — the same grouping no matter what order documents arrived in. (Technically:
re-resolve the *1-hop neighborhood* — the entities one match-link away from the new mention —
and look one link further only when the mention touches a *hub*, an entity already connected to
many others.)

**Keep every merge reversible.** Because over-merges are catastrophic *and* inevitable at scale,
every merge must be undoable. Three mechanisms, all in Postgres (the single authority, D6):
- resolution decisions are **append-only** — a better decision *supersedes* the old one
  (`superseded_by`); nothing is overwritten, so the full history survives;
- each merge records a **"before" snapshot** of which mentions belonged to which entity
  (`merge_events.pre_merge_membership_snapshot`) — to un-merge, replay the snapshot;
- a merge is a **redirect, not a deletion** (`merged_into`): the absorbed entity keeps its ID,
  pointing at the survivor (Wikidata-style), so undoing is just removing the redirect.

No OSS ER system (Splink, dedupe, Zingg, Graphiti) ships un-merge, so building it is genuinely
ours to do — and the P2 rebuild (D7) re-points the graph on every merge/un-merge for free.

**Distrust promiscuous signals (the "generic-identifier guard").** Some signals look identifying
but aren't — `info@company.com`, a placeholder, a very common name. If one alias suddenly links
to *many* distinct entities, that's a tell it is **generic, not identifying**: down-weight it
(stop trusting it as a match signal) and re-evaluate the merges it caused. (Senzing pioneered
this.)

**Blast-radius rule.** A merge's *blast radius* is how much it would affect if wrong — roughly the
combined size/connectedness of the two entities (their mention counts + graph degree). Never
auto-merge above a degree/evidence threshold — wrongly merging two
*hubs* is the worst case of all. High-impact merges are routed to human review (§8), ranked by
`expected_impact = blast_radius × (1 − confidence)`.

## 7. Governance — predicate promotion

A periodic job reviews frequent `other:<freetext>` predicates and either maps them to an
existing predicate or promotes them to a scope extension / the core. Promotion = inserting/
retyping rows; retyping is retroactively clean in P2 after rebuild (D7). **The one expensive
operation is *splitting* a heavily-used predicate** (D15 flags it; D7 retro-clean does not cover
splits cleanly) — hence start strict with a small core. *(Open: the promotion workflow owner +
the split cost are under-researched — registry SYNTHESIS G5.)*

## 8. Review tooling (D24)

**Build** a thin CLI cluster-review queue over Postgres (no OSS tool offers cluster-queue +
append-only reversible verdicts + provenance + blast-radius gating). Review **clusters, not
pairs**; route only the `expected_impact = blast_radius × (1 − confidence)` middle band to
humans; hub merges never auto-accept. Evidence panel borrows Splink's waterfall; 3-way verdict
ergonomics from Zingg; cluster-card-with-exclude interaction from OpenRefine. Every action
appends a reversible, provenance-stamped record to `resolution_decisions`/`merge_events`.

## 9. Scale & schema (D23)

- RANGE-partition `mentions` / `resolution_decisions` / `relation_evidence` (~10⁸ rows) by
  ingest month (`pg_partman`); **btree-only** on these hot tables (cap write-amplification).
  They are never fuzzy-scanned (queried by id/doc_id).
- Do **not** partition `entities`/`aliases` (≤10⁷, the blocking targets). GIN `gin_trgm_ops` +
  GIN `daitch_mokotoff(name)` on `aliases.normalized_lemma`; btree composite
  `(subject_entity_id, predicate[, object])` on `relations`.
- T0–T2 in Postgres; T3 embedding in Lance (D8); HNSW never in OLTP.
- **Row counts are contingent on the value gate (D25)** — size the load-test against *gated*
  volume.

## 10. Quality & evaluation (D22, O6)

- **Golden EVAL set** (unbiased, human-adjudicated): ~200 pairs/type (~100 hard positives incl.
  synthetic father/son/inflection/married-name + ~100 hard negatives; ~400/type for
  auto-merge-critical types); blocking-stratified positive over-sampling; **Wilson** CIs near
  p≈1. Held strictly separate from any future training set.
- **Per-tier metrics**, canary regression re-run per `resolver_version`.
- **Continuous health metrics:** cluster-size distribution (emerging giant cluster = over-merge),
  singleton rate per type (under-merge), unresolved-mention rate, merge-proposal acceptance rate,
  alias-per-entity growth.
- **Reversibility is an invariant:** any automated decision must be undoable by replaying lineage;
  anything that can't be undone goes to the review queue.

## 11. Open spikes (do before committing numbers)

1. **Golden-set labeling without circularity** — LLM-propose / human-verify loop; the denominator
   trap (recall needs ~370 true-positive pairs).
2. **LLM canonical-form consistency on inflected proper nouns + D-M phonetic recall** on declined names (no end-to-end
   Czech ER benchmark exists).
3. **Un-merge → bi-temporal supersession ripple** — confirm relation validity windows closed
   under a merged identity are correctly re-adjudicated on un-merge (this is where silent
   supersession failure lives; coordinate with the value-gate zombie-fact spike).
4. **Scale load-test** real mentions-per-doc, GIN index sizes, streaming throughput on a corpus
   slice (contingent on D25's filter rate).
5. **Predicate-promotion workflow + split cost** (G5).

## References
Decisions: D4, D5, D6, D7, D8, D9, D11, D15, D16, **D17–D24** (`decisions.md`). Analysis:
`plan/analysis/entity_registry.md`, `plan/analysis/registry_research/` (R1–R10, verify/,
SYNTHESIS.md). Concepts: `plan/analysis/concepts.md`.
