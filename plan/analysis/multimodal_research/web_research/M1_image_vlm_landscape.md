# M1 — Image → faithful, grounded structured text (2026 landscape)

**Question.** Best 2026 approaches to turn an IMAGE into faithful, GROUNDED structured text for a
memory system: dense captioning / structured description, chart+figure+table understanding, and OCR.
Frontier VLM APIs (Claude / GPT / Gemini) vs strong open VLMs (Qwen-VL, InternVL, OCR specialists).
What is faithful (low-hallucination) at scale, at what cost per image, and how to keep descriptions
grounded/auditable (region references). Recommendation + cheap-first cascade.

*Evidence collected June 2026. Each claim tagged **[V]** verified from a primary/official source I
fetched or a consistent set of sources, **[~]** plausible but from secondary aggregators only, or
**[?]** could not verify — flagged rather than asserted. Prices and benchmark numbers move monthly;
treat all numbers as starting points to measure (per CLAUDE.md), not committed constants.*

---

## 1. Key findings (bullets)

- **There is no single "image→text" model; there are two different jobs, and the cheap-first split is
  the whole game.** Job A = **read the page** (OCR + layout + tables + formulas + reading order →
  structured Markdown with region boxes). Job B = **describe the scene** (what a photo/figure/chart
  *means* in prose). Job A is solved cheaply and deterministically-enough by specialist document
  models; Job B is where you spend frontier-VLM money, and only selectively. Routing by which job an
  image needs is the dominant cost and quality lever.

- **For Job A (document/figure/chart/table extraction), small open OCR-VLMs now match or beat frontier
  APIs and cost ~10–50× less.** On OmniDocBench (the standard document-parsing benchmark), sub-2B
  specialist models lead: **MinerU2.5-Pro ~95.8**, **GLM-OCR (0.9B) ~95**, **PaddleOCR-VL-1.5 (0.9B)
  ~94.9**, **dots.ocr (1.7B) ~88** — all open-weight, all emitting **bounding boxes + categories +
  reading order**, i.e. grounded by construction. **[V/~]** Self-hosted cost is ~**\$0.0002/page**
  (olmOCR ~\$180–190 per **million** pages on one H100); hosted **Mistral OCR 3 is \$2/1,000 pages
  (\$1 batch)**. **[V]**

- **For Job B (faithful free-form description), frontier VLMs are still better at low-hallucination
  prose, but the price spread across the frontier is ~20×.** Approx all-in cost per 1-megapixel image
  with a ~300-token description: **Gemini 2.5 / 3 Flash ≈ \$0.001–0.002**, **Claude Haiku 4.5 ≈
  \$0.003**, **Claude Opus 4.8 / Gemini 3 Pro / GPT-5-class ≈ \$0.01–0.03**. **[V for the token math;
  ~ for list prices].** So "cheap frontier" (Flash-tier) is ~5–20× cheaper than "smart frontier"
  (Opus/Pro) for the *same* describe task — escalate by image only when the cheap tier flags
  uncertainty.

- **Grounding/auditability is a solved capability you must explicitly turn on.** All three frontier
  families and the open OCR-VLMs can emit **region references**: Gemini returns normalized
  `[ymin,xmin,ymax,xmax]` boxes in **0–1000** coordinates (plus segmentation masks on 2.5+); Claude
  returns **absolute pixel** boxes relative to the resized image; Qwen3-VL/InternVL do 2D (and Qwen 3D)
  grounding; OCR specialists (dots.ocr, PaddleOCR-VL, Granite-Docling **DocTags**) emit
  `element + bbox + category + reading-order` JSON natively. **[V]** Grounded captioning (forcing the
  model to attach a region to each asserted object) measurably cuts hallucination — ~**25–28% fewer
  hallucinated objects** in the grounded-vs-plain caption literature. **[~]**

- **Recommendation for ugm: a 3-rung cheap-first image cascade that drops cleanly into the D38
  converter router and generalizes D32 grounding from char-offsets to (page, bbox).** Rung 0:
  deterministic layout+OCR specialist (open, self-hosted, e.g. MinerU/dots.ocr/PaddleOCR-VL) →
  Markdown **with per-block page+bbox** — this is the image analogue of today's `{markdown, blocks[]}`.
  Rung 1: a **cheap frontier/open VLM** (Gemini Flash-tier, or self-hosted Qwen3-VL-8B) writes a
  **grounded structured description only for the non-text regions** (photos, figures, charts the OCR
  layer marked as `picture`/`chart`), each description carrying the region box it describes. Rung 2:
  escalate a small flagged minority to a frontier model (Opus/Pro/GPT-5) for hard charts/dense
  infographics. Spend scales with ambiguity, not volume (D4/D25).

---

## 2. Evidence & detail

### 2.1 The two jobs, and why the split matters

A memory system that ingests images needs different things from a scanned invoice, a slide screenshot,
a product photo, and a bar chart. Two distinct capabilities:

- **Job A — Document/structure reading (OCR + layout).** Recover the *text and structure already
  present in the image*: characters, tables (→ HTML/Markdown), formulas (→ LaTeX), code blocks,
  reading order, and the bounding box of each element. This is largely deterministic-in-spirit (the
  ground truth exists in the pixels) and is exactly what ugm's D38 router already calls "scanned/complex
  PDF + images → OCR". **Low hallucination is achievable because the model is transcribing, not
  inventing.**

- **Job B — Scene/figure description (dense captioning).** Produce *new prose* about what an image
  shows: a photo's contents, a diagram's meaning, a chart's trend. This is a **lossy, non-deterministic
  rewrite** — the source of hallucination risk and the reason grounding (region references) matters.

Mixing them is the classic mistake: pointing a big general VLM at a scanned page to "describe it" both
costs more and hallucinates more than a specialist OCR model that transcribes it. Conversely, running a
pure-OCR model on a vacation photo yields nothing useful. **Route per image to the job it needs.**

### 2.2 Job A — OCR / document / chart / table understanding (the cheap, grounded layer)

**OmniDocBench** (CVPR 2025; opendatalab) is the de-facto benchmark for end-to-end PDF/document
parsing, scoring text, tables, formulas, and reading order together.
<https://github.com/opendatalab/OmniDocBench> **[V]**

Leaderboard snapshot (overall score, OmniDocBench v1.5/v1.6 — **note version mismatch across sources,
treat as approximate**) **[~]**:

| Model | Params | Open? | OmniDocBench overall | Native grounding output |
|---|---|---|---|---|
| MinerU2.5-Pro | ~1.2B | Open (MinerU license, Apache-based) | ~95.8 (v1.6) | bbox + reading order + tables→HTML, formulas→LaTeX |
| GLM-OCR | 0.9B | Open | ~95.2 (v1.6) / 94.6 (v1.5) | layout boxes + categories |
| PaddleOCR-VL-1.5 | 0.9B | Open (Apache) | ~94.9 (v1.6) / 94.5 (v1.5) | layout boxes + reading order |
| dots.ocr | 1.7B | Open | ~88 (v1.5) | JSON `{bbox, category}` + Markdown + viz image |
| MinerU2.5 | 0.9–1.2B | Open | ~90.7 (v1.5) | bbox + reading order |

Sources: OmniDocBench repo; MinerU repo + MinerU2.5/2.5-Pro reports (arXiv 2509.22186, 2604.04771);
PaddleOCR-VL-1.5 report (arXiv 2601.21957); dots.ocr (HF `rednote-hilab/dots.ocr`, arXiv 2512.02498).
**[V for existence/positioning; ~ for exact scores]**

Why these matter for ugm specifically:

- **They emit grounding for free.** dots.ocr "outputs a JSON file with bounding boxes and categories, a
  Markdown file with recognized text, and a visualization image" and switches tasks (layout / text /
  bbox-grounding / table / formula) by prompt. **[V]** That is precisely the
  `blocks[] with offsets` contract D38 needs, except the locator is a **page+bbox** instead of a char
  offset.
- **Granite-Docling-258M / DocTags is the most ugm-aligned of all.** IBM's Granite-Docling (258M;
  Idefics3 arch with `siglip2-base-patch16-512` vision encoder + a Granite 165M LLM, released
  Sep/Oct 2025) emits **DocTags**: a markup that records *every page element + its coordinates + its
  logical relationships* (table topology, inline/floating math, code, captions, reading order), which
  downstream tools convert to Markdown/HTML/JSON. **[V]** This is "elements + coordinates +
  relationships" — an auditable, grounded intermediate, not just flat text.
- **Docling** (IBM/LF AI & Data, MIT license) is the orchestration library ugm should treat as the D38
  reference converter: PDF/DOCX/PPTX/XLSX/HTML/images, "page layout, reading order, table structure,
  code, formulas, image classification," **chart understanding** (barchart/piechart/lineplot → tables
  or code **plus** a description), DocTags export, runs **locally/air-gapped**, and exposes bbox per
  element. <https://github.com/docling-project/docling> **[V]**
- **MinerU 3.x** (the repo cloned in `_additional_context/MinerU`) gives ugm a production-shaped engine
  with **three backends** it can route between: `pipeline` ("fast & stable, **no hallucination**, CPU
  or GPU", now PP-OCRv6), `vlm-engine` (MinerU2.5-Pro 1.2B via vLLM/LMDeploy/mlx), and `hybrid-engine`
  ("native text extraction, low hallucination"). 109-language OCR, formulas→LaTeX, tables→HTML, header/
  footer removal, cross-page table merge, human reading order, multi-GPU router. License moved to an
  Apache-based MinerU license in 3.1. **[V — from the cloned README]** The `pipeline`/`hybrid`
  "no/low hallucination" framing is exactly the faithfulness property ugm wants for Job A.

**Frontier APIs also do Job A well** — Gemini 3 Pro "excels across the entire document processing
pipeline — from highly accurate OCR to complex visual reasoning" and tops document-understanding evals
**[~]**; Qwen2.5-VL reports **96.4% DocVQA** **[~]** — but for high-volume transcription they cost
more per page than a self-hosted 1B specialist and add a network dependency. Use them for Job A only on
the hard tail (degraded scans, exotic layouts) the specialist flags.

**Hosted OCR price points** (useful as the "buy vs. self-host" reference): **Mistral OCR 3** (Dec 2025)
**\$2 / 1,000 pages, \$1 batch**; Mistral OCR 4 (Jun 23 2026) \$4/\$2; "~1,000 pages per \$". Mistral
markets it as undercutting AWS Textract ~97% / Google Document AI ~93%. **[V/~]** Proprietary document
AI (Textract / Google Document AI / Azure) sits around **\$1,500 / million pages** for basic text, much
more for forms/tables. **[~]** Note ugm's D38 already names "Mistral OCR" as the example image/scanned
converter — that remains a sound *hosted* default; the self-hosted open stack is the scale play.

### 2.3 Job B — frontier VLMs for faithful free-form description

**Claude (Anthropic).** **[V — fetched platform.claude.com vision + pricing]**
- Tokenization: image is split into **28×28-pixel patches = 1 visual token each**; cost =
  `⌈width/28⌉ × ⌈height/28⌉`. Standard tier caps at **1,568 tokens / 1,568 px long edge**;
  high-resolution tier (**Opus 4.8 / 4.7, Fable 5, Mythos 5**) caps at **4,784 tokens / 2,576 px**.
  A 1,000×1,000 image = **1,296 tokens** on both tiers; a 4K image = 4,784 (high-res) vs ~1,560
  (standard, downscaled).
- List prices (per 1M tokens): **Opus 4.8 \$5 / \$25**, **Sonnet 4.6 \$3 / \$15**, **Haiku 4.5
  \$1 / \$5**. **[~ — consistent across aggregators, not the official table fetched]** Anthropic's own
  worked example: a 1MP image is ~**\$3.89 per 1,000 images** on Sonnet 4.6 (input only), ~**\$6.48 per
  1,000** on Opus 4.8, and a 4K image ~**\$23.92 per 1,000** on Opus 4.8. **[V]**
- Grounding: returns **absolute pixel coordinates relative to the post-resize image** (a dedicated
  "Coordinates and bounding boxes" guide explains the resize/pad math so you can map back to original).
  Explicitly: coordinate/localization outputs are **approximate**; counting large numbers of small
  objects is unreliable; and Claude **refuses to identify people** by policy (relevant to ugm D20
  biometric non-goal). **[V]**

**Gemini (Google).** **[V — fetched ai.google.dev image-understanding; prices from aggregators ~]**
- Tokenization: **258 tokens if both dims ≤ 384 px**; larger images tiled into **768×768 tiles, 258
  tokens each** (crop-unit = `floor(min(w,h)/1.5)`). A 960×540 image ≈ 6 tiles. Max **3,600 images/
  request**.
- Grounding: object detection returns boxes in **normalized 0–1000** coordinates, format
  `[ymin, xmin, ymax, xmax]`; **Gemini 2.5+ adds segmentation masks** (base64 PNG probability maps) —
  the richest hosted grounding output of the three families. **[V]**
- Frontier members (mid-2026): **Gemini 3 Pro** (Nov 18 2025) — SOTA document/OCR + visual reasoning
  (MMMU-Pro, Video-MMMU) **[~]**; **Gemini 3 Flash** at **\$0.50 / \$3.00** per 1M tokens **[~]**;
  **Gemini 3.5 Flash** (May 19 2026) reportedly tops Roboflow's Vision Evals across document
  understanding / counting / spatial **[~]**; older **Gemini 2.5 Flash \$0.30 / \$2.50**, ~258 tokens
  for a small image → ~**\$0.00008 input/image**. **[~]** Flash-tier Gemini is the cheapest competent
  frontier describer.

**GPT-5 family (OpenAI).** **[~ — prices inconsistent across aggregators; flag]** GPT-5 (Aug 2025) and
successors (GPT-5.2 Dec 2025, GPT-5.5) accept image input and **charge image tokens at the standard
text-token rate**. Commonly cited list for GPT-5 is **~\$1.25 / \$10** per 1M tokens (some aggregators
show lower "mini"/tiered numbers like \$0.625 input — **I could not confirm a single canonical image
price; treat GPT-5 image cost as "Opus/Pro-tier, ~\$0.01–0.03 per described 1MP image" and verify
against the live OpenAI pricing page before committing**). GPT-5 returns coordinates if prompted but
has no first-class segmentation-mask API like Gemini. **[?]**

**Approx all-in cost to *describe* one ~1MP image (input image tokens + ~300-token grounded
description output)** — order-of-magnitude, my arithmetic from the token rules above **[V math /
~ list prices]**:

| Model (tier) | Input img tokens | ~ all-in \$/image | ~ \$/1,000 images |
|---|---|---|---|
| Gemini 2.5 Flash | ~258–1,032 | ~\$0.001 | ~\$1 |
| Gemini 3 Flash | ~1,032 | ~\$0.0015 | ~\$1.5 |
| Claude Haiku 4.5 | 1,296 | ~\$0.003 | ~\$3 |
| Claude Sonnet 4.6 | 1,296 | ~\$0.008 | ~\$8 |
| Claude Opus 4.8 / Gemini 3 Pro / GPT-5-class | 1,296–4,784 | ~\$0.013–0.03 | ~\$13–30 |

Takeaway: the **describe** step is 5–20× cheaper on Flash/Haiku tiers than on Opus/Pro tiers. For a
millions-of-images corpus, default-describe on a cheap tier and **escalate by exception**.

### 2.4 Open VLMs for Job B (self-hosted description / grounding)

- **Qwen3-VL** (Alibaba, Sep–Oct 2025, **Apache 2.0**): dense **2B/4B/8B/32B** + MoE **30B-A3B /
  235B-A22B**, 256K context (expandable), strong **multilingual OCR**, **precise 2D/3D object
  grounding**, chart/UI understanding (Design2Code ~92, ChartMimic ~80.5; 235B-Thinking MMStar ~78.7).
  The flagship 235B reportedly matches/beats Gemini-2.5-Pro and GPT-5 on several VQA benches.
  <https://github.com/QwenLM/Qwen3-VL> **[~]** The 8B/32B dense models are the realistic
  self-host workhorses for ugm-scale description+grounding.
- **InternVL3** (OpenGVLab/Shanghai AI Lab, Apr 2025, 1B–78B): "Native Multimodal Pre-Training";
  **InternVL3-78B = 72.2 MMMU**, SOTA among open MLLMs, competitive with GPT-4o / Claude 3.5 / Gemini
  2.5 Pro; **InternVL3.5** (Aug 2025) extends versatility/efficiency. arXiv 2504.10479 / 2508.18265.
  **[V/~]**
- **Self-host economics** (the reason to consider open at scale): olmOCR-2-7B (Ai2, Oct 2025) reports
  **~\$180–190 per *million* pages** on an H100, **~1.78 pages/sec (~150k pages/day) per GPU**, ~3,050
  output tok/s. **[~]** That is ~**\$0.0002/page** — orders of magnitude under any hosted frontier
  describe. A self-hosted Qwen3-VL-8B describe step lands in a similar regime once batched on owned
  GPUs (no per-token list price), at the cost of running the infra.

### 2.5 Faithfulness & grounding — how to keep descriptions auditable

- **Hallucination is measurable.** **CHAIR** scores object hallucination by comparing mentioned objects
  to ground-truth annotations; **POPE**-style probing, and 2025 benches **DetailVerifyBench**,
  **HalDec-Bench**, **LOTUS** target *dense/long* caption hallucination specifically. **[V/~]**
- **Grounded captioning reduces hallucination.** Forcing the model to **interleave region references**
  (attach a bbox to each asserted object) cuts hallucinated objects ~**25–28%** and lifts VQA accuracy
  ~21–24% in the grounded-vs-plain literature (e.g., LLaVA-13B studies). Caveat: at least one paper
  ("Does Object Grounding Really Reduce Hallucination…", arXiv 2406.14492) argues the effect is
  task-dependent — so **measure on ugm's own data**, don't assume. **[~]**
- **Practical auditability recipe for ugm:** require every described object/claim to cite the **region
  box it came from** (Gemini 0–1000 boxes; Claude pixel boxes; OCR-VLM native boxes), and verify the
  box is **inside the image** and overlaps a layout region the OCR pass detected. This is the image
  analogue of D32's "anchor" (span is a real slice) + "window-membership" (added substring exists in
  the bundle): an asserted region must lie within the source image and, ideally, within a detected
  content block — a description that references empty/out-of-bounds regions is rejected. The
  **entailment** rung (D32 layer 3) stays text-only: does the description follow from the OCR'd text +
  detected objects in that region.

---

## 3. Confidence & gaps

- **High confidence [V]:** the two-jobs framing; Claude image tokenization + resolution tiers + Job-B
  cost math + grounding behavior + people-refusal (fetched from official docs); Gemini tokenization +
  0–1000 boxes + segmentation masks + 3,600-image limit (fetched from official docs); existence and
  positioning of the open OCR-VLM stack (MinerU/Docling/dots.ocr/PaddleOCR-VL/Granite-Docling) and
  their native bbox/DocTags grounding (cloned repos + official sources); Mistral OCR \$2/1k pricing.
- **Medium confidence [~]:** exact OmniDocBench scores (v1.5 vs v1.6 mixed across sources — directionally
  right, the precise decimals are not); frontier list prices for Claude/Gemini (consistent across
  aggregators but not all re-fetched from the live billing page today); Qwen3-VL/InternVL benchmark
  numbers (from vendor/aggregator summaries); olmOCR throughput/cost figures (secondary).
- **Low confidence / unverified [?]:** **GPT-5-family image pricing** — aggregators disagree (\$0.625 vs
  \$1.25 input); I did not pin a canonical per-image figure. **Verify against the live OpenAI pricing
  page before any GPT cost commitment.** Also unverified: whether claimed "no hallucination" of
  MinerU/Docling pipeline backends holds on ugm's specific document mix (vendor framing — must be
  measured), and the exact hallucination-reduction % from grounding on long structured descriptions
  (literature is mixed).
- **Gaps not covered here (other sub-questions):** native multimodal *retrieval* embeddings
  (CLIP/SigLIP/Voyage-multimodal/**ColPali** "embed the page image, skip OCR") — relevant to the brief's
  P1/Lance question #4 but out of M1's image→**text** scope; I flag ColPali as a complementary
  *projection* path (visual page retrieval) that does **not** replace the grounded-text description
  path. Video is a separate work item.

---

## 4. Recommendation for ugm (concrete, tied to decisions)

**Verdict: transcode images to grounded structured text at E0 via a 3-rung cheap-first cascade that
extends the existing D38 converter and generalizes D32 grounding from char-offsets to a polymorphic
`(page, bbox)` locator.** This keeps the text pipeline (E1→E2→E3), the one-belief-home invariant, and the
auditability crown jewel intact, while adding region-level provenance for pixels.

### 4.1 The image cascade (drops into the D38 router, honors D4/D25 cheap-first)

- **Rung 0 — deterministic read (always run; the image analogue of `{markdown, blocks[]}`).** Route any
  image/scanned input to an **open, self-hosted layout+OCR specialist** — **MinerU `pipeline`/`hybrid`
  backend** (or **Docling** with Granite-Docling/DocTags, or **dots.ocr**) — producing **Markdown +
  `blocks[]` where each block carries `{page, bbox, category, reading_order}`** and tables→HTML,
  formulas→LaTeX. This is the faithful, grounded, ~\$0.0002/page (self-host) or ~\$0.001–0.002/page
  (hosted Mistral OCR) layer. The block `category` (`text` / `table` / `formula` / `picture` / `chart`)
  is the routing signal for Rung 1. **Keep "Mistral OCR" as the hosted-default the D38 example already
  names; add the open self-hosted engine as the scale path.**
- **Rung 1 — cheap grounded description (selective; only on non-text regions).** For blocks the OCR pass
  marked `picture`/`chart`/`figure` (and for whole-image "photo" inputs with little text), call a
  **cheap describer** — **Gemini 2.5/3 Flash** hosted, or **self-hosted Qwen3-VL-8B / InternVL3-8B** —
  to emit a **structured description constrained to that region's bbox**, plus chart→table extraction.
  ~\$1–3 per 1,000 regions hosted; near-marginal-cost self-hosted. Each description stores the
  **region box it describes** (Gemini 0–1000 → convert to pixels; or the specialist's box).
- **Rung 2 — frontier escalation (the flagged tail only).** When Rung 1 self-reports low confidence, or
  the region is a dense infographic / complex chart / degraded scan, escalate that **single region** to
  a frontier model (**Claude Opus 4.8 / Gemini 3 Pro / GPT-5-class**), ~\$0.01–0.03/region. Spend
  scales with ambiguity, not volume — exactly D4 + the D25 "no pre-extraction value gate, junk-control
  in-call" stance, applied per region.

### 4.2 How it binds to the pipeline

- **D38 (converter):** an image converter is a new entry in the router table returning the *same*
  `{markdown, blocks[]}` shape, except each block's locator is `{page, bbox}` (and, for described
  regions, a `description` block whose text is the VLM prose and whose locator is the region box). It is
  **versioned** (`converter_version`) and **replayed-from-storage on rebuild** (D7/D33) — store the OCR
  JSON, the chosen rung, and the VLM description as durable artifacts; never re-call the model
  non-deterministically.
- **D32 (grounding) generalization — the key design delta:** replace "char offsets into converted text"
  with a **polymorphic media-locator**: text → `char_span`; image → `{page, bbox}` (optionally a
  Granite-Docling DocTags element id); (video, future → `timecode_range`). The three D32 acceptance
  rungs map cleanly: **anchor** = the bbox is in-bounds and overlaps a detected content block;
  **window-membership** = any quoted on-image text verbatim-exists in the OCR transcript of that region
  (rejects fabricated quotes); **entailment** = the description follows from the OCR text + detected
  objects in that region. A described claim that points at empty/out-of-image pixels fails anchor — the
  pixel-equivalent of a non-substring span.
- **E2/E3/D41/D43 unchanged:** OCR Markdown chunks (E1) and per-region descriptions both flow into E2 as
  text; claims carry `(page, bbox)` provenance instead of char offsets; values → observations (D43);
  asserted-validity intervals (D41) come from dates in the OCR'd/described text. No new belief home.
- **D20 / privacy boundary:** description and entity-linking from images stay **text-derived** (names in
  OCR/captions). **No biometric face/voice identification** — consistent with Claude's own
  people-refusal policy and a clean non-goal to state explicitly.

### 4.3 Concrete default stack to prototype-and-measure

- Job A engine: **MinerU 3.x** (`hybrid`/`pipeline`, self-hosted) as primary; **Docling + DocTags** as
  the grounded-structure alternative; **Mistral OCR 3** as the hosted fallback for the hard tail. All
  emit boxes.
- Job B describer: **Gemini 3 Flash** (hosted cheap) or **Qwen3-VL-8B** (self-hosted) for Rung 1;
  **Claude Opus 4.8 / Gemini 3 Pro** for Rung 2 escalation.
- Grounding contract: per-block `{page, bbox, category, reading_order}` + per-description `{region_bbox,
  source_engine, model_version}`; verify in-bounds + block-overlap before accepting (D32-analogue).

*All model choices and numbers are starting points to measure on ugm's own document mix, not committed
constants (CLAUDE.md Rule 2).*
