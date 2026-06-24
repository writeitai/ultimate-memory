# Layered Memory System (`ugm`): Fact Layer Architecture Analysis
**Prepared by:** Senior Data / Knowledge-Graph Architect  
**Status:** DESIGN Phase (Comprehensive Written Analysis)  
**Date:** June 2026

This document presents a rigorous, opinionated evaluation of the core data modeling and projection pipeline decisions for the `ugm` layered memory system. It addresses three critical architectural questions:
1. **The Verdict-Layer Shape** for non-relational temporal supersession.
2. **Postgres ↔ LadybugDB Projection Fit** under the ATTACH-direct capability.
3. **The Overall Stack Architecture** (Truth vs. Projection, Postgres vs. Graph).

---

## Executive Summary & Amending Prior Decisions

To support **temporal supersession of non-relational facts** (e.g., wallet balances, revenue, headcount that change over time and are asserted open-endedly with only `valid_from`) as a first-class requirement, we must amend and align several prior design decisions:

*   **Amend [D42 (Non-relational conflicts)](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/decisions.md#L812-L869):** The status quo of "surface-only, no literal supersession" is formally **rejected**. We will replace the write-time grouping projection `claim_attribute_facts` with full bi-temporal adjudication and temporal supersession for literal-object facts.
*   **Amend [D3 (Supersession at the relation level)](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/decisions.md#L49-L67):** Supersession now operates at the **fact level** (encompassing both entity-to-entity *relations* and entity-to-literal *attributes*). Claims remain strictly immutable records of source assertions.
*   **Maintain [D6 (One validity home)](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/decisions.md#L105-L131) and [D18 (No literal nodes)](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/decisions.md#L382-L405):** Validity as current belief has exactly one home: Postgres. The graph remains a derived, read-optimized projection holding only entity-to-entity relations. No literal nodes (like Date or Value nodes) will enter the graph.

---

## Q1: The Verdict-Layer Shape (Unified `facts` vs. Separate Tables)

To provide first-class bi-temporal supersession for non-relational facts, we compare two primary architectural options:
*   **(U) Unified `facts` Verdict Layer:** A single physical table in Postgres holds all adjudicated beliefs, using a polymorphic object definition (referencing an `entities` row OR storing a normalized literal value). A single supersession engine processes all writes. Graph-compatible entity-to-entity relations are exposed as a database view `relations` which the graph projects.
*   **(S) Separate Tables:** The existing `relations` table remains restricted to entity-to-entity relations. A separate, parallel table `proposition_facts` is introduced to handle entity-to-attribute-literal facts, replicating the entire bi-temporal schema, indexes, evidence-collapse join table, and supersession logic.

### 1. Architectural Comparison Matrix

| Dimension | Option U: Unified `facts` Table (Recommended) | Option S: Separate Tables (Rejected) | Rationale & Trade-offs |
| :--- | :--- | :--- | :--- |
| **D6: One Belief Home** | **Excellent.** All adjudicated beliefs (the "verdict layer") live in a single table, ensuring a single structural authority. | **Compromised.** Adjudicated beliefs are split across two tables, leading to fragmented queries and dual storage. | Option U provides a cleaner conceptual model: the Postgres "truth" is a single unified table of facts. |
| **Code & Engine Complexity** | **Low.** The bi-temporal engine (interval slicing, out-of-order claims, transaction-time invalidation, and evidence mapping) is implemented once. | **High.** The entire supersession and slicing logic must be duplicated or written abstractly to interact with different schemas. | Bi-temporal slicing and out-of-order adjustments are highly complex. Writing and maintaining two copies of this code is a severe liability. |
| **Promote-from-Literal Seam** | **Seamless.** Promoting an attribute (e.g., string `"Acme Corp"`) to a resolved entity is a simple bi-temporal transition (update/slice) within the same table. | **Complex.** Requires deleting/invalidating from `proposition_facts`, inserting into `relations`, and manually linking historical evidence across tables. | Entities often start as simple text strings in early claims before being resolved. Option U handles this transition natively. |
| **Polymorphic-Object Cost** | **Moderate.** Requires nullable columns (`object_entity_id`, `object_literal_value`) and conditional check constraints in SQL. | **None.** Each table has a clean, single-typed object field (`object_entity_id` is non-nullable; values are typed). | Postgres handles nullable fields and composite check constraints with negligible overhead. The cost is purely cognitive, which is mitigated by clear DDL. |
| **Evidence Collapse** | **Unified.** A single `fact_evidence` join table collapses corpus redundancy for both relations and attributes. | **Duplicated.** Requires separate `relation_evidence` and `proposition_fact_evidence` tables, increasing schema bloat. | At $10^8$ scale, maintaining separate partitioned join tables increases indexing overhead and migration footprint. |
| **Scale & Querying** | **Excellent.** Querying "all facts about entity X" (regardless of whether object is literal or entity) is a single fast index scan. | **Poor.** Requires joining and `UNION`-ing two separate large tables to retrieve an entity's complete profile. | Under Option S, profile rendering and FTS/vector indexing pipelines must perform complex multi-table queries. |

### 2. Concrete Schema for Recommendation (Option U)

We propose the following physical Postgres schema. It leverages standard declarative constraints to enforce polymorphic referential integrity and bi-temporal isolation.

```sql
-- Enums representing the status of facts and the domains of attribute values
CREATE TYPE relation_status AS ENUM ('active', 'invalidated');
CREATE TYPE evidence_stance AS ENUM ('supports', 'contradicts');
CREATE TYPE adjudication_outcome AS ENUM ('add', 'noop', 'supersede', 'contradict', 'same_as_merge_proposal');
CREATE TYPE adjudication_method AS ENUM ('novelty_gate', 'exact', 'fuzzy', 'embedding', 'small_model', 'frontier_llm');
CREATE TYPE decision_actor AS ENUM ('auto', 'human');

-- ─────────────────────────────────────────────────────────────────────────
-- facts: The unified verdict layer (Option U)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE facts (
  fact_id                 uuid PRIMARY KEY,            -- The fact's identity; flows to downstream projections
  deployment_id           uuid NOT NULL REFERENCES deployments(deployment_id),
  subject_entity_id       uuid NOT NULL,               -- The subject entity
  relationship_predicate  text,                        -- Non-null if object_kind = 'entity'
  relationship_attribute  text,                        -- Non-null if object_kind = 'literal'
  relationship_key        text GENERATED ALWAYS AS (COALESCE(relationship_predicate, relationship_attribute)) STORED,
  object_kind             text NOT NULL CHECK (object_kind IN ('entity', 'literal')),
  object_entity_id        uuid,                        -- References entities table if object_kind = 'entity'
  object_literal_value    jsonb,                       -- Typed normalized JSON structure if object_kind = 'literal'
  qualifiers_hash         text NOT NULL DEFAULT '',    -- Hash of identity-bearing qualifiers (e.g. accounting_basis)
  
  -- Bi-temporality columns
  valid_from              timestamptz,                 -- Valid-time: when the fact held in the world (NULL = unbounded)
  valid_until             timestamptz,                 -- Valid-time: closed by supersession when fact stops holding
  ingested_at             timestamptz NOT NULL DEFAULT now(), -- Transaction-time: when the system learned it
  invalidated_at          timestamptz,                 -- Transaction-time: when the system learned it was superseded
  
  -- Metrics and confidence caching
  evidence_count          integer NOT NULL DEFAULT 0,  -- Supporting evidence rows (confidence/salience signal)
  contradict_count        integer NOT NULL DEFAULT 0,  -- Contradicting evidence rows
  confidence              real,                        -- Aggregate confidence over evidence
  contradiction_group     uuid,                        -- Shared UUID when facts conflict and cannot be adjudicated
  status                  relation_status GENERATED ALWAYS AS (
                            CASE WHEN invalidated_at IS NOT NULL THEN 'invalidated'::relation_status 
                                 ELSE 'active'::relation_status END
                          ) STORED,
                          
  -- Hydration and formatting properties
  fact_label              text,                        -- Text description embedded in LanceDB
  fact_label_version      text,                        -- Pipeline component version
  fact_label_embedding_ref text,                       -- Opaque reference to the vector index in LanceDB
  normalizer_version      text NOT NULL,               -- Pipeline version used to normalize literal values
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),

  -- Constraints
  UNIQUE (deployment_id, fact_id),
  FOREIGN KEY (deployment_id, subject_entity_id) REFERENCES entities (deployment_id, entity_id),
  FOREIGN KEY (deployment_id, object_entity_id) REFERENCES entities (deployment_id, entity_id),
  FOREIGN KEY (deployment_id, relationship_predicate) REFERENCES predicates (deployment_id, predicate) ON UPDATE CASCADE,
  FOREIGN KEY (deployment_id, relationship_attribute) REFERENCES attributes (deployment_id, attribute_key) ON UPDATE CASCADE,

  -- Polymorphic exclusive-arc constraint:
  -- Enforces that predicate/entity-object go together, and attribute/literal-object go together.
  CONSTRAINT chk_polymorphic_object CHECK (
    (object_kind = 'entity'  AND object_entity_id IS NOT NULL AND object_literal_value IS NULL 
                             AND relationship_predicate IS NOT NULL AND relationship_attribute IS NULL) OR
    (object_kind = 'literal' AND object_entity_id IS NULL AND object_literal_value IS NOT NULL 
                             AND relationship_predicate IS NULL AND relationship_attribute IS NOT NULL)
  ),
  CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from),
  CHECK (invalidated_at IS NULL OR invalidated_at >= ingested_at)
);

-- Indexing for blocking and retrieval performance
CREATE INDEX ix_facts_subject_pred ON facts (deployment_id, subject_entity_id, relationship_predicate) WHERE object_kind = 'entity';
CREATE INDEX ix_facts_subject_attr ON facts (deployment_id, subject_entity_id, relationship_attribute) WHERE object_kind = 'literal';
CREATE INDEX ix_facts_object_reverse ON facts (deployment_id, object_entity_id) WHERE object_kind = 'entity';
CREATE INDEX ix_facts_contradiction ON facts (contradiction_group) WHERE contradiction_group IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────
-- GiST Bi-Temporal Exclusion Constraints
-- ─────────────────────────────────────────────────────────────────────────

-- Constraint 1: For Entity-object relations. Excludes overlapping active intervals for the SAME (s, p, o).
ALTER TABLE facts ADD CONSTRAINT exclude_overlapping_relations
EXCLUDE USING gist (
  deployment_id WITH =,
  subject_entity_id WITH =,
  relationship_predicate WITH =,
  object_entity_id WITH =,
  tstzrange(valid_from, valid_until) WITH &&
) WHERE (invalidated_at IS NULL AND contradiction_group IS NULL AND object_kind = 'entity');

-- Constraint 2: For Literal-object attributes. Excludes overlapping active intervals for the SAME attribute slot (s, a, qualifiers).
-- This ensures only ONE value is active for a given attribute/qualifier set over any interval.
ALTER TABLE facts ADD CONSTRAINT exclude_overlapping_attributes
EXCLUDE USING gist (
  deployment_id WITH =,
  subject_entity_id WITH =,
  relationship_attribute WITH =,
  qualifiers_hash WITH =,
  tstzrange(valid_from, valid_until) WITH &&
) WHERE (invalidated_at IS NULL AND contradiction_group IS NULL AND object_kind = 'literal');

-- ─────────────────────────────────────────────────────────────────────────
-- fact_evidence: Join table to claims (partitioned by HASH)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE fact_evidence (
  deployment_id       uuid NOT NULL,
  fact_id             uuid NOT NULL,               -- HASH partition key
  claim_id            uuid NOT NULL,               -- LOGICAL FK → claims (range-partitioned by month)
  stance              evidence_stance NOT NULL,
  normalizer_version  text NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (fact_id, claim_id)
) PARTITION BY HASH (fact_id);

CREATE INDEX ix_fact_evidence_claim ON fact_evidence (claim_id);

-- ─────────────────────────────────────────────────────────────────────────
-- fact_adjudications: Decision ledger tracking updates to the verdict layer
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE fact_adjudications (
  adjudication_id     uuid PRIMARY KEY,
  deployment_id       uuid NOT NULL REFERENCES deployments(deployment_id),
  fact_id             uuid NOT NULL,
  related_fact_id     uuid,
  outcome             adjudication_outcome NOT NULL,
  method              adjudication_method NOT NULL,
  confidence          real,
  triggering_claim_id uuid,                        -- LOGICAL FK → claims
  features            jsonb,
  adjudicator_version text NOT NULL,
  decided_by          decision_actor NOT NULL DEFAULT 'auto',
  decided_at          timestamptz NOT NULL DEFAULT now(),
  superseded_by       uuid REFERENCES fact_adjudications(adjudication_id),
  FOREIGN KEY (deployment_id, fact_id) REFERENCES facts (deployment_id, fact_id),
  FOREIGN KEY (deployment_id, related_fact_id) REFERENCES facts (deployment_id, fact_id)
);

CREATE INDEX ix_fact_adjud_fact ON fact_adjudications (fact_id);
```

### 3. Exposing the Graph-Ready view `relations`
To maintain absolute backward compatibility with the downstream LadybugDB projection pipeline, we project the entity-entity subset of the unified table as a read-only view.

```sql
CREATE VIEW relations AS
SELECT
  fact_id AS relation_id,
  deployment_id,
  subject_entity_id,
  relationship_predicate AS predicate,
  object_entity_id,
  valid_from,
  valid_until,
  ingested_at,
  invalidated_at,
  evidence_count,
  contradict_count,
  confidence,
  contradiction_group,
  status,
  fact_label,
  fact_label_version,
  fact_label_embedding_ref,
  normalizer_version,
  created_at,
  updated_at
FROM facts
WHERE object_kind = 'entity';
```

---

### 4. End-to-End Walkthrough: Wallet-Balance Temporal Supersession

To illustrate how Option U resolves temporal supersession, we walk through the ingestion of three open-ended, `valid_from`-only claims asserting a wallet balance over time.

*   **Subject:** `wallet_uuid_123` (Entity ID: `E_wallet`)
*   **Attribute Key:** `wallet_balance`
*   **Claims Received (in chronological ingestion sequence):**
    *   **Claim 1 (C1):** Ingested at $T_{ingest\_1}$. Asserts balance of `100` starting at `2026-01-01` (`valid_from`).
    *   **Claim 2 (C2):** Ingested at $T_{ingest\_2}$. Asserts balance of `150` starting at `2026-02-01` (`valid_from`).
    *   **Claim 3 (C3):** Ingested at $T_{ingest\_3}$. Asserts balance of `120` starting at `2026-03-01` (`valid_from`).

#### Step 1: Ingesting Claim 1 (C1)
1.  **Block/Match:** The adjudicator queries `facts` for active rows with key `(subject=E_wallet, relationship_attribute='wallet_balance')`. It finds 0 rows.
2.  **Adjudication:** The new claim is inserted as a new fact with an open-ended validity range `[2026-01-01, NULL)`.
3.  **Database State:**
    *   **Row inserted into `facts` (`F1`):**
        *   `fact_id`: `F1`
        *   `object_kind`: `'literal'`
        *   `object_literal_value`: `{"amount": 100, "currency": "USD"}`
        *   `valid_from`: `'2026-01-01T00:00:00Z'`
        *   `valid_until`: `NULL`
        *   `ingested_at`: $T_{ingest\_1}$
        *   `invalidated_at`: `NULL`
    *   **Row inserted into `fact_evidence`:** `(F1, C1, 'supports')`.
    *   **Row inserted into `fact_adjudications`:** `(outcome='add', method='exact')`.

#### Step 2: Ingesting Claim 2 (C2)
1.  **Block/Match:** The adjudicator queries `facts` and blocks on `(subject=E_wallet, relationship_attribute='wallet_balance')`. It returns `F1` (active, valid `[2026-01-01, NULL)`).
2.  **Comparison:** The normalizer determines that the value (`150`) differs from the active fact (`100`). The new claim's `valid_from` (`2026-02-01`) is greater than `F1`'s `valid_from` (`2026-01-01`).
3.  **Adjudication:** This triggers a temporal supersession:
    *   The active fact `F1`'s valid-time window is capped at the start time of the incoming claim. We update `F1` setting `valid_until = '2026-02-01T00:00:00Z'`. Note that `invalidated_at` remains `NULL` because the fact is still historically believed to be true *for that specific window*.
    *   A new fact `F2` is inserted for the new balance, valid `[2026-02-01, NULL)`.
4.  **Database State:**
    *   **`F1` Row Updated in `facts`:** `valid_until = '2026-02-01T00:00:00Z'`.
    *   **Row inserted into `facts` (`F2`):**
        *   `fact_id`: `F2`
        *   `object_kind`: `'literal'`
        *   `object_literal_value`: `{"amount": 150, "currency": "USD"}`
        *   `valid_from`: `'2026-02-01T00:00:00Z'`
        *   `valid_until`: `NULL`
        *   `ingested_at`: $T_{ingest\_2}$
        *   `invalidated_at`: `NULL`
    *   **Row inserted into `fact_evidence`:** `(F2, C2, 'supports')`.
    *   **Row inserted into `fact_adjudications`:** `(outcome='supersede', fact_id=F2, related_fact_id=F1)`.

#### Step 3: Ingesting Claim 3 (C3)
1.  **Block/Match:** The adjudicator blocks on `(subject=E_wallet, relationship_attribute='wallet_balance')`. It returns `F1` (valid `[2026-01-01, 2026-02-01)`) and `F2` (valid `[2026-02-01, NULL)`).
2.  **Comparison:** The incoming claim `valid_from` (`2026-03-01`) falls within the open-ended range of `F2`. The values differ (`120` vs. `150`).
3.  **Adjudication:** C3 supersedes `F2`:
    *   We cap `F2` by updating `valid_until = '2026-03-01T00:00:00Z'`.
    *   We insert a new fact `F3`, valid `[2026-03-01, NULL)`.
4.  **Database State:**
    *   **`F2` Row Updated in `facts`:** `valid_until = '2026-03-01T00:00:00Z'`.
    *   **Row inserted into `facts` (`F3`):**
        *   `fact_id`: `F3`
        *   `object_kind`: `'literal'`
        *   `object_literal_value`: `{"amount": 120, "currency": "USD"}`
        *   `valid_from`: `'2026-03-01T00:00:00Z'`
        *   `valid_until`: `NULL`
        *   `ingested_at`: $T_{ingest\_3}$
        *   `invalidated_at`: `NULL`
    *   **Row inserted into `fact_evidence`:** `(F3, C3, 'supports')`.
    *   **Row inserted into `fact_adjudications`:** `(outcome='supersede', fact_id=F3, related_fact_id=F2)`.

This database state cleanly answers the bi-temporal query "What was the wallet balance as of 2026-02-15?":
```sql
SELECT object_literal_value 
FROM facts 
WHERE subject_entity_id = 'E_wallet' 
  AND relationship_attribute = 'wallet_balance'
  -- valid-time filter
  AND valid_from <= '2026-02-15T00:00:00Z' 
  AND (valid_until IS NULL OR valid_until > '2026-02-15T00:00:00Z')
  -- transaction-time filter (only currently believed facts)
  AND invalidated_at IS NULL;
```
This correctly resolves to `F2` (balance = 150), with zero runtime evaluation or LLM calls.

---

## Q2: Postgres ↔ LadybugDB Projection Fit

Based on the verified capabilities in [ladybug_projection_findings.md](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/analysis/fact_layer_architecture_research/ladybug_projection_findings.md) and [ladybug_capabilities.md](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/analysis/ladybug_capabilities.md), we address how the unified Postgres schema projects to LadybugDB.

### 1. The Projection-Friendly Views (Postgres-Side)

LadybugDB has two major type mismatches when scanning Postgres tables via `ATTACH`:
1.  **No `timestamptz` support:** It will crash on any table scan containing a `timestamptz` column.
2.  **No `uuid` as a Primary Key type for node tables:** Node PKs must be `STRING` (or integer).

To hide this complexity from Cypher and allow clean, Parquet-free bulk loading, we define two projection-friendly views in Postgres. These views cast UUIDs to `text` and `timestamptz` values to timezone-naive UTC `timestamp` columns:

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- projection_entities: Casts UUIDs and filters active entities
-- ─────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW projection_entities AS
SELECT 
  entity_id::text AS id,
  type,
  canonical_name
FROM entities
WHERE status = 'active';

-- ─────────────────────────────────────────────────────────────────────────
-- projection_relations: Casts UUIDs and timestamptz to timezone-naive UTC timestamps.
-- Filters exclusively for active entity-to-entity relations (ignores literal attributes).
-- ─────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW projection_relations AS
SELECT 
  subject_entity_id::text AS "from_id", -- Target node PK must match Entity.id string
  object_entity_id::text AS "to_id",   -- Target node PK
  relationship_predicate AS relationship_predicate,
  fact_id::text AS relation_id,
  valid_from AT TIME ZONE 'UTC' AS valid_from,  -- Cast to timezone-naive timestamp
  valid_until AT TIME ZONE 'UTC' AS valid_until -- Cast to timezone-naive timestamp
FROM facts
WHERE object_kind = 'entity' 
  AND invalidated_at IS NULL; -- Only current beliefs are projected to L6
```

### 2. The Direct LadybugDB Projection Queries

Using the `ATTACH` extension, the projection pipeline can bulk-load the graph directly from the Postgres server in a single step with zero Parquet files.

```cypher
// 1. Initialize the Graph Schema
CREATE NODE TABLE Entity (
  id STRING,
  type STRING,
  canonical_name STRING,
  PRIMARY KEY (id)
);

CREATE REL TABLE Relates (
  FROM Entity TO Entity,
  relationship_predicate STRING,
  relation_id STRING,
  valid_from TIMESTAMP,
  valid_until TIMESTAMP
);

// 2. Attach the live Postgres database
ATTACH 'host=postgres-host port=5432 dbname=ugm user=postgres password=secret' AS pg (dbtype postgres, schema = 'public');

// 3. Bulk Load directly from the Postgres views
COPY Entity FROM pg.projection_entities;
// Note: LadybugDB maps the columns of Relates starting with FROM node key, TO node key, and then properties
COPY Relates FROM pg.projection_relations;
```

### 3. Switch to ATTACH-direct? (The Proposed Pipeline)

We recommend switching the P2 graph build from the DuckDB/Parquet-export loop to **ATTACH-direct**. 

#### The Hybrid Pipeline Decision:
*   **Graph Projection:** Uses ATTACH-direct. It eliminates the disk/network I/O of writing Parquet files to GCS and downloading them to the build worker. The type conversions are handled declaratively by Postgres views.
*   **External Analytics:** Community detection algorithms (e.g., Louvain/Leiden in igraph or graspologic) are unsupported in LadybugDB ([ladybug_capabilities.md §3](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/plan/analysis/ladybug_capabilities.md#L37-L47)). These algorithms still require an Arrow/Parquet export.
*   **The Hybrid Solution:** Build the LadybugDB instance via ATTACH-direct. Simultaneously, stream data directly from Postgres to Arrow in memory (using `connectorx` or standard DuckDB pipelines) to run the external clustering tools. The clustering results are then written back to Postgres (`entities.type`/`graph_degree`) and automatically picked up during the next rebuild cycle.

### 4. Post-Projection As-Of Cypher Traversal

Because LadybugDB has no native temporal traversal syntax, point-in-time graph traversals must use projected subgraphs based on the cast `TIMESTAMP` columns. To query paths as of world-time `$as_of` (e.g., `'2026-02-15T00:00:00'`), we project a filtered subgraph:

```cypher
// 1. Project the temporal subgraph
CALL PROJECT_GRAPH_CYPHER(
  'AsOfGraph',
  'MATCH (n:Entity) RETURN n',
  'MATCH (s:Entity)-[r:Relates]->(t:Entity) 
   WHERE r.valid_from <= $as_of 
     AND (r.valid_until IS NULL OR r.valid_until > $as_of) 
   RETURN s, r, t'
);

// 2. Run traversals on the projected subgraph
USE AsOfGraph;
MATCH p = (a:Entity {id: 'entity-1'})-[:Relates*1..3]->(b:Entity {id: 'entity-2'})
RETURN p;
```

---

## Q3: Step-Back Overall Architecture Review

The current target architecture consists of:
1.  **Postgres** as the single source of truth for evidence (claims) and belief (facts, adjudications).
2.  **LanceDB** as the vector/FTS index (filtering by entity identifiers).
3.  **LadybugDB** as a derived, read-optimized Cypher projection.
4.  **The K-Plane (Markdown Files)** as the human-readable compilation target.

We evaluate this stack against a fundamentally different alternative.

### Alternative: The Postgres-Only Architecture (pgvector + Recursive CTEs / Apache AGE)

Instead of projecting data to external LanceDB and LadybugDB instances, we run everything inside Postgres:
*   Use `pgvector` for vector similarity searches over facts and entity profiles.
*   Use standard Postgres Full-Text Search (FTS) for lexical search.
*   Run graph traversals directly inside Postgres using **recursive Common Table Expressions (CTEs)** or the **Apache AGE** extension (which embeds Cypher in PostgreSQL).

#### Honest Evaluation of the Postgres-Only Alternative:

*   **What it costs (The Downsides):**
    1.  **Traversal Latency & CPU Overhead:** Recursive CTEs in SQL are notoriously slow on deep or variable-length path queries (e.g., finding connections between entities at depth 3–5). They generate nested loops and heavy index-scan overhead. Apache AGE is cleaner but lacks the vectorised, columnar storage optimizations of a dedicated graph engine.
    2.  **No Direct Multi-Process Isolation:** Heavy analytical graph queries and vector similarity searches will share database resources (CPU, lock pool, memory buffer cache) with transactional writes. This creates severe resource contention at target scale.
    3.  **Complex Cypher-in-SQL Syntax:** Embedding Cypher inside SQL strings in Apache AGE is painful to write, test, and maintain compared to native cypher queries running on an embedded graph engine.
*   **What it saves (The Upsides):**
    1.  **No Sync / Drift:** Completely eliminates the LadybugDB projection pipeline, GCS snapshot uploads, and read-only reader hot-swaps. The "truth" and the "projection" are physically unified.
    2.  **Zero Serialization Overhead:** No need to cast UUIDs or timestamptz columns for external engines.
    3.  **Reduced Catalog Bloat:** Eliminates LanceDB and LadybugDB from the infrastructure footprint, leaving a single Postgres instance to deploy and maintain.

### Architectural Verdict

The **Postgres-Only alternative is rejected** because it fails to meet the low-latency query-path requirements of the layered memory system. 

In `ugm`, the read path must perform complex hybrid queries (e.g., "Find all documents referencing entities within 2 steps of Alice, ranked by vector similarity to question Q"). If these queries run on Postgres, transactional writes will suffer, and traversal latencies will scale poorly.

The **Unified `facts` (Option U) + ATTACH-direct LadybugDB projection** remains the best overall architecture. It cleanly separates concerns:
1.  **Postgres handles transaction processing and bi-temporal constraint validation.** It uses declarative exclusion constraints to enforce logical correctness.
2.  **LanceDB handles fast vector and FTS scans.** It avoids the constraint of LadybugDB's node-only index limit by keeping edge-relation embeddings out of the graph ([D8](file:///Users/jpuc/code/moje/ultimate_memory/ugm_2/ugm/decisions.md#L156-L170)).
3.  **LadybugDB provides embedded, zero-network-hop, memory-mapped Cypher traversals.** Using ATTACH-direct, the projection step is simplified, while views handle type conversion.

---

## Reject Summary & Migration Plan

### 1. What We Reject and Why
1.  **We reject D42's "surface-only, no literal supersession" policy.** It leaves temporal data (like wallet balances and revenues) un-adjudicated, forcing the API to output duplicate conflicting values when a single valid-time series is needed.
2.  **We reject Option S (Separate tables).** It duplicates complex bi-temporal slicing code, fragments the storage of belief, complicates profile querying, and makes promoting a literal string to a resolved entity complex.
3.  **We reject Postgres-only graph traversal (Apache AGE/CTEs).** It introduces high query latency and resource contention between transactional writes and heavy read traversals.
4.  **We reject Parquet-export loops for graph projection.** Direct SQL queries over an attached PG database are faster, simpler, and type-safe when wrapped in Postgres views.

### 2. Migration Path
To transition the current codebase to the Unified `facts` architecture:
1.  **SQL Migration:**
    *   Create the `facts` table incorporating the columns of `relations` plus `relationship_attribute` and `object_literal_value`.
    *   Apply the `exclude_overlapping_relations` and `exclude_overlapping_attributes` GiST exclusion constraints.
    *   Create the `fact_evidence` table (partitioned by HASH on `fact_id`) and migrate data from `relation_evidence`.
    *   Migrate historical data from `relations` into `facts` (setting `object_kind = 'entity'`).
    *   Drop the old `relations` table and replace it with the `relations` view.
    *   Drop `claim_attribute_facts` and `attribute_evidence`.
2.  **Adjudication Engine Update:**
    *   Update the E3 write worker to direct both relation extraction and non-relational attribute extraction to the `facts` table.
    *   Unify the supersession slicing functions to target the `facts` table directly.
3.  **Projection Script Update:**
    *   Deploy the `projection_entities` and `projection_relations` Postgres views.
    *   Replace the Parquet export step in the L6 worker with the Cypher `ATTACH` + `COPY FROM pg.view` commands.
