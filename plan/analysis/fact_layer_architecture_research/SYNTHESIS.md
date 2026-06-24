# SYNTHESIS — the fact layer, temporal supersession of non-relational facts, and the LadybugDB projection

Consolidates four independent inputs: an external **Codex** analysis (`external_agents/codex.md`), an
external **Antigravity** analysis (`external_agents/agy.md`), an internal **5-angle workflow with
adversarial critiques** (`internal_analysis.md`), and the **verified LadybugDB findings**
(`ladybug_projection_findings.md`). They **converge decisively**. This is *analysis* — it recommends a
candidate **D43** and a set of amendments, and logs nothing binding (the binding decision + schema
edits would be a follow-up, as D42 followed the conflict analysis). CLAUDE.md: written for a stranger
(Rule 1); full-scope, numbers are starting points (Rule 2).

## 0. The question

Three intertwined questions, raised because (a) the user affirmed that **temporal supersession of
non-relational facts** — a balance/revenue/headcount asserted open-endedly (`valid_from` only) and
*closed when the value changes* — is a **first-class must-have**, which D42 ("surface, never resolve")
cannot deliver; and (b) the LadybugDB typed-graph model seemed to fit the relations mental model
awkwardly, with the projection looking hard.

- **Q1.** The verdict-layer shape: **unified `facts`** vs **separate `relations` + `proposition_facts`**
  vs **D42 status quo**.
- **Q2.** Postgres ↔ LadybugDB projection fit (given the verified constraints).
- **Q3.** Is there a fundamentally better overall architecture?

## 1. Recommendation (all four inputs agree)

**Adopt one unified `facts` verdict layer over immutable claims**, with a polymorphic object
(`object_kind ∈ {entity, literal}`), **one** bi-temporal apparatus, **one** supersession/contradiction
adjudicator (the D4 cheap-first cascade generalized from `relation_id` to `fact_id`), **one** evidence
join, **one** adjudication transcript. **`relations` becomes the `object_kind='entity'` view** — the
only slice the graph can physically project. The single reframing (Codex): *stop treating "relation" as
the name of the verdict layer; the foundational object is `fact`, and a relation is just its
graph-projectable subset.*

**The gate that makes it correct (the internal workflow's decisive contribution).** A literal fact gets
the **belief axis** (a closable `valid_until`, a transaction-time `invalidated_at`, the literal
supersession constraint) **only when it is `supersedable`** — derived from the attribute's existing
`claim_valid_kind`:

- `effective_period` (a single-valued *state* — balance, headcount, status, current title) ⇒
  **supersedable**: a later value closes the predecessor's window (the affirmed must-have).
- `measurement_period` (a period figure — FY2023 revenue) ⇒ **not supersedable**: two sources giving
  different figures for the **same** period are a **both-stand disagreement** that must **never** get a
  silent winner — they keep **D42's no-belief-axis**, now enforced by a CHECK + the CI schema-test +
  the recipe linter. D42 is **subsumed, not deleted.**
- `event_time` (founding date — the date *is* the value) ⇒ handled as a value, not a window.

So the unified table delivers literal supersession **without** ever auto-resolving genuine
disagreements. A new `attribute_value_semantics` enum was **rejected** as a 1:1 relabel of
`claim_valid_kind`.

## 2. Q1 — why unified, not separate, not status quo

| | D6 (one belief home) | Engine | Promotion seam | Scale | Verdict |
|---|---|---|---|---|---|
| **D42 status quo** | n/a (no literal belief) | — | — | — | **Insufficient** — its only safety pillar is the *absence* of a belief axis; the must-have *is* a belief axis. Can't host it. |
| **S — separate tables** | **✗ two homes** | duplicated | drift on the seam | 2 EXCLUDEs/transcripts | **Rejected** — the same fact can live as `proposition_fact` *and* (post-promotion) as `relation` with no shared key → Mem0-class drift; the disjointness CHECK only covers the promotable subset, which is *not* the must-have's pure-literal core. |
| **U — unified `facts`** | **✓ one home (strengthened)** | one (D4 generalized) | trivial / often none | one engine, gated EXCLUDE | **Recommended** — same proven machinery; claims immutable (D3); projects as a filtered+cast COPY (D18 held structurally). |

The strongest argument *for* S — that entity-objects and literal-objects have different value
concerns — **fails**, because value normalization is **pre-verdict pre-processing**: once the object is
reduced to a canonical identity (`entity:<uuid>` or `literal:money:USD:5000000`), the supersession
engine sees one shape (subject, governed relationship, qualifiers, object identity, windows, evidence).
The polymorphic-object cost (an exactly-one-of CHECK) is real but bounded; the benefit — one
current-belief home for *all* structured facts — is large.

## 3. Concrete schema (consensus of agy's DDL + Codex's vocabulary unification + the workflow's gate)

```sql
CREATE TYPE fact_object_kind AS ENUM ('entity','literal');
-- REUSE existing enums: relation_status, evidence_stance, adjudication_outcome/method,
-- attribute_value_domain, claim_valid_kind. NO new attribute_value_semantics enum.

-- One governed relationship vocabulary (merges predicates + attributes), discriminated by range:
CREATE TABLE governed_relationships (
  deployment_id   uuid NOT NULL REFERENCES deployments,
  rel_key         text NOT NULL,                 -- 'works_for' | 'wallet_balance' | ...
  range_kind      fact_object_kind NOT NULL,     -- entity  => predicate (keeps predicate_signatures, D18 edge_type_map)
                                                 -- literal => attribute (value_domain + identity_qualifiers + ...)
  parent_key      text,
  description      text NOT NULL,
  synonyms         text[] NOT NULL DEFAULT '{}',
  tier             ontology_tier NOT NULL DEFAULT 'extension',
  -- literal-range only:
  value_domain     attribute_value_domain,        -- money|date|quantity|count|ratio|string_enum|boolean
  unit_dimension   text,
  identity_qualifiers text[] NOT NULL DEFAULT '{}',-- IFRS vs GAAP / global vs US => different slot, not a conflict
  default_valid_kind claim_valid_kind,            -- THE GATE: effective_period => supersedable; measurement_period => both-stand
  cardinality      text NOT NULL DEFAULT 'single',-- single (supersede) | set (coexist) for multi-valued literals
  usage_count      bigint NOT NULL DEFAULT 0,
  status           ontology_status NOT NULL DEFAULT 'active',
  PRIMARY KEY (deployment_id, rel_key)
);  -- predicates / attributes survive as compatibility VIEWS over this during migration

CREATE TABLE facts (
  fact_id           uuid PRIMARY KEY,
  deployment_id     uuid NOT NULL REFERENCES deployments,
  subject_entity_id uuid NOT NULL,                -- always an entity (D2 subject rule)
  rel_key           text NOT NULL,                -- → governed_relationships
  object_kind       fact_object_kind NOT NULL,    -- entity => graph-eligible; literal => Lance/PG only
  object_entity_id  uuid,                          -- iff entity
  object_value      jsonb,                          -- iff literal: {amount:5000000,currency:'USD'}
  object_value_identity text,                       -- iff literal: canonical hash(normalized value+unit+precision)
  qualifiers_hash   text NOT NULL DEFAULT '',
  valid_kind        claim_valid_kind,               -- DENORMALIZED + locked from governed_relationships.default_valid_kind
  cardinality       text NOT NULL DEFAULT 'single',  -- DENORMALIZED + locked from the registry: single (supersede) | set (coexist); EXCLUDEs cannot join the registry
  supersedable      boolean GENERATED ALWAYS AS      -- MECHANICALLY derived, not app-set (review fix): an app cannot mis-mark it
                      (object_kind = 'entity' OR (valid_kind = 'effective_period' AND cardinality = 'single')) STORED,
  -- one bi-temporal window. For a NON-supersedable literal, valid_from/valid_until is the ASSERTED
  -- measurement period (FY2023 = [2023-01-01, 2024-01-01)) — set once, never re-capped by the worker:
  valid_from timestamptz, valid_until timestamptz,
  ingested_at timestamptz NOT NULL DEFAULT now(), invalidated_at timestamptz,
  evidence_count int NOT NULL DEFAULT 0, contradict_count int NOT NULL DEFAULT 0, confidence real,
  contradiction_group uuid,
  status relation_status GENERATED ALWAYS AS
    (CASE WHEN invalidated_at IS NOT NULL THEN 'invalidated'::relation_status ELSE 'active'::relation_status END) STORED,
  fact_label text, fact_label_version text, fact_label_embedding_ref text,   -- label embedded in Lance (D8, now incl. literal facts)
  normalizer_version text NOT NULL, adjudicator_version text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deployment_id, fact_id),
  FOREIGN KEY (deployment_id, rel_key)           REFERENCES governed_relationships (deployment_id, rel_key),
  FOREIGN KEY (deployment_id, subject_entity_id) REFERENCES entities (deployment_id, entity_id),
  FOREIGN KEY (deployment_id, object_entity_id)  REFERENCES entities (deployment_id, entity_id),
  -- ONE exclusive-arc CHECK (review fix): an entity row can never leak literal columns, and vice-versa:
  CHECK ( (object_kind='entity'  AND object_entity_id IS NOT NULL AND object_value IS NULL     AND object_value_identity IS NULL)
       OR (object_kind='literal' AND object_entity_id IS NULL     AND object_value IS NOT NULL AND object_value_identity IS NOT NULL) ),
  CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from),
  CHECK (invalidated_at IS NULL OR invalidated_at >= ingested_at),
  -- the relocated D42 no-belief-axis guard (CI-tested). BLOCKER FIX (both reviewers): bar only the
  -- TRANSACTION-time invalidation, NOT valid_until — a non-supersedable literal MUST keep its asserted
  -- measurement period (else FY2023 is unrepresentable). The "never re-cap valid_until" + "no single-
  -- value recipe" halves are worker/linter invariants, not a column constraint:
  CHECK (supersedable OR invalidated_at IS NULL),
  -- entity arm: ≤1 believed, non-contradictory relation per (s, key, object) over overlapping world-time:
  EXCLUDE USING gist (deployment_id WITH =, subject_entity_id WITH =, rel_key WITH =,
                      object_entity_id WITH =, (tstzrange(valid_from, valid_until)) WITH &&)
    WHERE (object_kind='entity' AND invalidated_at IS NULL AND contradiction_group IS NULL),
  -- literal SINGLE-VALUED SUPERSEDABLE arm: ≤1 believed value per (s, key, qualifiers) over overlapping
  -- world-time. VALUE is EXCLUDED from the key, so a new value CLOSES the old window (supersession):
  EXCLUDE USING gist (deployment_id WITH =, subject_entity_id WITH =, rel_key WITH =,
                      qualifiers_hash WITH =, (tstzrange(valid_from, valid_until)) WITH &&)
    WHERE (object_kind='literal' AND supersedable AND cardinality='single'
           AND invalidated_at IS NULL AND contradiction_group IS NULL),
  -- literal COEXIST arm (review fix: both-stand non-supersedable OR multi-valued set): VALUE is INCLUDED
  -- in the key, so distinct values COEXIST (both stand) while exact duplicates are forbidden — no winner:
  EXCLUDE USING gist (deployment_id WITH =, subject_entity_id WITH =, rel_key WITH =, qualifiers_hash WITH =,
                      object_value_identity WITH =, (tstzrange(valid_from, valid_until)) WITH &&)
    WHERE (object_kind='literal' AND (NOT supersedable OR cardinality='set')
           AND invalidated_at IS NULL AND contradiction_group IS NULL)
);
CREATE INDEX ix_facts_block_subj ON facts (deployment_id, subject_entity_id, rel_key, object_kind);
CREATE INDEX ix_facts_block_obj  ON facts (deployment_id, object_entity_id, rel_key) WHERE object_kind='entity';
CREATE INDEX ix_facts_contradiction ON facts (contradiction_group) WHERE contradiction_group IS NOT NULL;

CREATE TABLE fact_evidence (   -- relation_evidence + attribute_evidence merged
  deployment_id uuid NOT NULL, fact_id uuid NOT NULL, claim_id uuid NOT NULL,
  stance evidence_stance NOT NULL, normalizer_version text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (fact_id, claim_id)
) PARTITION BY HASH (fact_id);

-- fact_adjudications: relation_adjudications generalized to fact_id (one transcript).
-- relations VIEW preserves every existing reader (graph build, blocking, recipes):
CREATE VIEW relations AS
  SELECT fact_id AS relation_id, deployment_id, subject_entity_id, rel_key AS predicate, object_entity_id,
         valid_from, valid_until, ingested_at, invalidated_at, evidence_count, contradict_count,
         confidence, contradiction_group, status, fact_label, fact_label_embedding_ref, normalizer_version
  FROM facts WHERE object_kind='entity';
```

## 4. End-to-end — the gate in action

**Supersedable (the must-have).** `wallet_balance` is `effective_period` ⇒ supersedable. Three
open-ended claims: $100 (from Jan), $150 (from Feb), $120 (from Mar). The adjudicator blocks on
`(subject, wallet_balance)`; each new value **caps** the predecessor's `valid_until` at the new
`valid_from` (note: `invalidated_at` stays NULL — the old value is still *true for its window*) and
inserts the new fact. *"Balance as of Feb 15"* = one indexed query → $150, zero LLM. The literal EXCLUDE
keeps exactly one believed value per instant.

**Both-stand (must NOT supersede).** `fiscal_revenue` is `measurement_period` ⇒ **not** supersedable.
"$5M FY2023" and "$7M FY2023" both land as `supersedable=false` literal facts; the CHECK forbids a
`valid_until`/`invalidated_at`; they share a `contradiction_group` and **both stand**, surfaced — the
recipe linter still bars a single-value answer. Exactly D42's behavior, now living as no-belief-axis
rows of `facts`.

## 5. Q2 — projection (the user's "won't project easily" worry, resolved)

The graph is **neutral** across U/S/D42 (every option projects the entity subset, drops literals) — so
LadybugDB doesn't decide the verdict-layer shape. U projects strictly cleanly, **Parquet-free**, via
Postgres-side casts in a read-only `SQL_QUERY` (the canonical sketch is in `ladybug_projection_findings`
§E + the synthesis below):

- **Entity-subset filter** `WHERE object_kind='entity'` — literals never selected (REL = node endpoints
  only; D18 structural).
- **`timestamptz` cast** `valid_from AT TIME ZONE 'UTC'` → tz-naïve UTC `TIMESTAMP` (timestamptz is
  unsupported by the attach). **U adds zero new cast surface** — only the entity arm crosses; the
  literal arm stays in Postgres+Lance where `timestamptz` is native.
- **UUID→STRING** node PK (`entity_id::text`); `fact_id::text` as an edge property.
- **ATTACH-direct** `COPY Entity/RELATES FROM SQL_QUERY('pg', …)` replaces the D7 Parquet hop; keep a
  Parquet/Arrow `COPY TO` only for the **D11** community pass (no Louvain in LadybugDB) **and as a
  verified fallback** until ATTACH bulk-COPY is load-tested at 10⁸ (the attach scanner lives in the
  un-vendored extensions repo — treat throughput as unverified).
- **No runtime `status<>'merged'` join** — canonical-only is pre-projection (merges re-point on
  rebuild, D21/p2 §2).
- **Generate the projection SQL from the registry**, never hand-maintain it — a missed `AT TIME ZONE`
  cast errors the whole COPY (unsupported type). Rebuild-first (D7) makes generation natural.
- **As-of** via `PROJECT_GRAPH_CYPHER` rel-predicates over the cast columns (D10); the supersedable
  literal as-of is a Lance scalar window scan. **The `$as_of` parameter must be supplied as a UTC-naïve
  `timestamp`** (the same convention as the cast columns) — the projection-SQL generator owns *both* the
  column casts and the parameter normalization (review fix).

So the projection becomes *easier* under U, not harder — the Postgres view/`SQL_QUERY` absorbs the
type-mismatch and the entity filter; the LadybugDB side is a trivial `COPY`.

## 6. Q3 — no fundamentally better architecture survives

The stack (Postgres truth + Lance vectors + LadybugDB entity-graph projection + K-plane narrative) is
right. Alternatives weighed and rejected: **event-sourced fold-on-read** (re-introduces corpus-scale
aggregation D23/D25 forbid; its correct residue *is* U), **reify literal facts as graph nodes**
(node-only indexes + no native temporal + 20–90 GB/snapshot + D18), **synthetic measurement entities**
(literal-in-entity-costume, graph explosion), **Postgres-only graph** (recursive-CTE/Apache-AGE
latency + write/read contention). ATTACH-direct improves the *build* but does not change the
truth/projection split. **Optional, documented, gated-on-demand:** a supersedable literal *may* also
project its currently-believed scalar as a **node property** on the subject Entity (node-indexable,
single-valued, full history staying Postgres+Lance) — not core.

## 7. Invariants & the candidate decision

**Candidate D43 — Facts are one unified verdict layer over immutable claims; object is entity or
literal; supersession is gated by attribute time-semantics.** Replace the separate `relations` table and
the no-belief-axis `claim_attribute_facts` projection with a single `facts` verdict table (polymorphic
object, one bi-temporal window, one D4 cascade, one `fact_evidence`, one `fact_adjudications`).
`relations` becomes the `object_kind='entity'` view (the graph's only slice). Predicates + attributes
merge into `governed_relationships` (range_kind entity|literal). The belief axis fires for a literal
**only when `supersedable`** (`claim_valid_kind='effective_period'`); non-supersedable literals keep
D42's no-belief-axis (CHECK + CI test + linter) and are surfaced, never resolved.

**Amendments (large but each a simplification — one engine, fewer tables):**
- **D2** — relations are the entity-object *view* over `facts`; subject always an entity, object
  entity-or-literal at truth grain (entity-only at graph grain). *Amend wording.*
- **D3** — supersession is **fact-level** (a strict generalization of relation-level), covering
  supersedable literal facts; **claims stay immutable** (untouched). *Amend wording.*
- **D4** — the cheap-first supersession/contradiction cascade now blocks on `(subject_entity, rel_key)`
  and operates on **`fact_id`** (not `relation_id`), covering the literal arm; the cascade logic is
  unchanged. *Amend wording.* (review fix — was missing.)
- **D5** — the governed **predicate** registry and the **attribute** registry merge into one
  `governed_relationships` vocabulary discriminated by `range_kind ∈ {entity, literal}` (entity-range
  keeps `predicate_signatures`/the D18 edge_type_map; literal-range keeps `value_domain` +
  `identity_qualifiers` + `default_valid_kind` + `cardinality`); `predicates`/`attributes` survive as
  compatibility views. The `other:`-escape + promotion funnel apply to both ranges. *Amend.* (review fix.)
- **D8** — fact-label embeddings in Lance now cover **all** structured facts (entity *and* literal),
  keyed by `fact_id`; the relation-only fact-label index becomes a `WHERE object_kind='entity'` filter
  for graph workflows, and literal facts gain label search too (they still never enter the graph).
  *Amend.* (review fix — was missing.)
- **D6** — *strengthened, not weakened*: one `facts` table = one belief home for both kinds; the
  "Refined by D42" no-belief-axis note is **re-scoped** to the non-supersedable literal subset only.
- **D7** — log the optional **ATTACH-direct** build hop (Parquet retained for D11 + as fallback).
- **D18** — add a **truth-shape-vs-graph-shape** clause: literals are permitted as fact *objects* in
  the Postgres truth/supersession table but **never** as graph nodes/edges (the `object_kind='entity'`
  projection filter is the structural guarantee); time is still never a predicate/Date-node *on the
  graph*. *Amend.*
- **D41** — claims stay immutable evidence (pillars intact at the claim grain); the believed value now
  lives in `facts`, not on the claim — so claim-validity is still never a second authority. *Amend
  reasoning.*
- **D42** — **superseded for supersedable attributes; repurposed (not deleted) for the both-stand
  residue** (its no-belief-axis CHECK, CI test, recipe linter, `attribute_conflicts`/
  `attribute_value_as_of` recipes, and pick-a/pick-b-illegal CHECK all survive, now applying to
  non-supersedable literal rows of `facts`); `attributes` folds into `governed_relationships`;
  `promote_to_relation` survives but is no longer the *only* path to a believed value.

## 8. Migration (additive at the read layer; no rewrite of immutable claims; P2/P3 free under D7)

1. **Widen + rename the entity arm** (near-zero risk): add the polymorphic + gate columns to
   `relations`, rename to `facts`, backfill existing rows `object_kind='entity', supersedable=true`. The
   relations GiST EXCLUDE becomes the entity-arm EXCLUDE verbatim. `relation_evidence`→`fact_evidence`
   and `relation_adjudications`→`fact_adjudications` are column renames (same HASH/PK).
2. **Merge vocabularies** into `governed_relationships` (predicates→entity, attributes→literal carrying
   `value_domain`/`default_valid_kind`/`identity_qualifiers` + `cardinality`); keep `predicates`/
   `attributes` as compatibility views.
3. **Literal arm = an upgrade of D42, not a teardown.** `claim_attribute_facts` is a derived projection
   — re-run E3's attribute branch over the zero-relation residue, branching on `claim_valid_kind`:
   `effective_period` clusters → supersedable literal facts (adjudicate windows + supersession chains);
   `measurement_period` clusters → non-supersedable literal facts (`contradiction_group`, both stand).
4. **Views** `relations` (entity) + `attribute_facts` (literal) keep every reader working; the recipe
   linter relocates its no-single-value bar to the **non-supersedable** literal recipes; a believed
   value-as-of is now legal (`current_belief=true`) for supersedable literals.
5. **CI**: replace the no-belief-axis schema-test with the `CHECK (supersedable OR …)` + a test that
   non-supersedable literals carry no closed window; add a **golden CI gate** on the
   supersedable-vs-both-stand routing and the EXCLUDE key choice (value-excluded vs value-included).
6. **Rebuild** P1 (Lance now covers supersedable literal windows), P2 (filter unchanged), re-run D11.
7. **decisions.md**: log D43 + the amendments; **postgres_schema_design.md**: §9 `facts`, retire/
   repurpose §9.A, rewrite §15 non-goals (drop "no believed pure-literal value" *for supersedable
   attributes*; keep it for both-stand), extend §17 spikes.

## 9. Residual risks (must clear before the literal arm ships)

1. **Supersedable-vs-both-stand classification is verdict-critical** (no longer surfacing-quality):
   mis-marking a `measurement_period` attribute as `effective_period` lets the system *silently
   supersede* figures that must both-stand (the exact requirements_v3 violation). `claim_valid_kind` is
   governed (**start strict; default to `measurement_period`**), golden-gated on
   `eval_suite='contradiction'`, reviewable like a predicate promotion. **The single biggest risk.**
2. **Fiscal-calendar / value-normalization is now on the verdict path** — a FY≠CY or $5M-vs-$5MM error
   writes a *wrong believed window* (a false verdict returned as truth). Fail-safe: **normalize-or-
   refuse** → ambiguous values go to `contradiction_group`/unbelieved, never a confident `valid_from`.
   (The D42 §17 fiscal-calendar spike is promoted from surfacing-quality to verdict-correctness.)
3. **Scale unproven** — extend the §17 conflict-row sizing spike to the unified-table population; verify
   the planner uses the partial `WHERE object_kind='entity'` indexes through the `relations` view;
   load-test ATTACH bulk-COPY at 10⁸ before deleting the Parquet build path.
4. **Cardinality** — multi-valued literals (several office locations) need the registry
   `cardinality ∈ {single,set}` flag (single ⇒ value-excluded EXCLUDE = supersede; set ⇒ value-included
   = coexist). Ship with the literal arm, golden-tested.
5. **Decision-log blast radius** (D2/D3/D6/D7/D18/D41/D42 + D43). Each change simplifies, but the whole
   verdict is **conditional on the affirmed must-have being firm** — if temporal supersession of
   non-relational facts were withdrawn, D42 status quo is again the better answer.
6. **Deep literal history stays Postgres+Lance-only** (the in-graph property-projection option carries
   only the currently-believed scalar). 7. **A promotion seam** remains for supersedable literals that
   later earn an entity object — now a rarer, single-table, audited hand-off (no cross-table dual-write).

## 10. Reviewer round (Codex + Antigravity)

Both external reviewers re-read this synthesis + candidate D43. **Both returned "sound-with-fixes"**:
the core direction (unified `facts` + the `supersedable` gate + `relations` view + ATTACH-direct
projection) is confirmed sound, **not** over-built, D6-strengthening — and they independently flagged
the **same BLOCKER** plus a convergent set of DDL bugs, all now applied above:

- **BLOCKER (both):** the no-belief-axis guard `CHECK (supersedable OR (valid_until IS NULL AND …))`
  made a non-supersedable **measurement period** (FY2023 = a *closed* asserted interval)
  unrepresentable. **Fixed** → `CHECK (supersedable OR invalidated_at IS NULL)`; `valid_until` now
  legitimately stores the asserted period, and the no-winner guarantee is the (worker) "never re-cap"
  + the linter's "no single-value recipe" — not a NULL `valid_until`.
- **MAJOR — `supersedable` must include cardinality, mechanically (both).** **Fixed** → `supersedable`
  is now a `GENERATED ALWAYS` column `(entity OR (effective_period AND single))`, app-uneditable; a
  multi-valued (`set`) `effective_period` attribute (e.g. several office locations) is therefore *not*
  supersedable and coexists.
- **MAJOR — one static EXCLUDE can't toggle the key by cardinality (both).** **Fixed** → the literal
  arm split into two partial EXCLUDEs: single-valued supersedable (value *excluded* → supersede) and
  coexist (value *included* → both-stand/set coexist, exact-duplicates forbidden) — which also closes
  the duplicate-value hole for non-supersedable literals.
- **MAJOR — polymorphic CHECK leak (Codex).** **Fixed** → one exclusive-arc CHECK; an entity row can
  never carry literal columns and vice-versa.
- **MAJOR — missing amendments (both).** **Fixed** → §7 now lists **D4** (cascade on `fact_id`), **D5**
  (one `governed_relationships` vocabulary), **D8** (fact-label embeddings for literal facts).
- **MINOR — PG16 syntax (both).** **Fixed** → `(tstzrange(...))` parenthesised in every EXCLUDE; the
  generated `status` casts each branch `::relation_status`; the `$as_of` parameter normalized UTC-naïve.

`cardinality` is denormalized + locked onto `facts` from `governed_relationships` (an EXCLUDE cannot
join the registry). No reviewer found the design over-built or proposed a materially simpler one that
still delivers the affirmed must-have; both reaffirmed unified-`facts` over separate-tables (D6) and
over Postgres-only-graph (latency/contention). The residuals in §9 — chiefly the
**supersedable-vs-both-stand classification** and **value-normalization now being on the verdict
path** — remain the gating correctness work to clear before any implementation.

## References

Inputs: `external_agents/codex.md`, `external_agents/agy.md`, `internal_analysis.md`,
`ladybug_projection_findings.md`. Decisions: `decisions.md` D2, D3, D4, D6, D7, D8, D18, D21, D41, D42.
Designs: `postgres_schema_design.md` (§8, §9, §9.A, §17), `p2_graph_design.md` (§2, §5b, §9),
`nonrelational_facts_design.md`. Explainer: `concepts.md`. Requirement: `requirements_v3.md`.
Prior LadybugDB verification: `../ladybug_capabilities.md`.
