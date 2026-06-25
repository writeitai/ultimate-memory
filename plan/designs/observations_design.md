# The Observation Layer — Non-Graph Facts with Temporal Validity (Design)

How the system records and time-travels facts that are **about one entity but not links between two
entities** — a headcount, a balance, a fiscal revenue, a founding date, a status — *without* forcing
them into the typed graph and *without* a governed attribute vocabulary. Binding design for decision
**D43**. It sits beside the **relations** layer (D2–D5/D18, unchanged) and builds on D3 (supersession
over verdicts, never claims), D4 (the cheap-first blocking cascade), D6 (validity has one home), D8
(vectors live in Lance), D18 (the graph holds only entities), and D41 (claims carry an immutable
asserted-validity interval).

> **Reading this cold (CLAUDE.md Rule 1).** You need no prior context. A **claim** is an atomic,
> immutable, natural-language assertion *as a source made it* (the evidence record — never edited). A
> **relation** is a believed `(subject_entity → predicate → object_entity)` fact — the kind a graph can
> hold as an edge. An **observation** (this doc) is a believed fact whose object is a **value or
> statement about a single entity** ("Acme's headcount is 600"), *not* a link to another entity — so it
> is **not** a graph edge. **Bi-temporal** means two clocks: *valid-time* (when the fact held in the
> world — `valid_from`/`valid_until`) and *transaction-time* (when we believed it —
> `ingested_at`/`invalidated_at`). **Supersession** = a newer belief closing an older one's validity
> window. **Blocking** = cheaply narrowing to the handful of existing rows a new fact might conflict
> with, before spending any expensive comparison.

## 1. Two canonical layers, split by what a fact *is*

A document yields claims; normalization (E3) turns claims into the facts the system *believes*. Those
facts come in two shapes, and D43 keeps them in **two separate canonical tables** rather than one:

- **Relations** — both ends are entities: `(Alice) —works_for→ (Acme)`. Typed (governed predicate),
  because a graph needs typed edges. This is the **only** layer that projects to the graph (P2).
- **Observations** — the object is a *value or statement* about one entity: `(Acme) · headcount · 600`,
  `(Acme) · fiscal_revenue · $5M (FY2023)`. A value like `600` or `$5M` is not an entity and by D18 can
  never be a graph node — so observations are **not** graph edges and never enter P2.

Both carry the same bi-temporal windows and the same supersession machinery *in spirit*, so a changing
headcount time-travels exactly as a changing employment does. They differ in two ways that matter:

| | Relations | Observations |
|---|---|---|
| object | another **entity** | a **value/statement** about the subject |
| typed by | a **governed predicate** (registry) | **nothing** — no attribute vocabulary |
| supersession slot | `(subject, predicate, object)` exact key | the **resolved entity** (+ semantic narrowing) |
| projects to graph (P2)? | **yes** (D18) | **no** |
| projects to search (P1/Lance)? | yes (fact-label) | yes (observation label + optional value) |

**Why two tables, not one merged "facts" table.** A relation and an observation can never describe the
*same* belief (entity-object vs value-object are disjoint), so the D6 "one belief home" rule — which
exists to stop the *same* fact living in two places and drifting — is not at stake. Two simple,
disjoint layers beat one polymorphic table whose every row must carry both an entity-object arm and a
literal-object arm. (A unified typed table *was* designed and rejected — see §4.)

### Running example

- **Doc B** (a 2024 filing): *"Acme's headcount was 500 at year-end 2023; revenue was \$5M for FY2023."*
- **Doc C** (a 2025 report): *"Acme now employs around 600 people."*
- **Doc D** (a different 2024 source): *"Acme's FY2023 revenue was \$7M."*

E3 writes three observations on the entity **Acme**: headcount-500 (valid from 2023-12-31),
revenue-\$5M (FY2023), revenue-\$7M (FY2023); then Doc C adds headcount-600 (2025). We want:
*"headcount mid-2024?"* → **500**; *"headcount now?"* → **600**; *"FY2023 revenue?"* → **both \$5M and
\$7M, surfaced as a conflict** (never one silently chosen). That is exactly what the layer delivers.

## 2. What an observation is

An observation is a believed value/statement about **one resolved entity**, with bi-temporal validity
and evidence. The row is deliberately lean (full DDL: `postgres_schema_design.md` §9.A):

- `subject_entity_id` — the **anchor**, always a resolved canonical entity. This is the supersession
  blocking key.
- `statement` — the canonical natural-language form of the observed fact ("Acme's headcount is 600").
  This is what gets embedded in Lance for semantic narrowing and retrieval.
- `value` *(optional, best-effort)* — a structured/normalized value when one is cleanly extractable. It
  exists only to enable value-range queries and to *help* the adjudicator compare — **not required**,
  **not** validated against any registry, no `value_domain`/`cardinality` typing. To keep the common
  cases queryable without a governed vocabulary, the normalizer **recommends** (not enforces) a few JSON
  shapes: numeric `{amount, unit}`, money `{amount, currency}`, date `{date, precision}`, status
  `{state}`. Anything that doesn't fit stays in `statement` alone.
- `about_period` *(optional, raw)* + `about_period_range` *(optional, canonical)* — the
  **reporting/reference period the value describes** ("FY2023", "fiscal 2023", "year ended 2023-12-31"),
  kept **distinct from world-validity**. This resolves a real modelling trap: "Acme's FY2023 revenue was
  \$5M" does *not* stop being true on 2023-12-31 — the value is *about* FY2023 but the belief holds until
  restated. So `valid_from`/`valid_until` carry the **world-validity of the belief**, while `about_period`
  carries **what the value describes**. The raw label is matched via a best-effort canonical
  `about_period_range` (FY2023 → `[2023-01-01, 2024-01-01)`) so equivalent labels ("fiscal 2023", "year
  ended 2023-12-31") match and containment is explicit (Q1-2023 ⊂ FY2023). **`about_period` is one
  dimension of the conflict slot, not the whole slot** (see §3).
- `value_fingerprint` *(optional)* — a hash of (normalized value + `about_period_range`): a **candidate
  lookup aid only** for evidence-collapse. It is **never sufficient to merge** — different *properties*
  can share a value and a period — so the adjudicator must still confirm a positive same-property match
  before collapsing (see §3).
- the **bi-temporal** quartet (`valid_from`/`valid_until` = world-validity, `ingested_at`/`invalidated_at`
  = belief-time), a generated `status` mirror of `invalidated_at` (one validity home, D6),
  `evidence_count` (supporting evidence rows) / `contradict_count` (contradicting *evidence* rows — note
  this is distinct from *conflicting observations*, which are linked by `contradiction_group`),
  `confidence`, and `contradiction_group` (set when two observations conflict and both must stand).

There is **no governed attribute key, no `value_domain`, no `unit_dimension`, no `cardinality`, and no
typed exclusion constraint.** The only DB guards are FK-to-entity and basic temporal sanity. Everything
about *which observations are the same thing* and *whether a new one supersedes* is decided by the
adjudicator (§3), not the schema. (`status` reuses the existing `relation_status` enum — `active` /
`invalidated` — intentionally, as a common fact-status type shared with relations.)

## 3. Supersession by blocking + adjudication (the heart)

This reuses the exact pattern relations use for supersession (D4) — *block cheaply, then adjudicate the
small residue* — with one change: **block on the resolved entity, not on a typed predicate.**

When a claim asserts a value/property about entity *E*:

1. **Block (exact, exhaustive).** Fetch *E*'s **live** observations: `WHERE subject_entity_id = E AND
   invalidated_at IS NULL`. Indexed; most entities have few observations, so this is cheap and — this is
   the key property — **exhaustive for that entity**. Nothing about *E* can be missed.
2. **Narrow (only for hubs).** If *E* has many observations, rank them by **semantic similarity** to the
   new statement (P1/Lance over the observation label) to choose *which to compare first*. This is an
   ordering optimization, not a membership filter: the entity block already makes **all** of *E*'s live
   observations *available* (an exact key — no clustering can hide one). Crucially, because `supersede`
   requires a **positive** match (step 3), a prior that top-k ranking happens to skip yields at worst a
   *duplicate coexisting observation* to reconcile later — **never** a wrong supersede. (Contrast pure
   clustering, where a mis-clustered prior is invisible and silently duplicated.)
3. **Adjudicate (cheap-first cascade, D4).** For each candidate, decide:
   Every outcome below first requires a **positive same-property match** (the adjudicator confirming the
   new statement and the candidate are *about the same thing* — `value_fingerprint`/`about_period` only
   *narrow* candidates, they never decide it). Then:
   - **evidence** — same property, same value, overlapping validity → don't insert a row; add evidence to
     the existing observation and bump `evidence_count`. This collapse is **adjudicated (best-effort)** —
     the fingerprint surfaces likely exact dups; the same-property check confirms them.
   - **supersede** — same property, no reporting period (an *effective state*), value *changed* over time
     → **cap** the prior observation's `valid_until` at the new `valid_from` and insert the new one. The
     prior stays *true for its window* (`invalidated_at` stays NULL). (Headcount 500 → 600.)
   - **contradict / coexist** — same property **and** same canonical period (`about_period_range`),
     *incompatible* value → both stand, with a shared `contradiction_group`; the recipe surfaces both,
     the system never picks. (FY2023 *revenue* \$5M vs \$7M conflict; FY2023 *revenue* vs FY2023 *profit*
     do **not** — different property; FY2023 vs Q1-2023 do **not** — different period.)
   - **new** — a different property, period, or thing → insert independently, no interaction.
4. **Fail safe — a binding adjudicator contract (not just a hope).** This is the honest core of the
   untyped design: "never silently resolve" is **policy enforced in E3 + eval**, not a schema invariant.
   The binding rules:
   - A **`supersede`** (capping a prior `valid_until`) is permitted **only** against a *positively
     matched* prior whose adjudicator margin clears an explicit threshold, **and every cap writes an
     `observation_adjudications` reason row.** No silent caps.
   - Below threshold, or on any *incomplete* comparison, the outcome **must** be `coexist`/`new` —
     never `supersede`. Coexisting is always safe (both surfaced); a wrong-but-confident supersede is
     the one forbidden outcome, and these rules make the *failure mode* a duplicate, not an overwrite.
   - A **contradiction precision/recall eval gate** on the golden set is an **acceptance criterion** for
     shipping the adjudicator (this is the E2/E3 eval harness flagged as unowned in `questions.md` — it
     becomes load-bearing here).
   That contract — not the DDL — is how "contradictions are surfaced, never silently resolved"
   (requirements_v3) is honored without a typed schema gate. The design does not pretend the DB
   guarantees it.

### Worked examples

**Supersede — a changing headcount.**

| step | what happens |
|---|---|
| Doc B → "headcount 500 (year-end 2023)" | block on Acme: none match → insert **O1** (value 500, `about_period`=NULL — an *effective state*, `valid_from`=2023-12-31 normalized from "year-end 2023", open). |
| Doc C → "≈600" (2025) | block on Acme finds O1; positive same-slot match, later value, no period → **cap O1** (`valid_until` ≈ 2025-01, normalized from "now"/report date), insert **O2** (600, open). An `observation_adjudications` row records `outcome=supersede` with its reason. |
| query *"headcount mid-2024?"* | `subject=Acme ∧ semantic≈headcount ∧ valid_from ≤ t < valid_until ∧ invalidated_at IS NULL` → **O1 = 500**. |

(`valid_from`/`valid_until` are normalized from the source's temporal language — "year-end 2023", "as
of", "now" → the report date — via the claim's D41 asserted validity, not from ingestion time.)

**Both-stand — conflicting FY2023 revenue.** Doc B "revenue \$5M" and Doc D "revenue \$7M" each become an
observation with **`about_period='FY2023'`** (`about_period_range` `[2023-01-01, 2024-01-01)`) and an open
world-validity (the figure doesn't stop being true at year-end). The adjudicator matches them on
same-entity + **same property (revenue, positive match)** + **same `about_period_range`** + incompatible
value → **contradiction**: both kept, shared `contradiction_group`; the recipe returns both. No typed
`measurement_period`/`cardinality` flag was needed. Correctly **not** a conflict: FY2023 *revenue* vs
FY2023 *profit* (different property), or FY2023 vs Q1-2023 revenue (different period) — both coexist.

**No recall hole.** Suppose Acme has 40 observations. A new headcount claim blocks on Acme (all 40 found,
exact), then semantic-ranks to compare against the existing *headcount* one first. Even if the semantic
rank were poor, the prior headcount is still *in the candidate set* (the entity block is exhaustive) — at
worst the adjudicator spends a bit more. Contrast a pure semantic-cluster approach, where a mis-clustered
prior headcount would be **invisible** and silently duplicated. Anchoring to the resolved entity is what
buys this.

## 4. Why no typing (the honest rationale)

A fuller design — a **unified, typed `facts` table** with a governed attribute vocabulary
(`value_domain`, `unit_dimension`, `cardinality`) and DB-enforced, schema-gated literal supersession —
was designed and **rejected** (preserved in a closed PR, not on main). The reasons, plainly:

- **The attribute space is not enumerable.** Trying to register every property a source might assert
  about an entity fragments exactly like free-text predicates would, and forces extra LLM typing calls
  whose output is brittle.
- **The typing existed only to make literal supersession *schema-enforced*.** If supersession is
  *adjudicated* (as relations always have been), none of `value_domain`/`unit_dimension`/`cardinality`
  is needed — the adjudicator decides value-equality and supersede-vs-coexist at comparison time, on the
  same LLM call it already makes.
- **Merging graph and non-graph facts under one polymorphic table** is a heavy mental model (an
  entity-object arm XOR a literal-object arm, multiple exclusion constraints, registry-locking triggers)
  for no truth-level benefit, since the two are disjoint (§1).

What we give up by going untyped is real and named in §7: value-equality and supersede-vs-coexist become
**adjudicator judgments + an eval gate**, not schema invariants. For a *memory* system (not a financial
ledger), dexterity and a simple mental model are worth that trade — and the fail-safe-to-coexist default
keeps the one hard guarantee intact.

## 5. Retrieval — through the projections

Observations are **storage**; queries go through projections (D9), exactly like everything else:

- **P1 / Lance** — each observation's `statement`/label is embedded for **semantic + value search**:
  *"what has Acme's headcount been over time?"* resolves Acme, pulls its observations, orders by
  `valid_from`. The optional structured `value` supports value-range filters.
- **P2 / graph** — observations are **never** projected (a value is not a node — D18). Only relations
  reach the graph.
- **as-of** — the same bi-temporal filter as relations: valid-time (`valid_from ≤ t < valid_until`) for
  "what was true at T", transaction-time (`ingested_at ≤ t < COALESCE(invalidated_at, ∞)`) for "what did
  we believe at T". A **period** query ("FY2023 revenue?") filters on `about_period`, not valid-time —
  it asks for the value *describing* that period, which both `contradiction_group` members satisfy (both
  surfaced).

The one cost of untyped storage shows up here: a query for a *specific* property is **semantic**
(label/value match), not an exact typed-key lookup. That is precisely what P1/Lance is built for, and
the optional `value` makes the common numeric cases exact.

## 6. Schema essentials

Full DDL in `postgres_schema_design.md` §9.A. Three tables, mirroring the relations trio but leaner:

- **`observations`** — the row in §2; entity-anchored, bi-temporal, generated `status`, optional `value`,
  `contradiction_group`; FK to `entities` + temporal CHECKs; **no typed EXCLUDE, no attribute FK.**
- **`observation_evidence`** — many-to-many join to claims (`HASH(observation_id)`, PK
  `(observation_id, claim_id)` = evidence-once); where corpus redundancy collapses into `evidence_count`.
- **`observation_adjudications`** — the append-only "why" transcript (supersede / contradict / merge),
  by cascade rung, so the non-deterministic adjudication is replayable on rebuild (D7).

## 7. Consequences, residuals, and what to measure

**Invariants preserved:** claims immutable (D2/D3); the graph holds only entities (D18 — observations
never project); validity has one home per fact (D6 — `status` is generated; relations and observations
are disjoint so they cannot drift); asserted-validity feeds but never overrides the believed window
(D41).

**Residuals — measure before locking (thresholds are starting points, not constants):**
1. **Supersede-vs-coexist is an adjudicator judgment, not a schema gate.** A confident-but-wrong
   `supersede` could silently resolve a conflict that should both-stand — the design does **not** pretend
   the DB prevents this. The safeguard is the **binding adjudicator contract of §3.4** (supersede only on
   a positively-matched prior above an explicit margin, with a persisted reason; else coexist) plus a
   contradiction **precision/recall eval gate** that is an **acceptance criterion** for shipping the
   adjudicator (the E2/E3 eval harness — `questions.md` flags it as unowned; this design makes it
   load-bearing and gives it an owner). This is the single biggest correctness risk and the price of
   dropping the typed gate; it fails toward *duplicate coexisting rows*, never silent overwrite.
2. **Adjudication cost.** Each value-claim does an entity block (cheap, indexed) + occasional semantic
   narrowing + an adjudication call — comparable to relation supersession. Load-test the per-write cost
   and the hub-entity tail (entities with many observations) at corpus scale.
3. **Specific-property retrieval is semantic, not exact-key.** Measure recall of "what is *E*'s
   `<property>`?" via the label/value match; tune how aggressively the normalizer fills the optional
   structured `value` for the common numeric/date cases.
4. **Observation volume vs. relations.** Size `observations`/`observation_evidence` against full
   extraction; decide partitioning by the same logic as `relation_evidence` (`HASH` by id).

**Out of scope (documented non-goals, not deferrals):** observations do **not** carry a governed
attribute vocabulary or schema-enforced supersession; they never enter the graph; **qualitative/opinion
belief** (e.g. sentiment that shifts over time) is a *separate, upstream* question — pure opinion is
dropped at E2 Selection (D31/D34) before it becomes a claim at all, so it is neither a relation nor an
observation today; whether to retain it is tracked in `questions.md`, not resolved here.

## References

Decision: `decisions.md` D43 (and D2, D3, D4, D5, D6, D8, D18, D41). Schema:
`postgres_schema_design.md` §9.A (`observations`/`observation_evidence`/`observation_adjudications`).
Normalization: `e2_e3_claims_relations_design.md` §5. Explainer: `plan/analysis/concepts.md`. Open
items (qualitative/opinion belief; the E2/E3 eval harness): `questions.md`.
