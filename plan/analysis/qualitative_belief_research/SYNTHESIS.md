# Qualitative Belief & the Verdict Layer — Re-evaluation (Analysis)

**What this answers.** Whether the D43 unified `facts` verdict layer (typed, governed relationships)
is the right shape — or over-engineered — once we insist that **temporal validity / time-travel is a
first-class requirement for *any* claim, including purely qualitative ones**. The forcing example:
multiple June-2026 sources say *"Jiri is the best boss in the world"*; multiple January-2027 sources say
*"Jiri is a terrible boss."* The later belief plausibly supersedes the earlier — yet it is pure
sentiment, fits no enumerable attribute, and may be partial (some still disagree).

> **Read this cold (CLAUDE.md Rule 1).** A **claim** is an atomic, immutable natural-language assertion
> *as a source made it* (the evidence record). A **fact / verdict** is what the system *currently
> believes* (revisable: its validity window can close). **Supersession** = a newer belief closing an
> older one's validity window. **Bi-temporal** = two clocks, *valid-time* (when it was true in the
> world) and *transaction-time* (when we believed it). D43 (`fact_layer_design.md`) makes the verdict
> layer one `facts` table whose object is an entity (a *relation*, graph-projectable) or a typed
> *literal* (a value), with supersession gated by a registered relationship type. This doc re-examines
> that against the qualitative requirement.

This re-evaluation was produced by a 17-agent internal workflow: four candidate architectures, each
designed independently and then attacked by three adversarial reviewers (correctness / dexterity /
scalability), then synthesized. The decisive finding came from cross-checking the **binding upstream
design**, not from the candidates themselves.

---

## 1. The decisive finding: qualitative belief is an *upstream* (extraction) concern, not a verdict-layer one

The whole debate about the verdict layer turns out to be **the wrong layer**. Pure sentiment never
becomes a claim in the first place:

- E2 extraction is Claimify-style (Selection → Decontextualization → Decomposition → grounding). The
  **Selection** stage is an explicit opinion filter: `e2_e3_claims_relations_design.md` §3 keeps only
  *"specific, verifiable"* propositions (a state, event, decision, quantity, policy, relationship) and
  **drops opinions** — its worked example literally drops *"considers it a runaway success"* as opinion.
  That stage is called out as *"the single biggest quality lever — removing it was the largest quality
  drop of any component."* (D31/D34/D35.)
- *"Jiri is the best boss"* has no quantity, date, entity-predicate, or change-of-state language. It is
  **dropped at Selection** → never becomes a claim → never gets an entity-resolved subject → never gets
  a `claim_valid_*` interval → is structurally invisible to **any** verdict layer downstream.

**Consequence:** swapping the verdict layer changes *nothing* about the qualitative case, because the
input does not exist in the system. Three of the six adversarial reviewers reached this independently.
The lever for qualitative temporal belief is the **extraction contract**, not the verdict table.

The boundary is *"verifiable proposition" vs "raw valence"*, and it is porous: *"The board rated Jiri
9/10 in the 2026 review"* (a quantity) is kept; *"most employees called Jiri a great boss in the 2026
survey"* (attributed) is borderline; *"Jiri is the best boss"* (raw valence) is dropped.

---

## 2. The verdict-layer comparison (for completeness)

Four candidate "where does the believed value live" architectures were designed and stress-tested
against scenarios S1 hard-supersede (headcount 600→700), S2 both-stand (FY revenue), S3 entity chain
(CEO Alice→Bob→Carol, open starts only), **S4 qualitative drift (the Jiri case)**, S5 scale (10⁸
claims), S6 uniform as-of, S7 immutability (200 identical claims).

| Candidate | Correctness | Dexterity | Scale | Simplicity | Qualitative (S4)? |
|---|---|---|---|---|---|
| **A — D43 typed verdict (current)** | high — *schema-enforced* "never silently resolve" | low | **excellent** | **high** | **no** (no slot for it) |
| B — emergent semantic slots (drop governed attributes) | low | high* | poor | low | partial* |
| C — hybrid (typed graph + soft verdict for the rest) | low–med | med | poor | very low | represents only |
| D — validity-bearing claim-clusters (steelman) | med | high* | med–poor | med | represents + supersedes* |

\* The dexterity of B/C/D is **illusory in this system**: the qualitative input they exist to serve is
dropped upstream (§1), so they validate against a pipeline that does not exist here.

**Why B/C/D lose even on their own terms:**

- They make the supersession **slot key** an *emergent clustering artifact* and put it in **plane E
  (truth)** — which breaks the rebuild-determinism contract (D1/D6/D7) the whole system rests on: a
  re-cluster can renumber/merge the very key that guarantees "≤1 belief per slot," and as-of answers
  stop being reproducible.
- They downgrade *"never silently resolve a conflict"* from a **schema invariant** (D43's generated,
  registry-locked `supersedable` column an app cannot forge) to a **model judgment** (a per-cluster
  inferred class). A clustering/classification error then *silently supersedes a both-stand figure* —
  the one behavior `requirements_v3` forbids — with no DB backstop.
- D does decisively **kill the "immutability / 200-claims" objection** (validity keyed to a cluster, not
  to claims, closes one belief while 200 claims stay untouched — S7 clean). That premise should not be
  used to reject claim-level validity again. But D pays with HAC clustering on the 10⁸ claim grain and
  the same model-enforced-safety downgrade.

**A (D43) is the simplest of the four and the only one whose core safety is a schema invariant.** Its
genuine limitation is real and narrow: it has **no verdict object for qualitative belief at all** — but
that is the scope boundary §1 shows belongs upstream, not a tuning failure of the verdict layer.

---

## 3. Recommendation

**Keep D43 as the verdict layer, essentially unchanged. Do not replace it with B, C, or D.** The
"over-engineered" intuition is, for the verdict layer specifically, backwards: D43 is the least complex
option and the only one that makes the forbidden silent-resolve mechanically impossible.

For the qualitative requirement, the choice is a **requirement decision**, not an architecture one:

- **(a) Surfaced distribution over time** *(safe; recommended)* — relax E2 Selection to **retain**
  sentiment as a distinct `opinion`-kind claim (signed stance + aspect), and add a bounded **stance
  layer** that is **coexist-by-default and never auto-caps**. Time-travel returns the *distribution* of
  stances valid at T (*2026 → mostly positive; 2027 → mostly negative, with dissent*) — drift is
  **surfaced as a temporal shift**, never resolved to one silently-chosen winner. Crucially, this stance
  layer lives in the **K/P projection plane** (rebuildable, model+version pinned — D7/D14), **not** in
  plane-E truth, so it never poisons the deterministic-rebuild contract or the GiST invariant the way
  B/C/D do. Structured *capping* "supersession" of an opinion is a reviewed promotion only.
- **(b) Non-goal** *(simplest)* — leave qualitative belief in **K3 narrative** (time-filterable evidence
  + citations, surface-only) and document **structured qualitative supersession as a non-goal**, i.e.
  narrow the must-have to "qualitative = time-filterable evidence + narrative," not "qualitative = a
  capped structured verdict."

**Biggest risk of (a):** retaining sentiment reverses *the single biggest quality lever* (E2's
opinion-drop) and could flood plane E with low-value, hard-to-corroborate valence. This must be measured
(opinion-claim precision/recall, corroboration rate) **before** any schema work — it is cheaper to
settle the requirement than to build a stance layer the pipeline cannot safely feed. If retention proves
net-negative, fall back to (b).

Either way, **D43 stays**, and the work is upstream (extraction contract) + a projection-plane companion
— not a verdict-table redesign.

---

## 4. The latent contradiction to reconcile (independent of the fork)

`requirements_v3.md` (line 29) classifies claims as **fact / opinion / prediction** and calls them
immutable/append-only — i.e. opinions *are* claims. But **D31/D34** have E2 Selection **drop** opinions.
These cannot both hold. Whichever fork is chosen, this must be reconciled: option (a) makes opinions a
retained claim kind (requirements wins, D31/D34 amended); option (b) removes "opinion" from the claim
taxonomy (D31/D34 win, requirements amended). Tracked in `questions.md`.

---

## 5. A separate axis: how *much* of D43 should the schema enforce? (hardened vs lean-pragmatic)

Orthogonal to the qualitative question is the user's sense that the D43 DDL *looks* over-engineered.
That look comes almost entirely from machinery added during the Codex review rounds, which moved
invariants from **application-enforced** (the E3 normalizer/adjudicator) to **schema-enforced** (triggers,
multiple EXCLUDE arms, generated columns, composite FKs). This is a **dial**, not a yes/no:

- **Maximal (current §9):** every invariant is a schema invariant — the DB physically cannot violate
  "never silently resolve," "one belief per slot," "gate can't be forged," "identity is immutable." Cost:
  ~120 lines of triggers/arms/constraints that read as baroque.
- **Lean-pragmatic (Appendix A):** keep the *cheap, high-value* guards in the schema; push the elaborate
  ones onto the normalizer/adjudicator + CI tests. The schema collapses to "a facts table + ~4
  constraints + one EXCLUDE." Cost: the moved invariants become *safe-if-the-code-is-correct* rather than
  *safe-by-construction* — a normalizer bug can silently produce a wrong verdict with no DB backstop.
- **Minimal:** facts table + exclusive-arc CHECK + PK only; all supersession/uniqueness adjudicator-driven
  (closest to the pre-D43 relations posture).

**Tension to weigh honestly:** the §2 evaluation rated D43 highest on correctness *because* the gate is a
schema invariant ("not a model judgment"). The lean-pragmatic version trades exactly that away for
readability. It is a legitimate trade (most production systems sit here, and the original relations design
did too), but it is not free. Appendix A gives the concrete lean version and the precise diff so the
choice can be made on the artifact, not the abstraction.

---

## Appendix A — Lean-pragmatic `facts` DDL (alternative to `postgres_schema_design.md` §9)

Same columns and semantics; supersession/uniqueness for everything except *no-duplicate-overlapping
entity edge* moves to the E3 adjudicator + CI. This is an **option**, not the committed schema.

```sql
CREATE TABLE facts (
  fact_id           uuid PRIMARY KEY,
  deployment_id     uuid NOT NULL REFERENCES deployments,
  subject_entity_id uuid NOT NULL,
  rel_key           text NOT NULL,                 -- governed predicate OR attribute
  object_kind       fact_object_kind NOT NULL,     -- entity | literal
  object_entity_id  uuid,                           -- set IFF entity
  object_value      jsonb,                          -- set IFF literal (normalized value)
  object_value_identity text,                       -- set IFF literal (value identity hash)
  qualifiers_hash   text NOT NULL DEFAULT '',
  valid_kind        claim_valid_kind,               -- set by the E3 normalizer FROM the registry (app invariant; CI-checked)
  cardinality       text NOT NULL DEFAULT 'set',    -- set by the normalizer FROM the registry (app invariant)
  supersedable      boolean GENERATED ALWAYS AS     -- NULL-safe; gate is still derived, just from app-set inputs
                      (COALESCE(object_kind='entity' OR (valid_kind='effective_period' AND cardinality='single'), false)) STORED NOT NULL,
  valid_from      timestamptz,
  valid_until     timestamptz,
  ingested_at     timestamptz NOT NULL DEFAULT now(),
  invalidated_at  timestamptz,
  evidence_count  integer NOT NULL DEFAULT 0,
  contradict_count integer NOT NULL DEFAULT 0,
  confidence      real,
  contradiction_group uuid,
  status          relation_status GENERATED ALWAYS AS
                    (CASE WHEN invalidated_at IS NOT NULL THEN 'invalidated'::relation_status ELSE 'active'::relation_status END) STORED,
  fact_label text, fact_label_version text, fact_label_embedding_ref text,
  normalizer_version text NOT NULL, adjudicator_version text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deployment_id, fact_id),
  FOREIGN KEY (deployment_id, rel_key)           REFERENCES governed_relationships (deployment_id, rel_key) ON UPDATE CASCADE,
  FOREIGN KEY (deployment_id, subject_entity_id) REFERENCES entities (deployment_id, entity_id),
  FOREIGN KEY (deployment_id, object_entity_id)  REFERENCES entities (deployment_id, entity_id),
  -- KEPT (cheap, high-value):
  CHECK ( (object_kind='entity'  AND object_entity_id IS NOT NULL AND object_value IS NULL     AND object_value_identity IS NULL)
       OR (object_kind='literal' AND object_entity_id IS NULL     AND object_value IS NOT NULL AND object_value_identity IS NOT NULL) ),
  CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from),
  CHECK (invalidated_at IS NULL OR invalidated_at >= ingested_at),
  CHECK (supersedable OR invalidated_at IS NULL),   -- the no-belief-axis FLOOR: a both-stand figure is never tx-invalidated
  -- ONE entity-relation uniqueness arm (exactly the pre-D43 relations table): no duplicate overlapping edge.
  EXCLUDE USING gist (
    deployment_id WITH =, subject_entity_id WITH =, rel_key WITH =, qualifiers_hash WITH =, object_entity_id WITH =,
    (tstzrange(valid_from, valid_until)) WITH &&
  ) WHERE (object_kind='entity' AND invalidated_at IS NULL AND contradiction_group IS NULL)
);
-- indexes, fact_evidence (PK evidence-once + hash partitions), fact_adjudications, relations VIEW: UNCHANGED.
-- relations/predicates/attributes views are read-only by REVOKE + comment (no INSTEAD OF triggers).
```

**Precise diff vs current §9 (what is REMOVED / SIMPLIFIED / MOVED-TO-APP):**

| Removed from schema | Now enforced by |
|---|---|
| 3 of the 4 GiST EXCLUDE arms (entity-functional split, literal-single, literal-set) — one entity arm remains | E3 adjudicator: functional "one CEO" cardinality, literal supersession, both-stand coexistence (CI-tested) |
| `UNIQUE NULLS NOT DISTINCT (…)` exact-duplicate floor | adjudicator dedup + CI |
| `facts_lock_gate_inputs()` + `trg_facts_lock_gate` (lock gate inputs, freeze identity, bar re-cap) | normalizer sets `valid_kind`/`cardinality` from the registry, never re-caps a non-supersedable window, never mutates identity — documented invariants + CI |
| `govrel_freeze_gate_fields()` + `trg_govrel_freeze_gate` | operational rule: "change a live relationship's semantics ⇒ rebuild the affected facts," not in-place edit |
| `reject_view_write()` + 3 × `INSTEAD OF` view triggers | `REVOKE INSERT/UPDATE/DELETE … FROM PUBLIC` + comment |
| composite range-kind FKs (`predicate_signatures` `range_kind='entity'`; `parent_key` same-range; `UNIQUE(deployment_id, rel_key, range_kind)`) | plain FKs + documented normalizer invariant |
| `CHECK (object_kind='entity' OR valid_kind IS NOT NULL)`, `CHECK (cardinality IN (…))` | `COALESCE` in `supersedable` makes a NULL `valid_kind` fail safe (non-supersedable); the rest is a normalizer/CI invariant |

| Kept identical | Why |
|---|---|
| All columns; `supersedable` + `status` GENERATED (one line each) | cheap, readable, and the gate is still derived not hand-set |
| exclusive-arc CHECK; strictly-positive interval CHECK; `invalidated_at ≥ ingested_at`; **`CHECK (supersedable OR invalidated_at IS NULL)`** | the last one is the single most important safety floor: a both-stand figure can never be transaction-invalidated |
| one entity EXCLUDE (no duplicate overlapping edge); all indexes; `fact_evidence`; `fact_adjudications`; `relations`/`predicates`/`attributes` views; `governed_relationships` + its range-kind split CHECK | the load-bearing structure is untouched |

Net: roughly **−120 lines** of DDL (two trigger functions + three view triggers + the govrel freeze +
three EXCLUDE arms + the exact-dup UNIQUE + the composite FKs), replaced by documented normalizer
invariants and CI tests. The schema reads as a facts table with ~4 checks and one exclusion.

---

## References

Workflow: internal 17-agent evaluation (4 designs × 3 adversarial lenses + synthesis), run
`wf_d5535d4f-0f6`. Binding designs: `decisions.md` (D2, D3, D6, D18, D31, D34, D35, D41, D42, D43),
`fact_layer_design.md`, `postgres_schema_design.md` §9, `e2_e3_claims_relations_design.md` §3,
`requirements_v3.md`. Open decision + the requirements/D31 contradiction: `questions.md`.
