# V6 — Integrating the value gate into the ugm pipeline

**Question.** Where does the salience/value gate (O3) sit in plane E (E0→E1→E2→E3 boundary;
per-document vs per-section vs per-chunk)? How is the gate/defer **decision** itself made
versioned, rebuildable state (D7) — recomputable and stored, never a silent drop? How does it
interact with the per-doc trigger model (D12) and the D4 cheap-first cascade? What is the cost
model (filter rate × per-stage savings) and how does it reshape the R9 scale numbers (which
"assume full extraction")? What do the **full / deferred / chunks-only** tiers mean concretely
for E1/E2/E3 and retrieval? Recommend the integration design + cost model + metrics, tied to
D1/D4/D7/D12 and O3, and to `registry_research/SYNTHESIS.md` (which flagged O3 as upstream of
R7/R9).

Evidence base: repo archaeology in `value_gate_research/repo_findings/*.md` and
`registry_research/repo_findings/*.md`; design context `objections.md` O3, `decisions.md`
D1/D4/D7/D12, `overall_design.md` plane E / trigger table, `entity_registry.md`. Primary
external sources fetched live (cited inline). "not found" = grepped/inspected and absent.

---

## 1. Key findings

1. **The gate is a new E-plane stage at the E1→E2 boundary, per-section (PageIndex node),
   not per-chunk and not per-document.** E0 (markdown + PageIndex hierarchy + node summaries)
   and E1 (chunking) are cheap, deterministic, and *produce the very signals the gate needs*
   (section structure, node summaries, embeddings, near-dup candidates). E2 (Claimify + coref +
   ER) and E3 (relation normalization + supersession cascade) are the expensive LLM stages O3
   targets. So the gate fires **after E1, before E2**, and decides per **PageIndex section**
   (the references section vs the core-findings section — O3's own example), with the document
   as the rollup unit and the chunk as the fallback granularity for the `chunks-only` tier.
   Per-document is too coarse (a good paper has a junk references section); per-chunk is too
   fine to be cheap and loses the structural signal E0 already computed.

2. **No prior system implements this gate — confirmed by counter-example across 5 repos —
   but two real primitives exist to lift, and a third (lazy extraction) is now validated by a
   shipping Microsoft system.** GraphRAG/LightRAG/HippoRAG/mem0/cognee all extract everything
   that survives chunking; their only pre-LLM cost lever is **exact content-hash dedup**
   (idempotent re-ingest), never value/salience/novelty
   (`value_gate_research/repo_findings/graphrag_lightrag_hipporag.md` §1–4;
   `mem0_cognee.md` bottom-line). That exact-hash dedup is the *floor* tier of our gate (cheap,
   already-built). The **defer-to-retrieval** half of O3 is exactly **LazyGraphRAG**, which
   defers *all* LLM use to query time and costs **0.1% of full-GraphRAG indexing** — a 1000×
   lever, live-verified below. So O3's two proposals (salience gate + lazy extraction) map onto
   one borrowed floor + one validated deferral pattern + one genuinely-unbuilt middle tier ugm
   must add.

3. **The gate VERDICT must be a first-class, append-only, versioned row — the same
   transcript/verdict epistemology as claims/relations (D2/D3) and resolution_decisions
   (entity_registry §4).** A `gate_decisions` row per (document, section) stamped with
   `gate_version`, the cheap features that drove it, the tier verdict
   (`full|deferred|chunks_only|dup`), and `superseded_by`. This makes D7 hold for the gate:
   the verdict is **recomputable** (re-run the gate → new rows superseding old), the dropped
   text is **never lost** (E0/E1 already persisted it in Postgres+GCS; the gate withholds E2,
   it does not delete), and a later "promote everything to full" is a **re-resolution campaign**
   (batch job), not a migration. A silent `if low_value: return` would violate D7 and is
   exactly the anti-pattern.

4. **Cost model: with a conservative filter mix (≈40–60% of sections diverted off the full-E2
   path), and E2/E3 being the LLM cost center, expected indexing-LLM cost drops to roughly
   40–60% of the full-extraction baseline — and the R9 row counts collapse correspondingly,
   because `mentions/resolution_decisions/relation_evidence` (the 10⁸ tables) are *outputs of
   E2/E3*.** GraphRAG's own documentation quantifies the prize: **graph extraction ≈ 75% of
   indexing cost** (live-verified). O3 estimates "plausibly 10×"; that upper bound is only
   reachable via the lazy/deferred tier (LazyGraphRAG's 0.1% proves the ceiling exists), not via
   salience-skipping alone. SYNTHESIS.md already flagged this dependency: O3 "changes R9 row
   counts, R7 golden-set composition, R6 `other:` rates, R1/R8 load" and every downstream
   quantity is stamped "assumes full extraction" until O3 is decided. V6 is the decision that
   un-stamps them.

---

## 2. Evidence & detail with citations

### 2.1 Where the gate sits — the E1→E2 boundary, per-section

**Plane E is already a staged per-document chain ending at E2/E3**
(`overall_design.md:86–105`, D12 `decisions.md:213–223`): E0 files → E1 chunks → E2 claims →
E3 relations, each a Cloud Run worker that enqueues the next stage for that document. The gate
slots in as a stage between E1 and E2 because:

- **E0 already computes the structural signal for free.** E0 runs PageIndex producing
  "hierarchy + node summaries" and records cross-references/citations
  (`overall_design.md:92`, `:101`). A *section* = a PageIndex node. The references section, the
  acknowledgements, the boilerplate footer — these are *named nodes* with summaries before any
  gate runs. This is precisely the granularity O3 frames its objection at: "a paper's
  references section with the same enthusiasm as its core findings" (`objections.md:71–72`).
- **E1 already computes the semantic signal for free.** E1 does "semchunk → LLM context prefix
  per chunk → embed → P1" (`overall_design.md:94`). The chunk embeddings (already written to
  Lance/P1) are exactly the vectors a near-duplicate / novelty check needs — no new embedding
  cost. The context-prefix LLM call is *already prompt-cached* per E1, so the gate piggybacks on
  E1's existing model touch rather than adding a fresh LLM stage.
- **E2/E3 are the cost center O3 names.** E2 = coref + Claimify + tiered ER; E3 = relation
  normalization + supersession cascade (`overall_design.md:96–102`). These are the per-chunk LLM
  fan-outs that cognee (`extract_graph_from_data.py:166–173`, one structured LLM call per
  non-DLT chunk — `mem0_cognee.md` COGNEE §) and mem0 (one unconditional `add()` LLM call —
  `mem0_cognee.md` MEM0 §) spend unconditionally. Gating *before* E2 is the only place the
  saving is large.

**Granularity verdict — per-section, document-rollup, chunk-fallback:**
- *Per-document* is too coarse: O3's whole example is intra-document (good paper, junk
  references). A document-level verdict re-creates the bug.
- *Per-chunk* is too fine to be the primary unit: it discards the PageIndex structural signal
  E0 paid for, and a per-chunk gate decision is itself a cost. Per-chunk is the *fallback* unit
  used only inside the `chunks-only` tier (below).
- *Per-section (PageIndex node)* uses the structure already computed, matches O3's framing, and
  rolls up to a document-level summary verdict for reporting.

**Cross-system confirmation that this boundary is empty in prior art.** Grep across all five
clones for `salien|novel|relevan|worth|low.?value|importance` at the pre-extraction boundary
returns nothing actionable: GraphRAG `create_base_text_units.py` emits every chunk
(`graphrag_lightrag_hipporag.md` §1); LightRAG's only gate is exact content-hash dedup
(`pipeline.py:473,501,665`; `graphrag_lightrag_hipporag.md` §2); HippoRAG gates only on exact
chunk-hash OpenIE cache (`HippoRAG.py:238–242`; §3); cognee's `importance_weight` exists but is
"carried metadata, never used to skip extraction" — an unconditioned `0.5` constant with the
merge-time use an explicit `# TODO` (`mem0_cognee.md` COGNEE §,
`DocumentChunk.py:36`). **The E1→E2 gate is unbuilt prior art; ugm must add it**
(`graphrag_lightrag_hipporag.md` §4 net-for-ugm).

### 2.2 The three tiers — concrete meaning for E1/E2/E3 and retrieval

| Tier | Gate verdict | E1 | E2 (claims/coref/ER) | E3 (relations/supersession) | P1 retrieval | P2 graph |
|---|---|---|---|---|---|---|
| **full** | high-salience, novel | run (always) | **run now** — Claimify + coref + tiered ER | **run now** — normalize, evidence, supersession cascade | chunks **+ claims + relation fact-labels** all searchable (D8/D9) | relations projected as edges |
| **deferred** | uncertain / low-priority but not junk | run (always) | **withheld**; enqueue a deferred-extraction task keyed to a trigger | withheld until E2 runs | **chunks searchable now**; claims/relations appear *after* the deferred E2 fires | nothing until promoted |
| **chunks-only** | low-value or near-dup or boilerplate (references, footers) | run (always) | **never run** (unless promoted) | never run | chunks searchable (so nothing is *lost* from retrieval), no claims/relations minted | no edges |
| **dup** (floor) | exact content-hash match of an already-processed section | skip | skip (already done) | skip | existing rows reused | reused |

Key properties:
- **E1 always runs.** Chunking + embedding are cheap and deterministic and are what keeps the
  *retrieval floor* intact: even `chunks-only` and `deferred` documents are findable via P1
  semantic/BM25 search (`overall_design.md:94`, D9 `decisions.md:169–188`). The gate never
  blinds retrieval; it only withholds the *expensive structured layer* (claims→relations→graph).
  This is the literal realization of O3's "progressive disclosure should apply to *processing*,
  not just summarization" (`objections.md:80–81`).
- **`deferred` is the lazy-extraction tier and has live prior art.** LazyGraphRAG (Microsoft
  Research) defers **all** LLM use to query time, with indexing cost "identical to vector RAG and
  0.1% of the costs of full GraphRAG" — a ~1000× reduction (live-fetched, see Sources). Its index
  uses only NLP noun-phrase extraction + graph statistics; LLM fires on retrieval, budgeted by a
  "relevance test budget" parameter. For ugm, `deferred` = "E1 done, E2 enqueued behind a
  trigger" — the trigger being **first retrieval of the section's chunks** or **a K2 scope
  declaring interest in its entities** (exactly O3's two proposed triggers,
  `objections.md:78–80`). This is a clean fit for D12: the deferred E2 task is just another
  per-document chain link, fired by a retrieval/interest event instead of by E1-completion.
- **`chunks-only` is the salience-skip tier.** It is what makes the references section cost
  zero E2/E3 LLM. Promotion is always possible (re-gate → `full`), so skipping is reversible,
  not destructive (D7).

### 2.3 The gate decision as versioned, rebuildable state (D7)

D7 requires every derived store to be "reproducible by a tested batch path, exercised routinely"
(`overall_design.md:55–56`), and rebuild guarantees apply to plane E (Postgres-authoritative,
D1 `decisions.md:13–26`). A gate that *silently drops* text breaks both: the drop is neither
recorded nor recomputable, and the dropped text never reaches E2 again even after a better gate
ships. The fix is to make the verdict a row, following the exact pattern already chosen for
resolution decisions (`entity_registry.md:54–85`) and claims/relations (D2/D3):

```
gate_decisions  (append-only — the verdict)
  document_id, section_id (PageIndex node), 
  tier  ∈ {full, deferred, chunks_only, dup},
  features  jsonb,         -- the cheap signals that drove it (see §2.4)
  gate_version,            -- pinned model/prompt/threshold set (D12 versioning)
  decided_at, superseded_by,
  deferred_trigger  nullable  -- e.g. 'first_retrieval' | 'scope:<id>' for the deferred tier
```

Properties, mapped to decisions:
- **Recomputable (D7).** Re-running the gate with a new `gate_version` writes new rows that
  supersede old ones — identical mechanics to embedding re-versioning (D12,
  `decisions.md:213–223`) and to resolution re-decisions (`entity_registry.md:75–77`). The set of
  `chunks_only` sections at any past `gate_version` is queryable for audit.
- **Never a silent drop (D1/D7).** E0/E1 already persisted the section's text (Postgres
  metadata + GCS bytes, `overall_design.md:46–48`). The gate **withholds E2**; the input is
  intact. "Promote all `deferred`/`chunks_only` to `full`" is a batch re-extraction campaign over
  a `WHERE tier != 'full'` filter — a rebuild path, exercised routinely, not a DR script. This is
  the gate-side analogue of "rebuildable from Postgres is exercised every cycle instead of rotting"
  (D7 `decisions.md:131`).
- **Idempotent + content-hashed (D12 worker discipline).** The `dup` tier reuses LightRAG's
  exact content-hash floor (`compute_text_content_hash`, `pipeline.py:473`) and cognee's
  file-level `content_hash` skip (`ingest_data.py:150–151`,
  `mem0_cognee.md` COGNEE §) — the only pre-LLM levers prior art actually ships — keyed by the
  same "content hash + processing version" D12 already mandates for all E workers
  (`decisions.md:217`).

### 2.4 Interaction with D4's cheap-first cascade

D4 is itself a cheap-first cascade *inside E3's supersession detection*: novelty gate →
`(entity_id, predicate)` blocking → exact → fuzzy → embedding → small model → frontier LLM, so
"write-side LLM cost scales with ambiguity, not volume" (`decisions.md:66–81`). **The V6 gate is
the same philosophy applied one stage earlier** — at the E1→E2 boundary instead of inside E3 —
so that E2 LLM cost scales with *value*, not volume. They compose as two independent rungs:

```
E1 done
  └─► [V6 SALIENCE GATE]  cheap-first, ascending cost:
        T-dup    exact content-hash (LightRAG/cognee floor)         → dup, skip E2
        T-struct PageIndex node type (references/ack/footer)         → chunks_only (deterministic)
        T-novel  embedding near-dup vs already-extracted sections    → chunks_only / deferred
                 (reuses E1 embeddings already in P1 — no new cost)
        T-salience small-model salience score on node summary        → full / deferred / chunks_only
                 (the only LLM rung; piggybacks E1's cached context call)
  └─► full → E2 → E3  (then D4's OWN cheap-first cascade runs for supersession)
```

So there are **two cheap-first cascades, nested**: V6's gate decides *whether* a section reaches
E2 at all; D4's cascade decides *how expensively* E3 adjudicates the relations that result. V6
shrinks D4's input volume; D4 is unchanged in mechanism. Neither replaces the other. This matches
SYNTHESIS.md's refinement of D4 — "make the cheap tier *escalate* near-misses, never auto-reject"
(SYNTHESIS §3 CONFIRMED-D4): the V6 gate's `T-salience` rung should **escalate uncertain
sections to `deferred` (re-examinable), never hard-`chunks_only`-reject**, so an under-salience
false-negative is recoverable at first retrieval rather than lost.

### 2.5 Interaction with the D12 trigger model

D12: "L0→L1→L2 chain per document; aggregates debounced" (`decisions.md:213–223`). V6 fits this
cleanly and extends it:
- **`full`** = the existing chain — E1-completion enqueues E2 immediately, as today.
- **`chunks-only`** = the chain *stops at E1* for that section. The per-doc chain "ends at E2"
  becomes "ends at E1 for skipped sections, E2 for full sections" — a per-section early
  termination, fully inside D12's per-document model.
- **`deferred`** = a *new trigger source* for E2: instead of E1-completion, the E2 task for a
  deferred section is enqueued by a **retrieval event** (the section's chunk is returned by a P1
  query) or a **scope-interest event** (a K2 scope declares interest in entities the section's
  node-summary mentions). This is D12-compatible because E2-on-deferred is still "a Cloud Tasks
  worker, idempotent by content-hash+version, 2 retries + DLQ" (`decisions.md:217`) — only the
  *enqueue trigger* differs. It is also the missing piece SYNTHESIS/repo-findings flagged: prior
  art "has no trigger that *withholds* the expensive call" (`mem0_cognee.md` relevance §);
  `deferred` is precisely that withholding trigger.

One caution to flag (gap, §3): the deferred-E2-on-retrieval path adds **first-retrieval latency**
for a deferred section's structured layer. Retrieval itself stays zero-LLM (D9,
`decisions.md:177`) because chunks are always searchable; but the *claims/relations* for a
deferred section won't exist until the deferred E2 completes. Acceptable iff the product tolerates
"chunks now, structured facts shortly after first touch" — needs a product decision.

### 2.6 Cost model: filter rate × per-stage savings, and the R9 reshape

**Where the LLM cost is.** GraphRAG documentation (live-verified): "We estimate graph extraction
to constitute roughly 75% of indexing cost" (`docs/index/methods.md:44`,
`graphrag_lightrag_hipporag.md` §1, confirmed via web). In ugm terms, E2+E3 (Claimify, coref,
tiered ER, relation normalization, supersession adjudication, fact-label embedding D8) are the
analogue of that 75% extraction cost; E0/E1 are the cheap deterministic remainder.

**The model.** Let:
- `f_full`, `f_def`, `f_chunk`, `f_dup` = fraction of sections routed to each tier (∑ = 1).
- `C_E2E3` = per-section full-extraction LLM cost (the cost center).
- `g` = gate cost per section (cheap: one small-model salience call piggybacking E1's cached
  context call + embedding near-dup over vectors already in P1 ≈ a few % of `C_E2E3`).

Indexing-LLM cost per section, **steady state** (deferred sections that are *never retrieved*
never pay E2):

```
Cost ≈ g + C_E2E3 × ( f_full + f_def × r_retrieve )
```
where `r_retrieve` = fraction of deferred sections eventually retrieved (the lazy lever:
LazyGraphRAG's 0.1% is the `f_full→0, r_retrieve→tiny` limit). `f_chunk` and `f_dup` contribute
**zero** `C_E2E3`.

**Worked illustrative bands** (filter rates are *modeled, not measured* — see §3; these are
planning bands, not benchmark numbers):

| Scenario | f_full | f_def | f_chunk+dup | r_retrieve | E2/E3 LLM cost vs full-extraction baseline |
|---|---|---|---|---|---|
| Conservative (salience-skip only, no lazy) | 0.55 | 0.10 | 0.35 | 1.0 (treat def≈full) | **≈ 65%** (0.55+0.10) + g |
| Moderate (skip + true defer) | 0.45 | 0.25 | 0.30 | 0.4 | **≈ 55%** (0.45 + 0.25×0.4) + g |
| Aggressive (lazy-leaning, references/boilerplate-heavy corpus) | 0.25 | 0.35 | 0.40 | 0.3 | **≈ 36%** (0.25 + 0.35×0.3) + g |
| Lazy ceiling (LazyGraphRAG-style, validated prior art) | →0 | most | rest | tiny | **≈ 0.1–a few %** (external: 0.1% of full GraphRAG) |

So **salience-skipping alone is a ~1.5–2× lever** (35–45% off E2/E3); the **10× O3 claims is only
reachable by leaning on the `deferred`/lazy tier** (LazyGraphRAG proves a 1000× *ceiling* exists,
so 10× is conservatively in-reach when most low-value content is deferred-and-never-retrieved).
O3's own framing — "plausibly 10×" (`objections.md:82`) — is consistent with this only if the
lazy tier carries most of the weight; salience-skip alone does not get there. **This is the
load-bearing nuance V6 adds to O3.**

**Reshaping R9 (the part SYNTHESIS demanded).** SYNTHESIS R9: the three 10⁸ tables are
`mentions / resolution_decisions / relation_evidence`, sized "assumes full extraction" and
"contingent on O3's outcome (G9)" (SYNTHESIS R9, §5 spike-1, O3 stamp at §3 "mark every
downstream quantity 'assumes full extraction'"). Crucially **all three tables are *outputs of
E2/E3*** — mentions are E2 outputs, resolution_decisions are ER outputs, relation_evidence is E3
output. Therefore the gate's filter rate multiplies directly into their row counts:

```
rows_mentions     ≈ rows_mentions_full     × (f_full + f_def × r_retrieve)
rows_resolution   ≈ rows_resolution_full   × (f_full + f_def × r_retrieve)
rows_relation_evid≈ rows_relation_evid_full× (f_full + f_def × r_retrieve)
```

At the Moderate band (~0.55), the three 10⁸ tables become ~5–6×10⁷ — still in R9's "engineer the
indexes not the row counts" comfort zone, now with *more* headroom, and with the partition/index
load-test (SYNTHESIS R9 spike-6) sized against gated volume, not full-extraction volume. **The
gate makes R9 more comfortable, never less.** It does *not* shrink the E0/E1-level tables
(`documents`, `chunks`) — those still scale with corpus size because E1 always runs; only the
structured-extraction tables shrink. The new cost is the `gate_decisions` table itself: one row
per (document, section) per `gate_version` — bounded by section count (≪ chunk count ≪ mention
count), negligible against the 10⁸ tables.

**R7 / golden-set coupling (SYNTHESIS's O3→R7 link).** SYNTHESIS flags O3 "changes R7 golden-set
composition" (§3, §5 spike-1). The gate adds a *new* labeled asset O6/R7 must cover: a
**gate-verdict golden set** — sections human-labeled `should_be_full / fine_to_skip` — to tune
the four-rung thresholds with Wilson CIs exactly as R7 prescribes for ER thresholds (SYNTHESIS
R7). The dangerous metric is the **false-skip rate** (a salient section sent to `chunks_only`):
its cost is a *silently missing fact*, the same failure class as a missed supersession
(`entity_registry.md:13–18`). This is why the gate must escalate-to-deferred, not reject.

---

## 3. Confidence & gaps

**Confidence: MEDIUM.**

High-confidence (verified): the *placement* (E1→E2 boundary, per-section using PageIndex/E0
signal) follows directly from `overall_design.md:92–102` and D12; the *absence of this gate in
all prior art* is grep-verified across five clones (`value_gate_research/repo_findings/*`,
cross-checked against `registry_research/repo_findings/*`); the **75% extraction-cost** figure is
confirmed in Microsoft's own GraphRAG docs (web + repo `docs/index/methods.md:44`); the
**LazyGraphRAG 0.1%-of-full-GraphRAG / defer-all-LLM-to-query** figures are live-fetched from
Microsoft Research (validating O3's lazy-extraction half as real, shipping prior art); the
verdict-as-versioned-row design is a direct re-application of the already-decided
transcript/verdict pattern (D2/D3, `entity_registry.md:54–85`).

Gaps / not verified (flagged honestly):
- **The "~98% junk" figure in O3 is NOT independently verified.** O3 cites "the Mem0 audit
  finding: ~98% of unfiltered extracted entries were junk" (`objections.md:70`). Web search did
  not surface a primary source for that exact 98% number (Mem0's public LOCOMO claims are about
  token/latency reduction and +26% accuracy, not a 98%-junk audit). **Treat the 98% as an
  unverified anecdote, not a planning input.** The defensible planning anchor is the *structural*
  argument (references/boilerplate/duplication are a large, corpus-dependent fraction) plus the
  *verified* 75%-extraction-cost and 0.1%-lazy-ceiling figures.
- **All filter-rate bands in §2.6 are MODELED, not measured.** `f_full/f_def/f_chunk` and
  `r_retrieve` depend entirely on the corpus and must be measured on a representative slice before
  any cost claim is committed — exactly SYNTHESIS's spike-1 ("prototype a cheap per-doc/section
  salience gate and measure the filter rate on a representative corpus slice"). The 10×/O3 claim
  is *plausible* given the lazy ceiling but **unproven for ugm's corpus**.
- **Deferred-extraction product latency** (claims/relations absent until first retrieval of a
  deferred section) is a UX trade-off needing a product decision (§2.5).
- **Interaction with E3 supersession is subtle.** If a `chunks_only`/`deferred` section contained
  the *only* evidence that supersedes a fact, skipping it produces a zombie fact (stale relation
  served as current) — the precise existential risk in `entity_registry.md:13–18`. The gate's
  salience signal should **up-weight temporal/change-of-state language** (supersession-bearing
  sentences) toward `full`, but this heuristic is unvalidated.
- **Single-source for the integration reasoning.** Per SYNTHESIS's provenance note, the
  `external_agents/*` independent cross-checks have repeatedly produced 0 bytes; this V6 analysis
  is single-source and should carry the same one-notch-lower confidence until a spike measures the
  filter rate.

---

## 4. Recommendation for ugm

**Adopt the gate as a new plane-E stage `E1.5` (the salience gate), per-PageIndex-section,
verdict-stored, between E1 and E2.** Concretely:

1. **Placement (ties D12, O3).** Insert `E1.5 gate` into the per-document Cloud Tasks chain:
   E0 → E1 → **E1.5 gate** → E2(full) | enqueue-deferred | stop(chunks-only). Granularity =
   PageIndex section, document rollup, chunk fallback for `chunks-only`. E1 *always* runs so the
   retrieval floor (P1 chunk search) is never blinded — this is O3's "progressive disclosure of
   *processing*" realized.

2. **Verdict as versioned, rebuildable state (ties D1/D7).** Add a `gate_decisions` append-only
   table (§2.3): `(document_id, section_id, tier, features jsonb, gate_version, decided_at,
   superseded_by, deferred_trigger)`. The gate **withholds E2, never deletes** input (E0/E1
   already persisted it). "Re-extract everything" = a batch campaign over `WHERE tier != 'full'`,
   exercised routinely as a D7 rebuild path, not a DR script.

3. **Gate = nested cheap-first cascade (ties D4).** Four ascending rungs:
   `T-dup` exact content-hash (lift LightRAG `compute_text_content_hash` + cognee `content_hash`
   — the only pre-LLM levers prior art ships) → `T-struct` PageIndex node-type (references/
   ack/footer → `chunks_only`, deterministic, zero LLM) → `T-novel` embedding near-dup reusing
   E1's P1 vectors (zero new embedding cost) → `T-salience` one small-model score on the node
   summary, piggybacking E1's cached context call. **Escalate uncertain sections to `deferred`,
   never hard-reject to `chunks_only`** (SYNTHESIS D4 refinement: cheap tier escalates, never
   auto-rejects). V6's gate shrinks the *input* to D4's E3 cascade; D4's mechanism is unchanged.

4. **Three tiers with the §2.2 contract.** `full` = E2+E3 now; `deferred` = E1 done, E2 enqueued
   behind a **retrieval-event or scope-interest trigger** (the lazy tier — validated by
   LazyGraphRAG's defer-all-LLM-to-query, 0.1%-of-full-GraphRAG indexing); `chunks-only` = E1
   only, chunks searchable, no claims/relations (the references-section case); `dup` = skip.
   Promotion is always available (re-gate → `full`).

5. **Cost model + metrics (ties O6/R7, SYNTHESIS O3→R7/R9 link).** Plan to the §2.6 model:
   `Cost ≈ g + C_E2E3 × (f_full + f_def × r_retrieve)`. **Commit no cost number until the filter
   rate is measured on a representative corpus slice** (SYNTHESIS spike-1). Ship from day one:
   per-tier section counts + `gate_version`; **false-skip rate** against a gate-verdict golden set
   (the dangerous metric — a skipped salient section = a silently missing fact, same failure class
   as a missed supersession); deferred→retrieved conversion (`r_retrieve`, the realized lazy
   lever); and E2/E3 LLM-spend-per-document vs the full-extraction baseline. Size R9's
   partition/index load-test against **gated** volume — the three 10⁸ tables shrink by the
   `(f_full + f_def·r_retrieve)` factor because they are E2/E3 outputs, making R9 *more*
   comfortable; the `documents`/`chunks` tables do not shrink (E1 always runs).

6. **Guardrails to flag in `registries_design.md` / `e2_e3_*_design.md`.** (a) Up-weight
   temporal/change-of-state language toward `full` so supersession-bearing sentences are not
   skipped into zombie facts (`entity_registry.md:13–18`). (b) Get a product decision on
   first-retrieval latency for deferred structured facts. (c) Carry this analysis at one-notch
   confidence (single-source per SYNTHESIS provenance note) until the spike runs. (d) Drop the
   unverified "98% junk" anecdote from planning inputs; anchor on the verified 75%-extraction /
   0.1%-lazy figures and the measured filter rate instead.

This is the decision that **un-stamps the "assumes full extraction" caveat** SYNTHESIS placed on
R7 and R9: V6 defines the gate, makes its verdict rebuildable state (D7), nests it with D4,
triggers it through D12, and gives R9 a measured multiplier and R7 a new golden-set asset.

---

### Sources

Design (repo): `objections.md` O3 (lines 65–87, priority 156–161); `decisions.md` D1 (13–26),
D4 (66–81), D7 (116–134), D12 (213–223); `overall_design.md` plane-E chain (86–105), trigger
table (37–41), stores (43–56); `entity_registry.md` transcript/verdict (54–85), ER-existential
(13–18), quality processes (154–178); `registry_research/SYNTHESIS.md` R7/R9 + O3 stamps
(§3 CHANGE, §3 CONTRADICTIONS O3, §5 spike-1, R9, R7).

Repo archaeology (this effort): `value_gate_research/repo_findings/graphrag_lightrag_hipporag.md`
(§1 GraphRAG no-gate + 75% cost `docs/index/methods.md:44`; §2 LightRAG content-hash dedup
`pipeline.py:473,501,665`; §3 HippoRAG chunk-hash cache `HippoRAG.py:238–242`; §4 net-for-ugm);
`value_gate_research/repo_findings/mem0_cognee.md` (mem0 unconditional `add()` LLM; cognee
per-chunk LLM `extract_graph_from_data.py:166–173`, `importance_weight` unused `DocumentChunk.py:36`,
file content-hash `ingest_data.py:150–151`); `registry_research/repo_findings/*` (ER/identity
cross-checks).

External (live-fetched June 2026):
- GraphRAG Methods — graph extraction ≈ 75% of indexing cost; FastGraphRAG = NLP-not-LLM:
  <https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md>
- LazyGraphRAG (Microsoft Research) — defers ALL LLM to query time; indexing cost "identical to
  vector RAG and 0.1% of the costs of full GraphRAG" (~1000×); relevance-test-budget knob:
  <https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/>
- Mem0 LOCOMO claims (token/latency/accuracy, **not** a 98%-junk audit — O3's 98% unverified):
  <https://mem0.ai/research> · <https://docs.mem0.ai/core-concepts/memory-evaluation>
