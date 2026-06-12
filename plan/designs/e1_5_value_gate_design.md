# E1.5 Value/Salience Gate — Design

The plane-E stage that decides, per document section, whether to pay for expensive E2/E3
extraction now, defer it, or skip it. Distills the value-gate research
(`plan/analysis/value_gate_research/SYNTHESIS.md`, V1–V6) into binding design. Formalizes
objection O3; decisions **D25–D30**. All filter-rate / cost numbers are starting points to be
measured on a corpus slice — not committed constants (D30).

## 1. Why (premise, verified)

E2/E3 (Claimify claims + coreference + entity resolution + relation normalization) is the cost
center *and* the quality bottleneck, and today it runs on everything. The premise that most raw
content is low-value is multiply-sourced: web survival ~5–10% after dedup/boilerplate-strip;
LLM-extracted graphs are measurably noisy; pruning ~40% of entities can *improve* answer quality
(denoising-KG arXiv 2510.14271, +8–17pp LightRAG win-rate). The famous "~98% junk" is a real but
single-deployment audit (mem0 #4573) — demoted to a footnote, not a population statistic.

**The decisive fact:** swapping a weak model for a strong one dropped junk only 97.8%→89.6% —
*a better model extracts more indiscriminately; the extraction prompt, not the model, is the
bottleneck.* You cannot model-quality your way out of junk; the gate must come **before**
extraction. And it is **unbuilt prior art**: GraphRAG, LightRAG, HippoRAG, mem0, cognee, Letta
all extract everything that survives chunking (the only universal pre-LLM lever is exact
content-hash dedup); GraphRAG extraction is ~75% of indexing cost. Codex and Antigravity
independently converged on the design below.

## 2. Position — plane-E stage E1.5 (D25)

A new per-document stage on the Cloud Tasks chain (D12), at the **E1→E2 boundary**:

```
E0 ─► E1 ─► E1.5 gate ─►┬─ FULL        → E2 → E3   (Claimify → coref → ER → relations → supersession)
                        ├─ DEFERRED    → enqueue, E2 withheld behind a trigger
                        ├─ CHUNKS-ONLY → stop (no E2/E3 unless later promoted)
                        └─ dup (floor) → skip (reuse existing rows)
```

**E0 and E1 always run for every document** — they are cheap, deterministic, and *produce the
signals the gate consumes*; running them keeps every document retrievable in P1 (the
precondition for lazy self-triggering). The gate withholds only the expensive E2/E3 LLM layer,
never the retrieval floor. This is the literal realization of "progressive disclosure of
*processing*, not just summarization."

**Unit:** the **PageIndex section** is canonical (document-rollup for reporting; chunk-level only
as the CHUNKS-ONLY fallback granularity). One logical gate stage with two signal-collection
points (some signals are cheaper at the section/E0 stage, some need E1 vectors) — not two stages,
to avoid doubling state.

## 3. Mechanism — nested cheap-first cascade (D26)

D4's philosophy, one stage earlier. Cheapest-and-most-decisive first; stop when a tier decides.

| Rung | Signal | Cost | Typical outcome |
|---|---|---|---|
| **T-dup** | exact content-hash (doc/section/chunk) | ~0; doubles as D7 idempotency cache | `dup` → skip |
| **T-struct** | PageIndex node-type (references, bibliography, nav, boilerplate, legal) | near-free E0 metadata | `chunks-only` (deterministic) |
| **T-novel** | embedding / MinHash near-dup vs already-extracted high-`evidence_count` sections (reuses E1 vectors) | bounded ANN — **budget it; not "a cosine" at 10⁸ claims** | near-dup → `chunks-only`/`deferred` |
| **T-salience** | distilled small classifier (fastText/BERT-class; features = density + source trust + structural + novelty) | ~6× cheaper than an LLM, GPU-free | band → tier |

- **The frontier LLM judge is OFF the hot path** — it labels the seed/golden set the classifier
  distills from, never a per-section call. Distillation (label once with an oracle, classify
  cheaply) is the only economically sound way to use LLM judgment here.
- **Escalate uncertain sections to DEFERRED, never hard-reject to CHUNKS-ONLY.**
- **Override-to-FULL signals:** never-defer source classes (first-party / user-authored /
  curated) and change-of-state / temporal lexical markers (the pre-extraction proxy for
  supersession-bearing content — see the zombie-fact risk).

## 4. The three tiers (+ floor)

| Tier | E1 | E2/E3 | P1 retrieval | P2 graph |
|---|---|---|---|---|
| **FULL** | always | run now | chunks + claims + fact-labels | edges projected |
| **DEFERRED** | always | withheld; E2 enqueued behind a trigger | chunks searchable now; claims/relations appear after promotion | nothing until promoted |
| **CHUNKS-ONLY** | always | never (unless promoted) | chunks searchable (nothing lost from retrieval) | no edges |
| **dup** | skip | skip | existing rows reused | reused |

## 5. State — durable, versioned Postgres; the queue is a projection (D27)

The defer decision is **first-class append-only Postgres state**, never only a Cloud Tasks
message (a queue purge must not silently drop documents — the failure mode D7 forbids).

```
gate_decisions (append-only — the verdict)
  document_id, section_id (PageIndex node), tier ∈ {full,deferred,chunks_only,dup},
  features jsonb, salience_score, gate_version, deferred_trigger nullable,
  decided_at, superseded_by

document_extraction_state (current state — drives the queue)
  document_id, section_id,
  state ∈ {pending, full_done, deferred, backfill_queued, backfilling, backfill_done,
           chunks_only, failed},
  processing_version, retrieval_count, last_retrieved_at, error_count, last_error,
  heartbeat_expires_at, updated_at

salience_gate_versions(gate_version, model_name, thresholds/bands jsonb, classifier_id, configured_at)
```

- Queue drained via `FOR UPDATE SKIP LOCKED`; Cloud Tasks enqueued **atomically with the state
  flip via transactional outbox**; backfill idempotent on `content_hash + processing_version`
  (D12); stale-task sweeper / heartbeat reconciler.
- **Rebuild semantics (D7):** rebuild reads the *stored* tier and never re-runs the gate. PITR
  restores the exact outstanding-work set; the queue regenerates by SQL.
- **Determinism caveat (state plainly):** deterministic rungs (hash/structural/near-dup) are
  recomputable; the **salience/LLM rung is replay-from-storage only** (model-endpoint drift). So
  "rebuildable" for the gate means *stored & auditable*, not *recomputed* — pin versions AND
  store outputs.

## 6. Lazy promotion triggers, priority order (D28)

A DEFERRED section is promoted to E2 by, in priority order:

1. **on-scope-interest** — a K2 scope's declared entity/predicate interest (D16,
   `scope_interests`) sweeps matching deferred docs. Highest leverage: ties cost to demand,
   where ugm beats LazyGraphRAG's query-random laziness.
2. **on-first-retrieval** — a P1 hit on a deferred chunk enqueues its E2 asynchronously (raw
   text served immediately; **no synchronous LLM on the query path**, D9). Lazy materialization,
   but *persisted to the ledger* — the trade LazyGraphRAG doesn't make.
3. **bounded steady-state drain** — a low-priority worker guarantees deferred ≠ never (a
   freshness SLA, like D7's rebuild cadence).
4. **gate-version re-classification** — a better gate promotes previously-deferred docs as a
   version-filtered batch.

Promotion starts at E2 over the existing E1 chunks; E0/E1 are not reprocessed.

## 7. Recall envelope — defer-don't-DROP (D29)

The immutable E0/E1 backstop (D1) is what makes aggressive gating safe — a skipped section is
*un-extracted, not lost*; backfill is routine idempotent re-extraction.

1. **Output is never DELETE** — only `{FULL, DEFERRED, CHUNKS-ONLY, dup}`.
2. **Always-full E1** — deferred ≠ unindexed; every doc can self-trigger.
3. **Never-defer classes** — source-trust pinning + change-of-state lexical up-weight.
4. **Bounded drain** — deferred is a scheduler, not a discard.
5. **Canary + sampled audit** — rare-but-critical facts planted in the golden set; CI fails if a
   candidate threshold routes a canary to DEFERRED without a backfilling trigger; sample the
   deferred stream for **per-fact false-skip rate** (tune against per-fact loss, never corpus
   average). Optional K3 belief guard: exclude mostly-still-deferred entities from belief
   promotion.

**Bias recall-conservative:** over-defer is cheap and recoverable; over-extract silently poisons
relations/graph/beliefs.

## 8. Cost model (D30)

`Cost ≈ g + C_E2E3 × (f_full + f_def·r_retrieve)` — `g` = per-section gate cost, `r_retrieve` =
fraction of deferred sections eventually extracted.

- **Honest lever:** salience-skip alone ≈ **1.5–2×** (E2/E3 → ~55–65% of baseline); the ~10× O3
  imagined needs the DEFERRED/never-retrieved tier carrying most of the weight (LazyGraphRAG's
  0.1% proves the ceiling exists).
- **R9 impact, favorable:** the three 10⁸ tables (`mentions`/`resolution_decisions`/
  `relation_evidence`) are E2/E3 outputs → they shrink by `(f_full + f_def·r_retrieve)`; R9 gets
  *more* comfortable and its load-test should be sized against gated volume. `documents`/`chunks`
  do not shrink (E1 always runs). `gate_decisions` is negligible.
- **Break-even discipline:** ship no multiplier and no salience threshold without a measured
  filter rate; define a break-even multiplier below which the gate's complexity + E1.5 latency +
  recall risk + *its own aggregate compute* is net-negative; the spike must clear it.

## 9. Phasing

- **Phase 1 (free, no training data):** T-dup + T-struct + T-novel + the DEFERRED machinery +
  defer-don't-DROP contract + the Postgres state tables. Captures the references/boilerplate/
  near-dup cases that motivate O3 with zero ML.
- **Phase 2 (behind the O6 golden set + break-even spike):** the distilled T-salience classifier;
  on-first-retrieval + bounded-drain triggers; per-tier + false-skip metrics.
- **Phase 3:** on-scope-interest fan-out (D16); gate-version re-classification; K3 belief guard.

## 10. Open spikes (gate the build on these — D30)

1. **Bound the gate's own aggregate compute** (the #1 risk): sections-per-doc, gate-cost-per-
   section, whether T-salience truly reuses E1's prompt cache (if it needs its own prompt, the
   cache doesn't help and it becomes a new fleet-scale LLM stage), and the T-novel ANN cost at
   10⁸ claims. If the gate isn't ≪ extraction *in aggregate*, it defeats its purpose.
2. **Measure the filter rate + define break-even** on a real corpus slice (`f_full/f_def/
   f_chunk/r_retrieve`).
3. **Harden rare-fact safeguards** — (i) does a deferred gem rank high enough in P1 (no edges /
   evidence_count) to self-trigger? (ii) extract-on-scope-interest is unbuilt yet load-bearing;
   (iii) **the zombie-fact / supersession-skip case** (skipping the only superseding evidence →
   serving a stale fact as current) — the highest-severity correctness risk; design + test
   change-of-state up-weighting; coordinate with the registry un-merge→supersession spike.
4. **Resolve never-defer-by-predicate circularity** — the gate runs before extraction so it can't
   know a section asserts `penicillin_allergy`; validate source-trust + lexical cues recover
   enough recall, or default high-stakes scopes to FULL.
5. **Validate the rebuild/determinism story** in a drill (stored tiers reproduce "corpus as gated
   so far"; salience rung is replay-from-storage).

## References
Decisions: D1, D4, D7, D9, D12, D16, **D25–D30** (`decisions.md`). Analysis:
`plan/analysis/value_gate_research/` (V1–V6, verify/, SYNTHESIS.md; external_agents Codex V2 +
Antigravity V3). Related: `plan/analysis/objections.md` (O3, O6).
