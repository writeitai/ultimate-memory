# LadybugDB projection findings — does the Postgres fact model project cleanly?

Verified June 2026 against the LadybugDB docs (`docs.ladybugdb.com/cypher/data-definition/create-table/`,
`.../extensions/attach/postgres/`) plus the prior `../ladybug_capabilities.md`. Compiled to ground the
fact-layer-architecture analysis (the unified-`facts`-vs-separate-tables question, P2 projection, and
the claims-validity decision). These are the *load-bearing* facts the analysts must reason on.

## A. CREATE NODE / REL TABLE — the typed-graph model

- **Node tables require a mandatory PRIMARY KEY**, type ∈ {STRING, numeric, DATE, BLOB, SERIAL}.
  **UUID is a supported *property* type but is NOT in the listed PK set** → our `entity_id` (uuid) is
  stored as a **STRING** node PK (cast `uuid::text` on projection), or kept as a UUID property with a
  STRING/SERIAL PK. Minor but real.
- **REL tables connect node tables only:** `CREATE REL TABLE T(FROM NodeA TO NodeB [, multiplicity], ...)`.
  The docs are explicit: *"Relationships cannot target non-node entities — only FROM NodeTable TO
  NodeTable constructions are supported."*  ⇒ **A literal/quantity-object fact can NEVER be a graph
  edge.** (Consistent with D18's "no Date/value nodes.") This is the single most important fact for the
  unified-vs-separate question: whatever the Postgres truth shape, the graph can only ever receive the
  **entity→entity** subset.
- **Multi-pair REL tables are allowed:** `CREATE REL TABLE Knows(FROM User TO User, FROM User TO City);`
  ⇒ one generic `RELATES` edge table can span many entity-type pairs (we don't need a table per
  predicate). Predicate stays a property; structural ones may get dedicated tables (p2 §2).
- **REL tables have no PK** (internal edge id) but carry arbitrary typed properties ⇒ our `relation_id`
  rides as a *property* (provenance/hydration key), not the edge identity.
- **Multiplicities:** MANY_MANY (default) / MANY_ONE / ONE_MANY / ONE_ONE. Our facts are MANY_MANY.
- **No `ALTER TABLE`.** Graph schema changes (new node/rel tables, new predicate-as-table) are done by
  **rebuilding**, not altering — which is exactly the D7 rebuild-first model. The projection schema is
  (re)generated each rebuild from the registry.

## B. ATTACH postgres — a Parquet-free projection path

- `ATTACH '<conn>' AS pg (dbtype postgres, schema = '...', skip_unsupported_table = ...)`. **Read-only.**
- You can scan attached tables from Cypher: `LOAD FROM pg.table RETURN *`, `CALL SQL_QUERY('pg','SELECT
  ... read-only ...') RETURN *`, or `USE pg; LOAD FROM table`.
- **You can bulk-load a graph table DIRECTLY from Postgres — no Parquet:**
  - `COPY Entity FROM pg.entities;`
  - `COPY Entity FROM (LOAD FROM pg.entities RETURN entity_id, name);`  (schema-mismatch / projection)
  - `COPY Relates FROM SQL_QUERY('pg', 'SELECT subject, object, predicate, ... FROM ... WHERE ...');`
  For a REL table the first two projected columns are the FROM/TO node PKs, the rest are properties.
- ⇒ **The whole P2 projection can be `ATTACH pg; COPY <each table> FROM SQL_QUERY(... filtered/cast ...)`**,
  replacing the Postgres→Parquet→`COPY FROM` hop in D7. The filter/transform happens *inside* the
  read-only `SQL_QUERY` (runs in Postgres), so it is exactly where a projection wants it.

## C. The hard wrinkle: `timestamptz` is UNSUPPORTED

- The postgres attach type map supports `timestamp` (→ TIMESTAMP), `date`, `uuid`, `json`, `numeric`,
  etc. — but **`timestamptz` (and `time`/`timetz`) are explicitly unsupported.** Our schema convention
  is *"every timestamp is `timestamptz`"* — including all four bi-temporal columns
  (`valid_from`/`valid_until`/`ingested_at`/`invalidated_at`).
- ⇒ A naïve `LOAD FROM pg.relations` (direct table scan) **errors on the timestamptz columns** (by
  default unsupported datatypes error; `skip_unsupported_table` only skips whole tables). The clean path
  is **`COPY … FROM SQL_QUERY('pg','SELECT valid_from AT TIME ZONE ''UTC'' AS valid_from, … ')`** — the
  cast to a tz-naïve UTC `timestamp` happens Postgres-side in the read-only query, sidestepping the
  unsupported type. (Alternative: keep the Parquet hop, which carries timestamptz fine; or store a
  parallel UTC `timestamp` column for projection.)
- This is concrete evidence for the user's intuition that *"the DB structure won't make the projection
  easy"*: it doesn't, **for free** — the as-of/bi-temporal columns need an explicit UTC cast (or
  Parquet) to cross into LadybugDB. The fix is cheap but must be a deliberate decision, and it touches
  the **claims-validity** model directly (whatever carries the windows that must project).

## D. As-of traversal still needs PROJECT_GRAPH_CYPHER

- LadybugDB has **no native temporal semantics** (prior finding §4). As-of queries are done by
  **projecting the graph to edges valid at `$as_of`** via `PROJECT_GRAPH_CYPHER` rel-predicates over the
  (now UTC-`timestamp`) temporal columns, then traversing (D10). So the temporal columns must (a) cross
  into the graph as a supported type (§C) and (b) be filterable by rel-predicates — both fine once cast.

## E. What this means for the architecture question (inputs, not conclusions)

1. **The graph can only ever hold the entity→entity subset.** A unified Postgres `facts` table
   (entity- or literal-object) projects to P2 by a **`WHERE object_kind='entity'`** filter in the COPY's
   `SQL_QUERY` — literal facts simply aren't projected. So "unify in Postgres, filter at projection" is
   *mechanically supported* and arguably clean. The separate-table design projects `relations` and skips
   `proposition_facts` — also clean. **Neither is blocked by LadybugDB; the projection is a filtered COPY
   either way.** The deciding factors are Postgres-side (one verdict engine vs two, D6), not graph-side.
2. **ATTACH-direct projection (no Parquet)** is newly attractive and would simplify D7 — but note (a)
   read-only is fine, (b) timestamptz must be cast, (c) community detection still needs a separate
   export (igraph/graspologic, D11) so a Parquet/Arrow export may still be produced for *that* pass even
   if the graph build goes ATTACH-direct. Consider a hybrid: ATTACH-direct for the LadybugDB build,
   Arrow/Parquet for the external-analytics pass.
3. **`timestamptz` everywhere** is a latent projection cost; the projection layer (SQL_QUERY casts) or a
   schema tweak (UTC `timestamp` projection columns) absorbs it. This is the concrete coupling between
   the **claims-validity decision** and the **projection**: the more places carry bi-temporal windows
   that must reach the graph, the more this cast matters.
4. **No ALTER + rebuild-first** means the graph schema is *generated from the registry each rebuild* — so
   adding predicates/attributes/types is free graph-side (rebuild), reinforcing that the governed
   vocabulary (predicates, and any attribute vocabulary) is the real schema authority, not LadybugDB DDL.

## Sources
`docs.ladybugdb.com/cypher/data-definition/create-table/`,
`docs.ladybugdb.com/extensions/attach/postgres/` (fetched June 2026); `../ladybug_capabilities.md`
(vendored-source + docs verification); designs `../../designs/p2_graph_design.md` (§2, §5b),
`../../designs/postgres_schema_design.md`.
