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
  method (T0–T5), confidence, features jsonb,        normalized_lemma, provenance
  resolver_version, decided_at, superseded_by        (source|lemmatizer|external_authority),
                                                      confidence, first_seen, last_seen
merge_events (append-only — reversibility)
  merge_id, survivor_id, absorbed_id, evidence,    external_ids
  pre_merge_membership_snapshot jsonb,               entity_id, authority (wikidata|openalex|
  decided_at, reversed_by                            doi|orcid|lei|…), external_id, confidence
```

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

## 3. Resolution cascade — T0–T5, block-loose / decide-tight (D17)

One canonical cascade (ends the prior tier-numbering drift). Stop at the first confident match.

| Tier | Mechanism | Role | Where |
|---|---|---|---|
| **T0** | external-authority match (D20) | accelerator (never gates) | connectors |
| **T1** | exact match on `normalized_lemma` | decision | Postgres |
| **T2** | fuzzy blocking — `pg_trgm` GIN, recall-first low floor | **candidate generation, NOT a decision** | Postgres |
| **T3** | phonetic — Daitch-Mokotoff (`fuzzystrmatch`), **not Soundex** | candidate generation | Postgres |
| **T4** | embedding similarity, residue only | decision (mid band) | Lance (D8) |
| **T5** | LLM adjudication (small→frontier); human review for high blast-radius | decision (ambiguous band) | worker |

- **Thresholds are per-type, golden-set-measured, versioned** (`resolver_versions`), stamped on
  every decision. No threshold ships without a per-type P/R curve (D17, D22). The old JW≥0.92 /
  cosine≥0.88 are placeholders to overwrite.
- Blocking (T2/T3) sets a hard recall ceiling, so cheap tiers **escalate near-misses to T5**,
  never auto-reject — textual recall is mediocre and over-rejection is a silent hole.
- Coreference (D19) runs *before* resolution to ground pronouns into mentions: inside the E2
  call by default (English), as a dedicated multilingual CorefUD pre-pass for Czech/Slavic;
  output is candidate mention-links only.

## 4. Ontology — universal core + anchored extensions (D15, D18)

- **Seed core (D18):** 8 types `Person, Organization, Place, Document⊂CreativeWork, Event,
  Concept, Project, Product`; 14 predicates with subject/object types:
  `works_for, member_of, affiliated_with, located_in, part_of, authored, created, about,
  knows_about, knows, participated_in, works_on, founded, related_to`. `related_to` is the
  predicate-side core parent. Time is bi-temporal edge metadata, never a predicate/Date-node.
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

## 5. Multilingual / inflected — work package WP-ML (D19, R3)

Czech (and Slavic generally) declines names across ~7 cases → ~7 surface forms per name, a
direct attack on `(entity_id, predicate)` blocking. Intake stage:

1. language-detect per mention → 2. lemmatize names to nominative (UDPipe2/MorphoDiTa for cs;
Stanza/spaCy tail) → 3. store the lemma as a **first-class alias** (`provenance=lemmatizer`) →
4. T1 exact runs on the lemma → 5. T2 `unaccent`+`pg_trgm`, T3 `fuzzystrmatch.daitch_mokotoff`
(UTF-8-safe, GIN-indexable; optional app-layer BMPM behind a flag) → transliteration only if the
corpus is confirmed multi-script. Czech coref uses a multilingual CorefUD model, not English
OntoNotes. **Acceptance test:** measured reduction in missed-supersession rate on inflected-name
pairs vs the surface-form baseline. *(Open spike: proper-noun/surname lemmatization accuracy is
the unverified hard case — measure before trusting WP-ML.)*

## 6. Clustering & reversibility (D21)

- **Decision clustering:** connected-components *to gather* candidate blobs (with a **black-hole
  guard**: raise threshold + repartition above component size T) → **HAC distance-cut inside
  each blob** (dedupe's `linkage(centroid)`+`fcluster(distance)`). **Never bare transitive
  closure** (A≈B, B≈C ⇏ A=C); never Louvain/Leiden for ER (that's D11 community detection).
- **Incremental:** max-both assignment + **nDR n=1** (re-cluster only the 1-hop neighborhood;
  order-independent; n=2 only when a hub is touched).
- **Reversibility (un-merge):** state lives only in Postgres — `resolution_decisions`
  (append-only), `merge_events` (pre-merge membership snapshot), `merged_into` redirects,
  optional negative/exclusion edges. No OSS system ships un-merge; building it is correct.
- **Generic-identifier guard** (Senzing): an alias that suddenly links many entities is
  down-weighted and re-evaluated.
- **Blast-radius rule:** never auto-merge above a degree/evidence threshold — wrongly merging
  two hubs is catastrophic; route to review (§8).

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
- T0–T3 in Postgres; T4 embedding in Lance (D8); HNSW never in OLTP.
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

## 11. Phasing

- **Phase 1:** registry schema + Alembic; T0–T3 deterministic tiers + T5 LLM adjudication; the
  seed ontology (D18) + domain/range; entity-resolution on English; the golden eval set + per-tier
  metrics + review CLI; reversibility records.
- **Phase 2:** T4 embedding tier; WP-ML (Czech lemmatization + D-M + multilingual coref); tier-0
  authority connectors; predicate-promotion workflow; health dashboards.
- **Phase 3:** learned matcher + active-learning training loop (separate from eval set); scope
  views; richer review UI if middle-band volume justifies it.

## 12. Open spikes (do before committing numbers)

1. **Golden-set labeling without circularity** — LLM-propose / human-verify loop; the denominator
   trap (recall needs ~370 true-positive pairs).
2. **Czech proper-noun lemmatization + D-M precision/recall** on declined names (no end-to-end
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
