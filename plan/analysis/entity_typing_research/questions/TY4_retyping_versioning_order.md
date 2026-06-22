# TY4 — Is type FIXED or RE-ADJUDICABLE? Versioning, order-of-operations, retyping ripple

**Question.** (1) Mechanism: is type a versioned, append-only decision (a `type_decisions`
ledger with `superseded_by`, mirroring `resolution_decisions`)? (2) The circular dependency:
domain/range (D18) validates relations but needs entity types, yet types come from the same
extraction that yields relations — what is the correct order of operations so it isn't
circular? (3) Retyping ripple: when an entity is retyped, what happens to relations previously
validated/rejected under the old type — re-validate, and how, given rebuild-first (D7)?

---

## 1. Key findings

1. **Type MUST be re-adjudicable, and the design already commits to it.** D15 says "retyping
   is retroactively clean in P2 after rebuild (D7)"
   (`decisions.md:306-308`); §7 of the registries design repeats it for predicate promotion
   (`registries_design.md:282-284`). Retyping therefore exists by construction — the only open
   question is the *mechanism*, which is currently unspecified. The system's own epistemics
   (D2/D3, "mentions are evidence, entities are verdicts, resolution is re-adjudicable",
   `registries_design.md:48`) make the answer forced: **type is a verdict, not a fixed
   attribute** — it must be a versioned, append-only decision exactly like resolution.

2. **The right data model is a `type_decisions` ledger structurally cloned from
   `resolution_decisions`** (`registries_design.md:57-61`): append-only,
   `mention_id|entity_id → type`, `method`, `confidence`, `features jsonb`, `resolver_version`,
   `decided_at`, `superseded_by`. The current `entities.type` column
   (`registries_design.md:54`) becomes a **materialized cache of the latest non-superseded
   verdict**, not the authority — exactly as `entities.merged_into` caches the resolution
   verdict. This reuses D21's reversibility machinery wholesale; no new machinery is invented
   (consistent with D15's "ontology is content, not new machinery", `decisions.md:280-281`).

3. **The circular dependency dissolves into a strict two-stage order: type first (subject +
   object), THEN validate the relation's domain/range.** This is the textbook NER→RE pipeline
   (entities/types recognized first, then for each typed pair the relation is classified/
   validated; [ACM Computing Surveys on Relation Extraction](https://dl.acm.org/doi/full/10.1145/3674501),
   [arXiv survey 2306.02051](https://arxiv.org/html/2306.02051v3)). It is *not* circular because
   typing consumes the **mention/text span**, not the relation; domain/range consumes the
   **already-assigned types**, not the text. In UGM terms: typing is a Plane-E *registry
   canonicalization* over mentions; domain/range is an *E3 relation-normalization gate* that
   runs strictly after both endpoints are typed. The known weakness of this order — **error
   propagation** (a wrong type silently kills a valid relation;
   [arXiv 2306.02051](https://arxiv.org/html/2306.02051v3)) — is precisely what makes
   re-adjudicability (finding 1) load-bearing rather than optional.

4. **The retyping ripple is "re-validation for free via rebuild" — but ONLY if rejected
   relations are not destroyed.** D7 rebuilds the whole P2 graph from Postgres every cycle, so
   merges/un-merges re-point edges for free (`decisions.md:131-133`). The same applies to
   retyping **iff** the E3 domain/range gate is *non-destructive*: a relation that fails
   domain/range must be **quarantined with a recorded rejection reason, not deleted** (analogous
   to a `contradiction_group`, `concepts.md:111-113`). Then a retype that changes an endpoint's
   type simply re-runs the gate over (a) live relations touching that entity and (b) quarantined
   relations touching it — admitting newly-valid ones, quarantining newly-invalid ones — and the
   next rebuild re-points the graph. **If rejected relations are hard-deleted, retyping is NOT
   clean** (the evidence to re-admit them is gone); this is the one place D7's "retro-clean"
   claim has a hidden precondition the design has not yet stated.

---

## 2. Evidence & detail with citations

### 2.1 The design already mandates retyping — three explicit hooks

- **D15 consequences:** "Retyping is retroactively clean in P2 thanks to rebuilds (D7). Only
  splitting heavily-used types/predicates is expensive" (`decisions.md:306-308`).
- **Registries §7 governance:** "Promotion = inserting/retyping rows; retyping is retroactively
  clean in P2 after rebuild (D7). The one expensive operation is *splitting* a heavily-used
  predicate" (`registries_design.md:282-284`).
- **Epistemic frame:** "mentions are evidence, entities are verdicts, resolution is
  re-adjudicable" + "the transcript/verdict epistemics of D2/D3 apply to resolution too"
  (`registries_design.md:48-49`). Type is an entity verdict (`entities.type`,
  `registries_design.md:54`), so by the system's own logic it inherits re-adjudicability.

Inference (flagged): the design states retyping is *clean* but **nowhere specifies the
mechanism** that records a retype, supersedes the prior type, or re-validates affected
relations. That gap is the substance of TY4. The repo findings confirm no surveyed system fills
it: "Neither system specifies a *post-hoc re-typing* pass… both type at extraction"
(`repo_findings/graphiti_cognee.md:222-226`). So this is genuinely novel design surface, not a
borrow.

### 2.2 What the surveyed systems do (and why none is a complete model)

| System | Type store | Versioned? | Reconciliation on merge | Re-validate relations on retype |
|---|---|---|---|---|
| Graphiti | Neo4j labels (`['Entity', <Type>]`) | No — overwrite | **Monotonic generic→specific promotion** (`dedup_helpers.py:170-189`, `repo_findings/graphiti_cognee.md:69-75`) | No |
| Cognee | `EntityType` node + `is_a` edge | No — first-writer-wins (`repo_findings/graphiti_cognee.md:167-170`) | None | No (and no domain/range at all) |
| LightRAG | type string on entity | No — overwrite | **Majority vote** `max(set,key=count)` (`operate.py:1671-1674`, `repo_findings/lightrag_graphrag_gliner.md:42-46`) | No |
| GraphRAG | type in identity key | No | **None — type forks identity** `groupby([title,type])` (`repo_findings/lightrag_graphrag_gliner.md:84-88`) | No |
| GLiNER | per-span `label`+`score` | n/a (mention-level, stateless) | n/a | n/a |

Two takeaways for UGM:
- **Graphiti's monotonic generic→specific promotion** (`repo_findings/graphiti_cognee.md:69-75,
  200-203`) is the closest validated reconciliation rule and should be UGM's *default* automatic
  retype trigger on merge (a `Concept` entity meets a specific-typed mention → promote). But it
  is overwrite-in-place, **not** versioned — UGM must wrap it in the ledger so the promotion is
  reversible (D21 demands every automatic decision be undoable, `registries_design.md:318-319`).
- **GraphRAG's `groupby([title,type])` is the explicit anti-pattern** — type in the identity key
  forks the same entity on type disagreement (`repo_findings/lightrag_graphrag_gliner.md:213-216`).
  UGM keeps type strictly OFF the identity key; type is a *re-adjudicable attribute of an
  entity whose identity is already fixed by D17*. A retype is therefore a single ledger append
  against a stable `entity_id`, never an entity split. (Note the asymmetry: retyping an *entity*
  is cheap; *splitting a type/predicate definition* is the expensive operation D15 flags,
  `decisions.md:306-308` — these are different operations and must not be conflated.)

### 2.3 The circular dependency — order of operations

The apparent circle: "domain/range needs types; types come from the extraction that yields
relations." It is broken by observing the two stages have **different inputs**:

```
Stage A  TYPE (mention → core type)        input = mention text span      → writes type_decisions
Stage B  domain/range gate (E3)            input = (subject_type, object_type, predicate)
                                                                            → writes/quarantines relation
```

Stage A never reads relations; Stage B never reads text. So the dependency is a DAG, not a
cycle. This is the standard pipeline NER→RE ordering — entities are typed first, then each typed
pair is checked/classified for a relation
([ACM CSUR 3674501](https://dl.acm.org/doi/full/10.1145/3674501);
[arXiv 2306.02051 §pipeline](https://arxiv.org/html/2306.02051v3)). GLiREL operationalizes
exactly this: it *consumes* pre-assigned types and enforces `allowed_head`/`allowed_tail`
(= domain/range) at RE time (`repo_findings/lightrag_graphrag_gliner.md:137-159`) — concrete
proof the order works in production-grade tooling and is the same `edge_type_map` shape D18
mandates (`decisions.md:370`).

Concrete UGM ordering inside the E2→E3 path, per mention/claim:

1. **Resolve** each mention → `entity_id` (D17 cascade T0–T5, `registries_design.md:84-94`).
2. **Type** each mention → one of the 8 core types (D18) or `other:`/fallback, written as a
   `type_decision` (Stage A). Entity-level type = current non-superseded verdict, reconciled
   on merge by generic→specific promotion (§2.2).
3. **Normalize** the claim to candidate relations `(subj_id, predicate, obj_id)` (D2).
4. **Validate** each candidate against `predicates.subject_type/object_type` (D18
   `edge_type_map`, `registries_design.md:113-128`) using the entity-level type verdicts from
   step 2 (Stage B). Pass → relation row; fail → **quarantine with rejection reason**, not
   delete.

Important subtlety the design must accept: **steps 2 and 3 read from the same extraction LLM
call**, but step 4 must read the *entity-level reconciled type verdict*, not the raw
mention-level type, because the object entity may have been typed more confidently by a prior
document. This is why typing is a registry canonicalization (cross-document, stateful), not a
pure per-call output — matching the repo recommendation to keep a *dedicated typing tier
separable from extraction* (`repo_findings/lightrag_graphrag_gliner.md:224-227`).

A note on error propagation: the pipeline order's documented weakness is that a wrong Stage-A
type silently suppresses a valid relation at Stage B
([arXiv 2306.02051](https://arxiv.org/html/2306.02051v3)). The literature's remedies are joint
extraction and **two-pass extract-then-correct refinement**
([GLiNER-Relex / iterative-inference / ITER](https://arxiv.org/html/2605.10108v1),
[arXiv 2211.14470](https://arxiv.org/abs/2211.14470)). UGM does not need a joint model — its
*rebuild-first* architecture (D7) already gives it the refinement loop for free, **provided
rejections are non-destructive** (§2.4). That is the architectural payoff: D7 turns the
pipeline's worst weakness into a recoverable, replayable state.

### 2.4 Retyping ripple under rebuild-first (D7)

D7: the P2 graph is fully rebuilt from Postgres each cycle; merges/un-merges re-point edges for
free (`decisions.md:120-135`). For a retype to be "retroactively clean" (D15) the same way, the
**re-validation must be a pure function of Postgres state** — which it is, *if* the rejected
relations remain in Postgres:

- A `type_decision` append that changes entity E's current type triggers re-validation of:
  - **live relations** where E is subject or object → re-run domain/range; if now invalid,
    move to quarantine;
  - **quarantined relations** touching E → re-run domain/range; if now valid, promote to live.
- The next D7 rebuild projects only live relations into P2 (consistent with D6: the graph is a
  dumb projection, `decisions.md:103-115`). No graph surgery; the graph never knew about the
  rejected edges.
- Reversibility (D21): the retype itself is a ledger row with `superseded_by`; un-retyping
  replays in the opposite direction. Every automatic retype is undoable
  (`registries_design.md:318-319`).

**The hidden precondition.** D7's "retyping is retroactively clean" silently assumes the
domain/range gate is **non-destructive**. If a relation that fails domain/range is *deleted*
rather than *quarantined*, the evidence needed to re-admit it after a retype is gone, and the
ripple is lossy — a stale relation can never come back even when the type that killed it is
corrected. This mirrors the system's existing supersession philosophy: **never delete the
record, close/flag it** (claims are never deleted, `concepts.md:104-109`; contradictions stay
live in a `contradiction_group`, `concepts.md:111-113`). A rejected-by-domain/range relation
should be stored the same way: a relation (or relation-candidate) row with
`status=rejected_domain_range`, `rejected_by_type_decision_id`, retaining its
`relation_evidence` links. This is a concrete, currently-unstated requirement that TY4 surfaces.

### 2.5 Versioned-ledger + retroactive-re-adjudication is a recognized pattern

External corroboration that "append-only ledger + decision-time supersession + retroactive
re-adjudication" is sound, not exotic:
- Append-only ledger tables are immutable-by-construction; inserts only, no in-place mutation
  ([Born SQL on system-versioned ledger tables](https://bornsql.ca/blog/system-versioned-ledger-tables-the-next-step/),
  [Microsoft Learn ledger](https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ledger-limits?view=sql-server-ver17)).
- A separate **decision-time axis** (`decided_at`, `decision_superseded_at`) layered over a
  valid-time axis is exactly the bi-temporal shape UGM already uses for relations
  ([HASH multi-temporal versioning in Postgres](https://hash.dev/blog/multi-temporal-versioning)).
  A `type_decision` is the same construction applied to the typing verdict.
- Retroactive adjudication — revising past determinations from the vantage of new information —
  is a coherent, well-discussed model
  ([Yale Law Journal, Retroactive Adjudication](https://yalelawjournal.org/article/retroactive-adjudication)),
  matching D3's relation-level re-adjudication that UGM extends to typing here.

---

## 3. Confidence & gaps

**Confidence: HIGH** that (a) type must be a versioned append-only `type_decision` ledger
mirroring `resolution_decisions`, (b) the order is type-endpoints-then-validate (standard
NER→RE, GLiREL-confirmed), and (c) the retype ripple is "re-validate affected + quarantined
relations, then rebuild." These follow directly and necessarily from cited design decisions
(D2/D3/D7/D15/D17/D21) plus standard IE pipeline practice.

**MEDIUM confidence / design choices to ratify:**
- Whether rejected-by-domain/range relations are *quarantined* (recommended) vs *re-derived
  from claims on demand*. Both make the ripple lossless; quarantine is simpler and matches the
  contradiction-group precedent, but adds rows. The cheaper alternative — keep only the claim
  (which is immutable anyway) and re-run normalization+gate for E's claims on retype — avoids a
  rejected-relations table entirely at the cost of re-running extraction-adjacent logic. **This
  is a real fork TY4 cannot settle without a corpus-slice cost measurement** (how many
  rejections per entity, how often retypes fire).
- Whether mention-level type verdicts are also superseded, or only the entity-level rollup. I
  recommend both rows exist (mention `type_decision` = evidence; entity type = verdict),
  paralleling mentions vs entities — but the entity-level rollup is the only one
  domain/range reads.

**Gaps I could not verify:**
- **No surveyed system implements post-hoc retyping at all** (`repo_findings/graphiti_cognee.md:222-226`),
  so the *mechanism* has no production reference implementation to copy — only the analogous
  resolution-ledger pattern within UGM itself. This is genuinely novel surface (like un-merge,
  D21, which "no OSS system ships").
- **Re-validation blast radius / cost is unmeasured.** Retyping a hub entity re-runs
  domain/range over all its edges; the design's nDR n=1 neighborhood-recluster heuristic (D21,
  `registries_design.md:269-271`) is the natural analog but its applicability to type-ripple is
  inference, not verified. Belongs with open spike #3 (un-merge → supersession ripple,
  `registries_design.md:338-340`).
- **Interaction of retype with bi-temporal relation windows** is untouched here and overlaps
  the un-merge/zombie-fact spike; a retype that quarantines a relation with a closed validity
  window needs the same care as un-merge (open spike #3).
- I did **not** find any benchmark number for retyping accuracy or error-propagation magnitude
  specific to this 8-type setting; none is invented.

---

## 4. Recommendation for UGM (concrete, tied to D15/D17/D18/D21/D22)

**R1 — Add a `type_decisions` ledger, structurally cloned from `resolution_decisions`** (extends
the D17/D21 reversibility machinery; ties to D15 "ontology is content, not new machinery"):

```
type_decisions (append-only — the typing verdict)
  type_decision_id,
  mention_id  → mentions,            -- mention-level evidence row
  entity_id   → entities,            -- the entity whose type is adjudicated (nullable until resolved)
  assigned_type → entity_types,      -- one of the 8 core (D18) or other:<freetext> / fallback
  method  ∈ {gliner, llm_extraction, generic→specific_promotion, external_authority, human, majority_vote},
  confidence,                        -- e.g. GLiNER per-span score (D22-tunable, see R5)
  features jsonb,
  resolver_version,                  -- per-type thresholds, versioned (D17/D22), stamped on every row
  decided_at,
  superseded_by  → type_decisions    -- null = current verdict
```

`entities.type` (`registries_design.md:54`) becomes a **materialized cache of the current
non-superseded entity-level verdict** — the authority is the ledger, exactly as `merged_into`
caches resolution. No new subsystem; reuses D21's append-only + `superseded_by` shape verbatim
(`registries_design.md:417-427`).

**R2 — Fix the order of operations as a strict DAG (resolve → type → normalize → validate),
typing as a Plane-E registry canonicalization that runs before the E3 domain/range gate.** The
gate (D18 `edge_type_map`) reads the **entity-level** type verdict, never the raw mention type.
This is the standard NER→RE pipeline, GLiREL-confirmed; it is not circular because typing
consumes text and the gate consumes types.

**R3 — Make the E3 domain/range gate NON-DESTRUCTIVE (the precondition that makes D7's
"retroactively clean" actually true).** A relation that fails domain/range is **quarantined**
(`status=rejected_domain_range`, `rejected_by_type_decision_id`, evidence links retained), not
deleted — same philosophy as claims-never-deleted (`concepts.md:104-109`) and
contradiction-groups (`concepts.md:111-113`). Only live relations project into P2 (D6/D7). This
single rule is what converts the pipeline's error-propagation weakness into a recoverable state.

**R4 — Define the retype ripple as a pure-Postgres re-validation, then rebuild (D7):** on a
`type_decision` that changes entity E's current type, re-run domain/range over (a) E's live
relations and (b) E's quarantined relations, moving each between live/quarantine as the new type
dictates; append the supersession; let the next D7 rebuild re-point the graph for free. Use
generic→specific promotion (Graphiti, `repo_findings/graphiti_cognee.md:69-75`) as the default
*automatic* retype trigger on merge — wrapped in the ledger so it is reversible (D21). Bound the
ripple with the D21 nDR-n=1 neighborhood heuristic as the starting point (verify on a corpus
slice).

**R5 — Type is OFF the identity key, and confidence-tuned on the golden set (D22).** Never
`groupby([title,type])` (GraphRAG anti-pattern). A retype is one ledger append against a stable
`entity_id` (D17), never an entity split. Type confidence (GLiNER per-span score, the only
surveyed source of a real number, `repo_findings/lightrag_graphrag_gliner.md:123-127`) gets a
per-type accept/escalate band measured on the **same golden-eval discipline as D17/D22** —
extend D22's "~200 pairs/type" obligation to cover type-assignment P/R, and add **retype-ripple
correctness** (a retype must leave no zombie live relation that now violates domain/range) to
D22's reversibility-invariant checks (`registries_design.md:318-319`).

**R6 — Record the new open spike.** Add to `registries_design.md` §12: "Retype ripple cost +
quarantine-vs-re-derive choice — measure rejections-per-entity and retype frequency on a corpus
slice; confirm retype + bi-temporal window interaction is closed under the same logic as un-merge
(coordinate with spike #3)."

---

## Sources

Repo (file:line cited inline): `decisions.md` (D2,D3,D6,D7,D15,D17,D18,D21,D22);
`plan/designs/registries_design.md` (§2 data model, §4 D18 predicates, §6 D21 reversibility, §7
governance, §10 D22, §12 spikes); `plan/analysis/concepts.md` (claims/relations epistemics,
supersession, contradiction-group); `plan/analysis/entity_typing_research/repo_findings/*.md`
(Graphiti promotion, GraphRAG fork anti-pattern, LightRAG majority vote, GLiNER scores, GLiREL
allowed_head/tail, "no system does post-hoc retyping").

Web:
- [A Comprehensive Survey on Relation Extraction — ACM Computing Surveys 3674501](https://dl.acm.org/doi/full/10.1145/3674501)
- [A Comprehensive Survey on Relation Extraction — arXiv 2306.02051](https://arxiv.org/html/2306.02051v3)
- [GLiNER-Relex: Joint NER and RE — arXiv 2605.10108](https://arxiv.org/html/2605.10108v1)
- [Document-level RE via Iterative Inference — arXiv 2211.14470](https://arxiv.org/abs/2211.14470)
- [System-versioned ledger tables — Born SQL](https://bornsql.ca/blog/system-versioned-ledger-tables-the-next-step/)
- [Ledger considerations and limitations — Microsoft Learn](https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ledger-limits?view=sql-server-ver17)
- [Multi-temporal versioning in Postgres — HASH Developer Blog](https://hash.dev/blog/multi-temporal-versioning)
- [Retroactive Adjudication — Yale Law Journal](https://yalelawjournal.org/article/retroactive-adjudication)
