# Multimodal ingestion landscape for AI memory, as of 2026-06-25

This memo is written for a text-centric, replayable memory pipeline: immutable raw bytes; a versioned conversion module that emits structured text plus source locators; downstream chunking, claim extraction, and entity resolution; and cheap-first cascades before any expensive model call.

I distinguish:

- **Verified fact**: directly supported by the cited source.
- **Inference**: engineering recommendation or cost extrapolation from verified pricing/behavior.
- **Unverified**: I could not verify a concrete number or behavior from a primary source and do not rely on it.

The short position: **do not make a frontier VLM the default converter**. At million-document scale, default to deterministic parsing/OCR plus layout provenance, use page/image embeddings for retrieval, and reserve VLM calls for routed exceptions: figures, charts, screenshots, low-confidence OCR, and representative video keyframes. For video, the real cost driver is not "video" as a media type; it is how many frames and seconds you ask a model to inspect.

## 1. Image understanding and VLMs

**Recommendation:** For "describe an image into faithful, grounded text" at scale, run a two-tier cascade:

1. **Default self-hosted tier:** OCR/layout first (`PaddleOCR-VL`, `Surya`, `Docling`, `MinerU`, depending on document vs natural image), then use an open VLM only on regions that need semantics. My default open VLM for English/multilingual document-like images is **Qwen2.5-VL-7B/72B** or newer Qwen3/InternVL family where licenses and hardware fit; use 7B for routing and 72B/API for high-value uncertain images.
2. **Escalation tier:** **Claude Sonnet/Opus, GPT-5.x vision, Gemini 3.x Pro/Flash** for chart reasoning, ambiguous screenshots, dense figures, or QA-style extraction when correctness matters more than unit cost.

**Verified facts.**

- Qwen2.5-VL's technical report says it targets visual recognition, object localization, document parsing, long-video comprehension, structured extraction from invoices/forms/tables, and chart/diagram/layout analysis; Qwen's blog says it ships 3B, 7B, and 72B models and supports bounding boxes/points and stable JSON outputs ([Qwen blog](https://qwenlm.github.io/blog/qwen2.5-vl/), [arXiv 2502.13923](https://arxiv.org/abs/2502.13923)).
- Anthropic documents image limits and costs: Claude charges images as visual tokens, with a 1000x1000 image costing 1296 visual tokens; Sonnet 4.6 is listed at $3/MTok input and $15/MTok output, and the vision guide estimates a 1000x1000 image at about $3.89 per thousand images for input only ([Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Claude vision](https://platform.claude.com/docs/en/build-with-claude/vision)).
- OpenAI states image inputs are metered in tokens and points users to a vision pricing calculator; current pricing tables list GPT-5.4/5.5 family token prices and separate realtime image/audio rates ([OpenAI images/vision](https://developers.openai.com/api/docs/guides/images-vision), [OpenAI pricing](https://developers.openai.com/api/docs/pricing)).
- Gemini pricing exposes a wide cost range: Gemini 3.1 Flash-Lite text/image/video input is $0.25/MTok standard and $0.125/MTok batch; Gemini 3.1 Pro Preview is $2/MTok input and $12/MTok output up to 200k tokens, with batch at half input/output ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)).

**Inference and practical cost.**

- A 1MP Claude Sonnet image with a 250-400 token caption is roughly **$7-$10 per 1,000 images**: about $3.89 input plus $3.75-$6.00 output. That is fine for routed exceptions and terrible as an unconditional million-image converter.
- Gemini Flash-Lite is the cheapest frontier API family for bulk visual labeling when quality is sufficient, but lower cost does not remove the need for deterministic OCR: OCR gives locators and replayable text; VLM captions do not reliably give exact offsets.
- Open VLMs are attractive when data privacy dominates and GPU amortization is available. However, for "faithful grounded text," open VLMs still hallucinate missing details. Force output schemas to include `visible_text`, `objects`, `relationships`, `uncertain`, `not_visible`, and `source_region_id`; never accept free-form captions as canonical facts.

**Position.**

Use VLMs as **semantic enrichers**, not as the first parser. For images in a memory system, store:

- deterministic OCR text with bounding boxes,
- image-level and region-level captions as versioned model artifacts,
- a confidence/routing sidecar,
- source locators: image hash, pixel bbox, page/frame timestamp if applicable.

## 2. Document parsing with figures, charts, and tables

**Recommendation:** Make **Docling or MinerU** the self-hosted default, but choose by workload:

- **Docling default** when you need a Python library, broad format support, a typed document model, lossless JSON, Markdown export, and provenance-compatible integration.
- **MinerU default** when your corpus is dominated by PDFs/images with heavy OCR, scientific formulas, multilingual OCR, and large-scale batch parsing where its router/API/concurrency design matters.
- **Mistral OCR** as the hosted cost baseline for difficult PDFs or burst capacity.
- **Reducto/LlamaParse** for "we need best practical parsing now" commercial workflows, but only behind a versioned adapter because pricing/output contracts are vendor-specific.
- **Marker** as a useful local baseline for PDF/image/PPTX/DOCX/XLSX to Markdown/JSON/HTML with image extraction, but I would not make it the only parser if you need durable locator fidelity across many document types.

**Verified facts from local repos.**

- Docling advertises PDF/DOCX/PPTX/XLSX/HTML/EPUB/audio/image support, advanced PDF layout/reading-order/table/formula/image classification, Markdown/HTML/WebVTT/DocLang/DocTags/lossless JSON export, local execution, OCR, VLM support, ASR, and an API server ([local: `_additional_context/docling/README.md:35-46`](../../../_additional_context/docling/README.md)). Its quickstart exports Markdown (`export_to_markdown`) ([local: `_additional_context/docling/README.md:91-99`](../../../_additional_context/docling/README.md)).
- Docling code builds `ProvenanceItem` objects with page number, character span, and bounding box for figure captions, figures, table captions, table cells, and tables ([local: `_additional_context/docling/docling/utils/glm_utils.py:144-165`](../../../_additional_context/docling/docling/utils/glm_utils.py), [local: `_additional_context/docling/docling/utils/glm_utils.py:193-260`](../../../_additional_context/docling/docling/utils/glm_utils.py)).
- MinerU documents private/offline deployment, with `pipeline`, `vlm-engine`, and `hybrid-engine` modes; it describes `pipeline` as fast/stable/no hallucination on CPU/GPU, VLM as higher accuracy, and hybrid as high accuracy with native text extraction and lower hallucination ([local: `_additional_context/MinerU/README.md:70-77`](../../../_additional_context/MinerU/README.md)).
- MinerU 3.4 says its `pipeline` OCR upgraded to PP-OCRv6, improving OmniDocBench v1.6 OCR accuracy by about 11% and OCR processing speed by about 100% ([local: `_additional_context/MinerU/README.md:83-90`](../../../_additional_context/MinerU/README.md)). MinerU 3.3 documents `effort=medium/high` with 35%-220% speed improvements for medium depending on platform/scenario, while `medium` omits image analysis ([local: `_additional_context/MinerU/README.md:101-116`](../../../_additional_context/MinerU/README.md)).
- MinerU features include PDF/image/DOCX/PPTX/XLSX inputs, header/footer removal, reading order, image descriptions, tables, formulas to LaTeX, tables to HTML, scanned/garbled PDF OCR, 109-language OCR, Markdown/JSON/intermediate outputs, CLI/FastAPI/Gradio, and CPU/GPU/MPS support ([local: `_additional_context/MinerU/README.md:170-185`](../../../_additional_context/MinerU/README.md)).

**Verified facts from web.**

- Mistral OCR 3 claims text and embedded image extraction, Markdown output with HTML table reconstruction, model ID `mistral-ocr-2512`, and pricing of **$2/1,000 pages**, or **$1/1,000 pages** via Batch API ([Mistral OCR 3](https://mistral.ai/news/mistral-ocr-3/)).
- Google Cloud lists Mistral OCR 25.05 as GA with document input/text output, understanding media/text/tables/equations, but with low default quotas: 30 QPM and 30 pages/request in listed regions ([Google Cloud Mistral OCR](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/mistral/mistral-ocr)).
- Reducto says Parse runs OCR, layout detection, table reconstruction, figure summarization, and semantic chunking, with every block returning type, page position, and confidence ([Reducto Parse](https://docs.reducto.ai/parse/overview)).
- LlamaIndex pricing is credit-based, with **1,000 credits = $1.25**; I did not verify a stable per-page LlamaParse credit cost from the public pricing page, so per-page LlamaParse cost is **unverified** ([LlamaIndex pricing](https://www.llamaindex.ai/pricing)).
- Marker states it converts PDF/image/PPTX/DOCX/XLSX/HTML/EPUB to Markdown, JSON, chunks, and HTML; formats tables/forms/equations/math; extracts images; removes headers/footers; supports optional LLM boosting; and runs on GPU/CPU/MPS ([Marker GitHub](https://github.com/datalab-to/marker)).

**Position.**

For this memory system, parser output must be more than Markdown. The durable contract should be:

```json
{
  "text": "canonical markdown or docling/docjson text rendering",
  "blocks": [
    {
      "id": "block_...",
      "type": "paragraph|table|figure|formula|caption|ocr_text",
      "text_span": [1234, 1450],
      "source": {"page": 7, "bbox": [x1, y1, x2, y2]},
      "assets": [{"type": "crop", "sha256": "..."}],
      "model_version": "parser@version"
    }
  ]
}
```

Markdown is for downstream language stages; JSON/provenance is for rebuilds, citation, and debugging.

## 3. Visual document retrieval

**Recommendation:** Add visual page retrieval as a **parallel index**, not a replacement for OCR text retrieval:

- For normal prose, OCR/text embeddings still win on cost, transparency, and exact citation.
- For slides, scans, charts, figures, diagrams, forms, tables, and bad OCR, use **ColQwen2/ColQwen2.5 or ColNomic/ColPali-style late interaction** over page images.
- Store page-image retrieval only at page or region granularity; do not try to put every multi-vector patch into a vanilla single-vector store without a retrieval backend designed for late interaction.

**Verified facts.**

- The local ColPali README describes ColPali as visual document retrieval using VLMs to create multi-vector embeddings from document page images, following ColBERT-style late interaction, and says this removes the need for brittle layout recognition/OCR pipelines while considering layout, charts, and visual content ([local: `_additional_context/colpali/README.md:19-28`](../../../_additional_context/colpali/README.md)).
- The local ColPali model table lists ColQwen2 and ColQwen2.5 variants with Apache 2.0 licenses and ViDoRe scores around 87-89, plus later ColQwen3-style entries above 90 in that local clone ([local: `_additional_context/colpali/README.md:33-48`](../../../_additional_context/colpali/README.md)).
- ColPali's optional fused MaxSim kernels avoid materializing a `[B, B, Lq, Ld]` tensor; the README notes memory grows quadratically with batch size and gives an H100 training benchmark where fused kernels doubled largest trainable batch size from 64 to 128 with unchanged throughput ([local: `_additional_context/colpali/README.md:64-72`](../../../_additional_context/colpali/README.md)).
- The ColPali paper states that directly embedding document page images with late interaction outperforms modern document retrieval pipelines while being simpler/faster/end-to-end trainable on ViDoRe ([arXiv 2407.01449](https://arxiv.org/abs/2407.01449)).
- DSE proposes treating document screenshots as a unified input without content extraction, preserving text/image/layout, and reports competitive text-intensive retrieval plus >15 nDCG@10 improvement over OCR text retrieval for mixed-modality slide retrieval ([arXiv 2406.11251](https://arxiv.org/abs/2406.11251)).

**Inference: storage and latency.**

- Late interaction stores many vectors per page. If a ColQwen page uses about 768 patch vectors at 128-320 dimensions, float16 storage is roughly **196 KB to 491 KB per page** before metadata/index overhead (`768 * dims * 2 bytes`). At 10M pages that is **~2-5 TB raw vectors**, likely more with ANN structures. This is not a side feature; it is an index architecture decision.
- Query latency is also different: scoring is MaxSim over query-token vectors and page patch vectors, not a single dot product. Use a two-stage search: cheap text/BM25/single-vector candidates first, then late-interaction rerank on top-K pages.

**Position.**

Visual retrieval beats OCR-then-embed-text when the answer is encoded in:

- chart geometry, table layout, or figure labels,
- scanned pages with poor OCR,
- slide decks and screenshots,
- forms where position matters,
- mixed text/visual pages where a caption alone loses the signal.

It loses when you need exact text snippets, legal-grade citations, or cheap corpus-wide recall over clean prose.

## 4. Multimodal embeddings

**Recommendation:** Use **three separate retrieval surfaces**, because no single embedding type is best:

1. **Text embedding index** over canonical text chunks. This remains the primary memory retrieval path.
2. **Single-vector multimodal index** over page images, figure crops, screenshots, and thumbnails for cheap cross-modal search. Use **Voyage multimodal**, **Cohere Embed v4**, **Jina CLIP v2**, **Nomic Embed Vision/Multimodal**, **SigLIP/CLIP** depending on hosting and quality needs.
3. **Late-interaction visual document index** over selected pages or page classes, using ColQwen/ColNomic/ColPali-like retrievers.

**Verified facts.**

- Voyage charges `voyage-multimodal-3.5`/`voyage-multimodal-3` by text tokens and image/video pixels: $0.12/MTok and $0.60 per billion pixels after free allowances. A 1000x1000 image is listed at **$0.60 per 1,000 images**; max charge per image is $0.0012 because images over 2M pixels are downsampled for billing ([Voyage pricing](https://docs.voyageai.com/docs/pricing)).
- Cohere Embed v4 supports text and image inputs, interleaved text+image content, float/int8/uint8/binary/ubinary outputs, and configurable dimensions 256-1536; Bedrock docs list context length up to ~128k tokens and image downsampling above 2,458,624 pixels ([AWS Bedrock Cohere Embed v4](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v4.html)).
- Cohere's pricing page exposes Model Vault dedicated instance pricing for Embed 4 at **$4/hour small** or **$5/hour medium**, but not a simple public token/image API price on that page ([Cohere pricing](https://cohere.com/pricing)). Pay-as-you-go Embed v4 unit price is therefore **unverified from the primary pricing page I opened**.
- Jina CLIP v2 is described as a multilingual multimodal embedding model for text and images, adding multilingual support, visual document understanding, and Matryoshka truncation ([Jina model page](https://jina.ai/models/jina-clip-v2/), [arXiv 2412.08802](https://arxiv.org/abs/2412.08802)).
- Nomic Embed Vision v1/v1.5 shares the same latent space as Nomic Embed Text v1/v1.5 ([Nomic Embed Vision](https://www.nomic.ai/news/nomic-embed-vision)); Nomic Embed Multimodal includes 3B/7B variants for text/images/PDFs/charts and ColNomic late-interaction variants ([Nomic Embed Multimodal](https://www.nomic.ai/news/nomic-embed-multimodal)).
- Gemini Models lists **Gemini Embedding 2** as a multimodal embedding model mapping text, images, video, audio, and PDFs into a unified space; pricing should be verified separately before production budgeting ([Gemini models](https://ai.google.dev/gemini-api/docs/models)).

**Position.**

Use single-vector multimodal embeddings for **recall and browsing**, not for final grounding. They are cheap and flexible, but collapse spatial detail. Use late interaction for page-level document retrieval where layout matters. Use text embeddings for exact memory extraction and claim/entity pipelines.

Recommended vector-store payloads:

- text chunks: `{doc_id, conversion_version, block_ids, charspan, page/bbox refs}`
- page image embeddings: `{doc_id, page, image_sha256, parser_version, lowres_asset_sha256}`
- figure/table crop embeddings: `{doc_id, page, bbox, crop_sha256, caption_block_id}`
- late-interaction page vectors: external shard/object pointer, not embedded directly into ordinary metadata rows.

## 5. ASR, diarization, and alignment

**Recommendation:** For self-hosted video/audio ingestion, use **faster-whisper or WhisperX today**, with **NVIDIA Parakeet/Canary** as the next model family to evaluate for speed and native word timestamps. Use **pyannote community-1** for diarization when privacy matters. Use **Deepgram or AssemblyAI** when you need managed scale, diarization, and operational SLAs faster than you can build them.

**Verified facts from local WhisperX.**

- WhisperX provides fast ASR with word-level timestamps and speaker diarization, claims 70x realtime with Whisper large-v2, uses faster-whisper requiring <8GB GPU memory for large-v2 with beam size 5, uses wav2vec2 alignment, pyannote diarization, and VAD preprocessing ([local: `_additional_context/whisperX/README.md:36-44`](../../../_additional_context/whisperX/README.md)).
- WhisperX's documented Python flow is transcribe, align, then assign speaker labels from a diarization pipeline ([local: `_additional_context/whisperX/README.md:161-205`](../../../_additional_context/whisperX/README.md)).
- WhisperX notes language-specific alignment defaults for `{en, fr, de, es, it}` and many other languages via Hugging Face, with manual model selection for unsupported languages ([local: `_additional_context/whisperX/README.md:150-151`](../../../_additional_context/whisperX/README.md)).

**Verified facts from web.**

- NVIDIA Canary 1B v2 model card claims 25 European languages, automatic punctuation/capitalization, accurate word- and segment-level timestamps, translation timestamps, and a permissive CC BY 4.0 license ([Canary 1B v2](https://huggingface.co/nvidia/canary-1b-v2)).
- Pyannote `speaker-diarization-community-1` provides exclusive speaker diarization to simplify reconciliation with transcription timestamps ([Hugging Face pyannote community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)); pyannote's blog positions community-1 as its best open-source diarization pipeline ([pyannote blog](https://www.pyannote.ai/blog/community-1)).
- Deepgram Nova-3 pricing is public: Nova-3 Monolingual is $0.0048/min streaming and $0.0077/min pre-recorded pay-as-you-go; Nova-3 Multilingual is $0.0058/min streaming and $0.0092/min pre-recorded. Speaker diarization is an add-on at $0.0020/min pay-as-you-go ([Deepgram pricing](https://deepgram.com/pricing)).
- AssemblyAI public pricing lists Universal-3 Pro at **$0.21/hr** and Universal-2 at **$0.15/hr**, with word-level timestamps in the pre-recorded feature description; add-on details continue on the same pricing page ([AssemblyAI pricing](https://www.assemblyai.com/pricing)).

**Inference.**

- WhisperX remains the best pragmatic open-source glue because it solves the memory-system need: transcript text plus word offsets plus speaker labels. Parakeet/Canary may be faster/cleaner for supported languages, but you still need diarization reconciliation and a pipeline wrapper.
- For 100k hours of audio, Deepgram Nova-3 Multilingual pre-recorded plus diarization is roughly `(0.0092 + 0.0020) * 60 * 100k = $67,200` pay-as-you-go before discounts. AssemblyAI Universal-2 base at $0.15/hr is $15,000 before add-ons. Self-hosted GPU cost can be far lower at high utilization, but engineering/QA costs dominate.

**Position.**

Store audio/video transcript as a first-class conversion:

```json
{
  "segments": [
    {
      "start_s": 12.34,
      "end_s": 18.90,
      "speaker": "SPEAKER_01",
      "text": "...",
      "words": [{"text": "word", "start_s": 12.34, "end_s": 12.56, "confidence": 0.91}]
    }
  ],
  "model_versions": {"asr": "...", "aligner": "...", "diarizer": "..."}
}
```

Run VAD first, then ASR, then alignment, then diarization/speaker assignment. For meetings with separate channels, preserve channel identity; it is often better than diarization.

## 6. Video understanding

**Recommendation:** Default to **keyframe/shot/ASR-first video understanding**. Use native long-context video models only for selected assets where temporal reasoning is the core content.

**Verified facts.**

- Gemini's video docs say the model samples video at **1 FPS** for visual descriptions and may miss rapid motion or quick scene changes ([Gemini video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)).
- Gemini technical details: 1M-context models can process up to 1 hour at default media resolution or 3 hours at low resolution; video tokenization is roughly **300 tokens/second** at default resolution or **100 tokens/second** at low resolution, including 1 FPS frames, audio, and metadata ([Gemini video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)).
- Gemini Enterprise docs list video understanding support across Gemini 3.5 Flash, 3.1 Flash-Lite, 2.5 Pro/Flash variants and note maximum video length around 45 minutes with audio or 1 hour without audio for listed models in that environment ([Google Cloud video understanding](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/video-understanding)).
- Qwen2.5-VL reports long-video comprehension and second-level event localization using absolute time encoding ([Qwen2.5-VL arXiv](https://arxiv.org/abs/2502.13923)).

**Inference: real cost driver.**

At Gemini 3.1 Pro $2/MTok input, a 60-minute video at 300 tokens/s is about `3600 * 300 = 1.08M input tokens`, or **$2.16 input only** before output; at batch it is about half. At Flash-Lite $0.25/MTok, the same input is **$0.27**. That is surprisingly affordable per hour, but latency, quota, privacy, and quality control still argue against feeding every video wholesale. Also, 1 FPS can miss UI changes, fast cuts, and on-screen text transitions.

**When native video is worth it:**

- "What happened when X occurred?" over long temporal context.
- Sports/security/lab footage where ordering and duration matter.
- Multimodal questions combining audio, visual action, and timestamps.
- You need a chapter-level narrative summary and can tolerate approximate grounding.

**When keyframes are better:**

- Lecture videos, screen recordings, slide decks, webinars.
- Product demos where on-screen text and UI state matter.
- Any corpus where you need source locators for claims.
- Any large-scale ingest where most frames are redundant.

**Position.**

Native video is an **escalation model**, not the ingestion backbone. The backbone is ASR + deterministic shot/scene segmentation + keyframe OCR + routed VLM descriptions.

## 7. Scene/shot detection and keyframe extraction

**Recommendation:** Use **PySceneDetect ContentDetector/AdaptiveDetector as the deterministic default**, with **TransNetV2** as an optional learned detector for edited media where gradual transitions/camera motion defeat thresholding.

**Verified facts from local PySceneDetect.**

- PySceneDetect exposes CLI and Python APIs for scene detection, split-video, and save-images; the README shows `detect('my_video.mp4', ContentDetector())` returning start/end times, and notes `AdaptiveDetector` handles fast camera movement better while `ThresholdDetector` handles fade in/out events ([local: `_additional_context/PySceneDetect/README.md:36-62`](../../../_additional_context/PySceneDetect/README.md)).
- `ContentDetector` defaults to threshold `27.0` and `min_scene_len=15`; its code computes frame score from HSV hue/saturation/luminance deltas and optional edges, comparing weighted frame score to threshold ([local: `_additional_context/PySceneDetect/scenedetect/detectors/content_detector.py:104-180`](../../../_additional_context/PySceneDetect/scenedetect/detectors/content_detector.py)).
- `AdaptiveDetector` computes content scores then applies a rolling average to mitigate false detections from camera movement; defaults include `adaptive_threshold=3.0`, `window_width=2`, and `min_content_val=15.0` ([local: `_additional_context/PySceneDetect/scenedetect/detectors/adaptive_detector.py:12-17`](../../../_additional_context/PySceneDetect/scenedetect/detectors/adaptive_detector.py), [local: `_additional_context/PySceneDetect/scenedetect/detectors/adaptive_detector.py:29-67`](../../../_additional_context/PySceneDetect/scenedetect/detectors/adaptive_detector.py)).

**Verified facts from web.**

- TransNetV2 is an open-source neural shot-boundary detector with reported F1 scores of 77.9 on ClipShots, 96.2 on BBC Planet Earth, and 93.9 on RAI in its README; the repo says users do not need to train and can use inference code ([TransNetV2 GitHub](https://github.com/soCzech/TransNetV2)).

**Position.**

The cheap deterministic video preprocessor should emit:

- container metadata: duration, fps, resolution, codecs, audio streams,
- shot boundaries from PySceneDetect,
- scene/chapter candidates from merged shots plus ASR topic shifts,
- keyframes: first/middle/last per shot plus perceptual-hash deduplication,
- frame locators: `{video_sha256, timestamp_s, frame_no, shot_id}`.

Only after this should a VLM see images.

## 8. On-screen and in-video text OCR

**Recommendation:** Treat video OCR as a separate channel from image captioning. Use frame sampling plus OCR before VLM. For slides/screen recordings, OCR is often more valuable than visual captions.

**Self-hostable stack:**

- **PaddleOCR / PaddleOCR-VL** for multilingual OCR and document-like frames.
- **Surya OCR** for layout, reading order, and table recognition when license fits.
- **Tesseract** only for cheap printed text baselines and controlled language/layout cases.
- **EasyOCR** for simple scene text in many scripts, but less suitable as the only document OCR backbone.

**Verified facts.**

- PaddleOCR's repo describes a lightweight OCR toolkit for images/PDFs, supports 100+ languages, and includes PaddleOCR-VL/document parsing topics ([PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR)). PaddleOCR-VL's paper describes a 0.9B multilingual document parser supporting 109 languages and recognizing text, tables, formulas, and charts ([PaddleOCR-VL arXiv](https://arxiv.org/html/2510.14528v1)).
- Surya is described as a 650M OCR model with layout analysis, reading order, table recognition, 91-language benchmark coverage, and claimed 5 pages/s on RTX 5090 ([Surya GitHub](https://github.com/datalab-to/surya)).
- Tesseract is an Apache 2.0 open-source OCR engine supporting many languages and direct/API usage ([Tesseract docs](https://tesseract-ocr.github.io/tessdoc/Installation.html)).
- EasyOCR supports 80+ languages and common scripts ([EasyOCR GitHub](https://github.com/JaidedAI/EasyOCR)).

**Pipeline detail.**

Do not OCR every frame. Use:

1. sample at shot boundaries and every N seconds for long static shots,
2. perceptual hash / SSIM dedupe frames,
3. crop likely text regions where possible,
4. run OCR,
5. merge text over time with start/end visibility intervals,
6. call VLM only when OCR confidence is low or text layout semantics matter.

Sidecar output:

```json
{
  "onscreen_text": [
    {
      "text": "Quarterly revenue",
      "start_s": 42.0,
      "end_s": 55.5,
      "frames": [{"t": 42.0, "bbox": [100, 80, 900, 140]}],
      "ocr_confidence": 0.94
    }
  ]
}
```

## 9. Recommended end-to-end pipelines

### Image pipeline

**Build by default. Use APIs selectively.**

1. **Byte intake:** store raw bytes immutably, compute SHA-256, MIME sniff, EXIF extraction, dimensions, color profile, perceptual hash. Build.
2. **Cheap routing:** classify as natural image, screenshot, scan, chart, table, figure, document page, meme, handwriting, low-quality. Build with heuristics plus small local classifier if needed.
3. **OCR/layout:** run PaddleOCR/Surya/Tesseract or parser-specific OCR depending on class. Build.
4. **Locator-preserving text rendering:** emit Markdown-ish text plus JSON blocks with pixel bboxes. Build.
5. **Embeddings:** text embeddings for OCR/captions; single-vector multimodal embeddings for image/crops; optional late-interaction if document page. Build or API depending on privacy.
6. **VLM enrichment:** only for routed classes: charts, diagrams, low OCR confidence, screenshots needing UI semantics, natural images with user value. Self-host Qwen/InternVL for bulk; API frontier for high-value failures.
7. **Validation:** require "visible evidence only"; store uncertainty; run OCR-VLM consistency checks for text-heavy images.

Recommended default model choices:

- OCR/doc image: PaddleOCR-VL or Surya, with Docling/MinerU for document wrappers.
- Open VLM: Qwen2.5-VL-7B for bulk, 72B or InternVL large for harder images if GPU budget exists.
- API VLM: Claude Sonnet/Opus for dense screenshots and document QA; Gemini Flash-Lite/Flash for cheap broad labeling; GPT-5.x where existing OpenAI stack and quality tests justify it.
- Embeddings: text index plus Voyage multimodal/Cohere Embed v4/Jina/Nomic; ColQwen/ColNomic for visual pages.

### Video pipeline

**Build the deterministic scaffold. API-call only the condensed evidence.**

1. **Byte intake:** store raw video, probe with ffprobe, extract streams, duration, fps, resolution, codecs. Build.
2. **Audio extraction and VAD:** extract mono 16k or preserve channels; VAD segments. Build.
3. **ASR:** faster-whisper/WhisperX, Parakeet/Canary evaluation lane, or managed Deepgram/AssemblyAI for SLA. Build/API configurable.
4. **Alignment and diarization:** WhisperX alignment + pyannote, or vendor diarization. Build/API configurable.
5. **Shot detection:** PySceneDetect ContentDetector/AdaptiveDetector; TransNetV2 optional. Build.
6. **Keyframe extraction:** first/mid/last per shot, dedupe by perceptual hash, additional frames where OCR/text changes. Build.
7. **Frame OCR:** OCR sampled frames, merge visible text intervals. Build.
8. **VLM on keyframes/clips:** describe only representative frames, chart/slides/UI states, or low-confidence regions. Build/API configurable.
9. **Native video model escalation:** Gemini/Qwen video only for selected queries/assets requiring temporal reasoning beyond sampled evidence.
10. **Text rendering:** interleave transcript, speaker turns, on-screen text, scene summaries, and frame/shot locators into canonical conversion output.

Example rendered text skeleton:

```markdown
## Video: source.mp4

### Chapter 1 [00:00:00-00:03:12]
Speaker S1: ...
On-screen text [00:00:42-00:00:55]: "Quarterly revenue"
Visual note [shot_0007, frame 00:00:43.2]: Bar chart shows revenue increasing from Q1 to Q4. Uncertain exact values; see OCR/table crop.
```

## Build-vs-API calls

| Stage | Default | Why |
|---|---:|---|
| MIME/probe/hash/perceptual hash | Build | Cheap, deterministic, core provenance. |
| PDF/document parsing | Build Docling/MinerU | Privacy, replayability, locators, cost. |
| Hard document fallback | API Mistral OCR/Reducto/LlamaParse | Useful for burst capacity and difficult files; keep adapter versioned. |
| OCR for frames/images | Build PaddleOCR/Surya/Tesseract | High volume, cheap local compute, locators. |
| Image captions | Build open VLM for bulk; API for exceptions | Cost and privacy; frontier APIs for quality-critical cases. |
| Text embeddings | Build/API | Usually cheap either way; choose by existing infra. |
| Multimodal single-vector embeddings | API or self-host | Voyage is cheap per image; self-host for privacy. |
| Late-interaction visual retrieval | Build | Storage/query architecture is specialized and corpus-coupled. |
| ASR | Build by default; API for SLA | WhisperX/faster-whisper are mature; APIs buy ops. |
| Diarization | Build pyannote or API | Pyannote is viable; APIs often simpler. |
| Native long video understanding | API | Frontier capability; use sparingly. |

## Cost-ordered pipeline

| Order | Step | Typical unit cost | Build/API | Store output |
|---:|---|---:|---|---|
| 1 | Hash, metadata, MIME, ffprobe/pdfinfo, EXIF | CPU pennies per million small files | Build | raw metadata, hashes |
| 2 | Frame/page extraction, thumbnails, pHash/SSIM dedupe | CPU/GPU decode cost | Build | asset hashes, frame/page locators |
| 3 | Shot detection with PySceneDetect | CPU linear in frames; no model API | Build | shot start/end times |
| 4 | OCR/layout on images/pages/frames | local GPU/CPU; vendor OCR baseline Mistral $1-$2/1k pages | Build first, API fallback | text, bbox, confidence |
| 5 | ASR without diarization | WhisperX local GPU; API roughly AssemblyAI $0.15-$0.21/hr or Deepgram ~$0.29-$0.55/hr before add-ons depending mode/model | Build/API | transcript segments |
| 6 | Diarization/alignment | local pyannote GPU/CPU or Deepgram +$0.002/min | Build/API | speaker word/segment labels |
| 7 | Text embeddings | often <$0.20/MTok API or local batch | Build/API | vector ids, chunk refs |
| 8 | Single-vector multimodal embeddings | Voyage verified: $0.60/1k 1MP images; max $1.20/1k images | API/build | image/page/crop vectors |
| 9 | Late-interaction page embeddings | local GPU; raw vector storage inferred ~196-491 KB/page for 768 patches x 128-320 fp16 dims | Build | external multi-vector shard |
| 10 | Open VLM routed captions | GPU amortized; throughput depends heavily on model/resolution/batching; benchmark locally | Build | captions, structured descriptions, uncertainty |
| 11 | Frontier VLM image calls | Claude Sonnet 1MP input verified ~$3.89/1k images; with 250-400 output tokens inferred ~$7-$10/1k images | API | model artifacts |
| 12 | Native video model calls | Gemini verified ~100-300 input tokens/sec; inferred 60 min at Pro <=200k tier is ~$2.16 input at default resolution, cheaper on Flash-Lite/batch | API | chapter/event summaries with timestamps |

## Confidence and gaps

**High confidence:**

- Cheap-first cascades are mandatory. OCR/layout/ASR/shot detection should precede VLM calls.
- Docling and MinerU are the best local parser families to evaluate first for this architecture because both expose structured outputs and local execution; Docling has strong provenance mechanics in code, MinerU has stronger scale/router claims in its README.
- Visual document retrieval should be a parallel index. It is not a replacement for canonical text conversion.
- WhisperX-style ASR + alignment + diarization maps well to memory source locators.
- Native video models are valuable but should be used on condensed or selected evidence, not every frame by default.

**Medium confidence / needs benchmark:**

- Open VLM ranking changes quickly. Qwen2.5-VL, InternVL, Qwen3-VL, and newer variants must be benchmarked on the system's real images: charts, screenshots, scans, handwriting, and low-quality figures.
- MinerU's reported speed/accuracy improvements are from its README/changelog; validate on your hardware and corpus.
- ColQwen/ColNomic storage estimates are inferred from common patch-vector dimensions, not measured in this workspace. Measure actual serialized size and query latency with your vector backend.
- Surya/PaddleOCR-VL throughput and quality should be tested on your actual language/layout mix; public claims may not transfer.

**Unverified / do not assume:**

- Stable public per-page pricing for Reducto and LlamaParse from primary pricing pages. Treat them as configurable commercial adapters and record exact contract/pricing externally.
- OpenAI image-token cost for every GPT-5.x model from a stable formula. OpenAI documents token metering and pricing, but exact image accounting varies by model and should be measured from API usage logs.
- Cohere Embed v4 pay-as-you-go token/image unit price from the pages opened here. Dedicated Model Vault pricing is public; API unit pricing should be verified in account docs/contract before committing budgets.
- Any vendor benchmark that is not reproduced on your documents. Use a golden set with source-locator accuracy, table reconstruction, OCR WER/CER, chart QA, latency, and dollars per 1,000 pages/images/hours.
