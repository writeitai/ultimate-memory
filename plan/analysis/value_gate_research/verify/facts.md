# Fact-check: load-bearing numbers & external claims in value_gate_research/questions/*.md

Adversarial verification pass. Default skeptical; "confirmed" only with a traceable source
(live URL fetched, or repo `file:line` read in this pass). Date: 2026-06-11.

Method: re-fetched the mem0 audit issue and every external paper/vendor page cited; re-grepped
the actual repo clones under `_additional_context/` for every `file:line` code claim.

---

## Verdict table

| # | Claim | Where | Verdict | Corrected / source |
|---|---|---|---|---|
| 1 | "98% junk" mem0 audit exists; issue #4573 titled "…97.8% were junk", 10,134 entries, 32 days | V1 §1,§2.1 | **confirmed** | github.com/mem0ai/mem0/issues/4573 — title & 97.8% & 10,134 verbatim. Issue exists (not 404). |
| 2 | Phase 0 removed 2,468 (exact dups + 668 copies of one hallucination); Phase 2 manual judged 6,070 junk; 38 kept as-is; 224 total usable | V1 §2.1 | **confirmed** | Issue #4573 verbatim: "removed 2,468 entries", "668 copies", "38 entries … clean enough to keep as-is", "224 clean memories". |
| 3 | Phase 1 = **2,943 near-duplicates (cosine > 0.95)** = 37.6% of remainder | V1 §1 ln74, §2.1, §2.5 | **likely-wrong (fabricated threshold)** | 2,943 and 37.6% are **confirmed** verbatim. But the issue does **NOT state a 0.95 cosine threshold** (re-fetched: "does not specify the cosine similarity threshold value"). The ">0.95" is invented; drop it or mark inferred. |
| 4 | Junk composition **raw counts**: boot-file 3,200 (52.7%), heartbeat 700, arch dumps 500, transient 450, hallucinated profiles 315, identity 200 | V1 §2.1, §2.5 | **unverified (counts) / confirmed (52.7%)** | Source gives **percentages** (boot 52.7%, heartbeat 11.5%, arch 8.2%, transient 7.4%, profiles 5.2%), not raw counts. V1's counts are back-computed and internally consistent (52.7%×~6,070≈3,200) but are **not** the verbatim figures and the smaller counts (700/500/450/315/200) don't all match the published percentages. Cite the percentages. |
| 5 | Swapping gemma2:2b → Claude Sonnet 4.6 dropped junk only to **89.6%**; "extraction prompt is the bottleneck, not the model" | V1 §1,§2.1 | **confirmed** | Issue #4573: "junk rate barely moved", final batch "89.6% junk rate with Claude Sonnet 4.6". (Model name "Sonnet 4.6" is the author's; reproduced as-is.) |
| 6 | "Less is More: Denoising KGs for RAG" (arXiv 2510.14271) is real; remove ~40% entities + 30–60% relations while maintaining/improving; up to 70% entity reduction safe | V1 §1,§2.2 | **confirmed** | arXiv 2510.14271 (framework "Deg-Rag", subm. Oct 16 2025). Verbatim: "while removing 40% of the entities and relations … consistently improves"; "comparable … up to 70%". (V1's "30–60% of relations" is a looser paraphrase of the 40%/up-to-70% spread — acceptable, not verbatim.) |
| 7 | LightRAG denoising win-rate lift: Agri 42.4→57.6, **CS 41.6→58.4**, Legal 42.4→51.6, Mix 46.0→54.0 (+8 to +17pp) | V1 §1,§2.2 | **confirmed** | arXiv 2510.14271v1 Table 1 "Overall": all four pairs match exactly. |
| 8 | "graph extraction ≈ 75% of indexing cost"; FastGraphRAG cheaper but noisier | V1, V2, V4, V6 | **confirmed** | Repo `graphrag/docs/index/methods.md:44` verbatim AND microsoft.github.io/graphrag/index/methods/. Microsoft *estimate*, not a benchmark — treat as order-of-magnitude (V4 §2.4 correctly flags this). |
| 9 | LazyGraphRAG: indexing cost "0.1% of full GraphRAG"; ">700× lower query cost"; "4% of query cost"; defers all LLM to query time | V3, V4, V6 | **confirmed** | MS Research blog (lazygraphrag…) all three phrases verbatim. Vendor self-report on their own Z100/Z500 conditions, not independently reproduced — V4 §2.4 & V3 §3 correctly caveat. |
| 10 | Ultra-FineWeb: filtering 15T tokens ≈ 6,000 H100-GPU-h (LLM classifier) vs ~1,000 CPU-h on 80 CPUs (fastText) = ~6× + GPU-free | V2 §1,§2.2 | **confirmed** | arXiv 2505.05427v1 Table 2 verbatim: "6,000 H100 GPU hours" vs "80 CPUs in 1,000 hours". 6× speedup. |
| 11 | Zero-RAG (arXiv 2511.00505): prune 30% Wikipedia <2pt drop; TriviaQA 70% removal = 0.62pt drop | V5 §1,§2.2 | **unverified (not re-fetched this pass)** | V5 quotes verbatim and self-flags the secondary "high→low density" sentence as unconfirmed. arXiv id plausible; treat headline numbers as quoted-but-not-independently-reverified here. No contradiction found. |
| 12 | mem0 LOCOMO ~91–92 accuracy; mem0's public numbers are accuracy/recall, not a junk rate | V4 §2 (ln224), V6 §3 | **plausible/unverified** | Not re-fetched this pass. Consistent with mem0's known LOCOMO marketing. Note this is used to argue the 98% has "no source" — see contradiction below. |

---

## Repo `file:line` code claims (re-grepped in `_additional_context/` this pass)

| Claim | Verdict | Evidence |
|---|---|---|
| mem0 "When in doubt, extract…" at `prompts.py:578` | **confirmed** | `mem0/mem0/configs/prompts.py:578` exact text. |
| mem0 `ADDITIVE_EXTRACTION_PROMPT` active at `prompts.py:468` | **confirmed** | `prompts.py:468`. |
| mem0 unconditional LLM call per `add(infer=True)`; `_add_to_vector_store` at `main.py:688`, "V3 PHASED BATCH" at 725, `generate_response` at 765 | **confirmed** | `main.py:688,725,765` all match. |
| mem0 `≥0.95` is entity-identity merge, not a memory-write gate (lines 452, 944, 1933, 2396) | **confirmed** | `main.py:452,944,1933,2396` all `score >= 0.95`. |
| LightRAG `compute_text_content_hash` at `pipeline.py:473` | **confirmed** | `pipeline.py:473` (also imported :81, reused :2925). |
| LightRAG `force_llm_summary_on_merge=8` (`constants.py:30`) | **confirmed** | `constants.py:30` `DEFAULT_FORCE_LLM_SUMMARY_ON_MERGE = 8`; field `lightrag.py:265`. |
| LightRAG `DEFAULT_MAX_GLEANING=1` (`constants.py:17`) | **confirmed** | `constants.py:17`. |
| HippoRAG `load_existing_openie` at `HippoRAG.py:884`, called :238 | **confirmed** | `HippoRAG.py:884` (def), :206/:238 (calls). |
| cognee per-chunk LLM `asyncio.gather`/`extract_content_graph` at `extract_graph_from_data.py:166-173` | **confirmed** | `extract_graph_from_data.py:166` gather, :168 `extract_content_graph`, :156 `non_dlt_chunks`. |
| cognee `importance_weight = 0.5` carried-but-unused at `DocumentChunk.py:36` | **confirmed** | `DocumentChunk.py:36` `importance_weight: Optional[float] = 0.5`. |
| "None of mem0/cognee/GraphRAG/LightRAG/HippoRAG has a value/salience/novelty gate; only exact-hash dedup" | **confirmed (consistent)** | Grep-absence pattern reproduced; matches all 5 repo_findings. Central claim is sound. |

---

## Cross-document contradiction (the one real problem to fix)

**The "98% junk" figure is treated three incompatible ways across the questions set:**

- **V1** (§1): "the '98% junk' claim is **REAL and traceable**" → mem0 issue #4573, 97.8%. ✅ correct.
- **V4** (§3, ln135-139): "The '~98% junk' figure in O3 is **not** substantiated by any repo
  artifact, and my web search … returned **no source for it**." ❌ stale/wrong.
- **V6** (§3, ln323-329; §4 ln397): "the '~98% junk' figure in O3 is **NOT** independently
  verified … Treat the 98% as an unverified anecdote … **Drop the unverified '98% junk' anecdote**." ❌ stale/wrong on existence.

**Resolution (verified this pass):** Issue #4573 **exists** and **does** report 97.8% on 10,134
entries. So **V1 is correct; V4 and V6 are out of date** — they failed to locate the source that
V1 found. The *substance* V4/V6 push (n=1, pathological, not a benchmark, don't use as a planning
multiplier) is **right and important** — but their stated reason ("no source exists") is **false**.
Recommended fix: align V4/V6 to V1's framing — the source is real (mem0 #4573, 97.8%), but it is a
single-deployment anecdote (52.7% of junk = an agent re-ingesting its own boot file), not a
general junk rate; keep the "don't cite as a population statistic / don't use as a 10× input"
caution, drop the "no source" claim.

---

## Numbers that are explicitly MODELED, not measured (correctly self-flagged — no action)

- V6 §2.6 filter-rate bands (f_full/f_def/f_chunk, ~36–65% cost) — modeled, self-flagged.
- "Plausibly 10×" cost lever (O3) — **unverified anywhere**; V1/V4/V6 all flag it as an
  inference, not a measurement. The verified ceiling is LazyGraphRAG's 0.1% (full deferral), a
  *different mechanism* than salience-skip. Correctly caveated.
- Hallucination 3–27% band (V1 §2.3) — search-snippet level only (primary PDF 2508.14391 body
  didn't extract); self-flagged.
- Common Crawl 5–10% survival (V1 §2.4) — cited to survey, not re-fetched this pass; plausible,
  standard pretraining-lit figure.

---

## Bottom line

The **central, load-bearing claims are confirmed**: the mem0 #4573 audit is real (97.8% / 10,134),
the denoising-KG paper's numbers (40%/70%, four LightRAG win-rates), GraphRAG's 75%, LazyGraphRAG's
0.1%/700×/4%, and Ultra-FineWeb's 6× all check out verbatim, and every spot-checked repo `file:line`
is accurate. Two defects: (a) V1's "cosine > 0.95" Phase-1 threshold is **fabricated** (not in the
source) and its junk-composition **raw counts** are back-computed, not verbatim (cite the
percentages); (b) V4 and V6 wrongly claim the 98% figure has **no source** — it does (V1 found it);
their skepticism about *using* the number is valid, their claim about its *existence* is not.
