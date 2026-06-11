# Requirements v2

I want a solution that would scale to millions of input documents and would still offer value.

v2 incorporates external reviews (claim-supersession architecture, write-side cost control,
context-preservation research) and resolves the open tensions from v1.

## Principles

- **Split source of truth.** Postgres is authoritative for L0–L2 and L6 (all deterministically
  rebuildable from it). The git repo is itself the source of truth for L3–L5 (LLM-derived, not
  reproducible) — it must be backed up; Postgres tracks its provenance and triggers only.
- **Append-only with soft invalidation.** Claims are never destructively deleted; supersession
  closes a validity window. Old claims stay queryable (audit, point-in-time reconstruction).
- **Single source of truth for validity.** Validity/invalidation metadata lives in Postgres only.
  Lance and Ladybug hold derived copies and filter at query time — never independently mutated
  (avoids vector/graph desync failure modes documented in Mem0).
- **Idempotent workers.** Every worker is keyed by content hash + processing version, safe to
  re-run (required for rebuilds and for retry semantics anyway).
- **Versioned processing.** Prompt version, model ID, and embedding model/dimension are recorded
  in Postgres for every derived artifact.
- **Cheap-first cascades.** Deterministic checks → small models → frontier LLM only for the
  ambiguous remainder. At millions of documents, write-side LLM calls dominate cost.

## Ingestion

- all inputs are tracked in Postgres
- deletion of an input must cascade through all layers (L1–L6 and a removal signal to the git layers)

### L0 - Files
- input files are stored on GCS
- they are transformed into Markdown files and saved in dedicated directory
- then they are processed via https://github.com/VectifyAI/PageIndex - we get a hierarchy + summaries for each document
- we should have ability to track files cross-references in DB (e.g. papers citing other papers)

### L1 - Chunks
- we use semchunk for chunking of the documents
- use Lance DB as the vector database
- each chunk gets a short LLM-generated **context prefix** prepended before embedding
  (Anthropic contextual-retrieval style; cheap with prompt caching) — solves retrievability
  without rewriting the text
- the chunks must hold reference to the original input document **and the PageIndex node**
  (parent-child retrieval: search small units, return the contextual parent)
- indexes properly designed: vector index + scalar indexes + FTS; specify embedding model,
  dimension, metric; plan compaction/reindex strategy

### L2 - Claims
- use the Claimify principle
- avoid decontextualization: claims keep their context prefix + provenance link instead of
  being rewritten to stand alone
- claims are atomic **natural-language assertions** annotated with claim type (fact / opinion /
  prediction) + temporal class (static / dynamic / atemporal) + provenance + resolved entity
  mentions
- claims are **bi-temporal**: `valid_from`, `valid_until`, `ingested_at`, `superseded_by`
- claims and relations are **distinct concepts** (many-to-many): a separate
  **relation-normalization step** maps eligible claims onto `(subject, predicate, object)`
  **relation** records against the predicate registry; existing relation → claim becomes
  supporting **evidence**; conflicting relation → supersession/contradiction adjudication runs
  at the relation level; graph edges (L6) project relations, never claims
- **coreference resolution runs before extraction** (pronouns resolved to canonical entities)
- **supersession pipeline** (the core scaling mechanism):
  1. **novelty gate** — cheap embedding-similarity thresholds: clearly novel → ADD without LLM;
     near-duplicate → NOOP without LLM; only the ambiguous band escalates
  2. **entity-keyed blocking** — candidate supersessions found via `(entity_id, predicate)`
     block, never O(N) similarity over the whole store
  3. **tiered resolution** — exact match → fuzzy (FTS-gated) → embedding similarity →
     small-model judgment → frontier LLM only for the residue
  4. **write-time handlers** — `supersedes` (closes validity window), `contradicts` (flagged,
     surfaced at retrieval instead of silently resolved), `same_as` (entity merge proposal)
- the active claims are embedded and available via Lance DB; queries filter
  `valid_until IS NULL OR valid_until > as_of` by default

### Entity registry
- canonical entities live in Postgres with cached alias → canonical-ID mappings
- entity resolution quality is make-or-break for blocking — invest here early

### L3 - General Knowledge
- the progressive disclosure summarization layer over the high-information claims
- **compile-and-lint cycle**: a background process compiles active claims into structured
  markdown; refresh is **incremental** — only summaries whose referenced claims changed are
  re-derived (no global recomputation à la GraphRAG)
- a periodic **semantic linter** scans for internal contradictions, broken links, orphan files,
  and claims whose underlying assumptions expired
- summaries reference the claim IDs they were derived from

### L4 - Special-Purpose Knowledge Layers
- e.g. people profiles, business planning, paper idea concepts etc. - whatever the system is aimed or wants to be better at
- also git-tracked, same repo as L3, distinct directories, multiple layers allowed
- same compile-and-lint + incremental refresh discipline as L3

### L5 - Core beliefs and stances
- ultra-derived and filtered layer holding the core beliefs and stances
- each belief links its supporting and contradicting claim IDs; beliefs update only on
  evidence, not on conversational drift
- (optional refinement: quantitative stance score with explicit uptake/anchoring parameters)

### L6 - graph layer
- tracking relationships between entities
- bi-temporal
- we should start with a reasonable ontology and evolve over time if necessary
- be inspired by graphiti / zep
- base it on **LadybugDB** (maintained Kuzu successor; columnar, Cypher, Arrow/Parquet interop)
- scope v1 to **entity-adjacency queries** (what blocking and retrieval actually need);
  multi-hop traversal is a later addition if real use cases demand it
- LadybugDB is embedded/single-writer → a **dedicated L6 writer worker** serializes all graph writes


## Deployment
- Postgres on Hetzner — with PITR backups and an HA/restore story (it is the spine)
- workers on GCP (cloud run jobs); connection pooling (pgBouncer) + TLS for the cross-cloud link
- the L3–L5 git repo is backed up independently (it is a source of truth)


## Processing
- via Cloud Run workers triggered via Cloud Tasks
- Cloud Tasks must have max. 2 retries, **plus a dead-letter queue** — failures land in Postgres
  with status, never disappear
- Cloud Tasks must be rate-limited to a reasonable number
- explicit **cost budget and metering** per layer (token + embedding spend tracked in Postgres)

### Trigger model
- **per-document chain**: L0 → L1 → L2 — each layer's worker triggers the next for that document
- **aggregate layers (L3–L6) are NOT per-document**: they are triggered windowed/debounced
  ("re-derive after N new claims or T minutes"), otherwise they become a serial bottleneck
  incompatible with millions of documents

### Git layers (L3/L4)
- the L3 and L4 should use Codex / OpenCode for processing
- we must make sure they always pull the latest main before they start and that they see the entire repo
- L3 and L4 must be a single repo
  - the directories structure must distinctly split the two
  - the L4 can have multiple special-purpose memory layers/directories
- they should be able to handle merge conflicts - i.e. they must re-try with the same session
- some highly-frequent edited files like root-level index.md might have to be edited by a separate worker that would be triggered after a rolling-window delay
  - i.e. if it gets a signal, there will be some delay before it starts
  - if the signal is received again within the delay window, the delay gets restarted to original value


## Retrieval
- we should prepare API and CLI
- the idea is that the agents would be able to use hybrid approaches
- we should offer searches:
  - lexical (FTS / BM25)
  - semantic
  - file search (greps etc.)
- they should be able to filter stuff, and also get the exact IDs
- they should be able to do cross-layer searches, but also per-layer searches
- **relations are searchable too**: each relation has a canonical fact label embedded in Lance
  (keyed by relation_id) with scalar filters (predicate, entities, validity) — graph edges are
  reachable semantically, not only via entity IDs
- results fused via **RRF** with graph-distance and evidence-count reranking; named **search
  recipes** on top of composable primitives; **no LLM calls** on the core search path
- **time-travel**: `as_of` parameter reconstructs the belief state at any past moment
  (bi-temporal claims make this nearly free)
- contradictions detected at write time are **surfaced**, not hidden
- expose the L3/L4 repo via an **MCP server** and auto-generated `llms.txt` /
  `llms-full.txt` for agent consumption

Basically we should offer a full flexibility.


## Maintenance
- semantic linter runs on schedule (see L3)
- **embedding migration plan**: re-embedding millions of vectors on model change is a known
  major cost — embedding model version is tracked per record, migration is a batch job
- LanceDB compaction/optimize scheduled; verify index integrity after optimize
  (known `merge_insert` + scalar-index pitfalls)
- periodic full-rebuild drill: prove the "rebuildable from Postgres" property actually holds


## Code
- we should use Python that would be as typed as possible - Pydantic / TypedDict + enums, types.Literal etc.
- we should use docstrings and comments
- we should structure code well
- we should use Pyright for type checking
- pytest for unit tests
- Alembic for Postgres schema migrations
