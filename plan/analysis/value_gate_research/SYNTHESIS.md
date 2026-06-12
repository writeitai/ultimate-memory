# SYNTHESIS — Value / Salience Gate (Objection O3)

Lead-architect synthesis of the value-gate research effort (questions V1–V6, repo_findings,
verify/*, external_agents Codex V2 + Antigravity V3) against the current design
(`objections.md` O3/O6, `decisions.md` D1–D16, `overall_design.md` plane E,
`registry_research/SYNTHESIS.md` — which flagged O3 as upstream of R7/R9 and stamped every
downstream quantity "assumes full extraction"). Decisive where the evidence allows; explicit
about what is still a spike.

**Provenance note (load-bearing — and different from the registry round).** Unlike the registry
research (where all four `external_agents/*` were 0 bytes), **this round's external agents
SUCCEEDED**: Codex V2 (`codex_V2_gating.md`, 17.9 KB) and Antigravity V3 (`agy_V3_lazy_extraction.md`,
27.5 KB) both produced full, independent analyses. `agy_V3.err` is 0 bytes (clean exit);
`codex_V2.err` is 4.3 MB of stderr noise but the output file is complete. So the gating question
(V2/Codex) and the lazy-extraction question (V3/Antigravity) each have a genuine independent
cross-check, and the registry-SYNTHESIS caveat that "external cross-checks repeatedly produce 0
bytes" (which V6 §3 inherited and used to self-downgrade) **no longer applies to this effort** —
confidence on V2 and V3 is upgraded one notch accordingly. The five Claude `verify/` re-checks
(`facts.md`, `completeness.md`) re-opened source at file:line and re-fetched primary papers; the
load-bearing numbers came back confirmed, with two defects flagged below.

---

## 1. Executive summary (the verdict)

1. **O3's premise is REAL but its headline is mis-cited — accept the objection, fix the number.**
   Most raw corpus content is low-value (web-scale survival after boilerplate-strip + dedup is
   ~5–10% of bytes — VERIFIED), LLM-extracted graphs are measurably noisy, and *pruning ~40% of
   entities / 30–60% of relations maintains or improves answer quality* (denoising-KG arXiv
   2510.14271, +8 to +17pp LightRAG win-rate — VERIFIED at source). The famous "~98% junk" is a
   **real, traceable single-deployment anecdote** (mem0 issue #4573, 97.8% of 10,134 entries —
   `verify/facts.md` [CHECKED]), *not* a population statistic: 52.7% of its junk was an agent
   re-ingesting its own boot file. **Decisive supporting fact:** swapping a 2B model for Claude
   Sonnet 4.6 dropped junk only to 89.6% — "a better model extracts *more* indiscriminately; the
   extraction prompt is the bottleneck, not the model." You cannot model-quality your way out of
   junk; you need a gate *before* extraction. Build the gate; demote the 98% to a footnote.

2. **The gate is genuinely unbuilt prior art — confirmed by counter-example across 6 systems.**
   GraphRAG, LightRAG, HippoRAG, mem0, cognee (and Letta) all extract everything that survives
   chunking; the *only* universal pre-LLM lever is **exact content-hash dedup** (idempotency, not
   selectivity), trivially defeated by one-byte paraphrase. GraphRAG quantifies the prize: graph
   extraction ≈ **75% of indexing cost** (VERIFIED). The value/salience/near-dup tier is ours to
   build and is a real differentiator — but "nobody built it" is partly because the recall risk is
   hard, not purely opportunity (`verify` O6).

3. **Recommended design: a new plane-E stage `E1.5`, at the E1→E2 boundary, per-PageIndex-section,
   as a nested cheap-first cascade (D4 applied one stage earlier).** Rungs ascend in cost:
   `T-dup` exact content-hash → `T-struct` PageIndex node-type (references/boilerplate/nav) →
   `T-novel` embedding near-dup vs already-extracted sections (reuses E1 vectors) → `T-salience`
   small-classifier score. Output one of three tiers: **FULL / DEFERRED / CHUNKS-ONLY** (+ `dup`
   floor). **E1 always runs** for every document — the gate withholds the expensive E2/E3 LLM
   layer, never the retrieval floor. Codex V2 and Antigravity V3 independently converge on exactly
   this E1/E2-boundary, three-tier, eager-E1 shape.

4. **Defer-don't-DROP, on an immutable backstop — this is what makes aggressive gating safe.**
   The gate's output is never DELETE; it is `{FULL, DEFERRED, CHUNKS_ONLY}`. E0/E1 are immutable
   and authoritative (Postgres + GCS hold every byte forever, D1). A skipped section is *un-extracted,
   not lost*; re-extraction is the same idempotent worker (D12) over the same truth (D7), so backfill
   is a routine rebuild path, not a DR script. The asymmetry — under-extraction is a cheap, recoverable
   cost; over-extraction silently poisons relations/graph/beliefs — argues for a **recall-conservative
   gate** that escalates uncertain sections to DEFERRED, never hard-rejects to CHUNKS-ONLY.

5. **Deferred/lazy extraction is real and validated, but ugm wants the opposite trade from the
   prior art.** LazyGraphRAG defers *all* LLM to query time at **0.1% of full-GraphRAG indexing
   cost** (VERIFIED) — proof the economic ceiling exists — but it *re-pays every query and persists
   nothing*. ugm defers *only the low-salience fraction* and, when extraction finally runs, **writes
   it to the Postgres ledger once, forever**. The defer DECISION is durable, versioned Postgres
   state (a `document_extraction_state` / `gate_decisions` row); the work queue is a *projection* of
   that state (regenerable by SQL), enqueued atomically via transactional-outbox. This keeps D7
   (rebuildable) and D12 (per-doc chain) intact — deferral is a conditional terminal state of E1,
   not a bypass.

6. **The cost lever is real but smaller than "10×" for skip-alone; 10× needs the lazy tier.**
   Salience-skipping alone is a ~1.5–2× lever (E2/E3 cost → ~55–65% of baseline). The 10× O3 claims
   is only reachable when the DEFERRED/never-retrieved tier carries most of the weight. The R9 impact
   is favorable: the three 10⁸ tables (`mentions / resolution_decisions / relation_evidence`) are all
   E2/E3 *outputs*, so they shrink by the same `(f_full + f_def·r_retrieve)` factor — R9 gets *more*
   comfortable, never less. `documents`/`chunks` do not shrink (E1 always runs). **Commit no cost
   multiplier until a spike measures the filter rate on a representative corpus slice.**

7. **The two real, under-answered risks (from `verify/completeness.md`) must be closed before
   committing:** (a) **the gate's own aggregate compute at 1M-doc × N-section scale is unbounded** —
   "piggybacks E1's cached call / marginal-zero novelty" are unvalidated architectural assumptions;
   if the salience rung needs its own prompt or the novelty check is a corpus-scale ANN query, the
   gate becomes a new fleet-scale LLM stage (the exact thing it's meant to avoid). (b) **The
   rare-fact safeguards are necessary but not shown sufficient** — a deferred gem may never rank
   top-k to self-trigger; never-defer-by-predicate is circular (predicate type is only known *after*
   extraction); the zombie-fact/supersession-skip case (skipping the only superseding evidence →
   serving a stale fact as current) is the highest-severity correctness risk and currently gets one
   unvalidated sentence.

8. **Verdict: ACCEPT O3, build the gate, but gate the build on a spike.** Ship the deterministic
   rungs (T-dup, T-struct, T-novel) first — free, no training data, they already capture the
   references/boilerplate/near-dup cases that motivate O3 — with the DEFERRED machinery and
   defer-don't-DROP contract. Treat the small-classifier salience rung and lazy/scope-interest
   triggers as fast-follows behind the O6 golden set. Define a **break-even multiplier** below which
   the gate's complexity/latency/recall-risk isn't worth it, and make the spike clear it. Propose new
   decisions **D25–D30** (registry SYNTHESIS already proposed through D24).

---

## 2. Per-question conclusions (V1–V6)

Confidence reflects the `verify/*` fact-checks AND — newly for this round — the *presence* of
independent external takes for V2 (Codex) and V3 (Antigravity).

### V1 — Junk rate / O3 premise → **PREMISE SUPPORTED (direction robust; headline demoted). Confidence: medium-high.**
- **Settled answer:** O3's premise (most extracted content is low-value; unfiltered junk degrades
  downstream quality) holds. The *direction* is multiply-sourced and has one peer-reviewed causal
  result; the *specific 98%* is n=1 and pathological.
- **Key evidence (VERIFIED at source):** mem0 #4573 = 97.8% junk / 10,134 entries / model-swap to
  Sonnet 4.6 only reaches 89.6% ("prompt is the bottleneck, not the model"); denoising-KG +8–17pp
  from pruning 40% entities; web-corpus 5–10% survival after dedup/boilerplate-strip; extraction
  hallucination 3–27% (snippet-level).
- **Agreement:** Codex V2 independently confirms the mem0 #4573 audit (10,134 → 224 survivors →
  97.8%), the HBS "selective recall +10%" study, and DEG-RAG entity reduction — so the premise has
  cross-agent corroboration, not just Claude's read.
- **Defects to carry (`verify/facts.md`):** V1's "cosine > 0.95" Phase-1 threshold is **fabricated**
  (not in the source — drop it); junk-composition raw counts are back-computed (cite the
  percentages). **C1 resolved in V1's favor:** V4 and V6 wrongly claim the 98% has *no source* — it
  does; they searched for the wrong artifact (a mem0-LOCOMO junk rate). Adopt V1's "demote + fix the
  citation," **reject V4/V6's "drop as unverified."**

### V2 — Gating signals & mechanisms → **Five-rung cheap-first cascade; distill an LLM judge into a small classifier. Confidence: high (now cross-checked by Codex).**
- **Settled answer:** A layered cascade, cheapest-and-most-destructive first: heuristic
  structural/length → exact+near-dup (hash → MinHash/SimHash) → embedding-novelty router → distilled
  small classifier (the steady-state value gate) → frontier-LLM judge **off the hot path** (seed
  labeling only). Signals that transfer: source trust, structural role (near-free from PageIndex),
  information/entity density, novelty-vs-known, near-dup. Noise: length-alone, perplexity
  (in-distribution bias), raw entity count.
- **Key evidence (VERIFIED):** FineWeb's ordered pipeline; Ultra-FineWeb fastText is **6× cheaper
  than an LLM classifier and GPU-free** (Table 2); SemDeDup removes ~50% at minimal loss; embedding
  is sunk at E1. The two-stage distillation pattern (LLM oracle labels seed → cheap classifier
  scales) is the dominant validated mechanism — and the seed set *is* the O6 golden set.
- **Agreement (Codex V2, independent):** Converges on the same cascade — "deterministic dedup +
  structural role + density/source + embedding novelty + demand, calibrated classifier *after*
  heuristics; small-LLM judging rare and reserved for borderline/high-impact." Codex adds a
  transparent scoring formula (`source_prior + structural + density + novelty + demand − dup_penalty
  − boilerplate_penalty − staleness`) and proposes a **two-stage gate (E0/E1 section gate + E1/E2
  chunk gate)** — slightly more than Claude's single E1.5 stage (see granularity note below). Codex's
  target operating point: skip 50–80% of E2/E3 with <2–5% gold-claim loss.
- **Caveats (`verify/completeness.md`):** "marginal-zero novelty" understates a corpus-scale ANN
  query at 10⁸ claims (O5); the small-LLM rung's *aggregate* cost is unbounded (G1).

### V3 — Lazy / deferred architecture → **Defer at E1→E2; decision is versioned Postgres state; queue is a projection. Confidence: high (now cross-checked by Antigravity).**
- **Settled answer:** Adopt deferred extraction as a per-document state machine in the Postgres
  spine. Defer boundary = E1→E2 (never before E1, or you can't retrieve to self-trigger). The defer
  verdict is durable, versioned, replayable Postgres state; the work queue is a derived projection
  drained via `FOR UPDATE SKIP LOCKED`, enqueued atomically with the state flip (transactional
  outbox). Four backfill triggers: on-scope-interest (D16, highest leverage), on-first-retrieval,
  bounded steady-state drain, gate-version re-classification.
- **Key evidence (VERIFIED):** LazyGraphRAG 0.1% indexing / 700× query (defers *all*, persists
  *nothing* — validates economics, not architecture); no cloned system implements defer (uniformly
  eager); DBOS durable-execution / outbox / SKIP-LOCKED patterns.
- **Agreement (Antigravity V3, independent):** Strong convergence — same Tiered-Processing (Pattern
  E) + Priority-Work-Queue (Pattern D) recommendation, same eager-E0/E1 + deferred-E2/E3 split, same
  "defer decision is versioned Postgres state, rebuild reads stored tier and never re-runs the gate"
  (the exact D7 answer). Antigravity adds concrete schema (`document_extraction_states`,
  `salience_gate_versions`, `scope_interests`), Postgres advisory-lock + dedup-key idempotency, a
  stale-task sweeper / heartbeat reconciler, and a `completeness_ratio` diagnostic returned on the
  query path. Antigravity's illustrative economics: ~$7.50/1k docs eager vs ~$0.15/1k deferred.
- **Caveats:** Antigravity proposes `processing_tier DEFAULT 'DEFERRED'` (defer-by-default) — ugm
  should default toward extract for trusted sources given the recall asymmetry (V5). The
  on-retrieval self-trigger has a cold-start ranking hole (`verify` G4).

### V4 — How real systems gate → **Industry practice is extract-all; the gate is unbuilt. Confidence: high.**
- **Settled answer:** All 5–6 surveyed systems extract everything that survives chunking; the only
  pre-LLM lever is exact-hash idempotency. mem0 inverts the order (the LLM call *is* the gate, recall-
  biased "when in doubt, extract"). The two systems that attacked extraction cost moved the LLM
  (FastGraphRAG = NLP-on-everything; LazyGraphRAG = defer-all), neither *gated by value*.
- **Key evidence (VERIFIED):** grep-absence of `salien|novel|relevan|worth|importance` across all
  clones; GraphRAG 75%; LazyGraphRAG 0.1%; cognee's `importance_weight=0.5` computed-but-unused (the
  cautionary anti-pattern: don't ship a salience score nothing reads).
- **Defect (`verify`):** V4 §3's "98% has no source" is **wrong** (C1) — its skepticism about
  *using* the number is right, its claim about *existence* is false. Borrow the idempotency floor +
  merge-side cascade; build the value tier.

### V5 — Recall safeguards (don't lose the gem) → **DEFER-don't-DROP + retrieval-backfill + never-defer classes + cheap-first gate + canary audits. Confidence: medium-high.**
- **Settled answer:** A five-part reversibility envelope; the gate's output is never DROP. Leverage
  E0/E1 immutability (D1) as the backstop the eviction literature has to bolt on. Bias conservative
  (over-defer is a *silent* hole; under-defer is a *gradual* cost).
- **Key evidence:** mem0's own eviction write-up names the failure mode — "LRU treats frequency as a
  proxy for importance; that breaks for low-frequency high-stakes data" (penicillin allergy);
  "passive aging is for noise, active forgetting is for facts." Zero-RAG prunes 30% Wikipedia <2pt /
  70% TriviaQA 0.62pt — but prunes *model-mastered* passages, the opposite of a rare user fact (so
  aggregate recall under-weights the tail). ugm's D2 collapses redundancy into one relation + N
  evidence, so interference cost is far lower than mem0's — the gate is justified by *extraction cost*,
  not retrieval interference.
- **Agreement (Antigravity V3):** Independently proposes the same mitigations — background drain,
  completeness metric, salience-override, K3/belief guard against mostly-deferred entities.
- **Open holes (`verify` G4/G6):** (i) deferred chunks may not rank high enough to self-trigger;
  (ii) extract-on-scope-interest is unbuilt/unvalidated yet promoted to highest-leverage; (iii)
  never-defer-by-predicate is **circular** — the gate runs *before* extraction so it only has weak
  *lexical* signal, not predicate type; (iv) the zombie-fact/supersession-skip risk is under-treated.

### V6 — Pipeline integration & cost model → **New stage E1.5, per-section, verdict-as-versioned-row; un-stamps R7/R9. Confidence: medium.**
- **Settled answer:** Gate at E1→E2, per-PageIndex-section (document rollup, chunk fallback for
  chunks-only). Verdict is an append-only `gate_decisions` row stamped with `gate_version` + features
  + tier + `superseded_by` — the same transcript/verdict epistemics as claims (D2) and
  resolution_decisions. Nested with D4: V6's gate shrinks the *input* to D4's E3 cascade; D4's
  mechanism is unchanged. Extends D12: `full` = existing chain; `chunks-only` = chain stops at E1;
  `deferred` = E2 enqueued by retrieval/scope-interest event instead of E1-completion.
- **Cost model:** `Cost ≈ g + C_E2E3 × (f_full + f_def·r_retrieve)`. The three 10⁸ tables shrink by
  the same factor (they are E2/E3 outputs) → R9 *more* comfortable. R7 gains a new asset: a
  gate-verdict golden set (sections labeled should-full / fine-to-skip), with **false-skip rate** as
  the dangerous metric (a skipped salient section = a silently missing fact).
- **Defects (`verify`):** the §2.6 cost bands (65/55/36%) are **modeled, not measured** — self-flagged
  but formatted to look like output (O2); the gate's own cost `g` is carried as a symbol and dropped
  (G1); "deterministically recomputable" is **wrong for the LLM rung** (only *replayable from stored
  verdict*, subject to model-endpoint drift — G3/C3); V6 inherited the now-obsolete "external agents
  produce 0 bytes" caveat — **does not apply this round** (Codex/Antigravity succeeded), so V6's
  self-downgrade can be partially lifted.

**Granularity reconciliation (C2, unreconciled across docs):** V2 says per-section *with per-chunk
overrides*; V6 says per-section primary, per-chunk fallback; V5 frames it at the document/section
row; Codex proposes *two* gates (section at E0/E1 + chunk at E1/E2). **Synthesis pick: per-section
(PageIndex node) is the canonical unit, document-rollup for reporting, chunk-level only as the
CHUNKS-ONLY fallback granularity.** Adopt Codex's insight that some signals are cheaper at the
section stage (structural role, source) and some need E1 (embedding novelty, density) — but implement
as **one logical gate stage with two signal-collection points**, not two separate gate stages, to
avoid doubling state and decisions.

---

## 3. Recommended design

### Position — E-plane boundary
A new stage **E1.5** on the per-document Cloud Tasks chain (D12):
`E0 → E1 → E1.5 gate → { E2 (FULL) | enqueue-deferred (DEFERRED) | stop (CHUNKS-ONLY) | skip (dup) }`.
The defer boundary is drawn **between E1 and E2, never before E1**. E0 (markdown + PageIndex
hierarchy + node summaries) and E1 (semchunk + context-prefix + embed → P1) **always run** for every
document — they are cheap, deterministic, and *produce the very signals the gate consumes*. This keeps
every document retrievable in P1 (the precondition for lazy self-triggering) and is the literal
realization of O3's "progressive disclosure of *processing*, not just summarization."

### Signals (cheap-first, ascending cost)
- **T-dup — exact content-hash** (doc + section + chunk). Lift LightRAG `compute_text_content_hash`
  + cognee `content_hash` — the only pre-LLM lever prior art ships; doubles as the D7 idempotency
  cache. → `dup`, skip.
- **T-struct — PageIndex node-type / structural role** (references, bibliography, acknowledgements,
  nav, headers/footers, legal/license boilerplate). Near-free metadata from E0, not inference.
  → `chunks-only` (deterministic).
- **T-novel — embedding near-dup vs already-extracted sections** (MinHash/SimHash for lexical +
  cosine vs existing claim/relation embeddings). Reuses E1 vectors. **Caveat:** at 10⁸ claims this is
  a corpus-scale ANN query, *not* "a cosine" — budget it; bound the candidate set. → near-dup of an
  already-extracted, high-`evidence_count` fact → `chunks-only` / `deferred`.
- **T-salience — distilled small classifier** (fastText/BERT-style; features = density + source trust
  + structural + novelty). The steady-state value gate, ~6× cheaper than an LLM and GPU-free. Output
  band → tier. **A frontier-LLM judge is OFF the hot path** — used only to label the seed/golden set
  the classifier distills from, never as a steady-state per-section call.
- **Override signals (escalate to FULL regardless of score):** never-defer source classes
  (user-authored / first-party / curated), and lexical change-of-state / temporal markers
  (supersession-bearing language) — the *pre-extraction-available* approximation of never-defer
  predicate classes (which the gate cannot know directly — see risks).

### Mechanism
Nested cheap-first cascade (D4 philosophy applied one stage earlier). Stop as soon as a tier is
decided. The LLM judge is a *seed-labeling* tool, not a per-item gate — distillation (label once,
classify cheaply) is the only economically sound way to use LLM judgment here, since ugm cannot
amortize a per-doc judge the way pretraining amortizes over many training runs. **Escalate uncertain
sections to DEFERRED, never hard-reject to CHUNKS-ONLY.**

### The three tiers (+ floor)
| Tier | E1 | E2/E3 | P1 retrieval | P2 graph |
|---|---|---|---|---|
| **FULL** | always | run now (Claimify → coref → ER → relations → supersession) | chunks + claims + fact-labels | edges projected |
| **DEFERRED** | always | withheld; E2 enqueued behind a trigger | chunks searchable now; claims/relations appear after promotion | nothing until promoted |
| **CHUNKS-ONLY** | always | never (unless promoted) | chunks searchable (nothing lost from retrieval) | no edges |
| **dup** (floor) | skip | skip | existing rows reused | reused |

### Lazy / deferred architecture
Promotion triggers, priority order: **(i) on-scope-interest** (a K2 scope's declared entity/predicate
interest, D16, sweeps deferred docs mentioning it — highest leverage, ties cost to demand, where ugm
beats LazyGraphRAG's query-random laziness); **(ii) on-first-retrieval** (a P1 hit on a deferred
section's chunk enqueues its E2 — lazy materialization, but *persisted* to the ledger, the trade
LazyGraphRAG doesn't make); **(iii) bounded steady-state drain** (a low-priority worker guarantees
"deferred ≠ never" — a freshness SLA analogous to D7's rebuild cadence); **(iv) gate-version
re-classification** (a better gate promotes previously-deferred docs as a version-filtered batch job).
Promotion starts at E2 over the existing E1 chunks — E0/E1 are not reprocessed. Idempotent on
`content_hash + processing_version` (D12) and `(source, assertion)` / `(s,p,o)` (D2).

### Where deferred & gate-decision state lives in Postgres (rebuildable per D7)
The defer decision is **first-class, append-only, versioned Postgres state** — the failure mode D7
forbids is putting it only in Cloud Tasks (a queue purge = silently dropped documents, unrebuildable).

```
gate_decisions  (append-only — the verdict)
  document_id, section_id (PageIndex node),
  tier ∈ {full, deferred, chunks_only, dup},
  features        jsonb,          -- the cheap signals that drove it (replayable)
  salience_score  real,
  gate_version,                   -- pinned model/prompt/threshold/classifier set (D12 versioning)
  deferred_trigger nullable,      -- 'first_retrieval' | 'scope:<id>' | 'drain' | 'gate_reclass'
  decided_at, superseded_by

document_extraction_state  (current processing state — drives the queue)
  document_id, section_id,
  state ∈ {pending, full_done, deferred, backfill_queued, backfilling, backfill_done, chunks_only, failed},
  processing_version, retrieval_count, last_retrieved_at, error_count, last_error,
  heartbeat_expires_at, updated_at

salience_gate_versions  (model_name, threshold/bands, classifier_id, configured_at)
scope_interests         (scope_id, interest_type ∈ {entity_type,predicate,metadata,keyword}, value)
```

**Rebuild semantics (D7):** the rebuild reads the *stored* `tier` and never re-evaluates the gate.
`FULL` → load chunks + E3 relations; `DEFERRED`/`CHUNKS_ONLY` → load chunks only, no extraction. A
PITR restore restores the exact outstanding-work set; the queue is regenerated by SQL over
`document_extraction_state`. **Determinism nuance (must state plainly — `verify` G3/C3):** the
deterministic rungs (hash/structural/near-dup) are *recomputable*; the **LLM/classifier salience
rung is only replayable from the stored verdict+features, not deterministically re-derivable** (model-
endpoint drift). So D7 for the gate means **"stored & auditable," not "recomputable"** for the
salience rung — pin versions AND store outputs; do not promise recomputation.

### Recall safeguards (defer-don't-drop)
1. **DEFER-don't-DROP contract** — output is never DELETE; E0/E1 immutable backstop (D1); backfill =
   routine idempotent re-extraction (D7/D12).
2. **Always-full E1** — deferred ≠ unindexed; every doc retrievable, can self-trigger.
3. **Never-defer classes** — source-trust pinning (first-party/curated → FULL) + lexical
   change-of-state up-weighting (the pre-extraction proxy for high-stakes predicates).
4. **Bounded drain** — "deferred" is a scheduler, not a discard.
5. **Canary + sampled audit** — plant rare-but-critical facts in O6's golden set; CI fails if a
   candidate threshold routes a canary to DEFERRED without a backfilling retrieval; sample
   `deferred`/`chunks_only` decisions to measure the in-house number the literature lacks
   (rare-critical-fact deferral rate at threshold τ); tune τ against per-fact loss, never corpus
   average. **K3/belief guard:** optionally exclude entities whose evidence is mostly still-deferred
   from belief promotion until backfilled.

### Cost model (filter-rate × savings; impact on R9)
`Cost ≈ g + C_E2E3 × (f_full + f_def·r_retrieve)`, where `g` = per-section gate cost,
`r_retrieve` = fraction of deferred sections eventually extracted. **Salience-skip alone ≈ 1.5–2×
(E2/E3 → ~55–65% of baseline); 10× requires the lazy tier carrying most of the weight** (LazyGraphRAG's
0.1% proves the ceiling exists). **R9 impact:** the three 10⁸ tables (`mentions / resolution_decisions
/ relation_evidence`) are E2/E3 outputs → they shrink by `(f_full + f_def·r_retrieve)`; at a moderate
~0.55 they become ~5–6×10⁷, well inside R9's "engineer the indexes not the row counts" comfort zone,
and R9's partition/index load-test should be sized against *gated* volume. `documents`/`chunks` do
**not** shrink (E1 always runs). New table cost (`gate_decisions`, one row per section per
`gate_version`) is negligible vs the 10⁸ tables. **All filter-rate bands are MODELED — commit no
multiplier until measured on a representative corpus slice (spike-1).**

---

## 4. Implications for decisions / objections

### Resolve O3
**ACCEPT O3 → becomes D25–D30 (below).** The objection's mechanism is correct and is the #1 cost/
quality lever; only its 98% citation needs fixing. Edit `objections.md` O3 to demote "~98% of
unfiltered extracted entries were junk" to *"a documented single-deployment audit (mem0 #4573, 97.8%
of 10,134 entries) consistent with broader corpus evidence; not a population statistic."* This also
**un-stamps the "assumes full extraction" caveat** the registry SYNTHESIS placed on R7 and R9.

### What changes in D4 / D7 / D12
- **D4 (cheap-first cascade)** — extended, not changed. A *second* nested cheap-first cascade now sits
  at the E1→E2 boundary (the V6 gate), upstream of D4's existing in-E3 supersession cascade. Same
  discipline; the gate shrinks D4's input volume. Carry the registry-SYNTHESIS refinement: cheap tier
  *escalates* near-misses (→ DEFERRED), never auto-rejects.
- **D7 (rebuildable)** — refined: the gate decision is rebuildable state, but with an explicit
  **determinism caveat** — deterministic rungs recomputable; salience/LLM rung replayable-from-storage
  only. Rebuild reads stored tier, never re-runs the gate. Add `gate_decisions` /
  `document_extraction_state` to the Postgres-authoritative set.
- **D12 (per-doc chain ends at E2)** — extended: the chain now ends at **E1.5** for `chunks_only`
  (early termination) and is **trigger-deferred** for `deferred` (E2 enqueued by retrieval/scope-
  interest, not E1-completion). Still Cloud Tasks, idempotent by content-hash+version, 2 retries +
  DLQ — only the enqueue trigger differs. Add heartbeat/stale-task sweeper (Antigravity V3).

### New decisions to propose (continue after registry's D17–D24 → start at D25)
- **D25 — Value/salience gate as plane-E stage E1.5 (E1→E2 boundary, per-PageIndex-section).** Eager
  E0/E1 for every doc; gate withholds E2/E3 only. Three tiers FULL/DEFERRED/CHUNKS-ONLY + dup floor.
  (V6, Codex V2, Antigravity V3.)
- **D26 — Gate = nested cheap-first cascade.** T-dup → T-struct → T-novel → T-salience (distilled
  small classifier); frontier LLM off-hot-path (seed labeling only); escalate-to-DEFERRED, never
  hard-reject. (V2, Codex.)
- **D27 — Defer decision is durable, versioned Postgres state; the queue is a projection.**
  `gate_decisions` (append-only verdict) + `document_extraction_state` (current state, drives queue
  via `FOR UPDATE SKIP LOCKED`); enqueue Cloud Tasks atomically via transactional outbox; backfill
  idempotent. Rebuild reads stored tier. (V3, Antigravity, V6.)
- **D28 — Lazy promotion triggers, priority order.** on-scope-interest (D16) → on-first-retrieval →
  bounded drain → gate-version re-classification. Defer ≠ never (freshness SLA). (V3, V5.)
- **D29 — Defer-don't-DROP recall envelope.** Output never DELETE; always-full E1; never-defer source
  classes + change-of-state lexical up-weight; bounded drain; canary/audit on the deferred stream with
  per-fact false-skip metric; K3 belief guard. (V5, V3.)
- **D30 — Gate cost & break-even discipline (O6 hook).** Day-one metrics: per-tier section counts,
  false-skip rate vs gate-verdict golden set, `r_retrieve` (realized lazy lever), E2/E3 spend-per-doc
  vs full-extraction baseline, *and the gate's own aggregate compute*. Commit no cost multiplier and
  ship no salience threshold without a measured filter rate and a defined break-even the spike must
  clear. (V6, `verify` G1/G5.)

### Must R7/R9 numbers be re-derived?
**Yes — but favorably, and only after the spike.** R7 gains a new labeled asset (the gate-verdict
golden set) and must add false-skip/false-defer metrics. R9's three 10⁸ tables shrink by the gate's
filter factor and its partition/index load-test should be sized against gated volume (more headroom).
Until the spike measures `f_full/f_def/f_chunk/r_retrieve` on a real slice, R9's counts stay
explicitly "assumes full extraction × (gate factor TBD)." The registry SYNTHESIS's stamp is
discharged in *mechanism* (gate decided) but not yet in *magnitude* (factor unmeasured).

---

## 5. Open risks & what to prototype first

**Spike before committing (highest leverage first):**

1. **Bound the gate's own aggregate compute (the #1 unaddressed risk — `verify` G1/G2/O5).** Measure
   on a representative slice: sections-per-document, gate-cost-per-section, and **whether the salience
   rung can truly reuse E1's prompt cache** (if it needs a different prompt, the cache doesn't help and
   it's a new fleet-scale LLM stage). Also bound the T-novel ANN query cost at 10⁸ claims. If the gate
   can't be kept ≪ extraction in *aggregate*, it defeats its own purpose.

2. **Measure the filter rate and define the break-even.** Prototype the deterministic rungs (T-dup,
   T-struct, T-novel) + a first salience classifier on a real corpus slice; measure
   `f_full/f_def/f_chunk/r_retrieve`. State the *minimum* multiplier at which the gate's complexity +
   E1.5 latency hop + recall risk + own compute are net-positive; gate the feature on clearing it.
   (`verify` G5, G7.)

3. **Harden the rare-fact safeguards — necessary but not shown sufficient (`verify` G4/G6).** Three
   holes to close with measurement, not assertion: (i) does a deferred gem actually rank high enough
   in P1 (without relation edges / evidence_count) to self-trigger? — test with planted facts; (ii)
   extract-on-scope-interest is unbuilt/unvalidated yet load-bearing — prototype and measure its
   recall/cost; (iii) **the zombie-fact / supersession-skip case** (skipping the only superseding
   evidence → serving a stale fact as current) is the highest-severity *correctness* failure and
   currently has one unvalidated mitigation — design and test the change-of-state up-weighting
   explicitly, and coordinate with the registry SYNTHESIS spike-2 (un-merge → supersession ripple).

4. **Resolve the never-defer-by-predicate circularity.** The gate runs before extraction, so it cannot
   know a section asserts a `penicillin_allergy` predicate — only weak lexical signal. Validate that
   source-trust pinning + lexical medical/legal/change-of-state cues recover enough recall on high-
   stakes facts, or accept that high-stakes scopes default to FULL.

5. **Validate determinism/rebuild story.** Confirm in a drill that a rebuild reproduces "corpus as
   gated so far" from stored tiers, and document that the salience rung is replay-from-storage (not
   recompute). Pin classifier/model versions in `salience_gate_versions`.

6. **Scope the O6 golden-set labeling cost (`verify` G8).** The gate-verdict golden set (sections
   labeled should-full/fine-to-skip + planted canaries) is an unscoped, unowned prerequisite — size
   it and assign an owner alongside the registry golden set (D22).

**Build order:** ship T-dup + T-struct + T-novel + the DEFERRED machinery + defer-don't-DROP contract
first (free, no training data, captures the references/boilerplate/near-dup cases that motivate O3).
Add the distilled classifier + lazy/scope-interest triggers as fast-follows behind the O6 golden set
and the spike clearing the break-even.

---

### Source map
Questions: `value_gate_research/questions/V1–V6.md`. External agents (BOTH SUCCEEDED this round):
`external_agents/codex_V2_gating.md` (Codex, gating), `external_agents/agy_V3_lazy_extraction.md`
(Antigravity, lazy/deferred). Verify: `value_gate_research/verify/{facts,completeness}.md`. Repo
archaeology: `value_gate_research/repo_findings/{mem0_cognee,graphrag_lightrag_hipporag}.md` (+
`registry_research/repo_findings/*`). Design: `objections.md` (O3, O6), `decisions.md` (D1–D16),
`overall_design.md` (plane E, trigger model), `registry_research/SYNTHESIS.md` (R7/R9, O3 stamps,
D17–D24).
