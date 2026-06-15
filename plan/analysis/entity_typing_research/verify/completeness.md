# Completeness & Coherence Critique — Entity Typing Research (TY1–TY5)

Adversarial review of `questions/TY1..TY5`, cross-checked against `repo_findings/*` and the
cloned repos under `_additional_context/`. Default stance: skeptical; load-bearing code claims
were re-read from source, key external claims re-fetched.

**Headline:** TY1–TY5 are unusually coherent and mostly compose into ONE design. The core
spine — *type at extraction (TY1) → cheap-first typing cascade (TY3) → mention-level votes
reconciled at merge (TY2) → versioned `type_decisions` ledger + non-destructive gate (TY4) →
abstain-over-dump with `other:` floor (TY5)* — is internally consistent and grounded in
verified code. But there are real **unresolved seams** (ordering of resolve-vs-type, the
quarantine table's existence, the metonymy/over-merge two-sided lever creating a loop risk)
that a synthesis MUST adjudicate rather than paper over.

Verified-from-source this pass: LightRAG dedup-before-vote bug (`operate.py:1668` →
`max(set(...),key=count)`, confirmed exact); Graphiti silent-swallow
(`dedup_helpers.py:175-176` `if resolved_specific_labels: return resolved_node`, confirmed);
GraphRAG `groupby(["title","type"])` (`extract_graph.py:108`, confirmed). GLEIF ELF page
re-fetched (see overclaim O3).

---

## gaps[]  — typing sub-problems unaddressed or under-addressed

- **G1. Attribute/value-vs-entity gate (the "deferred-extraction case") is never typed.**
  The task explicitly asks about the *value gate* / deferred-extraction case, and NONE of
  TY1–TY5 addresses it. The whole corpus assumes the unit being typed is already a mention of
  an *entity*. But a large fraction of extracted spans are **attribute values, literals, dates,
  quantities, roles** ("CEO", "42%", "March 2024") that should NOT become typed entities at all
  — they are edge attributes or claim values. TY5 brushes the closest ("CEO" as a role) but
  treats it as a Person-typing problem, not as an entity-vs-value gate. No question answers:
  *what decides a span is entity-worthy before the typing cascade runs?* If the cascade's Tt2
  (GLiNER) or Tt3 (LLM) is handed a value span, it will dutifully type it (probably `Concept`)
  and mint a junk entity. **This is the single largest hole.** The cascade needs a rung-zero
  *entity-worthiness / value gate* upstream of Tt0, or an explicit statement that E2 claim
  extraction already partitions entities from values before typing is invoked.

- **G2. The resolve-vs-type ordering is left genuinely contradictory across files (see C1).**
  No file owns the canonical order; three different orders are stated. This is a gap in
  *decision*, not just coherence — synthesis must pick one.

- **G3. No file specifies who owns the `Concept`-as-catch-all-vs-`other:` boundary at
  RUNTIME.** TY5 says "`Concept` is a positive assertion; `other:` is the dump"; TY1/TY3 say
  the terminal fallback is `Concept` ("never drop, never guess"). These are in tension (C3):
  TY3's "fall-back to `Concept`" is exactly the dumping TY5 forbids. The cascade's terminal
  rung is under-specified — does an unconfident mention land in `Concept` (TY1/TY3) or `other:`
  (TY5)? Domain/range behavior differs (Concept→`related_to` legal; `other:`→ungoverned).

- **G4. Cross-document type staleness / read-time consistency is unaddressed.** TY4 §2.3 notes
  the gate must read the *entity-level reconciled* type "because the object entity may have
  been typed more confidently by a prior document" — but no file specifies what happens when
  document N's relation is validated against entity type as-of-now, then a later document
  retypes the entity. TY4's ripple covers retype→relations, but not the *ordering race* between
  concurrent per-document chains (D12) typing the same entity. The "two-way handshake" (TY3
  §2.7) between resolution and typing is asserted but never sequenced for concurrency.

- **G5. No abstention/escalation budget or termination guarantee for the cascade.** TY3 defines
  escalate-on-low-confidence at every rung but never bounds how much escalates. If GLiNER's
  confidence is long-tailed (TY5's own cited finding) and the precision-conservative posture
  (TY3 finding 2) pushes everything ambiguous *up*, the LLM rung (Tt3) and human rung (Tt4)
  could receive far more volume than D24's review queue is sized for. No file estimates the
  escalation rate or states a fallback when the budget is exceeded (other than `Concept`/
  `other:`, which reopens G3).

- **G6. Subtype/extension-pack domain-range inheritance is asserted, not pressure-tested.**
  TY5/TY3 lean on D15 "domain/range checked at the parent/core level, so a missing subtype
  never blocks." But no file checks the case where a *pack predicate is defined on a subtype*
  (e.g. Work-pack `blocks: Task→Task`). If the entity is only typed to core `Event` (subtype
  abstained), does `blocks` validate or fail? Parent-level checking implies it would *under*-
  gate (allow Event→Event for a Task-only predicate). This is unaddressed and interacts with
  D18 correctness.

- **G7. mem0/letta/hipporag/zingg/splink were in scope but only mem0 is covered.** The
  repo_findings cover Graphiti, Cognee, LightRAG, GraphRAG, GLiNER, GLiREL, mem0. The
  `_additional_context/` dir also contains `letta`, `hipporag`, `dedupe`, `splink`, `zingg`,
  `fastcoref`, `maverick-coref`, `ladybug`. None checked for typing patterns. Likely low-yield
  (ER/coref tools), but the negative result is asserted by omission, not verified — a minor
  evidence gap.

---

## contradictions[] — where the answers don't compose into one design

- **C1. (LOAD-BEARING) Resolve-vs-type ordering is stated three different ways.**
  - **TY1** never sequences resolve vs type; it places typing "at E2 extraction" and treats
    resolution (D17) as downstream/separate ("keep it off resolution").
  - **TY3 §2.7** recommends **type FIRST, then resolve** ("type the mention early because
    typing improves resolution… a cheap pre-type feeds resolution") — a *two-way handshake*.
  - **TY4 §2.3 step 1-2** fixes the order as **resolve FIRST, then type** ("1. Resolve each
    mention → entity_id … 2. Type each mention").
  These cannot all be the canonical order. TY3 wants type→resolve (type scopes the per-type
  resolution thresholds); TY4 wants resolve→type (so the type attaches to a known entity_id).
  Both have real justification, which is exactly why synthesis must adjudicate. The likely
  reconciliation: a *cheap* mention-type (Tt0/Tt1/Tt2) runs **before** resolution to scope it,
  and the *entity-level reconciled* type is computed **after** resolution — i.e. typing
  straddles resolution, it is not strictly before or after. No single file states this cleanly;
  TY3 gestures at it, TY4 contradicts it with a strict DAG. **This is the #1 thing to fix.**

- **C2. The merge-time reconciliation rule is specified inconsistently.**
  - **TY1 §R5** and **TY3 §2.5/D21** adopt **Graphiti monotonic generic→specific promotion** as
    the default, with specific/specific conflict → review.
  - **TY2 §R2** and **TY5 §(1)** adopt a **confidence-weighted multiset vote with specificity
    tiebreak** (TY2 explicitly rejecting LightRAG's blind vote AND warning against Graphiti's
    monotonic lock for cross-core conflicts).
  - **TY5 §(1)** is sharper still: "do NOT adopt Graphiti's monotonic generic→specific lock for
    cross-core-type conflicts… monotonic promotion is fine only *within* a parent."
  So TY1/TY3 default to monotonic-promotion; TY2/TY5 default to weighted-vote and explicitly
  call monotonic promotion *dangerous* across core types. These are different algorithms with
  different outputs on the same input (a Person mention + an Organization mention on one
  entity: promotion locks whichever specific came first; weighted-vote picks by confidence/
  count). They *agree* only on the sub-case "Concept→specific" and "route hard conflicts to
  review." Synthesis must state the unified rule: **promote monotonically only within a
  parent chain; use confidence-weighted vote across siblings; route cross-core conflict to
  review.** No single file says exactly this; TY2 and TY5 are closest and should win over
  TY1/TY3's plain Graphiti promotion.

- **C3. Terminal fallback target conflicts: `Concept` vs `other:`.** TY1 finding-2/§R2 and TY3
  finding-2/fallback-row make the terminal fallback **`Concept`** ("never drop, never guess;
  lets `related_to` carry it"). TY5 §(3) forbids exactly this: "`Concept` is a positive
  assertion… Out-of-confidence mentions go to `other:`, not `Concept`." Domain/range
  consequences differ (Concept is a real core type with `related_to`; `other:` is ungoverned/
  monitored). This is a genuine design fork the synthesis must close, not a wording nit —
  it changes what predicates a low-confidence entity can carry.

- **C4. "Type as anti-merge signal" (TY2 R4 / TY3) vs "type OFF the identity key" (all files).**
  Every file insists type is NOT part of identity (rejecting GraphRAG groupby). Yet TY2 R4 and
  TY3 §2.7 feed type *into* the resolution decision as a soft discriminator at T5. This is
  defensible (soft prompt cue ≠ identity key) but the files never reconcile the surface tension:
  type is "orthogonal to identity" (TY3 finding 1, TY1 §R1) AND "a soft lever on the merge
  decision" (TY2 R4). A reader could read these as contradictory. Synthesis should state the
  precise distinction: type is not a *blocking/identity key* but IS *evidence* the T5 LLM may
  weigh — and crucially must guard against the loop in C5.

---

## overclaims[]

- **O1. (LOOP RISK — the task's explicit pressure-test) "type-disagreement-as-ER-signal" is
  presented as net-additive but the loop it creates is under-acknowledged.** TY2 builds a
  two-sided lever: type-incompatibility is a *soft anti-merge cue going IN* (R4, at T5) AND a
  *bad-merge detector coming OUT* (R3, post-merge → un-merge candidate). This is a feedback
  loop. Consider: T5 uses type to *avoid* merging Person/Place candidates (R4). The cases that
  slip through to a merge are therefore *exactly* the ones where other evidence overrode the
  type signal. R3 then re-flags those same merges as over-merge candidates *because* of the
  type split — re-surfacing a decision T5 already adjudicated *with the same signal*. Without a
  guard, an entity can oscillate: merged (type overridden by evidence) → flagged for un-merge
  (type conflict) → reviewer keeps merged → re-flagged next rebuild (type still conflicts).
  TY2 R3 partially mitigates with "metonymy-allowed pairs are recorded so not re-flagged each
  rebuild" and "low-confidence outlier absorbed by R2" — but it does NOT close the loop for the
  *balanced high-confidence cross-branch* case that was *intentionally* merged on strong
  non-type evidence. **The system needs a "type-conflict already adjudicated → suppress"
  latch**, analogous to the metonymy allow-list but for human-confirmed merges. TY2 implies but
  never states this. Mild overclaim of "net-additive, low risk."

- **O2. "The circular dependency dissolves into a strict DAG" (TY4 finding 3) is half true.**
  TY4 is correct that *per-call* (typing reads text, gate reads types) it's a DAG. But TY4's
  own §2.3 subtlety admits the gate reads the *cross-document entity-level reconciled* type,
  which depends on *prior* resolution+typing of the same entity — i.e. the acyclicity holds
  only *within one document's pass*, and the global system is iterative/fixed-point (D7 rebuild
  loop), not a DAG. TY4 actually says this ("rebuild-first gives the refinement loop for free")
  but the finding-1 headline "dissolves into a strict DAG" oversells it. The honest framing:
  *acyclic per-pass, convergent-iterative globally*. The "strict DAG" claim, taken alone, would
  mislead a synthesizer into thinking no fixed-point/convergence reasoning is needed (it is —
  see G4, G5 termination).

- **O3. GLEIF "every LEI record carries an ISO 20275 ELF code… a legal entity is the only thing
  that can have one" (TY3 §2.2, finding 3) is overstated — re-verified against GLEIF.** GLEIF's
  own page states ELF codes are assigned *only when one exists for that legal form and
  jurisdiction*, and reserves code **9999 for entities with no separate legal form**. So "every
  LEI carries an ELF" is false; the near-certain *type-bearingness* TY3 leans on is slightly
  weaker than claimed. The **directional** claim (LEI ⇒ Organization) still holds and the rung
  is still valid — but "near-certain by construction, every record" should be softened to "LEI
  ⇒ Organization with high precision; ELF refinement available when present." Minor staleness
  too: TY3 says "3,250+ legal forms / 175 countries"; GLEIF (Feb 2026) now says "3,600+ /
  200+ jurisdictions." Not load-bearing, but the "by construction / only thing" phrasing is an
  overclaim.

- **O4. "5/5 (or 6/6) surveyed systems type at extraction → convergent evidence for option
  (a)" (TY1 finding 1) over-weights a biased sample.** All surveyed systems are LLM-extraction
  KG builders, which structurally *can only* type at extraction (single call). GLiNER is
  counted as "option (a) at a cheaper tier" but GLiNER is a *separate model pass*, which is
  actually closer to a dedicated typing stage — TY3 itself uses GLiNER as a *separate rung*. So
  the "no precedent for a dedicated typing stage" claim (TY1 §2.1) is undercut by TY3's own
  recommendation to run GLiNER as a separate stage. The convergence is real but partly an
  artifact of sampling only single-call extractors; the absence of a dedicated-stage precedent
  is weak evidence, not strong.

- **O5. TY4's `type_decisions` ledger is presented as "reuses D21 wholesale, no new
  machinery" but it quietly introduces a NEW required table (`status=rejected_domain_range`
  quarantine of relations) that the design "has not yet stated" (TY4's own words).** TY4 is
  honest that this is a new precondition, but the §4 R-list framing ("no new subsystem") and
  the actual requirement (a rejected-relations store + re-validation engine + ripple bounding)
  are in tension. This is *more* than a ledger clone; it's a non-destructive gate + a
  re-validation traversal. Calling it "no new machinery" undersells the build cost.

---

## top-5-for-synthesis

1. **ADJUDICATE THE ORDER (C1) — typing straddles resolution; it is not strictly before or
   after.** Canonicalize: cheap mention-type (Tt0 authority / Tt1 surface / Tt2 GLiNER) runs
   *before* resolution to scope per-type thresholds and type-scoped authorities (TY3's win);
   the *entity-level reconciled* type is computed *after* resolution and is what D18's gate
   reads (TY4's win). State this single ordering explicitly — it is currently contradicted
   across TY1/TY3/TY4.

2. **CLOSE THE VALUE/ENTITY GATE GAP (G1).** Add an explicit rung-zero entity-worthiness gate
   (or a stated guarantee that E2 claim extraction partitions entities from attribute values
   *before* the typing cascade). Without it, the cascade types value spans into junk
   `Concept` entities. This is the largest hole and directly answers the task's
   deferred-extraction/value-gate pressure-test: **the current design does NOT handle it.**

3. **UNIFY THE RECONCILIATION RULE (C2) and BREAK THE ER-SIGNAL LOOP (O1).** Adopt TY2/TY5's
   rule over TY1/TY3's plain Graphiti promotion: monotonic generic→specific promotion *only
   within a parent chain*; confidence-weighted *multiset* vote (not deduped — LightRAG bug
   verified) across siblings; cross-core conflict → D24 review. Add the missing **"already-
   adjudicated → suppress" latch** so a merge intentionally kept on strong non-type evidence is
   not re-flagged for un-merge every rebuild by the same type signal. Type-disagreement-as-ER-
   signal is valuable but NOT loop-free as written.

4. **RESOLVE `Concept`-vs-`other:` TERMINAL FALLBACK (C3/G3).** Pick one: low-confidence
   mentions fall to monitored `other:<freetext>` (TY5) — NOT to `Concept` (TY1/TY3). This keeps
   `Concept` a positive type with real `related_to` semantics and prevents the OntoNotes-style
   ~half-the-mentions dumping pathology. The gate must then define behavior for `other:`-typed
   subjects (ungoverned → quarantine or `related_to`-only). Currently the two fallbacks are
   used interchangeably and have different domain/range consequences.

5. **STATE THE GLOBAL CONVERGENCE STORY, NOT JUST THE PER-PASS DAG (O2/G4/G5/O5).** The
   circular dependency is acyclic per-pass but iterative-convergent globally (D7 rebuild loop).
   Synthesis must: (a) make the gate non-destructive (TY4 R3 — quarantine, don't delete; this
   is a real new table, budget for it), (b) bound the retype ripple (TY4 nDR-n=1, unverified),
   and (c) bound cascade escalation volume against D24's queue (G5, unaddressed). The
   "retroactively clean" claim has the hidden precondition (non-destructive gate) TY4 correctly
   surfaces — elevate it to a first-class design requirement.

---

## Verification notes
- Code claims re-read from source this pass and CONFIRMED EXACT: LightRAG dedup-before-vote
  (`operate.py:1668` then `:1671` `max(set(entity_types),key=entity_types.count)`); Graphiti
  silent-swallow (`dedup_helpers.py:175-176`); GraphRAG identity fork
  (`extract_graph.py:108` `groupby(["title","type"])`). TY2's bug analysis and TY3/TY5's
  anti-pattern citations are accurate.
- External re-fetch: GLEIF ISO-20275 page contradicts TY3's "every LEI carries an ELF /
  only thing that can have one" (reserved 9999 exists; codes assigned only where they exist).
  Directional LEI⇒Org claim survives; "by construction" framing does not. (O3)
- OntoNotes 42.6% `other`: not primary-verified (PDF undecodable per TY5; secondary sources
  say "about half"). TY5 already flags this honestly — NOT scored as an overclaim.
- Not checked for typing patterns (asserted-by-omission): letta, hipporag, splink, zingg,
  dedupe, fastcoref, maverick-coref, ladybug (G7).
