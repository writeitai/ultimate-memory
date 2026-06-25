# Postgres Schema Design — the Plane-E Spine

This document specifies the **complete Postgres schema** for `ugm`: every table, column,
primary key, foreign key, index, enum, and the partitioning / deletion / versioning rules that
tie them together. Postgres is the **single source of truth for plane E** (evidence) and the
**only home of validity/invalidation state** (D6); every other store (LanceDB, LadybugDB, the
GCS corpus filesystem, the K-plane git repo) is either a rebuildable projection of what lives
here or an independently-backed source of truth whose *provenance and triggers* live here.

It is the binding companion to `overall_design.md` (§3 core data model, §9 lists this doc),
`registries_design.md` (D15–D24), `e0_files_design.md` (D36–D40),
`e2_e3_claims_relations_design.md` (D31–D35), `p2_graph_design.md` (D6–D11),
`concepts.md` (the claims/relations/evidence/bi-temporality explainer) and `decisions.md`
(D1–D43). Where a table or column exists *because of* a decision, the decision is cited inline.

> **Reading this as a stranger (CLAUDE.md Rule 1).** You do not need to have been in the design
> conversation. Each module opens with what it stores and *why it has the shape it has*; each
> column carries a description stating what it holds, its units, and any non-obvious constraint.
> Jargon is defined where first used or cited to a companion doc: **blocking** and **bi-temporal**
> in `concepts.md` §6/§5, **supersession** in `concepts.md` §4. The few statistical/tool terms
> this doc uses (**Wilson interval**, **Splink waterfall**, **novelty gate**) are glossed at first
> use below.

> **This is the full-scope schema (CLAUDE.md Rule 2).** It is sized and shaped for the millions-
> of-documents target, not an MVP. Numbers (partition cadence, retry budgets, golden-set sizes,
> threshold defaults) are **starting points to measure**, labelled as such — never committed
> constants. The one deliberately-excluded mechanism is the graph incremental-sync outbox
> (`graph_events`), a documented *non-goal* under D7 (rebuild-first); its absence is a scope
> boundary, not a deferral. §15 records it as a non-goal.

---

## 0. Conventions

These rules apply to every table unless a module overrides them with a stated reason.

- **Migrations & DDL ordering.** The schema is owned by **Alembic** (requirements_v3 §Code). The
  DDL in this document is the source; the migration emits each inline `--` column description as a
  `COMMENT ON COLUMN` and each `COMMENT ON TABLE` shown here. **All `CREATE TYPE` enum statements
  (§1) are created first, before any table** — they are presented in §1 (immediately below) for
  exactly this reason. Extensions (below) are created before that.
- **Identifiers.** All surrogate primary keys are **`uuid`**, generated as **UUIDv7**
  (time-ordered) by the application/worker, *not* the database — Cloud Run workers write
  concurrently and a central sequence would be a hotspot, while UUIDv7's leading timestamp gives
  index/heap locality on append-only tables and lets a reader derive the row's creation month from
  the id alone (used for partition pruning, §12). UUIDv7 also satisfies "`entity_id` is **never
  reused**" (D17/§4) for free. IDs are worker-minted so the row's identity is known before the
  INSERT (needed for idempotency and for deterministic-id dedup, §9).
- **Time vocabulary.** Every timestamp is **`timestamptz`** (UTC). Distinct *kinds* of time recur
  and must not be conflated (`concepts.md` §5):
  - **valid-time** — when a fact held *in the world*. On **relations** this is the revisable,
    adjudicated window `valid_from`/`valid_until`. On **claims** it is the **immutable,
    source-asserted** interval `claim_valid_from`/`claim_valid_until` (+ `claim_valid_precision`,
    `claim_valid_kind`) — *the window the source attributed to the proposition* (D41). Claim
    valid-time is *evidence* (immutable, many-valued per fact); relation valid-time is *current
    belief* (revisable, one per fact). They never write to each other.
  - **assertion-time** — `asserted_at` (claims only): when the **source** asserted the claim (≈
    `documents.published_at`). This is the assertion *event*, **not** the fact's world-time — "in
    2024 a report said FY2023 revenue was \$5M" has `asserted_at`=2024 but `claim_valid_*`=FY2023.
  - **transaction-time** — when the *system* learned/un-learned it: `ingested_at` (claims, relations)
    and `invalidated_at` (relations only). Never revised on claims; revisable on relations
    (supersession, D3).
  The relation pair (valid + transaction) = "bi-temporal". A relation answers "true in the world at
  T?" and "believed by us at T?"; a claim answers "asserted when / ingested when / asserted to hold
  over what world-interval?" — all three immutable.
- **Tenancy (`deployment_id`) and cross-deployment isolation.** The system runs as **N independent
  deployments**, one per problem domain (personal assistant, agency, a manufacturer's migration, a
  legal engine); entity spaces are **never shared across deployments** (`registries_design.md` §1,
  D16). Every deployment-scoped table carries `deployment_id`. Two physical realizations satisfy
  the same logical schema: **(a)** one database with `deployment_id` on every row (optionally with
  Row-Level Security), or **(b)** schema-/database-per-deployment (the column is then constant
  within a schema). This document is written for the stricter case (a). **The
  "never co-resolve across deployments" invariant is enforced structurally, not by prose:** every
  deployment-scoped parent table carries a `UNIQUE (deployment_id, <pk>)` key, and every
  deployment-scoped foreign key is **composite** — `FOREIGN KEY (deployment_id, x_id) REFERENCES
  parent (deployment_id, x_id)` — so a row in deployment A *cannot* reference a row in deployment B
  even though UUIDs are globally unique. (This is the single biggest change from a naive
  single-column-UUID FK design and is applied throughout.) **The one documented exception is a
  *self-referential* FK** — a row pointing at another row of the *same* table (a section's parent
  section; a merge or adjudication supersession chain: `merge_events.reversed_by`,
  `relation_adjudications.superseded_by`). Both rows are by construction in the same deployment (same
  document, same registry), so these remain single-column for brevity; they cannot cross deployments
  because the worker only ever links rows it created within one deployment.
- **Foreign keys at scale (D23).** The large append-only E-plane tables (`mentions`,
  `resolution_decisions`, `relation_evidence`, `claims`, `claim_extraction_decisions`, `chunks`)
  are **RANGE-partitioned by month** and use **logical foreign keys** — referential integrity
  enforced by the idempotent workers and verified by a periodic **auditor query**, **not** by a
  DB-level `FOREIGN KEY`. Reasons: (1) Postgres requires a FK to a partitioned table to reference a
  unique constraint that *includes the partition key*, which would force the partition month into
  every child and join; (2) D23's "btree-only, cap write-amplification" mandate on these hot
  tables. **All non-partitioned tables use real composite FK constraints** with the `ON DELETE`
  behavior stated per column. A logical-only FK is tagged `-- LOGICAL FK → table(col)`. The auditor
  checks for orphans **and** for duplicate logical-unique tuples that a partitioned table cannot
  enforce in-DB (notably `(relation_id, claim_id)` in `relation_evidence`, §9).
- **Versioning (D1, D12).** Every non-deterministic output records the version of the component
  that produced it (`*_version` columns), resolving to a row in `pipeline_component_versions` (§2)
  that pins model + prompt hash + params. This is what makes "rebuild = replay stored state, never
  re-call the model" (D7/D33) auditable and what scopes a re-processing batch.
- **Enums** (§1) are small, stable, system-owned vocabularies; `ALTER TYPE ... ADD VALUE` extends
  them. User-governed vocabularies (entity types, predicates) are **registry tables** (§3), not
  enums (D5/D15) — they must be insertable at runtime with descriptions and parent links.
- **JSONB** is used only for open-ended, not-queried-by-key payloads (resolver feature vectors,
  tier configs, validation reports, DLQ payloads). Anything filtered or joined is a column.
- **Naming.** snake_case; tables plural; `_id` = identity reference; `_ref` = opaque key into
  another store (e.g. a Lance row key); `_uri` = GCS object URI; `_at` = timestamptz; `_version` =
  component version string.
- **No document/body text in Postgres (D37).** Postgres stores compact, query-critical metadata
  and the section index; bodies/Markdown/chunk text/embeddings live in GCS / Lance. The schema
  stores **offsets + URIs**, plus the small generated artifacts that must be *replayed* on rebuild
  (context prefixes, claim text, decision ledgers) — derived metadata, not source bodies.

Required Postgres extensions (created before all types and tables):

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid fallback; digests
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- T1 fuzzy blocking: trigram GIN on names (D17)
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch; -- T2 phonetic: daitch_mokotoff() (D17, NOT soundex)
CREATE EXTENSION IF NOT EXISTS unaccent;      -- accent-fold names before trigram/phonetic (registries §5)
CREATE EXTENSION IF NOT EXISTS btree_gin;     -- composite GIN (deployment_id + trigram/phonetic) on blocking tables
CREATE EXTENSION IF NOT EXISTS btree_gist;    -- composite GiST: relations bi-temporal EXCLUDE constraint (§9)
CREATE EXTENSION IF NOT EXISTS pg_partman;    -- monthly RANGE partition automation (D23, §12)
```

PostgreSQL **16+** is assumed (composite-FK column-list `ON DELETE SET NULL` requires 15+; this is
relied on for `document_crossrefs`, §6).

---

## 1. Enum types (created first)

System-owned, stable vocabularies, created before any table. Extended with
`ALTER TYPE ... ADD VALUE`. (User-governed vocabularies — entity types, predicates — are registry
*tables*, §3, not enums.)

```sql
CREATE TYPE deployment_status      AS ENUM ('active','suspended','archived');

-- Every non-deterministic producer that stamps a *_version resolving to pipeline_component_versions
-- has a value here (so a version string can always resolve to a catalog row, D1/D12):
CREATE TYPE pipeline_component     AS ENUM (
  'ingester','converter','structurer','crossreferencer','chunker','context_prefixer',
  'extractor','grounder','resolver','normalizer','adjudicator','embedder','fact_labeler',
  'community_detector','snapshot_builder','knowledge_compiler','judge');
CREATE TYPE processing_target      AS ENUM ('document','document_section','chunk','claim','relation','snapshot','knowledge_artifact');
CREATE TYPE pipeline_stage         AS ENUM ('ingest','convert','structure','crossref','chunk','embed_chunk','extract_claims','ground_claims','resolve_entities','normalize_relations','adjudicate_supersession','embed_relation','label_relation','build_snapshot','detect_communities','compile_knowledge');
CREATE TYPE processing_status      AS ENUM ('pending','running','succeeded','failed','dead_letter','skipped');

CREATE TYPE ontology_tier          AS ENUM ('core','extension','other','deprecated');
CREATE TYPE ontology_status        AS ENUM ('active','deprecated');
CREATE TYPE scope_interest_kind    AS ENUM ('entity_type','predicate','metadata','keyword');

CREATE TYPE entity_status          AS ENUM ('active','merged','retired');
CREATE TYPE alias_provenance       AS ENUM ('source','llm_canonical');
CREATE TYPE resolution_tier        AS ENUM ('T0','T1','T2','T3','T4_small','T4_frontier','human');
CREATE TYPE decision_actor         AS ENUM ('auto','human');

CREATE TYPE review_item_kind       AS ENUM ('merge_cluster','split_cluster','type_conflict','generic_identifier','contradiction','attribute_conflict');  -- attribute_conflict (D42): a non-relational conflict_group; verdict restricted to both_stand/promote_to_relation (CHECK on review_queue)
CREATE TYPE review_status          AS ENUM ('pending','accepted','rejected','deferred','auto_resolved');
-- Covers all review_item_kinds (D24), not just merges: pick_a/pick_b/both_stand for contradictions,
-- downweight/keep_signal for generic_identifier, retype for type_conflict.
CREATE TYPE review_verdict         AS ENUM ('merge','not_merge','split','retype','downweight','keep_signal','pick_a','pick_b','both_stand','promote_to_relation','uncertain');  -- promote_to_relation (D42): with both_stand and the non-resolving uncertain, the only legal verdicts for an attribute conflict; pick_a/pick_b are CHECK-illegal there (a "pick" would write the forbidden claim-side current-value verdict)
CREATE TYPE golden_label           AS ENUM ('match','no_match');
CREATE TYPE golden_hardness        AS ENUM ('hard_positive','hard_negative','easy');
CREATE TYPE eval_suite             AS ENUM ('resolution','selection','grounding','retrieval','contradiction');
CREATE TYPE selection_outcome      AS ENUM ('keep','rewrite','drop','kept_flagged');

CREATE TYPE document_status        AS ENUM ('ingesting','converting','structuring','ready','failed','deleted');
CREATE TYPE section_role           AS ENUM ('body','abstract','introduction','results','methods','discussion','conclusion','references','appendix','table','figure_caption','nav','boilerplate','legal');
CREATE TYPE crossref_kind          AS ENUM ('cites','links_to','attaches','replies_to');

CREATE TYPE claim_temporal_class   AS ENUM ('static','dynamic','atemporal');
-- D41 source-asserted validity on claims (immutable; never a relation-style revisable window):
CREATE TYPE claim_valid_precision  AS ENUM ('unknown','instant','day','month','quarter','year','open');
CREATE TYPE claim_valid_kind       AS ENUM ('proposition_validity','event_time','measurement_period','effective_period');
-- D42 non-relational attribute facts (conflict surfacing):
CREATE TYPE attribute_value_domain AS ENUM ('money','date','quantity','count','ratio','string_enum','boolean'); -- typed domain that drives DETERMINISTIC value normalization ("$5M" == "5,000,000 USD")
CREATE TYPE attribute_conflict_state AS ENUM ('single','corroborated','value_disagreement','restatement','refinement','indeterminate'); -- deterministically computed grouping state; NEVER a verdict
CREATE TYPE grounding_audit_status AS ENUM ('unaudited','sampled_pass','sampled_fail','escalated');
-- The ledger records DROPs, low-confidence keeps (flags), and decontextualization EDITs.
-- Plain keeps are NOT persisted (they ARE the claims row); see §8.
CREATE TYPE extraction_decision_type AS ENUM ('selection_drop','selection_keep_flagged','decontext_edit');
CREATE TYPE selection_drop_reason  AS ENUM ('opinion','advice','hypothetical','generic','question','intro','conclusion','no_info','ambiguous','references_boilerplate');

CREATE TYPE evidence_stance        AS ENUM ('supports','contradicts');
CREATE TYPE relation_status        AS ENUM ('active','invalidated');  -- generated mirror of invalidated_at; retirement (zero-evidence GC, §13) = setting invalidated_at
CREATE TYPE fact_object_kind       AS ENUM ('entity','literal');  -- D43: a fact's object is an entity reference (graph-eligible) or a typed literal (Lance/PG only); also governed_relationships.range_kind
CREATE TYPE adjudication_outcome   AS ENUM ('add','noop','supersede','contradict','same_as_merge_proposal');
CREATE TYPE adjudication_method    AS ENUM ('novelty_gate','exact','fuzzy','embedding','small_model','frontier_llm');

CREATE TYPE projection_plane       AS ENUM ('P1_search','P2_graph','P3_corpusfs');
CREATE TYPE snapshot_status        AS ENUM ('building','validating','published','superseded','failed');
CREATE TYPE community_algorithm    AS ENUM ('leiden','louvain');  -- external detection pass (D11)

CREATE TYPE knowledge_layer        AS ENUM ('K1','K2','K3');
CREATE TYPE knowledge_artifact_status AS ENUM ('active','stale','tombstoned');
CREATE TYPE knowledge_evidence_role AS ENUM ('supports','contradicts','cites');
CREATE TYPE knowledge_trigger      AS ENUM ('claims_changed','community_changed','debounce_timer','manual','tombstone');
CREATE TYPE refresh_status         AS ENUM ('pending','running','done','failed');
```

`novelty_gate` (in `adjudication_method`) is the deterministic short-circuit at the front of the
supersession cascade: if a new claim's `(subject, predicate, object)` fact already exists with a
compatible window and adds nothing new, adjudication is skipped entirely (no LLM call) — the
cheap-first rung of D4. The other methods are self-evident (exact / fuzzy / embedding / small
model / frontier LLM).

---

## 2. Tenancy & pipeline infrastructure

The substrate every other module sits on: the deployment registry, the component-version catalog
that gives every `*_version` string meaning, the idempotency/dead-letter ledger that makes workers
re-runnable (D12), and the cost ledger that meters LLM/embedding spend per layer
(`overall_design.md` §8).

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- deployments — the tenancy root. One row per independent instance (D16/registries §1).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE deployments (
  deployment_id   uuid PRIMARY KEY,            -- stable instance identity; appears in every scoped FK
  slug            text NOT NULL UNIQUE,        -- short handle used in GCS bucket names: ugm-<slug>-raw etc.
  name            text NOT NULL,               -- human label ("Personal assistant", "Acme migration")
  description     text,                        -- what this deployment is for
  default_language text NOT NULL DEFAULT 'en', -- primary corpus language; gates the multilingual matching path (registries §5)
  raw_bucket      text NOT NULL,               -- gs:// raw bucket (immutable originals, never mounted) — D37
  artifacts_bucket text NOT NULL,              -- gs:// artifacts bucket (markdown/pageindex, mount-readable) — D37
  corpusfs_bucket text NOT NULL,               -- gs:// P3 corpus-filesystem bucket (snapshots + latest) — D40
  knowledge_repo_uri text,                     -- plane-K git remote (git is truth for K; PG holds provenance only) — D1
  status          deployment_status NOT NULL DEFAULT 'active',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE deployments IS
  'Independent system instances (D16). Entity spaces, registries, graphs and buckets are never shared across rows here; deployment_id scopes every other table and participates in every scoped FK.';

-- ─────────────────────────────────────────────────────────────────────────
-- pipeline_component_versions — what every *_version string means (D1/D12).
-- Pin model+prompt+params so replay-on-rebuild (D7) is auditable and re-process batches can be
-- scoped by a version filter (e.g. re-embed where embedding_version < 'emb-2026-02').
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE pipeline_component_versions (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  component       pipeline_component NOT NULL, -- which producer (see the pipeline_component enum, §1 — every value listed there can appear)
  version         text NOT NULL,               -- the string stamped on artifacts (e.g. 'extractor-2026-03a')
  model_name      text,                        -- LLM/embedding model id, if this component calls a model (e.g. 'claude-opus-4-8')
  prompt_hash     text,                        -- sha256 of the rendered prompt template (registry-derived prompts change ⇒ new version) — D15
  embedding_dim   int,                         -- embedder only: vector dimension (re-embedding is the hardest migration — questions.md Q3)
  params          jsonb NOT NULL DEFAULT '{}', -- decoding params, routing table, thresholds snapshot, etc.
  notes           text,
  configured_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (deployment_id, component, version)
);
COMMENT ON TABLE pipeline_component_versions IS
  'Catalog resolving every *_version string to its model/prompt/params, so replay-on-rebuild (D7) and version-scoped reprocessing are auditable (D1, D12). Every pipeline_component enum value can be catalogued here.';

-- ─────────────────────────────────────────────────────────────────────────
-- processing_state — idempotency + status + dead-letter, the D12 spine.
-- One row per (target, stage, component_version). A worker INSERTs (ON CONFLICT DO NOTHING) this
-- row before work; it is a no-op if a row for the SAME (deployment_id, target_kind, target_id,
-- stage, component_version) already has status='succeeded'. Because target ids are content-derived
-- and stable (a document re-upload resolves to the same doc_id via documents' UNIQUE(deployment,
-- content_hash); sub-document targets are deterministic), the (target,stage,version) tuple IS the
-- content+version idempotency key D12 calls for. content_hash is carried for diagnostics/replay.
-- The dead-letter queue is the rows with status='dead_letter' (no separate table).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE processing_state (
  processing_id   uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  target_kind     processing_target NOT NULL,  -- document | document_section | chunk | claim | relation | snapshot | knowledge_artifact
  target_id       uuid NOT NULL,               -- LOGICAL FK → the target table's PK (kind tells you which)
  stage           pipeline_stage NOT NULL,     -- the processing stage (see pipeline_stage enum, §1)
  component_version text NOT NULL,             -- LOGICAL FK → pipeline_component_versions(version); the version this attempt ran
  content_hash    text NOT NULL,               -- sha256 carried for diagnostics/replay; = doc raw-bytes hash, or parent-hash+salt for sub-document targets
  status          processing_status NOT NULL DEFAULT 'pending',
  attempts        smallint NOT NULL DEFAULT 0, -- Cloud Tasks retries so far
  max_attempts    smallint NOT NULL DEFAULT 2, -- per-stage retry budget (D12 starting point, tunable per stage — not a committed constant); ≥ this and still failing ⇒ dead_letter
  last_error      text,                        -- truncated error of the most recent failure
  payload         jsonb,                       -- enqueue payload, kept for DLQ inspection / manual replay
  enqueued_at     timestamptz NOT NULL DEFAULT now(),
  started_at      timestamptz,
  finished_at     timestamptz,
  UNIQUE (deployment_id, target_kind, target_id, stage, component_version)
);
COMMENT ON TABLE processing_state IS
  'Per-(target,stage,version) idempotency + status ledger (D12). No-op iff a succeeded row exists for the same (deployment,target_kind,target_id,stage,component_version). The DLQ is the rows with status=dead_letter; bounded retries then DLQ — failures never disappear.';
CREATE INDEX ix_procstate_dlq      ON processing_state (deployment_id, stage) WHERE status = 'dead_letter';
CREATE INDEX ix_procstate_runnable ON processing_state (deployment_id, status, stage) WHERE status IN ('pending','failed');
CREATE INDEX ix_procstate_target   ON processing_state (target_kind, target_id);

-- ─────────────────────────────────────────────────────────────────────────
-- cost_ledger — per-invocation cost/latency metering for enforced per-layer budgets (§8 overall).
-- A succeeded-but-ack-lost call must not be re-billed on the Cloud Tasks retry, so a ledger row is
-- anchored to a single logical call by (target,stage,version,attempt); enforcement reads the
-- deduplicated total.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE cost_ledger (
  cost_id         uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  stage           pipeline_stage NOT NULL,     -- which layer/stage incurred the spend
  target_kind     processing_target,           -- optional: what was being processed
  target_id       uuid,                        -- LOGICAL FK → target
  component_version text,                       -- LOGICAL FK → pipeline_component_versions(version)
  attempt         smallint NOT NULL DEFAULT 0, -- the processing_state.attempts this call belongs to (dedup anchor)
  model_name      text,                        -- model billed
  tier            text,                        -- cascade rung that fired (e.g. 'T4-small','T4-frontier','selection','decontext') — cost scales with ambiguity (D4/D17)
  tokens_in       bigint,                      -- prompt tokens (incl. cached-prefix accounting where applicable)
  tokens_out      bigint,                      -- completion tokens
  cost_usd        numeric(12,6),               -- billed cost in USD
  latency_ms      integer,                     -- wall-clock of the call
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deployment_id, target_kind, target_id, stage, component_version, attempt)  -- one billed row per logical call+attempt (no double-count on retry)
);
COMMENT ON TABLE cost_ledger IS
  'Append-only spend/latency per LLM/embedding call, for per-layer dashboards + enforced budgets (overall §8). Idempotent per (target,stage,version,attempt) so a retried-but-already-billed call cannot double-count; budget enforcement reads the deduplicated total.';
CREATE INDEX ix_cost_layer_time ON cost_ledger (deployment_id, stage, occurred_at);
```

---

## 3. Ontology & predicate registry (D5, D15, D18)

The **governed vocabulary**: entity types and predicates, their hierarchy (extend-never-fork), and
the **domain/range signatures** that mechanically reject extraction hallucinations
(`works_for: Person → Organization`). This is *content, not new machinery* (D15) — prompts render
from these rows. The core is identical in every deployment; **extension packs** and **scopes** add
to it per deployment.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- extension_packs — system-shipped sets of types+predicates a deployment enables as a unit.
-- "Extensions are not second-class" (registries §4): full entity status, governance tier only.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE extension_packs (
  pack_id         text PRIMARY KEY,            -- stable pack handle: 'work' | 'legal' | 'systems' | ...
  name            text NOT NULL,
  description     text NOT NULL,               -- what the pack is for and which deployments want it
  is_system       boolean NOT NULL DEFAULT true -- shipped with the system vs deployment-defined
);
COMMENT ON TABLE extension_packs IS
  'Predefined bundles of extension types/predicates (registries §4) — e.g. the Work pack (Task/Decision/Goal). Enabling a pack inserts its registry rows for a deployment.';

CREATE TABLE deployment_extension_packs (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  pack_id         text NOT NULL REFERENCES extension_packs,
  enabled_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (deployment_id, pack_id)
);
COMMENT ON TABLE deployment_extension_packs IS 'Which packs each deployment has enabled (registries §1: core + chosen packs + own scopes).';

-- ─────────────────────────────────────────────────────────────────────────
-- scopes — K2 special-purpose lenses over the one shared entity space (D16).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE scopes (
  scope_id        uuid NOT NULL,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  slug            text NOT NULL,               -- 'people' | 'product-atlas' | ...
  name            text NOT NULL,
  description     text,
  git_path        text,                        -- directory in the K-plane repo this scope compiles into (K2)
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (scope_id),
  UNIQUE (deployment_id, scope_id),            -- composite-FK target (tenancy isolation, §0)
  UNIQUE (deployment_id, slug)
);
COMMENT ON TABLE scopes IS
  'K2 scopes (D16): perspectives over shared evidence. "Scopes multiply; truth doesn''t" — a scope is registry rows + a view definition + a git directory, never a new database.';

-- ─────────────────────────────────────────────────────────────────────────
-- entity_types — the typed-entity vocabulary (8-type core + pack/scope extensions, D18).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE entity_types (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  type            text NOT NULL,               -- 'Person','Organization',... ; extension subtypes like 'ResearchPaper'
  parent_type     text,                        -- extend-never-fork: every extension declares a core parent (D15); NULL only for the 8 core roots
  description     text NOT NULL,               -- plain-language meaning, rendered into extraction prompts (D15)
  examples        text[] NOT NULL DEFAULT '{}',-- few-shot examples rendered into prompts
  schema_org_ref  text,                        -- schema.org anchor (D18); spot-checked before freezing
  tier            ontology_tier NOT NULL,      -- core | extension | other | deprecated (the three speeds, D15)
  pack_id         text REFERENCES extension_packs, -- non-null if from an extension pack
  scope_id        uuid,                        -- non-null if defined by a single K2 scope
  status          ontology_status NOT NULL DEFAULT 'active',
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (deployment_id, type),
  FOREIGN KEY (deployment_id, parent_type) REFERENCES entity_types (deployment_id, type),
  FOREIGN KEY (deployment_id, scope_id)    REFERENCES scopes (deployment_id, scope_id) ON DELETE SET NULL (scope_id)
);
COMMENT ON TABLE entity_types IS
  'Governed entity-type registry (D15/D18). 8 schema.org-aligned core roots + pack/scope extensions, each anchored to a core parent (extend-never-fork) so blocking and cross-scope queries always fall back to the core level.';
CREATE INDEX ix_entity_types_parent ON entity_types (deployment_id, parent_type);

-- ─────────────────────────────────────────────────────────────────────────
-- governed_relationships — the ONE governed relationship vocabulary (D43): predicates (entity-range)
-- AND attributes (literal-range) in one registry, discriminated by range_kind. The adjudicator and
-- the facts table see one shape. Same D5 governance for both ranges (synonyms, tier, other:-escape,
-- usage_count promotion funnel). entity-range rows keep predicate_signatures (the D18 edge_type_map);
-- literal-range rows carry the value_domain (drives normalization), identity_qualifiers, the
-- default_valid_kind (the D43 supersedable gate input), and cardinality (single|set).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE governed_relationships (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  rel_key         text NOT NULL,               -- 'works_for' (entity) | 'fiscal_revenue','headcount' (literal) | 'other:<freetext>' (tier='other')
  range_kind      fact_object_kind NOT NULL,   -- entity => predicate (object is an entity, graph-eligible); literal => attribute (object is a value)
  parent_key      text,                        -- extend-never-fork anchor (default parent 'related_to' for entity range, D18)
  description     text NOT NULL,               -- rendered into the extraction/normalization prompt (D5/D15)
  examples        text[] NOT NULL DEFAULT '{}',
  synonyms        text[] NOT NULL DEFAULT '{}',-- surface variants the normalizer maps onto this key (works_at/employed_by → works_for) — D5
  schema_org_ref  text,                        -- entity range: schema.org anchor (D18)
  tier            ontology_tier NOT NULL,      -- core | extension | other | deprecated (three speeds, D5)
  pack_id         text REFERENCES extension_packs,
  scope_id        uuid,                        -- composite FK to scopes (set NULL on scope delete)
  usage_count     bigint NOT NULL DEFAULT 0,   -- cached count of facts using this key; ranks tier='other' for promotion (D5 funnel)
  is_change_prone boolean NOT NULL DEFAULT false, -- entity range: employment/affiliation change over time ⇒ supersession-relevant (D18)
  exclude_from_graph_distance boolean NOT NULL DEFAULT false, -- entity range: causal/promiscuous predicates excluded from graph-distance rerank (registries §4)
  -- literal-range only (NULL for entity range):
  value_domain    attribute_value_domain,      -- money|date|quantity|count|ratio|string_enum|boolean — drives DETERMINISTIC value normalization
  unit_dimension  text,                        -- 'currency'|'persons'|'percent' — guards cross-unit false conflict
  identity_qualifiers text[] NOT NULL DEFAULT '{}', -- qualifier keys that are IDENTITY-bearing (geography, accounting_basis) ⇒ different slot, not a conflict
  default_valid_kind claim_valid_kind,         -- THE D43 GATE INPUT: effective_period ⇒ supersedable state; measurement_period ⇒ both-stand; event_time ⇒ date-is-value
  cardinality     text NOT NULL DEFAULT 'set',  -- single (a new value/object supersedes) | set (coexist). PERMISSIVE default 'set': an undeclared relationship coexists (never over-rejects); a stateful one that should supersede DECLARES 'single' (a forgotten 'single' conservatively both-stands, never silently overwrites)
  status          ontology_status NOT NULL DEFAULT 'active',
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (deployment_id, rel_key),
  -- (rel_key, range_kind) is unique-by-construction (rel_key already unique); exposed as a constraint so
  -- parent_key and predicate_signatures can FK on range_kind and thereby never cross entity↔literal:
  UNIQUE (deployment_id, rel_key, range_kind),
  -- extend-never-fork parent must be the SAME range_kind (a literal attribute can't parent to an entity
  -- predicate, which would dangle in the range-filtered compatibility views):
  FOREIGN KEY (deployment_id, parent_key, range_kind)
              REFERENCES governed_relationships (deployment_id, rel_key, range_kind),
  FOREIGN KEY (deployment_id, scope_id)   REFERENCES scopes (deployment_id, scope_id) ON DELETE SET NULL (scope_id),
  CHECK (cardinality IN ('single','set')),   -- single (a new value/object supersedes) | set (coexist); applies to BOTH ranges (D43)
  -- Full range-kind split (D43) — the registry, not the writer, is the source of truth for a fact's
  -- time-semantics, so the gate inputs must be present & valid here. A LITERAL relationship MUST declare
  -- its value_domain (drives normalization) AND its default_valid_kind (the supersedable-gate input); an
  -- ENTITY relationship MUST NOT carry literal-only fields (they would be meaningless on an edge):
  CHECK ( (range_kind = 'literal' AND value_domain IS NOT NULL AND default_valid_kind IS NOT NULL)
       OR (range_kind = 'entity'  AND value_domain IS NULL AND unit_dimension IS NULL
            AND default_valid_kind IS NULL AND identity_qualifiers = '{}') )
);
COMMENT ON TABLE governed_relationships IS
  'D43 unified relationship vocabulary: predicates (range_kind=entity, keep predicate_signatures/D18 edge_type_map) + attributes (range_kind=literal, carry value_domain + identity_qualifiers + default_valid_kind + cardinality), one registry. predicates/attributes below are D43 COMPATIBILITY VIEWS over this table; facts.rel_key and predicate_signatures FK here. Same D5 governance + other:-escape + usage_count promotion for both ranges.';
CREATE INDEX ix_govrel_other ON governed_relationships (deployment_id, usage_count DESC) WHERE tier = 'other';  -- promotion-candidate ranking
CREATE INDEX ix_govrel_range ON governed_relationships (deployment_id, range_kind);

-- GATE-FIELD IMMUTABILITY (D43): facts denormalize valid_kind/cardinality/range_kind from here and are
-- NOT auto-recomputed, so silently editing a relationship's gate fields would strand existing facts in
-- the wrong exclusion arm. Reject such edits once any fact uses the key; changing the semantics of a
-- live relationship is a deliberate, audited rebuild migration (re-derive the affected facts from their
-- immutable claims — rebuild-first, like the projections), not an in-place UPDATE.
CREATE FUNCTION govrel_freeze_gate_fields() RETURNS trigger AS $$
BEGIN
  -- ALL fields that facts derive from: the gate inputs (range_kind/default_valid_kind/cardinality) AND
  -- the normalization inputs (value_domain/unit_dimension/identity_qualifiers) — changing the latter
  -- after facts exist would strand existing object_value_identity / qualifiers_hash under old slot rules.
  IF (NEW.range_kind, NEW.default_valid_kind, NEW.cardinality,
      NEW.value_domain, NEW.unit_dimension, NEW.identity_qualifiers)
     IS DISTINCT FROM
     (OLD.range_kind, OLD.default_valid_kind, OLD.cardinality,
      OLD.value_domain, OLD.unit_dimension, OLD.identity_qualifiers)
     AND EXISTS (SELECT 1 FROM facts
                  WHERE deployment_id = OLD.deployment_id AND rel_key = OLD.rel_key) THEN
    RAISE EXCEPTION 'governed_relationships: cannot change fact-derivation fields (range_kind/default_valid_kind/cardinality/value_domain/unit_dimension/identity_qualifiers) of % while facts reference it (rebuild-migrate instead)', OLD.rel_key;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_govrel_freeze_gate BEFORE UPDATE ON governed_relationships
  FOR EACH ROW EXECUTE FUNCTION govrel_freeze_gate_fields();

-- HARD read-only guard for the D43 compatibility/projection views (`predicates`, `attributes`,
-- `relations`). A simple view is auto-updatable in PG, and REVOKE is bypassable by a role with direct
-- grants or by the owner; an INSTEAD OF trigger raises on every write path regardless of role. Each view
-- below attaches this + a REVOKE belt. All writes go to the base table (one vocabulary/verdict home, D6).
CREATE FUNCTION reject_view_write() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% is a read-only D43 compatibility view — write to the base table (governed_relationships / facts)', TG_TABLE_NAME;
END $$ LANGUAGE plpgsql;

-- D43 COMPATIBILITY VIEWS (preserve every existing reader): `predicates` and `attributes` are realized
-- as read-only VIEWS over governed_relationships (defined below), NOT separate tables — there is ONE
-- vocabulary table. `predicate_signatures` and `facts` FK to governed_relationships (not the views; a
-- view cannot be an FK target). The view definitions below also document the columns each exposes.

-- ─────────────────────────────────────────────────────────────────────────
-- predicates — the governed relation vocabulary (D5/D18). related_to is the core parent.
-- [D43: now a compatibility VIEW over governed_relationships WHERE range_kind='entity' — see above.]
-- The other:<freetext> escape (D5) is materialized here too: when the normalizer encounters an
-- other:<value>, it UPSERTs a row with tier='other' (so relations.predicate's FK holds AND the
-- promotion funnel is countable via usage_count). Domain/range is NOT enforced for tier='other'
-- rows until a periodic job promotes them (registries §4/§7).
-- ─────────────────────────────────────────────────────────────────────────
-- D43: `predicates` is a READ-ONLY VIEW over governed_relationships (the entity-range subset), NOT a
-- second table. The columns it exposes (and their old names) are mapped below; every pre-D43 reader
-- (prompt rendering, promotion job, graph build) keeps working unchanged. There is exactly ONE
-- vocabulary table (governed_relationships); writes/upserts (incl. the other:<freetext> escape) go
-- there, and `governed_relationships.ix_govrel_other` already ranks tier='other' for promotion.
CREATE VIEW predicates AS
  SELECT deployment_id,
         rel_key                     AS predicate,
         parent_key                  AS parent_predicate,
         description, examples, synonyms, schema_org_ref, tier, pack_id, scope_id,
         usage_count, is_change_prone, exclude_from_graph_distance, status, created_at
  FROM governed_relationships
  WHERE range_kind = 'entity';
COMMENT ON VIEW predicates IS
  'D43 compatibility view = governed_relationships WHERE range_kind=''entity''. Governed predicate vocabulary (D5/D18); extraction is constrained to these names with an other:<freetext> escape upserted into governed_relationships as tier=other (usage_count makes the promotion funnel queryable). related_to is the permissive core parent. Read-only — write to governed_relationships.';
CREATE TRIGGER trg_predicates_ro INSTEAD OF INSERT OR UPDATE OR DELETE ON predicates
  FOR EACH ROW EXECUTE FUNCTION reject_view_write();
REVOKE INSERT, UPDATE, DELETE ON predicates FROM PUBLIC;

-- ─────────────────────────────────────────────────────────────────────────
-- predicate_signatures — the domain/range gate (Graphiti edge_type_map shape, D18).
-- A child table because a predicate may allow several (subject_type,object_type) pairs. ENFORCEMENT
-- is by the NORMALIZER at E3 write time (application-enforced, not a per-insert DB trigger — at 10⁸
-- relations a trigger walking the type hierarchy on every write is too costly): the normalizer
-- resolves the subject/object entity types, walks each up its parent chain (extend-never-fork), and
-- accepts the relation only if some signature matches at any ancestor level. A relation that fails
-- is DROPPED — and is re-derivable from its immutable claim if the entity is later retyped, so no
-- quarantine table is needed (registries §4). (An optional BEFORE INSERT trigger may be added as a
-- belt-and-braces backstop in low-throughput deployments.)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE predicate_signatures (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  predicate       text NOT NULL,               -- the predicate this signature constrains
  range_kind      fact_object_kind NOT NULL DEFAULT 'entity' CHECK (range_kind = 'entity'),  -- constant: a signature only exists for an ENTITY-range predicate
  subject_type    text NOT NULL,               -- allowed subject entity_type (matched at this level OR any descendant via the normalizer's parent walk)
  object_type     text NOT NULL,               -- allowed object entity_type
  PRIMARY KEY (deployment_id, predicate, subject_type, object_type),
  -- D43: FK targets the ONE vocabulary table (a view cannot be an FK target). Carrying the constant
  -- range_kind='entity' in the composite FK PROVES the referenced relationship is entity-range — a
  -- literal attribute can never acquire a domain/range signature:
  FOREIGN KEY (deployment_id, predicate, range_kind)
              REFERENCES governed_relationships (deployment_id, rel_key, range_kind) ON DELETE CASCADE,
  FOREIGN KEY (deployment_id, subject_type) REFERENCES entity_types (deployment_id, type),
  FOREIGN KEY (deployment_id, object_type)  REFERENCES entity_types (deployment_id, type)
);
COMMENT ON TABLE predicate_signatures IS
  'Allowed (subject_type → object_type) pairs per entity-range relationship — the one structural ontology gate (D18), enforced by the normalizer (parent-chain walk) at E3 write time. FK → governed_relationships (D43). Subtypes inherit a parent''s signatures; a relation matching none is dropped (re-derivable from its claim).';

-- ─────────────────────────────────────────────────────────────────────────
-- attributes — the governed ATTRIBUTE/MEASURE vocabulary (D42), a PEER of `predicates`.
-- [D43: folded into governed_relationships (range_kind='literal') + realized as a compatibility VIEW;
--  its value_domain/identity_qualifiers/default_valid_kind/cardinality now live on governed_relationships,
--  and facts.rel_key (literal arm) FKs there. The block below documents the view's columns.]
-- A predicate relates two ENTITIES (D18 bars literal objects); an attribute attaches a LITERAL/
-- quantity to ONE entity — the literal-range home D18 deliberately keeps off predicates ("founded_date",
-- "fiscal_revenue", "headcount"). Same D5 governance as predicates (synonyms, tier, other:-escape,
-- usage_count promotion funnel). The typed value_domain drives DETERMINISTIC value normalization so
-- "$5M" and "5,000,000 USD" are recognized as the same value (not a phantom conflict). Needed because
-- detecting "is this the same attribute?" (revenue vs net revenue vs sales) is an ontology question —
-- free-text keys would fragment like free-text predicates and SILENTLY miss conflicts (D42 §3.1).
-- ─────────────────────────────────────────────────────────────────────────
-- D43: `attributes` is a READ-ONLY VIEW over governed_relationships (the literal-range subset), NOT a
-- second table. value_domain/default_valid_kind/identity_qualifiers/cardinality now live on
-- governed_relationships; writes (incl. the other:<freetext> escape) go there, and ix_govrel_other
-- ranks tier='other' for promotion.
CREATE VIEW attributes AS
  SELECT deployment_id,
         rel_key             AS attribute_key,
         parent_key          AS parent_attribute,
         description, value_domain, unit_dimension, default_valid_kind, identity_qualifiers,
         cardinality, synonyms, examples, tier, pack_id, scope_id, usage_count, status, created_at
  FROM governed_relationships
  WHERE range_kind = 'literal';
COMMENT ON VIEW attributes IS
  'D43 compatibility view = governed_relationships WHERE range_kind=''literal''. Governed attribute/measure vocabulary (D42), the literal-range home D18 keeps off predicates. value_domain drives deterministic value normalization; identity_qualifiers say which qualifiers are conflict-bearing; default_valid_kind feeds the supersedable gate. Read-only — write to governed_relationships.';
CREATE TRIGGER trg_attributes_ro INSTEAD OF INSERT OR UPDATE OR DELETE ON attributes
  FOR EACH ROW EXECUTE FUNCTION reject_view_write();
REVOKE INSERT, UPDATE, DELETE ON attributes FROM PUBLIC;

-- ─────────────────────────────────────────────────────────────────────────
-- scope_interests — registry-declared scope views + extraction interests (D16).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE scope_interests (
  interest_id     uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  scope_id        uuid NOT NULL,
  interest_type   scope_interest_kind NOT NULL, -- entity_type | predicate | metadata | keyword
  value           text NOT NULL,                -- the type name / predicate / metadata key / keyword
  UNIQUE (scope_id, interest_type, value),
  FOREIGN KEY (deployment_id, scope_id) REFERENCES scopes (deployment_id, scope_id) ON DELETE CASCADE
);
COMMENT ON TABLE scope_interests IS
  'Per-scope interest list (D16): the predicate/type footprint that defines the scope''s PROJECT_GRAPH_CYPHER view and what its K2 compilation selects. A query/compile-time selection over fully-extracted facts — never a promotion trigger (D28 withdrawn).';
```

The **seed core** (D18) — 8 entity types and 14 predicates with signatures — is data inserted by a
migration, not schema. Its authoritative list is in `registries_design.md` §4; the seeding
migration cites that section rather than duplicating it here (avoids drift).

---

## 4. Entity registry & resolution (D17–D24)

The identity authority. The **transcript/verdict** epistemics of D2/D3 apply (`entity_registry.md`
§4): **mentions are evidence** (immutable), **entities are verdicts** (re-adjudicable),
**resolution is replayable**. The governing asymmetry is **under-merging degrades gradually;
over-merging poisons catastrophically**, so everything is recall-conservative and reversible.
"Blocking" (cheaply narrowing the candidate-match set so you avoid an all-pairs comparison) is
defined in `concepts.md` §6.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- entities — the canonical registry. entity_id is NEVER reused; a merge is a redirect
-- (merged_into), never a rewrite (Wikidata model). UNIQUE(deployment_id, entity_id) is the
-- composite-FK target that keeps every entity reference inside one deployment (§0).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE entities (
  entity_id       uuid PRIMARY KEY,            -- canonical identity; never reused (D17); flows downstream to Lance/Ladybug
  deployment_id   uuid NOT NULL REFERENCES deployments,
  type            text NOT NULL,               -- canonical type = majority/highest-confidence vote across mentions (registries §4)
  canonical_name  text NOT NULL,               -- preferred display/blocking name; mirrored as an alias row (invariant below)
  normalized_name text NOT NULL,               -- unaccent+lower(canonical_name)
  status          entity_status NOT NULL DEFAULT 'active', -- active | merged | retired
  merged_into     uuid,                        -- redirect target when status=merged; follow the chain to the survivor (D21)
  type_confidence real,                        -- confidence of the type vote; low + cross-mention disagreement ⇒ over-merge signal (registries §4)
  profile_summary text,                        -- short registry-maintained blurb; improves future LLM adjudication (Graphiti lesson)
  profile_embedding_ref text,                  -- opaque Lance key for the profile embedding used in T3 (no vectors in PG/graph — D6/D8)
  mention_count   integer NOT NULL DEFAULT 0,  -- cached |mentions|; half of blast_radius (registries §6) and a health metric
  graph_degree    integer NOT NULL DEFAULT 0,  -- cached relation degree from the LATEST PUBLISHED P2 snapshot (§9); other half of blast_radius
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deployment_id, entity_id),           -- composite-FK target (tenancy isolation, §0)
  FOREIGN KEY (deployment_id, type) REFERENCES entity_types (deployment_id, type),
  FOREIGN KEY (deployment_id, merged_into) REFERENCES entities (deployment_id, entity_id), -- same-deployment redirect only
  CHECK ((status = 'merged') = (merged_into IS NOT NULL))  -- merged iff it redirects; an active/retired entity must NOT redirect
);
COMMENT ON TABLE entities IS
  'Canonical entity registry (D17/D21). entity_id never reused; merges are redirects via merged_into (un-mergeable), not rewrites. type is the cross-mention vote; mention_count+graph_degree cache the blast-radius inputs for review gating (registries §6/§8).';
CREATE INDEX ix_entities_type     ON entities (deployment_id, type);
CREATE INDEX ix_entities_redirect ON entities (merged_into) WHERE merged_into IS NOT NULL;
-- entities is searchable by name but the PRIMARY blocking index lives on aliases (below). This
-- composite GIN (deployment_id leading, via btree_gin) keeps name search tenant-scoped:
CREATE INDEX ix_entities_name_trgm ON entities USING gin (deployment_id, normalized_name gin_trgm_ops);

-- ─────────────────────────────────────────────────────────────────────────
-- aliases — surface forms per entity, the BLOCKING TARGET (D23). Includes the LLM-emitted
-- canonical form (provenance=llm_canonical) on which T0 exact-match runs. INVARIANT: each entity's
-- canonical_name exists as an alias row, so the cascade scans aliases only. Deliberately NOT
-- partitioned (≤10⁷, D23) so its GIN trigram/phonetic indexes can live on it.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE aliases (
  alias_id        uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  entity_id       uuid NOT NULL,               -- composite FK below (same-deployment)
  alias_text      text NOT NULL,               -- surface form as seen / as canonicalized
  normalized_lemma text NOT NULL,              -- unaccent+lower (and LLM nominative form for inflected langs, registries §5); the indexed match key
  provenance      alias_provenance NOT NULL,   -- source (observed in a document) | llm_canonical (extractor-emitted nominative form)
  confidence      real,                        -- confidence this surface really names this entity
  first_seen      timestamptz NOT NULL DEFAULT now(),
  last_seen       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deployment_id, entity_id, normalized_lemma, provenance),
  FOREIGN KEY (deployment_id, entity_id) REFERENCES entities (deployment_id, entity_id) ON DELETE CASCADE
);
COMMENT ON TABLE aliases IS
  'Surface forms per entity and the blocking target for resolution (D17/D23). T0 exact-matches the llm_canonical lemma; T1 trigram-blocks and T2 phonetic-blocks on normalized_lemma. Not partitioned so its GIN indexes are usable.';
-- The two blocking indexes (D17/D23). Composite (deployment_id leading, via btree_gin) so a
-- per-deployment blocking query — `WHERE deployment_id=$d AND normalized_lemma % $1` (trigram) or
-- `WHERE deployment_id=$d AND daitch_mokotoff(normalized_lemma) && daitch_mokotoff($1)` (phonetic)
-- — is satisfied inside the index, never scanning other deployments' aliases (tenancy + selectivity,
-- §0). [Refines the single-column form in D23/registries §9 for the single-DB realization — see §17.]
CREATE INDEX ix_aliases_lemma_trgm  ON aliases USING gin (deployment_id, normalized_lemma gin_trgm_ops);
CREATE INDEX ix_aliases_lemma_dm    ON aliases USING gin (deployment_id, daitch_mokotoff(normalized_lemma));
CREATE INDEX ix_aliases_lemma_exact ON aliases (deployment_id, normalized_lemma);  -- T0 exact match
CREATE INDEX ix_aliases_entity      ON aliases (entity_id);

-- ─────────────────────────────────────────────────────────────────────────
-- generic_identifier_guard — the Senzing "promiscuous signal" guard (D21/registries §6).
-- Keyed by the normalized string (not a single alias row): the property "links to MANY distinct
-- entities ⇒ generic not identifying" is about the string across the registry.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE generic_identifier_guard (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  normalized_lemma text NOT NULL,              -- the suspect surface string
  distinct_entity_count integer NOT NULL,      -- how many distinct entities it currently links — the tell
  is_downweighted boolean NOT NULL DEFAULT true, -- stop trusting it as a blocking/match signal
  reason          text,                        -- 'role-address' | 'placeholder' | 'common-name' | ...
  evaluated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (deployment_id, normalized_lemma)
);
COMMENT ON TABLE generic_identifier_guard IS
  'Surfaces that link too many entities to be identifying (D21). Down-weighted so they stop driving merges; the merges they already caused are re-evaluated — enumerated via merge_events.trigger_lemmas (below).';

-- ─────────────────────────────────────────────────────────────────────────
-- resolution_exclusions — negative/"these are NOT the same" edges (D21).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE resolution_exclusions (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  entity_id_low   uuid NOT NULL,               -- least(a,b) — canonical ordering keeps the pair unique
  entity_id_high  uuid NOT NULL,               -- greatest(a,b)
  reason          text,                        -- why they are known-distinct (evidence / reviewer note)
  created_by      decision_actor NOT NULL,     -- auto | human
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (deployment_id, entity_id_low, entity_id_high),
  CHECK (entity_id_low < entity_id_high),
  FOREIGN KEY (deployment_id, entity_id_low)  REFERENCES entities (deployment_id, entity_id),
  FOREIGN KEY (deployment_id, entity_id_high) REFERENCES entities (deployment_id, entity_id)
);
COMMENT ON TABLE resolution_exclusions IS
  'Adjudicated non-match constraints (D21): block re-proposing a merge the clusterer or a human ruled out (two J. Smiths, father/son). Consulted by the cascade and clustering.';

-- ─────────────────────────────────────────────────────────────────────────
-- resolver_versions — per-version tier config + per-type thresholds (D17/D22).
-- Also the home of the review-routing band boundaries (auto-accept ceiling / hub-merge floor, D24).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE resolver_versions (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  resolver_version text NOT NULL,              -- e.g. 'resolver-2026-03a'
  tier_config     jsonb NOT NULL,              -- T0–T4 enable/order, blocking floors, escalation bands, review band boundaries + hub-merge blast-radius cutoff (D24)
  thresholds_by_type jsonb NOT NULL,           -- per-entity-type accept/reject bands (golden-set-measured, D22) — starting points, not constants
  configured_at   timestamptz NOT NULL DEFAULT now(),
  notes           text,
  PRIMARY KEY (deployment_id, resolver_version)
);
COMMENT ON TABLE resolver_versions IS
  'Versioned, per-type resolution thresholds + tier config + review-routing bands (D17/D22/D24). Block-loose/decide-tight; thresholds are golden-set-measured starting points to be re-measured, never committed constants.';

-- ─────────────────────────────────────────────────────────────────────────
-- mentions — the immutable transcript: every entity mention as extracted (D17). ~10⁸ rows ⇒
-- monthly RANGE partition by created_at; btree-only; logical FKs (D23). Queried by id/claim_id/
-- doc_id, never fuzzy-scanned (the fuzzy index lives on aliases). Partition pruning for id lookups:
-- §12.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE mentions (
  mention_id      uuid NOT NULL,               -- PK component (with created_at)
  deployment_id   uuid NOT NULL,               -- LOGICAL FK → deployments
  surface_form    text NOT NULL,               -- the mention exactly as it appeared
  normalized_lemma text NOT NULL,              -- unaccent+lower of surface_form
  canonical_name_form text,                    -- LLM-emitted nominative/canonical form at extraction (registries §5) — feeds T0 + becomes an llm_canonical alias
  emitted_type    text,                        -- entity type the extractor emitted for this mention (registry-constrained)
  type_confidence real,                        -- extractor confidence in emitted_type
  context         text,                        -- short surrounding snippet for adjudication/audit (not the document body)
  language        text,                        -- mention language (per-deployment multilingual path, registries §5)
  claim_id        uuid,                        -- LOGICAL FK → claims; the claim this mention occurs in
  chunk_id        uuid,                        -- LOGICAL FK → chunks
  doc_id          uuid NOT NULL,               -- LOGICAL FK → documents
  char_start      integer,                     -- mention offset into the document markdown
  char_end        integer,
  created_at      timestamptz NOT NULL DEFAULT now(),  -- partition key (ingest month)
  PRIMARY KEY (mention_id, created_at)
) PARTITION BY RANGE (created_at);
COMMENT ON TABLE mentions IS
  'Immutable transcript of entity mentions (D17). Evidence for resolution verdicts; never edited. Monthly-partitioned, btree-only, logical FKs (D23). canonical_name_form is the LLM nominative form feeding T0 (registries §5).';
CREATE INDEX ix_mentions_claim ON mentions (claim_id);
CREATE INDEX ix_mentions_doc   ON mentions (deployment_id, doc_id);

-- ─────────────────────────────────────────────────────────────────────────
-- resolution_decisions — append-only verdict (D17). A better resolver SUPERSEDES (superseded_by),
-- never overwrites. ~10⁸ rows ⇒ monthly partition by decided_at; logical FKs (D23).
-- method ∈ {T0,T3,T4_small,T4_frontier,human}: T1/T2 are BLOCKING (candidate generation), never a
-- decision (D17 block-loose/decide-tight) — enforced by the CHECK below; which blocking tier
-- surfaced a candidate is recorded inside features.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE resolution_decisions (
  decision_id     uuid NOT NULL,
  deployment_id   uuid NOT NULL,               -- LOGICAL FK → deployments
  mention_id      uuid NOT NULL,               -- LOGICAL FK → mentions
  entity_id       uuid NOT NULL,               -- LOGICAL FK → entities; the resolved canonical id
  method          resolution_tier NOT NULL,    -- T0 | T3 | T4_small | T4_frontier | human (NOT T1/T2 — see CHECK)
  confidence      real NOT NULL,               -- tier confidence; bands per resolver_versions.thresholds_by_type
  is_new_entity   boolean NOT NULL DEFAULT false, -- true if this decision minted a new entity (no confident match)
  features        jsonb,                       -- evidence used (trigram/phonetic/cosine scores incl. the surfacing blocking tier, LLM rationale)
  resolver_version text NOT NULL,              -- LOGICAL FK → resolver_versions; pins the thresholds in force
  decided_by      decision_actor NOT NULL DEFAULT 'auto',
  decided_at      timestamptz NOT NULL DEFAULT now(),  -- partition key
  superseded_by   uuid,                        -- LOGICAL FK → resolution_decisions; set when a later decision replaces this one
  PRIMARY KEY (decision_id, decided_at),
  CHECK (method NOT IN ('T1','T2'))            -- T1/T2 are candidate generation, never a verdict (D17)
) PARTITION BY RANGE (decided_at);
COMMENT ON TABLE resolution_decisions IS
  'Append-only resolution verdicts (D17/D21). Replaced by superseded_by, never overwritten — re-adjudicable. Monthly-partitioned, logical FKs (D23). method excludes the blocking tiers T1/T2 (block-loose/decide-tight); features keeps the per-tier evidence for audit.';
CREATE INDEX ix_resdec_mention ON resolution_decisions (mention_id);
CREATE INDEX ix_resdec_entity  ON resolution_decisions (deployment_id, entity_id);
CREATE INDEX ix_resdec_live    ON resolution_decisions (mention_id) WHERE superseded_by IS NULL;

-- ─────────────────────────────────────────────────────────────────────────
-- merge_events — append-only reversibility record (D21). Snapshots pre-merge membership so
-- un-merge replays it. trigger_lemmas makes the generic-identifier-guard re-evaluation queryable
-- (registries §6: "the merges a downweighted signal caused are re-evaluated"). Not huge ⇒ real
-- composite FKs, no partition.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE merge_events (
  merge_id        uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  survivor_id     uuid NOT NULL,               -- the entity that absorbed the other
  absorbed_id     uuid NOT NULL,               -- the entity redirected into survivor (keeps its id, status=merged)
  trigger_lemmas  text[] NOT NULL DEFAULT '{}',-- the blocking lemma(s) that drove this merge — enumerated for guard re-evaluation (D21, registries §6)
  evidence        jsonb,                       -- why the merge fired (scores, reviewer note)
  blast_radius    integer,                     -- combined mention_count+degree at merge time (registries §6) — never auto-merge above threshold
  pre_merge_membership_snapshot jsonb NOT NULL,-- which mentions belonged to which entity BEFORE the merge — replay to un-merge (D21)
  decided_by      decision_actor NOT NULL DEFAULT 'auto', -- hub merges never auto (registries §6/§8)
  decided_at      timestamptz NOT NULL DEFAULT now(),
  reversed_by     uuid REFERENCES merge_events,-- the un-merge event that undid this one, if any
  FOREIGN KEY (deployment_id, survivor_id) REFERENCES entities (deployment_id, entity_id),
  FOREIGN KEY (deployment_id, absorbed_id) REFERENCES entities (deployment_id, entity_id)
);
COMMENT ON TABLE merge_events IS
  'Append-only merge log enabling un-merge (D21) — the capability no OSS ER system ships. pre_merge_membership_snapshot is the "before" picture replayed to reverse; trigger_lemmas lets the generic-identifier guard re-evaluate affected merges; P2 rebuild re-points the graph for free.';
CREATE INDEX ix_merge_survivor ON merge_events (survivor_id);
CREATE INDEX ix_merge_absorbed ON merge_events (absorbed_id);
CREATE INDEX ix_merge_trigger  ON merge_events USING gin (trigger_lemmas); -- guard re-evaluation by lemma
```

---

## 5. Review queue, golden set & evaluation (D22, D24, O6)

Resolution quality is a *measured pipeline property*. Three first-class assets: the **cluster-
review queue** (D24 — review clusters, not pairs; route only the middle impact band to humans), the
**golden EVAL set** (D22 — unbiased, human-adjudicated, held separate from any future training
set), and the **eval-run history** (per-tier metrics with Wilson confidence intervals).

> **Wilson interval** (used below) = a small-sample-robust error bar on a proportion like precision
> or recall, so a P/R figure measured on only ~200 golden pairs is not read as more precise than
> the sample supports (D22). **Splink waterfall** (used in the review payload) = the per-feature
> score breakdown a reviewer sees — how each signal (trigram, phonetic, embedding, shared context)
> raised or lowered the match score — which is what a human needs to adjudicate a cluster.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- review_queue — the thin Postgres-backed CLUSTER review queue (D24). An action here appends to
-- resolution_decisions / merge_events (the verdict tables); the queue holds proposals + status.
-- Band boundaries (auto-accept ceiling / review band / hub-merge no-auto-accept floor) live,
-- versioned, in resolver_versions.tier_config (so routing thresholds are auditable per version).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE review_queue (
  review_id       uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  item_kind       review_item_kind NOT NULL,   -- merge_cluster | split_cluster | type_conflict | generic_identifier | contradiction | attribute_conflict (D42)
  candidate       jsonb NOT NULL,              -- the cluster: entity/mention ids + the Splink-style per-feature score waterfall + cluster card; for attribute_conflict: the conflict_group + member attr_fact_ids
  blast_radius    integer NOT NULL,            -- combined size/connectedness if wrong (registries §6)
  confidence      real NOT NULL,               -- model confidence in the proposal
  expected_impact real NOT NULL,               -- blast_radius × (1−confidence) — the routing/ranking score (D24)
  status          review_status NOT NULL DEFAULT 'pending', -- pending | accepted | rejected | deferred | auto_resolved
  verdict         review_verdict,              -- outcome appropriate to item_kind (merge/split/pick_a/downweight/retype/...) ; non-merge kinds use the matching enum value or verdict_note
  verdict_note    text,
  assigned_to     text,                        -- reviewer handle
  result_decision_id uuid,                     -- LOGICAL FK → the resolution_decisions / merge_events / attribute conflict_group the verdict produced
  created_at      timestamptz NOT NULL DEFAULT now(),
  resolved_at     timestamptz,
  -- D42: an attribute conflict is surface-not-resolve — a human may confirm both sides stand or
  -- promote the fact to a relation, but may NEVER pick a winning value (that would be a forbidden
  -- claim-side current-value verdict; the believed value's only home is a promoted relation):
  CHECK (item_kind <> 'attribute_conflict' OR verdict IS NULL OR verdict IN ('both_stand','promote_to_relation','uncertain'))
);
COMMENT ON TABLE review_queue IS
  'Cluster-level human review queue (D24). Only the middle expected_impact band (boundaries in resolver_versions.tier_config) is routed to humans; hub merges never auto-accept. Verdicts append reversible, provenance-stamped rows to resolution_decisions/merge_events. verdict covers all item_kinds, not only merges.';
CREATE INDEX ix_review_pending ON review_queue (deployment_id, expected_impact DESC) WHERE status = 'pending';

-- ─────────────────────────────────────────────────────────────────────────
-- golden_pairs — the unbiased ER eval set (D22). Human-adjudicated (the cascade/LLM may propose,
-- only humans label — breaks circularity). expected_blocking_tier records the stratum so blocking
-- recall is measurable per tier (the "blocking-stratified" intent).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE golden_pairs (
  pair_id         uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  entity_type     text NOT NULL,               -- the type stratum this pair tests
  surface_a       text NOT NULL,               -- mention/alias A (stored as text so the set survives re-resolution)
  surface_b       text NOT NULL,
  context_a       text,                        -- disambiguating context for A
  context_b       text,
  label           golden_label NOT NULL,       -- match | no_match — the ground truth
  hardness        golden_hardness NOT NULL,    -- hard_positive | hard_negative | easy
  expected_blocking_tier resolution_tier,      -- which tier should surface this pair (exact/trigram/phonetic/embedding) — for per-stratum recall (D22)
  is_synthetic    boolean NOT NULL DEFAULT false, -- planted father/son/inflection/married-name case
  adjudicated_by  text NOT NULL,               -- human adjudicator (circularity guard, D22)
  created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE golden_pairs IS
  'Human-adjudicated ER evaluation pairs (D22). Measures P/R and tunes per-type thresholds; never used for training. expected_blocking_tier supports blocking-stratified recall. Stored as surface+context so it survives re-resolution.';
CREATE INDEX ix_golden_type ON golden_pairs (deployment_id, entity_type);

-- ─────────────────────────────────────────────────────────────────────────
-- golden_claim_labels — the E2 Selection verifiability golden set (D22/D25/D35).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE golden_claim_labels (
  label_id        uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  proposition     text NOT NULL,               -- the candidate proposition under test
  context         text,                        -- the bundle context it was judged in
  expected_outcome selection_outcome NOT NULL, -- keep | rewrite | drop | kept_flagged (D31/D35)
  protected_class text,                        -- never-drop class if any: 'quantity'|'date'|'named_entity_predicate'|'change_of_state' (D35)
  adjudicated_by  text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE golden_claim_labels IS
  'Human-labelled Selection cases (D22/D35): the verifiability golden set + planted never-drop canaries that fail CI if Selection drops them. Tunes per-fact false-drop, not a corpus average.';

-- ─────────────────────────────────────────────────────────────────────────
-- eval_runs — metrics history per resolver/extractor version, all suites (D22, O6 both halves).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE eval_runs (
  eval_run_id     uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  suite           eval_suite NOT NULL,         -- resolution | selection | grounding | retrieval | contradiction
  component_version text NOT NULL,             -- LOGICAL FK → pipeline_component_versions / resolver_versions; what was measured
  metrics         jsonb NOT NULL,              -- per-tier/per-type P/R with Wilson CIs; recall@k per recipe; rerank weights; per-fact false-drop
  passed          boolean,                     -- did the canary regression pass for this version?
  ran_at          timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE eval_runs IS
  'Evaluation history (D22/O6). Per-tier/per-type metrics with Wilson intervals for resolution; recall@k + rerank tuning for retrieval; per-fact false-drop for selection. A canary regression re-runs per version.';
CREATE INDEX ix_eval_suite_ver ON eval_runs (deployment_id, suite, ran_at);

-- ─────────────────────────────────────────────────────────────────────────
-- canary_cases — known-tricky regressions re-run per resolver/extractor version (registries §10).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE canary_cases (
  canary_id       uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  suite           eval_suite NOT NULL,
  description     text NOT NULL,               -- what tricky behavior this guards (e.g. 'inflected Czech surname must merge')
  input           jsonb NOT NULL,              -- the case input
  expected        jsonb NOT NULL,              -- the required outcome
  created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE canary_cases IS 'Regression canaries (registries §10): tricky cases re-run per version; a regression blocks the version from shipping.';
```

---

## 6. E0 — documents, sections, cross-references (D36–D40)

Bodies live in GCS (raw + artifacts buckets); Postgres holds **identity, versions, processing
state, artifact URIs, hashes, costs, and the section index** (D37) — never the body. Each E0
sub-worker (ingest → convert → structure → crossref, D36) is **separately versioned** and
idempotent on `content_hash + its own version`.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- documents — one row per ingested document. ID-addressed (doc_id + content_hash), never
-- title-addressed (D37). content_hash = sha256(raw bytes) is the idempotency key and the only
-- surviving dedup (D25). A hard-delete SOFT-TOMBSTONES the row (status='deleted', URIs nulled,
-- deleted_at set) rather than physically removing it (§13) — so the 'deleted' enum value and the
-- ix_documents_live partial index are meaningful, and logical-FK auditors can tell "forgotten"
-- from "never existed".
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE documents (
  doc_id          uuid PRIMARY KEY,            -- stable opaque document identity (used in GCS paths)
  deployment_id   uuid NOT NULL REFERENCES deployments,
  content_hash    text NOT NULL,               -- sha256 of raw bytes — idempotency key (D12); re-ingesting an identical file is a no-op
  document_entity_id uuid,                      -- OPTIONAL bridge to the Document-typed entity for this file (see note below); composite FK
  title           text,                        -- best-effort title (the human name lives in P3, not the canonical path)
  source          text,                        -- provenance label (uploader, connector, feed)
  source_uri      text,                        -- original location, if any
  mime            text NOT NULL,               -- detected MIME, drives the conversion router (D38)
  byte_size       bigint,                      -- raw size in bytes
  language        text,                        -- detected primary language
  published_at    timestamptz,                 -- document's own date (resolves "last year"; orders ingestion); world-time origin
  -- GCS object URIs (bodies live here, not in PG — D37):
  raw_uri         text NOT NULL,               -- gs://…-raw/<doc_id>/<content_hash>/original.<ext> (immutable, never mounted)
  markdown_uri    text,                        -- gs://…-artifacts/…/document.md
  pageindex_uri   text,                        -- gs://…-artifacts/…/pageindex.json (structure sidecar)
  conversion_uri  text,                        -- gs://…-artifacts/…/conversion.json (blocks + page/char offsets — load-bearing for grounding, D32/D38)
  meta_uri        text,                        -- gs://…-artifacts/…/meta.json (per-doc metadata sidecar, e0 §2)
  -- conversion provenance (D38):
  converter_name  text,                        -- which converter the router picked (ocr/markitdown/passthrough/…)
  converter_version text,                      -- LOGICAL FK → pipeline_component_versions; a bump re-converts + rebuilds downstream (D7)
  -- structure provenance (LLM-derived, non-deterministic — versioned + replayed on rebuild, D39/D7):
  structurer_name text,
  structurer_version text,                      -- LOGICAL FK → pipeline_component_versions (structurer)
  structurer_model text,
  structurer_prompt_version text,
  pageindex_hash  text,                        -- hash of the structure output (change detection)
  placement_version text,                      -- LOGICAL FK → pipeline_component_versions (placement-hint producer, D39 → P3 input)
  section_index_version text,                  -- LOGICAL FK → pipeline_component_versions (document_sections projector)
  crossref_version text,                       -- LOGICAL FK → pipeline_component_versions (crossreferencer, D36) — the 4th E0 sub-worker's version
  status          document_status NOT NULL DEFAULT 'ingesting', -- ingesting | converting | structuring | ready | failed | deleted
  error           text,                        -- terminal error summary, if status=failed
  ingested_at     timestamptz NOT NULL DEFAULT now(),  -- system-time origin for everything derived from this doc
  updated_at      timestamptz NOT NULL DEFAULT now(),
  deleted_at      timestamptz,                 -- tombstone timestamp for hard-delete/forget (D37); row retained as a soft tombstone (§13)
  UNIQUE (deployment_id, content_hash),         -- per-deployment dedup; NEVER dedup across deployments (D37)
  UNIQUE (deployment_id, doc_id),               -- composite-FK target (tenancy isolation, §0)
  FOREIGN KEY (deployment_id, document_entity_id) REFERENCES entities (deployment_id, entity_id) ON DELETE SET NULL (document_entity_id)
);
COMMENT ON TABLE documents IS
  'E0 document index (D37). Bodies live in GCS (raw+artifacts); PG holds identity/versions/URIs/hashes/state only. content_hash is the sole dedup (idempotency, D25). A forget soft-tombstones the row (deleted_at + status=deleted + nulled URIs) so the K-plane cascade and auditors can reference it.';
CREATE INDEX ix_documents_status   ON documents (deployment_id, status) WHERE status <> 'ready';
CREATE INDEX ix_documents_hash     ON documents (deployment_id, content_hash);
CREATE INDEX ix_documents_live     ON documents (deployment_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_documents_entity   ON documents (document_entity_id) WHERE document_entity_id IS NOT NULL;
```

> **Document ↔ entity bridge (D18, Codex review).** D18 makes `Document ⊂ CreativeWork` a core
> *entity* type with predicates `authored: Person → Document` and `about: Document → any`, so
> documents participate in relations as entities. The corpus's *ingested files* and the *registry's
> Document entities* are distinct but linkable: `documents.document_entity_id` points an ingested
> file at its registry entity **when one exists**. Policy: an ingested document gets a Document
> entity when it is referenced as the subject/object of a relation (e.g. "Alice authored this
> report") or by a deployment-configured default; a Document entity may also exist for a
> *cited-but-not-ingested* paper (created from a `document_crossrefs` row with no `to_doc_id`),
> which has a registry entity but no `documents` row. So the bridge is nullable in both directions
> and neither side is mandatory.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- document_sections — the queryable PageIndex section index (D39). Every document gets rows here
-- unconditionally (a short doc gets one synthetic root section). Summaries are kept as context,
-- never facts. parent_section_id cascades on delete so a hard-delete removes the whole subtree (§13).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE document_sections (
  section_id      uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  doc_id          uuid NOT NULL,               -- composite FK below, ON DELETE CASCADE
  parent_section_id uuid REFERENCES document_sections ON DELETE CASCADE, -- tree structure; NULL for root; cascades the subtree
  node_path       text NOT NULL,               -- materialized path, e.g. '0.2.1' — cheap ancestor/subtree queries
  title           text,
  role            section_role NOT NULL,       -- body|abstract|introduction|...|references|nav|boilerplate|legal (D39)
  char_start      integer NOT NULL,            -- section span start, char offset into document.md
  char_end        integer NOT NULL,            -- section span end
  page_start      integer,                     -- source page span (from conversion blocks), if paginated
  page_end        integer,
  ordinal         integer NOT NULL,            -- order among siblings
  summary         text,                        -- per-section summary (D39): context for E1 prefixes/navigation/Selection-explainability; NOT a fact source
  placement_path  text,                        -- per-section placement hint for P3 (advisory; D39/D40)
  structurer_version text,                     -- LOGICAL FK → pipeline_component_versions; matches documents.structurer_version
  UNIQUE (doc_id, node_path),
  FOREIGN KEY (deployment_id, doc_id) REFERENCES documents (deployment_id, doc_id) ON DELETE CASCADE
);
COMMENT ON TABLE document_sections IS
  'Per-document section tree (D39): path/role/span/summary/placement per section. Drives section-aware chunking (E1), the E2 role signal (Selection drops references/boilerplate at proposition grain), and P3 placement. Summaries are context, never facts.';
CREATE INDEX ix_sections_doc    ON document_sections (doc_id);
CREATE INDEX ix_sections_role   ON document_sections (deployment_id, role);
CREATE INDEX ix_sections_parent ON document_sections (parent_section_id);

-- ─────────────────────────────────────────────────────────────────────────
-- document_crossrefs — citations / inter-document links (the crossref sub-worker, D36). to_doc_id
-- is NULL until/unless the cited target resolves to an ingested document. ON DELETE SET NULL uses
-- the PG15+ column-list form so only to_doc_id is cleared (deployment_id stays). Projected to graph
-- CITES edges (p2 §2).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE document_crossrefs (
  crossref_id     uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  from_doc_id     uuid NOT NULL,               -- composite FK below, ON DELETE CASCADE
  to_doc_id       uuid,                        -- composite FK below, ON DELETE SET NULL(to_doc_id); NULL if cited doc not (yet) ingested
  kind            crossref_kind NOT NULL,      -- cites | links_to | attaches | replies_to
  raw_citation    text,                        -- the citation text as found; RETAINED even when resolved, so a forgotten target can be re-resolved (§13)
  context         text,                        -- surrounding context of the reference
  resolved        boolean NOT NULL DEFAULT false, -- whether to_doc_id was matched
  crossref_version text,                       -- LOGICAL FK → pipeline_component_versions (crossreferencer); a bump re-extracts (D36/D7)
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (deployment_id, from_doc_id) REFERENCES documents (deployment_id, doc_id) ON DELETE CASCADE,
  FOREIGN KEY (deployment_id, to_doc_id)   REFERENCES documents (deployment_id, doc_id) ON DELETE SET NULL (to_doc_id)
);
COMMENT ON TABLE document_crossrefs IS
  'Cross-document references from the E0 crossref sub-worker (D36), versioned by crossref_version (D7 replay). Projected to graph CITES edges; raw_citation is retained even after resolution so a forgotten/re-ingested target can be re-resolved.';
CREATE INDEX ix_crossrefs_from ON document_crossrefs (from_doc_id);
CREATE INDEX ix_crossrefs_to   ON document_crossrefs (to_doc_id) WHERE to_doc_id IS NOT NULL;
```

---

## 7. E1 — chunks

Retrieval-sized units that preserve context and trace back to position. Chunk **text and embedding
live in Lance (P1)**; Postgres holds metadata, offsets, the section link, and the **generated
context prefix** (LLM-derived, so it is *replayed* on rebuild, not regenerated — D7 — and therefore
stored as derived metadata, not body text).

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- chunks — semchunk units, section-aware (never split mid-section, D39). Body = markdown_uri sliced
-- by [char_start,char_end] (NOT stored in PG, D37). Embedding in Lance keyed by chunk_id. Large
-- (tens of millions) ⇒ monthly partition by created_at; logical FKs (D23). Pruning: §12.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE chunks (
  chunk_id        uuid NOT NULL,
  deployment_id   uuid NOT NULL,               -- LOGICAL FK → deployments
  doc_id          uuid NOT NULL,               -- LOGICAL FK → documents
  section_id      uuid,                        -- LOGICAL FK → document_sections; section (role/path signal for E2)
  ordinal         integer NOT NULL,            -- position within the document
  char_start      integer NOT NULL,            -- chunk span start, offset into document.md
  char_end        integer NOT NULL,            -- chunk span end
  token_count     integer,                     -- token length (sizing/budget)
  context_prefix  text,                        -- generated "where this sits" sentence (E1); replayed on rebuild — derived metadata, not body
  prefixer_version text,                       -- LOGICAL FK → pipeline_component_versions (context_prefixer)
  chunker_version text,                        -- LOGICAL FK → pipeline_component_versions (semchunk config)
  embedding_ref   text,                        -- opaque Lance row key for this chunk's vector (vectors live in P1, not PG — D8)
  embedding_version text,                       -- LOGICAL FK → pipeline_component_versions (embedder); scopes re-embedding batches
  created_at      timestamptz NOT NULL DEFAULT now(),  -- partition key
  PRIMARY KEY (chunk_id, created_at)
) PARTITION BY RANGE (created_at);
COMMENT ON TABLE chunks IS
  'E1 retrieval units (semchunk, section-aware). Text+embedding live in Lance (P1); PG stores offsets, section link, the replayable context prefix, and version stamps. Monthly-partitioned, logical FKs (D23).';
CREATE INDEX ix_chunks_doc     ON chunks (deployment_id, doc_id);
CREATE INDEX ix_chunks_section ON chunks (section_id);
```

---

## 8. E2 — claims, the extraction decision ledger, grounding audits (D31–D35)

A **claim** is an atomic, standalone, verifiable assertion (Claimify-staged extraction). Claims are
**immutable, append-only** — they record *what a source said* and are never superseded
(supersession is on *relations*, D3). The model stores both the standalone `claim_text` and the
verbatim `source_span` + offsets + the `added_context` substrings (D32), so grounding is
**provenance + entailment**, not verbatim-substring matching.

> **Reconciliation note (claim "type").** `requirements_v3` (an earlier conception) said claims are
> "typed (fact / opinion / prediction)". The current binding design (D31/D34 Claimify Selection)
> **drops** opinions / advice / hypotheticals at Selection rather than storing them as typed claims
> — so the *stored* claim space collapses to "verifiable proposition", and opinion/prediction
> material lives only in the **drop ledger** (`claim_extraction_decisions`), not as a
> `claims.claim_type` value. We therefore carry no fact/opinion/prediction column; we carry
> `temporal_class` (the "temporally classified" half) and the grounding/recall-envelope fields the
> binding design names. Intentional simplification (CLAUDE.md), recorded so a reader does not think
> the column was forgotten.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- claims — immutable verifiable propositions (D31/D32). THREE immutable time axes (concepts §5, D41):
-- asserted_at = assertion-EVENT time (when the source spoke, ≈ published_at); claim_valid_from/until
-- (+ precision/kind) = the world-time interval the SOURCE asserted the proposition held (valid-time
-- as EVIDENCE, not current belief); ingested_at = when WE extracted it (transaction-time). None ever
-- change, and claim validity is never superseded (D3) — adjudicated validity lives only on relations.
-- A row in claims is an ACCEPTED claim: the deterministic grounding gate (anchor + window
-- membership, D32 layers 1-2) MUST pass, enforced by the CHECK — a claim that fails the gate is
-- never produced (it becomes a ledger entry or is discarded), so the flags exist for audit and are
-- always true here. Large (~5×10⁷) ⇒ monthly partition by ingested_at; logical FKs (D23).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE claims (
  claim_id        uuid NOT NULL,
  deployment_id   uuid NOT NULL,               -- LOGICAL FK → deployments
  doc_id          uuid NOT NULL,               -- LOGICAL FK → documents (provenance always attached — requirements_v3)
  chunk_id        uuid NOT NULL,               -- LOGICAL FK → chunks (the target chunk of the context bundle)
  section_id      uuid,                        -- LOGICAL FK → document_sections (denormalized role/path; explains a Selection decision)
  claim_text      text NOT NULL,               -- the STANDALONE assertion — what retrieval/E3/reasoning use (decontextualized, D32)
  source_span     text NOT NULL,               -- the verbatim slice of the chunk the claim derives from (provenance/audit, D32)
  char_start      integer NOT NULL,            -- source_span offset into document.md (anchor check: a real in-bounds slice, D32 layer 1)
  char_end        integer NOT NULL,
  added_context   jsonb NOT NULL DEFAULT '[]', -- [{text, source_kind: header|neighbour|prefix|hint, source_ref}] — each substring decontextualization ADDED (D32 layer 2)
  temporal_class  claim_temporal_class,        -- static | dynamic | atemporal — the "temporally classified" requirement (see reconciliation note)
  is_attributed   boolean NOT NULL DEFAULT false, -- preserves a "X said Y" attribution (entailment rule: entails "X said Y", not "Y" — D32)
  -- grounding verdicts (D32). Deterministic layers 1-2 are an ACCEPTANCE GATE (must be true here);
  -- the LLM layers 3-4 are advisory/sampled and may be false on a kept-but-borderline claim:
  anchor_ok       boolean NOT NULL,            -- layer 1: source_span is a real in-bounds slice of the chunk (deterministic)
  window_membership_ok boolean NOT NULL,       -- layer 2: every added_context substring verbatim-exists in its declared bundle source (deterministic; rejects fabrication)
  entailment_self_verdict boolean,             -- layer 3: in-call self-assertion the bundle entails the claim (~free, optimistic)
  audit_status    grounding_audit_status NOT NULL DEFAULT 'unaudited', -- layer 4: unaudited | sampled_pass | sampled_fail | escalated (sampled, not per-claim)
  kept_flagged    boolean NOT NULL DEFAULT false, -- D35 low-confidence Selection outcome: kept but marked-for-review (mirrors a selection_keep_flagged ledger row — see invariant below)
  asserted_at     timestamptz,                 -- ASSERTION-EVENT time: when the source asserted this (≈ documents.published_at) — immutable; NOT the fact's world-time (that is claim_valid_*, D41)
  -- D41 source-asserted world-validity INTERVAL — immutable evidence about WHEN (not current belief).
  -- Overlap of these intervals across sources is EXPECTED (it is evidence), so there is deliberately
  -- NO uniqueness/EXCLUDE, NO invalidated_at, NO status here — the opposite of relations (§9):
  claim_valid_from timestamptz,                -- world-time start the SOURCE attributed (NULL = unbounded-before/unknown); immutable
  claim_valid_until timestamptz,               -- world-time end (NULL = open-per-source OR unknown; disambiguated by claim_valid_precision)
  claim_valid_precision claim_valid_precision NOT NULL DEFAULT 'unknown', -- unknown|instant|day|month|quarter|year|open — "FY2023" stores a normalized [start,end] without lying about granularity
  claim_valid_kind claim_valid_kind,           -- which world-interval this is: proposition_validity|event_time|measurement_period|effective_period (so a measurement period is never conflated with an event date or with asserted_at)
  extractor_version text NOT NULL,             -- LOGICAL FK → pipeline_component_versions (extractor); replay-on-rebuild key (D33)
  embedding_ref   text,                        -- opaque Lance key (claims are searchable in P1)
  embedding_version text,                       -- LOGICAL FK → pipeline_component_versions (embedder)
  ingested_at     timestamptz NOT NULL DEFAULT now(),  -- transaction-time + partition key; immutable
  PRIMARY KEY (claim_id, ingested_at),
  CHECK (char_end >= char_start),
  CHECK (anchor_ok AND window_membership_ok),  -- a claims row is an ACCEPTED claim; the deterministic grounding gate passed (D32)
  -- D41 precision/bounds coherence (claim validity carries no status/invalidated_at — it is immutable):
  CHECK (claim_valid_until IS NULL OR claim_valid_from IS NULL OR claim_valid_until >= claim_valid_from),
  CHECK (claim_valid_precision <> 'unknown' OR (claim_valid_from IS NULL AND claim_valid_until IS NULL)),
  CHECK (claim_valid_precision <> 'open'    OR (claim_valid_from IS NOT NULL AND claim_valid_until IS NULL)),
  CHECK (claim_valid_precision <> 'instant' OR (claim_valid_from IS NOT NULL AND claim_valid_until = claim_valid_from)),
  -- a bounded precision must actually carry both bounds (else it silently degrades to unknown/open):
  CHECK (claim_valid_precision NOT IN ('day','month','quarter','year') OR (claim_valid_from IS NOT NULL AND claim_valid_until IS NOT NULL))
) PARTITION BY RANGE (ingested_at);
COMMENT ON TABLE claims IS
  'E2 immutable verifiable propositions (D31/D32). Stores standalone claim_text + verbatim source_span + offsets + added_context for provenance-and-entailment grounding. Three immutable time axes (D41): asserted_at (assertion event), claim_valid_from/until (+precision/kind = source-asserted world-interval — evidence, not belief), ingested_at (system); never superseded (supersession is on relations, D3). A row here passed the deterministic grounding gate. Monthly-partitioned, logical FKs.';
CREATE INDEX ix_claims_doc      ON claims (deployment_id, doc_id);
CREATE INDEX ix_claims_chunk    ON claims (chunk_id);
CREATE INDEX ix_claims_flagged  ON claims (deployment_id) WHERE kept_flagged = true;        -- review surface (D35)
CREATE INDEX ix_claims_audit    ON claims (deployment_id) WHERE audit_status = 'sampled_fail'; -- grounding regressions
-- D41 claim-validity is projected to Lance (P1) as filterable scalar columns (claim_valid_from/until/
-- precision) beside the claim embedding (same pattern as relation windows, D8); the time-filter path
-- is Lance, so there is NO new Postgres index by default (preserves D23's btree-light mandate on this
-- ~5×10⁷ partitioned table). A `claims_as_of(t)` search recipe (D9) answers "what did sources assert
-- held over T" at the EVIDENCE grain; belief-as-of stays relations-only (D10) and the recipe registry
-- BARS claims_as_of from answering "currently true". An OPTIONAL partial btree on (deployment_id,
-- claim_valid_from, claim_valid_until) WHERE claim_valid_precision <> 'unknown' is added only if
-- PG-side temporal claim filtering is ever load-tested against D23 — a spike (§17), not a default.

-- ─────────────────────────────────────────────────────────────────────────
-- claim_extraction_decisions — the append-only, version-stamped extraction transcript (D33). It
-- records every Selection DROP (with reason), every low-confidence KEEP-FLAG, and every
-- decontextualization EDIT. Plain keeps are NOT recorded (they ARE the claims row) — keeping the
-- table sized for drops+flags+edits, not every keep. Rebuild reads stored claims + these decisions
-- and never re-calls the model (D7). Large ⇒ monthly partition by decided_at.
-- INVARIANT: a kept_flagged claim is the pair (claims row with kept_flagged=true) + (a
-- selection_keep_flagged decision here); the ledger is the replay source from which
-- claims.kept_flagged is reconstituted on rebuild.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE claim_extraction_decisions (
  decision_id     uuid NOT NULL,
  deployment_id   uuid NOT NULL,               -- LOGICAL FK → deployments
  doc_id          uuid NOT NULL,               -- LOGICAL FK → documents
  chunk_id        uuid NOT NULL,               -- LOGICAL FK → chunks
  claim_id        uuid,                        -- LOGICAL FK → claims; set for decontext edits + selection_keep_flagged; NULL for selection_drop (no claim produced)
  decision_type   extraction_decision_type NOT NULL, -- selection_drop | selection_keep_flagged | decontext_edit
  source_span     text,                        -- the proposition/sentence the decision was about
  reason          selection_drop_reason,       -- for drops: opinion|advice|hypothetical|generic|question|intro|conclusion|no_info|ambiguous|references_boilerplate (D31)
  edit_detail     jsonb,                        -- for decontext edits: what was resolved/added and from which bundle source
  protected_class text,                        -- never-drop class checked/applied (quantity|date|named_entity_predicate|change_of_state) — D35
  extractor_version text NOT NULL,             -- LOGICAL FK → pipeline_component_versions; the version that made this decision
  decided_at      timestamptz NOT NULL DEFAULT now(),  -- partition key
  PRIMARY KEY (decision_id, decided_at)
) PARTITION BY RANGE (decided_at);
COMMENT ON TABLE claim_extraction_decisions IS
  'Append-only Selection-drop + keep-flag + decontextualization-edit ledger (D33); plain keeps are not recorded. Makes aggressive Selection auditable and recoverable: a better prompt re-examines only the drops; rebuild replays from here without re-calling the model (D7). Monthly-partitioned.';
CREATE INDEX ix_cxd_chunk ON claim_extraction_decisions (chunk_id);
CREATE INDEX ix_cxd_drops ON claim_extraction_decisions (deployment_id, reason) WHERE decision_type = 'selection_drop';

-- ─────────────────────────────────────────────────────────────────────────
-- grounding_audits — the sampled independent entailment audit (D32 layer 4). Not per-claim
-- (self-grading is optimistic; a separate judge re-checks a sample; only a borderline band
-- escalates). claims.audit_status caches the latest result.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE grounding_audits (
  audit_id        uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  claim_id        uuid NOT NULL,               -- LOGICAL FK → claims (partitioned)
  verdict         grounding_audit_status NOT NULL, -- sampled_pass | sampled_fail | escalated
  judge_version   text NOT NULL,               -- LOGICAL FK → pipeline_component_versions (independent judge)
  rationale       text,
  sampled_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE grounding_audits IS
  'Sampled independent entailment audits of claims (D32 layer 4). Offline, not per-claim; feeds claims.audit_status and the grounding eval suite.';
CREATE INDEX ix_grounding_claim ON grounding_audits (claim_id);
```

---

## 9. E3 — facts: one verdict layer for entity *and* literal facts (D2–D4, D8, D43)

A **fact** is the system's current, adjudicated belief about one thing in the world —
`(subject_entity, governed relationship, object)` where the **object is an entity reference OR a typed
literal** (`object_kind ∈ {entity, literal}`). It is the unit of **supersession** and **contradiction**
and carries the **bi-temporal** windows. **Evidence** is the many-to-many join back to the claims that
support/contradict it — where corpus redundancy collapses into `evidence_count` (a free
confidence/salience signal, D2). One claim may yield several facts, and one fact may be evidenced by
many claims (`concepts.md` §2); uniqueness is per `(fact_id, claim_id)` in `fact_evidence`.

A **relation** (*"Alice works at Acme"*) is just a fact whose object is an **entity** — and that
subset is the only thing the graph can hold (a LadybugDB relationship needs node endpoints, so a
literal can never be an edge — D18). So **`relations` is a read-only VIEW** over `facts WHERE
object_kind='entity'`, and P2 projects that view. A **literal** fact (*"Acme's headcount is 600"*,
*"revenue was \$5M in FY2023"*) lives in the same table, gets the same windows + supersession, but
never enters the graph. Design + worked examples: `fact_layer_design.md` (D43). The governed
relationship vocabulary — predicates **and** attributes, merged — is `governed_relationships` (§3).

**The supersedable gate (D43) — what makes one table correct.** A literal fact gets the belief axis (a
closable `valid_until`, an `invalidated_at`, the literal supersession constraint) **only when
`supersedable`** — a *generated, NULL-safe* column = `object_kind='entity' OR (valid_kind='effective_period'
AND cardinality='single')`, whose inputs (`valid_kind`, `cardinality`) are **locked from the registry by
`trg_facts_lock_gate`** so a writer can forge neither the flag nor what feeds it. So a changing **state**
(balance/headcount) supersedes (a new value caps the old window); a **period figure** ($5M vs $7M for the
same FY2023) is **not** supersedable and both values stand (the D42 behavior, DB-enforced by `CHECK
(supersedable OR invalidated_at IS NULL)` + the same trigger freezing its asserted window); a multi-valued
literal (`cardinality='set'`) coexists. The **same `cardinality`** splits the *entity* side too —
functional predicates (`single`, e.g. `has_ceo`) supersede, multi-valued ones (`set`, e.g. `member_of`)
coexist — via the four exclusion arms below. This is what lets the *one* table deliver supersession
without ever silently resolving a genuine disagreement (the gate reuses `claim_valid_kind`, D41 — no new
enum). Objects that are literals never become graph nodes/edges (D18 holds on the graph; the truth table
may carry them).

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- facts — the unified verdict layer (D43): the system's current belief, for entity-object AND
-- literal-object facts, over immutable claims. Replaces the old `relations` table and the D42
-- `claim_attribute_facts` projection. The (subject, relationship) blocking key for supersession is
-- small (distinct facts, not assertions) — what makes supersession affordable at scale (concepts §6).
-- The fact LABEL + its embedding live in Lance (D8, now incl. literal facts); PG keeps text + ref.
-- Not partitioned (distinct facts; the heavy assertion-grain tables are claims/evidence).
--
-- "Live belief" = invalidated_at IS NULL (transaction-time), regardless of valid_until: a
-- believed-historical fact ("headcount was 500 in 2023", valid_until capped, invalidated_at NULL) is
-- still currently believed. status is a GENERATED mirror of invalidated_at (one validity home, D6).
--
-- supersedable is GENERATED (D43) — an app cannot mis-mark it: entities are always supersedable
-- (an edge can always be invalidated); a literal is supersedable only if its attribute is a
-- single-valued effective_period STATE. valid_kind + cardinality (the gate inputs) are LOCKED from
-- governed_relationships by trg_facts_lock_gate, so the writer cannot forge the gate. FOUR partial GiST
-- EXCLUSION constraints enforce "≤1 believed fact per slot over overlapping world-time", split by
-- cardinality so functional and multi-valued relationships behave correctly (these need the btree_gist
-- extension — the `=` operator class for uuid/text in a GiST key — created in §1):
--   • entity FUNCTIONAL (single): object EXCLUDED from key → a new object supersedes (one CEO at a time)
--   • entity SET (set): object INCLUDED → distinct objects coexist (member of several orgs)
--   • literal single-valued-supersedable: value EXCLUDED → a new value supersedes (a changing balance)
--   • literal SET (effective_period + set): value INCLUDED + overlap → concurrent values coexist (offices)
-- A measurement_period/event_time literal is in NO range-overlap arm (range overlap is the wrong operator
-- for a period figure — FY2023 vs Q1-2023 overlap but differ); different values for the same period
-- both-stand (FY2023 $5M vs $7M) and an always-on exact-duplicate UNIQUE bars only a true duplicate. That
-- UNIQUE also closes the "grouped rows leave every partial arm" hole (the arms are contradiction_group-
-- aware; the UNIQUE is not). Identity columns are frozen post-insert by trg_facts_lock_gate.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE facts (
  fact_id           uuid PRIMARY KEY,            -- the fact's identity; provenance handle in the graph/Lance projections
  deployment_id     uuid NOT NULL REFERENCES deployments,
  subject_entity_id uuid NOT NULL,               -- canonical subject (always an entity — D2 subject rule); composite FK below
  rel_key           text NOT NULL,               -- governed relationship (predicate OR attribute); composite FK → governed_relationships (§3)
  object_kind       fact_object_kind NOT NULL,   -- entity => graph-eligible relation; literal => Lance/PG only, never a graph edge (D18)
  object_entity_id  uuid,                          -- set IFF object_kind='entity' (canonical object); composite FK below
  object_value      jsonb,                          -- set IFF object_kind='literal' — typed normalized value, e.g. {amount:5000000,currency:'USD'}
  object_value_identity text,                       -- set IFF literal — canonical hash(normalized value+unit+precision): "$5M" == "5,000,000 USD"; the literal dedup key
  qualifiers_hash   text NOT NULL DEFAULT '',     -- identity-bearing qualifiers (IFRS vs GAAP, global vs US ⇒ DIFFERENT slot, not a conflict)
  valid_kind        claim_valid_kind,             -- DENORMALIZED + LOCKED from governed_relationships.default_valid_kind by trg_facts_lock_gate (below); gate input
  cardinality       text NOT NULL DEFAULT 'set',  -- DENORMALIZED + LOCKED from the registry by trg_facts_lock_gate: single (supersede) | set (coexist); EXCLUDEs can't join the registry
  -- MECHANICAL gate (D43), not app-set. COALESCE→false makes it NULL-SAFE: a literal whose valid_kind is
  -- somehow NULL falls to the SAFE side (non-supersedable ⇒ coexist/both-stand), never escaping every
  -- EXCLUDE arm. NOT NULL so the partial-index predicates and the CHECK below are never UNKNOWN.
  supersedable      boolean GENERATED ALWAYS AS
                      (COALESCE(object_kind = 'entity'
                                OR (valid_kind = 'effective_period' AND cardinality = 'single'), false)) STORED NOT NULL,
  -- bi-temporality (concepts §5): two clocks. For a NON-supersedable literal, valid_from/valid_until
  -- is the ASSERTED measurement period (FY2023 = [2023-01-01, 2024-01-01)) — set once, never re-capped:
  valid_from      timestamptz,                   -- VALID-time start: when the fact began holding in the world (NULL = unknown/always)
  valid_until     timestamptz,                   -- VALID-time end: capped by supersession (supersedable) OR the asserted period bound (non-supersedable)
  ingested_at     timestamptz NOT NULL DEFAULT now(), -- TRANSACTION-time: when the system first believed this fact
  invalidated_at  timestamptz,                   -- TRANSACTION-time: when the system learned it was superseded (NULL = still believed)
  evidence_count  integer NOT NULL DEFAULT 0,    -- cached COUNT of supporting evidence rows — free confidence/salience signal (D2); K3 candidate filter
  contradict_count integer NOT NULL DEFAULT 0,   -- cached COUNT of contradicting evidence rows
  confidence      real,                          -- aggregate confidence over evidence (not an extraction-time guess — concepts §3)
  contradiction_group uuid,                      -- shared id when two live facts conflict and can't be adjudicated — retrieval shows both sides (concepts §4)
  status          relation_status GENERATED ALWAYS AS
                    (CASE WHEN invalidated_at IS NOT NULL THEN 'invalidated'::relation_status ELSE 'active'::relation_status END) STORED,
  fact_label      text,                          -- "Alice Novak works at Acme as VP of Engineering" / "Acme headcount = 600 since 2025" — embedded in Lance (D8)
  fact_label_version text,                       -- LOGICAL FK → pipeline_component_versions (fact_labeler)
  fact_label_embedding_ref text,                 -- opaque Lance key for the fact-label vector (P1; no vectors in PG/graph — D8)
  normalizer_version text NOT NULL,              -- LOGICAL FK → pipeline_component_versions; replay-on-rebuild
  adjudicator_version text,                      -- LOGICAL FK → pipeline_component_versions (supersession/contradiction adjudicator, D4)
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deployment_id, fact_id),               -- composite-FK target (tenancy isolation, §0)
  FOREIGN KEY (deployment_id, rel_key)           REFERENCES governed_relationships (deployment_id, rel_key) ON UPDATE CASCADE,
  FOREIGN KEY (deployment_id, subject_entity_id) REFERENCES entities (deployment_id, entity_id),
  FOREIGN KEY (deployment_id, object_entity_id)  REFERENCES entities (deployment_id, entity_id),
  -- ONE exclusive-arc CHECK: an entity row can never leak literal columns, and vice-versa:
  CHECK ( (object_kind='entity'  AND object_entity_id IS NOT NULL AND object_value IS NULL     AND object_value_identity IS NULL)
       OR (object_kind='literal' AND object_entity_id IS NULL     AND object_value IS NOT NULL AND object_value_identity IS NOT NULL) ),
  CHECK (cardinality IN ('single','set')),
  -- a literal MUST carry its time-semantics (the gate input) so `supersedable` is never decided on a
  -- NULL valid_kind — trg_facts_lock_gate copies it from the registry; this CHECK is the floor:
  CHECK (object_kind = 'entity' OR valid_kind IS NOT NULL),
  -- intervals are STRICTLY POSITIVE: tstzrange(t,t) is EMPTY under the default [) bounds and overlaps
  -- nothing, which would let two identical instantaneous facts both slip past every EXCLUDE arm. An
  -- instant (event_time) is stored as its non-empty asserted-precision window (a day/second, D41),
  -- never as a zero-length range:
  CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from),
  CHECK (invalidated_at IS NULL OR invalidated_at >= ingested_at),  -- can't un-learn before learning
  -- the relocated D42 no-belief-axis guard: a NON-supersedable literal may keep its ASSERTED period
  -- (valid_until) but NEVER a transaction-time invalidation/supersession close. The companion half —
  -- "never RE-CAP an already-asserted window" — is DB-enforced by trg_facts_lock_gate (below), NOT
  -- left to worker/linter discipline (D43 verdict-critical safety belongs in the schema):
  CHECK (supersedable OR invalidated_at IS NULL),
  -- ENTITY FUNCTIONAL arm (cardinality='single', e.g. has_ceo, headquartered_in) — object EXCLUDED from
  -- the key ⇒ ANY two overlapping live edges for the same (subject, rel, qualifiers) conflict, so a NEW
  -- object must cap/close the old: DB-enforced functional supersession, symmetric with the literal-single
  -- arm. cardinality is an EXPLICIT per-predicate declaration in the seed (registries §4); the permissive
  -- default is 'set' (most relations are multi-valued), so a functional predicate must OPT IN to 'single'.
  -- A forgotten 'single' therefore coexists (the adjudicator still supersedes, as pre-D43) rather than
  -- over-rejecting legitimate concurrent edges — the conservative direction:
  EXCLUDE USING gist (
    deployment_id WITH =, subject_entity_id WITH =, rel_key WITH =, qualifiers_hash WITH =,
    (tstzrange(valid_from, valid_until)) WITH &&
  ) WHERE (object_kind='entity' AND cardinality='single' AND invalidated_at IS NULL AND contradiction_group IS NULL),
  -- ENTITY SET arm (cardinality='set', e.g. member_of, located_in) — object INCLUDED ⇒ distinct objects
  -- COEXIST (a person member_of several orgs at once); only an exact-duplicate overlapping edge is barred.
  -- qualifiers_hash is in the key so IFRS-vs-GAAP-style qualified edges are distinct slots (concern parity
  -- with literals); it defaults to '' so unqualified relations are unaffected:
  EXCLUDE USING gist (
    deployment_id WITH =, subject_entity_id WITH =, rel_key WITH =, qualifiers_hash WITH =, object_entity_id WITH =,
    (tstzrange(valid_from, valid_until)) WITH &&
  ) WHERE (object_kind='entity' AND cardinality='set' AND invalidated_at IS NULL AND contradiction_group IS NULL),
  -- LITERAL SINGLE-VALUED SUPERSEDABLE arm — VALUE EXCLUDED from the key ⇒ a new value closes the old
  -- window (supersession). The affirmed must-have (a balance/headcount over time):
  EXCLUDE USING gist (
    deployment_id WITH =, subject_entity_id WITH =, rel_key WITH =, qualifiers_hash WITH =,
    (tstzrange(valid_from, valid_until)) WITH &&
  ) WHERE (object_kind='literal' AND supersedable AND cardinality='single'
           AND invalidated_at IS NULL AND contradiction_group IS NULL),
  -- LITERAL SET arm — a multi-valued effective_period STATE (e.g. several office locations held at once):
  -- VALUE INCLUDED + range overlap ⇒ distinct concurrent values COEXIST, while a re-asserted same value
  -- over an overlapping window is folded (overlapping duplicate barred). RESTRICTED to effective_period:
  -- a measurement_period figure is not a stateful interval, so range-overlap is the WRONG operator for it
  -- (FY2023 and Q1-2023 overlap yet are different measurements). measurement_period / event_time literals
  -- are in NO range-overlap arm — they rely on the exact-identity UNIQUE below, which lets different
  -- values for the SAME period both-stand while still barring an exact duplicate:
  EXCLUDE USING gist (
    deployment_id WITH =, subject_entity_id WITH =, rel_key WITH =, qualifiers_hash WITH =,
    object_value_identity WITH =, (tstzrange(valid_from, valid_until)) WITH &&
  ) WHERE (object_kind='literal' AND valid_kind='effective_period' AND cardinality='set'
           AND invalidated_at IS NULL AND contradiction_group IS NULL),
  -- EXACT-DUPLICATE FLOOR (applies to EVERY row, grouped or not). The GiST arms above all carry
  -- `contradiction_group IS NULL`, so once two conflicting rows are grouped they leave every arm — this
  -- always-on UNIQUE still bars a *true* exact duplicate (same subject+rel+qualifiers+object+window) of any
  -- row, and is the sole dup-guard for measurement_period / event_time literals (different values or
  -- periods coexist; an identical one cannot). NULLS NOT DISTINCT so open windows and the absent object
  -- column (entity vs literal) compare equal:
  UNIQUE NULLS NOT DISTINCT
    (deployment_id, subject_entity_id, rel_key, qualifiers_hash, object_entity_id, object_value_identity,
     valid_from, valid_until)
);
COMMENT ON TABLE facts IS
  'D43 unified verdict layer: current belief for entity- AND literal-object facts, over immutable claims. relation_id concept → fact_id. Object is an entity (→ graph) or a typed literal (Lance/PG only, D18). One bi-temporal window; status + supersedable are GENERATED, valid_kind/cardinality LOCKED from the registry by trg_facts_lock_gate (one validity home D6; the gate cannot be forged). Four partial GiST EXCLUDEs (entity-functional / entity-set / literal-single-supersede / literal-set, effective_period only) gate supersession by cardinality, plus an always-on exact-duplicate UNIQUE that also de-dupes measurement_period/event_time literals (which otherwise both-stand). Identity columns are immutable post-insert (trg_facts_lock_gate). Replaces relations + claim_attribute_facts (D42).';
-- The supersession blocking key (D4) — small, distinct facts; THE index that makes supersession
-- detection affordable (concepts §6); covers both arms via object_kind:
CREATE INDEX ix_facts_block_subj ON facts (deployment_id, subject_entity_id, rel_key, object_kind);
CREATE INDEX ix_facts_block_obj  ON facts (deployment_id, object_entity_id, rel_key) WHERE object_kind='entity';  -- reverse blocking ("who works_at acme?")
CREATE INDEX ix_facts_contradiction ON facts (contradiction_group) WHERE contradiction_group IS NOT NULL;
CREATE INDEX ix_facts_live       ON facts (deployment_id, subject_entity_id) WHERE invalidated_at IS NULL;

-- ─────────────────────────────────────────────────────────────────────────
-- GATE INTEGRITY (D43) — the supersedable gate is only as trustworthy as its inputs, so valid_kind and
-- cardinality are NOT app-set: this BEFORE trigger COPIES them from the row's governed_relationships
-- entry on every write and LOCKS them (a fact's time-semantics come from its REGISTERED relationship,
-- never from the writer). It also (a) verifies object_kind matches the relationship's range_kind, and
-- (b) makes the asserted window of a NON-supersedable literal immutable after insert — the "never re-cap
-- a period figure" invariant, moved out of worker/linter discipline into the DB. NOTE: supersedable is a
-- GENERATED column and is computed AFTER before-row triggers, so the gate is recomputed locally here
-- (from the just-locked inputs) rather than read off NEW.
-- ─────────────────────────────────────────────────────────────────────────
CREATE FUNCTION facts_lock_gate_inputs() RETURNS trigger AS $$
DECLARE
  r              governed_relationships%ROWTYPE;
  v_supersedable boolean;
BEGIN
  SELECT * INTO r FROM governed_relationships
    WHERE deployment_id = NEW.deployment_id AND rel_key = NEW.rel_key;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'facts: unknown relationship % (deployment %)', NEW.rel_key, NEW.deployment_id;
  END IF;
  IF r.range_kind <> NEW.object_kind THEN
    RAISE EXCEPTION 'facts: object_kind % conflicts with %.range_kind %', NEW.object_kind, NEW.rel_key, r.range_kind;
  END IF;
  -- copy + lock the gate inputs from the registry (any app-supplied value is overwritten):
  NEW.valid_kind  := r.default_valid_kind;     -- NULL for entity range; NOT NULL for literal (registry CHECK)
  NEW.cardinality := r.cardinality;
  IF TG_OP = 'UPDATE' THEN
    -- IDENTITY IS IMMUTABLE post-insert: a fact's id/tenant/subject/relationship/object/qualifiers never
    -- change — only its belief axis (valid_until cap on a supersedable row, invalidated_at, evidence/
    -- labels) may move. Freezing identity also closes the bypass where rel_key is flipped to a supersedable
    -- kind to mutate the window and flipped back. fact_id is included because fact_evidence's FK is logical
    -- (D23) — re-keying a fact would silently orphan its evidence:
    IF NEW.fact_id            IS DISTINCT FROM OLD.fact_id
       OR NEW.deployment_id      IS DISTINCT FROM OLD.deployment_id
       OR NEW.subject_entity_id  IS DISTINCT FROM OLD.subject_entity_id
       OR NEW.rel_key            IS DISTINCT FROM OLD.rel_key
       OR NEW.object_kind        IS DISTINCT FROM OLD.object_kind
       OR NEW.object_entity_id   IS DISTINCT FROM OLD.object_entity_id
       OR NEW.object_value          IS DISTINCT FROM OLD.object_value
       OR NEW.object_value_identity IS DISTINCT FROM OLD.object_value_identity
       OR NEW.qualifiers_hash    IS DISTINCT FROM OLD.qualifiers_hash THEN
      RAISE EXCEPTION 'facts: identity columns are immutable after insert (fact %)', OLD.fact_id;
    END IF;
    -- "never re-cap an asserted window" — judged on the row's OWN (now-immutable, registry-locked) kind:
    v_supersedable := COALESCE(NEW.object_kind = 'entity'
                               OR (NEW.valid_kind = 'effective_period' AND NEW.cardinality = 'single'), false);
    IF NOT v_supersedable
       AND (NEW.valid_from IS DISTINCT FROM OLD.valid_from OR NEW.valid_until IS DISTINCT FROM OLD.valid_until) THEN
      RAISE EXCEPTION 'facts: cannot re-cap the asserted window of non-supersedable fact %', NEW.fact_id;
    END IF;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_facts_lock_gate BEFORE INSERT OR UPDATE ON facts
  FOR EACH ROW EXECUTE FUNCTION facts_lock_gate_inputs();

-- relations VIEW — the entity-object subset; the ONLY slice the graph projects (D18/D43). Preserves
-- every existing reader (graph rebuild, (entity,predicate) blocking, recipes) unchanged. READ-ONLY:
-- a simple view like this is auto-updatable in PG, so writes are revoked from app roles below — every
-- write goes to `facts`, keeping one verdict home (D6). (Add INSTEAD OF triggers if a role needs the
-- view writable.)
CREATE VIEW relations AS
  SELECT fact_id AS relation_id, deployment_id, subject_entity_id, rel_key AS predicate, object_entity_id,
         valid_from, valid_until, ingested_at, invalidated_at, evidence_count, contradict_count,
         confidence, contradiction_group, status, fact_label, fact_label_version,
         fact_label_embedding_ref, normalizer_version, created_at, updated_at
  FROM facts WHERE object_kind = 'entity';
CREATE TRIGGER trg_relations_ro INSTEAD OF INSERT OR UPDATE OR DELETE ON relations
  FOR EACH ROW EXECUTE FUNCTION reject_view_write();   -- hard read-only (auto-updatable view otherwise)
REVOKE INSERT, UPDATE, DELETE ON relations FROM PUBLIC;  -- belt: read-only compatibility view; write to facts
COMMENT ON VIEW relations IS
  'D43 read-only compatibility view = facts WHERE object_kind=''entity'' (the graph-projectable subset). Writes hard-blocked (INSTEAD OF trigger + REVOKE) — go to facts. "relation" is now a subset of "fact", not a table.';
```

> **Contradiction insert protocol (concepts §4).** When the adjudicator cannot resolve a conflict
> between two same-`(subject, rel, object/value)` facts with overlapping windows (murky dates), both
> stay live with a shared `contradiction_group`. Because every EXCLUDE arm ignores rows where
> `contradiction_group IS NOT NULL`, the second open row must be inserted **with its
> `contradiction_group` already set** (assigned in the same transaction that detects the conflict and
> stamps the group onto the existing row too). The arms therefore never see two live
> `contradiction_group IS NULL` rows for the same overlapping slot. (For non-supersedable literals —
> the both-stand period figures — the *coexist* arm keeps the distinct values, and **surfacing does not
> depend on a `contradiction_group` being set**: the `attribute_conflicts` recipe finds them directly —
> ≥2 distinct live values for the same `(subject, rel, qualifiers, period)` slot — so a missing group
> can never make a disagreement invisible. The `contradiction_group` is the adjudicator's *optional
> annotation* that links the two once it has run; the coexistence query is the floor, D42 behavior
> preserved.)

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- fact_evidence — the many-to-many join claims ⇄ facts (D2; merges relation_evidence +
-- attribute_evidence). "Where corpus redundancy goes to die": 200 documents asserting the same fact =
-- one fact + 200 rows here. ~10⁸ rows.
--
-- Partitioned by HASH(fact_id), NOT by ingest month — because every hot access is by fact_id
-- (hydration) and the evidence-once invariant is on (fact_id, claim_id). With the partition key =
-- fact_id: fact hydration prunes to ONE partition, AND a real PRIMARY KEY (fact_id, claim_id) enforces
-- "a claim evidences a fact at most once" in-DB (so facts.evidence_count cannot be inflated by a retry
-- — a re-link is an ON CONFLICT no-op). Refines D23 (monthly) for this table — see §17. Hash
-- partitions are STATIC (created at migration, e.g. 64). The claim_id reverse lookup ("which facts
-- does this claim evidence") scans all partitions but is the cold path. FKs remain logical (D23).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE fact_evidence (
  deployment_id   uuid NOT NULL,               -- LOGICAL FK → deployments
  fact_id         uuid NOT NULL,               -- LOGICAL FK → facts; HASH partition key
  claim_id        uuid NOT NULL,               -- LOGICAL FK → claims; the asserting claim (immutable evidence). One claim may evidence MANY facts.
  stance          evidence_stance NOT NULL,    -- supports | contradicts (concepts §3/§4)
  normalizer_version text NOT NULL,            -- LOGICAL FK → pipeline_component_versions; which normalizer linked them
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (fact_id, claim_id)              -- evidence-once, DB-enforced (partition key fact_id is included); re-link via ON CONFLICT DO NOTHING is a no-op
) PARTITION BY HASH (fact_id);
-- The N child partitions are part of the migration contract — a partitioned parent with NO children
-- rejects every insert ("no partition of relation found for row"). This block is EXECUTABLE DDL (not
-- illustrative): create the fixed modulus at migration and never repartition live (rebuild-first, like
-- the graph). The per-partition PK + indexes are inherited automatically:
DO $$ BEGIN
  FOR i IN 0..63 LOOP
    EXECUTE format('CREATE TABLE fact_evidence_p%s PARTITION OF fact_evidence '
                   'FOR VALUES WITH (MODULUS 64, REMAINDER %s);', i, i);
  END LOOP;
END $$;
COMMENT ON TABLE fact_evidence IS
  'Many-to-many evidence links (D2; D43 merge of relation_evidence + attribute_evidence). Corpus redundancy collapses here into facts.evidence_count. Partitioned by HASH(fact_id), 64 static child partitions created at migration, so fact hydration prunes to one partition and PRIMARY KEY (fact_id, claim_id) enforces evidence-once in-DB (refines D23 — §17). claim_id reverse lookup scans all partitions (cold path). Logical FKs (D23).';
CREATE INDEX ix_factevidence_claim ON fact_evidence (claim_id);  -- reverse lookup: facts a claim evidences (all-partition scan)

-- ─────────────────────────────────────────────────────────────────────────
-- fact_adjudications — append-only supersession/contradiction transcript (D3/D4; generalizes
-- relation_adjudications to fact_id). Records WHY a fact's window closed (entity OR literal supersession),
-- a contradiction flagged, or a merge proposed — by which cascade rung, with what confidence/evidence.
-- Makes the non-deterministic adjudication replayable on rebuild (D7) and answers "why did headcount's
-- valid_until close on 2025-03-01?". Real composite FK; the deletion GC retires (not deletes) facts
-- referenced here so the audit trail survives (§13).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE fact_adjudications (
  adjudication_id uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  fact_id         uuid NOT NULL,               -- the fact acted upon (composite FK below)
  related_fact_id uuid,                        -- the other fact in a supersede/contradict pair, if any (composite FK below)
  outcome         adjudication_outcome NOT NULL, -- add | noop | supersede | contradict | same_as_merge_proposal (D4 write-time outcomes)
  method          adjudication_method NOT NULL,  -- novelty_gate | exact | fuzzy | embedding | small_model | frontier_llm (cheap-first cascade, D4)
  confidence      real,
  triggering_claim_id uuid,                     -- LOGICAL FK → claims; the new claim that triggered adjudication
  features        jsonb,                        -- scores/rationale the decision used (audit); scrubbed on hard-forget (§13)
  adjudicator_version text NOT NULL,            -- LOGICAL FK → pipeline_component_versions
  decided_by      decision_actor NOT NULL DEFAULT 'auto',
  decided_at      timestamptz NOT NULL DEFAULT now(),
  superseded_by   uuid REFERENCES fact_adjudications, -- a later adjudication that overrode this one
  FOREIGN KEY (deployment_id, fact_id)         REFERENCES facts (deployment_id, fact_id),
  FOREIGN KEY (deployment_id, related_fact_id) REFERENCES facts (deployment_id, fact_id)
);
COMMENT ON TABLE fact_adjudications IS
  'Append-only supersession/contradiction decision log (D3/D4; D43 generalizes relation_adjudications to fact_id, covering literal supersession). Explains every window closure / contradiction flag / merge proposal; replayed on P2 rebuild and used for "what did we believe at T / why" audits.';
CREATE INDEX ix_adjud_fact ON fact_adjudications (fact_id);
CREATE INDEX ix_adjud_live ON fact_adjudications (fact_id) WHERE superseded_by IS NULL;
```

### 9.A Non-relational facts are now `facts` rows (D43 supersedes the D42 projection)

D42 introduced a **derived, no-belief-axis** `claim_attribute_facts` projection that could only
*surface* non-relational conflicts (never resolve them). **D43 retires it.** Non-relational facts are
now first-class **literal-object rows of the unified `facts` table** (§9), with the same bi-temporal
windows, evidence join, and adjudicator as entity facts — gated by `supersedable` so that:

- **supersedable literals** (single-valued `effective_period` *states* — a balance, headcount, status)
  get a real **closeable validity window**: a later value caps the predecessor. This is the affirmed
  must-have that D42 could not deliver.
- **non-supersedable literals** (`measurement_period` period figures; the D42 *both-stand residue*)
  keep the **no-belief-axis** behavior — the *coexist* EXCLUDE arm lets distinct same-period values
  both stand, `CHECK (supersedable OR invalidated_at IS NULL)` + the CI schema-test forbid a stored
  winner, and the `attribute_conflicts` / `attribute_value_as_of` recipes + the recipe linter surface
  them without ever returning a single value. **D42's surfacing semantics are preserved**, now living
  as rows of `facts` instead of a separate projection.

So `claim_attribute_facts` and `attribute_evidence` are **removed** (their evidence merges into
`fact_evidence`); the `attributes` registry merges into `governed_relationships` (§3). The D42 design
doc (`nonrelational_facts_design.md`) is read as the *why-we-surface* rationale; `fact_layer_design.md`
(D43) is the *how supersedable ones additionally get a value*. Full reasoning + the reviewer round:
`plan/analysis/fact_layer_architecture_research/`.

---

## 10. Graph analytics writeback (D11) & projection snapshots (D7, D40)

P1/P2/P3 are **derived projections**; two things flow *back into* Postgres because the rest of the
system reads them: (1) **community detection + centrality** (D11 — Louvain/Leiden run externally;
PageRank/K-Core/WCC natively), serving K1 refresh triggers and salience priors; and (2) a
**snapshot registry** for P1/P2/P3 (D7/D40) — observability, validation gating, reader
coordination. Per-entity analytics are **regenerated each rebuild** and **garbage-collected** when
their snapshot is superseded — without GC these tables grow by ~entities-per-cycle forever at the
6-hourly cadence, which contradicts their disposable intent.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- projection_snapshots — registry of P1/P2/P3 rebuilds (D7/D40). Immutable versioned snapshots;
-- a validation gate must pass before is_latest flips (failure ⇒ previous snapshot keeps serving).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE projection_snapshots (
  snapshot_id     uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  plane           projection_plane NOT NULL,   -- P1_search | P2_graph | P3_corpusfs
  version         text NOT NULL,               -- monotonic/timestamped snapshot version (also the GCS path segment)
  gcs_uri         text NOT NULL,               -- gs://…/snapshots/<version>/
  status          snapshot_status NOT NULL DEFAULT 'building', -- building | validating | published | superseded | failed
  is_latest       boolean NOT NULL DEFAULT false, -- the pointer readers follow; exactly one per (deployment,plane)
  row_counts      jsonb,                       -- per-table counts validated against Postgres (D7 validation gate)
  validation      jsonb,                       -- validation report (pass/fail per check)
  built_from_watermark timestamptz,            -- max ingested_at included — bounds projection staleness (freshness SLA = cadence, D7)
  built_at        timestamptz NOT NULL DEFAULT now(),
  published_at    timestamptz,
  UNIQUE (deployment_id, plane, version),
  UNIQUE (deployment_id, snapshot_id)           -- composite-FK target (tenancy isolation, §0)
);
COMMENT ON TABLE projection_snapshots IS
  'Registry of immutable P1/P2/P3 snapshots (D7/D40). Validation gates is_latest; old snapshots are free point-in-time debugging artifacts. Mirrors the GCS latest pointer for operators/workers.';
CREATE UNIQUE INDEX ux_snapshot_latest ON projection_snapshots (deployment_id, plane) WHERE is_latest;

-- ─────────────────────────────────────────────────────────────────────────
-- communities — detected entity communities per P2 snapshot (D11). Recomputed each rebuild.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE communities (
  community_id    uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  snapshot_id     uuid NOT NULL,               -- which (P2_graph) rebuild produced this partition (composite FK below)
  label           text,                        -- optional human/LLM topic label (K1 hint)
  size            integer NOT NULL,            -- member count; an emerging giant community can signal over-merge (health metric, registries §10)
  algorithm       community_algorithm NOT NULL,-- leiden | louvain (external pass) — D11
  detected_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deployment_id, community_id),         -- composite-FK target
  FOREIGN KEY (deployment_id, snapshot_id) REFERENCES projection_snapshots (deployment_id, snapshot_id) ON DELETE CASCADE
);
COMMENT ON TABLE communities IS
  'Externally-detected communities per P2 graph snapshot (D11). Feed K1 refresh triggers ("claims in community C changed") and salience; recomputed each rebuild and GC''d with their snapshot (graph stays a projection). FK references must be a plane=P2_graph snapshot (invariant; the writer only inserts P2 snapshots here).';
CREATE INDEX ix_communities_snapshot ON communities (snapshot_id);

-- ─────────────────────────────────────────────────────────────────────────
-- entity_graph_metrics — per-entity centrality + community membership per snapshot (D11). PageRank
-- = salience prior; degree feeds entities.graph_degree (blast-radius) — refreshed ONLY from the
-- currently-published is_latest P2 snapshot, after the validation gate passes, so the auto-merge
-- gate is never computed from a stale/unvalidated projection. component_id is a synthetic
-- per-snapshot WCC grouping label (NOT an FK).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE entity_graph_metrics (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  entity_id       uuid NOT NULL,               -- composite FK below
  snapshot_id     uuid NOT NULL,               -- composite FK below (a P2_graph snapshot)
  community_id    uuid,                        -- this entity's community in this snapshot (composite FK below)
  pagerank        double precision,            -- salience prior (retrieval rank + K3 filter)
  degree          integer,                     -- relation degree — copied into entities.graph_degree from the latest published snapshot only
  k_core          integer,                     -- k-core number (hub-ness)
  component_id    uuid,                        -- synthetic per-snapshot weakly-connected-component label (NOT an FK; scoped to snapshot_id)
  computed_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (deployment_id, entity_id, snapshot_id),
  FOREIGN KEY (deployment_id, entity_id)    REFERENCES entities (deployment_id, entity_id) ON DELETE CASCADE,
  FOREIGN KEY (deployment_id, snapshot_id)  REFERENCES projection_snapshots (deployment_id, snapshot_id) ON DELETE CASCADE,
  FOREIGN KEY (deployment_id, community_id) REFERENCES communities (deployment_id, community_id) ON DELETE SET NULL (community_id)
);
COMMENT ON TABLE entity_graph_metrics IS
  'Per-entity graph analytics written back from each P2 rebuild (D11): PageRank salience, degree (blast-radius), k-core, community, WCC. Read by retrieval ranking, K3 filtering, ER health checks. GC''d when its snapshot is superseded. entities.graph_degree is refreshed only from the published is_latest snapshot.';
CREATE INDEX ix_egm_entity   ON entity_graph_metrics (entity_id);
CREATE INDEX ix_egm_snapshot ON entity_graph_metrics (snapshot_id);
```

**Retention/GC (D7 disposability).** On a successful publish (the `is_latest` flip), the rebuild's
finalize step **deletes `communities` and `entity_graph_metrics` rows of superseded snapshots**
(keeping the latest, or latest-N for debugging) — the `ON DELETE CASCADE` from
`projection_snapshots` does this when a superseded snapshot row is pruned, or the finalize step
deletes them directly. The lightweight `projection_snapshots` registry rows and the GCS snapshot
objects are retained as point-in-time debugging artifacts independently of this per-entity GC.

---

## 11. K-plane provenance & refresh triggers (D1, D12)

The K plane (K1/K2/K3) is **compiled markdown whose source of truth is the git repo**, backed up
independently (D1). Postgres stores only **provenance** (which compiled artifact references which
claims/relations/documents) and **triggers** (the debounced refresh queue) — needed for
**incremental refresh** ("recompile only artifacts whose referenced claims changed", D12) and the
**deletion cascade** (a removed input emits a tombstone signal to the K layer, D37).

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- knowledge_artifacts — the PG handle on a K-plane git file (provenance/trigger target, D1).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE knowledge_artifacts (
  artifact_id     uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  layer           knowledge_layer NOT NULL,    -- K1 | K2 | K3
  scope_id        uuid,                        -- non-null for K2 scope artifacts (composite FK below)
  git_path        text NOT NULL,               -- path of the markdown file in the K repo
  kind            text,                        -- 'summary' | 'profile' | 'belief' | 'decision_log' | ...
  content_hash    text,                        -- hash of the git file at last compile (change detection)
  compiler_version text,                       -- LOGICAL FK → pipeline_component_versions (knowledge_compiler — Codex/OpenCode session config)
  last_compiled_at timestamptz,
  status          knowledge_artifact_status NOT NULL DEFAULT 'active', -- active | stale | tombstoned
  UNIQUE (deployment_id, git_path),
  UNIQUE (deployment_id, artifact_id),          -- composite-FK target
  FOREIGN KEY (deployment_id, scope_id) REFERENCES scopes (deployment_id, scope_id) ON DELETE SET NULL (scope_id)
);
COMMENT ON TABLE knowledge_artifacts IS
  'Provenance handle on each K-plane git file (D1). PG holds the handle + evidence links + compile state; git holds the content. Enables incremental recompile and deletion tombstones without making PG authoritative for K.';
CREATE INDEX ix_kartifacts_scope ON knowledge_artifacts (scope_id);

-- ─────────────────────────────────────────────────────────────────────────
-- knowledge_artifact_evidence — the belief/summary ⇄ evidence links (K3 requirement + cascade).
-- "every belief links its supporting and contradicting evidence" (requirements_v3 K3). Also lets a
-- deleted document/claim find the K artifacts to tombstone/recompile. A single link targets EXACTLY
-- ONE of claim/relation/doc (the others NULL) — so a surrogate PK + a num_nonnulls CHECK + a
-- NULL-tolerant unique index, NOT an all-columns PK (PK columns cannot be NULL).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE knowledge_artifact_evidence (
  evidence_link_id uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  artifact_id     uuid NOT NULL,               -- composite FK below, ON DELETE CASCADE
  claim_id        uuid,                        -- LOGICAL FK → claims (partitioned)
  relation_id     uuid,                        -- composite FK below, ON DELETE CASCADE (real, relations is not partitioned)
  doc_id          uuid,                        -- LOGICAL FK → documents
  role            knowledge_evidence_role NOT NULL, -- supports | contradicts | cites (K3 links supporting AND contradicting evidence)
  CHECK (num_nonnulls(claim_id, relation_id, doc_id) = 1),  -- exactly one target per link
  FOREIGN KEY (deployment_id, artifact_id) REFERENCES knowledge_artifacts (deployment_id, artifact_id) ON DELETE CASCADE,
  FOREIGN KEY (deployment_id, relation_id) REFERENCES relations (deployment_id, relation_id) ON DELETE CASCADE
);
COMMENT ON TABLE knowledge_artifact_evidence IS
  'Links K artifacts (esp. K3 beliefs) to the ONE claim/relation/document each evidence row supports or contradicts (requirements_v3 K3). Drives "recompile artifacts whose evidence changed" (D12) and the deletion-cascade tombstone signal (D37). Exactly-one-target enforced by CHECK; surrogate PK because the targets are nullable alternatives.';
-- NULL-tolerant dedup (one link per (artifact, target, role)); NULLS NOT DISTINCT treats the two
-- NULL targets as equal so the populated one is the discriminator:
CREATE UNIQUE INDEX ux_kae_link ON knowledge_artifact_evidence (artifact_id, role, claim_id, relation_id, doc_id) NULLS NOT DISTINCT;
CREATE INDEX ix_kae_claim    ON knowledge_artifact_evidence (claim_id)    WHERE claim_id IS NOT NULL;
CREATE INDEX ix_kae_relation ON knowledge_artifact_evidence (relation_id) WHERE relation_id IS NOT NULL;
CREATE INDEX ix_kae_doc      ON knowledge_artifact_evidence (doc_id)      WHERE doc_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────
-- knowledge_refresh_queue — the debounced aggregate-layer trigger (D12). K1/K2/K3 fire on
-- windows/debounce ("N new claims or T minutes") + "claims in community C changed" (D11). Hot files
-- (root index.md) use a rolling-window delay (not_before).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE knowledge_refresh_queue (
  refresh_id      uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  artifact_id     uuid,                        -- composite FK below (nullable); NULL = "decide which" at processing time
  scope_id        uuid,                        -- composite FK below
  trigger         knowledge_trigger NOT NULL,  -- claims_changed | community_changed | debounce_timer | manual | tombstone
  payload         jsonb,                       -- e.g. {changed_claim_ids:[…]} | {community_id:…} | {deleted_doc_id:…}
  not_before      timestamptz,                 -- rolling-window delay for hot files (D12) — don't process before this
  status          refresh_status NOT NULL DEFAULT 'pending', -- pending | running | done | failed
  enqueued_at     timestamptz NOT NULL DEFAULT now(),
  processed_at    timestamptz,
  FOREIGN KEY (deployment_id, artifact_id) REFERENCES knowledge_artifacts (deployment_id, artifact_id) ON DELETE CASCADE,
  FOREIGN KEY (deployment_id, scope_id)    REFERENCES scopes (deployment_id, scope_id) ON DELETE CASCADE
);
COMMENT ON TABLE knowledge_refresh_queue IS
  'Debounced refresh triggers for the aggregate K layers (D12). Coalesces "N new claims or T minutes" + community-change + tombstone signals; not_before implements the hot-file rolling-window delay.';
CREATE INDEX ix_krefresh_runnable ON knowledge_refresh_queue (deployment_id, status, not_before) WHERE status = 'pending';
```

---

## 12. Partitioning & partition pruning (D23)

Six append-only E-plane tables are partitioned for scale (D23). **Five** are **RANGE-partitioned by
month** (`pg_partman`) on their transaction-time column; **`relation_evidence` is HASH-partitioned by
`relation_id`** (rationale below). Monthly RANGE caps btree size, makes "drop the oldest month from
the *hot* set" a partition detach, and aligns with projection archival (p2 §8). **This is binding**
(the schema is partitioned as stated); a load-test (registries §11 spike 4, sized against *ungated*
volume per D25) may change the *cadence* or the hash *partition count* — any such change is a
documented revision to D23 and to this section, not an open "maybe".

| Table | Partition key | FK policy |
|---|---|---|
| `mentions` | `created_at` (monthly RANGE) | logical (D23-named) |
| `resolution_decisions` | `decided_at` (monthly RANGE) | logical (D23-named) |
| `relation_evidence` | **`HASH(relation_id)`** | logical (refines D23 — §17) |
| `claims` | `ingested_at` (monthly RANGE) | logical |
| `claim_extraction_decisions` | `decided_at` (monthly RANGE) | logical |
| `chunks` | `created_at` (monthly RANGE) | logical |

D23 explicitly names the first three (sized at 10⁸); the other three are partitioned on the same
principle (large, append-only, queried by id/parent not fuzzy-scanned). **`entities` and `aliases`
are deliberately NOT partitioned** (≤10⁷, the blocking targets whose GIN trigram/phonetic indexes
must span the whole set, D23). `relations` and `relation_adjudications` are not partitioned (distinct
facts + their adjudications are far smaller than the assertion-grain tables).

**Partition pruning on ID lookups.** Most hot queries select by id/parent (`doc_id → claims`,
`mention_id → resolution_decisions`, `relation_id → relation_evidence`), which do *not* mention the
partition key, so a naive query scans every monthly partition's local index. The mitigation, applied
by the data-access layer: **UUIDv7 ids embed their creation timestamp**, and a child row's creation
time is closely correlated with its parent's ingest time, so the application derives a time bound
from the id (or from the parent's `ingested_at`) and adds it as a predicate (e.g.
`AND ingested_at BETWEEN $lo AND $hi`), pruning to 1–2 partitions. This works for every
ingest-time-correlated table (`claims`, `mentions`, `chunks`, `claim_extraction_decisions`, and —
for the first-resolution pass — `resolution_decisions`).

**`relation_evidence` is the exception, and is the reason it is hash-partitioned:** evidence for a
popular fact accrues over the fact's whole life, so an id-derived time bound would *not* prune a
`relation_id → evidence` lookup. Partitioning by `HASH(relation_id)` instead prunes relation
hydration to one partition *and* makes the real `PRIMARY KEY (relation_id, claim_id)` evidence-once
guarantee enforceable in-DB (a partitioned PK must include the partition key, which `relation_id` now
is). This refines D23 (which named it for monthly partitioning) for this one table — §17 records the
recommended D23 update. The `claim_id` reverse lookup still fans across hash partitions, but it is the
cold path.

**Partition-key consequences in the DDL:** a partitioned table's PRIMARY KEY/UNIQUE must include the
partition key, so the five RANGE tables use composite PKs `(id, <time>)` and `relation_evidence` uses
`(relation_id, claim_id)`. The application treats the UUIDv7 alone as identity (globally unique by
construction); the composite is the Postgres mechanical requirement.

---

## 13. Deletion / forget cascade (D37, requirements_v3)

Removing an input propagates through every derived layer, and **hard delete** of the original bytes
must be supported (GDPR forget, D37). Deletion is executed by a **deletion worker in batches**
(the large tables are partitioned and logical-FK, so there is no single giant `ON DELETE CASCADE`
transaction); the real composite FKs on the smaller tables are the integrity backstop. Two modes:

### 13.1 Normal delete (remove a document; retain audit history)

1. **K tombstone first.** Before touching evidence, enqueue a `knowledge_refresh_queue` row with
   `trigger='tombstone'` carrying the doc/claim ids (found via `knowledge_artifact_evidence`), so
   the K compiler recompiles/removes affected artifacts in git (the tombstone signal, D37). Doing
   this first ensures the links are still present to discover.
2. **GCS**: purge the document's raw + artifacts objects.
3. **`documents`**: **soft-tombstone** — set `status='deleted'`, null the artifact URIs, set
   `deleted_at`; **keep the row** (so the `deleted` enum value and `ix_documents_live` are
   meaningful, the logical-FK auditor distinguishes "forgotten" from "never existed", and crossref
   targets resolve sanely). The worker then clears the document's `document_sections` (cascade) and
   sets dependent `document_crossrefs.to_doc_id = NULL, resolved = false` while **retaining
   `raw_citation`** so the link can be re-resolved if the target is re-ingested.
4. **`chunks`** (logical FK): the worker deletes the doc's chunks (their Lance vectors drop on the
   next P1 maintenance/rebuild). It deletes a document's chunks in the **same batch as / before** the
   `document_sections` rows, so the auditor never flags a transient orphaned `chunk.section_id`
   (and the auditor ignores rows for documents with `deleted_at` set).
5. **`claims`** (logical FK): deleted with their chunks; the worker deletes the dependent
   `mentions`, `claim_extraction_decisions`, `grounding_audits`, and `relation_evidence` rows.
   `mentions → resolution_decisions` are deleted likewise.
6. **`relations`**: **not** deleted with one document's claims — a relation is a *shared* fact. The
   worker recomputes `evidence_count`/`contradict_count` (a `COUNT(DISTINCT claim_id)`, so duplicates
   cannot inflate it). A relation whose supporting evidence drops to zero is **retired by setting
   `invalidated_at`** (so the generated `status` becomes `invalidated` and the projection stops
   emitting it) — it is **not physically deleted**, because `relation_adjudications` and
   `knowledge_artifact_evidence` reference it and the audit trail is retained. A
   `relation_adjudications` row records the retirement reason so it is distinguishable from a
   supersession in audit.
7. **`entities`**: not deleted; a separate GC **retires** (`status='retired'`) entities with zero
   surviving mentions. They are **not physically deleted**, because `merge_events`,
   `resolution_exclusions`, `relation_adjudications`, and `entity_graph_metrics` reference them and
   D21 mandates retaining merge history for un-merge. Retired entities are not emitted on rebuild.
8. **P1/P2/P3**: cascade "for free" — projections don't materialize removed/retired data on the next
   rebuild (D40).

### 13.2 Hard forget (GDPR — erase the bytes *and* the derived text)

Normal delete already purges the GCS bytes and the document row's text-bearing URIs. A full forget
additionally **scrubs or deletes the source-bearing payloads** that normal delete retains for audit:
`relation_adjudications.features`, `merge_events.evidence`, `mentions.context`/`surface_form`, and
any `claim_text`/`source_span` already removed with the claims. Because those audit rows reference
`relations`/`entities` via real composite FKs, a forget that *physically* deletes a relation/entity
must first delete or anonymize the referencing audit rows (or rely on the retire-don't-delete model
of §13.1 and scrub the free-text fields in place). The worker performs this as an explicit forget
pass, distinct from normal delete, and records it in `processing_state` (`stage`-scoped) for audit
of the erasure itself.

The logical-FK **auditor** (run periodically) catches any orphan or duplicate-`(relation_id,
claim_id)` the worker missed, and ignores rows belonging to documents with `deleted_at` set (a
delete in flight).

---

## 14. How a write flows through the schema (worked example)

From `concepts.md`'s running example — *Doc C (Jan 2026): "Alice Novak left Acme to found Beacon
Labs."*

1. **E0** `documents` row (`ingesting`→`ready`), `document_sections` rows; `processing_state` tracks
   each sub-worker; `cost_ledger` logs the OCR/structure calls (idempotent per attempt).
2. **E1** `chunks` rows with offsets + `context_prefix`; vectors land in Lance keyed by `chunk_id`.
3. **E2 Selection** keeps the two verifiable propositions (any drop/edit → `claim_extraction_decisions`).
   Kept propositions → `claims` (`c3`, `c4`) with `source_span`, offsets, `added_context`,
   `anchor_ok`/`window_membership_ok` true (the CHECK); mentions of "Alice Novak", "Acme", "Beacon
   Labs" → `mentions` with `canonical_name_form`.
4. **Resolution** (T0–T4) writes `resolution_decisions` (method ∈ {T0,T3,T4_*,human}) linking each
   mention to an `entities` row via the `aliases` blocking indexes; "Beacon Labs" is new
   (`is_new_entity`).
5. **E3 normalize**: `c4` → `(alice, founded, beacon_labs)` — new `relations` row (passes
   domain/range via the normalizer's parent-walk), one `relation_evidence(supports)` row keyed
   `(relation_id, claim_id)` (a re-link is an `ON CONFLICT` no-op). `c3` triggers **supersession** on `(alice, works_for, acme)`: the
   blocking index `ix_relations_block_subj` finds it, the cascade adjudicates `supersede`, a
   `relation_adjudications` row records why, and the relation's `valid_until`/`invalidated_at` close
   (the GiST EXCLUDE permits this — the closed window no longer overlaps a live one; `c1`,`c2` claims
   untouched, D3). `status` flips to `invalidated` automatically (generated column).
6. **Projections**: next P2 rebuild re-points edges; `entity_graph_metrics`/`communities` write back
   (old snapshot's rows GC'd); `projection_snapshots` records the new version and flips `is_latest`
   after validation. `knowledge_refresh_queue` fires `claims_changed` for any K artifact whose
   evidence referenced the Acme employment fact.

---

## 15. Non-goals (scope boundaries, not deferrals)

- **No `graph_events` outbox / incremental-sync state.** P2 is rebuild-first (D7); incremental is a
  *documented alternative* (`p2_graph_design.md` §5), not built.
- **No value/salience-gate state** (`gate_decisions` / `document_extraction_state` /
  `salience_gate_versions`) — D25–D30 withdrawn. Junk-control is in-call E2 Selection
  (`claim_extraction_decisions`) + D2 redundancy-collapse + content-hash idempotency.
- **No `external_ids` table.** Resolution is registry-self-contained (D20); future internal/domain
  authoritative IDs would attach as *aliases*, never as the canonical `entity_id`.
- **No vectors in Postgres.** All embeddings live in Lance (P1); PG stores opaque `*_ref` keys +
  model/version. HNSW never in OLTP (D8/D23).
- **No document/chunk body text in Postgres** (D37) — bodies in GCS; PG holds offsets + URIs.
- **No fact/opinion/prediction claim type** — opinions are dropped at Selection, not stored as typed
  claims (§8 reconciliation note).
- **Supersedable literal facts NOW get a believed, closeable value (D43 — was a D42 non-goal).** A
  single-valued `effective_period` *state* (a balance, headcount, status) is a `supersedable` literal
  row of `facts` with a real `valid_from`/`valid_until` that a later value caps — so "headcount as of
  mid-2024" has a structured answer. This **lifts** D42's "no believed pure-literal value" non-goal for
  the supersedable subset.
- **No *resolution* of same-period non-relational disagreements (D42, preserved by D43).** Two sources
  giving different figures for the **same closed period** ("$5M" vs "$7M" for FY2023) are
  **non-supersedable** literal facts: the *coexist* EXCLUDE arm keeps both, `CHECK (supersedable OR
  invalidated_at IS NULL)` + the CI test forbid a stored winner, and the linter bars a single-value
  answer. Picking a winner stays a non-goal; both stand, surfaced (`attribute_conflicts` recipe + a
  `contradiction_group`).
- **No structured supersession of non-relational *restatements* (D42, preserved).** A later source
  correcting an earlier figure for the **same** period ("$5M"→"$5.2M" FY2023) is a same-period
  disagreement (`conflict_state='restatement'`), surfaced as an `asserted_at`-ordered hint — *not*
  supersession (that closes a *state* window, not a restated period). A believed working value for a
  restated period is K3 narrative, never an E-plane verdict.
- **No multi-interval / recurring / un-datable claim validity (D41).** The single
  `claim_valid_from`/`until` interval does not model recurrence ("every Q4") or anchor-events that
  can't be dated at extraction ("as of the merger"); D31 decomposition absorbs most multi-span
  sentences into atomic single-interval claims. The documented upgrade is an expressivity child table
  (btree-indexed, D23-restamped), built only on measured demand (§17).

---

## 16. Decision → table map

| Decision | Realized by |
|---|---|
| D1 split source of truth; versioned processing | `pipeline_component_versions`; K-plane provenance §11; `*_version` columns |
| D2 claims/facts distinct, M:N evidence | `claims`, `facts` (`relations` = entity view), `fact_evidence` (+ `evidence_count`) |
| D3 supersession at fact level, bi-temporal | `facts` 4 temporal columns + 3 GiST EXCLUDE arms; `fact_adjudications`; claims immutable (incl. their D41 asserted-validity interval) |
| D4 supersession blocking + cheap-first cascade | `ix_relations_block_subj/obj`; `relation_adjudications.method` (incl. `novelty_gate`) |
| D5 governed predicate registry + `other:` | `predicates` (`synonyms`, `tier='other'` upsert, `usage_count` funnel) |
| D6 graph is a projection; validity has one home | adjudicated validity only on `relations`; generated `status`; claim-validity is evidence, not a second home (D41); analytics writeback §10 |
| D7 rebuild-first; immutable snapshots | `projection_snapshots`; replay via `*_version` + decision ledgers; snapshot GC |
| D8 fact-label embeddings in Lance (entity + literal) | `facts.fact_label*` + `*_embedding_ref` keyed by `fact_id` (no PG vectors); graph search filters `object_kind='entity'` |
| D9 search/rerank; evidence-count + graph-distance | `relations.evidence_count`; `entity_graph_metrics.pagerank/degree` |
| D11 communities external → write back to PG | `communities`, `entity_graph_metrics` (+ GC) |
| D12 idempotency, retries, DLQ, debounced K triggers | `processing_state`, `cost_ledger`, `knowledge_refresh_queue` |
| D15/D18 ontology core+extensions, domain/range | `entity_types`, `predicates`, `predicate_signatures` (normalizer-enforced), `extension_packs` |
| D16 one graph, scope views | `scopes`, `scope_interests` |
| D17 T0–T4 cascade, block-loose/decide-tight | `aliases` composite GIN indexes; `resolution_decisions.method` (CHECK excludes T1/T2); `resolver_versions` |
| D19 coref in-call | `mentions.canonical_name_form` (no coref model/table) |
| D20 no external authority | non-goal §15 |
| D21 clustering, reversibility, generic-id guard | `merge_events` (+ `trigger_lemmas`), `resolution_exclusions`, `generic_identifier_guard`, `superseded_by` |
| D22 golden set + eval | `golden_pairs` (+ `expected_blocking_tier`), `golden_claim_labels`, `eval_runs`, `canary_cases` |
| D23 partition the big tables; btree-only; GIN on aliases | §12; `aliases` composite GIN trigram + Daitch-Mokotoff |
| D24 cluster review queue | `review_queue` (band boundaries in `resolver_versions.tier_config`) |
| D25 no value gate | non-goal §15 |
| D31/D32 Claimify staged extraction + grounding | `claims` (`source_span`, `added_context`, grounding flags + gate CHECK), `grounding_audits` |
| D33 extraction decision ledger | `claim_extraction_decisions` |
| D35 Selection recall envelope | `claims.kept_flagged`, `selection_drop_reason`, `protected_class`, `golden_claim_labels` |
| D36/D37 E0 sub-workers (incl. crossref version), storage split | `documents` (URIs + all four sub-worker versions), `document_crossrefs.crossref_version` |
| D39 PageIndex sections + placement | `document_sections` (path/role/span/summary/placement) |
| D40 P3 corpus filesystem | `projection_snapshots (plane='P3_corpusfs')` + `document(_sections).placement*` |
| D41 claim-grain source-asserted validity | `claims.claim_valid_from/until/precision/kind` (immutable); `claims_as_of` recipe (evidence-only); Lance scalar projection |
| D42 non-relational conflicts surfaced (subsumed by D43) | both-stand residue = non-supersedable literal rows of `facts` (coexist EXCLUDE arm + `CHECK (supersedable OR invalidated_at IS NULL)`); enums `attribute_value_domain`/`attribute_conflict_state`; `review_verdict='promote_to_relation'`; `attribute_conflicts`/`attribute_value_as_of` recipes |
| D43 unified `facts` verdict layer; supersedable gate | `governed_relationships` (§3); `facts` + `fact_evidence` + `fact_adjudications` + `relations` view (§9); enum `fact_object_kind`; generated `supersedable`/`status`; 3 GiST EXCLUDE arms; ATTACH-direct projection (p2 §5) |

---

## 17. Open spikes / recommended decision revisits (measure before locking)

Per CLAUDE.md, numbers are starting points. Items that may move the schema or a decision:

1. **`relation_evidence` partitioning — D23 amendment applied; update the decision text.** All
   three reviewers flagged that monthly time-partitioning defeats the `relation_id → evidence`
   lookup (time-uncorrelated, §12) *and* prevents a DB-level evidence-once guarantee. The schema
   therefore partitions `relation_evidence` by **`HASH(relation_id)`** with `PRIMARY KEY
   (relation_id, claim_id)` — relation hydration prunes to one partition and evidence-once is
   DB-enforced (no worker-invariant/auditor needed for *this* duplicate class). D23 names monthly
   partitioning for this table; **D23 should be updated** to record the hash-by-`relation_id`
   choice. Confirm the partition count (start 64) on a corpus-slice load-test.
2. **GIN blocking index shape — reconcile with D23/registries §9.** The schema makes the `aliases`
   blocking GIN indexes **composite (deployment_id-leading, via `btree_gin`)** to deliver the §0
   tenancy invariant and selectivity in the single-DB realization. D23/registries §9 currently
   describe single-column GIN on `normalized_lemma`. Update those texts to match, or, if
   schema-per-deployment (realization b) is mandated, drop the `btree_gin` extension and revert to
   single-column GIN. Decide on the realization.
3. **Embedding dimension** (questions Q3): pins `pipeline_component_versions.embedding_dim` and the
   re-embedding batch path — the hardest thing to change later.
4. **Logical-FK auditor cost**: the periodic orphan + duplicate-`(relation_id, claim_id)` check over
   the partitioned tables — confirm it stays cheap enough to run often; else reconsider selective
   real FKs (or spike #1's hash-partition, which removes the duplicate check).
5. **K-provenance granularity**: whether `knowledge_artifact_evidence` at claim grain is affordable,
   or should coarsen to relation/community grain for the largest K1 summaries.
6. **Un-merge ↔ supersession ripple** (registries §11 spike 3): verify replaying
   `merge_events.pre_merge_membership_snapshot` correctly re-adjudicates relation windows closed
   under a merged identity (`relation_adjudications.superseded_by` supports it; the procedure needs a
   test).
7. **P3/D40 wording reconciliation.** D40 in `decisions.md` lists "the K-plane structure" as a P3
   build input; the binding `e0_files_design.md` §6 scopes K to a *cross-link*, not a structural
   dependency (so P3 stays rebuildable from the E spine + artifacts). This schema follows the binding
   design (P3 is `projection_snapshots` + placement columns, no K dependency); D40's phrasing should
   be corrected to match.
8. **Snapshot retention depth** (latest-only vs latest-N for `communities`/`entity_graph_metrics`):
   pick the debugging-history depth against storage cost.
9. **Claim asserted-validity (D41) — measure before locking.** (a) Precision/recall of the extracted
   `claim_valid_*` interval on a golden slice + a per-fact canary for window false-extraction (D35).
   (b) Fiscal-calendar expansion ("FY2023" ≠ calendar 2023 for off-calendar years) — `precision` + the
   grounded source substring keep a wrong expansion auditable, but exact resolution is an
   extraction-quality spike. (c) Whether the optional PG partial btree on `claim_valid_*` is ever
   needed (vs. Lance-only filtering) — load-test write-amplification against D23 first. (d) If
   recurrence / un-datable anchor-events prove load-bearing, the expressivity child table (btree-only,
   D23-restamped) is the documented upgrade — a named alternative, not a deferral.
10. **Non-relational extraction quality (D42 → D43) — measure before locking.** *(Under D43 the
    structures are the literal subset of `facts` + `fact_evidence`, not `claim_attribute_facts`/
    `attribute_evidence`; conflict-row sizing + the supersession write path moved to spike #11(d). The
    remaining items are extraction-quality concerns that hold regardless of table shape.)* (a) **Conflict-row
    sizing**: load-test the non-supersedable literal (both-stand) subset of `facts` + the `fact_evidence`
    volume on a corpus slice — conflict rows are exactly the ones the "distinct facts not assertions"
    collapse does *not* shrink, so the naive distinct-cell count under-estimates. (b) **Attribute-vocabulary
    fragmentation** P/R + canaries on `eval_suite='contradiction'` (do `revenue`/`net revenue`/`sales`
    co-register?). (c) **Value normalization incl. fiscal calendars** — the silent false-agreement risk
    (FY≠CY; "$5M" vs "$5MM" vs "$5bn"). (d) **Precision-subsumption** golden coverage
    (refinement-vs-conflict on dates/quantities). (e) Confirm the **no-belief-axis** is enforced — under
    D43 it is now DB-level (`CHECK (supersedable OR invalidated_at IS NULL)` + `trg_facts_lock_gate`
    freezing the asserted window), with the recipe-linter bar (no single-value answer for a both-stand
    figure) as the application-side companion; a CI schema-test pins both.
11. **Unified `facts` layer (D43) — measure before locking.** (a) **Supersedable-vs-both-stand
    classification** is now verdict-critical (a mis-marked `measurement_period` would *silently
    supersede* figures that must both-stand) — golden-gate `claim_valid_kind`/`default_valid_kind` on
    `eval_suite='contradiction'`, start strict (default `measurement_period`). **The biggest correctness
    risk.** (b) **Value normalization is now on the verdict path** (a FY≠CY / `$5M`-vs-`$5MM` error
    writes a wrong *believed* window) — verify **normalize-or-refuse** (ambiguous ⇒ `contradiction_group`,
    never a confident `valid_from`). (c) **Cardinality** (`single`/`set`) golden coverage — a wrong
    branch fabricates conflicts or hides supersession. (d) **Scale**: load-test the unified-table
    conflict-row sizing + the supersession write path; verify the planner uses the partial
    `WHERE object_kind='entity'` indexes *through the `relations` view*; load-test **ATTACH bulk-COPY
    throughput** at 10⁸ before deleting the Parquet build path (attach scanner un-vendored,
    `ladybug_capabilities.md` §5). (e) Confirm the `supersedable`/`status` GENERATED columns are usable
    in the partial-index predicates as written.

## References

Designs: `overall_design.md` (§3 data model, §9 index), `registries_design.md` (D15–D24),
`e0_files_design.md` (D36–D40), `e2_e3_claims_relations_design.md` (D31–D35), `p2_graph_design.md`
(D6–D11). Explainer: `concepts.md`. Decisions: `decisions.md` (D1–D43); fact layer: `fact_layer_design.md`. Requirements:
`requirements/requirements_v3.md`. Open items: `questions.md`.
