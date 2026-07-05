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

- **E0 — Files** *(formerly L0)*: every input tracked and preserved (raw bytes kept immutably);
  normalized to a common text form via a **configurable conversion module** (OCR where needed);
  per-document **structure** (hierarchy + section roles + summaries) extracted, plus a **placement
  hint** for the corpus filesystem; cross-references between documents (e.g. citations) tracked.
  Converted bodies live in object storage; the spine holds only metadata + the queryable structure.
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

One compilation mechanism, many scopes (D45–D47); K1/K2/K3 name **content tiers** of that one
mechanism, not separate machinery — and they are its shipped **default configuration**: the
mechanism is a framework, and a deployment (including any user of the open-source library)
defines its own scopes and tiers (knowledge structure is configuration, not machinery — D47).
Two content kinds, one shared guarantee — **every K artifact records the evidence it rests
on** (citations), so staleness, deletion reach, and audit are mechanical, never guessed:

- **Compiled knowledge**: LLM-written pages derived from the evidence each page's recorded
  **routing rule** selects (entity / community / predicate / document-set keys — evaluated
  mechanically, chosen by an LLM planner); regenerated when stale (semantically reproducible);
  refreshed incrementally, never globally; body machine-owned — human input enters via
  per-page **curation** (pins / exclusions / corrections) that regeneration must honor and can
  never destroy.
- **Authored knowledge**: human/agent-authored first-class content (target states, designs,
  decisions); never auto-regenerated; cites the evidence it was based on and is **flagged for
  review when that evidence changes**.
- **K1 — General knowledge** *(formerly L3)*: the default scope — progressive-disclosure
  summaries (entity, topic, source pages) over the evidence.
- **K2 — Special-purpose scopes** *(formerly L4)*: pluggable purpose scopes (people profiles,
  business planning, as-is/to-be migration tracking, …); multiple scopes coexist; each scope
  anchors its vocabulary in a shared model page all its pages compile against.
- **K3 — Core beliefs and stances** *(formerly L5)*: the belief tier — ultra-distilled,
  compiled only from high-evidence, uncontradicted facts; every belief linked to its
  supporting and contradicting evidence; updates only on evidence, resistant to drift.

### Plane P — Projections (derived, no authority; rebuilt on schedule)

- **P1 — Search indexes**: vector/FTS indexes over chunks, claims, and relation fact labels;
  fully rebuildable from the spine.
- **P2 — Graph** *(formerly L6)*: relationships between entities; bi-temporal; supports
  as-of queries; ontology starts small and evolves by governance; fully rebuildable from the
  spine.
- **P3 — Corpus filesystem**: the corpus organized as a navigable **directory tree**, materialized
  to object storage and **mounted read-only** so agentic workers can browse the memory on their
  filesystem; built from document placement hints + entities/relations + the K-plane structure;
  fully rebuildable. Agents read the curated hierarchy and drill into the source documents.

## Knowledge lifecycle

- New information **supersedes** old information without destroying it — validity windows
  close; nothing is silently deleted.
- **Contradictions are surfaced**, never silently resolved.
- **Authored knowledge is never silently undermined**: human/agent-authored pages record the
  evidence they were based on and are flagged for review when that evidence changes (D46).
- **Two time axes** everywhere knowledge lives: when a fact was true in the world, and when
  the system learned/believed it.
- **Time-travel**: reconstruct both "what was true at T" and "what did we believe at T".
- **Deletion cascade**: removing an input must propagate through every derived layer; hard
  delete supported where required.

## Retrieval

- Exposed as **API, CLI, MCP server, and a mounted filesystem** (the corpus filesystem, P3,
  mounted read-only) — designed for agents composing hybrid strategies, including browsing the
  memory as files (`ls`/`cat`/`grep` over a navigable directory tree).
- Search modes: lexical (FTS/BM25), semantic, structured (filters, exact IDs), file-level
  (greps over the mounted corpus filesystem), graph (neighborhood, paths, as-of).
- Per-layer and cross-layer search; everything filterable; every result carries exact IDs and
  hydrates down to provenance (claim → evidence → source document).
- Named search recipes on top of composable primitives.
- **No LLM calls on the core search path** — query latency is retrieval-bound.
- Full flexibility is the goal: agents choose strategies, the system does not impose one.
- **The query surface must make the claim/relation temporal split explicit to agents.** Claims have
  **no temporal supersession** — they are immutable evidence (what a source asserted, including the
  validity interval *it* asserted), never closed or invalidated. **All supersession / current-belief
  validity lives only on relations.** So the querying system must surface, and its API/recipe naming
  must enforce, the distinction: a relation as-of query answers *"what does the system currently
  believe held at T"* (it honors supersession); a claim query answers *"what did sources assert"*
  (evidence, possibly stale, contradictory, or later superseded at the relation level). An agent must
  never read a claim's validity as the system's current belief, and "is this still true?" must route
  through relations, never through claims. (See D3, D6, D41.)

## Operational properties

- **Single source of truth for validity** — validity/invalidation state lives in exactly one
  place; all other stores hold derived, rebuildable projections.
- **Split source of truth**: deterministic layers rebuildable from the relational spine. The
  plane-K git repo is a source of truth backed up as such — with its **irreducible core being
  human-authored content** (authored pages + curation); compiled pages are semantically
  regenerable from the spine plus their recorded compile inputs (D45/D46).
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
- Plane K compilation: **Codex / OpenCode** as the planner/writer agents over a **single git
  repo**, orchestrated by the manifest-driven compile driver — one automated committer,
  dependency-ordered compiles; no concurrent sessions editing shared files (D45).

## Code

- Python, typed as strictly as practical (Pydantic, TypedDict, enums, Literal).
- Pyright for type checking; pytest for unit tests; Alembic for schema migrations.
- Docstrings, comments, well-structured modules.
