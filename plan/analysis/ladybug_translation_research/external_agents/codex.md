# LadybugDB Translation Analysis for Postgres Relations Graph

Author: Codex  
Date: 2026-06-25

## Executive Answer

The Postgres `entities` + `relations` design transfers to LadybugDB cleanly at the logical graph level: canonical entities become nodes, and D18/D43 `relations` already are exactly the entity-to-entity facts that Ladybug relationship tables require. `observations` correctly do not transfer to the graph because their object is a value/statement, not a node.

The transfer is easiest if LadybugDB uses:

```cypher
CREATE NODE TABLE Entity(
  entity_id UUID PRIMARY KEY,
  deployment_id UUID,
  type STRING,
  canonical_name STRING,
  normalized_name STRING,
  status STRING,
  merged_into UUID,
  type_confidence FLOAT,
  profile_summary STRING,
  mention_count INT64,
  graph_degree INT64,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE REL TABLE RELATES(
  FROM Entity TO Entity,
  relation_id UUID,
  deployment_id UUID,
  predicate STRING,
  valid_from TIMESTAMP,
  valid_until TIMESTAMP,
  ingested_at TIMESTAMP,
  invalidated_at TIMESTAMP,
  evidence_count INT64,
  contradict_count INT64,
  confidence FLOAT,
  contradiction_group UUID,
  status STRING,
  fact_label STRING,
  fact_label_version STRING,
  normalizer_version STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

This is a better fit than per-type node tables or per-predicate relationship tables because the Postgres ontology is governed data, not DDL. `postgres_schema_design.md` §3 says entity types and predicates are registry rows; §9 says relations are governed `(subject_entity, predicate, object_entity)` facts; `p2_graph_design.md` §2 already resolves the schema-full/evolving-ontology conflict by using a generic semantic edge table with `predicate` as a property. VERIFIED in repo docs.

Important correction: LadybugDB docs currently say node primary keys can be `STRING`, numeric, `DATE`, or `BLOB`, but the current LadybugDB source/tests verify `UUID` node primary keys work. Tests include `CREATE NODE TABLE test(id UUID, PRIMARY KEY(id));` with successful node creation and matching in `/tmp/ladybug-src/test/test_files/transaction/create_node/create_empty_checkpoint.test` and `dml_node/create/create_empty.test`; another issue regression creates `V(id UUID PRIMARY KEY)` and `E(FROM V TO V)`. So UUID entity IDs do not need to be cast to `STRING` on current LadybugDB. Mark this as version-sensitive because the public docs at https://docs.ladybugdb.com/cypher/data-definition/create-table/ are stale/incomplete on UUID PKs. VERIFIED in source/tests; docs contradiction noted.

## 1. Node/Rel Table Model

### Recommended node model: one `Entity` node table

Use one `Entity` node table with `type STRING`, not one node table per entity type.

Reasons:

- Postgres type governance is data-driven. `postgres_schema_design.md` §3 stores `entity_types(type text, parent_type text, ...)`, and D15/D18 in `decisions.md` make ontology extension a registry operation. Per-type Ladybug node tables would turn registry changes and retyping into graph DDL/data movement.
- Ladybug nodes have one table/label only. The CREATE TABLE docs say every node/relationship has one label/table. A single `Entity` table preserves the canonical ID space and keeps entity retyping a property update on rebuild.
- D18's domain/range gate is already enforced before projection by the normalizer through `predicate_signatures`; Ladybug does not need per-type endpoint tables to enforce it.
- `related_to any -> any` alone would imply a wide matrix under per-type tables; extensions would add more pairs.

Alternative: per-core-type node tables (`Person`, `Organization`, etc.) are useful only if type labels are more important than easy transfer. They make every relation load pair-sensitive and make entity retyping harder. Not recommended for the user's priority.

### Recommended relation model: one `RELATES` relationship table

Use one `RELATES(FROM Entity TO Entity, predicate STRING, ...)` table.

Why not per-predicate tables:

- The 14 core predicates in `registries_design.md` §4 are a seed, not a fixed schema. `predicates` includes extension and `other:<freetext>` rows (`postgres_schema_design.md` §3).
- Per-predicate tables make ontology promotion/renaming a Ladybug DDL concern. Rebuild-first makes DDL possible, but not easiest.
- As-of filtering, evidence properties, confidence, contradiction fields, and provenance are identical across predicates.

Why not per `(subject_type, object_type)` pair:

- It mirrors `predicate_signatures`, but signatures are validation rules, not storage identity.
- `related_to any -> any` and subtype inheritance make this explode quickly.
- Ladybug multi-pair relationship tables require a specific `(from='X', to='Y')` option when copying into tables with multiple endpoint pairs. Source binder code verifies that multi-pair rel copy requires those options. That would force many partitioned loads from Postgres. VERIFIED in `/tmp/ladybug-src/src/binder/bind/copy/bind_copy_from.cpp`.

Cleanest mapping:

```cypher
CREATE NODE TABLE Entity(... entity_id UUID PRIMARY KEY, type STRING, ...);
CREATE REL TABLE RELATES(FROM Entity TO Entity, predicate STRING, relation_id UUID, ...);
```

Hot predicates can later be promoted to dedicated relationship tables during rebuild if query performance proves it. That should be a physical optimization, not the baseline.

## 2. Copy-From-Postgres Mechanics

LadybugDB PostgreSQL attach syntax is documented at https://docs.ladybugdb.com/extensions/attach/postgres/:

```cypher
INSTALL postgres;
LOAD postgres;

ATTACH
  'dbname=ugm user=ugm host=<host> password=<password> port=5432' AS pg
  (dbtype postgres, schema='public');
```

The docs verify `LOAD FROM pg.table`, `CALL SQL_QUERY('pg', '<read-only SQL>')`, and `COPY ... FROM SQL_QUERY(...)` for importing attached PostgreSQL data. VERIFIED docs.

### Load nodes

Use SQL_QUERY instead of copying the raw table. The projection SQL should cast Postgres-only types at the boundary:

```cypher
COPY Entity FROM SQL_QUERY('pg', '
  SELECT
    entity_id,
    deployment_id,
    type::text AS type,
    canonical_name,
    normalized_name,
    status::text AS status,
    merged_into,
    type_confidence,
    profile_summary,
    mention_count::bigint AS mention_count,
    graph_degree::bigint AS graph_degree,
    created_at AT TIME ZONE ''UTC'' AS created_at,
    updated_at AT TIME ZONE ''UTC'' AS updated_at
  FROM entities
  WHERE deployment_id = ''<deployment_uuid>''::uuid
    AND status <> ''merged''
');
```

`status <> 'merged'` follows the graph rule that only canonical entities enter P2 (`p2_graph_design.md` §2; `postgres_schema_design.md` §4). If retired entities can still appear in historical relations you intend to traverse, include them; exclude only merged redirect rows.

### Load relations

Ladybug relationship copy expects the first two input values to be the source and destination node primary-key values. Source code binds expected relationship columns as `"from"`, `"to"`, then relationship properties; the `"from"` and `"to"` types are copied from the endpoint node primary-key definitions. VERIFIED in `/tmp/ladybug-src/src/binder/bind/copy/bind_copy_from.cpp`.

For a single-pair `RELATES(FROM Entity TO Entity)` table, no `from='Entity', to='Entity'` option is needed:

```cypher
COPY RELATES FROM SQL_QUERY('pg', '
  SELECT
    subject_entity_id AS "from",
    object_entity_id AS "to",
    relation_id,
    deployment_id,
    predicate::text AS predicate,
    valid_from AT TIME ZONE ''UTC'' AS valid_from,
    valid_until AT TIME ZONE ''UTC'' AS valid_until,
    ingested_at AT TIME ZONE ''UTC'' AS ingested_at,
    invalidated_at AT TIME ZONE ''UTC'' AS invalidated_at,
    evidence_count::bigint AS evidence_count,
    contradict_count::bigint AS contradict_count,
    confidence,
    contradiction_group,
    status::text AS status,
    fact_label,
    fact_label_version,
    normalizer_version,
    created_at AT TIME ZONE ''UTC'' AS created_at,
    updated_at AT TIME ZONE ''UTC'' AS updated_at
  FROM relations
  WHERE deployment_id = ''<deployment_uuid>''::uuid
');
```

This is the key transfer: `relations.subject_entity_id` is the Ladybug relationship source endpoint key, and `relations.object_entity_id` is the destination endpoint key. Ladybug resolves those UUID values against `Entity.entity_id`.

Can `COPY` target a relationship table directly from SQL_QUERY? The docs verify `COPY Person FROM SQL_QUERY(...)` and separately verify `COPY HasReward FROM (MATCH ... RETURN ...)` for relationship tables in https://docs.ladybugdb.com/import/copy-from-subquery/. Source verifies relationship `COPY FROM` binds subquery sources and endpoint columns. I did not find a public test combining `REL TABLE + SQL_QUERY` specifically, so this exact combination is INFERRED but strongly supported. Spike it before production.

Recommended Postgres projection views:

```sql
CREATE VIEW p2_graph_entities_v AS
SELECT
  entity_id,
  deployment_id,
  type::text AS type,
  canonical_name,
  normalized_name,
  status::text AS status,
  merged_into,
  type_confidence,
  profile_summary,
  mention_count::bigint AS mention_count,
  graph_degree::bigint AS graph_degree,
  created_at AT TIME ZONE 'UTC' AS created_at,
  updated_at AT TIME ZONE 'UTC' AS updated_at
FROM entities
WHERE status <> 'merged';

CREATE VIEW p2_graph_relates_v AS
SELECT
  subject_entity_id AS "from",
  object_entity_id AS "to",
  relation_id,
  deployment_id,
  predicate::text AS predicate,
  valid_from AT TIME ZONE 'UTC' AS valid_from,
  valid_until AT TIME ZONE 'UTC' AS valid_until,
  ingested_at AT TIME ZONE 'UTC' AS ingested_at,
  invalidated_at AT TIME ZONE 'UTC' AS invalidated_at,
  evidence_count::bigint AS evidence_count,
  contradict_count::bigint AS contradict_count,
  confidence,
  contradiction_group,
  status::text AS status,
  fact_label,
  fact_label_version,
  normalizer_version,
  created_at AT TIME ZONE 'UTC' AS created_at,
  updated_at AT TIME ZONE 'UTC' AS updated_at
FROM relations;
```

Then load with:

```cypher
COPY Entity FROM SQL_QUERY('pg', 'SELECT * FROM p2_graph_entities_v WHERE deployment_id = ''<deployment_uuid>''::uuid');
COPY RELATES FROM SQL_QUERY('pg', 'SELECT * FROM p2_graph_relates_v WHERE deployment_id = ''<deployment_uuid>''::uuid');
```

## 3. Type Transferability, Column by Column

### `entities`

| Column | PG type | Ladybug transfer | Rating | Transform |
|---|---:|---:|---|---|
| `entity_id` | `uuid` | `UUID PRIMARY KEY` | clean, version-sensitive | Use as UUID. Source/tests verify UUID node PK. Fallback: `entity_id::text` into `STRING PRIMARY KEY`. |
| `deployment_id` | `uuid` | `UUID` property | clean | No cast needed per Postgres attach map. |
| `type` | `text` FK to registry | `STRING` | clean | `type::text AS type` optional. Not a Postgres enum. |
| `canonical_name` | `text` | `STRING` | clean | Direct. |
| `normalized_name` | `text` | `STRING` | clean | Direct. |
| `status` | `entity_status` enum | `STRING` | needs-cast | `status::text AS status`, or drop after filtering. Postgres ENUM is undocumented in attach map. |
| `merged_into` | `uuid` | `UUID` nullable | clean | Keep if useful, but merged rows should not be projected as canonical nodes. |
| `type_confidence` | `real` | `FLOAT` | clean | Direct. |
| `profile_summary` | `text` | `STRING` | clean | Direct. |
| `profile_embedding_ref` | `text` | `STRING` but should not project | drop | D8 says no embeddings in graph. Keep only if operationally useful; graph should hydrate via PG/Lance. |
| `mention_count` | `integer` | `INT64` recommended | clean | Cast `mention_count::bigint` to avoid future overflow; `INT32` also maps directly. |
| `graph_degree` | `integer` | `INT64` recommended | needs judgment | This is derived from latest P2; loading it into the rebuilt P2 snapshot is circular/stale. Prefer drop or recompute after build. |
| `created_at` | `timestamptz` | `TIMESTAMP` | needs-cast | `created_at AT TIME ZONE 'UTC' AS created_at`. |
| `updated_at` | `timestamptz` | `TIMESTAMP` | needs-cast | Same. |

### `relations`

| Column | PG type | Ladybug transfer | Rating | Transform |
|---|---:|---:|---|---|
| `relation_id` | `uuid` | `UUID` rel property | clean | Direct. Relationship tables cannot define user PKs; keep as provenance property. |
| `deployment_id` | `uuid` | `UUID` property | clean | Direct, or drop if one deployment per snapshot. |
| `subject_entity_id` | `uuid` | REL source endpoint | clean | Select as `"from"`; must match an existing `Entity.entity_id`. |
| `predicate` | `text` FK to registry | `STRING` | clean | Direct or `predicate::text`. Not a Postgres enum. |
| `object_entity_id` | `uuid` | REL destination endpoint | clean | Select as `"to"`; must match an existing `Entity.entity_id`. |
| `valid_from` | `timestamptz` | `TIMESTAMP` | needs-cast | `valid_from AT TIME ZONE 'UTC'`. NULL remains NULL. |
| `valid_until` | `timestamptz` | `TIMESTAMP` | needs-cast | Same. |
| `ingested_at` | `timestamptz` | `TIMESTAMP` | needs-cast | Same. |
| `invalidated_at` | `timestamptz` | `TIMESTAMP` | needs-cast | Same. |
| `evidence_count` | `integer` | `INT64` recommended | clean | `evidence_count::bigint`; counts are salience signals. |
| `contradict_count` | `integer` | `INT64` recommended | clean | `contradict_count::bigint`. |
| `confidence` | `real` | `FLOAT` | clean | Direct. |
| `contradiction_group` | `uuid` | `UUID` nullable | clean | Direct. |
| `status` | generated `relation_status` enum | `STRING`, or drop | needs-cast/restructure | Ladybug has no generated columns. Use `status::text`, or omit and use `invalidated_at IS NULL`. |
| `fact_label` | `text` | `STRING` | clean | Direct; useful display label, not full claim text. |
| `fact_label_version` | `text` | `STRING` | clean but optional | Keep only if graph users need label provenance without PG hydration. |
| `fact_label_embedding_ref` | `text` | `STRING` but should not project | drop | D8: relation embeddings live in Lance, not graph. |
| `normalizer_version` | `text` | `STRING` | clean but optional | Projection can keep for audit, but `relation_id` can hydrate PG. |
| `created_at` | `timestamptz` | `TIMESTAMP` | needs-cast | `created_at AT TIME ZONE 'UTC'`. |
| `updated_at` | `timestamptz` | `TIMESTAMP` | needs-cast | Same. |

### Registry columns relevant to projection

`entity_types`, `predicates`, and `predicate_signatures` mostly should not be graph tables in the baseline. Their job is to govern extraction/normalization before projection (`postgres_schema_design.md` §3; D15/D18).

If included for debugging:

- `deployment_id uuid`: clean to `UUID`.
- `type`, `parent_type`, `predicate`, `parent_predicate`, `subject_type`, `object_type`, descriptions, refs: clean to `STRING`.
- `tier ontology_tier`, `status ontology_status`: needs cast to `STRING` with `tier::text`, `status::text`.
- `examples text[]`, `synonyms text[]`: needs verification/restructure. Ladybug supports `STRING[]`, but the PostgreSQL attach type map does not document PostgreSQL arrays. Use `to_json(examples)::json AS examples_json`, `array_to_string(examples, '|')`, or drop at graph boundary.
- `usage_count bigint`: clean to `INT64`.
- booleans: clean to `BOOL`.
- `created_at timestamptz`: needs `AT TIME ZONE 'UTC'`.

### Requested crux types

- `uuid`: Postgres attach maps `uuid -> UUID`. UUID properties are clean. UUID node PK is VERIFIED in current source/tests despite docs omission. Use UUID, but add a version spike.
- `timestamptz`: attach docs mark unsupported. Always cast to naive UTC `TIMESTAMP` with `AT TIME ZONE 'UTC'`.
- Postgres ENUMs: undocumented in attach map. Cast every enum to `text` at projection boundary.
- `text[]` arrays: Ladybug supports list/array types, but PostgreSQL attach does not document PG arrays. Drop, JSON-cast, or delimiter-cast. Do not depend on direct array transfer before a spike.
- generated columns: Ladybug supports defaults but not Postgres-style generated columns in the docs. Select generated values as plain projected columns, cast enum to text, or recompute/drop.
- `numeric`: attach maps to `DECIMAL`; clean if precision/scale are compatible. For graph properties, prefer explicit `::double precision` unless exact decimal arithmetic is needed in graph.
- `jsonb`: attach docs list `json -> JSON`, not `jsonb`. Cast `jsonb_col::json AS json_col` or `jsonb_col::text` before loading. Most JSONB audit fields should be dropped from P2.

## 4. Observations

Observations must not project to LadybugDB P2.

Reason: Ladybug relationship tables are declared as `CREATE REL TABLE r(FROM NodeA TO NodeB, ...)`; endpoints are node tables, not scalar values. The CREATE TABLE docs define relationships as connections between node tables and source/destination nodes. A literal value cannot be a `FROM` or `TO` endpoint. VERIFIED docs.

That validates D18/D43:

- D18: graph holds entity-to-entity facts; time is edge metadata, not a Date node.
- D43: observations are value/statement facts about one entity and "never enter the P2 graph."
- `postgres_schema_design.md` §9.A explicitly says observations project to P1/Lance only.

Nothing from observations belongs in the graph baseline. If graph users need "has observation" navigation later, that would require reifying observations as nodes (`Entity -> ObservationNode`), but that violates the current D43 separation, bloats P2, and makes literal facts look graph-native. Do not do it unless requirements change.

## 5. As-Of / Temporal

Ladybug has `TIMESTAMP` but no native temporal validity semantics (`plan/analysis/ladybug_capabilities.md` §4; docs data types at https://docs.ladybugdb.com/cypher/data-types/). The four relation timestamps support as-of queries as ordinary properties.

Direct one-hop as-of query:

```cypher
MATCH (a:Entity {entity_id: UUID('<entity_uuid>')})-[r:RELATES]-(b:Entity)
WHERE r.ingested_at <= timestamp('2025-03-01 00:00:00')
  AND (r.invalidated_at IS NULL OR r.invalidated_at > timestamp('2025-03-01 00:00:00'))
  AND (r.valid_from IS NULL OR r.valid_from <= timestamp('2025-03-01 00:00:00'))
  AND (r.valid_until IS NULL OR r.valid_until > timestamp('2025-03-01 00:00:00'))
RETURN a, r, b;
```

Projected graph shape for as-of traversal/analytics:

```cypher
CALL PROJECT_GRAPH_CYPHER(
  'asof_2025_03_01',
  'MATCH (a:Entity)-[r:RELATES]->(b:Entity)
   WHERE r.ingested_at <= timestamp("2025-03-01 00:00:00")
     AND (r.invalidated_at IS NULL OR r.invalidated_at > timestamp("2025-03-01 00:00:00"))
     AND (r.valid_from IS NULL OR r.valid_from <= timestamp("2025-03-01 00:00:00"))
     AND (r.valid_until IS NULL OR r.valid_until > timestamp("2025-03-01 00:00:00"))
   RETURN a, r, b'
);
```

For native Cypher path queries without a named projected graph binding, use path filtering:

```cypher
MATCH p = (a:Entity {entity_id: UUID('<entity_uuid>')})-[rs:RELATES*1..3]-(b:Entity)
WHERE all(r IN rels(p) WHERE
  r.ingested_at <= timestamp('2025-03-01 00:00:00')
  AND (r.invalidated_at IS NULL OR r.invalidated_at > timestamp('2025-03-01 00:00:00'))
  AND (r.valid_from IS NULL OR r.valid_from <= timestamp('2025-03-01 00:00:00'))
  AND (r.valid_until IS NULL OR r.valid_until > timestamp('2025-03-01 00:00:00'))
)
RETURN p
LIMIT 100;
```

Caveat: prior local capability notes say relationship predicates via projected graphs enable as-of traversal, but source tests I checked mostly show projected graphs used by graph algorithms and metadata calls. I did not verify a syntax that binds `MATCH` directly to a named projected graph. Treat high-performance as-of multi-hop traversal as a required spike. Correctness is still available with direct path filtering or by materializing an as-of snapshot during rebuild.

## 6. Scorecard and Recommendations

### Scorecard

| Structure | Transfer rating | Notes |
|---|---|---|
| `entities` as one Ladybug node table | clean | UUID PK works in current source/tests; cast timestamps/enums. |
| `relations` as one Ladybug rel table | clean | Shape exactly matches `FROM Entity TO Entity`; endpoints come from subject/object UUIDs. |
| Governed predicates as `predicate STRING` | clean | Best match for runtime registry governance. |
| Predicate signatures | clean as PG-only validation | Do not encode as Ladybug endpoint tables unless optimizing later. |
| Per-type node tables | needs-restructure | More DDL, hard retyping, multi-pair load complexity. |
| Per-predicate rel tables | needs-restructure | More DDL on ontology changes; not easiest. |
| Observations | do not transfer | Correctly non-graph; values cannot be rel endpoints. |
| `uuid` IDs | clean, version-sensitive | Source/tests verify UUID PK; docs omit. |
| `timestamptz` | needs-cast | Cast to UTC naive TIMESTAMP. |
| Postgres enums | needs-cast | Cast to STRING. |
| arrays | needs-restructure/verify | Drop, JSON-cast, or delimiter-cast. |
| generated `status` | needs-cast/drop | Load as plain STRING or derive from `invalidated_at`. |
| `numeric` | clean with explicit choice | DECIMAL if exact; DOUBLE for graph analytics. |
| `jsonb` | needs-cast/drop | Cast to `json`/text; usually drop from P2. |

### Actionable recommendations

1. Add dedicated Postgres projection views `p2_graph_entities_v` and `p2_graph_relates_v`. These views should expose only Ladybug-supported types and column order: `"from"`, `"to"`, then rel properties for `RELATES`.

2. Keep UUIDs as UUID in Ladybug, but add a build-time smoke test:

```cypher
CREATE NODE TABLE uuid_pk_smoke(id UUID PRIMARY KEY);
CREATE (:uuid_pk_smoke {id: UUID('00000000-0000-0000-0000-000000000001')});
MATCH (n:uuid_pk_smoke {id: UUID('00000000-0000-0000-0000-000000000001')}) RETURN count(*);
```

If this fails on a packaged Ladybug version, switch the projection views to `entity_id::text`, `"from"::text`, and `"to"::text`, and use `STRING PRIMARY KEY`.

3. Cast all `timestamptz` in projection SQL:

```sql
valid_from AT TIME ZONE 'UTC' AS valid_from
```

Do not rely on attach handling because docs mark `timestamptz` unsupported.

4. Cast all Postgres enums to text in projection SQL:

```sql
status::text AS status,
tier::text AS tier
```

5. Do not project arrays unless a graph query needs them. If needed, expose `to_json(synonyms)::json` or `array_to_string(synonyms, '|')`; do not assume PG `text[]` maps through attach.

6. Drop embedding refs from P2 by default (`profile_embedding_ref`, `fact_label_embedding_ref`). D8 says embeddings live in Lance, and graph relation properties cannot be vector/FTS indexed anyway.

7. Use `INT64` for counts in Ladybug even when Postgres uses `integer`. It avoids future overflow and keeps analytics functions simple.

8. Keep `relation_id` as the provenance handle. Do not try to make it a Ladybug relationship primary key; Ladybug relationship tables have internally generated edge IDs and no user primary key.

9. Keep graph DDL stable. New entity types and predicates should not require Ladybug DDL. Use registry rows plus `type`/`predicate` properties; promote hot predicates only after measured query pain.

10. Run an attach-load spike at realistic row counts before committing to no-Parquet rebuilds. D7's Parquet path remains the safer high-throughput baseline; direct Postgres attach is attractive but the extension implementation lives outside the vendored core.

## 7. Risks / Unknowns

- UUID-as-node-PK: VERIFIED in current GitHub source/tests, contradicted by omission in public docs. Risk is packaged version drift. Add smoke test.
- `COPY RELATES FROM SQL_QUERY(...)`: INFERRED from docs and source. Docs verify `COPY ... FROM SQL_QUERY` for node tables and `COPY` into rel tables from subqueries; source verifies rel copy endpoint binding. Need one production-version spike.
- PostgreSQL enum handling through attach: UNVERIFIED. Docs type map omits enums. Cast to text.
- PostgreSQL array handling through attach: UNVERIFIED. Docs type map omits arrays, although Ladybug itself supports `STRING[]`. Cast/drop arrays at the view boundary.
- `jsonb`: UNVERIFIED directly. Docs list `json -> JSON`, not `jsonb`. Cast or drop.
- Direct attach throughput at 10^7-10^8 rows: UNVERIFIED. D7 Parquet rebuild remains operationally safer until measured.
- Attach scanner implementation: extension implementation is not in the core source tree I cloned; `plan/analysis/ladybug_capabilities.md` also flags external extension code. Treat attach behavior beyond docs as a spike.
- Projected graph use for named-graph Cypher traversal: partially verified for `PROJECT_GRAPH`/`PROJECT_GRAPH_CYPHER` creation and graph algorithms; exact high-performance path traversal syntax over a named projected graph was not verified. Correctness can fall back to path filtering or materialized as-of snapshots.

## Sources

- `plan/designs/postgres_schema_design.md` §1, §3, §4, §9, §9.A.
- `plan/designs/p2_graph_design.md` §1-§5.
- `plan/analysis/ladybug_capabilities.md` §4-§6.
- `decisions.md` D6, D7, D8, D10, D11, D18, D43.
- `plan/designs/overall_design.md` §1-§3, §5-§6.
- `plan/designs/registries_design.md` §4.
- Ladybug docs: https://docs.ladybugdb.com/cypher/data-definition/create-table/
- Ladybug docs: https://docs.ladybugdb.com/extensions/attach/postgres/
- Ladybug docs: https://docs.ladybugdb.com/cypher/data-types/
- Ladybug docs: https://docs.ladybugdb.com/cypher/data-types/list-and-array/
- Ladybug docs: https://docs.ladybugdb.com/import/copy-from-subquery/
- Ladybug docs: https://docs.ladybugdb.com/cypher/transaction/
- Ladybug source/tests cloned from https://github.com/LadybugDB/ladybug on 2026-06-25 into `/tmp/ladybug-src`.
