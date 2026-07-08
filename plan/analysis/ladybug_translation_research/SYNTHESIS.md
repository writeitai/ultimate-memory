# Translating Postgres → LadybugDB — Synthesis

**Question.** How do we project the Postgres `entities`/`relations` (the graph slice of plane E) into
LadybugDB (the P2 graph — a maintained fork of Kùzu), and are the Postgres structures **easily
transferable**? Special focus: the transfer should be mechanical and robust.

**Method.** Three independent parallel analyses, then integrated here:
- **Codex** (`external_agents/codex.md`) — cloned the LadybugDB **source** to verify claims against tests.
- **Antigravity** (`external_agents/antigravity.md`) — docs + capability grounding; scorecard.
- An **internal 5-angle workflow** (node/rel model · type transferability · COPY mechanics · observations
  + as-of · recommendations), each angle adversarially verified.
Grounding: docs.ladybugdb.com (CREATE TABLE, attach/postgres, data-types), `ladybug_capabilities.md`,
the repo schema/decisions. Each finding is tagged **VERIFIED** (docs/source) or **INFERRED**.

**Reviewed** by Codex (*sound-with-fixes*) and Antigravity (*needs-rework*), both against LadybugDB
source. Their corrections are folded in: the as-of mechanism (you **cannot** `MATCH`-traverse a projected
graph — §4), the merge-survivor recursion must be **cycle-safe + gated** (§3), parallel edges are
**preserved not `DISTINCT`-deduped** (§3), keep-retracted is for **transaction-time** (not "closed facts")
and must **align with node retirement** (§3/§13), `COPY <Rel> FROM SQL_QUERY` is **VERIFIED** (not
inferred), LadybugDB **does** have `ALTER TABLE`, and graph-derived metrics (`pagerank`/`graph_degree`)
are **not** reprojected.

## Executive answer

**The Postgres structures transfer cleanly** — and they do so *because* of the design's own rules, not
in spite of them. The graph is a **dumb projection** (D6): it inherits *outcomes* (a believed
`(subject, predicate, object)` fact with validity windows), never *constraints*. So generated columns,
EXCLUDE arms, composite FKs, and D18 domain/range signatures all stay in Postgres and **correctly do not
transfer** — by design, not limitation. What crosses the boundary is a thin, well-shaped slice:

| Graph object | Postgres source |
|---|---|
| `Entity` node | `entities` (canonical **survivors only**) |
| `Document` node | `documents` (live only) |
| `RELATES` edge | `relations` (entity→entity, bi-temporal) |
| `MENTIONED_IN` edge | `mentions` ⋈ live `resolution_decisions` (**aggregated**) |
| `DOC_CROSSREF` edge | `document_crossrefs` (resolved only) |
| `IS_DOCUMENT` bridge | `documents.document_entity_id` (where set) |

**Observations and claims never project** (D43/D8) — a value is not a node, and a LadybugDB REL endpoint
*must* be a node table bound to a PK. The engine's node-only-endpoint rule and the design's
"value-is-not-a-node" rule are the same constraint from two sides.

The whole transfer reduces to **three mechanical transforms at the projection boundary** (a set of
Postgres views), plus **two correctness rules** the first-pass analyses got wrong:

- *Transforms:* (a) cast `timestamptz → AT TIME ZONE 'UTC'` (naive UTC `TIMESTAMP`); (b) cast Postgres
  ENUMs `→ ::text`; (c) drop graph-irrelevant columns (embeddings, audit, generated `status`).
- *Correctness rules (both external agents missed these; the internal verifiers caught them):*
  1. **Resolve merge redirects.** `merged_into` is a redirect, not a rewrite, and relations are *not*
     re-pointed in Postgres — so a naive `WHERE status='active'` join **drops every edge whose endpoint
     was merged away.** The export must follow `merged_into` recursively to the survivor and dedup.
  2. **Keep retracted edges** (within a retention window) **for transaction-time as-of**. Exporting
     `WHERE invalidated_at IS NULL` drops *retracted* beliefs (believed at T, later found wrong) and
     breaks transaction-time travel. (A valid-time *closed* fact — `valid_until` set, `invalidated_at`
     NULL — is **not** dropped by that filter; the rule is about retractions.) Endpoints must still
     survive the node filter — an edge whose endpoint was retired/forgotten (§13) is dropped.

**UUID-as-node-PK is VERIFIED** in LadybugDB source/tests (Codex cloned the tree; the public CREATE TABLE
docs are stale on this). So entity ids stay native `UUID` — no STRING cast — with a one-line build-time
smoke test + a documented STRING fallback for version drift.

The remaining unknowns are all **spikes**, not blockers: `COPY <RelTable> FROM SQL_QUERY('pg',…)` (the
cross-DB scanner is un-vendored), attach scan-pushdown at 10⁷–10⁸ rows, and `PROJECT_GRAPH_CYPHER`
parameter binding. The committed **Parquet rebuild path (D7) stays the safe baseline**; ATTACH-direct is
an optimization that consumes the *same* projection views.

---

## 1. Node / rel table model

**One `Entity` node table with `type` as a STRING property — not one table per type.** Entity types are
*registry data* (`entity_types`, extensible via packs/scopes under extend-never-fork, D15/D18), not a
fixed schema. Per-type tables would force schema churn + cross-table UNIONs on every new subtype and tie
the graph's shape to registry data. (LadybugDB **does** support `ALTER TABLE` — add/drop/rename columns,
add/drop rel connections — so this is an ergonomics + rebuild-discipline argument, *not* a DDL limitation;
an earlier "no ALTER" framing was wrong.) `type` is a cheap scalar filter.

**One generic `RELATES` rel table with `predicate` as a property — not per-predicate or
per-(subject_type,object_type) tables.** The vocabulary is governance-extensible (`other:<freetext>`),
core predicates carry *union* domains/ranges (`related_to: any→any`), and per-pair tables explode into
the 8×8 cross-product. Crucially they'd buy *nothing*: D18 signatures are enforced by the **E3 normalizer
at write time**, not the graph — the graph receives pre-validated relations. (VERIFIED in source: multi-pair
REL `COPY` requires explicit `(from=,to=)` options, so per-pair tables would also force partitioned loads —
another reason the single generic table wins.)

```cypher
-- NODES
CREATE NODE TABLE Entity(
  id              UUID PRIMARY KEY,   -- entities.entity_id  (VERIFIED: UUID PK works in source/tests; fallback ::text→STRING PK)
  type            STRING,             -- registry value (8 core types + extension subtypes) — DATA, not schema
  name            STRING,             -- entities.canonical_name
  normalized_name STRING,
  summary         STRING,             -- entities.profile_summary (nullable)
  created_at      TIMESTAMP           -- AT TIME ZONE 'UTC'
  -- NB: graph analytics (pagerank, graph_degree) are NOT loaded from Postgres — they are graph-DERIVED
  -- (D11), so reprojecting a stored value is circular. Compute them POST-load and write to the separate
  -- entity_graph_metrics table; do not put them in this load projection.
);
CREATE NODE TABLE Document(
  id           UUID PRIMARY KEY,      -- documents.doc_id  (DISTINCT id-space from Entity)
  title        STRING,
  source_uri   STRING,
  published_at DATE                   -- (published_at AT TIME ZONE 'UTC')::date  ← tz-cast AND date-truncate
);

-- SEMANTIC EDGES (project relations; bi-temporal; D2/D8/D10)
CREATE REL TABLE RELATES(
  FROM Entity TO Entity,
  relation_id         UUID,           -- provenance handle (rel prop, NOT a PK) → hydrate evidence/Lance
  predicate           STRING,         -- governed predicate incl. other:*
  fact                STRING,         -- relations.fact_label (short label, not full claim)
  evidence_count      INT64,
  contradict_count    INT64,
  confidence          DOUBLE,
  contradiction_group UUID,           -- both live sides of an unresolved contradiction share it
  valid_from          TIMESTAMP,      -- ┐ all four: AT TIME ZONE 'UTC'; the as-of payload (D10)
  valid_until         TIMESTAMP,      -- │
  ingested_at         TIMESTAMP,      -- │
  invalidated_at      TIMESTAMP       -- ┘ NULL = still believed; liveness DERIVED in Cypher — no `status` column (D6)
);

-- STRUCTURAL EDGES (E0/E1 metadata; no validity windows)
CREATE REL TABLE MENTIONED_IN(FROM Entity TO Document, mention_count INT64, first_seen TIMESTAMP);
CREATE REL TABLE DOC_CROSSREF(FROM Document TO Document, kind STRING, context STRING);  -- generalizes p2 §2 CITES
CREATE REL TABLE IS_DOCUMENT(FROM Entity TO Document);  -- bridge: a Document-typed entity ↔ its E0 doc row
```

Two structural notes (proposed edits to `p2_graph_design.md` §2): generalize its `CITES(FROM Document TO
Document, context)` to `DOC_CROSSREF(kind STRING, …)` (anti-explosion, same logic as the predicate
decision); and add the `IS_DOCUMENT` bridge from `documents.document_entity_id` (the Entity↔Document bridge
is already resolved in the schema — `postgres_schema_design.md` documents/entities composite FK — but p2 §2
doesn't emit it).

---

## 2. Type transferability (column-by-column)

Casts live in the **projection SELECT / `SQL_QUERY('pg',…)`** — don't rely on the attach scanner's type
mapping for `timestamptz`/ENUM (the attach type-map marks `timestamptz` unsupported; the engine *does*
have a `TIMESTAMP_TZ` type, but the scanner's exact mapping is unverified), so cast deterministically in
the views.

### `entities` → `Entity`

| column | PG type | target | verdict | transform |
|---|---|---|---|---|
| `entity_id` | uuid | `UUID PRIMARY KEY` | **clean** (VERIFIED) | native UUID; fallback `::text` |
| `deployment_id` | uuid | — | na | WHERE scope, never a column (D16) |
| `type` | text (registry FK) | `STRING` | **clean** | pass through — NOT an enum |
| `canonical_name` / `normalized_name` / `profile_summary` | text | `STRING` | **clean** | direct |
| `status` | `entity_status` enum | — | na | a *filter* + merge-redirect input (§3), not a column |
| `merged_into` | uuid self-FK | — | na-as-column | **load-bearing for export** (§3) |
| `mention_count` | integer | `INT64` | **clean** | `::bigint` |
| `graph_degree` | integer | — | na | graph-*derived* (D11) — reprojecting is circular; recompute in-graph |
| `profile_embedding_ref` | text | — | na | Lance key; no vectors in graph (D8) |
| `created_at` | timestamptz | `TIMESTAMP` | **needs-cast** | `AT TIME ZONE 'UTC'` |

### `relations` → `RELATES`

| column | PG type | target | verdict | transform |
|---|---|---|---|---|
| `subject_entity_id` / `object_entity_id` | uuid | `FROM`/`TO` (cols 1–2) | **clean** | **merge-redirect-resolved** (§3); positional binding |
| `relation_id` | uuid | `UUID` rel prop | **clean** | provenance (rel tables have no user PK) |
| `predicate` | text (registry FK) | `STRING` | **clean** | not an enum |
| `fact_label` | text | `STRING` | **clean** | short label (full text/vec in Lance, D8) |
| `evidence_count`/`contradict_count` | integer | `INT64` | **clean** | `::bigint` |
| `confidence` | real | `DOUBLE` | **clean** | `::float8` (explicit) |
| `contradiction_group` | uuid | `UUID` | **clean** | **must project** (don't drop — surfaces both conflict sides) |
| `valid_from`/`valid_until`/`ingested_at`/`invalidated_at` | timestamptz ×4 | `TIMESTAMP` ×4 | **needs-cast** | `AT TIME ZONE 'UTC'`; NULLs preserved |
| `status` | `relation_status` GENERATED | — | **drop** | derive liveness in Cypher (D6); don't replicate a generated mirror |
| `*_version` / `*_embedding_ref` / `created_at`/`updated_at` | text/tstz | — | na | stay in Postgres |

### `documents` / `document_crossrefs` / `mentions`

| column | PG type | target | verdict | transform |
|---|---|---|---|---|
| `documents.doc_id` | uuid | `UUID PK` | **clean** | |
| `documents.published_at` | timestamptz | `DATE` | **needs-cast** | `(… AT TIME ZONE 'UTC')::date` — tz-cast **and** date-truncate |
| `documents.document_entity_id` | uuid nullable | `IS_DOCUMENT` endpoint | **restructure** | emit bridge `WHERE NOT NULL`, **survivor-redirected** through the merge CTE (§3) |
| `document_crossrefs.to_doc_id` | uuid **nullable** | `TO Document` | **restructure** | **MUST `WHERE to_doc_id IS NOT NULL`** or COPY-REL throws (cited-but-not-ingested) |
| `document_crossrefs.kind` | `crossref_kind` enum | `STRING` | **needs-cast** | `::text` |
| `mentions.*` → `mention_count`/`first_seen` | aggregate | `INT64`/`TIMESTAMP` | **restructure** | no source table — `GROUP BY` over `mentions ⋈ live resolution_decisions` |

### Type rules (uniform)
- `timestamptz` → `AT TIME ZONE 'UTC'` → naive `TIMESTAMP` (unsupported in the attach map otherwise);
  for a DATE target apply `::date` **instead**.
- `uuid` → native `UUID` (PK + property); a STRING fallback must be applied **uniformly** to the PK *and*
  every endpoint (endpoints resolve by equality against the node PK — mixing STRING PK with UUID endpoints
  silently fails to load).
- Postgres ENUM → `::text` → `STRING`. `predicate`/`type` are registry **text, not enums** — don't over-cast.
- `integer`→`INT64`, `real`→`DOUBLE`, `numeric`→`DECIMAL` (or `::float8` for graph analytics).
- `text[]`/`jsonb` → **na** (no projected column uses them; LadybugDB *has* `LIST`/`JSON`, so they're
  transferable if ever needed — serialize explicitly; never assume PG-array-over-ATTACH works).

---

## 3. Load: ATTACH + COPY (via projection views), with the two correctness rules

**Hard engine rules (VERIFIED):** (1) a rel's FROM/TO resolve against the node PK *at COPY time* and a
missing endpoint **throws** — so **load + commit all nodes before any rel COPY**; (2) the endpoint columns
must be the **first two** selected, FROM-then-TO (positional binding).

**Recommendation: encapsulate every projection as a Postgres view** (`v_graph_entities`,
`v_graph_documents`, `v_graph_relates`, `v_graph_mentioned_in`, `v_graph_crossref`, `v_graph_is_document`),
added under `postgres_schema_design.md` §10. The views are the **single auditable COPY contract** — casts,
survivor-redirect, filters, and aggregation live in one place, decoupling the lean graph from the rich
OLTP schema and pinning the projection against base-schema drift.

```cypher
ATTACH 'dbname=ugm host=... user=ugm_graph_ro sslmode=require' AS pg (dbtype postgres);   -- read-only (D6/D7)
-- CREATE node + rel tables (§1)
-- NODES FIRST, then RELS (endpoints resolve against node PKs at COPY time — a missing endpoint throws):
COPY Entity       FROM SQL_QUERY('pg', 'SELECT * FROM v_graph_entities');
COPY Document     FROM SQL_QUERY('pg', 'SELECT * FROM v_graph_documents');
COPY RELATES      FROM SQL_QUERY('pg', 'SELECT * FROM v_graph_relates');
COPY MENTIONED_IN FROM SQL_QUERY('pg', 'SELECT * FROM v_graph_mentioned_in');
COPY DOC_CROSSREF FROM SQL_QUERY('pg', 'SELECT * FROM v_graph_crossref');
COPY IS_DOCUMENT  FROM SQL_QUERY('pg', 'SELECT * FROM v_graph_is_document');
```

**Deployment scope (D16).** A deployment is its *own* Postgres instance (`registries_design.md`), so the
attached DB already *is* the deployment — the views need **no `deployment_id` filter** and `SQL_QUERY`
needs no bind parameters (it takes a literal SQL string; there is no `:param` binding — if a deployment
ever shared a DB, the worker would literalize a *validated* UUID into the string, never pass a bind var).

**The correctness rules, baked into the views:**

1. **Merge-redirect (the major hole both external agents missed).** A merge is a *redirect, not a
   rewrite* (`entity_id` never reused; relations not re-pointed in PG). `v_graph_relates`,
   `v_graph_mentioned_in`, **and `v_graph_is_document`** must follow `merged_into` **recursively** (chains
   A→B→C) to the survivor on *every* entity endpoint. Without this a rebuild silently drops every edge
   touching a merged entity — contradicting p2 §5 ("a merge is a no-op in a rebuild — the next rebuild
   re-points edges"). **Cycle-safe + gated:** `merged_into` acyclicity is *not* schema-enforced, so the
   recursion needs a cycle guard, and a pre-snapshot **validation gate** must assert every retained
   endpoint resolves to exactly one non-merged survivor — a cycle or unresolved redirect **aborts the
   snapshot**, never loads a corrupt graph.
2. **Parallel edges are preserved, not `DISTINCT`-deduped.** Re-pointing can land two *distinct*
   relations (different `relation_id`/evidence/confidence) on the same `(from, predicate, to, window)`.
   `DISTINCT` can neither collapse them (the `relation_id`/evidence differ) nor should it — they are
   distinct facts. Keep them as parallel edges (REL is MANY_MANY); collapsing duplicate beliefs is
   **Postgres E3's** job (same-(s,p,o) supersession on the next normalization), not a projection trick. If
   in-graph collapse is ever wanted, define an explicit aggregation (group by resolved fact identity,
   carry `relation_ids` as a list) — never a blind `DISTINCT`.
3. **Keep retracted edges for transaction-time as-of (within retention), and align endpoints.** Don't
   filter `invalidated_at IS NULL`: that drops *retracted* beliefs (what we believed at T but later
   learned was wrong), breaking **transaction-time** travel. *(A valid-time **closed** fact — `valid_until`
   set, `invalidated_at` NULL — is **not** affected by that filter; the rule is about retractions, not
   closed facts.)* Keep live + recently-invalidated edges (retention window, p2 §8, N to measure). **But**
   the deletion/forget cascade (§13) *retires* entities while retaining invalidated relations, and retired
   entities aren't emitted as nodes — so a retained edge whose endpoint was retired/forgotten **must be
   dropped** (its endpoint can't be a node). Node and edge retention must align: emit a rel only if both
   survivor endpoints are present nodes; as-of therefore excludes forgotten-endpoint history (documented
   limit).

```sql
-- sketch of the load-bearing view (full DDL in postgres_schema_design.md §10)
CREATE VIEW v_graph_relates AS
WITH RECURSIVE surv AS (             -- entity_id → final survivor; CYCLE-guarded; flags unresolved for the gate
  /* walk merged_into to the row where merged_into IS NULL; emit (entity_id, survivor, survivor_is_emitted) */ …
)
SELECT s1.survivor AS "from", s2.survivor AS "to",          -- endpoints first, merge-redirected
       r.relation_id, r.predicate, r.fact_label AS fact,
       r.evidence_count::bigint, r.contradict_count::bigint, r.confidence::float8,
       r.contradiction_group,
       (r.valid_from AT TIME ZONE 'UTC')     AS valid_from,
       (r.valid_until AT TIME ZONE 'UTC')    AS valid_until,
       (r.ingested_at AT TIME ZONE 'UTC')    AS ingested_at,
       (r.invalidated_at AT TIME ZONE 'UTC') AS invalidated_at
FROM relations r
JOIN surv s1 ON s1.entity_id = r.subject_entity_id AND s1.survivor_is_emitted   -- endpoint present as a node
JOIN surv s2 ON s2.entity_id = r.object_entity_id  AND s2.survivor_is_emitted
WHERE r.invalidated_at IS NULL
   OR r.invalidated_at > now() - interval '<retention>';   -- keep recent retracted edges (tx-time as-of)
-- parallel edges (distinct relation_id) are PRESERVED; NO blind DISTINCT (rule 2)
```

Also: `MENTIONED_IN` = `GROUP BY (survivor, doc) → COUNT(*), (MIN(created_at) AT TIME ZONE 'UTC')` over
`mentions ⋈ resolution_decisions WHERE superseded_by IS NULL`, EXISTS-guarded to live docs; `DOC_CROSSREF`
filters `to_doc_id IS NOT NULL` and casts `kind::text`; `IS_DOCUMENT` redirects `document_entity_id`
through the survivor CTE too. One snapshot = one deployment (D16).

**Transport.** `COPY <Node> FROM SQL_QUERY('pg',…)` **and** `COPY <Rel> FROM SQL_QUERY('pg',…)` with
positional FROM/TO binding are both **VERIFIED** (the binder maps any COPY scan source — table function or
query — to rel endpoints via the first two projected columns: `bind_copy_from.cpp:244-258`). **Keep the
Parquet hop (D7) as the committed baseline** nonetheless: the cross-DB *scanner throughput* at 10⁷–10⁸ rows
and its WHERE/JOIN/GROUP-BY pushdown are unverified, and the 10⁸-row `MENTIONED_IN` aggregation + merge
recursion argue for a PG-side materialized export until measured. ATTACH-direct and Parquet consume the
*same* views.

---

## 4. Observations don't project; the as-of shape

**Observations have no legal edge shape.** `observations` has one entity column (`subject_entity_id`) and
the value in `statement` — deliberately no `object_entity_id`. A REL endpoint must be a node bound to a
PK; a literal has no PK identity. Reifying the value as a node is exactly what D18/D43 forbid. So the
engine rule and the design rule coincide; observations → P1/Lance only (and their embedding would be
un-indexable in-graph anyway — vector/FTS are node-property-only, D8). Claims likewise → Lance, not graph.

**As-of (D10) — corrected by the review (source-verified).** LadybugDB has no native temporal semantics;
*we* enforce it with predicates on the four naive-UTC `TIMESTAMP` columns. **But you cannot `MATCH`-
traverse a `PROJECT_GRAPH[_CYPHER]` projection.** Projected graphs are *transient inputs to GDS
algorithms* (PageRank, components, shortest-path); Cypher path `MATCH` runs against the persistent catalog,
switched only via `CREATE GRAPH` / `USE GRAPH`. Also `PROJECT_GRAPH_CYPHER` takes exactly `(STRING, STRING)`
— **no** parameter-map argument — and there is no `MATCH … IN GRAPH` / `USING GRAPH` traversal syntax.
*(This refines D10 / `ladybug_capabilities.md` §4, which overstated "as-of traversal via projected graphs"
— that mechanism works for **algorithms**, not for path `MATCH`.)* So as-of has two working shapes:

**(a) Inline recursive-pattern predicate** — the correctness baseline; one statement, no projection.
*(Corrected 2026-07 — the original example here used the outer `WHERE all(r IN rels(p) …)` form, which
is applied AFTER matching and is a correctness bug when combined with `SHORTEST`; the predicate must be
written inside the recursive pattern, where it is evaluated per edge during traversal. Full source-level
investigation + the query rulebook: `../ladybug_query_semantics.md`.)*
```cypher
MATCH p = (a:Entity {id:$focal})
    -[rs:RELATES* SHORTEST 1..3 (r, _ | WHERE
        r.ingested_at <= $as_of
    AND (r.invalidated_at IS NULL OR r.invalidated_at > $as_of)   -- transaction-time
    AND (r.valid_from  IS NULL OR r.valid_from  <= $as_of)
    AND (r.valid_until IS NULL OR r.valid_until >  $as_of))]-     -- valid-time
    (b:Entity)
RETURN p;
```
**(b) Materialized as-of graph** — for heavy/repeated as-of analytics: build a persistent graph at
rebuild (`CREATE GRAPH asof_<t>` + load the time-filtered edge set) and `USE GRAPH asof_<t>`. For GDS
algorithms specifically, `PROJECT_GRAPH('g', {'Entity':'true', 'RELATES':'<rel-predicate>'})` with the
timestamp **literalized** into the predicate string, then run the algorithm over `g` — `PROJECT_GRAPH` is
for algorithms, not path `MATCH`.

The two as-of axes compose with the snapshot history: pick the immutable snapshot *current at-or-before*
`$as_of` (not after), then the predicate does the fine cut. Current-belief default = the transaction-time
half (`invalidated_at IS NULL AND (valid_until IS NULL OR valid_until > $now)`) — a believed-historical
fact (valid_until set, invalidated_at NULL) is still current.

---

## 5. Transferability scorecard + recommendations

| Structure | Verdict |
|---|---|
| `Entity` node (UUID PK), `RELATES` edge, `predicate` as property | **clean** |
| bi-temporal columns | **needs-cast** (tz→UTC) |
| `relations.status` (generated) | **drop** (derive in Cypher) |
| merge-redirect on endpoints | **needs-restructure** (cycle-safe recursive survivor + validation gate; preserve parallel edges) |
| keep retracted edges for tx-time as-of | **needs-restructure** (retention filter; align endpoints — drop edges to retired nodes) |
| `MENTIONED_IN` (aggregate), `DOC_CROSSREF` (nullable filter + `kind::text`), `IS_DOCUMENT` (bridge) | **needs-restructure** |
| `published_at` → DATE | **needs-cast** (tz + date-trunc) |
| Postgres ENUM (`crossref_kind`) | **needs-cast** (`::text`) |
| observations / claims / signatures / generated cols / EXCLUDE / composite FK | **na (by design)** |

**Recommendations (make the PG schema more transferable):**
1. **Add `v_graph_*` projection views** (§10) — the COPY contract: deployment-scoped, pre-cast,
   pre-filtered, **survivor-redirected**, pre-aggregated. Single auditable boundary.
2. **Bake merge-redirect into `v_graph_relates`/`v_graph_mentioned_in`** (recursive `merged_into` +
   dedup) — the single highest-impact correctness fix.
3. **Push all casts into the views** (tz→UTC, `published_at::date`, `kind::text`, `::float8`, `::bigint`);
   `id` native `UUID` with a uniform STRING fallback.
4. **Drop `relations.status`**, derive liveness in Cypher; **keep `contradiction_group`**; **keep
   invalidated edges** within retention.
5. **Filter `DOC_CROSSREF` on `to_doc_id IS NOT NULL`**, EXISTS-guard `MENTIONED_IN` to live docs, emit
   `IS_DOCUMENT`; update p2 §2 (generalize `CITES`→`DOC_CROSSREF`, add the bridge, align the stale
   ontology/predicate vocabulary to D18 — resolves `questions.md` #27).
6. **Node-before-rel load order**; add a per-table PG-count vs graph-count gate before the snapshot
   pointer-swap.
7. **Keep observations/claims out** with an explicit assertion in the rebuild job (the ban is normative,
   D43/D18 — harden it so no future maintainer reifies them).
8. **Keep the Parquet hop committed (D7)**; treat ATTACH-direct REL-from-`SQL_QUERY` as an optimization to
   spike; the views serve both transports.

---

## 6. Open questions / spikes (none are blockers)

1. **UUID-as-PK on the deployed build** — source/test-verified; confirm against the running engine version
   with a one-line smoke test; STRING fallback documented.
2. **Cross-DB scan pushdown** — does the postgres scanner push WHERE/JOIN/GROUP BY into PG, or pull whole
   tables? Decides live ATTACH-scan vs PG-side materialized/Parquet for the 10⁸ `MENTIONED_IN`
   aggregation + the merge-survivor recursion. *(The `COPY <Rel> FROM SQL_QUERY` capability itself is
   now VERIFIED — `bind_copy_from.cpp:244-258`; the open part is throughput, not capability.)*
3. **Merge-redirect cycle/gate** — `merged_into` acyclicity is not schema-enforced; implement the
   recursive survivor resolution with a cycle guard + a pre-snapshot validation gate (every retained
   endpoint → exactly one non-merged emitted survivor, else abort). Verify the recursive CTE terminates
   on the real data.
4. **As-of mechanism** — RESOLVED: `MATCH` over a projected graph is **unsupported** (projections feed
   GDS only; `PROJECT_GRAPH_CYPHER` is `(STRING,STRING)`). As-of correctness = the inline
   recursive-pattern predicate (§4a); heavy/repeat = materialized persistent `CREATE GRAPH`/`USE GRAPH`
   (§4b). *(Corrected 2026-07: this spike originally said inline filtering "can't push the predicate
   into traversal" — wrong for the inline `(r, _ | WHERE …)` form, which IS evaluated per edge during
   the neighbor scan (`on_disk_graph.cpp:308`); only the outer `all(r IN rels(p) …)` form is post-hoc,
   and that form must never be combined with `SHORTEST`. See `../ladybug_query_semantics.md`.)* Spike
   re-aimed: measure per-edge evaluator cost of the inline form at corpus scale, and verify parameter
   binding inside inline predicates (untested upstream).
5. **NULL `TIMESTAMP` through the Parquet round-trip** — the `IS NULL OR …` guards assume SQL 3-valued
   logic; affects both as-of and the current-belief default.
6. **Attach scan throughput at 10⁷–10⁸** — gates ATTACH-direct vs the committed Parquet baseline.
7. **Node/edge retention alignment** — keep-retracted-edges (tx-time as-of) vs the §13 deletion cascade
   that retires entities: confirm the export drops edges to retired/forgotten endpoints (else COPY-REL
   throws) and document the as-of history limit that creates.
8. **`published_at` grain** (DATE vs naive TIMESTAMP) and **snapshot retention window N** (p2 §8) —
   numbers to measure.
9. **Self-loops / parallel edges** — legal under default MANY_MANY; preserved (distinct `relation_id`s),
   *not* collapsed in the view (rule 2); same-(s,p,o) collapse is Postgres E3's job.

## Sources
`external_agents/codex.md` (source/test-verified), `external_agents/antigravity.md`, the internal 5-angle
workflow (run `wf_988258e5-eba`). Docs: docs.ladybugdb.com (create-table, attach/postgres, data-types,
copy-from-subquery). Repo: `postgres_schema_design.md` §1/§3/§4/§9/§9.A, `p2_graph_design.md`,
`ladybug_capabilities.md`, `decisions.md` D6/D7/D8/D10/D11/D16/D18/D43.
