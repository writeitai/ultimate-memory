# Fact-layer architecture verdict: unified facts, direct graph projection

Date: 2026-06-24

This analysis answers the three requested architecture questions for the `ugm` design phase. It treats
the verified LadybugDB findings as load-bearing facts, preserves the settled rule that claims are
immutable evidence, and explicitly amends D42 because the newly affirmed requirement is stronger than
D42: temporal supersession of non-relational literal facts is a first-class must-have.

The short verdict:

- Choose **U: a unified adjudicated `facts` verdict layer**.
- Make `relations` a compatibility view over `facts WHERE object_kind = 'entity'`.
- Let literal-object facts use the same bi-temporal windows, evidence collapse, contradiction groups,
  and adjudication log as entity-object facts.
- Keep LadybugDB as the entity graph only. The graph projects only the `object_kind = 'entity'`
  subset because LadybugDB REL tables cannot target literals and D18 correctly forbids value/date
  nodes in the graph.
- Amend P2/D7 from "Postgres -> Parquet -> LadybugDB" to **ATTACH-direct for the Ladybug graph build**,
  with an optional Arrow/Parquet export generated from the same projection SQL for external community
  detection.

## Q1. Verdict-layer shape for non-relational temporal supersession

### The options

#### D42 status quo: relations supersede; literals are surfaced only

D42 is now insufficient. It was intellectually coherent for a weaker requirement: "surface
non-relational conflicts without creating a second belief authority." It deliberately avoided a
winner, validity window, status, or supersession path on `claim_attribute_facts`.

That shape cannot represent the affirmed wallet-balance requirement. A wallet balance is not merely a
set of conflicting source assertions. It is a dynamic scalar fact where a later open-ended assertion
normally closes the previous open-ended belief for the same subject and governed slot. If the system
cannot answer "what balance did we believe was valid on 2026-02-15?" from a structured verdict layer,
then it does not have first-class temporal supersession for literals.

Reject D42 status quo for this requirement.

#### S: keep `relations`; add separate `proposition_facts`

This is tempting because it avoids a polymorphic object column. It keeps entity-object facts in
`relations(subject, predicate, object_entity)` and adds a new
`proposition_facts(subject, attribute, typed_literal)` table with its own validity, evidence,
contradiction, and adjudication machinery.

The problem is not the table count. The problem is the duplicated verdict engine:

- two window-closing implementations;
- two contradiction protocols;
- two as-of query paths;
- two evidence joins;
- two adjudication ledgers;
- two sets of "current belief" indexes;
- two subtly different definitions of a fact slot.

At 10^8 claims, the expensive thing is not an XOR check between `object_entity_id` and
`literal_value`. The expensive thing is allowing two belief authorities to evolve independently.
D6 says validity has one home. A separate literal verdict table can be made "also in Postgres", but
that is not the spirit of D6. D6 is about a single adjudicated belief model, not just a single
database server.

The strongest argument for S is type purity: entity objects and literal objects have different value
normalization concerns. That argument fails because value normalization is pre-verdict
pre-processing. Money/date/unit/fiscal-calendar normalization belongs before the adjudicator, just as
entity resolution belongs before relation normalization. Once the object is reduced to a canonical
`object_identity`, the supersession engine sees the same shape: subject, governed relationship, slot
qualifiers, object identity, valid window, transaction window, evidence.

Reject S unless implementation constraints prove PostgreSQL cannot sustain the unified table. Nothing
in the current evidence suggests that.

#### U: unified adjudicated `facts`

The correct shape is one verdict table:

```
subject entity
+ governed relationship
+ object, either entity reference or typed literal
+ valid-time window
+ transaction-time window
+ evidence
+ contradiction group
+ adjudication transcript
```

This is not "claims become mutable." Claims remain immutable evidence. The new table is the verdict
layer, the same conceptual layer that `relations` already occupies.

The polymorphic object cost is real, but bounded:

- enforce exactly one of `object_entity_id` or literal columns;
- compute a canonical `object_identity` text key for uniqueness/exclusion;
- keep value-domain-specific normalization outside the table;
- use filtered indexes for entity-object and literal-object hot paths;
- expose typed compatibility views for callers that want non-polymorphic surfaces.

The benefit is much larger: one current-belief home for all structured facts.

### Recommended schema

The following DDL is the recommended logical schema, not a migration-ready Alembic file. It preserves
the current schema conventions: UUID identities, `timestamptz` in Postgres, governed vocabulary, D2
M:N evidence, D3 relation/fact-level supersession, and D6 Postgres-only validity.

First, unify the predicate/attribute vocabulary into a governed relationship registry. The current
`predicates` and `attributes` tables can become compatibility views or child tables, but the
adjudicator should see one registry.

```sql
CREATE TYPE fact_object_kind AS ENUM ('entity', 'literal');
CREATE TYPE fact_relationship_kind AS ENUM ('entity_relation', 'literal_attribute');

CREATE TABLE fact_relationships (
  deployment_id      uuid NOT NULL REFERENCES deployments,
  relationship_key   text NOT NULL,
  relationship_kind  fact_relationship_kind NOT NULL,
  parent_relationship_key text,
  description        text NOT NULL,
  synonyms           text[] NOT NULL DEFAULT '{}',
  tier               ontology_tier NOT NULL DEFAULT 'extension',
  status             ontology_status NOT NULL DEFAULT 'active',

  -- Domain and range. Entity ranges are graph-projectable; literal ranges are not.
  subject_type       text NOT NULL,
  object_kind        fact_object_kind NOT NULL,
  object_entity_type text,
  literal_domain     attribute_value_domain,

  -- Slot semantics for supersession. Examples:
  -- works_for may be many-valued unless a role/contract qualifier says otherwise.
  -- wallet_balance is one-current-value per subject+account+currency slot.
  is_functional_per_slot boolean NOT NULL DEFAULT false,
  default_close_previous boolean NOT NULL DEFAULT false,
  identity_qualifiers text[] NOT NULL DEFAULT '{}',

  exclude_from_graph_distance boolean NOT NULL DEFAULT false,
  usage_count        bigint NOT NULL DEFAULT 0,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),

  PRIMARY KEY (deployment_id, relationship_key),
  FOREIGN KEY (deployment_id, subject_type)
    REFERENCES entity_types (deployment_id, type),
  FOREIGN KEY (deployment_id, object_entity_type)
    REFERENCES entity_types (deployment_id, type),
  FOREIGN KEY (deployment_id, parent_relationship_key)
    REFERENCES fact_relationships (deployment_id, relationship_key),
  CHECK (
    (object_kind = 'entity'
      AND relationship_kind = 'entity_relation'
      AND object_entity_type IS NOT NULL
      AND literal_domain IS NULL)
    OR
    (object_kind = 'literal'
      AND relationship_kind = 'literal_attribute'
      AND object_entity_type IS NULL
      AND literal_domain IS NOT NULL)
  )
);
```

Then the verdict table:

```sql
CREATE TABLE facts (
  fact_id            uuid PRIMARY KEY,
  deployment_id      uuid NOT NULL REFERENCES deployments,

  subject_entity_id  uuid NOT NULL,
  relationship_key   text NOT NULL,
  object_kind        fact_object_kind NOT NULL,

  -- Entity object. Present iff object_kind = 'entity'.
  object_entity_id   uuid,

  -- Literal object. Present iff object_kind = 'literal'.
  literal_domain     attribute_value_domain,
  literal_value      jsonb,
  literal_value_text text,
  literal_value_precision text,

  -- Canonical identity used by uniqueness and evidence collapse.
  -- Examples:
  --   entity:  'entity:8b7...'
  --   literal: 'literal:money:USD:5000000'
  -- For non-normalizable literals, use a conservative per-assertion identity so the system
  -- surfaces possible disagreement rather than falsely collapsing distinct values.
  object_identity    text NOT NULL,

  -- Identity-bearing qualifiers declared by fact_relationships.identity_qualifiers.
  -- Display qualifiers may live in the evidence/claim; identity qualifiers affect blocking.
  qualifiers         jsonb NOT NULL DEFAULT '{}',
  qualifiers_hash    text NOT NULL DEFAULT '',

  valid_kind         claim_valid_kind NOT NULL DEFAULT 'proposition_validity',
  valid_from         timestamptz,
  valid_until        timestamptz,
  valid_precision    claim_valid_precision NOT NULL DEFAULT 'unknown',

  ingested_at        timestamptz NOT NULL DEFAULT now(),
  invalidated_at     timestamptz,

  evidence_count     integer NOT NULL DEFAULT 0,
  contradict_count   integer NOT NULL DEFAULT 0,
  confidence         real,
  contradiction_group uuid,

  status relation_status GENERATED ALWAYS AS
    (CASE WHEN invalidated_at IS NOT NULL
      THEN 'invalidated'::relation_status
      ELSE 'active'::relation_status
     END) STORED,

  fact_label         text,
  fact_label_version text,
  fact_label_embedding_ref text,
  normalizer_version text NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),

  UNIQUE (deployment_id, fact_id),
  FOREIGN KEY (deployment_id, subject_entity_id)
    REFERENCES entities (deployment_id, entity_id),
  FOREIGN KEY (deployment_id, relationship_key)
    REFERENCES fact_relationships (deployment_id, relationship_key),
  FOREIGN KEY (deployment_id, object_entity_id)
    REFERENCES entities (deployment_id, entity_id),

  CHECK (
    (object_kind = 'entity'
      AND object_entity_id IS NOT NULL
      AND literal_domain IS NULL
      AND literal_value IS NULL)
    OR
    (object_kind = 'literal'
      AND object_entity_id IS NULL
      AND literal_domain IS NOT NULL
      AND literal_value IS NOT NULL)
  ),
  CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from),
  CHECK (invalidated_at IS NULL OR invalidated_at >= ingested_at),

  -- At most one currently believed, non-contradictory fact with the same complete identity
  -- and overlapping valid-time. This is evidence-collapse, not supersession blocking.
  EXCLUDE USING gist (
    deployment_id WITH =,
    subject_entity_id WITH =,
    relationship_key WITH =,
    object_kind WITH =,
    object_identity WITH =,
    qualifiers_hash WITH =,
    tstzrange(valid_from, valid_until, '[)') WITH &&
  )
  WHERE (invalidated_at IS NULL AND contradiction_group IS NULL)
);

CREATE INDEX ix_facts_slot
  ON facts (deployment_id, subject_entity_id, relationship_key, qualifiers_hash);

CREATE INDEX ix_facts_entity_object
  ON facts (deployment_id, object_entity_id, relationship_key)
  WHERE object_kind = 'entity';

CREATE INDEX ix_facts_literal_slot
  ON facts (deployment_id, subject_entity_id, relationship_key, qualifiers_hash)
  WHERE object_kind = 'literal';

CREATE INDEX ix_facts_live_subject
  ON facts (deployment_id, subject_entity_id)
  WHERE invalidated_at IS NULL;

CREATE INDEX ix_facts_contradiction
  ON facts (contradiction_group)
  WHERE contradiction_group IS NOT NULL;
```

Evidence and adjudication become fact-grain, not relation-grain:

```sql
CREATE TABLE fact_evidence (
  deployment_id      uuid NOT NULL,
  fact_id            uuid NOT NULL,
  claim_id           uuid NOT NULL,
  stance             evidence_stance NOT NULL,
  normalizer_version text NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (fact_id, claim_id)
) PARTITION BY HASH (fact_id);

CREATE INDEX ix_factevidence_claim ON fact_evidence (claim_id);

CREATE TYPE fact_adjudication_outcome AS ENUM (
  'add',
  'noop',
  'supersede',
  'contradict',
  'same_as_merge_proposal',
  'promote_object_to_entity'
);

CREATE TABLE fact_adjudications (
  adjudication_id uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  fact_id         uuid NOT NULL,
  related_fact_id uuid,
  outcome         fact_adjudication_outcome NOT NULL,
  method          adjudication_method NOT NULL,
  confidence      real,
  triggering_claim_id uuid,
  features        jsonb,
  adjudicator_version text NOT NULL,
  decided_by      decision_actor NOT NULL DEFAULT 'auto',
  decided_at      timestamptz NOT NULL DEFAULT now(),
  superseded_by   uuid REFERENCES fact_adjudications,
  FOREIGN KEY (deployment_id, fact_id)
    REFERENCES facts (deployment_id, fact_id),
  FOREIGN KEY (deployment_id, related_fact_id)
    REFERENCES facts (deployment_id, fact_id)
);
```

The compatibility view for existing graph/search code:

```sql
CREATE VIEW relations AS
SELECT
  fact_id AS relation_id,
  deployment_id,
  subject_entity_id,
  relationship_key AS predicate,
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

CREATE VIEW relation_evidence AS
SELECT
  fe.deployment_id,
  fe.fact_id AS relation_id,
  fe.claim_id,
  fe.stance,
  fe.normalizer_version,
  fe.created_at
FROM fact_evidence fe
JOIN facts f
  ON f.deployment_id = fe.deployment_id
 AND f.fact_id = fe.fact_id
WHERE f.object_kind = 'entity';
```

For callers that want literal facts without polymorphism:

```sql
CREATE VIEW literal_facts AS
SELECT *
FROM facts
WHERE object_kind = 'literal';
```

### Engine behavior: shared supersession, isolated normalization

The adjudicator has two keys:

1. **Fact identity key** for evidence collapse:
   `(subject_entity_id, relationship_key, qualifiers_hash, object_kind, object_identity, valid range)`.
   Same value, compatible window -> add evidence to the existing fact.

2. **Slot key** for supersession/contradiction:
   `(subject_entity_id, relationship_key, qualifiers_hash)` plus the relationship's time semantics.
   Different value in a functional slot -> adjudicate whether to close, contradict, or coexist.

That is the same engine for entity and literal objects. Entity resolution and literal normalization are
different pre-processors, but they both produce `object_identity`.

Examples:

- Entity relation: "Alice works at Acme" -> `object_identity = entity:<acme_uuid>`.
- Literal fact: "Wallet W balance was 100 USD from Jan 1" ->
  `object_identity = literal:money:USD:100.00`.
- Literal restatement: "FY2023 revenue was 5.2M USD" -> same slot as the prior FY2023 revenue fact,
  different `object_identity`, adjudicated by the same outcome vocabulary.

The registry must mark which relationships are functional per slot. `wallet_balance` is functional:
one current value per wallet/currency/accounting qualifier. `board_member` is not. Some entity
predicates are functional in a qualifier scope; some literal attributes are not. This should be
registry data, not hard-coded table behavior.

### Wallet-balance series, end to end

Input claims:

1. `c1`: "Wallet A balance is 100 USD as of 2026-01-01."
2. `c2`: "Wallet A balance is 120 USD as of 2026-02-01."
3. `c3`: "Wallet A balance is 90 USD as of 2026-03-01."

Assume `wallet_balance` is a governed literal relationship:

```
relationship_key = 'wallet_balance'
object_kind = 'literal'
literal_domain = 'money'
is_functional_per_slot = true
default_close_previous = true
identity_qualifiers = ['wallet_id', 'currency']
```

Processing `c1`:

- E2 claim is immutable. It carries source text, `asserted_at`, `claim_valid_from = 2026-01-01`,
  `claim_valid_until = NULL`, and source provenance.
- The normalizer resolves subject entity `wallet_a`.
- Money normalization emits `{amount: 100, currency: 'USD'}` and
  `object_identity = literal:money:USD:100.00`.
- No live fact exists for the slot `(wallet_a, wallet_balance, wallet_id/currency qualifiers)`.
- Insert `f1`:
  - `object_kind = literal`
  - `valid_from = 2026-01-01`
  - `valid_until = NULL`
  - `ingested_at = t1`
  - `invalidated_at = NULL`
- Insert `fact_evidence(f1, c1, supports)`.

Processing `c2`:

- Normalization emits `object_identity = literal:money:USD:120.00`, `valid_from = 2026-02-01`.
- Slot blocking finds `f1`, because supersession blocks on subject+relationship+qualifiers, not on
  value.
- Registry says the slot is functional and default-close-previous.
- Adjudicator records a `supersede` decision.
- Update `f1`:
  - `valid_until = 2026-02-01`
  - `invalidated_at = t2`
- Insert `f2`:
  - `valid_from = 2026-02-01`
  - `valid_until = NULL`
  - `ingested_at = t2`
- Insert `fact_evidence(f2, c2, supports)`.

Processing `c3` repeats the same pattern:

- Close `f2.valid_until = 2026-03-01`, `f2.invalidated_at = t3`.
- Insert `f3` open-ended from `2026-03-01`.

Queries:

```sql
-- Current believed balance:
SELECT *
FROM facts
WHERE deployment_id = $1
  AND subject_entity_id = $wallet_a
  AND relationship_key = 'wallet_balance'
  AND object_kind = 'literal'
  AND invalidated_at IS NULL;
```

returns `f3`.

```sql
-- World-time as-of:
SELECT *
FROM facts
WHERE deployment_id = $1
  AND subject_entity_id = $wallet_a
  AND relationship_key = 'wallet_balance'
  AND object_kind = 'literal'
  AND valid_from <= '2026-02-15'::timestamptz
  AND (valid_until IS NULL OR valid_until > '2026-02-15'::timestamptz);
```

returns `f2`.

```sql
-- Bi-temporal as-of: what did the system believe at transaction time T
-- about world time W?
SELECT *
FROM facts
WHERE deployment_id = $1
  AND subject_entity_id = $wallet_a
  AND relationship_key = 'wallet_balance'
  AND object_kind = 'literal'
  AND ingested_at <= $system_as_of
  AND (invalidated_at IS NULL OR invalidated_at > $system_as_of)
  AND valid_from <= $world_as_of
  AND (valid_until IS NULL OR valid_until > $world_as_of);
```

This is the same query shape used for entity-object facts.

### Evidence collapse at scale

Evidence collapse still works. If 1,000 sources assert the same balance for the same open interval
before any superseding claim arrives, the system stores one fact and 1,000 evidence rows, not 1,000
current-value records. If a later claim changes the value, one fact window closes and one fact opens.

This matters more for literal facts than D42 did. D42's `claim_attribute_facts` grouped evidence but
refused to become a verdict. Under the new requirement, the verdict layer must collapse repeated
literal assertions exactly as relations collapse repeated entity assertions.

### Promotion from literal to entity

The unified table gives a clean promotion seam. Suppose a literal-like assertion later deserves an
entity object: "Series A financing: 5M USD" may become an entity `FundingRound` with relations to the
company, investors, amount, and date. Claims stay immutable. The normalizer can attach the same
claims as evidence to new entity-object facts and record a `promote_object_to_entity` adjudication
link from the old literal fact to the new entity fact.

With separate tables, promotion crosses verdict systems. With unified `facts`, promotion changes
object kind but not the evidence/adjudication model.

### Decisions to amend

- **D42 must be replaced**, not patched. New D42 should say: non-relational literal facts that can be
  normalized into a governed `(subject, relationship, typed-literal)` slot are first-class facts in
  the unified verdict layer. Purely irreducible n-ary claims remain evidence-only.
- **D2 remains intact**: claims are still distinct from verdict facts; M:N evidence remains.
- **D3 remains intact but should be generalized**: supersession operates at the fact level. The
  `relations` name becomes the entity-object subset of facts.
- **D6 is strengthened**: current belief has one home, `facts`, inside Postgres. LadybugDB, Lance, and
  K artifacts remain projections/consumers.
- **D18 remains intact for the graph**: literals and time are not graph nodes. Literal facts live in
  Postgres and P1 search, not in P2 graph edges.

## Q2. Postgres to LadybugDB projection fit

### Does unified `facts` project cleanly?

Yes. It projects more cleanly than the current separate schema because the P2 worker has exactly one
source table and one decisive filter:

```sql
WHERE object_kind = 'entity'
```

LadybugDB REL tables require node endpoints. Literal facts can never be edges. A unified Postgres
truth table does not fight this; it makes the graph projection an entity-subset projection.

The graph schema should also be amended: LadybugDB node primary keys cannot be UUIDs. Use STRING node
PKs and cast Postgres UUIDs to text.

```cypher
CREATE NODE TABLE Entity(
  id STRING PRIMARY KEY,
  name STRING,
  type STRING,
  summary STRING,
  created_at TIMESTAMP
);

CREATE REL TABLE Relates(
  FROM Entity TO Entity,
  predicate STRING,
  fact_id STRING,
  fact STRING,
  evidence_count INT64,
  valid_from TIMESTAMP,
  valid_until TIMESTAMP,
  ingested_at TIMESTAMP,
  invalidated_at TIMESTAMP,
  confidence DOUBLE,
  contradiction_group STRING
);
```

The durable P2 snapshot should normally load a superset of entity facts and keep the temporal columns,
then use `PROJECT_GRAPH_CYPHER` for user as-of traversal. Baking a user as-of into the durable COPY
would destroy arbitrary time-travel. However, an as-of-filtered COPY is valid for scratch graphs,
validation, or a deliberately materialized as-of snapshot. Both forms are shown below.

### ATTACH-direct graph load

Attach Postgres read-only:

```cypher
ATTACH 'host=... dbname=ugm user=... password=...' AS pg
  (dbtype postgres, schema = 'public');
```

Load entities. The `timestamptz` cast is mandatory because LadybugDB's Postgres attach does not
support `timestamptz`; cast to UTC `timestamp` in the SQL query.

```cypher
COPY Entity FROM SQL_QUERY('pg', $$
  SELECT
    e.entity_id::text AS id,
    e.canonical_name AS name,
    e.type AS type,
    e.profile_summary AS summary,
    e.created_at AT TIME ZONE 'UTC' AS created_at
  FROM entities e
  WHERE e.deployment_id = '00000000-0000-0000-0000-000000000000'::uuid
    AND e.status = 'active'
$$);
```

Canonical durable load for entity facts, retaining temporal columns for D10 as-of projection:

```cypher
COPY Relates FROM SQL_QUERY('pg', $$
  SELECT
    f.subject_entity_id::text AS from_id,
    f.object_entity_id::text AS to_id,
    f.relationship_key AS predicate,
    f.fact_id::text AS fact_id,
    f.fact_label AS fact,
    f.evidence_count::bigint AS evidence_count,
    f.valid_from AT TIME ZONE 'UTC' AS valid_from,
    f.valid_until AT TIME ZONE 'UTC' AS valid_until,
    f.ingested_at AT TIME ZONE 'UTC' AS ingested_at,
    f.invalidated_at AT TIME ZONE 'UTC' AS invalidated_at,
    f.confidence::double precision AS confidence,
    f.contradiction_group::text AS contradiction_group
  FROM facts f
  JOIN entities s
    ON s.deployment_id = f.deployment_id
   AND s.entity_id = f.subject_entity_id
   AND s.status = 'active'
  JOIN entities o
    ON o.deployment_id = f.deployment_id
   AND o.entity_id = f.object_entity_id
   AND o.status = 'active'
  WHERE f.deployment_id = '00000000-0000-0000-0000-000000000000'::uuid
    AND f.object_kind = 'entity'
$$);
```

As-of-filtered load, if the build intentionally wants a graph cut as of one time:

```cypher
COPY Relates FROM SQL_QUERY('pg', $$
  SELECT
    f.subject_entity_id::text AS from_id,
    f.object_entity_id::text AS to_id,
    f.relationship_key AS predicate,
    f.fact_id::text AS fact_id,
    f.fact_label AS fact,
    f.evidence_count::bigint AS evidence_count,
    f.valid_from AT TIME ZONE 'UTC' AS valid_from,
    f.valid_until AT TIME ZONE 'UTC' AS valid_until,
    f.ingested_at AT TIME ZONE 'UTC' AS ingested_at,
    f.invalidated_at AT TIME ZONE 'UTC' AS invalidated_at,
    f.confidence::double precision AS confidence,
    f.contradiction_group::text AS contradiction_group
  FROM facts f
  JOIN entities s
    ON s.deployment_id = f.deployment_id
   AND s.entity_id = f.subject_entity_id
   AND s.status = 'active'
  JOIN entities o
    ON o.deployment_id = f.deployment_id
   AND o.entity_id = f.object_entity_id
   AND o.status = 'active'
  WHERE f.deployment_id = '00000000-0000-0000-0000-000000000000'::uuid
    AND f.object_kind = 'entity'
    AND f.ingested_at <= '2026-06-24T00:00:00Z'::timestamptz
    AND (f.invalidated_at IS NULL OR f.invalidated_at > '2026-06-24T00:00:00Z'::timestamptz)
    AND (f.valid_from IS NULL OR f.valid_from <= '2026-06-24T00:00:00Z'::timestamptz)
    AND (f.valid_until IS NULL OR f.valid_until > '2026-06-24T00:00:00Z'::timestamptz)
$$);
```

That final `WHERE` is deliberately in Postgres. LadybugDB sees only supported scalar types after the
projection. PostgreSQL handles `timestamptz` comparison and the UTC cast.

### Should P2 switch from Parquet export to ATTACH-direct?

Yes, for the LadybugDB build. Amend D7's implementation detail from Parquet-first to
ATTACH-direct-first.

Reasons:

- Verified LadybugDB supports `COPY ... FROM SQL_QUERY('pg', ...)` directly into node and REL tables.
- The read-only limitation is fine. P2 is a projection builder.
- The `timestamptz` incompatibility is best handled in projection SQL with explicit
  `AT TIME ZONE 'UTC'` casts.
- It removes a whole intermediate artifact from the graph build path.
- It makes the entity-subset filter and UUID-to-STRING cast explicit at the boundary where they
  belong.

Keep a hybrid pipeline for analytics:

1. **P2 Ladybug build:** ATTACH Postgres and `COPY` from `SQL_QUERY`.
2. **External community detection:** produce Arrow/Parquet from the same canonical projection SQL,
   either via PostgreSQL `COPY (SELECT ...) TO ...` or from LadybugDB `COPY TO` after load.
3. **Write analytics back to Postgres:** communities, PageRank, degree, and centrality remain derived
   writebacks, not graph authority.

The key is to make the projection SQL a versioned artifact. Do not maintain separate "graph SQL" and
"community export SQL" by hand. The same source query should feed both.

### As-of traversal after projection

For the durable snapshot, load the entity facts with temporal columns and project a query-time
subgraph using LadybugDB projected graphs. Conceptually:

```cypher
CALL PROJECT_GRAPH_CYPHER(
  'entity_facts_as_of',
  'MATCH (n:Entity) RETURN n',
  '
   MATCH (a:Entity)-[r:Relates]->(b:Entity)
   WHERE r.ingested_at <= TIMESTAMP("2026-06-24 00:00:00")
     AND (r.invalidated_at IS NULL OR r.invalidated_at > TIMESTAMP("2026-06-24 00:00:00"))
     AND (r.valid_from IS NULL OR r.valid_from <= TIMESTAMP("2026-06-24 00:00:00"))
     AND (r.valid_until IS NULL OR r.valid_until > TIMESTAMP("2026-06-24 00:00:00"))
   RETURN a, r, b
  '
);
```

Then run traversal against `entity_facts_as_of`. The exact LadybugDB invocation syntax should be
kept in the P2 implementation tests because projected-graph syntax is engine-specific, but the
architectural point is fixed: after ATTACH-direct load, all four temporal columns are LadybugDB
`TIMESTAMP`, so D10 remains valid.

Literal facts never enter this graph. Literal as-of queries run in Postgres or P1 scalar-filtered
search over `facts`.

### Current schema friction and projection-friendly fixes

The current schema/design makes projection harder in four places:

1. **P2 DDL says `UUID PRIMARY KEY` for `Entity`.** Verified LadybugDB docs say UUID is not a node PK
   type. Use `STRING PRIMARY KEY` and cast `entity_id::text`.

2. **`timestamptz` everywhere is correct for Postgres but unsupported by LadybugDB attach.** Keep
   `timestamptz` in Postgres. Add projection SQL or projection views that cast every timestamp with
   `AT TIME ZONE 'UTC'`.

3. **The current `relations` table is entity-only and `claim_attribute_facts` is surface-only.** That
   made sense under D42 but fails the new literal-supersession requirement. Replace with unified
   `facts` and a `relations` view.

4. **Projection shape should be explicit.** Add a versioned SQL definition, function, or materialized
   projection view for P2:

```sql
CREATE VIEW p2_relates_projection AS
SELECT
  f.subject_entity_id::text AS from_id,
  f.object_entity_id::text AS to_id,
  f.relationship_key AS predicate,
  f.fact_id::text AS fact_id,
  f.fact_label AS fact,
  f.evidence_count::bigint AS evidence_count,
  f.valid_from AT TIME ZONE 'UTC' AS valid_from,
  f.valid_until AT TIME ZONE 'UTC' AS valid_until,
  f.ingested_at AT TIME ZONE 'UTC' AS ingested_at,
  f.invalidated_at AT TIME ZONE 'UTC' AS invalidated_at,
  f.confidence::double precision AS confidence,
  f.contradiction_group::text AS contradiction_group
FROM facts f
WHERE f.object_kind = 'entity';
```

This view is not authority. It is a projection contract.

## Q3. Is there a fundamentally better overall architecture?

The best overall architecture remains:

- Postgres is truth for Evidence and the unified fact verdict layer.
- Lance is P1 search for chunks, claims, and fact labels.
- LadybugDB is P2 entity graph projection.
- K plane is a cited narrative/compiled consumer, not a structured verdict authority.
- Rebuild-first remains the right projection model.
- ATTACH-direct improves the graph build but does not change the truth/projection split.

That said, there are real alternatives worth judging.

### Alternative A: Reify every fact as a graph node

Shape:

```
(subject Entity)-[:HAS_FACT]->(fact FactNode)-[:OBJECT_ENTITY]->(object Entity)
```

Literal facts store the typed literal as properties on `FactNode`, not as value nodes. This avoids
literal endpoints on REL tables and could exploit LadybugDB's node-only vector/FTS indexes by indexing
fact nodes.

Benefits:

- One graph representation for entity and literal facts.
- Fact labels could become node properties, so LadybugDB's node-only vector/FTS limitation becomes
  less painful.
- Some provenance traversals become visually uniform.

Why it loses:

- It changes P2 from an entity adjacency projection into a fact store. That blurs D6 and D8, even if
  technically derived.
- It roughly doubles or triples graph objects: every fact becomes a node plus one or two edges.
- Ordinary entity traversal becomes contorted: every semantic hop becomes two hops through a fact
  node.
- Community detection and graph distance become polluted by high-degree fact nodes unless every
  algorithm uses carefully projected views.
- It still does not make literal values graph endpoints, and D18 still says value/date nodes are not
  graph objects.
- It tempts the system to put fact search in the graph, fighting the already-settled Lance role.

This is a defensible design for a graph-native knowledge base. It is not the best design for `ugm`,
whose graph is a disposable entity-structure projection.

### Alternative B: Drop LadybugDB; use Postgres for graph queries

Shape:

- Store unified `facts` in Postgres.
- Use recursive CTEs, indexes, maybe Apache AGE or another PG graph extension.
- Keep Lance for vector search.

Benefits:

- No projection mismatch.
- No UUID-to-STRING cast.
- No `timestamptz` attach issue.
- One fewer embedded database in deployment.

Why it loses:

- P2 exists because graph traversal, path algorithms, read-only snapshot serving, and graph analytics
  are different workloads from OLTP fact adjudication.
- The LadybugDB snapshot isolates query load from the truth store.
- Rebuild-first snapshots make entity merges and graph corruption cheap.
- LadybugDB gives native path traversal and projected graphs. PostgreSQL can emulate this, but not as
  cleanly for repeated retrieval workloads.
- Community/PageRank/WCC-style analytics do not belong on the OLTP primary.

This alternative is simpler at small scale, but it gives up the reason P2 exists.

### Alternative C: Append-only fact versions instead of in-place window updates

Shape:

- Never update `facts.valid_until` or `facts.invalidated_at`.
- Append `fact_versions` or `fact_state_events`.
- Current/as-of state is computed from an event log or materialized current table.

Benefits:

- Strong audit story.
- No mutable verdict rows.
- Late-arriving corrections can be represented as events.

Why it loses as the primary model:

- The current design already has the audit story in `fact_adjudications`.
- As-of queries become event folding unless a current-state projection is maintained, which recreates
  mutable state under another name.
- PostgreSQL range exclusion on current facts is a clean way to enforce "no overlapping live belief"
  at write time.
- The adjudicated fact row is not evidence. It is allowed to be revised; that is the entire point of
  D3. Making it append-only buys conceptual symmetry at the cost of query and constraint complexity.

A small event log is still correct: that is `fact_adjudications`. Do not make the verdict table
event-sourced unless regulatory audit requirements become much stricter than currently stated.

### Alternative D: Keep separate `relations` and `proposition_facts`

This is Q1 option S. It is the nearest plausible competitor.

It wins on narrow type purity and may be easier to implement incrementally. It loses architecturally:
two verdict tables mean two belief homes, two adjudication APIs, and two sets of edge cases. The new
requirement explicitly says literal temporal supersession is first-class. First-class should mean the
same verdict machinery, not a parallel subsystem.

### Alternative E: Move literal temporal belief to K3

Shape:

- Keep D42 surface-only in E.
- Let K3 choose working scalar values in compiled prose with citations.

Why it loses:

- K3 is not the structured truth layer.
- Query-time systems need machine-readable as-of answers.
- K3 refresh is debounced, narrative, and scoped. It cannot be the only home of wallet balances,
  revenue series, or headcount series.

K3 should narrate conflicts and cite evidence. It should not be the structured current-value store.

### Final architecture recommendation

The materially best design is the current direction with two amendments:

1. **Unify the adjudicated fact layer.**
   `facts` becomes the sole current-belief home for structured facts, whether the object is an entity
   or a typed literal. `relations` is the graph-projectable view.

2. **Switch LadybugDB build to ATTACH-direct.**
   Use `COPY ... FROM SQL_QUERY('pg', ...)`, cast UUIDs to STRING, cast `timestamptz` to UTC
   `timestamp`, and keep optional Parquet/Arrow export for external analytics.

This architecture wins because it aligns each system with its natural job:

- Postgres enforces the hard correctness invariants: evidence, verdicts, windows, contradiction,
  tenancy, registry governance.
- Lance handles semantic and lexical entry over large text/fact-label surfaces.
- LadybugDB handles entity graph structure, paths, projected as-of traversal, and snapshot serving.
- K plane handles compiled explanations and working narratives, never hidden structured truth.

## Migration plan

1. **Introduce `fact_relationships`.**
   Backfill current `predicates` as `entity_relation` rows and current `attributes` as
   `literal_attribute` rows. Keep `predicates` and `attributes` as compatibility views or tables fed
   from the unified registry during transition.

2. **Create `facts`, `fact_evidence`, and `fact_adjudications`.**
   Keep old tables during backfill. Add compatibility views with old names after cutover.

3. **Backfill existing `relations`.**
   Every `relations` row becomes a `facts` row with `object_kind = 'entity'` and
   `object_identity = 'entity:' || object_entity_id::text`. Backfill `relation_evidence` into
   `fact_evidence`. Backfill `relation_adjudications` into `fact_adjudications`.

4. **Reprocess D42 attribute clusters into literal verdict facts.**
   Do not blindly treat `claim_attribute_facts` as current truth. It was designed as a no-belief-axis
   projection. Use it as a candidate grouping input, but run the new fact adjudicator over immutable
   claims in slot order. For functional dynamic relationships, close open-ended predecessor windows.
   For unresolved disagreements, assign `contradiction_group`.

5. **Replace old surfaces.**
   Expose:
   - `relations` view for entity-object facts;
   - `relation_evidence` view over `fact_evidence`;
   - `literal_facts` view for typed-literal facts;
   - `facts_as_of` recipes for unified bi-temporal lookup.

6. **Update P1.**
   Rename the Lance "relations" fact-label index conceptually to a "facts" index, while preserving a
   relation-only filtered index or scalar filter for graph workflows. Literal facts deserve fact-label
   search too; they just do not project to P2.

7. **Update P2.**
   Change LadybugDB node PKs to STRING. Replace Parquet-first graph loading with ATTACH-direct
   projection SQL. Filter `facts.object_kind = 'entity'`.

8. **Retire or redefine D42 artifacts.**
   `claim_attribute_facts` can either disappear or become a temporary detector/debugging projection.
   It must no longer be the final architecture for governed literal facts. Irreducible n-ary claims
   may still need a surface-only conflict index, but that is a residual claim-analysis problem, not
   the primary literal-fact design.

## What is explicitly rejected

- Claim mutation, claim `valid_until`, or claim supersession. This remains ruled out.
- Literal/date/value nodes in the graph. D18 remains correct for P2.
- Separate literal verdict table duplicating relation machinery.
- D42 surface-only as the answer for dynamic scalar facts.
- Query-time LLM adjudication for current values.
- Making K3 the structured home of scalar truth.
- Putting embeddings or FTS for fact labels in LadybugDB by reifying facts solely to exploit
  node-only indexes.

## Bottom line

The design should stop treating "relation" as the name of the verdict layer. "Relation" is only the
graph-projectable subset: facts whose object is another entity. The foundational object should be
`fact`.

That one rename is not cosmetic. It lets the system satisfy the new literal temporal supersession
requirement without corrupting claims, without introducing a second supersession engine, and without
lying to LadybugDB about literals being graph objects.
