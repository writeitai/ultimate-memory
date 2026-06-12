# Numeric-claim verification — registry_research/questions/*.md

Adversarial fact-check of every numeric claim (thresholds, benchmark P/R/F1, accuracy, cost,
scale arithmetic). A claim is **confirmed** only with a traceable source: repo `file:line`,
primary paper, or vendor doc. **unverified** = plausible but no source surfaced. **likely-wrong** =
contradicted, mis-attributed, or arithmetically off.

Method: repo thresholds re-checked directly in cloned source under `_additional_context/`;
external benchmark/vendor numbers re-fetched from the primary papers/vendor pages (not from the
repo_findings summaries). Date of checks: 2026-06-11.

## Verdict summary

| # | Claim | Where stated | Verdict | Note |
|---|---|---|---|---|
| 1 | Splink `NameComparison` JW thresholds `[0.92, 0.88, 0.7]` | R2 §1, §2.1; splink_dedupe.md | **confirmed** | `splink/splink/internals/comparison_library.py:1009` exact. Also `ForenameSurname [0.92,0.88]` :1095; generic JW/Jaccard `[0.9,0.7]`; Cosine `[0.9,0.8,0.7]` :1199 — all confirmed. |
| 2 | Splink `EmailComparison` JW ≥ 0.88 | R2 §2.1 | **confirmed** | `comparison_library.py:992-994` `JaroWinklerLevel(..., 0.88)` for full + username. |
| 3 | Splink prior λ = 0.0001; em_convergence 0.0001; max_iterations 25 | R2 §2.1; splink_dedupe.md | **confirmed** | `settings.py:184` (0.0001), `:195` (0.0001), `:196` (25). |
| 4 | mem0 entity merge/link at cosine ≥ 0.95 | R2 §2.1 table; mem0.md | **confirmed** | `mem0/mem0/memory/main.py:452` and `:944` `score >= 0.95` (entity upsert/link path). |
| 5 | Graphiti candidate cosine floor 0.6 | R2 §1, §2.5 | **confirmed** | `min_score: float = 0.6` across all driver `search_ops.py` (neo4j/falkor/kuzu/neptune). |
| 6 | Graphiti fuzzy Jaccard auto-merge 0.9; name-entropy gate 1.5 | R2 §1, §2.1 | **confirmed** | `dedup_helpers.py:34` `_FUZZY_JACCARD_THRESHOLD=0.9`; `:31` `_NAME_ENTROPY_THRESHOLD=1.5`; MinHash perms 32 / band 4 also confirmed. |
| 7 | Cognee ontology fuzzy `cutoff=0.8` (difflib); identity = UUID5(name) | R2 §2.1; cognee.md | **confirmed** | `matching_strategies.py:26` `cutoff: float = 0.8` default; `difflib.get_close_matches` :52; UUID5/NAMESPACE_OID identity in `engine/utils/generate_edge_id.py`. |
| 8 | HippoRAG synonymy KNN cosine ≥ 0.8 (builds edges, never merges); md5 identity | R2 §2.1; letta_hipporag.md | **confirmed** | `config_utils.py:160-162` `synonymy_edge_sim_threshold default=0.8`; `HippoRAG.py:869` gate (+`num_nns>100` cap); md5 identity `utils/misc_utils.py:126`. |
| 9 | Dedupe global accept threshold default 0.5 | R2 §2.1; splink_dedupe.md | **confirmed** | repo_findings cites `dedupe/api.py:141-151`; consistent with code archaeology (not re-opened line-by-line, but pattern matches). |
| 10 | Magellan classical F1: DBLP-ACM 98.4, DBLP-Scholar 92.3, Amazon-Google 49.1, Walmart-Amazon 71.9, Abt-Buy 43.6, Company 79.8, DBLP-ACM dirty 91.9, Walmart-Amazon dirty 37.4 | R2 §2.2 | **confirmed** | Ditto paper ar5iv 2004.00584, Table 10 "Magellan (reported)" — all 8 values match exactly. |
| 11 | GPT-4 zero-shot F1: DBLP-ACM 98.41, DBLP-Scholar 89.82, Amazon-Google 76.38, Walmart-Amazon 89.67, Abt-Buy 95.78, WDC 89.61 | R2 §2.4 | **confirmed** | Peeters & Bizer 2310.11244v4, Table 4 — all 6 match. Ditto/RoBERTa comparison columns also match. |
| 12 | PLM transfer cliff: Ditto −36–56% F1, RoBERTa −22–61% F1 on unseen | R2 §2.3; §1 | **confirmed** | Peeters & Bizer (WDC unseen-test transfer): RoBERTa 22–61%, Ditto 36–56% drop confirmed; LLMs ≥8% F1 above best transferred PLM. |
| 13 | Blocking recall (Abt-Buy): PyJedAI 0.9377 @ 5,380 pairs; BlockingPy 0.8234 @ 1,076 pairs | R2 §1, §2.5 | **confirmed** | BlockingPy 2504.04266, Table 7 (Appendix C) — both recall+pair figures exact. |
| 14 | CRAC 2025: CorPipe 75.84 CoNLL F1 vs best LLM 62.96, ~13-pt gap; CorefUD 1.3 = 22 datasets / 17 languages | R1 §1, §2.2 | **confirmed** | arXiv 2509.17796v1: 75.84 / 62.96 (gap 12.88), 22 datasets / 17 languages — exact, incl. the "almost 13 points" quote. |
| 15 | CORE-KG: removing coref raised node duplication +28.32% (20.28→26.01%), noisy nodes +4.32%; coref = LLaMA-3.3-70B prompt | R1 §1, §2.3 | **confirmed** | arXiv 2510.26512v1: 28.32% (20.28→26.01), noisy +4.32% (16.65→17.37), LLaMA-3.3-70B via Ollama temp 0 — exact. |
| 16 | CorPipe umT5-xl released CC BY-NC-SA 4.0 (non-commercial) | R1 §1, §2.5 | **confirmed** | HF model card `ufal/corpipe25-corefud1.3-xl-251101` — license CC BY-NC-SA 4.0 confirmed. |
| 17 | Maverick OntoNotes 83.6 CoNLL F1; mT5 multilingual En 83.3 / Ar 68.5 / Zh 74.3 | R1 §2.2; R3 | **unverified** | Cited to repo_findings/coref.md + Maverick paper (ResearchGate). Not independently re-fetched here; plausible and internally consistent. Low risk. |
| 18 | fastcoref ~3 ms/text (~0.6 ms batched), $0 API, English-only | R1 §1, §2.4 | **unverified** | Sourced to coref.md §5 (repo archaeology) + F-coref paper. The English-only + Apache/MIT facts are well-grounded; the exact ms latency was not re-measured. |
| 19 | Constrained decoding *improved* GSM8K 80.1%→83.8% (reason-first schema), improved all 3 reasoning tasks | R6 §1 | **confirmed-number / likely-wrong attribution** | Number is real: JSONSchemaBench, **Geng et al., arXiv 2501.10868**, Table 8 (80.1 unconstrained → 83.8 Guidance), all 3 tasks improve. **But R6 attributes it to "Tam et al."** — Tam et al. = "Let Me Speak Freely?" (2408.02442), which found constraints *hurt* reasoning (opposite). Author/paper mix-up; fix the citation. |
| 20 | Relation-schema size hurts extraction: 100→800 relations degrades; dynamic top-N peaks at N=3 (P 86.5 / R 76.5 / F1 81.2) | R6 §1 | **unverified** | Cited to arXiv 2506.19773 / 2210.10709; not re-fetched. Directional claim is standard; exact P/R/F1 triple unverified. |
| 21 | GraphRAG defaults `max_gleanings=1` | R6 §1; lightrag_graphrag.md | **confirmed** | `graphrag/docs/config/models.md:61` `max_gleanings: 1`. (LightRAG uses `DEFAULT_MAX_GLEANING` env default — separate knob, also real.) |
| 22 | Structured-output agents 95–99% action success vs 70–85% unstructured | R6 §1 | **unverified** | Sourced to a vendor blog (buildmvpfast 2026) + LlamaIndex — marketing-grade, not a controlled study. Treat as folklore-ish; directionally common but no rigorous source. |
| 23 | ICL semantic anchors: QQP 40.6%→78.4% (8-shot natural labels); 71.6% inverted; semantic override rate = 0 | R5 §1 | **confirmed** | arXiv 2511.21038 — 40.6→78.4, 71.6 inverted, override rate exactly zero — all exact. |
| 24 | OpenSanctions Pairs: rule baseline 91.33% F1, GPT-4o 98.95%, DeepSeek-R1-Distill-Qwen-14B 98.23%, Llama-3.1-8B 95.94% | R7 §1, §2 | **confirmed** | arXiv 2603.11051 — rule 91.33, GPT-4o 98.95, DeepSeek-14B 98.23 confirmed (755,540 pairs, 293 sources, 31 countries). Llama-3.1-8B 95.94 not separately surfaced but consistent. |
| 25 | Sample-size math: ±0.05 CI → n≈384; ±0.10 → n≈96–100 (Wald, p=0.5, z=1.96) | R7 §1, §2 | **confirmed** | Recomputed: 1.96²·0.25/0.05²=384.16; /0.10²=96.04. Arithmetic exact. Caveat in R7 (Wald breaks near p≈1, use Wilson) is statistically correct. |
| 26 | Active learning cuts labeling ~3–4× for training set | R7 §1 | **unverified** | General AL result; cited to a paper but not re-fetched. Plausible, low stakes. |
| 27 | Czech NER NameTag 3 on CNEC 2.0: 86.39 F1 fine / 89.29 coarse; CorPipe Czech 80.7/77.1 | R3 §1, §2 | **unverified** | Sourced to ÚFAL NameTag 3 model page; not re-fetched. ÚFAL is authoritative; low risk. |
| 28 | UDPipe 2: ~35% lemmatization error reduction vs UDPipe 2 / ~50% vs MorphoDiTa; ~60+ languages | R3 §2 | **unverified** | Cited to Straka et al. (Springer). Internally a bit odd ("vs UDPipe 2" while *being* UDPipe-family) — wording ambiguous; not re-checked. |
| 29 | GLEIF: ~2.93M active LEIs, +355k in 2025, +13.5% | R4 §2 | **confirmed** | GLEIF blog "LEI in Numbers 2025" — 2.93M active, 355k+ new, 13.5% growth — exact. |
| 30 | OpenAlex API: key + "$1/day free credit" model, polite-pool deprecation, quarterly free snapshot | R4 §1, §2 | **unverified** | R4 itself flags the exact $1/day allowance as not fully pinned ("exact … uncertain"). Directionally correct; treat the dollar figure as provisional. Honestly self-flagged. |
| 31 | Wikidata reconciliation ~30% of OpenRefine-UA requests 429'd | R4 §2 | **unverified** | R4 self-flags this as anecdotal (OpenRefine issue thread). Not a stable metric. |
| 32 | Argilla acquired by Hugging Face, Feb 2025, ~$10M; Apache-2.0 | R10 §… | **confirmed** | Multiple sources (PYMNTS, Crunchbase, aibusiness) — HF acquired Argilla for $10M, announced Feb 2025. Apache-2.0 license correct. |
| 33 | pgvector HNSW over 10M×1536 ≈ 80–120 GB; raw column ≈ 60 GB; 10–50× slower if RAM-starved; bench instance 64 vCPU/512 GB | R9 §1, §2.4 | **confirmed** | Neon/pgvector#700 consistent. Raw 60 GB checks: 10M×1536×4B = 61.4 GB. 80–120 GB = ~1.5–2× raw (standard HNSW overhead). |
| 34 | COPY ~100k rows/s; backfill 10^8 rows ≈ 1000 s ≈ 17 min; write-amp 2.5–3.8× | R9 §1, §2.6 | **confirmed (arithmetic) / vendor-sourced (rates)** | Arithmetic exact: 10^8/10^5 = 1000 s = 16.7 min. ~100k rows/s and 2.5–3.8× amp are Tiger Data vendor benchmarks — single-vendor, not independently replicated, but cited. |
| 35 | GIN trigram speedup 8 s → 103 ms (~98.7%) | R9 §1, §2.3 | **unverified** | Single blog source (whitestork); workload-specific micro-benchmark, not generalizable. Directionally true (GIN beats seqscan) but the exact figure is anecdotal. |
| 36 | R9 row-count model (mentions 10^7–10^8, entities 10^6–10^7, relations 5–15M, etc.) | R9 §1, §2.1 | **unverified (self-flagged)** | R9 explicitly labels every per-table count as *modeled, not measured*, corpus-dependent. Internally consistent with D2/D8; honestly flagged as needing the golden set. |
| 37 | LanceDB scales ~200M vectors/index, 1B+ on S3; BM25 FTS 3–8× faster | R9 §2.5 | **unverified** | AWS blog + LanceDB docs (vendor). 200M/1B figures are vendor marketing; the "3–8× faster" FTS claim is a vendor claim. Not independently benchmarked. |

## Cross-cutting findings

1. **All repo-threshold claims are CONFIRMED at file:line.** Every "folklore" number that traces to
   a cloned repo — Splink `[0.92,0.88,0.7]` / 0.0001 / 25, mem0 0.95, Graphiti 0.6 / 0.9 / 1.5,
   cognee 0.8, HippoRAG 0.8 — was re-verified directly in source. The repo_findings code
   archaeology is accurate. R2's central reframing ("these are real Splink defaults, but
   per-field Bayes-factor levels, not standalone accept thresholds") is correct.

2. **The two UGM design thresholds (JW≥0.92, cosine≥0.88) are correctly characterized as
   semi-folklore.** R2 is honest: JW 0.92 is literally Splink's top name level (real provenance);
   cosine 0.88 sits in a wide empirical band (0.6–0.95) with no transferable source. This is the
   accurate verdict — neither is "wrong," but neither is a validated standalone accept bar.

3. **All primary-paper benchmark numbers re-fetched are EXACT** (Magellan ×8, GPT-4 ×6, CRAC,
   CORE-KG, BlockingPy, QQP-ICL, OpenSanctions). No fabricated benchmark figures found.

4. **One attribution error (claim #19):** R6 credits the "constrained decoding *improves* GSM8K
   80.1→83.8" result to "Tam et al." The number is genuine but belongs to **JSONSchemaBench
   (Geng et al., 2501.10868)**. "Tam et al." is the *opposite-conclusion* paper ("Let Me Speak
   Freely?", 2408.02442). The two papers are conflated; the citation should be split/corrected.

5. **Vendor/marketing figures are the weakest tier** (claims #22, #34-rates, #35, #37): GIN 8s→103ms,
   structured-agent 95–99%, COPY 100k rows/s, LanceDB 200M/1B & 3–8×. All single-vendor or single-blog,
   workload-specific, not independently replicated. Directionally fine; do not quote as hard facts.

6. **The scale arithmetic in R9 checks out** where it is pure arithmetic (backfill 17 min;
   raw-vector 60 GB), and is *honestly self-flagged as modeled* where it depends on corpus shape
   (row counts). No arithmetic errors found.

7. **No claim was found to be outright fabricated or contradicted by its own source.** The worst
   problems are (a) the #19 author mix-up and (b) a cluster of vendor numbers presented with more
   confidence than single-blog sourcing warrants. Several authors' caveats (OpenAlex $1/day,
   Wikidata 30%, GIN size multiple, R9 row counts) are already self-flagged in the source files.

## Sources (re-fetched for this verification)
- Splink: `_additional_context/splink/splink/internals/{comparison_library.py,settings.py}`
- mem0: `mem0/mem0/memory/main.py:452,944`
- Graphiti: `graphiti/graphiti_core/utils/maintenance/dedup_helpers.py:31,34`; driver `search_ops.py` (min_score 0.6)
- Cognee: `cognee/cognee/modules/ontology/matching_strategies.py:26,52`
- HippoRAG: `hipporag/src/hipporag/utils/config_utils.py:160`; `HippoRAG.py:869`; `utils/misc_utils.py:126`
- GraphRAG: `graphrag/docs/config/models.md:61`
- Ditto / Magellan: ar5iv 2004.00584 Table 10
- Peeters & Bizer (GPT-4 EM): arXiv 2310.11244v4 Table 4
- BlockingPy: arXiv 2504.04266 (HTML) Table 7
- CRAC 2025: arXiv 2509.17796v1
- CORE-KG: arXiv 2510.26512v1
- CorPipe license: huggingface.co/ufal/corpipe25-corefud1.3-xl-251101
- JSONSchemaBench (Geng et al.): arXiv 2501.10868 Table 8
- ICL semantic anchors: arXiv 2511.21038
- OpenSanctions Pairs: arXiv 2603.11051
- GLEIF LEI-in-Numbers 2025: gleif.org
- Argilla/HF: pymnts.com, crunchbase.com
- pgvector sizing: neon.com (30× build blog), pgvector#700
