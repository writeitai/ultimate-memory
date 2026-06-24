# Internal multi-agent analysis — non-relational claim conflicts

Output of an internal 5-angle design workflow (detection-first / track-structure-first /
handle-adjudicate-first / query-reaction-first / consequences-adversarial), each proposal
adversarially critiqued, then synthesized. Companion to `external_agents/codex.md` (independent
Codex analysis); both are consolidated in `SYNTHESIS.md`. This is *analysis* (working material,
opinionated, non-binding) — the binding decision it recommends (a proposed **D42**) is described in
`SYNTHESIS.md` §Recommended decision, not yet logged.

## The problem (recap)

D41 gave each claim an immutable, source-asserted validity *interval*, so a temporally-scoped fact
that yields **no relation** (single-entity / attribute / literal-or-quantity-object / n-ary — D2,
D18) is now time-*filterable* as evidence (`claims_as_of`). It did **not** give such facts a
**fact-identity**, so two sources asserting incompatible content for the same entity + attribute +
world-time have no shared handle, no `contradiction_group`, no verdict — `claims_as_of` returns
both but nothing groups or flags them. Three flavors: conflicting value same period ($5M vs $7M
FY2023); conflicting attribute (founded 1998 vs 1999); temporal restatement ($5M reported 2024 →
$5.2M reported 2025).

## Synthesized recommendation

A thin **"detect + surface, never resolve"** design in three parts, in dependency order:

1. **API / recipe-linter floor (zero schema; the requirement-bearing core).** Extend the recipe
   linter (which already bars `claims_as_of` from "currently true") so that *any* claims-plane
   recipe that can return a non-relational fact **must not** expose a single-winner accessor.
   "Is X's value currently V?" routes to a relation recipe; if no relation exists, the API returns
   *"no adjudicated value; N conflicting assertions exist; promote-to-relation to track."* This
   alone closes the actual harm (an agent reading top-1 as the answer) and needs no table.
2. **Governed attribute-slot vocabulary (small registry — Track A).** A new `attributes` registry,
   a **peer of `predicates`** (reusing D5 machinery wholesale: name / parent / description /
   `value_domain ∈ {money,date,quantity,count,ratio,string_enum,boolean}` / unit dimension /
   synonyms[] / tier / `usage_count` / `other:` escape / promotion job). It is a genuine peer, not
   a reuse: a predicate relates two entities (D18 bars literal objects); an **attribute attaches a
   literal/quantity to ONE entity** — exactly the literal-range home D18 deliberately kept off
   predicates. Seed core small (D5 strict-first). `value_domain` drives **deterministic
   normalization** so "$5M" and "5,000,000 USD" do not read as a conflict.
3. **Derived, non-authoritative grouping projection (Track B/C hybrid, no belief axis).** A
   rebuildable `claim_attribute_facts` projection keyed `(deployment_id, subject_entity_id,
   attribute_key, valid_bucket)` + an `attribute_evidence(attr_fact_id, claim_id, stance)` join
   (mirroring `relation_evidence`), carrying member claims, `normalized_value`, `asserted_at`, and a
   **deterministically-computed** `conflict_state ∈ {single, corroborated, value_disagreement,
   restatement, refinement, indeterminate}`. **Hard structural constraint:** it carries **no**
   `believed_claim_id`, **no** winner pointer, **no** `valid_until`/`invalidated_at`/`status`, **no**
   supersede verdict. It **groups and describes; it never resolves.** Materialized at **E3 write
   time** on the zero-relation residue (reusing the existing `(subject, slot)` blocking shape + D17
   entity resolution + D4 cheap-first cascade the claim already pays for) — **not** a query-time or
   rebuild-time `GROUP BY` over the hot `claims` table (which would force a D23-forbidden btree or a
   full-table aggregation — the value-gate self-defeat of D25). Zero query-path LLM (D9).

### Staged plan

- **Minimal now (the complete intended surfacing mechanism — not an MVP phase):** the linter floor
  (1); the `attributes` registry + deterministic value-normalization incl. the **fiscal-calendar
  (FY≠CY) bucketing rule as a hard construction rule** (detection correctness depends on it, so per
  Rule 2 it cannot be deferred); E2 emits `(subject_entity, attribute_key, normalized_value, unit)`
  for single-subject attribute claims, grounded by the existing D32 window-membership check (the
  value substring must verbatim-exist in the bundle, exactly like the D41 date); E3 materializes
  `claim_attribute_facts` + `attribute_evidence` and computes `conflict_state` deterministically;
  the `attribute_conflicts(subject, attribute_key?, as_of?)` recipe + inline conflict tags on
  `claims_as_of`; route high-impact conflicts to the **existing D24 review queue** under
  `review_item_kind='contradiction'` with a **new `promote_to_relation` verdict** and a CHECK that
  `pick_a`/`pick_b` are illegal for an attribute conflict (a human "pick" would write a claim-side
  verdict — the forbidden second authority).
- **Named upgrades on measured demand (documented alternatives, not phases):**
  (U1) if a non-relational attribute genuinely needs an adjudicated **current value**, it **promotes
  to a relation** via the D5 `other:` funnel — but only when an entity object can be manufactured;
  a pure-literal attribute stays surfaced-only **forever** (the terminal non-goal). The attribute
  `usage_count` + conflict hit-rate per `(subject, slot)` is the promotion signal.
  (U2) a believed-value **narrative** ("sources disagree; the 2025 filing says $5.2M") is compiled
  **offline by K3** (debounced, D12), reading the conflict group with zero query-path LLM.
  (U3) irreducible n-ary facts + recurrence/anchor-event validity stay on D41's documented
  expressivity-child-table ramp.

## By sub-problem

- **Detect.** Block key `(deployment_id, subject_entity_id, attribute_key, valid_bucket)` —
  *the crux and the whole reason the gap exists*: relations get cheap detection because E3
  manufactures and indexes `(subject, predicate, object)`; non-relational claims carry only
  `claim_text` + a per-`claim_id` `claim_valid_*` that D41 says is "never addressable as the
  validity of fact F," so there is no handle under which $5M and $7M can meet. The key is **derived
  over immutable claims, never stored back on the claim**. `valid_bucket` is computed on the
  D41-normalized `[start,end]` window (via `tstzrange &&`), **never on the label string** (else
  off-calendar FY produces phantom conflicts and misses real ones). Conflict-vs-compatible-refinement
  is deterministic and cheap-first (D4-shaped): disjoint bucket → series (free, filtered by `&&`);
  same value within tolerance → corroboration; precision subsumption → refinement; overlapping
  bucket + incompatible value → `value_disagreement`; non-normalizable → `indeterminate`
  (fail-**safe** toward surfacing). No LLM on the residue.
- **Track.** Hybrid (registry + derived projection); reject Track D (literal-on-relation, breaks
  D18) and any winner-bearing table. `claim_attribute_facts` is the **fourth derived projection of
  claims** (alongside relations, P1 vectors, P2 graph): deletable, rebuildable (D7), no
  source-of-truth. The no-belief-axis is the **sole remaining structural guarantee of D6** once a
  fact-identity exists and must be enforced **mechanically** (a CI schema-test forbidding any
  winner/value/validity column + a recipe-linter rule), not by convention.
- **Handle.** Surface-all, never pick-winner — forced by both the requirement ("contradictions
  surfaced, never silently resolved") and D3/D6. Detection produces a `conflict_group` and stops:
  no window closed, no `invalidated_at`, no claim superseded, no believed value. Review (D24)
  confirms "same measure and genuinely conflict" or routes to promotion (U1) — **never** "pick the
  true value."
- **Query.** `claims_as_of` is unchanged (evidence-only). New `attribute_conflicts(...)` and
  `attribute_value_as_of(...)` recipes return **all** asserted values + conflict grouping, never a
  single value (linter-enforced — the API analogue of D6). Each conflicting claim carries its
  `conflict_group` id inline. Zero LLM; `conflict_state` precomputed at E3.
- **K-plane.** K is the **consumer/narrator**, never the structured verdict home. A conflict group
  triggers K refresh; K3 compiles cited belief-with-contradiction prose ("$5M per the 2024 filing,
  $5.2M per the 2025 restatement") — exactly its existing job via `knowledge_artifact_evidence`. It
  never invents a single value the structured layer refused to assert.
- **Temporal restatement.** Same `conflict_group`, distinguished by `conflict_state='restatement'`,
  surfaced as an `asserted_at`-ordered presentation hint — *not* a relation `valid_until` closure,
  *not* a stored verdict. The discriminator from a two-source `value_disagreement` is **same bucket +
  distinct value + different `asserted_at`**. This is exactly why D41 split `asserted_at` (assertion
  event) from `claim_valid_*` (world-time). Both values stand forever (D41). "Latest wins" is an
  agent read-time policy or an offline K3 narrative, never a stored verdict.

## Overall consequences (honest)

- **D2:** intact — `claim_attribute_facts` has literal objects, no predicate, no entity-entity edge;
  it fills the "claims that yield no relation" cell with a lighter structure, not a covert relation.
- **D3:** intact — no claim supersession, no second supersession engine, no window closed.
- **D6 — the proof changes, and this is the load-bearing honesty.** D41's "no second belief home"
  rested on **three** pillars: immutable **+** many-valued **+** no-fact-identity. This design
  **manufactures a fact-identity** `(subject, attribute_key, bucket)` — unavoidable, because without
  it there is no key under which two claims can meet (the gap *is* the absence of this key). So
  D41's three-pillar proof **reduces to two**: immutable **+** no-belief-axis. The argument it is
  still safe: a queryable grouping handle that can only return "members of F," never "the value of
  F," cannot be current belief. The no-belief-axis becomes the *sole* structural D6 guarantee for
  non-relational facts and must be enforced mechanically. **This is a substantive amendment to D41's
  stated reasoning, raised as such — not "wording, not substance."**
- **D18:** untouched — literals/quantities/dates never enter relations; they are grouped by an
  `attribute_key` string, never an object entity or Date-node.
- **New governance surface:** a real cost — a second registry to seed/tune/promote **plus** a
  value-normalization concern (money/date/unit/fiscal-calendar) predicates never had. Mitigated by
  start-strict + `other:` escape + the fact that quantities/dates are already D35 protected classes;
  inherits both unsolved-at-scale dependencies (D17 ER quality, D5-style vocabulary stability) and
  adds the fiscal-calendar spike.
- **Scale:** correct only because the grouping is materialized at E3 write time on the `(subject,
  slot)` block (cost scales with ambiguity, not volume). `claim_attribute_facts` is sized by distinct
  `(subject × attribute × bucket)` cells **plus** extra rows per conflicted cell — and conflict cells
  are exactly the ones the "distinct facts not assertions" collapse does **not** shrink, so the
  conflict subset is larger than a naive estimate (a new §17 load-test spike). `attribute_evidence`
  is another ~10⁸ table following the `relation_evidence` pattern (HASH by `attr_fact_id`, evidence-
  once). Fits D23 provided the corrected conflict-row count is confirmed.

## What the workflow rejected (killed by critiques)

- `believed_claim_id` / winner pointer on the projection — inverts D41 pillar 2, creates a second
  current-belief home that drifts against a promoted relation (the Mem0 desync class D6 forbids).
- `restatement_supersede` as a stored outcome — winner-picking supersession outside relations.
- A `claim_contradiction_group` / `proposition_facts` **with** a winner/validity column — the slippery
  slope to a full second adjudicated layer that re-opens D3/D6.
- A standing `claim_fact_clusters` `GROUP BY` read-model claimed "Lance-scalar-cheap" — its scale
  claim is false (a key on `(subject, attribute)` is a `GROUP BY` over ~5×10⁷ partitioned claims, not
  a per-row scalar filter); replaced by E3 write-time materialization.
- K3 as a structured query-path verdict home; review-queue verdicts that "pick the true value" — both
  re-introduce a second authority.

## Residual after this recommendation (narrowed, not closed)

1. **Untagged / unregistered attributes** — detection recall is the **serial product** of three
   LLM-tagging steps (attribute_key emitted **and** subject resolved **and** value normalized); an
   untagged or fragmented attribute is silently missed, exactly as today. Coverage must never be
   reported as full.
2. **Mis-normalized values reading as false agreement** — the dangerous (silent) direction; mitigated
   by failing to `indeterminate` on non-normalizable input (over-surface, never false-merge), but the
   false-equate case is real and load-bearing for the fiscal-calendar spike.
3. **Irreducible n-ary facts** — no clean `(subject, attribute)` key; stay surfaced-only at claim
   grain via semantic co-retrieval.
4. **No believed current value for a pure-literal fact — by design.** The system never asserts
   "Acme's FY2023 revenue *is* $5M" unless the fact earns a relation (U1). A conflicting pure-literal
   attribute stays surfaced-only forever; an agent wanting one number gets "N conflicting assertions,
   no adjudicated value" + the promote-to-relation advisory. That is the requirement working as
   intended, but a real residual for any consumer expecting a scalar.

## Appendix — the five angles and their adversarial verdicts

| Angle | Critique verdict | The strongest objection it surfaced |
|---|---|---|
| **detection-first** | sound_with_fixes (D2✓ D3✓ D6✓) | The block key it depends on **manufactures the fact-identity D41 forbids** — a real, must-name amendment to D41 (3→2 pillar proof), not "wording". Also: conflict rows don't benefit from the "distinct facts" collapse, so sizing is larger than stated; recall is a 3-step serial product. |
| **track-structure-first** | sound_with_fixes (D2✓ D3✓ **D6✗**) | The conflict key erodes the *structural* basis of D41's no-fact-identity pillar; the no-winner guard was left as **convention** (a table comment + linter), which must instead be a **mechanical** schema invariant. |
| **handle-adjudicate-first** | sound_with_fixes (D2✓ **D3✗ D6✗**) | It proposed a `believed_claim_id` + `restatement_supersede` — a second current-belief authority that drifts against a promoted relation (Mem0 desync) and a supersession engine outside relations. **Rejected**; kept only its surface-all framing. |
| **query-reaction-first** | **over_built** (D2✗ D3✓ D6✓) | The requirement-closing work is only the linter rule (~5% of the proposal); the clustering machinery is UX, and a `(subject, attribute)` key on the *claims* table reconstructs the relation blocking key D2 split off. Kept the linter floor; rejected the standing read-model. |
| **consequences-adversarial** | sound_with_fixes (D2✓ D3✓ D6✓) | Even the "do nothing structural" floor smuggles in an `attribute_slot` key (the same Trojan horse) and a query-time recipe can't decide conflict-vs-refinement without an LLM (D9 bars it) — so it can only **co-locate**, not flag. Establishes K-as-consumer and the minimal honest intervention. |

The cross-angle agreement is decisive: a grouping key is **necessary** (so the fact-identity and the
D6-proof-reduction are unavoidable and must be owned), a winner/verdict is **forbidden** (the
no-belief-axis is the sole structural D6 guarantee and must be mechanical), and the requirement is
satisfied at the grain of "both sides co-located + machine-readable conflict flag," with K3 the
narrative home and promote-to-relation the only path to a believed value.
