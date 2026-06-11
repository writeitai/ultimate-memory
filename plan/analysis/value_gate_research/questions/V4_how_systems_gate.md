# V4 — How real systems gate/filter extraction (and where the ones that don't pay for it)

**Question.** Synthesize from the repo_findings how mem0, cognee, GraphRAG, LightRAG, and HippoRAG
gate/filter *which text gets extracted* before spending LLM cost. What is the actual industry
practice — gate, or extract-all? Where do the ones that don't gate pay for it? What should ugm
borrow?

**Scope of evidence.** Five cloned repos under `_additional_context/`, read in two prior passes:
`value_gate_research/repo_findings/{mem0_cognee.md, graphrag_lightrag_hipporag.md}` and
`registry_research/repo_findings/{mem0.md, cognee.md, lightrag_graphrag.md, letta_hipporag.md}`.
Every code claim below traces to those archaeology docs (which cite `file:line` in the clones);
I re-verify the two load-bearing external numbers (GraphRAG 75%, LazyGraphRAG 0.1%) against
vendor docs. "not found" = grepped and absent in the inspected checkout.

---

## 1. Key findings

1. **Industry practice is extract-all, not gate.** All five systems run the expensive
   extraction step on *everything that survives chunking* (cognee, GraphRAG, LightRAG, HippoRAG)
   or *every conversational turn* (mem0). **None implements a value / salience / novelty /
   relevance gate that decides "is this text worth extracting?" before paying the LLM.** This is
   unanimous across the corpus and directly validates objection O3: the gate ugm proposes is
   *unbuilt prior art* — a differentiator, not a catch-up feature.

2. **The only universal pre-LLM cost lever is exact-bytes idempotency, never selectivity.** What
   every system *does* build is content-hash dedup so re-ingesting identical bytes costs ~0:
   LightRAG (`compute_text_content_hash`, doc + chunk + filename), HippoRAG (chunk-hash OpenIE
   cache), cognee (file-level `content_hash`), mem0 (post-LLM MD5 memory dedup), GraphRAG
   (doc-id in the update pipeline). All are **byte-exact** — a one-word paraphrase, a boilerplate
   footer, or a references section that differs by a byte gets full extraction. This is
   *idempotency*, the cheapest rung of a D4 cascade — useful but **insufficient as the gate**.

3. **mem0 is the partial exception, and it inverts the order: the LLM call *is* the gate.** mem0
   delegates all filtering (chit-chat drop, novelty, coref, dedup) *into* one unconditional
   extraction prompt, then dedups exactly afterward. Its prompt explicitly chooses recall over
   cost — *"When in doubt, extract. A slightly redundant memory is far less costly than a missing
   one. The deduplication system downstream will handle true duplicates"* (`prompts.py:578`). So
   mem0 pays the LLM on **every turn** and only drops *purely phatic* content. This is a
   *quality* filter applied after the model is already paid for, not a *cost* filter.

4. **Where the extract-all systems pay: extraction dominates indexing cost, so non-selectivity is
   a near-linear cost multiplier on corpus size — and the two systems that attacked it did so by
   deferring/swapping the LLM, not by gating text.** Microsoft quantifies the prize: *"graph
   extraction [constitutes] roughly 75% of indexing cost"*
   ([GraphRAG methods](https://microsoft.github.io/graphrag/index/methods/)). The two known cost
   wins both move the LLM rather than filter input: **FastGraphRAG** swaps the LLM for spaCy/NLP on
   *everything* ("much cheaper … quite a bit noisier", same page); **LazyGraphRAG** *defers all LLM
   use to query time*, reaching *"data indexing costs … identical to vector RAG and 0.1% of the
   costs of full GraphRAG"*
   ([LazyGraphRAG](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)).
   LazyGraphRAG is the closest existing system to O3's "lazy extraction" idea — and it pays for
   the deferral at **query time** (it still does work, just later and only on retrieved material).
   The cost of *no* gate and *no* deferral is paid as Letta's / mem0's documented **junk
   accumulation** (O3) and as poisoned downstream layers (relations, graph, compiled summaries).

---

## 2. Evidence & detail with citations

All `file:line` references are in the cited archaeology docs; the docs grep the actual clones.

### 2.1 The five systems, by gating mechanism

| System | Gate *before* LLM extraction? | What it actually does pre-LLM | Near-dup / novelty beyond exact? | Cost/quality number present |
|---|---|---|---|---|
| **GraphRAG** | **No value gate.** Standard pipeline extracts every chunk. | Fixed workflow `create_base_text_units → extract_graph(LLM)`; grep `filter\|skip\|salien\|novel\|relevan\|min_\|worth` on `create_base_text_units.py` → nothing. Post-hoc `prune_graph` (degree/freq/edge-weight) runs only in the **Fast** pipeline, **after** NLP extraction, never gates the LLM path. Re-ingest dedup by doc-id (update pipeline). | **not found** | **"graph extraction ≈ 75% of indexing cost"** (`docs/index/methods.md:44`, re-verified vs vendor); Fast = spaCy/TextBlob, "much cheaper … noisier" |
| **LightRAG** | **No value gate.** Extracts every non-duplicate chunk. | Two real **exact content-hash** dedup layers: file pipeline (`compute_text_content_hash`, `pipeline.py:473,501,665` — doc + filename) and SDK insert (`lightrag.py:1410,1432` — doc + chunk). Grep `salien\|novel\|relevan\|worth\|low.?value\|importance` on `pipeline.py`+`operate.py` → nothing. | **exact-bytes only** | none committed (eval scaffolding only) |
| **HippoRAG 2** | **No value gate.** Extracts every new chunk. | **Exact chunk-hash OpenIE cache** (`load_existing_openie`, chunk id = `md5(passage)`, `HippoRAG.py:884-913,238-242`) + `get_missing_string_hash_ids` embedding cache. Only post-LLM filter is structural `filter_invalid_triples` (`llm_utils.py:222` — keep iff 3 elements, "Do not apply any text preprocessing"). | **exact-hash only** | none committed (paper-cited, arXiv 2502.14802) |
| **cognee** | **No salience gate.** Extracts every non-DLT chunk (`extract_graph_from_data.py:166-173`, `asyncio.gather` over all chunks). | (a) file-level `content_hash` skip of unchanged docs (`ingest_data.py:150-178`); (b) deterministic **type**-skip for DLT/tabular row-chunks (`:149-159`, graph built from schema, zero LLM). `importance_weight=0.5` exists on chunks but is **carried metadata, never used to skip** (merge-time use is a `# TODO`). | **exact file-hash + type only** | benchmark file reports **accuracy only** (Graph Completion CoT correctness 0.925, F1 0.841); **no cost/token/latency** figures |
| **mem0** | **No pre-LLM gate; the LLM call is the gate.** One unconditional extraction call per `add(infer=True)` (`main.py:765-771`). | Filtering is *inside* the prompt (drop greetings/filler; "When in doubt, extract", `prompts.py:578,580-582`) + post-LLM exact MD5 memory dedup (`main.py:810-828`). The ADD/UPDATE/DELETE/**NONE** novelty controller (`prompts.py:176-185`) is **dormant — zero call sites** in `main.py`. The `≥0.95` threshold is entity-identity merge, **not** a memory-write gate. | **exact-MD5 only** (post-LLM) | none in source (eval framework exists, no committed figures) |
| **Letta/MemGPT** | **No gate, no ER, no dedup.** `insert_passage` stores text+embedding with no same-vs-different check; archival can hold near-duplicates freely. | — (only tag-list dedup for vector/SQL consistency). | **none** | n/a (text-tier memory, not extraction) |

### 2.2 Three "almost-gates" that are not value gates

These are the most gate-like mechanisms in the corpus; each is worth understanding precisely so
ugm doesn't mistake them for the missing tier:

- **LightRAG merge-side cheap-first summary cascade** (`operate.py:265
  _handle_entity_relation_summary`, `force_llm_summary_on_merge=8`, `constants.py:30`): single
  description → no LLM; `< 8` fragments **and** `< 1200` tokens → deterministic `<SEP>`-join, no
  LLM; else map-reduce LLM. This defers the LLM by **merge depth**, not input value — cost scales
  with how many times a fact is re-asserted, never "don't extract this chunk." This is the one
  reusable **D4 cheap-first** primitive in the corpus, but it sits on the *merge* side, after
  extraction already ran.

- **cognee cascade extraction** (`extract_graph_from_data_v2.py`, `n_rounds=2`) and **GraphRAG /
  LightRAG gleaning** (`max_gleanings=1`): these *add* LLM passes for recall. They are the
  **opposite** of a gate — a cost-*up* knob.

- **HippoRAG NER-conditioned triples** (triple must contain ≥1 NER entity,
  `triple_extraction.py`): a precision lever *within* the paid extraction, not a pre-extraction
  gate.

### 2.3 Where the non-gaters pay — with the numbers that exist

- **Cost scales with corpus *size*, not corpus *value*.** Because extraction is ~75% of indexing
  cost (GraphRAG, verified), and every system runs it on every surviving chunk, a corpus that is
  mostly boilerplate/references/duplication (O3's stated reality at 1M docs) pays near-full price
  for near-zero value. Exact-hash dedup only catches *byte-identical* repeats, so paraphrase and
  sub-document low-value text are unprotected.
- **Quality poisoning, not just cost.** O3's chain — junk in extraction poisons relations → graph
  → every compiled layer — is corroborated by the field: HippoRAG and Letta both lack the
  value/salience gate, and the Letta finding explicitly flags "Mem0-class junk-accumulation
  risk." mem0's own design accepts this trade deliberately (recall-bias maxim, `prompts.py:578`)
  and leans entirely on downstream dedup, which is byte-exact and "trivially defeated by one-word
  paraphrase."
- **The two systems that *did* attack extraction cost moved the LLM, they didn't gate text:**
  - *FastGraphRAG* — swap LLM → NLP on everything: "much cheaper … noisier"
    (no committed multiplier in repo; vendor confirms the qualitative trade).
  - *LazyGraphRAG* — defer all LLM to query time: indexing cost "identical to vector RAG and
    **0.1% of the costs of full GraphRAG**"; global-query "**more than 700× lower query cost**"
    at "comparable answer quality"; strong results at "**4% of the query cost** of GraphRAG global
    search" (LazyGraphRAG blog, verified). **This is the empirical case for O3's lazy-extraction
    half:** the prize is real and large, and the cost reappears — bounded — at retrieval time.

### 2.4 Confidence of the two external numbers

- **75% extraction-of-indexing-cost** — verified verbatim on the GraphRAG methods page; it is a
  Microsoft *estimate*, not a measured benchmark. Treat as order-of-magnitude, not precise.
- **LazyGraphRAG 0.1% indexing / 700× query** — verified verbatim on the Microsoft Research blog;
  vendor self-report on their own benchmark conditions (Z100/Z500), not independently reproduced
  here. Directionally strong; exact magnitudes are vendor-stated.

---

## 3. Confidence & gaps

**Confidence: HIGH** for the central claim (no system implements a value/salience/novelty gate
before extraction; the universal pre-LLM lever is exact-hash idempotency). It is unanimous across
five independently archaeologized repos, each grepped for the relevant keywords with "not found"
recorded, and consistent with both external reviews referenced in the design docs.

**Gaps / could-not-verify:**
- **The "~98% junk" figure in O3** (`objections.md:71`) is *not* substantiated by any repo
  artifact, and my web search for a mem0 LOCOMO junk-percentage returned **no source for it** —
  mem0's published numbers are accuracy/recall (LOCOMO ~91–92), not a junk rate. Treat the 98%
  as an unverified rhetorical figure, not a benchmark. The *direction* (mem0 over-extracts by
  design) is verified in code (`prompts.py:578`); the *magnitude* is not.
- **No in-repo cost/token/latency numbers** in mem0, cognee, LightRAG, or HippoRAG. cognee
  publishes accuracy only. So the cost case for a gate rests on the GraphRAG 75% estimate +
  LazyGraphRAG deferral numbers, both Microsoft self-reported, not on the other four systems.
- **O3's "plausibly 10× cost lever"** is an inference, not a measured result anywhere. The
  closest measured analogue is LazyGraphRAG's deferral (≫10× on indexing), but that is *defer*,
  not *gate by value* — a different mechanism with a different cost-reappearance profile.
- **None of these systems offers a reusable implementation of the value tier itself.** Everything
  ugm would borrow is either an idempotency primitive or a merge-side cascade; the gate is new
  code.

---

## 4. Recommendation for ugm

The field gives ugm a clear, evidence-backed position: **everyone extract-alls; the value gate is
genuinely unbuilt; the prize is large but the gate code is ours to write.** Borrow the
idempotency floor and the deferral idea from prior art; build the value/salience tier the field
lacks. Concretely:

**Borrow (proven, lift directly):**
- **Exact content-hash idempotency as the cascade floor (D4 rung 0; supports D7).** Adopt
  LightRAG's doc + chunk + filename content-hash and HippoRAG's chunk-hash extraction cache. This
  is the cheapest tier of the D4 cheap-first cascade and *is* the D7 rebuildable/idempotent
  guarantee — re-ingesting identical bytes must cost zero LLM. This is the one thing every mature
  system built; ship it. **But it is the floor, not the gate** (it dies to paraphrase).
- **LightRAG's merge-side cheap-first summary cascade** (`force_llm_summary_on_merge=8`,
  deterministic `<SEP>`-join below threshold) as the model for ugm's **relation-merge / evidence
  aggregation** LLM-deferral: don't summarize a fact label until enough evidence accrues. Maps
  cleanly onto E3 (D2 evidence-count) and D8 fact-label generation ("only on material adjudication
  changes").

**Build (the differentiator O3 names — no prior art to copy):**
- **A cheap per-document/per-section salience gate as a new E1→E2 stage (D12 trigger model).**
  Place it on the per-document chain *before* Claimify/coref/ER. Output the three-way routing O3
  specifies — **full extraction / deferred / chunks-only** — using cheap signals (PageIndex
  node type + summary already produced at E0; section role e.g. references/boilerplate; length;
  exact-hash novelty; optionally a small-model salience score). This is a D4 cheap-first cascade
  applied to *whether to extract*, not just *how to resolve*. It is exactly the tier GraphRAG's
  "Standard vs Fast" split *doesn't* have (Fast swaps the model for all text; ugm gates *which*
  text reaches the expensive model).
- **Lazy / deferred extraction on a work queue (O3's second half; D12 deferred triggers).** For
  "deferred" documents, extract claims when their chunks are first *retrieved* (P1) or when a K2
  scope declares interest in their entities. LazyGraphRAG is the empirical proof this works
  (0.1% indexing cost; cost reappears, bounded, at query time). ugm's per-document Cloud Tasks
  chain (D12) already supports staged/deferred triggering — this is a queue + a trigger, not new
  infrastructure. Tie the trigger to P1 retrieval and K-scope interest declarations.

**Guardrails (from the corpus's failures):**
- **Bias the gate toward recall, but gate by *value* not by *phaticness*.** mem0's recall-bias
  maxim ("when in doubt, extract") is the right *default* to avoid silent fact loss — but mem0
  applies it *after* paying the LLM. ugm applies the same recall bias to the *cheap* gate
  decision: route ambiguous sections to "full extraction," not to "skip." Cost is saved on the
  *confidently* low-value (references, boilerplate, exact/near-dup), where the asymmetry is safe.
- **Near-duplicate suppression beyond exact-hash is part of the gate, and none of these systems
  has it.** Add an embedding/near-dup tier above the exact-hash floor (the thing LightRAG/HippoRAG
  explicitly lack) so paraphrased boilerplate is caught — but, per O3's and the registry's
  asymmetry logic, suppress only high-confidence near-dups; route the rest to extraction.
- **D1 / D7 compatibility:** the gate decision (route + reason + gate-version) must be recorded
  in Postgres as plane-E state so it is auditable and re-runnable — a better gate later = a batch
  re-decision over deferred docs, exactly like the resolution-decision re-adjudication pattern
  (entity_registry §4) and embedding migrations (D12). Never let the gate become hidden,
  irreproducible state.
- **O6 dependency (flag).** Every threshold in this gate (salience cutoff, near-dup similarity,
  defer-vs-skip boundary) is untunable without the golden set / junk-rate metric O6 demands.
  The gate and its eval harness must ship together, or the gate is blind.

**Net positioning statement for the design:** *The state of the art is idempotency, not
selectivity. ugm's value gate + lazy extraction is the selectivity tier no inspected system
implements; GraphRAG quantifies the prize (~75% of indexing cost is extraction) and LazyGraphRAG
proves deferral captures most of it (0.1% indexing cost). ugm borrows the exact-hash floor and the
merge-side cascade as proven primitives, and builds the value/salience/near-dup gate — recall-
biased, Postgres-recorded, eval-gated — as the differentiator.*

---

## Sources

- Repo archaeology (cite `file:line` in `_additional_context/` clones):
  `plan/analysis/value_gate_research/repo_findings/{mem0_cognee.md, graphrag_lightrag_hipporag.md}`,
  `plan/analysis/registry_research/repo_findings/{mem0.md, cognee.md, lightrag_graphrag.md, letta_hipporag.md}`.
- Design context: `objections.md` (O3, O6), `decisions.md` (D1, D2, D4, D7, D8, D12),
  `plan/designs/overall_design.md` (planes E/K/P, trigger model), `plan/analysis/entity_registry.md`.
- [GraphRAG — Indexing Methods (75% extraction cost; FastGraphRAG cheaper/noisier)](https://microsoft.github.io/graphrag/index/methods/)
- [LazyGraphRAG: setting a new standard for quality and cost (0.1% indexing cost; 700× lower global-query cost; 4% query cost)](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)
- [Mem0 algorithm LOCOMO results (~91–92; no junk-rate figure found)](https://agentry.press/news/mem0-algorithm-update-hits-91-6-on-locomo-94-8-on-longmemeval/)
