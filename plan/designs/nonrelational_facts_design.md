# Non-Relational Facts — Attribute Conflicts (Design)

How the system **detects, groups, and surfaces** disagreements between sources about facts that
never become graph relations — *without* inventing a second place that decides what is "currently
true." Binding design for decision **D42**, building on **D41** (claims carry an immutable
source-asserted validity interval), D2/D3/D6/D18 (the claim/relation split and its invariants), D5
(governed vocabulary), and D24 (cluster review). Full research + the rejected alternatives:
`plan/analysis/nonrelational_conflict_research/` (Codex + a 5-angle internal workflow + SYNTHESIS).

> **Read this cold (CLAUDE.md Rule 1).** You do not need prior context. §1 explains the gap with a
> worked example; §2 the one idea that makes the design safe; §3–§8 the mechanism. Two terms recur:
> a **relation** is a graph fact `(subject_entity, predicate, object_entity)` — both ends are
> entities (D18 keeps literals and dates off relations); a **claim** is an immutable
> natural-language assertion a source made (the evidence record). A claim can yield a relation, or
> none.

## 1. The gap, with an example

By design (D2), **many claims yield no relation** — there is no two-entity `(subject, predicate,
object)` to extract. Three common shapes:

- **single-entity attribute:** *"Acme was founded in 1998."*
- **literal / quantity object:** *"Acme's FY2023 revenue was $5M."* ("$5M" is a quantity, not an
  entity; D18 forbids making it one.)
- **n-ary:** *"Acme sold 40,000 units in Germany in Q4 through reseller X."*

D41 already gave each such claim an **immutable, source-asserted validity interval**
(`claim_valid_from`/`claim_valid_until` + precision + kind), so *"FY2023 revenue was $5M"* is now
**time-filterable as evidence** — you can ask "what did sources assert about Acme over 2023?" and get
it. What D41 did **not** give it is a **fact-identity**: a stable handle under which two claims are
recognized as being *about the same thing*. Relations get this for free — E3 manufactures
`(subject_entity, predicate, object_entity)` and indexes it, so two claims about the same fact meet
on that key and the system can attach a `contradiction_group`. Non-relational claims have only their
text plus a per-`claim_id` interval, which D41 itself says is *"never addressable as the validity of
fact F."* So:

> Source A (2024 filing): *"Acme's FY2023 revenue was $5M."*
> Source B (analyst note): *"Acme's FY2023 revenue was $7M."*

Both survive extraction, both are time-aligned to FY2023, and **nothing groups or flags them as
conflicting.** A `claims_as_of` search returns one or both as separate hits; an agent can read the
top hit as "the answer" and never learn the other side exists. That violates the standing
requirement **"contradictions are surfaced, never silently resolved."** Three flavors of the gap:

1. **value disagreement, same period** — $5M vs $7M for FY2023;
2. **attribute disagreement** — "founded 1998" vs "founded 1999";
3. **temporal restatement** — "$5M" (reported 2024) → "$5.2M" (reported 2025) for the same FY2023, a
   later source *correcting* an earlier figure.

This is distinct from *relational* contradiction, which is already handled on relations
(`contradiction_group`, `concepts.md` §4). This design covers only the **non-relational** case.

## 2. The one idea: detect & surface, never resolve

The design is a **conflict *index***, not a second fact-deciding layer. It **groups** conflicting
non-relational evidence and **describes** the disagreement so retrieval can show all sides; it
**never** picks a winner, closes a validity window, or stores a "current value." Concretely it has
three parts (detailed in §3–§5):

1. a governed **`attributes` registry** — the vocabulary of measurable/attributable properties
   (`fiscal_revenue`, `founded_date`, `headcount`, …), a *peer* of the predicate registry;
2. a derived, **no-belief-axis** grouping projection **`claim_attribute_facts`** (+ an
   `attribute_evidence` join), keyed by `(subject_entity, attribute, world-time bucket)`, that
   collects the claims occupying one "fact slot" and computes a deterministic **`conflict_state`**;
3. **retrieval recipes + a linter rule** that surface all sides and *forbid* the API from returning
   a single value for a non-relational fact.

### Why this does not become a second "source of truth for validity" (D6)

This is the crux, and it requires an honest admission. D41 argued claim-validity is *not* a second
belief authority via **three** mechanical properties: it is **immutable**, **many-valued per fact**
(N sources → N windows, all stand), and has **no fact-identity**. This design **deliberately
manufactures a fact-identity** — the grouping key `(subject_entity, attribute, bucket)` — because
*without* it there is no handle under which "$5M" and "$7M" can ever meet; the gap *is* the absence
of that key. So D41's three-pillar proof **reduces to two pillars for non-relational facts:
immutable + no-belief-axis.**

The remaining safety argument: a grouping handle that can only answer *"which claims occupy fact
slot F"* — never *"the value of F"* — cannot be current belief. **The no-belief-axis therefore
becomes the *sole* structural guarantee of D6 for non-relational facts, and it is enforced
mechanically, not by convention** (§4): the projection has no winner pointer, no `valid_until`, no
`status`, no supersede outcome, and a CI schema-test + the recipe linter forbid ever adding one. The
*only* place a non-relational fact can acquire an adjudicated current value is by **promotion to a
relation** (§6), where the one existing belief authority handles it.

## 3. Detection

### 3.1 A governed attribute vocabulary (why free text fails)

To decide that two claims are about *the same attribute*, the system needs a **governed name** for
that attribute. This is an ontology question, not a string match: `revenue` / `net revenue` /
`sales` / `ARR` may be the same measure or four different ones depending on the deployment; `founded`
/ `incorporated` / `launched` are usually distinct. Free-text attribute keys would fragment exactly
as free-text predicates do (D5: `works_at` / `employed_by` silently break blocking) — and here the
failure is **silent**: ungoverned keys never co-block, so real conflicts are simply *never detected*.
That is the catastrophic-because-silent class the whole system is built to avoid.

So detection requires an **`attributes` registry**, a peer of the predicate registry, reusing D5
governance wholesale (synonyms, tiers `core | extension | other | deprecated`, the `other:<freetext>`
escape, a periodic promotion job, a `usage_count`). It differs from predicates in one principled
way: a **predicate** relates two *entities* (D18 bars literal objects), while an **attribute**
attaches a *literal/quantity* to **one** entity — precisely the literal-range home D18 keeps off
predicates. Each attribute declares a typed **`value_domain`** (`money | date | quantity | count |
ratio | string_enum | boolean`) that drives **deterministic value normalization**, so "$5M" and
"5,000,000 USD" are recognized as the *same* value (not a phantom conflict). The seed core is small
(D5 strict-first): e.g. `founded_date`, `fiscal_revenue`, `headcount`, `valuation`, `price`,
`launch_date`, `status` — the exact list is less important than the rule that extraction may not
invent ungoverned blocking keys. Full table: `postgres_schema_design.md` §3; promotion funnel:
`registries_design.md`.

### 3.2 The grouping key

The block key — the fact-identity from §2 — is:

```
(deployment_id, subject_entity_id, attribute_key, valid_bucket)
```

- **`subject_entity_id`** reuses the existing entity registry + T0–T4 resolution cascade (D17). No
  new entity resolution is built; without a canonical subject, "Acme Inc." / "ACME" / "Acme Corp"
  would form separate blocks and conflicts would vanish.
- **`attribute_key`** is the governed token from §3.1.
- **`valid_bucket`** is derived from D41's **normalized** `[claim_valid_from, claim_valid_until]`
  window at its `claim_valid_precision`, compared with the `tstzrange &&` overlap operator (the same
  operator the relations bi-temporal constraint uses). **Hard rule: bucket on the normalized window,
  never on the label string** — "FY2023" ≠ calendar 2023 for off-calendar fiscal years, so bucketing
  on the string would both fabricate conflicts and miss real ones.

The key is **computed as a derived projection over immutable claims; it is never stored back on the
claim** (storing it on the claim would make the claim itself addressable as "fact F" and re-violate
D41's no-fact-identity property at the evidence grain).

The key shape depends on the attribute's *time semantics* (its `claim_valid_kind`):
- **measurement-period** attributes (revenue) block on the normalized period, so "$5M FY2023" and
  "$7M FY2023" meet;
- **event-time** attributes (founding date) block **without** the date in the key (the date is the
  *value*, not the period), so "founded 1998" and "founded 1999" meet even though their intervals do
  not overlap — if the date were in the key the conflict would be missed;
- **state / effective-period** attributes block on overlapping validity windows.

**Qualifiers are part of identity.** "Global revenue" vs "US revenue", or "revenue under IFRS" vs
"under GAAP", are *not* conflicts; the attribute registry declares which qualifiers are
identity-bearing, and a missing qualifier yields a *possible* (not confirmed) conflict.

### 3.3 Conflict vs. compatible refinement (deterministic, cheap-first)

Inside a block, detection is aggregate-first and deterministic — **no LLM** (the "which value is
right?" judgment is exactly what this layer refuses to make). It normalizes values to typed
ranges/classes and assigns a `conflict_state`:

- **disjoint buckets** → a time *series*, not a conflict (filtered out for free by the `&&` test);
- **same normalized value** (within the attribute's tolerance) → **corroboration** (more evidence,
  no conflict);
- **precision subsumption** — "founded 1998" vs "founded March 1998" (the fine value lies inside the
  coarse one) → **compatible refinement**, not a conflict;
- **overlapping bucket + incompatible value** → **`value_disagreement`** (the genuine conflict);
- **same bucket + incompatible value + different `asserted_at`** → **`restatement`** (a source
  correcting itself over time — see §7);
- **non-normalizable value** → **`indeterminate`** — *fail-safe toward surfacing*: when in doubt,
  flag a possible conflict rather than assert false agreement.

### 3.4 When detection runs

- **At E3 write time**, as a sibling branch to relation normalization, on the *zero-relation
  residue* (the claims D2 routes to nothing). The lookup is bounded by the `(subject, attribute,
  bucket)` block — cost scales with ambiguity, not corpus size. This is the same "claim → structured
  fact" move E3 already makes, for the arity-1 / literal-object case. It is **not** a query-time or
  rebuild-time `GROUP BY` over the ~5×10⁷ `claims` table (that would force a full-table aggregation
  or a btree on the hot partitioned claims table — the value-gate self-defeat D25 warns against).
- **Periodic / event-driven backfills** recompute affected blocks after entity merges/un-merges
  (D21), attribute promotions, fiscal-calendar fixes, or normalizer-version changes — all of which
  can move claims between blocks.
- **Query-time** only as a *presentation safeguard* (attach known conflict siblings); never the
  primary detector (no corpus scan, no LLM on the hot path — D9).

**Honest recall limit.** Detection fires only when extraction tagged a *registered* attribute, the
subject *resolved*, and the value *normalized* — three serial steps, each with a silent-miss mode. An
untagged or fragmented attribute is invisible, exactly as today. This is a **coverage expansion**
(relational + the governed single-subject-attribute subset), **not** full coverage; §9 records the
residual, and the system must never report governed-subset coverage as complete.

## 4. Tracking — a derived projection with no belief axis

Detection materializes two objects (DDL: `postgres_schema_design.md`):

- **`claim_attribute_facts`** — one row per `(deployment_id, subject_entity_id, attribute_key,
  valid_bucket, normalized_value cluster)`, carrying the `conflict_state`, a shared `conflict_group`
  uuid when ≥2 incompatible value clusters share a slot, `asserted_at` extremes, and detector
  version. It is the **fourth derived projection of claims** — alongside relations (E3 truth), the
  Lance vector index (P1), and the graph (P2) — **rebuildable from immutable claims + the attribute
  registry, holding no source of truth** (D7).
- **`attribute_evidence(attr_fact_id, claim_id, stance)`** — the many-to-many join back to the
  asserting claims, mirroring `relation_evidence` (HASH-partitioned by `attr_fact_id`, evidence-once
  PK).

**The load-bearing invariant — the sole structural guarantee of D6 here:** `claim_attribute_facts`
has **no belief axis**. No `believed_claim_id`/winner pointer, no `valid_until`/`invalidated_at`/
`status`, no supersede outcome. It groups and describes; it never resolves. This is enforced
**mechanically**, not by convention:

- a **CI schema-test** asserts the table never gains a winner/value-verdict/validity column;
- the **recipe linter** bars any recipe over it from returning a single value or implying a winner.

(A `believed_claim_id` would invert D41's many-valued property and create a second current-belief
home that drifts against a relation once the fact is promoted — the documented Mem0 desync class D6
forbids. That is why it is structurally prohibited, not merely discouraged.)

## 5. Query-system reaction

- **`claims_as_of(t)` is unchanged** — still evidence-grain ("what did sources assert held over T"),
  still barred by the linter from answering "currently true." The win is that it is no longer the
  *only* surface, and each returned claim now carries its `conflict_group` id inline (joined via
  `attribute_evidence`), so an agent is **told** "this asserted value has competitors."
- **New `attribute_conflicts(subject, attribute_key?, as_of?)`** returns conflict groups directly
  over the small projection — "where do sources disagree about Acme's attributes?" becomes a
  structured, zero-LLM lookup instead of an agent eyeballing a claim dump.
- **New `attribute_value_as_of(subject, attribute_key, t)`** returns the **set** of asserted values
  valid at `t` *with* their conflict status — never a single value.
- **The linter rule (the API analogue of D6):** these recipes may not return "the value" or imply a
  winner. For a current-truth question about a non-relational attribute the API answers, machine-
  readably: *no adjudicated value; N conflicting assertions; here is the conflict group; promote to a
  relation to track a believed value.* Result rows expose `result_grain = claim_evidence`,
  `current_belief = false`, `conflict_state`, `conflict_group`, per-claim `source` + `asserted_at` +
  world-time + value + a clearly-labelled `source_weight` (a *ranking hint*, never a verdict).
- **Presentation may rank** by recency / source authority / evidence count, and may *say* "newer
  source", "amended report", "more supporting claims" — but must **never** say "winner",
  "superseded", "current value", or "true as of" unless the answer comes from a relation, a K3
  belief, or a (future) promoted fact.

## 6. Handling, review, and promotion

- **Surface-all, never pick-winner** — forced by both the requirement and D3/D6. Detection emits a
  `conflict_group` and stops.
- **Review (D24).** High-impact conflicts (heavily-evidenced subject, or an active K2 scope) route
  to the existing cluster-review queue under a dedicated **`review_item_kind = 'attribute_conflict'`**
  (distinct from the relational `'contradiction'`, so the constraint is cleanly keyable). The review
  verdicts are **`both_stand`**, a **new `promote_to_relation`**, or the non-resolving **`uncertain`**
  ("can't tell" — leaves the conflict standing) — `pick_a`/`pick_b` are *illegal*
  for an attribute conflict (a human "pick" would write a claim-side current-value verdict, the
  forbidden second authority), enforced by a CHECK. Review means "confirm these are the same
  measure and genuinely conflict" or "this attribute deserves a relation home", **never** "pick the
  true value."
- **Promotion to a relation** is the *only* path to an adjudicated current value. When a
  non-relational fact's object is genuinely a domain entity (a `LaunchEvent`, a `FundingRound`, a
  named report), it is promoted via the D5 `other:`/predicate funnel and becomes a relation, gaining
  the full bi-temporal window + `contradiction_group` + supersession in the one existing authority.
  A **pure-literal** attribute (a scalar like revenue, with no entity to manufacture) **stays
  surfaced-only forever** — that is the correct terminal state (§9). The promotion signal is the
  attribute's `usage_count` + conflict hit-rate per `(subject, attribute)`, mirroring the predicate
  promotion funnel.

## 7. Temporal restatement

A *restatement* is a source **correcting itself over time** — "$5M" (reported 2024) → "$5.2M"
(reported 2025) for the **same** FY2023. It lives in the **same** `conflict_group` as an ordinary
disagreement, distinguished only by `conflict_state = 'restatement'` and surfaced as an
**`asserted_at`-ordered presentation hint** (newest-asserted first). The discriminator from a
two-source `value_disagreement` is exactly: *same bucket + distinct value + different `asserted_at`*.
This is precisely why D41 split `asserted_at` (the assertion *event* time) from `claim_valid_*` (the
source-asserted *world* time): restatement is detectable because those two clocks are separate.

Restatement is **not** supersession. Supersession closes a *relation's* validity window over world-
time (D3); restatement is assertion-time self-correction over a fact that has no relation window to
close. **Both values are kept forever** as immutable evidence (D41). *"The 2025 figure is the more
current testimony"* is true and surfaced as an ordering hint; *"$5.2M is the believed value"* is
**not** a system verdict — it is at most an agent read-time policy or an offline K3 narrative. The
third clock (system belief evolving for a pure-literal fact) genuinely has **no home**, and that is
correct: a fact that needs a believed, evolving value must earn a relation (§6).

## 8. K-plane interaction

K is the **consumer and narrator**, never the structured verdict home. A new/changed
`conflict_group` enqueues a K refresh (D12); K3 — which already links *supporting and contradicting*
evidence (`knowledge_artifact_evidence`) and compiles **offline** (debounced) — narrates the
conflict with citations:

> *Acme's FY2023 revenue is reported inconsistently: $5M in the 2024 annual report; $5.2M in a 2025
> amended report that appears to restate it. Treat $5.2M as the working value when one is required;
> retain $5M as contradictory evidence.*

That is a compiled, cited, qualified **belief artifact** — not a claim edit, not a relation window,
not a structured per-fact verdict on the read path. K3 may *choose* a working value (by recency,
authority, explicit restatement language, or human review) but must cite both sides; the system never
buries that choice inside retrieval ranking.

## 9. Overall consequences & residual non-goals

**Invariants.** D2 intact (the projection has literal values, no predicate, no entity-entity edge —
not a covert relation); D3 intact (no claim supersession, no second supersession engine, no window
closed); D18 intact (literals never enter relations; they are *grouped* by an attribute-key string).
**D6 is preserved under the reduced two-pillar proof** (§2), enforced mechanically.

**Cost.** A genuine new governance surface — a second registry to seed/tune/promote, **plus** value
normalization (money/date/unit/fiscal-calendar) predicates never needed. Mitigated by start-strict +
`other:` escape + the fact that quantities/dates are already D35 protected classes. It inherits both
unsolved-at-scale dependencies (D17 resolution quality, D5-style vocabulary stability) and adds the
fiscal-calendar spike. Scale is acceptable **only** with E3 write-time materialization on the
`(subject, attribute, bucket)` block; conflict rows are exactly the ones the "distinct facts not
assertions" collapse does *not* shrink, so the conflict subset is larger than a naive cell count — a
load-test spike (`postgres_schema_design.md` §17).

**Residual non-goals (narrowed, not closed):**
1. **Untagged / unregistered / fragmented attributes** — silently undetected, as today (recall is the
   serial product of three LLM-tagging steps).
2. **Mis-normalized values reading as false agreement** — the dangerous silent direction; mitigated by
   failing to `indeterminate` on non-normalizable input, but the false-equate case (off-calendar
   fiscal years, "$5M" vs "$5MM" vs "$5bn") is real and load-bearing for the fiscal-calendar spike.
3. **Irreducible n-ary facts** — no clean `(subject, attribute)` key; surfaced-only at claim grain via
   semantic co-retrieval.
4. **No believed current value for a pure-literal fact — by design.** The system never asserts "Acme's
   FY2023 revenue *is* $5M" unless the fact earns a relation (§6). A conflicting pure-literal attribute
   stays surfaced-only forever; a consumer wanting one number gets "N conflicting assertions, no
   adjudicated value." That is the requirement working as intended, but a real residual for any
   consumer expecting a scalar answer.

## 10. Decisions & spikes

**Decision:** **D42** (this layer). Foundations: D2, D3, D5, D6, D18, D24, **D41**. D42 also
**refines D41's reasoning** (its no-second-home proof drops from three pillars to two) and the **D6**
note (the no-belief-axis is the structural guard for the non-relational case).

**Spikes (measure before locking — numbers are starting points):**
1. **Conflict-row sizing** — load-test the conflict subset of `claim_attribute_facts` + the
   `attribute_evidence` volume on a corpus slice (the naive distinct-cell count under-estimates).
2. **Attribute-vocabulary fragmentation** — P/R + canaries on the existing `eval_suite='contradiction'`
   for whether `revenue`/`net revenue`/`sales` co-register correctly.
3. **Value normalization incl. fiscal calendars** — correctness of money/date/unit normalization and
   FY≠CY bucketing (the silent false-agreement risk).
4. **Precision-subsumption edge cases** — golden coverage for refinement-vs-conflict on dates/quantities.

## References

Research: `plan/analysis/nonrelational_conflict_research/` (`external_agents/codex.md`,
`internal_analysis.md`, `SYNTHESIS.md`). Decisions: `decisions.md` (D42 + D2, D3, D5, D6, D18, D24,
D41). Schema: `postgres_schema_design.md` (§3 `attributes` registry, §9 `claim_attribute_facts` +
`attribute_evidence`, §15 non-goal, §17 spikes). Adjacent designs: `e2_e3_claims_relations_design.md`
(E3 normalization + the attribute sibling branch), `registries_design.md` (attribute promotion
funnel). Explainer: `concepts.md` (§4 relational contradiction, §6 blocking). Requirement:
`requirements/requirements_v3.md` ("contradictions are surfaced, never silently resolved", extended
to the non-relational case).
