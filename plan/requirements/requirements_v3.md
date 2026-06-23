# Requirements v3

What we want from the system. Highest level of abstraction — capabilities, properties, and
constraints; the *how* lives in `plan/designs/`. Supersedes `requirements_v2.md` (root).
Decision rationale: `decisions.md`. Open items: `questions.md`.

## Vision

- A general-purpose memory system that ingests millions of heterogeneous documents and
  distills them into progressively more abstract, navigable knowledge layers.
- Consumed primarily by AI agents, with full human auditability.
- Still valuable at a million documents — scale is a requirement, not an aspiration.

## System structure: three planes (D14)

The system is organized as three planes; the plane determines trigger model, source of
truth, and rebuild semantics. L-numbers from earlier drafts survive as shorthand.

### Plane E — Evidence (per-document; relational spine is the source of truth)

- **E0 — Files** *(formerly L0)*: every input tracked and preserved; normalized to a common
  text form; document structure (hierarchy + summaries) extracted; cross-references between
  documents (e.g. citations) tracked.
- **E1 — Chunks** *(formerly L1)*: retrieval-sized units that preserve their surrounding
  context and trace back to the exact source document and position.
- **E2 — Claims** *(formerly L2)*: atomic, verifiable natural-language assertions; typed
  (fact / opinion / prediction) and temporally classified; immutable and append-only;
  provenance always attached; entity mentions resolved to canonical entities.
- **E3 — Relations**: distinct facts `(subject, predicate, object)` normalized from claims;
  many-to-many evidence links between claims and relations; the unit of supersession and
  contradiction.
- **Registries** (cross-cutting substrate of plane E — registries canonicalize, layers
  transform): canonical **entities** with aliases and resolution; governed **predicate**
  vocabulary with an escape hatch and periodic promotion.

### Plane K — Knowledge (aggregate, compiled, debounced; git is the source of truth)

- **K1 — General knowledge** *(formerly L3)*: progressive-disclosure summaries over
  high-information claims; refreshed incrementally, never globally; human-editable and
  version-controlled.
- **K2 — Special-purpose scopes** *(formerly L4)*: pluggable domain layers (people profiles,
  business planning, paper ideas, …); same guarantees as K1; multiple scopes may coexist.
- **K3 — Core beliefs and stances** *(formerly L5)*: ultra-distilled; every belief linked to
  its supporting and contradicting evidence; updates only on evidence, resistant to drift.

### Plane P — Projections (derived, no authority; rebuilt on schedule)

- **P1 — Search indexes**: vector/FTS indexes over chunks, claims, and relation fact labels;
  fully rebuildable from the spine.
- **P2 — Graph** *(formerly L6)*: relationships between entities; bi-temporal; supports
  as-of queries; ontology starts small and evolves by governance; fully rebuildable from the
  spine.

## Knowledge lifecycle

- New information **supersedes** old information without destroying it — validity windows
  close; nothing is silently deleted.
- **Contradictions are surfaced**, never silently resolved.
- **Two time axes** everywhere knowledge lives: when a fact was true in the world, and when
  the system learned/believed it.
- **Time-travel**: reconstruct both "what was true at T" and "what did we believe at T".
- **Deletion cascade**: removing an input must propagate through every derived layer; hard
  delete supported where required.

## Retrieval

- Exposed as **API, CLI, and MCP server**; designed for agents composing hybrid strategies.
- Search modes: lexical (FTS/BM25), semantic, structured (filters, exact IDs), file-level
  (greps), graph (neighborhood, paths, as-of).
- Per-layer and cross-layer search; everything filterable; every result carries exact IDs and
  hydrates down to provenance (claim → evidence → source document).
- Named search recipes on top of composable primitives.
- **No LLM calls on the core search path** — query latency is retrieval-bound.
- Full flexibility is the goal: agents choose strategies, the system does not impose one.

## Operational properties

- **Single source of truth for validity** — validity/invalidation state lives in exactly one
  place; all other stores hold derived, rebuildable projections.
- **Split source of truth**: deterministic layers rebuildable from the relational spine;
  LLM-derived git layers are their own source of truth and are backed up as such.
- **Rebuildability is exercised**, not assumed (periodic rebuild as the normal sync path
  and/or drills).
- **Idempotent processing**: every worker re-runnable, keyed by content hash + processing
  version.
- **Versioned processing**: prompt, model, and embedding versions recorded for every derived
  artifact.
- **Cost discipline**: cheap-first cascades — deterministic checks before small models before
  frontier models; LLM spend scales with ambiguity, not volume; per-layer cost metering and
  budgets.
- **Cost-proportional extraction**: extraction effort must not be wasted on junk. Junk is filtered
  **in-call at claim extraction** (proposition-level verifiability — opinion / boilerplate / intro /
  references dropped where they are cheapest to identify), and redundant *facts* collapse into one
  relation with an evidence count rather than re-paying per duplicate; exact-duplicate inputs are a
  no-op re-ingest (idempotency). Nothing is silently dropped — every input stays in the immutable
  originals and is always re-extractable. (No separate pre-extraction value/salience gate; see D25.)
- **Failures never disappear**: bounded retries, then dead-letter with recorded status.
- **Freshness**: plane E processes promptly per document; planes K and P are
  debounced/scheduled — staleness bounded by an explicit, configurable cadence.
- Observability over all pipelines; backups for both sources of truth.

## Imposed constraints (fixed choices)

- Relational spine: **Postgres** (Hetzner). Vectors: **LanceDB**. Graph: **LadybugDB**.
- Document structure: **PageIndex**. Chunking: **semchunk**. Claim extraction: **Claimify**
  principle.
- Workers: **GCP Cloud Run jobs** triggered via **Cloud Tasks** (max 2 retries, rate-limited).
- Plane K compilation (K1/K2): **Codex / OpenCode** sessions over a **single git repo**
  (distinct directory split; conflict retry within the same session; rolling-window delay
  for hot files).

## Code

- Python, typed as strictly as practical (Pydantic, TypedDict, enums, Literal).
- Pyright for type checking; pytest for unit tests; Alembic for schema migrations.
- Docstrings, comments, well-structured modules.
