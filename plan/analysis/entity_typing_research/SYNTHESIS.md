# Entity Typing — SYNTHESIS (lead-architect close)

Synthesizes two independent research streams — the **Codex architecture stream**
(`external_agents/codex_arch.md`) and the **Claude question stream** (`questions/TY1–TY5`,
`repo_findings/*`) — adjudicated by the two verify passes (`verify/completeness.md`,
`verify/facts.md`). The **Antigravity landscape stream** (`external_agents/agy_landscape.md`)
**failed (0 bytes, empty `.err`)** — no landscape input; proceeding on the other two streams,
which independently converged.

Downweighted per `verify/`: the GLEIF "every LEI carries an ELF / by construction" framing
(softened to "LEI ⇒ Organization, high precision"), the "3,250+/175-country" ELF magnitude
(stale), the OntoNotes 42.6% figure (secondary citation, not UGM-measured — used only as a
*risk indicator*), the P31→core mapping accuracy and DOI→Document (design-level, unverified —
both flagged as spikes). All 20 source-code claims were re-verified verbatim and stand.

Decision-numbering note: the **O5 PR ships D17–D24**; the **value-gate PR ships D25–D30**
(referenced as D25 in `registries_design.md` §3/§9). This typing work therefore lands as
**D31-typing** (placeholder `Dxx-typing` below); it amends D17/D18/D21/D22.

---

## 1. Recommended architecture (TL;DR)

- **Typing is a registry adjudication, not an extractor field.** E2 extraction emits a
  contextual *mention*-type vote (closed JSON-schema enum rendered from the registry — Graphiti's
  pattern upgraded from integer-IDs to a true enum); the registry decides the *canonical entity*
  type via an append-only `entity_type_decisions` ledger, exactly as `resolution_decisions`
  decides identity. Mention type = evidence; entity type = verdict (D2/D3 epistemics extended).

- **Typing STRADDLES resolution — it is neither strictly before nor strictly after** (adjudicates
  the #1 cross-stream contradiction). A *cheap mention-type* (Tt0 authority / Tt1 surface / Tt2
  GLiNER) runs **before** resolution so type scopes per-type thresholds and type-scoped
  authorities (Codex/TY3 win); the *entity-level reconciled* type is computed **after**
  resolution and is what the D18 domain/range gate reads (TY4 win). Two type artifacts, two
  positions — not one.

- **The cascade (Tt0–Tt4, sibling of D17, not a clone): type-tight / fall-back-loose.**
  Tt0 external-authority (shares D17-T0, type falls out free on a hit) → Tt1 deterministic
  surface/gazetteer (ELF suffixes→Org, honorific→Person) → Tt2 GLiNER zero-shot typed-NER (the
  *only* rung with a real per-span confidence, the knob D22 tunes) → Tt3 extraction-LLM closed
  enum → Tt4 human review for high blast-radius. Escalation axis is **semantic-signal strength**
  (not D17's string/embedding similarity — copying pg_trgm/Daitch-Mokotoff into typing is a
  category error). Precision-conservative because a *wrong* type silently kills every predicate
  on the entity through the D18 gate, whereas a *missing* type degrades gracefully.

- **Mention→entity reconciliation = the unified rule** (adjudicates the #2 contradiction —
  TY2/TY5 over plain Graphiti promotion): **(a)** monotonic generic→specific promotion *only
  within a parent chain* (`Concept`/core → subtype; specific never downgraded); **(b)**
  confidence-weighted **multiset** vote across siblings (NOT deduped — LightRAG's
  `operate.py:1668` dedup-before-vote bug collapses to first-seen-wins); **(c)** a *balanced,
  high-confidence, cross-core-incompatible* split → **D24 review queue as an over-merge
  candidate, never an auto-un-merge**; known metonymy pairs (Person↔Org, Org↔Place) allow-listed
  so facet-shift stays merged. A **"already-adjudicated → suppress" latch** stops a merge kept on
  strong non-type evidence from being re-flagged every rebuild (closes the verify O1 loop risk).

- **Retyping/versioning: append-only `entity_type_decisions` + `mention_type_decisions` ledger,
  `entities.type` is a materialized cache.** A retype is one ledger append against a stable
  `entity_id` (type is **OFF the identity key** — never GraphRAG's `groupby([title,type])` fork).
  Retyping triggers re-validation of the entity's live + quarantined relations, then the D7
  rebuild re-points the graph for free. **Load-bearing precondition (now first-class): the D18
  gate must be NON-DESTRUCTIVE** — a relation that fails domain/range is *quarantined*
  (`status=rejected_type_mismatch`, evidence retained), not deleted; otherwise "retyping is
  retroactively clean" (D15) is false because the evidence to re-admit is gone.

- **Ambiguity & `Concept`: abstain to `other:`, never dump to `Concept`** (adjudicates the #3
  contradiction — TY5 over TY1/TY3's "fall back to `Concept`"). **`Concept` is a positive
  assertion** ("an identifiable abstraction/topic the model is confident about"); the terminal
  fallback for *low-confidence* mentions is the monitored **`other:<freetext>`** floor (D5/D15),
  NOT `Concept` — this prevents the OntoNotes-`other`-style ~half-the-mentions dumping pathology.
  `Concept` is also the worst ER case (heterogeneous embeddings break blocking/HAC), so set its
  per-type thresholds **auto-merge-OFF** → route to T5/review. D18 runs as a **metonymy prior**,
  not only a gate: "the White House *said*" → the Org-domain predicate steers the type to
  Organization.

- **Subtype: coarse mandatory, leaf abstainable.** The extractor MUST commit to one of the 8
  core types (D18 needs it); the leaf subtype is a *separate, thresholded, abstainable* decision
  (one GLiNER call, `multi_label=True`, `return_class_probs=True`). Domain/range is checked at
  the **parent/core level** via D15 inheritance, so a missing subtype never blocks a predicate.
  **Open seam (verify G6): a pack predicate defined *on a subtype* (`blocks: Task→Task`) would
  under-gate if the entity is only core-typed `Event`** — resolve in design close (R below).

- **Order-of-operations resolving the circular dependency:** per document — **extract mentions +
  candidate relations → cheap-type mentions (Tt0–Tt2) → resolve mentions→entities (type-scoped)
  → reconcile canonical entity type (Tt3 + ledger) → validate candidate relations against
  endpoint entity types (D18) → accept | quarantine.** Acyclic *per-pass* (typing reads text,
  the gate reads types — GLiREL-confirmed NER→RE shape), **convergent-iterative globally** via
  the D7 rebuild loop (correcting the verify O2 "strict DAG" overclaim). A relation with an
  untyped/`other:` or sub-confident endpoint is `pending_type`, never forced through `related_to`.

---

## 2. The five questions answered (TY1–TY5)

### TY1 — WHEN/WHERE does typing happen?
**Settled:** Type at **E2 extraction time, in-call, as a closed JSON-schema enum rendered from
the registry** (8 core + enabled pack/scope subtypes), producing a *mention* vote — **plus** the
cheap cascade rungs that can run before resolution to scope it. The *entity-level* type is a
post-resolution reconciliation. **Not** option (b) typing-during-resolution (no system does it;
architecturally wrong — D18 needs the type earlier); **not** a mandatory standalone classify
stage in the hot path (Graphiti ships `classify_nodes` but doesn't use it inline).
**Confidence: HIGH.** Evidence: 5/5 surveyed systems type at extraction
(`extract_nodes.py:28-38`, `prompt.py:62`, `extract_graph.py:11-15`); Graphiti's verified
node→resolve→edge ordering (`graphiti.py:617/621/656`) proves types must precede the D18 gate;
UGM's own D15/D18 "prompts render from the registry."
**Agreement/divergence:** Codex and Claude **agree** type is extraction-time evidence + registry
verdict. **Divergence (the one real seam):** Codex and TY4 state a strict **resolve→type** DAG;
TY3 argues **type→resolve** (type scopes resolution). **Adjudicated:** typing *straddles*
resolution (cheap-type before, reconcile after) — neither stream's strict order alone is right.

### TY2 — Mention vs entity typing; disagreement-as-ER-signal
**Settled:** Type is OFF the identity key, reconciled as an entity attribute by the unified rule
(within-parent monotonic promotion + cross-sibling confidence-weighted multiset vote + cross-core
conflict → review). A **balanced, high-confidence, cross-core-incompatible** type split is an
**over-merge candidate** (Washington person/place, Java language/island) routed to D24, **never an
auto-un-merge**; metonymy pairs allow-listed (White House↔administration stay merged). Add the
"already-adjudicated → suppress" latch to break the feedback loop.
**Confidence: HIGH** on reconciliation mechanics and the anti-patterns; **MEDIUM** that the
vote-distribution/compatibility heuristic cleanly separates over-merge from metonymy (no
production precedent — UGM-original, must be golden-set-validated).
**Agreement/divergence:** Both streams **reject** GraphRAG identity-fork and LightRAG blind vote;
both adopt type as a *soft* anti-merge cue at T5. **Divergence:** Codex/TY3 default to plain
Graphiti monotonic promotion; TY2/TY5 call cross-core monotonic promotion *dangerous* and win —
**promotion only within a parent chain, vote across siblings.** verify O1 flags the two-sided
lever (anti-merge in + bad-merge-detector out) as a loop; the suppress-latch is the fix.

### TY3 — Is there a typing cascade?
**Settled:** **Yes — Tt0–Tt4, a sibling of D17 sharing only T0**, with a different escalation
axis (semantic-signal strength), an inverted conservatism (**type-tight / fall-back-loose**), and
GLiNER as the confidence-bearing broad rung. Phase 1 = Tt1 + Tt3 + `other:` floor (no new model,
unblocks D18); Phase 2 = Tt0 (lands with D20 authority connectors) + Tt2 (GLiNER, own model store
like the coref worker).
**Confidence: HIGH** on shape and that it must not clone D17's similarity mechanisms; **MEDIUM**
on exact rung ordering and whether a *separate* GLiNER pass beats inline-LLM typing (cost
unmeasured).
**Agreement/divergence:** Codex's `ET0–ET5` and Claude's `Tt0–Tt4` are the **same cascade**
(authority → deterministic → gazetteer/GLiNER → LLM → human), independently derived — strong
convergence. Naming differs only. **Caveat (verify O4):** "no precedent for a dedicated typing
stage" is weak — GLiNER *is* a separate pass; treat the cascade as a UGM synthesis whose rungs
are each independently validated, not a borrowed pattern.

### TY4 — Fixed or re-adjudicable? Versioning, order, ripple
**Settled:** **Re-adjudicable.** Append-only `entity_type_decisions` (+ `mention_type_decisions`)
ledger cloned from `resolution_decisions`; `entities.type` is the materialized current verdict.
Order = resolve → type → normalize → validate (per-pass DAG, GLiREL-confirmed). Ripple =
re-validate the entity's live + quarantined relations, then D7 rebuilds — **iff the gate is
non-destructive** (quarantine, don't delete). Default automatic retype trigger = within-parent
generic→specific promotion on merge, wrapped in the ledger for D21 reversibility.
**Confidence: HIGH** on the ledger, the order, and the ripple-via-rebuild; **MEDIUM** on
quarantine-table vs re-derive-from-claims (a real cost fork needing a corpus slice).
**Agreement/divergence:** Codex and TY4 **agree** completely on the append-only ledger + cache +
non-destructive gate + replayable candidate relations. **Adjudicated overclaim (verify O2):**
"dissolves into a strict DAG" is only true per-pass; globally it's convergent-iterative (D7 loop)
— synthesis states this explicitly. **verify O5:** the non-destructive gate is a *real new table +
re-validation traversal*, not "no new machinery" — budget for it.

### TY5 — Ambiguity, subtype granularity, the `Concept` dumping-ground
**Settled:** Metonymy/polysemy → context-scoped mention typing + D18-as-prior + **honest abstain**
(no clean type-recovering fallback exists). Subtype → **core mandatory, leaf abstainable**, checked
at the parent level. `Concept` → **a positive type, protected by an `other:` floor below it**, with
three new health metrics (Concept-share, other:-share + top values, intra-Concept embedding
dispersion) and auto-merge-OFF thresholds.
**Confidence: HIGH** on all three core claims (metonymy needs context + no clean fallback; coarse
reliable / leaf hard; broad catch-all becomes a near-plurality dump — OntoNotes `other`=42.6% as a
*risk indicator*, secondary-cited, not a UGM prediction).
**Agreement/divergence:** Codex independently reached the **same** "`Concept` is not unknown; use
an explicit `unresolved_type`/`other:` state outside the ontology" conclusion. **Divergence within
the Claude stream (verify C3):** TY1/TY3's "terminal fallback = `Concept`" contradicts TY5's
"fallback = `other:`." **Adjudicated for `other:`** — it keeps `Concept` a real `related_to`-
carrying type and prevents the dumping pathology.

### Cross-cutting gap both streams under-addressed (verify G1 — flagged, not closed here)
**The entity-vs-value gate.** A large fraction of extracted spans are attribute values, literals,
dates, quantities, roles ("CEO", "42%", "March 2024") that must NOT become typed entities. If the
cascade is handed a value span it will type it (probably `Concept`/`other:`) and mint a junk
entity. **This is owned by the value-gate PR (D25–D30), not by typing** — but the typing design
must *assume E2 partitions entities from values before the cascade runs* and state that contract
explicitly (R7 below). Listed as an open risk.

---

## 3. Design close — ready to apply

### (a) New section for `registries_design.md` (insert as new §4a, after §4 Ontology)

> ## 4a. Entity typing — two-level, append-only, cascade-adjudicated (Dxx-typing)
>
> Typing is a registry adjudication paralleling resolution (§2 epistemics): **mention type is
> evidence, entity type is a re-adjudicable verdict.** It is the subsystem that makes the D18
> domain/range gate runnable (the gate needs a type) without making the gate circular.
>
> **Pipeline (per document):** extract mentions + candidate relations → cheap-type mentions
> (Tt0–Tt2) → resolve mentions→entities (type-scoped) → reconcile canonical entity type (Tt3 +
> ledger) → validate candidate relations vs endpoint entity types → **accept | quarantine**.
> Acyclic per-pass; convergent-iterative globally via the D7 rebuild loop.
>
> **Typing cascade (Tt0–Tt4 — sibling of D17, shares only T0; type-tight / fall-back-loose):**
>
> | Rung | Mechanism | Confidence | Escalates when |
> |---|---|---|---|
> | Tt0 | External authority (shares D17-T0): LEI⇒Org (high precision), ORCID⇒Person, DOI⇒Document, Wikidata P31→core via mapping table | near-certain on hit | authority misses (most do, D20) |
> | Tt1 | Deterministic surface/gazetteer: ELF suffixes⇒Org, honorific/PER-gazetteer⇒Person, DOI-shape/extension⇒Document; **never rejects** | high on match | no pattern matches |
> | Tt2 | GLiNER zero-shot typed-NER, labels = registry menu, per-type threshold; the only rung with a real golden-set-tunable confidence | per-span score (D22-tuned per type) | score in/below escalate band |
> | Tt3 | Extraction LLM, **closed enum** (never free-string) | model-reported | cross-core conflict on merge, or high blast-radius |
> | Tt4 | Human review (reuse D24 CLI) | adjudicated, reversible | — |
> | floor | **`other:<freetext>`** (monitored, D5) — NOT `Concept` | — | terminal: low-confidence abstains here |
>
> **Reconciliation rule (mention votes → entity type):** monotonic generic→specific promotion
> *only within a parent chain*; confidence-weighted **multiset** vote across siblings (never
> deduped); balanced high-confidence **cross-core** conflict → D24 review as an over-merge
> candidate (never auto-un-merge); metonymy pairs (`type_metonymy_pairs`) allow-listed; an
> "already-adjudicated → suppress" latch prevents re-flagging human-confirmed merges.
>
> **Rules:** every accepted entity has exactly one current core type; ≤1 current leaf subtype
> (ancestors satisfy parent signatures). Type is **OFF the identity key** (never
> `groupby([title,type])`). `Concept` is a positive assertion, never the unknown sink; unknown =
> `other:`/`unresolved_type`, which cannot pass D18 (`pending_type`). The D18 gate is
> **non-destructive** (quarantine, don't delete) — the precondition that makes D15's "retyping is
> retroactively clean" actually true. Subtype is **coarse-mandatory, leaf-abstainable**; gating is
> at the parent level **except** a predicate whose signature *names a subtype* requires that leaf
> (a `Task→Task` predicate does not validate on a core-`Event`-only endpoint — it is `pending_type`
> until the subtype is confirmed). D18 runs as a **metonymy prior**, not only a gate.

### (b) Data-model additions (Postgres — extends §2)

```sql
-- mentions: add the contextual type vote (immutable evidence)
ALTER TABLE mentions
  ADD proposed_core_type   text REFERENCES entity_types(type),
  ADD proposed_subtype     text REFERENCES entity_types(type),
  ADD proposed_type_confidence numeric,
  ADD proposed_type_method text,                  -- tt0..tt4 / other
  ADD type_resolver_version text;

-- mention-level decisions (append-only — evidence verdicts)
CREATE TABLE mention_type_decisions (
  decision_id  bigserial PRIMARY KEY,
  mention_id   uuid NOT NULL REFERENCES mentions,
  decided_core_type text REFERENCES entity_types(type),
  decided_subtype   text REFERENCES entity_types(type),
  status text NOT NULL,                           -- accepted|pending|unresolved_type|conflict_review
  method text NOT NULL, confidence numeric NOT NULL,
  features jsonb NOT NULL, type_resolver_version text NOT NULL,
  decided_at timestamptz NOT NULL, superseded_by bigint
);

-- entities: cache the current canonical verdict (authority is the ledger)
ALTER TABLE entities
  ADD subtype          text REFERENCES entity_types(type),
  ADD type_confidence  numeric,
  ADD type_decision_id bigint,                    -- → entity_type_decisions (current)
  ADD type_facets      jsonb;                     -- metonymy: secondary type facets kept

-- entity-level decisions (append-only — the canonical verdict, clones resolution_decisions)
CREATE TABLE entity_type_decisions (
  decision_id  bigserial PRIMARY KEY,
  entity_id    uuid NOT NULL REFERENCES entities,
  decided_core_type text NOT NULL REFERENCES entity_types(type),
  decided_subtype   text REFERENCES entity_types(type),
  status text NOT NULL, method text NOT NULL, confidence numeric NOT NULL,
  evidence jsonb NOT NULL, type_resolver_version text NOT NULL,
  decided_at timestamptz NOT NULL, superseded_by bigint,
  caused_by_merge_id uuid, caused_by_resolution_decision_id uuid,
  adjudicated_latch boolean NOT NULL DEFAULT false  -- "already reviewed → suppress re-flag"
);

-- candidate relations: relations pending/failing type validation (the non-destructive store)
CREATE TABLE candidate_relations (
  candidate_relation_id uuid PRIMARY KEY,
  claim_id uuid NOT NULL, subject_mention_id uuid NOT NULL,
  predicate text NOT NULL REFERENCES predicates(predicate),
  object_mention_id uuid NOT NULL, extraction_features jsonb NOT NULL,
  validation_status text NOT NULL,        -- accepted|pending_type|rejected_type_mismatch
  rejection_reason text, replay_after_type_decision_id bigint,
  created_at timestamptz NOT NULL
);

-- relations: stamp which type verdicts gated them (for ripple re-validation)
ALTER TABLE relations
  ADD validation_status text NOT NULL DEFAULT 'accepted',
  ADD subject_type_decision_id bigint REFERENCES entity_type_decisions,
  ADD object_type_decision_id  bigint REFERENCES entity_type_decisions,
  ADD type_validation_version  text;

-- registry: metonymy allow-list + extend resolver_versions with typing config
CREATE TABLE type_metonymy_pairs (
  type_a text NOT NULL REFERENCES entity_types(type),
  type_b text NOT NULL REFERENCES entity_types(type),
  PRIMARY KEY (type_a, type_b)
);                                          -- seed: Person/Organization, Organization/Place
ALTER TABLE resolver_versions               -- reuse the existing versioning table (no new one)
  ADD typing_tier_config jsonb,
  ADD type_thresholds_by_type jsonb,
  ADD enabled_type_menu jsonb,
  ADD authority_type_map_version text;
```

Indexes: `mention_type_decisions(mention_id, decided_at desc)`;
`entity_type_decisions(entity_id, decided_at desc)`;
`candidate_relations(validation_status, replay_after_type_decision_id)`;
`entities(type, canonical_name)` for type-aware blocking. Partition
`mention_type_decisions`/`candidate_relations` by ingest month like the other 10⁸ tables (D23).

### (c) Proposed DECISION text (placeholder Dxx-typing; lands as D31 after the value-gate D25–D30)

> ## D31. Entity typing — two-level append-only verdicts, a cascade sibling to D17, non-destructive gate
>
> **Decision.** UGM adds an entity-typing subsystem parallel to entity resolution. The E2
> extractor proposes a **mention** type from the registry-rendered closed enum (8 core + enabled
> pack/scope subtypes). A cheap-first **typing cascade Tt0–Tt4** (external-authority → deterministic
> surface/gazetteer → GLiNER → extraction-LLM → human; **shares only T0 with D17**, escalates on
> **semantic-signal strength**, is **type-tight / fall-back-loose**) adjudicates it. Typing
> **straddles resolution**: cheap rungs run before resolution to scope it (per-type thresholds,
> type-scoped authorities); the **canonical entity type** is reconciled after resolution and stored
> as an append-only verdict in **`entity_type_decisions`** (`entities.type` is a cache, exactly as
> `merged_into` caches resolution). Reconciliation = within-parent monotonic generic→specific
> promotion + cross-sibling confidence-weighted **multiset** vote + cross-core conflict → D24 review
> (never auto-un-merge), with metonymy pairs allow-listed and an already-adjudicated suppress latch.
> Type is **OFF the identity key**. The terminal low-confidence fallback is the monitored
> **`other:<freetext>`** floor, **never `Concept`** (`Concept` is a positive type). Subtype is
> **coarse-mandatory, leaf-abstainable**, gated at the parent level except where a predicate names a
> subtype. The **D18 domain/range gate is non-destructive**: a failing relation is **quarantined**
> (`candidate_relations`, evidence retained), not deleted. Retyping is one ledger append against a
> stable `entity_id` that re-validates the entity's live + quarantined relations; the D7 rebuild
> re-points the graph. Order is acyclic per-pass, convergent-iterative globally.
>
> **Context.** D18 mandated domain/range but D17–D24 never said how types are assigned. Graphiti
> supplies the extraction interface (closed `entity_type_id`, `edge_type_map` keyed by node labels)
> and the within-parent promotion rule, but no audit/rebuild semantics. GLiNER is the only surveyed
> system with a real per-span type confidence. GraphRAG's `groupby([title,type])` (forks identity)
> and LightRAG's dedup-before-vote are the explicit anti-patterns. Two independent research streams
> (Codex architecture, Claude TY1–TY5) converged on this shape; the Antigravity landscape stream
> failed to produce output.
>
> **Consequences.** Relation validation is no longer circular. Type disagreement becomes a
> first-class ER quality signal feeding D24. Retyping is retroactively clean in P2 (D7) **given the
> non-destructive gate** — a new requirement this decision elevates. `Concept` stays meaningful and
> measurable. Golden-set/eval (D22) must add typed-mention and canonical-entity type accuracy by
> core type and subtype, plus retype-ripple correctness (no zombie live relation violating
> domain/range after a retype).

### (d) How it amends D17 / D18 / D21 / D22

- **Amends D17.** Adds a *sibling* cascade (Tt0–Tt4), not a tier of D17. Shares **only T0**; does
  **not** import T1–T4 similarity mechanisms (pg_trgm/Daitch-Mokotoff/embedding) — those are
  identity operators, typing is K-way classification. Type is computed *around* resolution (cheap
  before, reconcile after) and **scopes** D17: a mention typed Person is blocked/scored against
  Person thresholds; an Org suffix steers it to LEI not ORCID. Type remains **OFF the identity
  key** and enters D17-T5 only as a **soft** discriminator (the NYC/Knicks, Java/island cue) —
  never a hard block (preserves metonymy + generic→specific).

- **Amends D18.** Makes the `edge_type_map` gate **runnable and non-circular** (it reads the
  reconciled *entity-level* type, produced before it runs) **and non-destructive** (failures
  quarantine to `candidate_relations`, not delete). Adds D18-as-**metonymy-prior** usage. Clarifies
  subtype gating: parent-level by default (D15 inheritance), **leaf-level when a predicate names a
  subtype** (closes verify G6 under-gating). A `Concept`/`other:`/`pending_type` endpoint yields
  `pending_type`, not a forced `related_to` edge.

- **Amends D21.** The typing ledger **reuses D21 reversibility wholesale** (append-only +
  `superseded_by`, same shape as `resolution_decisions`/`merge_events`) — but adds two concrete
  pieces D21 didn't have: the **non-destructive relation quarantine** (`candidate_relations`) and
  the **retype ripple** (re-validate live + quarantined relations on a type change, bounded by the
  D21 nDR n=1 neighborhood heuristic as a starting point). Type-disagreement becomes a new cheap
  contributor to D21's `expected_impact = blast_radius × (1 − confidence)` review ranking. The
  within-parent promotion is wrapped in the ledger so it is undoable.

- **Amends D22.** Extends the golden EVAL set with: a **typing slice** (mention-level type labels +
  canonical entity-type labels, per core type and subtype, P/R curves per `resolver_version`); a
  **same-name cross-type slice** (Washington/Java/Apple as hard split-positives; White
  House/administration as hard keep-merged-negatives) to tune `type_conflict_score` +
  `type_metonymy_pairs`; **~400 hard pairs/type for `Concept`** (auto-merge-critical, worst
  cohesion); and **retype-ripple correctness** as a reversibility invariant. Adds three continuous
  health metrics: `Concept`-share, `other:`-share + top `other:` values (the promotion funnel), and
  intra-`Concept` embedding dispersion. Labeling stays human-adjudicated (cascade may propose).

---

## 4. Open risks & what to spike

1. **Entity-vs-value gate (verify G1 — largest hole).** The cascade will mint junk entities from
   value/literal/role spans unless E2 partitions entities from values *upstream*. **Owned by the
   value-gate PR (D25–D30); typing assumes the contract.** Spike: confirm E2's claim extraction
   already emits an entity-worthiness partition before any typing rung runs; if not, add a rung-zero
   gate. **Blocks correctness.**
2. **Quarantine vs re-derive-from-claims (TY4 fork).** Both make the ripple lossless. Quarantine
   (`candidate_relations`) is simpler and matches the contradiction-group precedent but adds 10⁸-scale
   rows; re-deriving from immutable claims on retype avoids the table at extraction-replay cost.
   Spike: measure rejections-per-entity and retype frequency on a corpus slice before committing.
3. **Retype ripple cost / blast radius.** Retyping a hub re-validates all its edges. Spike: validate
   the D21 nDR n=1 bound for type-ripple; confirm retype + bi-temporal validity-window interaction is
   closed under the same logic as un-merge (**coordinate with `registries_design.md` §12 spike #3**).
4. **Cascade escalation budget (verify G5).** Precision-conservative escalation + GLiNER's long-tailed
   confidence could flood Tt3/Tt4 beyond the D24 queue's capacity. Spike: measure escalation rate per
   rung; define the budget-exceeded fallback (`other:`, not silent drop).
5. **Over-merge-vs-metonymy split rate + loop stability (TY2 MEDIUM / verify O1).** No precedent; the
   `type_conflict_score` heuristic and the suppress-latch are UGM-original. Spike: golden-set-validate
   on the same-name cross-type slice; confirm no oscillation on balanced cross-core merges kept on
   strong non-type evidence.
6. **GLiNER value vs inline-LLM typing (cost) + licensing/serving.** Whether a separate GLiNER pass
   beats inline-enum LLM typing is unmeasured; commercial serving/licensing unchecked (parallels the
   CorPipe open item, §5). Spike: benchmark menu-size effect (8 core only vs core+Work pack vs large
   deployment menus) on accuracy and cost.
7. **Wikidata P31→core mapping accuracy + DOI/Crossref type granularity (verify B2/B6).** Tt0's
   authority-type map is near-certain only at the class head; the long tail (fictional/legendary/
   group-of-humans; dataset/software DOIs → Product not Document) needs a versioned mapping table.
   Spike: measure mapping precision before trusting Tt0 as a decision rung.
8. **`Concept`-share on a real UGM corpus.** The 42.6%-dump figure is from OntoNotes, a *risk
   indicator*, not a UGM prediction. Spike: measure `Concept`-share + `other:`-share on a corpus slice
   before trusting any abstain threshold (same spirit as the §12 do-before-numbers spikes).

---

## TL;DR (8 bullets)

1. **Typing is a registry verdict, not an extractor field** — mention type (closed-enum E2 vote) is
   evidence; entity type lives in an append-only `entity_type_decisions` ledger, `entities.type` is a
   cache.
2. **Typing straddles resolution** — cheap rungs (authority/surface/GLiNER) run *before* to scope it;
   the canonical type is reconciled *after*; the D18 gate reads the post-resolution type (settles the
   one real cross-stream contradiction).
3. **Cascade Tt0–Tt4 is a sibling of D17, not a clone** — shares only T0, escalates on semantic-signal
   strength, **type-tight / fall-back-loose** (a wrong type silently kills predicates; a missing one
   degrades gracefully).
4. **Reconciliation = within-parent monotonic promotion + cross-sibling confidence-weighted multiset
   vote + cross-core conflict → D24 review (never auto-un-merge)**, metonymy pairs allow-listed, plus
   an already-adjudicated suppress latch to kill the feedback loop.
5. **Retyping is append-only and clean *iff* the D18 gate is non-destructive** — failing relations
   quarantine to `candidate_relations` (not deleted); retype re-validates live + quarantined, D7
   rebuilds the graph. Type is OFF the identity key.
6. **`Concept` is a positive type; the unknown sink is `other:<freetext>`** — abstain to `other:`,
   never dump to `Concept`; `Concept` runs auto-merge-OFF and gets dedicated health metrics.
7. **Subtype: core mandatory, leaf abstainable** — gated at the parent level except where a predicate
   names a subtype (then `pending_type` until confirmed); the circular dependency is acyclic per-pass,
   convergent-iterative globally via the D7 loop.
8. **Ships as D31-typing (after value-gate D25–D30), amending D17/D18/D21/D22** — biggest open risk is
   the **entity-vs-value gate** (owned by the value-gate PR; typing assumes the contract); the
   Antigravity landscape stream failed and was excluded.
