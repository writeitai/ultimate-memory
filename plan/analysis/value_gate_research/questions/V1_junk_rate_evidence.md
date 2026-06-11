# V1 — How much extracted content is LOW-VALUE at scale, and does junk degrade quality?

Research question (O3 premise): "most content is low-value." Verify/debunk the "~98% of
unfiltered memory entries are junk" claim attributed to a Mem0 audit, find its actual source,
and gather independent evidence on (a) noise prevalence in LLM extraction/memory and (b) whether
junk measurably degrades downstream KG/RAG quality. Conclude how strongly O3's premise is
supported.

Citation discipline: **[VERIFIED]** = read at source (URL / repo file:line). **[INFERENCE]** =
reasoned from verified facts. **[UNVERIFIED]** = claimed somewhere but I could not confirm the
underlying measurement. Repo file:line cites are to clones under `_additional_context/` via the
two `repo_findings/*.md` notes.

---

## 1. Key findings

1. **The "98% junk" claim is REAL and traceable — but it is one anecdote, not a benchmark.**
   The actual source is **mem0 GitHub issue #4573, "What we found after auditing 10,134 mem0
   entries: 97.8% were junk"** (Feb 23–Mar 26 2026, single deployment) [VERIFIED — issue
   fetched]. O3's "~98%" rounds 97.8%. It is **not** a controlled study, not a mem0-maintainer
   audit, and not multi-deployment: it is one user auditing one agent+human conversation stream
   on a Qdrant backend. So O3's framing ("the Mem0 audit finding") **overstates its authority** —
   it is a vivid existence proof, not a population statistic.

2. **The headline number is inflated by a pathological setup, but the underlying mechanism O3
   names is exactly right.** 52.7% of the junk was an agent re-extracting its own boot
   file / system prompt, plus heartbeat/cron noise and architecture dumps — artifacts of an
   agent-talking-to-agent loop, not generic corpus junk. Critically, the author found that
   **swapping the weak 2B model for Claude Sonnet 4.6 did NOT fix it** — junk only fell from
   ~97–98.5% to **89.6%**, because "a better model follows the extraction prompt more
   faithfully, which means it extracts more indiscriminately. The extraction prompt is the
   bottleneck, not the model." [VERIFIED — issue]. Root cause per the author: **"there's nothing
   between extraction and storage that checks whether a fact is grounded"** — i.e. *the missing
   value gate*, the precise gap O3 (and D4) target.

3. **Independent, peer-reviewed evidence confirms LLM-extracted graphs are heavily noisy and that
   the noise measurably degrades RAG quality.** "Less is More: Denoising Knowledge Graphs for
   RAG" (arXiv 2510.14271) shows you can **remove ~40% of entities and 30–60% of relations** from
   LLM-built KGs while *maintaining or improving* answer quality — denoising lifted LightRAG
   win-rate by **+8 to +17 percentage points** across four domains (e.g. CS 41.6%→58.4%)
   [VERIFIED — paper fetched]. That is direct causal evidence: junk in extraction → worse
   retrieval/generation, and pruning it helps. This is the strongest independent support for
   O3's "junk poisons everything downstream."

4. **Web-corpus and extraction-precision literature put a defensible floor under "most content is
   low-value" for general corpora.** Raw Common Crawl is "overwhelmingly noise"; after
   boilerplate-strip + dedup **only ~5–10% of bytes survive as usable text** [VERIFIED — survey],
   and LLM relation extraction hallucination rates run **3% (best OpenAI) to 27% (PaLM-Chat)**
   [VERIFIED — search]. So at *document-corpus* scale, "the majority of raw content is low-value"
   is well-supported (high confidence); the specific "~98% of memory entries" figure is
   setup-specific and should not be cited as a general rate.

**CONCLUSION:** O3's premise — *most extracted content is low-value, and unfiltered junk
degrades downstream quality* — is **empirically supported with MEDIUM-HIGH confidence.** The
*direction* is robust (multiple independent sources; one peer-reviewed causal result). The
*specific 98% number is weak* (n=1, pathological setup) and should be demoted from "the Mem0
audit finding" to "a documented anecdote consistent with broader evidence."

---

## 2. Evidence & detail with citations

### 2.1 Source trace of the "~98% junk" claim — DEBUNKED as a benchmark, VERIFIED as an anecdote

O3 (`objections.md:69`) says: *"cf. the Mem0 audit finding: ~98% of unfiltered extracted entries
were junk."* The actual artifact:

- **mem0ai/mem0 issue #4573** — *"What we found after auditing 10,134 mem0 entries: 97.8% were
  junk."* [VERIFIED — fetched twice]. Method: one user pulled their entire production collection
  (10,134 entries, 32 days) and ran a 3-phase audit.
  - **Phase 0:** 2,468 exact-hash duplicates + obvious hallucination clusters removed (incl. "668
    copies of a single feedback-loop hallucination").
  - **Phase 1:** cosine-similarity script flagged **2,943 near-duplicates (cosine > 0.95)** =
    37.6% of what remained.
  - **Phase 2:** manual review judged a further 6,070 entries junk.
  - **Survivors:** **224 "clean enough"**, of which 186 "had to be deleted and rewritten" →
    **only 38 of 10,134 (0.4%) kept as-is.** So depending on the bar, junk is 97.8% (loose) to
    99.6% (strict).
- **Junk composition** (skews the headline): Boot-file/system-prompt restating **3,200 (52.7% of
  junk)**, heartbeat/cron noise 700, architecture dumps 500, transient task state 450,
  hallucinated user profiles 315, identity confusion 200 [VERIFIED — issue]. **The single
  largest bucket is an artifact of an agent re-ingesting its own scaffolding**, not the
  boilerplate/near-dup/low-salience junk O3 cares about for a *document* corpus. This is the key
  caveat: **the 97.8% is not transferable to ugm's 1M-document setting as a point estimate.**
- **Model is not the fix (load-bearing for O3/D4):** gemma2:2b (days 1–20) → Claude Sonnet 4.6
  (days 21–32). Junk fell only to **89.6%**; author: *"The extraction prompt is the bottleneck,
  not the model … there's nothing between extraction and storage that checks whether a fact is
  grounded."* Top requested fix: *"A quality gate between extraction and storage"* [VERIFIED —
  issue]. **No maintainer rebuttal was visible in the fetched content** [could not verify a
  response either way].

This corroborates our own repo archaeology: mem0's active pipeline has **no pre-LLM value gate**;
the LLM call fires unconditionally on every `add()`, the ADD/UPDATE/DELETE/NONE controller is
*dormant*, and dedup is **byte-exact MD5 only** — trivially defeated by paraphrase
(`mem0_cognee.md:9-15,56-78`; `registry_research/.../mem0.md:26-32,44-49`). The audit is the
field consequence of that design: a recall-biased "when in doubt, extract … dedup downstream"
prompt (`prompts.py:578`, cited `mem0_cognee.md:48-52`) with no grounding check.

### 2.2 Independent evidence that LLM-extracted KGs are noisy AND that noise degrades RAG

- **"Less is More: Denoising Knowledge Graphs for RAG"** (arXiv 2510.14271) [VERIFIED — fetched]:
  - LLM-built KGs carry enough redundancy/error that **removing ~40% of entities and ~30–60% of
    relations maintains or improves** downstream answers; on Mix/Legal, comparable quality holds
    **up to 70% entity reduction.**
  - **Causal quality lift from denoising (LightRAG):** Agriculture 42.4%→57.6% (+15.2pp), CS
    41.6%→58.4% (+16.8pp), Legal 42.4%→51.6% (+9.2pp), Mix 46.0%→54.0% (+8pp). Similar gains on
    HippoRAG / LGraphRAG / GGraphRAG.
  - Token cost roughly flat or lower after denoising → **this is a quality lever first, cost
    lever second** in their framing.
  - This is the single strongest, peer-reviewed, *causal* datapoint for O3: noisy extraction
    measurably hurts retrieval+generation, and pruning it helps by double-digit points.
- **DEG-RAG / survey evidence** [VERIFIED — search snippet, arXiv 2510.14271 + survey]: "Without
  entity resolution or triple reflection, the performance of Graph-based RAG significantly
  degrades in all datasets." LLMs produce duplicate entities (morphology/casing/abbreviation/
  multilingual variants of one concept) and erroneous triples from outdated/incorrect source
  text. Consistent with our `entity_registry.md:18` ("over-merged entities create false hubs that
  poison graph-distance reranking") and the cross-system finding that GraphRAG/LightRAG/HippoRAG
  have **no value/salience gate, only exact-hash dedup** (`graphrag_lightrag_hipporag.md:6-12,
  143-159`).
- **GraphRAG's own cost framing** (`docs/index/methods.md:44`, via `graphrag_lightrag_hipporag.md:44-48`)
  [VERIFIED via repo note]: *"graph extraction ≈ 75% of indexing cost."* → A gate that drops a
  meaningful fraction of low-value chunks is a near-linear LLM-cost lever [INFERENCE], supporting
  O3's "plausibly 10×" *as plausibility, not a measured figure* — I found **no source measuring an
  actual 10× cost reduction from a salience gate** [UNVERIFIED].

### 2.3 Hallucination / extraction-precision rates (the "hallucinated" junk class)

- LLM information-extraction hallucination rates span **3% (best OpenAI) to 27% (PaLM-Chat)**;
  hallucination rate ≈ (1 − precision) for binary relation labels; models "default to generating
  plausible values rather than acknowledging uncertainty" [VERIFIED — search, multiple arXiv
  hits]. I attempted the primary source (arXiv 2508.14391) but the PDF body did not extract — so
  the per-model breakdown above is **[VERIFIED at search-snippet level, not at source]**; treat
  the 3–27% band as indicative, not precise.

### 2.4 Web-corpus boilerplate / duplication prevalence (the "boilerplate/near-dup" classes)

[VERIFIED — Common Crawl survey, arXiv 2407.07630 + secondary]:
- Raw Common Crawl is "overwhelmingly noise: navigation chrome, ad copy, SEO spam, generated
  boilerplate, broken HTML."
- Cross-snapshot dedup removes **60–80%** of bulk; one study found **23% duplicates** in a pool.
- Even *after* dedup, residual near-dups persist (**C4 3.04%, RealNews 13.63%**).
- **Net survival after boilerplate-strip + lang-filter + dedup ≈ 5–10% of bytes.**
- → For *general web/document corpora*, "the large majority of raw content is low-value" is
  well-established in LLM pretraining practice (high confidence). ugm ingests documents (E0→E1→E2),
  so this corpus-level evidence is **more directly transferable to ugm than the mem0 chat-memory
  anecdote.**

### 2.5 Taxonomy of "junk" (synthesized; each class mapped to the gate that should catch it)

| Junk class | What it is | Evidence it's prevalent | Cheapest catch (cascade tier) |
|---|---|---|---|
| **Boilerplate / chrome** | nav, headers/footers, cookie banners, signatures | CC: most of raw bytes; survival 5–10% [VERIFIED] | deterministic, pre-LLM (structural/heuristic) |
| **Navigation / references / scaffolding** | reference lists, ToCs, system prompts, config dumps | mem0 #4573: boot-file restating = 52.7% of junk [VERIFIED] | per-section salience gate (O3 tier-1) |
| **Exact duplicate** | byte-identical re-ingest | mem0 Phase 0 = 2,468; LightRAG/HippoRAG built on this | content-hash (LightRAG `pipeline.py:473`; HippoRAG chunk-hash) [VERIFIED via repo note] |
| **Near-duplicate / paraphrase** | same fact, ≥1 byte diff | mem0: 2,943 @ cosine>0.95 = 37.6% of remainder [VERIFIED]; C4 3%, RealNews 13.6% | embedding-novelty tier — *unbuilt in all surveyed repos* |
| **Trivia / low-salience** | true but worthless filler | denoising-KG: 40% entities removable w/o loss [VERIFIED] | salience gate / evidence-count prior |
| **Hallucinated** | facts not grounded in source | 3–27% extraction hallucination [VERIFIED-snippet]; mem0 "668 copies of one hallucination" | grounding check + domain/range constraints (D15) |
| **Identity-confused** | attributes mis-assigned (agent vs user, person vs process) | mem0: 200 identity-confusion + 315 hallucinated profiles [VERIFIED] | identity-aware extraction + ER (E-registry) |

This taxonomy is **synthesized by me** from the cited sources; the *class definitions* are mine
[INFERENCE], the *prevalence numbers* are each cited [VERIFIED where marked].

---

## 3. Confidence & gaps

**Overall confidence in O3's premise: MEDIUM-HIGH.**

What's solid [VERIFIED]:
- The "98% junk" claim has a real, locatable source (mem0 #4573, 97.8%); O3 cited it accurately
  in spirit.
- Independent, peer-reviewed *causal* evidence that extraction noise degrades RAG and that
  aggressive denoising helps by +8–17pp (arXiv 2510.14271).
- Corpus-level "most raw content is low-value" is standard, quantified LLM-pretraining knowledge
  (5–10% survival).
- The *mechanism* O3 attacks (no value/grounding gate before storage; exact-hash-only dedup) is
  confirmed absent in mem0, cognee, GraphRAG, LightRAG, HippoRAG (our repo notes).

Gaps / what I could NOT verify:
- **The 97.8% is n=1 and pathological** (52.7% = an agent eating its own boot file). It does
  **not** establish a general ~98% junk rate for *document* corpora — do not cite it as such.
- **No source measured the "plausibly 10×" cost reduction** from a salience gate [UNVERIFIED]; the
  ~75%-of-indexing-cost figure makes large savings *plausible* but the multiplier is unestablished.
- **Per-model hallucination breakdown** (3–27%) verified only at search-snippet level; the primary
  PDF (2508.14391) did not extract.
- **No maintainer/independent replication** of the mem0 audit was found [could not verify].
- **No measurement specific to ugm's design** (Claimify + relations + evidence-count). The closest
  proxy is the denoising-KG paper, which studies LLM-built KGs generally.

---

## 4. Recommendation for ugm (tied to D1/D4/D7/D12 and O3)

1. **Adopt O3's salience gate — but justify it on the VERIFIED evidence, not the 98% headline.**
   The defensible case is: (a) corpus-level 5–10% survival, (b) the denoising-KG +8–17pp causal
   lift, (c) the mem0 finding that *a better model makes junk WORSE, not better* ("extracts more
   indiscriminately"). That last point is the decisive argument for D4's **cheap-first cascade**:
   you cannot model-quality your way out of junk; you need a gate *before* extraction, not a
   smarter extractor. **Demote the "~98%" in `objections.md:69` to "a documented single-deployment
   audit (mem0 #4573, 97.8%) consistent with broader corpus evidence" — keep the objection, fix
   the citation.**

2. **D4 cascade, with the gate ugm's predecessors all lack.** Every surveyed system stops at the
   *exact-dup* rung (content-hash) and never reaches a *value* rung
   (`graphrag_lightrag_hipporag.md:149-159`). ugm should layer: exact content-hash (free, steal
   LightRAG `pipeline.py:473` / HippoRAG chunk-hash) → **embedding near-dup** (catches the 37.6%
   class mem0's MD5 misses) → **per-section salience** (catches the 52.7% references/scaffolding
   class) → LLM extraction only on survivors. The mem0 audit's own ranked fix list ("mark recalled
   memories so extraction doesn't re-extract them" + "quality gate between extraction and storage")
   is a ready blueprint.

3. **D12 triggers / lazy extraction is well-motivated by the references-section problem.** O3's
   "lazy extraction on first retrieval" directly addresses the boilerplate/references class: a
   paper's reference list is unlikely to ever be the retrieval target, so deferring its extraction
   costs nothing and avoids the GraphRAG "75% of indexing cost spent on everything" trap. Stage E2
   extraction behind a retrieval/interest trigger for low-salience sections; keep the per-document
   E0→E1→E2 chain eager only for high-salience content.

4. **D1 + D7 make the gate cheap to get wrong — exploit that to gate AGGRESSIVELY.** Because
   Postgres is authoritative (D1) and projections rebuild (D7), an over-aggressive salience gate
   that defers a useful section is *recoverable*: re-run extraction on the deferred queue and
   rebuild P1/P2. This asymmetry (under-extraction is cheap to fix, over-extraction poisons every
   derived layer per O3) argues for a **recall-conservative gate tuned toward dropping/deferring**,
   the opposite of mem0's "when in doubt, extract." The denoising-KG result (quality *improves*
   when 40% is pruned) says the safe operating point is well into aggressive territory.

5. **O6 dependency (flag, don't resolve here):** every threshold above (near-dup cosine, salience
   cutoff, defer-vs-extract) is untunable without the golden set O6 demands. The mem0 audit is the
   cautionary tale of shipping a gate-less pipeline with no junk-rate metric and discovering 97.8%
   junk 32 days later. ugm should instrument **junk-rate / drop-rate / deferred-rate as day-one
   production metrics** on the gate (O6), so the gate's threshold is measured, not hoped.

---

## Sources

- mem0 audit (PRIMARY for the claim): https://github.com/mem0ai/mem0/issues/4573
- Less is More: Denoising KGs for RAG: https://arxiv.org/abs/2510.14271 · html: https://arxiv.org/html/2510.14271v1
- Hallucination-Resistant Relation Extraction (per-model rates, body not extracted): https://arxiv.org/pdf/2508.14391
- Challenges with Massive Web-mined Corpora (boilerplate/dedup/survival): https://arxiv.org/html/2407.07630v1
- Common Crawl noise overview: https://zeroentropy.dev/concepts/common-crawl/
- Mem0 token-efficiency framing (context): https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm
- Repo archaeology (this project): `plan/analysis/value_gate_research/repo_findings/mem0_cognee.md`,
  `.../graphrag_lightrag_hipporag.md`; `plan/analysis/registry_research/repo_findings/mem0.md`
