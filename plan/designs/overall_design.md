# Overall System Design

The architecture that satisfies `plan/requirements/requirements_v3.md`. This document is the
map; per-layer designs (this directory) are the territory. Decision rationale lives in
`decisions.md` (root, cited as D1–D13); supporting research in `plan/analysis/`.

## 1. System overview

```
                          INGESTION (per document)                AGGREGATION (debounced)
                ┌──────────────────────────────────────────┐   ┌──────────────────────────┐
 inputs ──► GCS │ L0 files ──► L1 chunks ──► L2 claims ─────┼──►│ L3 general knowledge      │
                │  markdown     semchunk      claimify      │   │ L4 special-purpose layers │
                │  PageIndex    ctx prefix    coref+entities│   │ L5 core beliefs           │
                │               embeddings    relations     │   │ L6 graph (rebuild)        │
                └──────────────────────────────────────────┘   └──────────────────────────┘
                        │              │             │                │            │
                        ▼              ▼             ▼                ▼            ▼
                ┌────────────────────────────────────────────────────────────────────────┐
                │ Postgres (spine)   LanceDB (vectors)   git repo (L3–L5)   LadybugDB     │
                │ source of truth    derived             source of truth    derived       │
                └────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                 RETRIEVAL: API / CLI / MCP
                              entry (Lance/PG) → expand (graph)
                                   → hydrate (PG → GCS)
```

## 2. Stores and sources of truth (D1, D6)

| Store | Role | Authority | Rebuildable from |
|---|---|---|---|
| **Postgres** (Hetzner) | spine: inputs, chunks-metadata, claims, entities, predicates, relations, evidence, validity, processing state, costs | **source of truth** for L0–L2, relations, L6 inputs | — (PITR backups) |
| **GCS** | original files + markdown + graph snapshots | source of truth for file bytes | — |
| **LanceDB** | vector + FTS indexes: chunks, claims, relation fact labels | derived | Postgres |
| **git repo** | L3 general knowledge, L4 special-purpose layers, L5 beliefs | **source of truth** (LLM-derived, not reproducible) | — (own backups) |
| **LadybugDB** | graph projection of entities + relations | derived | Postgres (every cycle) |

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

## 4. Ingestion pipeline (per-document chain, D12)

Each stage is a Cloud Run worker triggered via Cloud Tasks; each completion enqueues the next
stage for that document. All workers idempotent (content hash + processing version), max 2
retries then dead-letter into Postgres.

1. **L0**: store original → convert to Markdown → PageIndex (hierarchy + node summaries) →
   record cross-references (citations).
2. **L1**: semchunk → LLM context prefix per chunk (contextual-retrieval style; prompt-cached)
   → embed → Lance, with references to document + PageIndex node.
3. **L2**: coreference resolution → Claimify extraction → entity resolution (tiered: exact →
   fuzzy → embedding → adjudication) → relation normalization → **supersession cascade**
   (D4): novelty gate → `(entity_id, predicate)` blocking over relations → cheap-first
   escalation → write-time outcomes (`supersedes` closes windows, `contradicts` flags,
   `same_as` proposes merges).

## 5. Aggregate derivation (debounced, D12)

Aggregate layers are **never** triggered per document — windowed/debounced ("N new claims or
T minutes"), since they summarize across the corpus.

- **L3/L4** (git): Codex/OpenCode sessions compile active claims into structured markdown;
  incremental — only summaries whose referenced claims changed; pull latest main, retry merge
  conflicts within the same session; hot files (root `index.md`) handled by a rolling-window
  delayed worker. Periodic **semantic linter** flags contradictions, broken links, stale
  assumptions. Repo exposed via MCP + auto-generated `llms.txt`.
- **L5**: beliefs derived from high-evidence, low-contradiction relations + L3/L4 synthesis;
  every belief links supporting/contradicting claim IDs; updates only on evidence.
- **L6**: full rebuild from Postgres → Parquet → LadybugDB → validated immutable GCS
  snapshot; readers serve read-only copies and hot-swap (D7). Full design:
  `l6_graph_design.md`.

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
- Surfaces: HTTP API, CLI, MCP server (memory layers + the L3/L4 repo).
- `as_of` parameter supported end-to-end on both time axes.

## 7. Deployment topology

- **Postgres on Hetzner**: pgBouncer pooling, TLS for cross-cloud access, PITR backups.
- **Workers on GCP**: Cloud Run jobs, Cloud Tasks queues (rate-limited, 2 retries + DLQ).
- **GCS**: input files, markdown, Parquet exports, graph snapshots.
- **git repo** (L3–L5): hosted remote + independent backup; written only by the aggregate
  workers and humans.
- Retrieval API holds local LanceDB datasets and LadybugDB snapshots; Postgres is the only
  cross-cloud dependency on the hot path (kept to ID hydration).

## 8. Cross-cutting concerns

- **Cost**: per-layer metering in Postgres; cheap-first cascades everywhere an LLM is
  involved; budgets enforced, not advisory.
- **Versioning**: prompt/model/embedding versions on every artifact; embedding migration is
  a planned batch path (re-embed by version filter).
- **Deletion cascade**: input removal propagates L1→L6 + tombstone signal to git layers;
  hard-delete supported.
- **Maintenance**: Lance compaction schedule; rebuild drills; semantic linter cadence;
  predicate-registry review.
- **Observability**: pipeline tracing/metrics; DLQ inspection; per-stage throughput and
  spend dashboards.

## 9. Per-layer designs (this directory)

| Design doc | Scope | Status |
|---|---|---|
| `overall_design.md` | this document | current |
| `l0_files_design.md` | ingestion, markdown, PageIndex, cross-refs | future |
| `l1_chunks_design.md` | chunking, context prefixes, Lance layout | future |
| `l2_claims_design.md` | extraction, entities, relations, supersession cascade | future |
| `l3_l4_git_layers_design.md` | repo layout, Codex/OpenCode workers, linter | future |
| `l5_beliefs_design.md` | belief derivation and update rules | future |
| `l6_graph_design.md` | graph projection, rebuild, snapshots, search | **current** |
| `retrieval_design.md` | API/CLI/MCP, recipes, rerankers | future |
| `postgres_schema_design.md` | spine schema, migrations, indexes | future |

## 10. Open questions

Tracked in `questions.md` (root). Highest-impact for design work: embedding model choice
(hardest to change), backfill vs. steady-state volumes, hard-delete obligations.
