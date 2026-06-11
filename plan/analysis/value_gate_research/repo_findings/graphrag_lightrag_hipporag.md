# Value-gate archaeology: GraphRAG · LightRAG · HippoRAG

**Question (O3):** does any of these GATE/FILTER *which text gets extracted* before spending LLM
cost — a value / salience / novelty / dedup / relevance filter? Or do they extract everything?

**Headline answer:** None of the three has a *value / salience / novelty / relevance* gate. All
three extract **everything that survives chunking**. The *only* pre-extraction cost lever any of
them implements is **exact content-hash dedup** (idempotent re-ingest): identical doc/chunk
bytes are skipped, but a near-duplicate, a low-value paragraph, or a references section is
extracted with full enthusiasm. This is precisely the gap O3 names ("L2 processes a paper's
references section with the same enthusiasm as its core findings"). Every claim below is cited
from source under `_additional_context/`. "not found" = grepped and absent in this checkout.

Reuses prior reads in `registry_research/repo_findings/lightrag_graphrag.md` and
`letta_hipporag.md` (ER/identity layer); this doc adds the *pre-extraction gating* axis only.

---

## 1. GraphRAG (Microsoft) — extracts everything; cost lever is model-swap, not text-gating

**Pipeline order leaves no room for a gate.** Default (`Standard`) pipeline is a fixed workflow
list (`packages/graphrag/graphrag/index/workflows/factory.py:52-62`):
`create_base_text_units` → `create_final_documents` → **`extract_graph`** (LLM) →
`finalize_graph` → `extract_covariates` → … . Chunking feeds the LLM extractor directly. There
is **no filter/skip/salience step between chunking and extraction**:
- `create_base_text_units.py` — grep for `filter|skip|salien|novel|relevan|drop|min_|worth`
  returns **nothing**. Every chunk is emitted.
- `extract_graph` runs the LLM on every text unit; gleaning loop (`max_gleanings=1`,
  `config/defaults.py:137`) only *adds* passes, never skips low-value chunks.
- `extract_covariates` (claims) runs on everything too, but is **`enabled: bool = False`** by
  default (`config/defaults.py:132`).

**The only filter in the repo is post-extraction graph pruning, and it's not in the LLM path.**
`index/operations/prune_graph.py:14` `prune_graph(...)` drops low-degree / low-frequency nodes
and bottom-`min_edge_weight_pct=40`% edges — but it runs over the *already-built* entity/relation
DataFrames (`prune_graph.py:80-95`), i.e. **after** all LLM cost is spent. And it is only wired
into the **`Fast`** pipeline (`factory.py:63-72`: `extract_graph_nlp` → `prune_graph`), never the
`Standard` (LLM) one. `Fast` mode's "extraction" is **spaCy/TextBlob noun-phrase + co-occurrence**
(`index/operations/build_noun_graph/build_noun_graph.py:63` "NLP extraction is CPU-bound
(spaCy/TextBlob)") — i.e. GraphRAG's cost lever is *swap the LLM out entirely*, not *gate which
text the LLM sees*.

**Documented cost numbers (the one quotable place):** `docs/index/methods.md:44` — *"We estimate
graph extraction to constitute roughly 75% of indexing cost. FastGraphRAG is therefore much
cheaper … the tradeoff is that the extracted graph is … quite a bit noisier."* So GraphRAG
confirms extraction dominates cost and offers exactly two settings: pay the LLM on everything
(Standard), or run NLP on everything + prune after (Fast). No middle "extract only the valuable
chunks" option. **No near-dup/novelty check before extraction. not found.**

- **Spends LLM on:** every chunk (entity+relation extraction, gleaning, community reports,
  optional claims). **Saves by:** Fast mode (NLP instead of LLM) + post-hoc graph prune; cheap
  deterministic delimited-tuple parse instead of function-calling. Re-ingest dedup: handled in
  the `update` pipeline by doc-id, not a content novelty check.

---

## 2. LightRAG (HKUDS) — extracts everything; real **exact content-hash dedup**, no novelty/salience

**Two genuine pre-extraction dedup layers, both exact-hash:**

1. **Batch + persisted dedup in the file pipeline** (`pipeline.py:231 apipeline_enqueue_documents`,
   docstring step 1 = *"generate MD5 hash IDs and remove duplicate contents"*, step 3 = *"Filter
   out already processed documents"*). Implementation (`pipeline.py:461-518` `_add_content`):
   - `content_hash = compute_text_content_hash(content)` (`pipeline.py:473`; impl
     `utils_pipeline.py:492`).
   - In-batch: if `content_hash in content_hash_to_doc_id` → recorded as
     `duplicate_kind="content_hash"` and **dropped** (`pipeline.py:501-513`). Same-path files
     dropped as `duplicate_kind="filename"` (`:487-499`).
   - Cross-batch / persisted: `unique_new_doc_ids = await self.doc_status.filter_keys(...)`
     (`pipeline.py:630`) + `get_existing_doc_by_content_hash(self.doc_status, content_hash)`
     (`pipeline.py:665`) — a doc whose content hash already exists in `doc_status` never reaches
     extraction.
2. **SDK direct-insert dedup** (`lightrag.py:1404-1438`, `ainsert_custom_chunks`):
   `doc_key = compute_mdhash_id(full_text, prefix="doc-")` → `full_docs.filter_keys({doc_key})`;
   if empty → *"This document is already in the storage."* return (no extraction). Then per
   chunk `chunk_key = compute_mdhash_id(chunk_text, prefix="chunk-")` →
   `text_chunks.filter_keys(...)`; if all chunks known → *"All chunks are already in the
   storage."* return. Only the surviving chunks go to `_process_extract_entities`
   (`lightrag.py:1442`).

**That is the entire gate. It is exact-bytes only.** Grep across `pipeline.py` + `operate.py`
for `salien|novel|relevan|worth|low.?value|importance` → **nothing**. No near-duplicate /
embedding-novelty / salience / "is this chunk worth extracting" check anywhere. A paraphrase, a
boilerplate footer, or a low-value paragraph that differs by one byte from a stored chunk passes
straight into entity/relation extraction. Entity/relation extraction itself (`operate.py`) runs
on every surviving chunk with no value filter; gleaning (`DEFAULT_MAX_GLEANING=1`,
`constants.py:17`) only adds passes (token-guarded at `operate.py:3541`).

The closest thing to a "value" knob is the **cheap-first *summary* cascade** on the merge side
(`operate.py:265 _handle_entity_relation_summary`; `force_llm_summary_on_merge=8`): single
description → no LLM; <8 fragments and <1200 tokens → just `<SEP>`-join, no LLM; else map-reduce
LLM. That defers LLM by *merge depth*, not by *input value* — it never decides "don't extract
this chunk." (Prior `lightrag_graphrag.md` §7 covers this.)

- **Spends LLM on:** every non-duplicate chunk (extraction + gleaning), and merge-summary only
  past the 8-fragment threshold. **Saves by:** exact doc/chunk content-hash dedup (idempotent
  re-ingest), deterministic `<SEP>`-join below the merge threshold, optional reranker
  `min_rerank_score` filter (`lightrag.py:496`) — but that's **query-time**, not ingest.
  **Near-dup/novelty before extraction: not found.**

---

## 3. HippoRAG 2 (OSU-NLP) — extracts everything; **exact chunk-hash OpenIE cache**, no value gate

**One real pre-extraction cost saver: OpenIE result cache keyed by exact chunk hash.**
`index()` (`HippoRAG.py:218`) calls `load_existing_openie(chunk_to_rows.keys())`
(`HippoRAG.py:238`) which returns `chunk_keys_to_process` = the keys whose OpenIE results are
**not already on disk** (`load_existing_openie` `HippoRAG.py:884-913`; chunk id =
`compute_mdhash_id(passage, 'chunk-')`, line 913). Only those run the LLM:
`if len(chunk_keys_to_process) > 0: self.openie.batch_openie(new_openie_rows)`
(`HippoRAG.py:241-242`). The embedding store reinforces this — `insert_strings` /
`get_missing_string_hash_ids` (`embedding_store.py:44-80`) compute `compute_mdhash_id(text)` and
only encode `missing_ids` (`"Inserting N new records, M records already exist"`,
`embedding_store.py:80`).

**This is exact-string identity only.** Chunk id = md5 of the passage string (no normalization
beyond what the embedder sees). So a re-run of the *same* corpus costs ~0 extra LLM; but any
*new* chunk — including a near-duplicate or a low-value one — gets the **full two-call OpenIE**
(NER then triples, `information_extraction/openie_openai.py:130`). There is **no salience /
novelty / relevance / value filter** before OpenIE: grep over `information_extraction/` and
`HippoRAG.py` for `salien|novel|relevan|worth|low.?value|filter.*before` → nothing relevant.

The only "filter" named in the extraction path is **`filter_invalid_triples`**
(`utils/llm_utils.py:222`) — and it is *post*-LLM and purely structural (keep iff exactly 3
elements + dedupe; docstring: *"Do not apply any text preprocessing techniques or rules"*). It
removes malformed triples, not low-value input. Synonymy edges (0.8 cosine KNN,
`config_utils.py:160`) are a *post-extraction* KG-wiring step, never a pre-extraction gate.
Lifecycle: `delete()` reference-counts (drop a triple/entity only if no surviving chunk produces
it, `HippoRAG.py:316-345`) — a retraction rule, not an ingest gate.

- **Spends LLM on:** every new (uncached) chunk — NER call + triple call (`gpt-4o-mini`,
  `temperature=0`, `config_utils.py:18,50`), single-pass (no gleaning); plus 1 query-time fact-
  filter call. **Saves by:** exact-chunk-hash OpenIE/embedding cache (idempotent re-index),
  `temperature=0`, single-pass extraction, incremental synonymy (new nodes vs all,
  `HippoRAG.py:847` "to reduce cost for incremental graph updates"). **Cost/quality numbers:**
  none in source; README cites arXiv 2502.14802 only (eval harness `evaluation/retrieval_eval.py`
  recall@k, no committed figures). **Near-dup/novelty before extraction: not found.**

---

## 4. Cross-cutting: where cost is spent vs saved; novelty checks; numbers

| System | Gate *before* LLM extraction? | What it actually is | Near-dup / novelty? | Cost number in repo |
|---|---|---|---|---|
| **GraphRAG** | **No value gate.** Extracts every chunk (Standard). | Post-hoc `prune_graph` (degree/freq/edge-weight) — Fast pipeline only, *after* NLP extraction, never gates the LLM path. Re-ingest dedup by doc-id (update pipeline). | not found | **"graph extraction ≈ 75% of indexing cost"** (`docs/index/methods.md:44`); Fast = spaCy/TextBlob, "much cheaper … noisier" |
| **LightRAG** | **No value gate.** Extracts every non-duplicate chunk. | **Exact content-hash dedup** (`compute_text_content_hash`, `pipeline.py:473,501,665`; `lightrag.py:1410,1432`) + filename dedup. Merge-side cheap-first summary cascade (`force_llm_summary_on_merge=8`). | **Exact-bytes only** — no embedding/near-dup/salience | none committed (eval scaffolding only) |
| **HippoRAG** | **No value gate.** Extracts every new chunk. | **Exact chunk-hash OpenIE/embedding cache** (`load_existing_openie` + `get_missing_string_hash_ids`). Post-LLM structural `filter_invalid_triples`. | **Exact-hash only** | none committed (paper-cited) |

**Net for ugm / O3:** all three validate the objection by counter-example. The state of the art
here is *idempotency* (don't re-extract identical bytes), **not** *selectivity* (don't extract
low-value text). The novelty/salience gate O3 proposes — a cheap per-doc/section decision of
"full extraction / deferred / chunks-only", plus near-duplicate suppression beyond exact-hash —
**exists in none of them** and is exactly the differentiator. GraphRAG even quantifies the prize:
extraction is ~75% of indexing cost, so a gate that drops a meaningful fraction of low-value
chunks is a near-linear LLM-cost lever (consistent with O3's "plausibly 10×"). The only reusable
primitives to lift: (a) LightRAG's content-hash + filename dedup as the *exact-dup floor* of the
cascade (cheap, already-built), (b) HippoRAG's chunk-hash extraction cache as the rebuild/idempotency
guarantee (supports D7 rebuildable), (c) GraphRAG's Fast/Standard split as the model-tier idea
(D4 cheap-first) — but the *value/salience/novelty tier itself is unbuilt prior art; ugm must add it.*

Aligns with: **D4** (cheap-first cascade — these stop at the "exact-dup" rung, never reach a
value rung), **D7** (their hash caches are the rebuildable/idempotent property ugm wants),
**D12** (triggers — none of them stages extraction; it's eager on ingest, the opposite of O3's
lazy/deferred-on-retrieval proposal).
