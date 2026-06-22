# Overall System Design

The architecture that satisfies `plan/requirements/requirements_v3.md`. This document is the
map; per-layer designs (this directory) are the territory. Decision rationale lives in
`decisions.md` (root, cited as D1–D24); supporting research in `plan/analysis/`.

## 1. System overview: three planes (D14)

The system is a DAG across three planes, not a ladder. The plane determines the operational
rules — trigger model, source of truth, mutability, rebuild semantics.

```
 PLANE E — EVIDENCE (per-document chain; Postgres is truth)
            ┌── registries: entities, predicates ──┐
            ▼                  ▼                    ▼
 inputs ─► E0 files ─► E1 chunks ─► E2 claims ─► E3 relations
           (GCS, markdown, (semchunk,   (claimify,    (normalization,
            PageIndex)      ctx prefix)  coref)        evidence, supersession)
                 │            │            │   │
                 │            │            │   │      PLANE K — KNOWLEDGE (debounced,
                 │            │            │   │      LLM-compiled; git is truth)
                 │            │            ▼   ▼
                 │            │        K1 general / K2 scopes ─► K3 beliefs
                 │            │            │   │
                 ▼            ▼            ▼   ▼      PLANE P — PROJECTIONS (scheduled
            ┌─────────────────────────────────────┐  rebuild; derived, no authority)
            │ P1 search indexes (Lance: chunks,   │
            │    claims, relation fact labels)    │
            │ P2 graph snapshot (LadybugDB)       │
            └─────────────────────────────────────┘
                              │
                              ▼
                 RETRIEVAL: API / CLI / MCP
              entry (P1/PG) → expand (P2) → hydrate (PG → GCS)
```

| Plane | Trigger | Source of truth | Mutability | "Rebuild" means |
|---|---|---|---|---|
| **E** | per-document chain | Postgres | append-only, windows close | n/a — it *is* the truth |
| **K** | debounced/windowed | git repo | agent- and human-edited | re-compile (semantic) |
| **P** | scheduled cycle | none | immutable snapshots | from Postgres, every cycle |

## 2. Stores and sources of truth (D1, D6)

| Store | Role | Authority | Rebuildable from |
|---|---|---|---|
| **Postgres** (Hetzner) | spine: inputs, chunk metadata, claims, entities, predicates, relations, evidence, validity, processing state, costs | **source of truth** for plane E | — (PITR backups) |
| **GCS** | original files + markdown + P2 snapshots | source of truth for file bytes | — |
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
    └─< claims ──< claim_entity_mentions ──┘        predicates (governed registry)
          │                                              │
          └──< relation_evidence >── relations ──────────┘
               (stance: supports        (subject, predicate, object,
                | contradicts)           valid_from/valid_until,
                                         ingested_at/invalidated_at)
```

- **Claims** — immutable NL assertions; identity = assertion-by-a-source; typed + temporally
  classified; never superseded themselves.
- **Relations** — distinct facts; identity = the fact; bi-temporal validity windows; the unit
  of supersession and contradiction (D3).
- **Evidence** — many-to-many; corpus redundancy collapses into evidence counts (free
  confidence/salience signal).
- **Entities** — canonical registry with aliases, types, cached resolutions; only canonical
  IDs flow downstream.
- **Predicates** — governed vocabulary with `other:` escape and periodic promotion (D5).
- **Ontology** — universal schema.org-aligned core + user extensions anchored to it
  (extend-never-fork), with domain/range constraints; lives in the registries (D15).
  K2 scopes share one entity space and one graph; scope views are registry-declared
  projections, never separate databases (D16).

## 4. Plane E: ingestion pipeline (per-document chain, D12)

Each stage is a Cloud Run worker triggered via Cloud Tasks; each completion enqueues the next
stage for that document. All workers idempotent (content hash + processing version), max 2
retries then dead-letter into Postgres.

1. **E0**: store original → convert to Markdown → PageIndex (hierarchy + node summaries) →
   record cross-references (citations).
2. **E1**: semchunk → LLM context prefix per chunk (contextual-retrieval style; prompt-cached)
   → embed → P1, with references to document + PageIndex node.
3. **E2 → E3**: coreference (D19: in the E2 extraction call, all languages) →
   Claimify extraction → entity resolution (tiered cascade T0–T4, D17, via the entity
   registry) → relation normalization (predicate registry, domain/range D18) →
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
| `e0_files_design.md` | ingestion, markdown, PageIndex, cross-refs | future |
| `e1_chunks_design.md` | chunking, context prefixes, P1 layout | future |
| `e2_e3_claims_relations_design.md` | extraction, relation normalization, supersession cascade | future |
| `registries_design.md` | entity resolution, ontology, governance, review, eval (D15–D24) | **current** |
| `k_layers_design.md` | K1/K2 repo layout, Codex/OpenCode workers, linter | future |
| `k3_beliefs_design.md` | belief derivation and update rules | future |
| `p2_graph_design.md` | graph projection, rebuild, snapshots, search | **current** |
| `retrieval_design.md` | API/CLI/MCP, recipes, rerankers | future |
| `postgres_schema_design.md` | spine schema, migrations, indexes | future |

## 10. Open questions

Tracked in `questions.md` (root). Highest-impact for design work: embedding model choice
(hardest to change), backfill vs. steady-state volumes, hard-delete obligations.
