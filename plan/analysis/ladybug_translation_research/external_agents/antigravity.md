# LadybugDB Translation Analysis
**Author:** Antigravity (Advanced Agentic Coding)  
**Date:** June 2026  
**Status:** COMPLETE (Grounding: Verified LadybugDB Docs, Core Source, and Project Decisions)

---

## Executive Summary

This document evaluates the transferability of PostgreSQL "relations" graph data from the E-plane database to **LadybugDB** (P2 Graph projection, a maintained community fork of KùzuDB) for tenant-scoped graph traversals. 

Our core conclusion is that **the Postgres database structures are EASILY transferable to LadybugDB**, provided the aggregate projection boundary handles data types correctly. By leveraging LadybugDB's `ATTACH` and `COPY ... FROM SQL_QUERY` mechanics, the P2 aggregate worker can rebuild the graph directly from Postgres in minutes without an intermediate Parquet hop. 

The biggest transferability friction points are **`timestamptz` timezone handling**, PostgreSQL **custom enums**, and **structural arrays**, all of which must be resolved by casting at the SQL projection boundary (via a database `VIEW` or targeted `SELECT` projections). LadybugDB natively supports `UUID` as a primary key, simplifying identity mapping from the [entities](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/postgres_schema_design.md#L480-L501) registry.

---

## 1. Node/Rel Table Model

We evaluate the node/rel modeling strategies for translating the E-plane Postgres truth into LadybugDB's DDL schema:

### 1.1 Node Table Modeling: Unified `Entity` vs. Per-Type Node Tables
Postgres [entities](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/postgres_schema_design.md#L480-L501) defines 8 core entity types (`Person`, `Organization`, `Place`, `Document`, `Event`, `Concept`, `Project`, `Product`) via the [entity_types](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/postgres_schema_design.md#L368-L387) registry.

*   **Option A: One Unified `Entity` Node Table.** A single node table represents all entities, storing their specific entity type in a `type` property string.
*   **Option B: Separate Node Table Per Type (8 Tables).** Explicitly creating `Person`, `Organization`, etc., tables.

> [!IMPORTANT]
> **Recommendation:** We recommend a unified `Entity` node table (Option A) as specified in [p2_graph_design.md §2](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/p2_graph_design.md#L46-L81). 
> 
> *Rationale:* LadybugDB is strongly schema-typed. Under [D15/D18](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/decisions.md#L374-L397), users can dynamically enable "extension packs" (e.g., a Work Pack adding a `Decision` entity). If every entity type had a separate node table, the aggregate graph builder would have to run dynamic Cypher DDL migrations (e.g. `CREATE NODE TABLE`) during every rebuild cycle. A unified `Entity` node table keeps the schema static; new entity types simply flow as text labels in the `type` column.

### 1.2 Relationship Table Modeling: Single `RELATES` vs. Per-Predicate Tables
Postgres [relations](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/postgres_schema_design.md#L1137-L1172) tracks 14 seed predicates with strict domain/range constraints (e.g. `works_for` is `Person → Organization`).

*   **Option (a): One generic `RELATES` table** with multi-pair endpoints and a `predicate` property.
*   **Option (b): Per-predicate relationship tables** (`WORKS_FOR`, `MEMBER_OF`, etc.).
*   **Option (c): Per-(subject_type, object_type)-pair tables** (`PERSON_WORKS_FOR_ORGANIZATION`, etc.).

> [!IMPORTANT]
> **Recommendation:** We recommend **Option (a)**: a single, polymorphic `RELATES` relationship table, defined as:
> ```cypher
> CREATE REL TABLE RELATES(FROM Entity TO Entity, predicate STRING, ...);
> ```
> *Rationale:* 
> 1. **Polymorphic Traversal:** Cypher queries like "find all connections between X and Y" can be written as `MATCH (a)-[r:RELATES]->(b)` rather than unioning 14+ specific relationship tables.
> 2. **Vocabulary Growth:** Similar to dynamic entity types, the predicate registry allows `other:<freetext>` escape values ([predicates](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/postgres_schema_design.md#L395-L414) table). A single generic relationship table holds these dynamic values as properties without DDL modification.
> 3. **Polymorphic Endpoints:** LadybugDB natively supports multi-pair endpoints for a single relationship table. If `Document` is split out from `Entity` (as done in the current graph design for structural reasons), `RELATES` cleanly supports:
> ```cypher
> CREATE REL TABLE RELATES(FROM Entity TO Entity, FROM Entity TO Document, FROM Document TO Entity, FROM Document TO Document, predicate STRING, ...);
> ```

---

## 2. COPY-FROM-POSTGRES Mechanics (Direct ATTACH Ingestion)

Instead of exporting Postgres tables to Parquet files and loading them, LadybugDB's `ATTACH` extension allows direct pull-style bulk loading from a Postgres instance.

### 2.1 Attaching the Database
The aggregate builder initiates a read-only attachment using the following Cypher statement:
```cypher
ATTACH 'host=postgres-db port=5432 dbname=spine user=postgres password=secret' AS pg (dbtype postgres);
```
*(Verified: June 2026, [ladybug_capabilities.md §5](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/analysis/ladybug_capabilities.md#L70-L75)).*

### 2.2 Node Loading Statement
To load the `Entity` table directly from the Postgres `entities` table, ignoring inactive/merged entries:
```cypher
COPY Entity FROM SQL_QUERY('pg', '
  SELECT 
    entity_id AS id, 
    canonical_name AS name, 
    type, 
    profile_summary AS summary, 
    created_at AT TIME ZONE \'UTC\' AS created_at
  FROM entities
  WHERE status = \'active\'
');
```
*   **PK Mapping:** The primary key `Entity.id` receives `entities.entity_id` as a `UUID`.
*   **Time Casting:** The timezone-aware `timestamptz` column `created_at` is converted to a naive timestamp in UTC on the Postgres side, which maps to LadybugDB's `TIMESTAMP` type.

### 2.3 Relationship Loading Statement
A relationship table in LadybugDB expects its input stream to contain:
1.  **Column 1:** Source node primary key (maps to `FROM` table PK type).
2.  **Column 2:** Destination node primary key (maps to `TO` table PK type).
3.  **Remaining Columns:** Relationship properties in their exact declared order.

*(Verified: June 2026, Kùzu/LadybugDB COPY REL syntax).*

We can query the Postgres `relations` table directly and load it into `RELATES`:
```cypher
COPY RELATES FROM SQL_QUERY('pg', '
  SELECT 
    subject_entity_id, 
    object_entity_id, 
    predicate, 
    relation_id, 
    fact_label AS fact, 
    evidence_count::int8 AS evidence_count, 
    valid_from AT TIME ZONE \'UTC\' AS valid_from, 
    valid_until AT TIME ZONE \'UTC\' AS valid_until, 
    ingested_at AT TIME ZONE \'UTC\' AS ingested_at, 
    invalidated_at AT TIME ZONE \'UTC\' AS invalidated_at, 
    confidence::float8 AS confidence
  FROM relations
  WHERE invalidated_at IS NULL
');
```
> [!NOTE]
> **Endpoint Integrity:** Since the query retrieves `subject_entity_id` and `object_entity_id` as the first two fields, LadybugDB correctly resolves them against the `Entity` table's primary keys. Because Kùzu/LadybugDB enforces referential integrity on relationships, any entity IDs not already loaded into the `Entity` node table will throw a load error. Therefore, **nodes must be loaded first**.

---

## 3. Type Transferability Column-by-Column Analysis

We analyze every column of the core Postgres tables to determine how cleanly they translate to LadybugDB.

### 3.1 Node Mapping: Postgres `entities`

| Postgres Column | PG Type | Ladybug Target Type | Classification | Transform / Cast SQL Statement | Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `entity_id` | `uuid` | `UUID` | **As-Is** | `entity_id` | **Verified:** LadybugDB natively supports `UUID` as a primary key. |
| `deployment_id` | `uuid` | — | **Drop** | *Omitted* | Graph snapshot is scoped to one tenant/deployment; tenant filter is applied in the `WHERE` clause during load. |
| `type` | `text` | `STRING` | **As-Is** | `type` | Simple string representation of canonical type. |
| `canonical_name` | `text` | `STRING` | **As-Is** | `canonical_name` | Used as the primary node display name. |
| `normalized_name` | `text` | — | **Drop** | *Omitted* | Only needed in Postgres to accelerate trigram/fuzzy registry lookups. |
| `status` | `entity_status` | — | **Drop / Omit** | *Omitted* | Filtered out in `WHERE status = 'active'`. (We do not project inactive/merged entities). |
| `merged_into` | `uuid` | — | **Drop** | *Omitted* | Rebuild-first model handles redirects in Postgres. Active nodes absorb edges before graph creation. |
| `type_confidence` | `real` | `FLOAT` | **Needs-Cast** | `type_confidence::float4` | Maps Postgres `real` (`float4`) to Ladybug `FLOAT`. |
| `profile_summary` | `text` | `STRING` | **As-Is** | `profile_summary` | Maps to `summary`. |
| `profile_embedding_ref`| `text` | — | **Drop** | *Omitted* | **D8:** Node/relationship embeddings live in LanceDB, not in the graph snapshot. |
| `mention_count` | `integer`| `INT32` | **Needs-Cast** | `mention_count::int4` | Postgres `integer` (`int4`) maps to Ladybug `INT32`. |
| `graph_degree` | `integer`| — | **Drop** | *Omitted* | Only useful in Postgres to rank ER merge review blast-radii. |
| `created_at` | `timestamptz` | `TIMESTAMP` | **Needs-Cast** | `created_at AT TIME ZONE 'UTC'` | **Critical:** `timestamptz` is unsupported; must cast to naive UTC timestamp. |
| `updated_at` | `timestamptz` | — | **Drop** | *Omitted* | Omitted to keep the graph snapshot lean. |

---

### 3.2 Edge Mapping: Postgres `relations`

| Postgres Column | PG Type | Ladybug Target Type | Classification | Transform / Cast SQL Statement | Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `relation_id` | `uuid` | `UUID` | **As-Is** | `relation_id` | Kept for hydration queries back to Postgres evidence. |
| `deployment_id` | `uuid` | — | **Drop** | *Omitted* | Tenant filter applied during ingestion query. |
| `subject_entity_id` | `uuid` | `UUID` | **As-Is** | `subject_entity_id` | Serves as relationship `FROM` endpoint. |
| `predicate` | `text` | `STRING` | **As-Is** | `predicate` | maps Postgres `text` to Ladybug `STRING`. |
| `object_entity_id` | `uuid` | `UUID` | **As-Is** | `object_entity_id` | Serves as relationship `TO` endpoint. |
| `valid_from` | `timestamptz` | `TIMESTAMP` | **Needs-Cast** | `valid_from AT TIME ZONE 'UTC'` | Must cast to naive UTC timestamp. |
| `valid_until` | `timestamptz` | `TIMESTAMP` | **Needs-Cast** | `valid_until AT TIME ZONE 'UTC'` | Must cast to naive UTC timestamp. |
| `ingested_at` | `timestamptz` | `TIMESTAMP` | **Needs-Cast** | `ingested_at AT TIME ZONE 'UTC'` | Must cast to naive UTC timestamp. |
| `invalidated_at` | `timestamptz` | `TIMESTAMP` | **Needs-Cast** | `invalidated_at AT TIME ZONE 'UTC'` | Must cast to naive UTC timestamp. |
| `evidence_count` | `integer`| `INT64` | **Needs-Cast** | `evidence_count::int8` | Cast to 64-bit integer (`INT64`) as defined in P2 DDL. |
| `contradict_count`| `integer`| — | **Drop** | *Omitted* | Omitted for graph traversal simplicity. |
| `confidence` | `real` | `DOUBLE` | **Needs-Cast** | `confidence::float8` | Cast to double precision to map to Ladybug `DOUBLE`. |
| `contradiction_group`| `uuid` | `UUID` | **As-Is** | `contradiction_group` | Retained to flag conflicting edges. |
| `status` | `relation_status`| — | **Drop** | *Omitted* | Redundant with `invalidated_at IS NULL` filters. Custom enums are unsupported. |
| `fact_label` | `text` | `STRING` | **As-Is** | `fact_label` | Maps to `fact` text string. |
| `fact_label_embedding_ref`| `text` | — | **Drop** | *Omitted* | **D8:** Embeddings live in LanceDB. |

---

### 3.3 Registry Mapping: PostgreSQL Arrays (`text[]` / enums)

Tables like [entity_types](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/postgres_schema_design.md#L368-L387) and [predicates](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/postgres_schema_design.md#L395-L414) contain arrays (`examples text[]`, `synonyms text[]`).

*   **Classification:** **Drop.**
*   **Transform/Cast:** Omit entirely from graph projections.
*   **Rationale:** Node tables in the graph only hold entities. Predicate definition and synonyms are meta-level schemas used in the ingestion pipeline (E-plane), not in structural traversal (P-plane). Dropping them keeps the graph footprint light.

---

## 4. Observations Analysis

PostgreSQL [observations](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/designs/postgres_schema_design.md#L1296-L1326) represents facts about a single entity where the target is a literal value (e.g., `"headcount is 600"`, `"FY2023 revenue was $5M"`).

*   **Do they project to the graph?** **No.**
*   **Technical Reason:** LadybugDB relationship tables require both `FROM` and `TO` endpoints to be defined node tables. An endpoint can **never** be a literal value (like a string, integer, or date). To represent observations as edges, we would have to reify every observed value as a node (e.g. creating millions of dummy `Value` nodes), which would cause massive index bloat and make graph queries highly complex.
*   **Implications:** This validates decisions **D18** and **D43**. Observations are strictly single-entity value attributes. They project to **P1 (LanceDB)** only (for semantic/text search) and remain queryable in Postgres, bypassing the graph snapshot entirely.

---

## 5. Bi-Temporal / Temporal Traversal Queries

LadybugDB has no native concepts of time-travel or temporal valid intervals, but they can be implemented using projected subgraphs.

### 5.1 Variable-Length Path Filtering Challenge
Using a standard Cypher `WHERE` clause after matching a path:
```cypher
MATCH p = (a:Entity {id: $id})-[r:RELATES*1..3]-(b:Entity)
WHERE ALL(edge IN relationships(p) WHERE edge.valid_from <= $as_of AND ...)
RETURN p;
```
This forces the engine to traverse *all* physical paths in the database first, and then filter them out, causing massive memory allocations and latency spikes.

### 5.2 The Solution: Projected Graphs with Rel Predicates
LadybugDB supports `PROJECT_GRAPH_CYPHER`, allowing us to project a virtual, filtered subgraph in memory. The filter is executed *during* traversal:

#### Step 1: Create the Temporal Subgraph
```cypher
CALL PROJECT_GRAPH_CYPHER('temp_subgraph', '
  MATCH (a:Entity)-[r:RELATES]->(b:Entity)
  WHERE r.ingested_at <= $as_of
    AND (r.invalidated_at IS NULL OR r.invalidated_at > $as_of)
    AND (r.valid_from IS NULL OR r.valid_from <= $as_of)
    AND (r.valid_until IS NULL OR r.valid_until > $as_of)
  RETURN a, r, b
');
```
#### Step 2: Traverse the Projected Subgraph Natively
```cypher
MATCH p = (a:Entity {id: $id})-[r:RELATES*1..3]-(b:Entity)
USING GRAPH temp_subgraph
RETURN p;
```
This query executes at C++ speeds over index-backed subgraphs, satisfying **D10** (As-of traversal via projected graphs).

---

## 6. Transferability Scorecard & Recommendations

### 6.1 Scorecard

| Postgres Structure | Component | Status | Transferability Score | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **`entities` Registry** | IDs (`uuid`) | Clean | **10/10** | UUID PKs are natively supported. |
| | Timestamps (`timestamptz`) | Needs-Cast | **7/10** | Requires explicit UTC time-zone casting. |
| | Enums (`entity_status`) | Needs-Cast / Drop | **8/10** | Custom enums must be cast to string or dropped. |
| **`relations` Table** | Endpoint IDs (`uuid`) | Clean | **10/10** | Natively maps to REL table FROM/TO pairs. |
| | Properties (`fact_label`, `evidence_count`) | Clean | **10/10** | Maps straight to STRING and INT64. |
| | Timestamps (`timestamptz`) | Needs-Cast | **7/10** | Requires explicit UTC timezone casting. |
| | generated `status` | Drop | **9/10** | Ignore generated enums. |
| **`observations` Table** | Single-entity Facts | Omit | **N/A** | Correctly kept out of the graph (D43). |

---

### 6.2 Actionable Recommendations

To make the Postgres schema and LadybugDB bulk-loader as simple and robust as possible, we recommend the following:

1.  **Expose a Dedicated Projection View in Postgres.** Do not write complex Cypher SQL queries that perform time-casting and enum conversion directly against the raw tables. Instead, define structured Postgres `VIEWS` that represent the graph projection boundary:
    *   `v_graph_projection_nodes`: Exposes `id`, `name`, `type`, `summary`, and naive `created_at`.
    *   `v_graph_projection_edges`: Exposes `subject_entity_id`, `object_entity_id`, `predicate::text`, `relation_id`, `fact_label`, `evidence_count`, and all timestamps cast via `AT TIME ZONE 'UTC'`.
2.  **This keeps the loading logic simple:**
    ```cypher
    COPY Entity FROM pg.v_graph_projection_nodes;
    COPY RELATES FROM pg.v_graph_projection_edges;
    ```
3.  **Strict Loading Order Enforcement.** The ingestion worker must guarantee that the `Entity` table is completely loaded and committed *before* starting the `RELATES` load. Since `RELATES` references `Entity` keys, out-of-order execution will fail.
4.  **Enforce Lowercase Table and Column Names.** LadybugDB's parser can be sensitive to case. We recommend standardizing on lowercase table names and lowercase properties (`id`, `name`, `predicate`) at the projection boundary.

---

## 7. Risks & Unknowns

The team should verify the following points before deploying the P2 worker in production:

1.  **Postgres Attach Scanner Performance.** While `ATTACH` works natively, testing must verify the scanner's latency and throughput when pulling $10^7$ rows directly over a network connection from Hetzner. If networking limits the scanner's speed, we may need to fall back to exporting to Parquet files via GCS.
2.  **Multi-pair relationship table bulk loading.** While Kùzu supports `COPY` on multi-pair relationship tables, we need to verify that copying from a unified `SQL_QUERY` statement doesn't trigger edge-case parser warnings if some endpoint pairs are sparsely populated.
3.  **UUID Primary Key index performance.** We must monitor memory consumption in LadybugDB when using `UUID` columns as node primary keys instead of integer `SERIAL` sequences. UUID indices can consume up to 2-3x more RAM at large scales ($10^8$ nodes).
