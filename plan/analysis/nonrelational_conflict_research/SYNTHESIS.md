# SYNTHESIS — handling conflicts between non-relational claims

Consolidates two independent analyses of the residual gap D41 documented: an external **Codex**
analysis (`external_agents/codex.md`) and an internal **5-angle design workflow**
(`internal_analysis.md`, with adversarial critiques). They converge strongly; where they differ,
the internal workflow is sharper on scale and on the one hard intellectual consequence. This is
*analysis* — it **recommends** a decision (a proposed **D42**) and the doc edits to realize it, but
logs nothing binding. Numbers are starting points (CLAUDE.md Rule 2); written for a cold reader
(Rule 1).

## 1. The gap, precisely

By design, many claims yield **no relation** (D2): single-entity / attribute facts ("Acme was
founded in 1998"), literal- or quantity-object facts ("Acme's FY2023 revenue was $5M"), and n-ary
facts (D18 keeps literals and dates off relations). **D41** gave each claim an immutable,
source-asserted validity *interval*, so such a fact is now time-**filterable** as evidence
(`claims_as_of`). What D41 did **not** give it is a **fact-identity** — a stable handle under which
two claims are "about the same thing." So two sources asserting incompatible content for the same
entity + attribute + world-time have nothing to group or flag them: `claims_as_of` returns both,
silently, side by side. Three flavors:

- **value disagreement, same period:** "$5M" vs "$7M" for FY2023;
- **attribute disagreement:** "founded 1998" vs "founded 1999";
- **temporal restatement:** "$5M" (reported 2024) → "$5.2M" (reported 2025) for the same FY2023.

This is distinct from *relational* contradiction, which the system already handles
(`relations.contradiction_group`, concepts §4). The gap is specifically the non-relational case, and
it matters because of the standing requirement: **"contradictions are surfaced, never silently
resolved"** (requirements_v3).

## 2. The converged answer — *detect + surface, never resolve*

Both analyses reject a second adjudicated fact layer as the base design and land on the same shape:
**a lightweight, governed conflict *index* that groups and describes incompatible non-relational
evidence but never picks a winner, closes a window, or stores a believed value.** Three parts:

1. **API / recipe-linter floor (zero schema — the requirement-bearing core).** The recipe linter
   (which already bars `claims_as_of` from "currently true") gains a rule: no claims-plane recipe
   that can return a non-relational fact may expose a single-winner accessor. "Is X currently V?"
   routes to a relation recipe; with no relation, the API returns *"no adjudicated value; N
   conflicting assertions; promote-to-relation to track."* This alone closes the real harm — an
   agent reading top-1 as the answer.
2. **A governed `attributes` registry — a peer of `predicates`.** Detecting "is this the same
   attribute?" is an ontology question (`revenue` vs `net revenue` vs `sales`); free-text keys would
   fragment exactly as free-text predicates do (D5) and **silently miss** conflicts — the
   catastrophic-because-silent class. The registry reuses D5 governance wholesale (synonyms, tiers,
   `other:` escape, promotion job, `usage_count`) and adds a **typed `value_domain`**
   (money/date/quantity/count/ratio/enum/bool) that drives **deterministic value normalization** (so
   "$5M" and "5,000,000 USD" do not read as a conflict). It is a genuine peer, not a reuse: a
   predicate relates two **entities**; an attribute attaches a **literal/quantity to one entity** —
   precisely the literal-range home D18 deliberately keeps off predicates. Seed core small (D5
   strict-first).
3. **A derived, non-authoritative grouping projection.** `claim_attribute_facts`, keyed
   `(deployment_id, subject_entity_id, attribute_key, valid_bucket)`, with an
   `attribute_evidence(attr_fact_id, claim_id, stance)` join (mirroring `relation_evidence`), member
   claims, `normalized_value`, `asserted_at`, and a **deterministically-computed** `conflict_state ∈
   {single, corroborated, value_disagreement, restatement, refinement, indeterminate}`. It is the
   **fourth derived projection of claims** (alongside relations, P1 vectors, P2 graph): rebuildable
   (D7), holds no source-of-truth. **Hard structural constraint — its sole reason to be safe:** no
   `believed_claim_id`, no winner, no `valid_until`/`invalidated_at`/`status`, no supersede outcome.
   It **groups and describes; it never resolves.**

### Where the two analyses agree, and the one sharpening

They agree on every load-bearing point: governed attribute vocabulary is mandatory; entity
resolution is reused (D17), not rebuilt; the index is evidence/grouping, never belief; temporal
restatement is an annotation, not supersession; K3 narrates; promote-to-relation is the only path to
a believed value; reject claim supersession, hidden winners, and Date/Money nodes.

The internal workflow sharpens two things Codex left softer:

- **Scale / where detection runs.** Materialize the grouping at **E3 write time** on the `(subject,
  slot)` block (cost scales with ambiguity, not volume), **not** as a query-time or rebuild `GROUP
  BY` over the ~5×10⁷ partitioned `claims` table — which would force a D23-forbidden btree or a
  full-table aggregation (the value-gate self-defeat of D25). `attribute_evidence` follows the
  `relation_evidence` pattern (HASH by `attr_fact_id`, evidence-once).
- **The honest cost to D6 (below).** It names the proof-reduction explicitly rather than asserting
  "no invariant changes."

## 3. The four sub-problems, answered

- **Detect.** Block key `(deployment_id, subject_entity_id, attribute_key, valid_bucket)` — derived
  over immutable claims, **never stored back on the claim**. `valid_bucket` is computed on the
  D41-normalized `[start,end]` window (`tstzrange &&`), **never on the label string** (off-calendar
  FY≠CY would otherwise fabricate and miss conflicts — a hard construction rule). Conflict vs.
  compatible-refinement is deterministic, cheap-first (D4-shaped): disjoint bucket → time series
  (free); equal value within tolerance → corroboration; precision subsumption ("1998" ⊃ "March
  1998") → refinement; overlapping bucket + incompatible value → `value_disagreement`;
  non-normalizable → `indeterminate` (**fail-safe toward surfacing**). No LLM on the residue.
- **Track.** The derived projection + the governed registry. Reject literal-on-relation (D18) and
  any winner-bearing table. The **no-belief-axis must be enforced mechanically** — a CI schema-test
  forbidding any winner/value/validity column, plus the recipe-linter bar — because it is the *sole*
  remaining structural guarantee of D6 once a fact-identity exists (it cannot be a convention a
  future contributor quietly violates).
- **Handle.** Surface-all, never pick-winner. Detection emits a `conflict_group` and stops. High-
  impact conflicts route to the **existing D24 review queue** (`review_item_kind='contradiction'`,
  currently unwired) — but with a **new `promote_to_relation` verdict** and a CHECK that
  `pick_a`/`pick_b` are illegal for an attribute conflict (a human "pick" would write a claim-side
  verdict = the forbidden second authority). Review means "confirm same measure / genuine conflict"
  or "this deserves a relation home," never "pick the true value."
- **Query.** `claims_as_of` unchanged (evidence-only). New `attribute_conflicts(subject,
  attribute_key?, as_of?)` and `attribute_value_as_of(...)` return **all** asserted values + their
  conflict grouping, never a single value (linter-enforced — the API analogue of D6); conflicting
  claims carry their `conflict_group` id inline. Zero query-path LLM; `conflict_state` precomputed at
  E3.
- **K-plane.** K is the **consumer/narrator**, never the structured verdict home. A conflict group
  triggers K refresh (D12); K3 compiles cited belief-with-contradiction prose via
  `knowledge_artifact_evidence` ("$5M per the 2024 filing; $5.2M per the 2025 restatement; treat
  $5.2M as the working value"). It never invents a value the structured layer refused to assert.
- **Temporal restatement.** Same `conflict_group`, `conflict_state='restatement'`, surfaced as an
  `asserted_at`-ordered hint — *not* a relation `valid_until` closure, *not* a stored verdict. The
  discriminator from a two-source disagreement is **same bucket + distinct value + different
  `asserted_at`**. This is exactly why D41 split `asserted_at` (assertion event) from `claim_valid_*`
  (world-time). Both values stand forever (D41). "Latest wins" is an agent read-time policy or an
  offline K3 narrative, never a stored verdict — the third clock (system belief evolution) genuinely
  has no home for a pure-literal fact, and that is correct.

## 4. The honest cost: D41's safety proof drops from three pillars to two

This is the one consequence that must not be glossed. D41 argued claim-validity is *not* a second
belief authority via **three** mechanical properties: **immutable + many-valued-per-fact +
no-fact-identity**. Closing this gap **requires manufacturing a fact-identity** `(subject,
attribute_key, bucket)` — there is no way to group "$5M" and "$7M" without a shared handle; the gap
*is* the absence of that handle. So D41's three-pillar proof **reduces to two: immutable +
no-belief-axis.** The claim that this is still safe: a queryable grouping handle that can only return
*"members of F"*, never *"the value of F"*, cannot be current belief. **The no-belief-axis therefore
becomes the sole structural D6 guarantee for non-relational facts and must be enforced mechanically.**
This is a substantive amendment to D41's *reasoning* (not its data) and the proposed D42 must state
it, not bury it.

## 5. Overall consequences

- **D2 / D3 / D18 intact.** No covert relation (literal objects, no predicate, no edge); no claim
  supersession or second supersession engine; literals never enter relations.
- **D6 preserved under the reduced (two-pillar) proof**, enforced mechanically (above).
- **A genuine new governance surface** — a second registry to seed/tune/promote **plus** value
  normalization (money/date/unit/fiscal-calendar) predicates never needed. Real cost; mitigated by
  start-strict + `other:` escape + quantities/dates already being D35 protected classes. Inherits
  both unsolved-at-scale dependencies (D17 ER quality, D5 vocabulary stability) and adds the
  fiscal-calendar spike.
- **Scale is acceptable only with write-time materialization** on the `(subject, slot)` block.
  Conflict rows are exactly the ones the "distinct facts not assertions" collapse (concepts §6) does
  **not** shrink, so the conflict subset is larger than a naive cell count — a load-test spike.
- **The requirement moves from relational-only to relational + the governed single-subject-attribute
  subset of non-relational, surfaced for agent/K judgment.** Not full coverage — detection recall is
  the serial product of three LLM-tagging steps. Coverage must never be reported as complete.

## 6. Residual non-goals after this recommendation (narrowed, not closed)

1. **Untagged / unregistered / fragmented attributes** → silently undetected, exactly as today
   (recall = attribute_key emitted ∧ subject resolved ∧ value normalized).
2. **Mis-normalized values reading as false agreement** → the dangerous silent direction; mitigated
   by failing to `indeterminate` on non-normalizable input, but the false-equate case is real
   (fiscal-calendar spike).
3. **Irreducible n-ary facts** → no clean key; surfaced-only at claim grain via semantic co-retrieval.
4. **No believed current value for a pure-literal fact — by design.** The system never asserts "Acme
   FY2023 revenue *is* $5M" unless the fact earns a relation (promote-on-demand). A conflicting
   pure-literal attribute stays surfaced-only forever; a consumer wanting one number gets "N
   conflicting assertions, no adjudicated value." Requirement working as intended, but a real
   residual.

## 7. Recommended decision (proposed — not yet logged)

**D42 — Non-relational conflicts are detected, grouped, and surfaced — never resolved.** A governed
`attributes` registry (peer of predicates, the literal-range home) + a derived, no-belief-axis
`claim_attribute_facts` grouping projection + `attribute_evidence`, materialized at E3 on the
zero-relation residue, with deterministic `conflict_state`; surfaced by `attribute_conflicts` /
inline tags on `claims_as_of` and barred (linter) from returning a single value; reviewed via D24
(`promote_to_relation`, never pick-a-value); narrated by K3; with **promote-to-relation** the only
path to a believed value. State the **D41 proof-reduction (3→2 pillars)** and the **mechanically-
enforced no-belief-axis** explicitly.

Docs a future implementation would touch (recommendation only):
- `decisions.md` — add **D42**; amend **D41**'s reasoning (3→2 pillars; fact-identity now exists and
  is safe only because the row has no winner/validity column) and its `§Consequences` residual bullet
  (the gap is now *detected and surfaced*, not "invisible until query"); amend the **D6** "refined by
  D41" note to name the no-belief-axis as the structural guard; note the attribute registry as a
  D5/D18 sibling.
- `postgres_schema_design.md` — new `attributes` registry + `claim_attribute_facts` projection (with
  a load-bearing no-winner/no-validity COMMENT, like the relations GiST-EXCLUDE comment) +
  `attribute_evidence`; new enums `attribute_value_domain`, `attribute_conflict_state`; add
  `promote_to_relation` to `review_verdict` + the pick-a/pick-b CHECK; rewrite the §15 non-goal;
  add the §16 D42 row; add §17 spikes (conflict-row sizing load-test; attribute-vocabulary P/R +
  canary on the existing `eval_suite='contradiction'`; value-normalization incl. fiscal calendar;
  precision-subsumption golden coverage).
- `e2_e3_claims_relations_design.md` §5/§7 — the E3 sibling-branch attribute-fact emission, grounded
  by D32 window-membership; the attribute-track spike.
- `registries_design.md` — the attribute promotion funnel (mirrors §7 predicate promotion; conflict
  hit-rate per `(subject, slot)` as the promotion signal).

## References

Analyses: `external_agents/codex.md` (independent), `internal_analysis.md` (5-angle workflow +
critiques). Decisions: `decisions.md` D2, D3, D5, D6, D18, D24, **D41**. Designs:
`postgres_schema_design.md` (§8 claims + D41 `claim_valid_*`, §9 relations/`contradiction_group`,
§15 non-goals), `e2_e3_claims_relations_design.md`, `registries_design.md`. Explainer:
`concepts.md` (§4 relational contradiction, §6 blocking). Requirement: `requirements_v3.md`
("contradictions are surfaced, never silently resolved").
