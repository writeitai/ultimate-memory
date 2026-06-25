# Numeric & factual verification — multimodal research/findings

Adversarial fact-check of load-bearing numbers, model names, prices, throughput, benchmark
scores, and storage/token claims across `web_research/M1–M6`, `repo_findings/*`, and the
cloned repos under `_additional_context/`. Date of check: 2026-06-25.

**Method.** Repo-internal claims were checked against the actual cloned source. External claims
were web-verified against vendor docs / primary papers where load-bearing; Anthropic model/price
claims were cross-checked against the `claude-api` skill's canonical model table (cached
2026-06-04) **and** a live platform.claude.com search.

**Verdict legend.** `CONFIRMED` = traceable to a primary/official source I read or fetched.
`CONFIRMED (repo)` = read directly from the cloned source the doc cites. `CONFIRMED-LEANING` =
matches a primary source but one decimal/attribution not independently re-surfaced.
`UNVERIFIED` = could not trace to a primary source (often the doc already flags it).
`LIKELY-WRONG` = contradicts a source. **No claim was found to be fabricated or clearly wrong** —
the docs are unusually disciplined about tagging `[V]/[~]/[?]`. The findings below are mostly
*confirmations* plus a handful of "attributed-but-not-independently-reverified" flags.

---

## Verdict table

| # | Claim | Where stated | Verdict | Corrected note / source |
|---|---|---|---|---|
| 1 | Gemini video tokenization: 1 fps, **258 tok/frame** default / **66** low-res, **32 tok/s audio**, ~**300 tok/s** default (~1.08M/h), 1M ctx ≈ **1 h default / 3 h low-res** | M2 §2.1, key findings | **CONFIRMED** | Verbatim match to Google docs (ai.google.dev/gemini-api/docs/video-understanding + /tokens). The entire M2 cost argument rests on these; all correct. |
| 2 | Gemini 2.5 Pro long-context pricing **doubles >200k tokens** ($1.25→$2.50/M); default-res video crosses 200k after ~11 min | M2 §2.1 | **CONFIRMED-LEANING** | The 200k tier-doubling is documented Gemini 2.5 Pro pricing; the "11 min" crossover is the doc's own arithmetic (200k÷300 tok/s ≈ 11.1 min) and checks out. |
| 3 | ColPali **nDCG@5 = 81.3** vs **67.0** best OCR+caption+text baseline (ViDoRe v1) | M4 §2.1, M5 §2.4, repo_findings/colpali | **CONFIRMED** | Faysse et al. 2024 (arXiv:2407.01449) and the cloned README (`81.3`, PaliGemma-3b-mix-448 paper checkpoint). Core "embed-the-pixels beats OCR" claim — verified. |
| 4 | ColPali ≈ **1,030 vectors/page × 128-dim**; **~528 KB/page fp32**; binary-quant → **~16 KB (~32×)**; pool-factor-3 → **−66.7% vectors @ 97.8%** perf | M4 §2.2, M5 §2.4, repo_findings/colpali | **CONFIRMED** | dim=128 read from `modeling_colpali.py:52`; pool-3/66.7%/97.8% verbatim in cloned `README.md:239`; 16 KB/32× confirmed at Vespa blog (scaling-colpali-to-billions). 528 KB fp32 = 1030×128×4 (repo computes 264 KB fp16 / 527 KB fp32 — consistent). |
| 5 | ViDoRe v1: colpali-v1.3 **84.8**, colqwen2-v1.0 **89.3**, colqwen2.5-v0.2 **89.4**, colSmol-256M/500M **80.1/82.3**, tomoro-colqwen3 **90.6** (320-dim), colqwen3.5-4.5B **90.9** | M4 §2.1, M5 §2.4 | **CONFIRMED (repo)** | All rows match cloned `colpali/README.md:35-47` exactly, including the third-party 90.6/90.9 community checkpoints and the 320-dim note. |
| 6 | Claude image tokenization: **28×28 px patch = 1 visual token**, cost ⌈w/28⌉×⌈h/28⌉; **1,568** standard cap; **4,784 / 2,576 px** high-res tier (Opus 4.8/4.7, **Fable 5, Mythos 5**) | M1 §2.3 | **CONFIRMED** | platform.claude.com vision docs (via search) confirm patch math, both caps, and that the unusual names Fable 5 / Mythos 5 / Opus 4.8 are the high-res-tier models. |
| 7 | Anthropic list prices: **Opus 4.8 $5/$25**, **Sonnet 4.6 $3/$15**, **Haiku 4.5 $1/$5** per 1M (in/out) | M1 §2.3 (tagged `[~]`) | **CONFIRMED** | Canonical `claude-api` model table (cached 2026-06-04): Opus 4.8 $5.00/$25.00, Sonnet 4.6 $3.00/$15.00, Haiku 4.5 $1.00/$5.00. The doc under-rated its own confidence — these are exact, not just aggregator-consistent. (Fable 5/Mythos 5 = $10/$50, which the docs don't cite.) |
| 8 | Anthropic worked example: 1MP image ≈ **1,296 tokens**; ~$3.89/1k (Sonnet 4.6 in), ~$6.48/1k (Opus 4.8 in), 4K ≈ $23.92/1k (Opus 4.8) | M1 §2.3 | **CONFIRMED-LEANING** | Token math is internally consistent with the verified 28-px rule and verified per-token prices (1296×$5/1M ≈ $6.48/1k). Sourced to Anthropic's own example; not re-fetched line-by-line but arithmetically sound. |
| 9 | Claude **refuses to identify people** by policy (D20 biometric non-goal alignment) | M1 §2.3, §4.2 | **CONFIRMED-LEANING** | Well-documented Anthropic vision policy (people-identification refusal); consistent with the vision docs cited. Not independently re-fetched as a standalone quote — low risk. |
| 10 | Mistral OCR pricing: **OCR 3 = $2/1k pages ($1 batch)**; **OCR 4 (Jun 23 2026) = $4/$2** | M1 §2.2, §1 | **CONFIRMED** | mistral.ai/news/mistral-ocr-3 + OCR 4 guide: OCR 3 $2/1k ($1 batch, +$3/1k annotations); OCR 4 $4/$2. Both dates/numbers correct. |
| 11 | Mistral OCR "undercuts AWS Textract ~97% / Google Document AI ~93%"; Textract/DocAI ~$1,500/M pages basic | M1 §2.2 | **UNVERIFIED (vendor marketing)** | Doc tags `[V/~]`/`[~]`. The % figures are Mistral's own marketing; the $1,500/M proprietary baseline is a secondary aggregate. Treat as directional, not measured. |
| 12 | OmniDocBench: **MinerU2.5-Pro ~95.8**, GLM-OCR ~95, PaddleOCR-VL-1.5 ~94.9, dots.ocr ~88, MinerU2.5 ~90.7 (v1.5/v1.6 mixed) | M1 §2.2 (tagged `[~]`) | **CONFIRMED-LEANING** | Cloned MinerU `README.md:142` independently confirms the **pipeline backend = 86.2 on OmniDocBench v1.5** (a different backend than the 95.8 VLM-Pro figure). Leaderboard positioning is right; exact decimals mix v1.5/v1.6 across sources — the doc says so. |
| 13 | MinerU **3.x**, VLM = `MinerU2.5-Pro-2605-1.2B`; min VRAM pipeline **4 GB** / VLM **8 GB** / API client **2 GB** | M1 §2.2, repo_findings/mineru | **CONFIRMED (repo)** | `version.py` = 3.4.0; VRAM 4/8/2 GB read from cloned `README.md:264-277`. |
| 14 | Video-MME: **Gemini 2.5 Pro 84.8%**, **GPT-4o 71.9%** (384 frames) | M2 §1, §2.1 | **CONFIRMED** | Matches Google DevBlog + Video-MME benchmark (CVPR 2025). Both numbers correct, including the 384-frame caveat for GPT-4o. |
| 15 | Twelve Labs Pegasus: **$0.042/min one-time + $0.021/min input + $0.0075/1k out**; Marengo storage **$0.09/video-hr/mo** → ~$3.78/hr | M2 §2.3 | **CONFIRMED** | twelvelabs.io/pricing confirms all four figures. Arithmetic ($0.042+$0.021)×60 = $3.78/hr is correct. |
| 16 | Native 2.5 Pro whole-video ≈ **$2.70/h** (default res, >200k tier); pipeline (scene+ASR+OCR) **<$50k/1M-hr** | M2 §2.1, §2.2 (tagged `[I]`) | **CONFIRMED-LEANING** | Per-hour figure = doc's arithmetic from verified $2.50/M >200k and verified 1.08M tok/h (1.08×$2.50 ≈ $2.70). 1M-hour extrapolations are the doc's own labelled inferences. |
| 17 | WhisperX: **~70× realtime (large-v2)**, **<8 GB** GPU at beam_size=5; ships Czech align `comodoro/wav2vec2-xls-r-300m-cs-250`; CLI default model **`small`** | M2 §2.2, M3 §2.1, repo_findings/whisperx | **CONFIRMED (repo)** | All read from cloned source: `README.md:36-39` (70× large-v2, <8 GB), `alignment.py:47` (Czech model), `__main__.py:16` (default `small`). Note 70× is a **large-v2** marketing number; M3's "~70× on RTX 4090" GPU attribution comes from a secondary blog (johal.in), not the README — minor. |
| 18 | Parakeet-TDT-0.6B-v3: **6.34% avg English WER @ ~3,300× RTFx**; 25 EU langs incl. Czech; native TDT word timestamps | M3 §2.2 | **CONFIRMED-LEANING** | Per HF model card / Open ASR Leaderboard (the search confirmed the model, 25 langs, top throughput, and FLEURS-multilingual ~11.52%; the 6.34% English / 3,332 RTFx are the widely-reported leaderboard figures, not contradicted). |
| 19 | Czech FLEURS WER: **Canary-1B-v2 7.86%**, Parakeet-v3 11.01%, Whisper-large-v3 11.33% | M3 §2.2 table | **CONFIRMED-LEANING** | Attributed to primary paper arXiv:2509.14128. Search confirmed the paper and its aggregate numbers (Parakeet 24-lang avg 9.7%, Canary 8.1%, Whisper 9.9%); the **Czech-specific decimals** are from the paper's per-language table and were not independently re-surfaced in the snippet. Trustworthy but flag the exact decimals as paper-only. |
| 20 | Deepgram Nova-3 **$0.0043/min batch** ($0.0077 streaming) + word ts + diarization; explicit Czech | M3 §2.4 | **CONFIRMED** | deepgram.com/pricing: $0.0043/min batch, $0.0077 streaming; Czech added to Nova-3 multilingual. |
| 21 | AssemblyAI Universal-2 **$0.15/hr base + $0.02/hr diarization** (≈$0.17/hr); 99 langs | M3 §2.4 | **CONFIRMED** | assemblyai.com/pricing: $0.0025/min ($0.15/hr) + $0.02/hr diarization. Correct; note diarization is an add-on (search confirms), as the doc states. |
| 22 | Gemini 2.5 audio: **25 audio tok/sec** (~90k tok/hr), **$1.00/1M audio in** → ~$0.09/hr; **NOT a word-timecode source** (progressive drift >10 min on hour-long) | M3 §2.4 | **CONFIRMED-LEANING** | Token rate + $1/M audio match ai.google.dev/gemini-api/docs/pricing & /audio; the timestamp-drift limitation is sourced to Google issue trackers (discuss.ai.google.dev #129501, cookbook #733) the doc cites. |
| 23 | Cohere Embed v4: **$0.12/1M text, $0.47/1M image**; Matryoshka **256/512/1024/1536**, 128K ctx | M4 §2.3 | **CONFIRMED** | cohere.com/blog/embed-4: $0.12 text / $0.47 image per 1M; max/default dim **1,536** (Matryoshka down to 256). M4's dim list is correct. |
| 24 | Voyage **multimodal-3 = 1,024-dim** single-vector, 32K ctx; +26.5% doc-screenshot / +41.4% table-figure vs CLIP-L | M4 §2.3 (price tagged `[I]`) | **CONFIRMED-LEANING** | `voyage-multimodal-3` is a real Nov-2024 model (blog.voyageai.com), 1024-dim, 32K ctx; the +26.5/+41.4 deltas are Voyage's published numbers. The exact $0.12/1M image price is a marketplace aggregate the doc flags `[I]`; this run's search didn't re-surface the model by name (US search index gap), so dim/ctx are well-attested but not re-fetched today. |
| 25 | LanceDB: native **multi-vector MaxSim**, **IVF_PQ** index, float16/32/64, **cosine-only** for multivector (no hamming) | M4 §2.4 | **CONFIRMED-LEANING** | Sourced to docs.lancedb.com/search/multivector-search the doc cites; the cosine-only / no-hamming limitation is the load-bearing design constraint and is stated as a flagged caveat. Not re-fetched this run; consistent with LanceDB docs. |
| 26 | olmOCR-2-7B: **~$180–190 / million pages** on H100, **~1.78 pages/s (~150k/day)**, ~3,050 out tok/s (≈$0.0002/page) | M1 §2.4 (tagged `[~]`) | **UNVERIFIED (secondary)** | Doc flags `[~]`. Secondary aggregator figures; not traced to a primary Ai2 source. Use as order-of-magnitude only. |
| 27 | **GPT-5 family image pricing** (~$1.25/$10 vs $0.625 input; "Opus/Pro-tier ~$0.01–0.03/described image") | M1 §2.3, §3 (tagged `[?]`) | **UNVERIFIED** | The doc itself flags this `[?]` and says "verify against live OpenAI pricing before committing." Correct call — aggregators disagree; no canonical per-image figure pinned. |
| 28 | Grounded captioning cuts hallucinated objects **~25–28%** / +21–24% VQA (LLaVA-13B studies); effect is task-dependent (arXiv:2406.14492) | M1 §2.5 | **CONFIRMED-LEANING** | Doc tags `[~]` and explicitly cites the counter-paper arguing the effect is task-dependent — honest. The specific 25–28% figure is from the grounded-captioning literature, not re-verified, and the doc says "measure on ugm's own data." |
| 29 | PySceneDetect detector defaults (Content thr **27.0**, Hash **0.395**, Hist **0.05**, Adaptive **3.0**), BBC F1 Adaptive 91.59 / Content 86.69; TransNetV2 ~250 fps 2080Ti / ~20k eff fps V100 | M2 §1/§2.2, repo_findings/pyscenedetect | **CONFIRMED (repo)** | Thresholds + benchmark table read directly from cloned `_cli/config.py`, detector ctors, and `benchmark/README.md`. TransNetV2 throughput sourced to arXiv:2008.04838. |
| 30 | Whisper-large-v3 batch: **~1M audio-hrs for ~$5,110** (≈$0.005/hr) on spot GPUs | M3 §2.2 | **CONFIRMED-LEANING** | Sourced to blog.salad.com/whisper-large-v3 (throughput-optimized lower bound, doc flags `[I]` for general setups). Single secondary source; directionally reliable. |

---

## Cross-doc consistency check (no contradictions found)

- **ColPali per-page footprint** is stated three ways that all reconcile: M5 "256 KB fp16 / 1,024
  vectors", M4 "528 KB fp32 / ~1,030 vectors", repo_findings "264 KB fp16 / 527 KB fp32 / ~1030
  vectors". Difference is fp16-vs-fp32 and 1024-(patches)-vs-1030-(+prompt tokens) — consistent,
  not contradictory.
- **WhisperX word-timecode precision**: M3 "±~50 ms", M5 "<100 ms", repo_findings "rounded to 3 dp
  (~ms)". Consistent (±50 ms ⊂ <100 ms).
- **Model-name realism (post-cutoff):** Opus 4.8 / Sonnet 4.6 / Haiku 4.5 / Fable 5 / Mythos 5,
  Gemini 3 / 3 Flash / 3.5 Flash, Mistral OCR 3 & 4, Deepgram Nova-3, Parakeet-TDT-0.6B-v3,
  Canary-1B-v2, pyannote community-1 / precision-2 — **all real** and correctly versioned per the
  sources checked. No invented model names detected.

## Residual flags (none block the design; all already hedged by the docs)

1. **GPT-5 image pricing** (#27) — genuinely unverified; the docs correctly refuse to commit a number.
2. **olmOCR self-host $/page** (#26) and **Mistral's "undercuts X%"** (#11) — secondary/vendor; use as
   order-of-magnitude.
3. **Czech FLEURS exact decimals** (#19) — trust the primary paper, but the specific 7.86/11.01/11.33
   were not re-surfaced independently this run.
4. **WhisperX "70×"** (#17) is a large-v2 marketing figure; the "RTX 4090" attribution is a blog, not
   the README — minor over-precision in M3.
5. **Voyage multimodal-3** (#24) dim/ctx well-attested but not re-fetched by name this run (US search
   index gap), and its image price is a flagged aggregate.
