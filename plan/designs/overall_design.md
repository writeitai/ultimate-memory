# Overall System Design

The architecture that satisfies `plan/requirements/requirements_v3.md`. This document is the
map; per-layer designs (this directory) are the territory. Decision rationale lives in
`decisions.md` (root, cited as D1–D43); supporting research in `plan/analysis/`.

## 1. System overview: three planes (D14)

The system is a DAG across three planes, not a ladder. The plane determines the operational
rules — trigger model, source of truth, mutability, rebuild semantics.

```
 PLANE E — EVIDENCE (per-document chain; Postgres is truth)
            ┌── registries: entities, predicates ──┐
            ▼                  ▼                    ▼
 inputs ─► E0 files ─► E1 chunks ─► E2 claims ─► E3 relations
           (raw+md+         (semchunk,   (claimify,    (normalization,
            PageIndex,      ctx prefix)  coref)        evidence, supersession)
            placement)      │            │   │
                 │          │            │   │      PLANE K — KNOWLEDGE (debounced,
                 │          │            │   │      LLM-compiled; git is truth)
                 │          │            ▼   ▼
                 │          │        K1 general / K2 scopes ─► K3 beliefs
                 │          │            │   │
                 ▼          ▼            ▼   ▼      PLANE P — PROJECTIONS (scheduled
            ┌─────────────────────────────────────┐  rebuild; derived, no authority)
            │ P1 search indexes (Lance: chunks,   │
            │    claims, relation fact labels)    │
            │ P2 graph snapshot (LadybugDB)       │
            │ P3 corpus filesystem (GCS tree,     │
            │    mounted read-only to agents)     │
            └─────────────────────────────────────┘
                              │
                              ▼
                 RETRIEVAL: API / CLI / MCP / mounted FS
            entry (P1/PG) → expand (P2) → hydrate (PG → GCS); browse (P3)
```

| Plane | Trigger | Source of truth | Mutability | "Rebuild" means |
|---|---|---|---|---|
| **E** | per-document chain | Postgres | append-only, windows close | n/a — it *is* the truth |
| **K** | debounced/windowed | git repo | agent- and human-edited | re-compile (semantic) |
| **P** | scheduled cycle | none | immutable snapshots | from Postgres, every cycle |

## 2. Stores and sources of truth (D1, D6)

| Store | Role | Authority | Rebuildable from |
|---|---|---|---|
| **Postgres** (Hetzner) | spine: inputs, document/section metadata, chunk metadata, claims, entities, predicates, relations, evidence, validity, processing state, costs | **source of truth** for plane E | — (PITR backups) |
| **GCS — raw** | immutable original files | source of truth for file bytes | — |
| **GCS — artifacts** | per-document markdown + `pageindex.json` + conversion sidecars (E0, D37) | source of truth for converted bodies | E0 re-run by `converter_version` |
| **GCS — corpus fs** | **P3**: corpus organized as a mounted directory tree (D40) | derived | Postgres + artifacts (every cycle) |
| **LanceDB** | **P1**: vector + FTS indexes over chunks, claims, relation fact labels | derived | Postgres |
| **git repo** | plane K: K1 general, K2 scopes, K3 beliefs | **source of truth** (LLM-derived, not reproducible) | — (own backups) |
| **LadybugDB** | **P2**: graph projection of entities + relations | derived | Postgres (every cycle) |

Two hard rules: validity/invalidation state exists **only** in Postgres — Lance and Ladybug
carry filtered copies, never independently mutated (D6); and every derived store must be
reproducible by a tested batch path, exercised routinely (D7).

## 3. Core data model (D2, D3, D5)

Worked explainer with examples: `plan/analysis/concepts.md`.

```
documents ─< chunks                    entities ──< entity_aliases
    │                                      │
    └─< claims ──< claim_entity_mentions ──┘    governed_relationships (governed registry)
          │                                              │
          └──< fact_evidence >── facts ──────────────────┘
               (stance: supports        (subject, relationship, object_kind ∈
                | contradicts)            {entity, literal}, object_entity_id |
                                          object_value, valid_from/valid_until,
                                          ingested_at/invalidated_at)
          relations = view over facts WHERE object_kind = 'entity'  (D43)
```

- **Claims** — immutable NL assertions; identity = assertion-by-a-source; temporally classified and
  carrying an immutable **source-asserted validity interval** (D41); never superseded themselves.
- **Facts** — the unified verdict layer (D43): distinct facts whose object is either an **entity**
  (a *relation*, projected to the graph) or a **typed literal** (a value such as a balance or fiscal
  revenue — never a graph node). Identity = the fact; bi-temporal validity windows; the single unit
  of supersession and contradiction (D3) for both kinds. *Supersedable* literals (values that change
  over time) supersede like relations; same-period measurements both stand. **Relations** are the
  `object_kind='entity'` subset, exposed as a compatibility view. See `fact_layer_design.md`.
- **Evidence** — many-to-many; corpus redundancy collapses into evidence counts (free
  confidence/salience signal).
- **Entities** — canonical registry with aliases, types, cached resolutions; only canonical
  IDs flow downstream.
- **Relationships** — one governed vocabulary with `other:` escape and periodic promotion (D5/D43),
  covering predicates (entity range) and attributes (literal range); `predicates`/`attributes`
  remain as compatibility views.
- **Ontology** — universal schema.org-aligned core + user extensions anchored to it
  (extend-never-fork), with domain/range constraints; lives in the registries (D15).
  K2 scopes share one entity space and one graph; scope views are registry-declared
  projections, never separate databases (D16).

## 4. Plane E: ingestion pipeline (per-document chain, D12)

Each stage is a Cloud Run worker triggered via Cloud Tasks; each completion enqueues the next
stage for that document. All workers idempotent (content hash + processing version), max 2
retries then dead-letter into Postgres.

1. **E0** (document layer, a chain of idempotent sub-workers — D36; design: `e0_files_design.md`):
   **ingest** (store raw to GCS + `content_hash`) → **convert** (raw → Markdown via the configurable
   module, D38) → **structure** (PageIndex tree + roles + spans + summaries + a **placement hint**,
   D39) → **crossref** (citations). Bodies live in GCS (raw + artifacts buckets); Postgres holds only
   metadata + the queryable section index (D37).
2. **E1**: semchunk → LLM context prefix per chunk (contextual-retrieval style; prompt-cached)
   → embed → P1, with references to document + PageIndex node.
3. **E2 → E3** (every chunked document — there is no pre-extraction value gate, D25): coreference
   (D19: in the E2 extraction call, all languages) → **Claimify extraction with in-call Selection**
   (proposition-level verifiability KEEP/REWRITE/DROP — the value filter that replaces any
   pre-extraction gate; the E0 PageIndex section path is fed in so references/boilerplate/intro/
   conclusion drop at proposition grain) → entity resolution (tiered cascade T0–T4, D17, via the
   entity registry) → relation normalization (predicate registry, domain/range D18) →
   **supersession cascade** (D4): novelty gate → `(entity_id, predicate)` blocking over
   relations → cheap-first escalation → write-time outcomes (`supersedes` closes windows,
   `contradicts` flags, `same_as` proposes merges). Registry detail: `registries_design.md`.

Note on P1: search indexes are *written inline* by E-plane workers (chunks/claims/relation
labels embedded as they land) but remain plane-P objects — fully rebuildable from Postgres by
batch, carrying no authority.

## 5. Planes K and P: aggregate derivation (debounced/scheduled, D12)

Neither plane is triggered per document — K is windowed/debounced ("N new claims or T
minutes"), P rebuilds on schedule; both summarize/project across the corpus.

- **K1/K2** (git): Codex/OpenCode sessions compile active claims into structured markdown;
  incremental — only summaries whose referenced claims changed; pull latest main, retry merge
  conflicts within the same session; hot files (root `index.md`) handled by a rolling-window
  delayed worker. Periodic **semantic linter** flags contradictions, broken links, stale
  assumptions. Repo exposed via MCP + auto-generated `llms.txt`.
- **K3**: beliefs derived from high-evidence, low-contradiction relations + K1/K2 synthesis;
  every belief links supporting/contradicting claim IDs; updates only on evidence.
- **P2**: full rebuild from Postgres → Parquet → LadybugDB → validated immutable GCS
  snapshot; readers serve read-only copies and hot-swap (D7). Full design:
  `p2_graph_design.md`.
- **P1**: written inline by plane E (see §4); batch rebuild path exercised for embedding
  migrations and drills.
- **P3 — corpus filesystem** (D40): a rebuildable GCS directory tree organizing the corpus for
  agent navigation, **mounted read-only** to agentic workers. Built from E0 placement hints (D39)
  + entities/relations + the K-plane structure; folders by topic/source/entity, leaves linking to
  the E0 artifacts, generated `_index.md`/`llms.txt` at each level. Cross-links with K
  (understanding ↔ source). Full design: `e0_files_design.md` §6.

## 6. Retrieval architecture (D8, D9)

```
entry                          expand                    hydrate
Lance: relations (fact-label   LadybugDB snapshot:       Postgres:
  embeddings + scalar cols),   neighborhood, paths,      relation → evidence
  claims, chunks               as-of traversal           claims → documents
PG: FTS, entity registry       (projected graphs, D10)   → GCS bytes
        └──── RRF fusion ──── graph-distance + evidence-count rerank ────┘
```

- Channels run in parallel; **RRF** fuses; rerankers: graph distance from focal entities,
  evidence count; optional cross-encoder. **Zero LLM calls** on the core path.
- Composable primitives + named recipes (`relation_hybrid_rrf`, `relation_near_entity`,
  `claims_verbatim`, …).
- Surfaces: HTTP API, CLI, MCP server (memory planes + the K1/K2 repo).
- `as_of` parameter supported end-to-end on both time axes.

## 7. Deployment topology

- **Postgres on Hetzner**: pgBouncer pooling, TLS for cross-cloud access, PITR backups.
- **Workers on GCP**: Cloud Run jobs, Cloud Tasks queues (rate-limited, 2 retries + DLQ).
- **GCS**: input files, markdown, Parquet exports, graph snapshots.
- **git repo** (plane K): hosted remote + independent backup; written only by the aggregate
  workers and humans.
- Retrieval API holds local LanceDB datasets and LadybugDB snapshots; Postgres is the only
  cross-cloud dependency on the hot path (kept to ID hydration).

## 8. Cross-cutting concerns

- **Cost**: per-layer metering in Postgres; cheap-first cascades everywhere an LLM is
  involved; budgets enforced, not advisory.
- **Versioning**: prompt/model/embedding versions on every artifact; embedding migration is
  a planned batch path (re-embed by version filter).
- **Deletion cascade**: input removal propagates E1→P2 + tombstone signal to git layers;
  hard-delete supported.
- **Maintenance**: Lance compaction schedule; rebuild drills; semantic linter cadence;
  predicate-registry review.
- **Observability**: pipeline tracing/metrics; DLQ inspection; per-stage throughput and
  spend dashboards.

## 9. Per-layer designs (this directory)

| Design doc | Scope | Status |
|---|---|---|
| `overall_design.md` | this document | current |
| `e0_files_design.md` | E0 document layer + P3 corpus filesystem (D36–D40) | **current** |
| `e1_chunks_design.md` | chunking, context prefixes, P1 layout | planned |
| `e2_e3_claims_relations_design.md` | claim extraction + relation normalization; why there is no value gate (D31–D35, D25) | **current** |
| `fact_layer_design.md` | the unified `facts` verdict layer — entity & literal objects, the `supersedable` gate, interval-capping, ATTACH-direct projection (D43) | **current** |
| `nonrelational_facts_design.md` | non-relational attribute conflicts — detect/group/surface (D42; **superseded/subsumed by D43**, see `fact_layer_design.md`) | superseded |
| `registries_design.md` | entity resolution, ontology, governance, review, eval (D15–D24) | **current** |
| `k_layers_design.md` | K1/K2 repo layout, Codex/OpenCode workers, linter | planned |
| `k3_beliefs_design.md` | belief derivation and update rules | planned |
| `p2_graph_design.md` | graph projection, rebuild, snapshots, search | **current** |
| `retrieval_design.md` | API/CLI/MCP, recipes, rerankers | planned |
| `postgres_schema_design.md` | spine schema, tables, indexes, partitioning, deletion cascade | **current** |

## 10. Open questions

Tracked in `questions.md` (root). Highest-impact for design work: embedding model choice
(hardest to change), backfill vs. steady-state volumes, hard-delete obligations.
