# M2 — Understanding VIDEO for a memory system at scale (2026)

Research note for `ugm`. Scope: how to turn video into durable, groundable, rebuildable evidence at
**millions-of-documents** scale. Verdict-first, with the cost math that drives the verdict.

Legend: **[V]** = verified from a cited source; **[I]** = inferred / my calculation from cited
primitives; **[?]** = could not verify, flagged.

---

## 1. Key findings (bullets)

- **The cost lever is exactly two numbers: `frames sent to a VLM × tokens per frame` (plus audio
  tokens).** Everything else in a video pipeline (container demux, shot/scene detection, perceptual
  hashing, ASR, OCR) is **cheap, deterministic, CPU/GPU-cheap, and one-time**. The expensive,
  non-deterministic, per-query-repeatable part is pixels → VLM tokens. Design the pipeline so the
  VLM sees the **fewest, best** frames, and so the bulk of semantics comes from the (near-free)
  **ASR transcript**. **[V/I]**

- **Native long-context video ingestion (Gemini) is real and excellent for quality, but it is the
  wrong PRIMARY representation for a memory system.** Gemini stores video at **1 fps**, tokenizes
  each frame at **258 tokens (default) or 66 tokens (low `media_resolution`)**, plus **~32 tokens/s
  audio** → **~300 tokens/s default (~1.08M tok/hour)** or **~100 tokens/s low-res (~360k
  tok/hour)**. A 1M-context model covers **~1 h default / ~3 h low-res** of video. **[V]** This is
  a per-query cost you re-pay every time you ask the video a question, and it produces a monolithic
  context, not durable structure. Use it as a **targeted reasoner over already-segmented clips**,
  not as the ingestion substrate.

- **Open video-LLMs (Qwen2.5-VL / Qwen3-VL, LLaVA-Video) are good enough to be the captioner** and
  remove per-token API cost (self-host floor ≈ $0 per token, you pay GPU time). Video-MME (the
  standard video-understanding benchmark): Gemini 2.5 Pro **84.8%**, GPT-4o **71.9%** (384 frames),
  LLaVA-Video-7B is competitive on Video-MME/MLVU/LongVideoBench, Qwen2.5-VL adds dynamic-FPS +
  absolute-time encoding for hour-long video and sub-second localization (Charades-STA mIoU
  50.9). **[V]** LLaVA-Video-7B caps at **64 frames / 32K context**; that frame cap is *why* you
  must segment first. **[V]**

- **The cheap+deterministic pipeline is essentially free at scale.** ASR (WhisperX/faster-whisper) runs
  **~70× real-time** on one GPU (<8 GB for large-v2) and costs **~$0.005–0.05 per audio-hour**
  ($1 ≈ ~200 hours on cheap spot GPUs). Shot detection: PySceneDetect `ContentDetector` is a pure
  HSV mean-pixel-difference threshold on decoded frames (deterministic, decode-bound, CPU); the
  learned `TransNetV2` detector runs **~250 fps on a 2080Ti, ~20k effective fps on V100**. **[V]**
  Segmenting + transcribing 1M video-hours costs **tens of thousands of dollars one-time**, vs.
  **millions** to push every hour through a frontier video model. **[I]**

- **Recommended pipeline (cheap→expensive cascade, matches D4):**
  `demux → shot/scene segmentation (deterministic) → ASR transcript with word timecodes + diarization
  (cheap) → on-screen-text OCR on dedup'd keyframes (cheap) → SELECTIVE VLM captioning of 1 keyframe
  per shot / per scene (the only expensive step, bounded by shot count not duration) → roll captions
  + transcript into a scene/chapter tree (the "PageIndex analogue for video")`. Frontier native-video
  models are reserved for **escalation** on high-value/ambiguous scenes, not the default path. Every
  artifact is **versioned and replayed from storage on rebuild** (D7/D33), never re-derived
  nondeterministically.

---

## 2. Evidence & detail (with citations)

### 2.1 The three approaches, compared

#### (a) Native long-context video models — Gemini ingesting video directly

**Mechanism & tokenization [V]:** Gemini samples video at **1 fps**, processes audio at 1 kbps mono,
and tokenizes **frames at 258 tok (default) / 66 tok (low `media_resolution`)** and **audio at 32
tok/s**. Totals: **~300 tok/s default**, **~100 tok/s low-res**. A 1M-context model handles **~1 hour
default / ~3 hours low-res**.
Source: <https://ai.google.dev/gemini-api/docs/video-understanding>,
<https://ai.google.dev/gemini-api/docs/tokens>.

**Quality [V]:** Gemini 2.5 Pro scores **84.8%** on Video-MME — top tier among general models;
GPT-4o is **71.9%** (with 384 sampled frames). Video-MME leaderboard:
<https://llm-stats.com/benchmarks/video-mme>; Video-MME paper:
<https://arxiv.org/pdf/2405.21075>.

**Cost math (input tokens only, my calc) [I]** using current Gemini pricing
(<https://ai.google.dev/gemini-api/docs/pricing>, fetched Jun 2026):

| Model (input $/1M) | Default res (1.08M tok/h) | Low res (0.36M tok/h) |
|---|---|---|
| 2.5 Flash-Lite ($0.10) | **$0.108/h** | **$0.036/h** |
| 2.5 Flash ($0.30) | **$0.324/h** | $0.108/h |
| 3 Flash ($0.50) | $0.54/h | $0.18/h |
| 2.5 Pro ($1.25 ≤200k, **$2.50 >200k**) | **$2.70/h** | $0.90/h |

Two traps: (1) **2.5 Pro / 3.x Pro long-context pricing DOUBLES once a single prompt crosses 200k
tokens** — and a default-res video crosses 200k after **~11 minutes** (200k ÷ 300 tok/s), so any real
video is billed at the high tier. **[V]** pricing page; **[I]** the 11-min crossover. (2) These are
**per-query** input costs: ingesting the whole video into context to answer one question, then
re-paying to answer the next. For a memory system that will be queried many times, this is the wrong
place to spend.

**Position:** native video models are a **reasoner**, not a **store**. Reserve them for escalation
on a *bounded clip* (a single scene, already located by the cheap pipeline), where their cost is
small and their quality is highest.

#### (b) Keyframe-sampling-then-VLM

**Why it wins on cost [V/I]:** "Cost is two multiplications: frames sampled × tokens per frame, plus
audio" (Forasoft, *Video VLMs in 2026*:
<https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/video-vlms-frame-sampling-token-streaming-2026>).
Uniform dense sampling either misses events (too sparse) or is "prohibitively" expensive (too dense);
**adaptive keyframe / key-clip selection reports +8–10 points** over uniform sampling on long-video
benchmarks, with the gain largest at **small frame budgets (5–20 frames)** — i.e., picking *which*
frames matters more than adding frames. Some learned policies find the right frames while sampling
**~1% of the video**.
Sources: *Adaptive Keyframe Sampling* <https://arxiv.org/pdf/2502.21271>; *From Frames to Clips*
<https://arxiv.org/html/2510.02262v1>; *VideoBrain* <https://arxiv.org/abs/2602.04094>.

**The deterministic keyframe selector you already have:** PySceneDetect. Pick **one representative
frame per detected shot** (or per scene) → frame count scales with **content/edits, not duration**.
A 1-hour talking-head screen recording may have 10–40 shots; an action film has thousands. This is
the natural "selective" budget and it is free to compute.

**Cost example [I]:** suppose keyframe selection yields ~100 frames for a 1-hour video. At 258
tok/frame that's ~25.8k frame-tokens; captioned by Gemini 2.5 Flash ($0.30/M in, $2.50/M out) the
**input is ~$0.008/h**; the real spend is the **output captions** (a few hundred tokens × 100 frames
≈ 30k out ≈ $0.075/h) and the per-call overhead. Self-hosted Qwen2.5-VL-7B drops the per-token cost
to GPU time. Either way it's **single-digit cents per video-hour**, paid **once**, and it produces
durable per-shot descriptions you can ground to a timecode. Contrast with $2.70/h *per query* for
native 2.5 Pro.

#### (c) Open video-LLMs (Qwen2.5-VL video, Qwen3-VL, LLaVA-Video)

- **Qwen2.5-VL [V]:** dynamic-FPS sampling + **absolute-time encoding** (temporal position = real
  seconds), MRoPE aligned to timestamps, 3D-conv temporal modeling; handles **hour-long** video and
  **sub-second event localization** (Charades-STA temporal mIoU **50.9**, LongVideoBench-val
  **60.7**). Tech report: <https://arxiv.org/pdf/2502.13923>. 72B and 7B on HF:
  <https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct>.
- **Qwen3-VL [V]:** improved spatial/video-dynamics comprehension, longer context; flagship MoE
  (235B-A22B, ~22B active/token ≈ 22B-dense inference cost) needs **8× ≥80 GB GPUs**; vLLM ≥0.11
  supports it. <https://github.com/QwenLM/Qwen3-VL>,
  <https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html>. Smaller dense variants are
  the practical captioners on 1–2 GPUs. **[I]** the "practical captioner" judgment.
- **LLaVA-Video-7B [V]:** Qwen2-based, **32K context, ≤64 frames**, trained on LLaVA-Video-178K;
  competitive on Video-MME/MLVU/LongVideoBench/Dream-1K. <https://arxiv.org/html/2410.02713v3>,
  <https://huggingface.co/lmms-lab/LLaVA-Video-7B-Qwen2>. The **64-frame cap is the key constraint**:
  these models cannot ingest an hour raw — you MUST segment and feed them clips/keyframes.

**Takeaway:** open models are strong enough to be the **default captioner/summarizer** over
pre-segmented clips, removing per-token API cost and giving you a versioned, self-hosted, replayable
component (D7/D33). Frontier Gemini stays available for escalation.

### 2.2 Where the real cost is (and isn't)

**Cheap + deterministic (compute once, store, replay — never re-derive):**

- **Demux / decode** — ffmpeg, CPU, real-time-ish; free.
- **Shot/scene segmentation** — PySceneDetect `ContentDetector` = HSV mean-pixel-difference vs.
  threshold (`scenedetect/detectors/content_detector.py`, `_mean_pixel_distance`), fully
  deterministic; `AdaptiveDetector` (rolling-average), `HashDetector` (perceptual hash),
  `HistogramDetector` (YUV histogram), `ThresholdDetector` (fade/cut by intensity). Learned
  `TransNetV2` (4.2M params, dilated-3D-conv) gets top F1 on ClipShots/BBC at **~250 fps (2080Ti) /
  ~20k effective fps (V100)**. Sources: repo `_additional_context/PySceneDetect`;
  <https://arxiv.org/pdf/2008.04838>.
- **ASR transcript with word-level timecodes + diarization** — WhisperX: **~70× real-time** (large-v2,
  <8 GB GPU, beam 5), faster-whisper backend, wav2vec2 forced alignment for word timestamps,
  pyannote diarization, VAD batching. **~$0.005–0.05/audio-hour** ($1 ≈ ~200 h on cheap spot GPUs).
  Repo `_additional_context/whisperX`; <https://arxiv.org/abs/2303.00747>;
  cost: <https://blog.salad.com/whisper-large-v3/>, <https://www.spheron.network/blog/whisper-v4-asr-gpu-cloud-production-guide/>.
- **On-screen-text OCR** — run only on **deduplicated keyframes** (perceptual-hash near-duplicate
  frames so you OCR each distinct slide/screen once, not every frame). Cheap, deterministic.
- **Perceptual hashing / near-dup collapse** — collapses a static slide held for 5 minutes (300
  frames) into one keyframe. The single biggest free win for screen recordings / slide decks.

**Expensive + non-deterministic (minimize, version, cache):**

- **VLM captioning of frames/scenes** — the only place real money and nondeterminism enter. Bound it
  by **shot count**, not duration; describe **one keyframe per shot** (or per merged scene), not N
  uniform frames.
- **Native frontier video ingestion** — escalation only, on bounded clips.
- **LLM roll-up** — summarizing scene captions+transcript into a chapter tree; small text-only LLM
  calls, cheap.

**Scale arithmetic (1,000,000 video-hours) [I]:**

| Path | Approx cost | When paid |
|---|---|---|
| Native 2.5 Pro, default res, whole video | ~$2.7M | **every query** |
| Native Flash-Lite, low-res, whole video | ~$36k | every query |
| Pipeline: scene-detect + ASR + OCR | **<$50k** | **once** |
| Selective keyframe VLM (~cents/h) | ~$10k–$100k | once |

The deterministic pipeline + selective captioning is **one-time tens-of-thousands**, queryable forever
for free (it's now text + structure). Native whole-video ingestion is **millions, re-paid per query**.
This is the whole argument.

### 2.3 How production systems segment + summarize long video

A clear convergent pattern across 2025–2026 production and research systems:

- **NVIDIA VSS Blueprint (reference architecture) [V]:** chunk long video → VLM dense-captions each
  chunk → LLM aggregates/summarizes → builds a **knowledge graph** (GraphRAG on ArangoDB in v2.4);
  separate deterministic **CV pipeline** emits object/track metadata fused per chunk; CA-RAG builds
  the graph *during* ingestion for parallelism. Confirms: chunk-first, caption-per-chunk,
  summarize-and-aggregate, graph on top. <https://developer.nvidia.com/blog/build-a-video-search-and-summarization-agent-with-nvidia-ai-blueprint/>,
  <https://docs.nvidia.com/vss/latest/content/architecture.html>.
- **ARC-Chapter [V]:** hour-long-video chaptering trained on million-level chapters by a pipeline that
  **unifies ASR transcripts + scene text + visual captions into multi-level (hierarchical, temporally
  grounded) chapter annotations** — i.e., exactly transcript+OCR+captions → chapter tree.
  <https://arxiv.org/html/2511.14349>.
- **VideoMiner [V]:** builds a **hierarchical tree** by iterative segment→caption→cluster, with a
  policy selecting which tree nodes (keyframes) to expand for a VLM — the tree-structured selective
  pattern. ICCV 2025: <https://openaccess.thecvf.com/content/ICCV2025/papers/Cao_VideoMiner_Iteratively_Grounding_Key_Frames_of_Hour-Long_Videos_via_Tree-based_ICCV_2025_paper.pdf>.
- **Zero-shot "screenplay" summarization [V]:** select clips → VLM-caption each clip (with character
  IDs) → **align captions to the transcript in time → "screenplay" → LLM summary**. DenseStep2M is a
  training-free shot-segment + visual-text-alignment pipeline. <https://arxiv.org/pdf/2505.06594>,
  <https://arxiv.org/html/2604.26565v1>.
- **Managed option — Twelve Labs (Marengo/Pegasus) [V]:** Pegasus video-language indexing
  **$0.042/min one-time + $0.021/min input + $0.0075/1k output tokens**; Marengo embeddings +
  storage **$0.09/video-hour/month**. That's **~$3.78/hour** to index+query and a **recurring storage
  bill** — fine as a buy-vs-build benchmark, **too expensive and too opaque (closed, can't replay)
  for ugm's millions-scale, audit-grounded store.** <https://www.twelvelabs.io/pricing>,
  <https://www.twelvelabs.io/blog/introducing-pegasus-1-2>.

**The universal shape:** segment → transcribe → caption keyframes/scenes → align on a timeline →
roll up into a hierarchical chapter/scene tree → (optionally) graph. ugm should adopt this shape and
make every node **groundable to a timecode** and **versioned/replayable**.

---

## 3. Confidence & gaps

- **High confidence [V]:** Gemini tokenization math (258/66 tok-frame, 32 tok/s audio, ~300/~100
  tok/s, 1 h / 3 h windows); current Gemini prices and the 200k long-context doubling; WhisperX ~70×
  real-time and <8 GB; PySceneDetect detector mechanisms (read from source); TransNetV2 throughput/F1;
  LLaVA-Video 64-frame/32K cap; Video-MME headline scores; Twelve Labs per-minute pricing; the
  production segment→caption→tree pattern (NVIDIA VSS, ARC-Chapter, VideoMiner).
- **Medium confidence [I]:** all per-hour and 1M-hour **cost extrapolations** — they're my arithmetic
  from cited unit prices and assume input-token-dominant cost, ignore prompt/output overhead, batching
  discounts, and **context caching** (which would further cut re-query cost on native ingestion). The
  "~100 keyframes/hour" example is illustrative; real shot counts vary 10×–100× by content type.
- **Gaps / not verified [?]:** exact Qwen2.5-VL-72B Video-MME number (leaderboard didn't surface it;
  reported only as "robust on MVBench/PerceptionTest/Video-MME"); Qwen3-VL throughput/$ per video-hour
  on vLLM (no clean benchmark found); Gemini **Batch API** (typically ~50% off) applicability to video
  inputs — likely yes but unconfirmed for video; whether Gemini context caching reduces the per-query
  re-pay for stored video (probable, would change the (a) calculus, unverified for video specifically).
  These don't change the verdict (the deterministic pipeline dominates regardless) but would refine the
  escalation budget.

---

## 4. Recommendation for ugm (concrete, tied to decisions)

**Verdict: build the cheap-first deterministic pipeline as the PRIMARY video representation; use VLMs
selectively per shot/scene; reserve frontier native-video ingestion for escalation.** This is the
video instantiation of the hybrid already argued in `external_agents/codex_architecture.md` (text is
the reasoning interface; native media is the evidence anchor; P1 vectors are projection-only) and it
is the direct application of **D4 (cheap-first cascade)** and **D7/D33 (versioned, replayed-from-
storage, never nondeterministically re-derived)**.

### 4.1 The video conversion cascade (the `convert()` for `mime: video/*`, generalizing D38)

Cheapest → most expensive, each stage gated by the previous:

1. **Demux + probe** (ffmpeg) — streams, fps, duration, codecs. Deterministic.
2. **Shot/scene segmentation** — PySceneDetect `ContentDetector` (default) or `TransNetV2` (learned,
   for hard/high-motion content). Deterministic, replayable; output is a list of `(shot_id,
   start_tc, end_tc)`. Optionally merge shots into **scenes** by visual+transcript similarity.
3. **ASR** — WhisperX large-v3: word-level timecodes + segment text + **speaker diarization**. Near-
   free, deterministic given pinned model version. This is the **primary semantic content** of most
   videos (meetings, lectures, product demos) and it lands straight into the **D32 char-offset world**
   because a transcript IS text.
4. **Keyframe selection + near-dup collapse** — one representative frame per shot; perceptual-hash to
   drop held/static frames (slides, screens). Deterministic.
5. **OCR on keyframes** — on-screen text / slides / code / UI. Cheap, deterministic. Critical for
   screen recordings, which are mostly text-on-screen, not speech.
6. **Selective VLM captioning** — caption **one keyframe per shot/scene** (self-hosted Qwen2.5-VL /
   LLaVA-Video by default; Gemini for escalation). This is the **only expensive, nondeterministic
   step**; its budget is **shot count**, persisted with `model_version` + prompt + sample policy in
   the conversion manifest (D7/D33/D38), and **never re-run on rebuild** — replayed from storage.
7. **Roll-up (chapter tree)** — a small text LLM merges per-shot captions + OCR + diarized transcript
   into a **scene/chapter tree** (titles + summaries + timecode spans). Cheap.

**Escalation rule (D4 in spirit):** only send a scene's raw clip to a frontier native-video model
(Gemini, bounded to that scene's seconds so it stays under the 200k/low-res-cheap regime) when the
cheap path is ambiguous or the scene is high-value. Spend scales with ambiguity/value, not volume —
exactly D25/D4's principle, here applied to pixels instead of claims.

### 4.2 The "PageIndex analogue for video" (extends D39)

D39 gives documents a per-document hierarchical tree (`node_id, title, summary, nested nodes,
spans`). The video analogue is a **MediaIndex / scene tree** with the same shape but **temporal
locators**:

```
video_index:
  video_id, content_hash, duration, fps, raw_uri
  chapters[]:            # LLM roll-up level (the "sections")
    chapter_id, title, summary, start_tc, end_tc
    scenes[]:            # merged shots
      scene_id, start_tc, end_tc, keyframe_uri(s), keyframe_phash
      shots[]:           # deterministic segmentation
        shot_id, start_tc, end_tc
      visual_caption{ text, model_version }     # selective VLM (replayable)
      ocr_runs[]{ text, bbox, frame_tc }        # cheap OCR
  transcript[]:          # WhisperX, the text pipeline input
    seg_id, start_tc, end_tc, speaker, text, word_timestamps[]
  conversion_manifest:   # D7/D33: every model+version+prompt+policy+artifact_uri
```

The **`document_markdown` that E1/E2 consume** is a deterministic **linearization** of this tree:
diarized transcript interleaved with per-scene `[visual: …]` captions and `[on-screen: …]` OCR, with
chapter/scene headings. Each linearized line carries **both** a char-offset (for the existing E1/E2
pipeline, D32 anchor verification) **and** a pointer to the MediaIndex node + **timecode range** (the
true native anchor). Claims extracted by E2 thus ground to a **timecode (+ optional keyframe bbox)**,
not merely to a generated sentence — auditability *improves*.

### 4.3 Grounding (D32) for video

D32's source_span (char offsets) generalizes to a **polymorphic media-locator**: for video it is a
`{start_tc, end_tc, optional keyframe_uri+bbox}`. Anchor verification splits cleanly by provenance:

- **Transcript-derived claims** keep **strict D32**: the span is a verbatim slice of ASR text at
  known timecodes — exact, deterministic, fully auditable today.
- **Visual-caption-derived claims** are anchored by **frame/timecode membership + (optional) region
  bbox**, with the caption stored alongside its `model_version`. Because the caption is a *lossy,
  nondeterministic rewrite*, the audit guarantee is "this claim was derived by model M(version v)
  from the frame at this timecode/region," and the artifact (keyframe + caption + manifest) is
  persisted and replayable. The anchor is the **pixels at a time**, not the generated sentence — same
  principle as codex_architecture's "the chart region, not the caption."

### 4.4 P1 / retrieval

Add a **multimodal sub-index** over **keyframes and scene segments** (CLIP/SigLIP keyframe embeddings;
ColPali/ColQwen-style late-interaction multi-vectors for slide/screen page-images — see
`_additional_context/colpali`; optionally Marengo native-video-segment embeddings as a managed
benchmark). These vectors are **entry points only** (D6/D8/D9): they locate candidate scenes for
visual-similarity search; **Postgres stays the one belief ledger** and truth is decided by the
claims/relations/observations derived through the text pipeline. This keeps "one belief home" intact
while recovering the visual retrieval power that pure-text linearization would lose.

### 4.5 Non-goals / scope boundaries (state, don't phase)

- **No parallel "visual fact" store.** Visual evidence produces the same claims/relations/observations
  via the text pipeline; it does not get its own belief system (would violate D2/D3/D6/D43 — two homes
  for belief that would drift).
- **Native whole-video frontier ingestion is not the default substrate** — it is an escalation
  reasoner over bounded clips. Documented alternative, not a future phase.
- **Frame-exhaustive captioning (every frame, or dense uniform sampling) is a non-goal** — the
  evidence (Adaptive Keyframe Sampling, +8–10 pts at small budgets) and the cost math both say
  shot-bounded selective captioning is strictly better. The deletion of dense sampling is a
  *simplification* (correct at any scale), not a deferral.
