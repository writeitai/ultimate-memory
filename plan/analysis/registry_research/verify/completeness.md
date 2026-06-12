# Completeness & Coherence Critique — registry_research questions + repo_findings

**Role:** adversarial fact-checker / completeness critic over all of `questions/R1–R10` and
`repo_findings/*` (cognee, coref, graphiti, letta_hipporag, lightrag_graphrag, mem0,
splink_dedupe, zingg). Cross-referenced against the design docs (`entity_registry.md`,
`decisions.md` D1–D16, `objections.md` O1–O6, `concepts.md`) and spot-checked against the
cloned repos under `_additional_context/`.

**Headline verdict.** The ten question docs are unusually high quality: hedged, source-cited,
and disciplined about separating verified facts from inference. The dominant risk is **not**
fabrication — it is **(a) a structural hole in the cross-check process, (b) several decisions
the registry depends on that no question actually answers, and (c) a handful of cross-doc
inconsistencies the synthesis must pick a side on.** Details below.

---

## 0. Verified spot-checks (what holds up)

These load-bearing repo claims were checked against actual source and are **confirmed**:

- Graphiti `_FUZZY_JACCARD_THRESHOLD = 0.9`, `_NAME_ENTROPY_THRESHOLD = 1.5`,
  `_MIN_NAME_LENGTH = 6`, MinHash/LSH fuzzy path, and `edge_type_map: dict[(src,tgt) -> [rel]]`
  domain/range gating — all present in `graphiti_core/utils/maintenance/dedup_helpers.py` and
  `edge_operations.py`. (R2, R5, R6, R8 all rely on these — correct.)
- mem0 `score >= 0.95` gate — present 4× in `mem0/memory/main.py` (lines 452, 944, 1933, 2396).
  **Minor overclaim flag:** R2/§2.1 calls this "entity merge ≥0.95 cosine"; in source it is a
  retrieve/skip-or-update gate in the memory add/search path, not a graph-entity merge. The
  number is right; the framing ("no type awareness, no adjudication") is fair, but it is not
  literally an entity-resolution merge threshold. Synthesis should not cite mem0 0.95 as an "ER
  auto-merge precedent" without that caveat.
- Coref repos (maverick/fastcoref) are intra-document neural cluster resolvers, transitive by
  construction, no un-merge — confirmed in `coref.md` and consistent with the repos.

The benchmark numbers (Ditto/Magellan/GPT-4 ER F1, CRAC 2025 13-point gap, CORE-KG 28%,
nDR/PMC7250616, binomial CI sizing) are quoted with sources and the docs themselves flag which
are unverifiable. I did not re-fetch every arXiv PDF; the docs' own confidence tags are honest
and I take them at face value where they say "could not verify."

---

## 1. gaps[] — what is missing / under-answered

**G1 — [PROCESS, severe] The promised cross-checks did not run.** R2, R5, R6, R8 each state a
second independent agent covers the same question ("a Codex agent covers the same question",
"an Antigravity agent also covers this", "Codex cross-check"). The actual outputs in
`external_agents/` are **0 bytes**: `codex_R2_er_cascades.md`, `codex_R6_extraction.md`,
`agy_R5_ontology_cores.md`, `agy_R8_clustering.md` are all empty; only the `.err` files have
content. So the four most architecturally load-bearing questions (ER cascade, ontology core,
extraction design, clustering) have **no independent verification despite the docs implying
one exists**. R2/§4.4 even routes its biggest gap "to the Codex cross-check" — which is empty.
This is the single most important thing the synthesis must not paper over.

**G2 — [DESIGN, severe] O3 (the salience / value gate) is essentially unaddressed.** O3 is
named in `objections.md` as the **highest-priority** objection ("plausibly a 10× cost lever";
top-3 with O6). The entire research program is downstream of it: extracting on everything vs.
gating changes the row counts in R9, the golden-set composition in R7, the `other:` rate in R6,
and the coref/ER load in R1/R8. Yet O3 appears only twice, in passing, in R1 — and **no question
researches the salience gate, lazy/deferred extraction, or the Mem0 "~98% junk" finding**. R9
sizes tables assuming full extraction of 1M docs; if O3's gate lands, those numbers are wrong by
the gate's filter rate. This is a real hole, not a nuance.

**G3 — [DESIGN] Cross-document coref is claimed out of scope but never owned.** `coref.md` and R1
correctly scope dedicated coref to *intra-document*. But the design's actual need —
*cross-document* "the CEO" / "she" / "the project" grounding when a claim's pronoun refers to an
entity introduced in a *different* document — is named as out of scope by coref.md and then
**not picked up by any tier in R2/R8**. The ER cascade resolves *named mentions*; nothing
resolves a cross-doc definite-NP/pronoun that the per-doc coref pass could not see. This is a
silent recall hole between R1 and R2.

**G4 — [DESIGN] Relation/claim dedup (D2) is under-researched relative to entity ER.** Nine of
ten questions are about *entity* resolution. D2's `(s,p,o)` relation identity and
`relation_evidence` aggregation — explicitly called "the most load-bearing artifact" in O1 — get
only R2/§2.7's "use Fellegi-Sunter for the relation side" gesture. No question covers: how
near-duplicate relations are blocked/deduped, how `(s,p,o)` identity is computed when p is an
`other:` freetext predicate, or how contradiction-group formation (concepts.md §4) is decided.
The supersession *mechanism* (concepts.md) is assumed correct by every question but stress-tested
by none.

**G5 — [DESIGN] No question covers the `other:` → core predicate promotion workflow.** R5/R6 both
say "measure `other:` rate" and "it's the promotion funnel," but the actual governance
mechanism (who promotes, what splitting a heavily-used predicate costs — D15 itself flags
splitting as "the genuinely expensive" operation, and D7 retro-clean does **not** cover predicate
splits cleanly) is unowned. O5's "predicate promotion workflow" deliverable has no research
behind it.

**G6 — [DESIGN] Bi-temporal supersession + ER interaction is unexamined.** When two entities are
**un-merged** (R8), what happens to relations whose validity windows were closed by adjudication
*assuming the merged identity*? R8 handles cluster membership reversibility but not the
downstream relation/validity re-adjudication that an un-merge forces. The "re-resolution campaign
+ rebuild" hand-wave (R7, R8) assumes relations recompute cleanly; nobody verifies that
supersession decisions are replayable after an identity change.

**G7 — [EVIDENCE] Retrieval-quality eval (the second half of O6) is dropped.** R7 covers the ER
golden set thoroughly but O6 also demands "retrieval evals (recall@k on known-answer queries per
search recipe)." No question touches retrieval eval, rerank-weight tuning (D9), or
contradiction-detection precision. R7's scope silently narrowed O6 to ER-only.

**G8 — [DESIGN] Coref cost claim is internally hand-waved.** R1 asserts in-extraction coref is
"~$0 marginal" because E2 already calls an LLM. But R6 recommends ~600-token chunks for recall;
small chunks *break* the long-range coref that R1 relies on the extractor to do in-context, and
R1's own Ref-Long evidence says long-context referencing is weak. R1 and R6 each assume the other
isn't true. No one reconciles chunk-size vs. in-context-coref reliability.

**G9 — [SCALE] R9's row-count model is unowned by the data model.** R9 assumes 10–100
mentions/doc and that `entities`/`aliases` stay ≤10^7. If O3 is rejected (full extraction) and
docs are entity-dense, aliases could blow past that, and R9's "we never fuzzy-scan 100M rows"
conclusion — its headline — is contingent on an unverified corpus assumption. Flagged in R9 §3
but not resolved.

---

## 2. contradictions[] — where the docs disagree with each other

**C1 — Coref default: OFF (R1) vs. mandatory multilingual model (R3).** R1's verdict is
"MAKE-OPTIONAL, default OFF, rely on in-extraction LLM coref." R3 §4 step 7 says coref
"**must** be language-aware" and to use a CorPipe-class multilingual model for Czech, treating a
dedicated coref engine as required for the target (Czech) corpus, not optional. For a
Czech-first product these collide: R1's *default* is exactly what R3 says will silently split
inflected entities. The synthesis must decide whether the **default** is OFF (R1) or
ON-for-Czech (R3) — they cannot both be the shipping default.

**C2 — "Coref before extraction" as hard ordering (R6) vs. coref-inside-the-E2-call (R1).** R6
§4.1 states the pipeline order as "coref → E2 Claimify → E3" with coref as a discrete prior
stage (citing D4 "coref before extraction"). R1's entire cost argument depends on coref happening
*inside* the E2 LLM call, not as a separate stage. These are different pipeline topologies. D4's
own wording ("coreference resolution runs before claim extraction") reads as R6's ordering, which
**undercuts R1's "$0 marginal / rides the E2 call" claim.** Pick one topology.

**C3 — mem0's 0.95 as "aggressive auto-merge, no adjudication" (R2) vs. its actual role.** R2
§2.1 lists mem0 entity merge `≥0.95 cosine` as a precedent data point in the cosine-threshold
band analysis. In source it is a retrieve-and-update gate, not a graph entity merge. Not a
contradiction between two question docs, but R2's table and R8's "mem0 ... no un-merge" framing
lean on slightly different readings of the same code. Minor; reconcile the characterization.

**C4 — Tier-4 embedding numbering.** R2's cascade puts embedding KNN at **Tier 2 (blocking)** and
LLM at Tier 4; R3 §2.6 and R9 call embedding similarity **Tier 4**; `entity_registry.md` §4 lists
"embedding" as tier ~4 (of 0–5). The tier numbers are used inconsistently across R2/R3/R9 (R2
even has embedding as both a loose blocking floor *and* a later tier). This is cosmetic but will
cause real confusion in `registries_design.md` if not unified into one canonical tier table.

**C5 — Where the golden set comes from vs. circularity.** R7 §4 says build the eval set by
"reuse the D4 cheap-first cascade itself to emit candidate pairs" and have the Tier-5 adjudicator
**propose** labels. R7's own §2.2 warns that using an LLM's output to measure itself is circular,
and that AL-sampled / blocking-sampled sets are **biased and invalid for measuring
generalization**. R7's recommendation (blocking-stratified, cascade-generated candidates) is
exactly the biased-sampling it warns against for the *eval* set. The doc flags the tension but
its concrete plan does not resolve it — the synthesis must.

---

## 3. overclaims[] — claims strong relative to their evidence

**O-1 — "The industry has already dropped dedicated coref" (R1).** Supported by 6 repos, but all
6 are LLM-extraction memory systems that share one design philosophy; this is convergence within
a *monoculture*, not independent confirmation that dedicated coref has no value. R1 mostly hedges
this, but the one-line summary states it as settled fact. The CORE-KG +28% duplication result
(R1's own evidence) actively cuts against "drop it."

**O-2 — "We never fuzzy-scan 100M rows" (R9 headline).** True only under the modeled row counts,
which R9 admits are "modeled, not measured" and corpus-dependent, and which assume O3's outcome.
Presented as a near-certain architectural conclusion; it is contingent.

**O-3 — Postgres `daitch_mokotoff` + `pg_trgm` "solve" multilingual matching (R3/R9).** The
components are verified to exist and be UTF-8-safe. But R3 itself flags that **proper-noun/surname
lemmatization accuracy is unverified**, BMPM Czech precision/recall on declined names is
unverified, and there is **no end-to-end Czech ER benchmark**. The recommendation reads more
confident ("most of the multilingual machinery is available with zero new infrastructure") than
the underlying "every number is component-level, none end-to-end" evidence.

**O-4 — "Constrained decoding helps, not hurts" (R6).** Rests substantially on **one** benchmark
paper (Tam et al. 2501.10868) plus a **vendor blog** (BoundaryML, who sell SAP). R6 flags the
vendor sourcing, but the §1 key-finding states it with more certainty than one-paper-plus-vendor
warrants, and the "smaller models are hurt" exception is conceded to have no rigorous isolating
study.

**O-5 — Tier-0 authority recommendations rest on changed-under-our-feet facts (R4).** R4 honestly
flags that OpenAlex moved to API-key+credit and Crossref cut limits 2025-12-01, but then makes
firm launch recommendations ("INTEGRATE") on top of access models it says it could not fully
verify ("exact credit-to-request conversion is not published"). The verdicts are reasonable but
more provisional than the recommendation table presents.

**O-6 — "CLIP / HAC-with-cut is the production answer" (R8).** R8 concedes the FAMER PDFs would
not extract, so CLIP's "outperforms all previous algorithms" superiority is **from abstracts, not
tables**, and CLIP's core assumption (duplicate-free sources) is **violated** by ugm's data. R8
correctly pivots to HAC — but the recommendation inherits authority from a benchmark magnitude it
could not actually read.

**O-7 — Binomial "~200/type, grow to 400" sizing (R7).** Explicitly a synthesis, not a cited
constant, and R7 says so — but it is then carried into the concrete v1 plan as if firm. The
denominator trap (recall needs ~370 *true-positive pairs*, rare under a 0.0001 prior) means the
real labeling cost to hit those CIs may be much higher than "200/type" suggests.

---

## 4. Top 5 things the synthesis MUST resolve

1. **The cross-check never happened (G1).** Treat R2, R5, R6, R8 as *single-source* despite their
   "second independent take" language. Either re-run the Codex/Antigravity agents or explicitly
   downgrade confidence on the ER-cascade, ontology-core, extraction, and clustering
   recommendations. Do not let the synthesis inherit a verification that produced 0 bytes.

2. **Decide the coref topology and default once (C1 + C2 + G8).** Three docs assume three
   different things: R1 (optional, default OFF, inside the E2 call), R3 (mandatory multilingual
   model for Czech), R6 (discrete coref stage *before* E2). For a Czech-first product these are in
   direct tension, and R6's small-chunk recommendation breaks R1's in-context-coref premise. Pick
   one pipeline shape and one per-language default.

3. **Fold in O3 (the value gate) before trusting R7/R9 numbers (G2 + G9 + O-2).** O3 is the
   stated #1 objection and silently absent from the research. It changes golden-set composition
   (R7), table sizing (R9), `other:` rates (R6), and ER/coref load (R1/R8). The synthesis must
   either research it or explicitly mark every downstream quantity as "assumes full extraction."

4. **Own the relation-side and the un-merge ripple (G4 + G5 + G6).** Nine questions are about
   *entity* identity; D2 relation identity, `other:`→core promotion, and what an un-merge does to
   bi-temporal supersession windows are under-researched. These are exactly where "silent
   supersession failure" (the existential risk per `entity_registry.md` §1) actually lives.

5. **Unify one canonical tier table and break the golden-set circularity (C4 + C5).** Publish a
   single Tier 0–5 definition (R2/R3/R9 currently disagree on numbering and on whether embedding
   is "blocking" or "tier 4"), and resolve R7's eval-set sampling so the set used to *measure*
   precision/recall is not the same biased, cascade-generated, LLM-proposed set R7 itself says is
   invalid for measurement.

---

## Appendix — coverage map (which open question each doc answers)

`entity_registry.md` §8 open questions: #1 seed core → R5 (✓); #2 thresholds/bands → R2+R7
(✓ but golden-set-gated); #3 review tooling → R10 (✓); #4 external authorities → R4 (✓);
#5 multilingual → R3 (✓, flagged as WP-ML); #6 scope-view format → **not covered by any question**
(gap); #7 coref engine → R1+R3 (✓ but contradictory, see C1/C2). O6 → R7 (ER half only; retrieval
eval half dropped, G7). O3/O4 → **not covered** (G2). O5 subsystem deliverables: registry schema,
alias lifecycle, predicate-promotion workflow → only partially researched (G5).
