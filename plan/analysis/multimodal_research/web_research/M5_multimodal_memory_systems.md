# M5 — How existing AI memory / RAG systems handle images & video

Research date: 2026-06-25. Question M5. Consuming system: **ugm**, a text-centric memory pipeline
(E evidence / K knowledge / P projections; Postgres is truth; claims grounded by char offsets; D-numbers
refer to `/Users/jpuc/code/moje/ultimate_memory/ugm_3/ugm/decisions.md`).

Evidence convention: **[V]** = verified against primary docs/source/paper I read; **[I]** = inferred or
synthesised; **[?]** = could not verify, flagged. Numbers without a citation are flagged as such.

---

## 1. Key findings (bullets)

- **Two camps, and the split is the whole story.** (a) *Reduce-to-text* systems (Mem0, Cognee, Graphiti,
  RAGFlow/DeepDoc, Docling, MinerU) run media through OCR / ASR / a vision-LLM and feed the resulting
  **text** into an otherwise text-native pipeline. (b) *Embed-the-pixels* systems (Morphik via ColPali,
  LlamaIndex via CLIP, late-interaction visual RAG) skip parsing and store **image/patch embeddings**,
  retrieving page-images and handing them to a VLM at answer time. A few research systems (WorldMM,
  M3-Agent, Video-RAG) do **both** — text for reasoning/extraction, embeddings for visual recall. [V]
- **The good systems keep a *locator*; the memory-framework systems mostly drop it.** Document parsers
  (RAGFlow/DeepDoc, Docling, MinerU) preserve **page number + bounding box** per chunk; ASR tooling
  (whisperX) preserves **word-level timecodes (<100 ms) + speaker**; video-RAG ties every snippet to
  **frames/timestamps/boxes**. But the *agent-memory* products (Mem0, Cognee, Graphiti) reduce an image to a
  caption-memory and **keep no region/timecode grounding** to the pixels. This is exactly the provenance
  ugm's claim/grounding model (D32) is built to preserve — the memory frameworks throw away the thing ugm
  treats as load-bearing. [V]
- **"Don't parse, just embed page images" (Morphik/ColPali) wins retrieval recall on visually-rich docs but
  cannot host a claim/relation/observation layer.** ColPali-style multivector page embeddings give strong
  document-retrieval numbers (ViDoRe nDCG@5 ~81–90) and Morphik reports big end-to-end accuracy wins, but the
  unit of memory is "a page image," not an atomic, temporally-validated, entity-anchored assertion. There is
  no supersession, no `evidence_count`, no entity identity. It is a *retrieval index*, not a knowledge
  substrate. [V]
- **Multi-store memory products get burned by exactly the desync ugm's D6 already forbids.** Mem0's
  vector+graph+KV split has documented consistency bugs (e.g. a `delete_all()` that reset the whole vector
  store). This is the documented failure class D6 ("validity has one home; the graph is a derived
  projection") was written against — and it gets *worse*, not better, if you bolt a second embedded modality
  onto graph nodes (the path Graphiti's open multimodal proposal takes). [V]
- **For ugm the entire multimodal extension lives in E0 `convert()` + the grounding locator, not in a new
  plane.** ugm already has the right bones: immutable raw bytes (D1/D37), a versioned `convert(bytes, mime,
  hints) -> {markdown, blocks[] with offsets}` (D38), a per-document structure tree (D39), char-offset
  grounding with verbatim-span + entailment (D32), and replay-from-storage for every non-deterministic stage
  (D7/D33). Steal the *mechanism* the good parsers use — emit text **plus** a generalized locator (char
  offset **or** page+bbox **or** time-interval+speaker) — and E1→E2→E3→K→P run unchanged. Avoid putting
  pixel embeddings on the P2 graph or into the rebuildable snapshot as authority (the D8 economics + D6
  one-home rules both say no). [I, grounded in D32/D38/D6/D8]

---

## 2. Evidence & detail (per system)

### 2.1 Mem0 — reduce-to-text caption-memory, no provenance
- **Mechanism [V]:** Mem0 "runs the image through a vision model that extracts text and key details," then
  stores those as **standard text memories** so "search, filters, and analytics continue to work." It is
  explicitly a caption/summary path — it "ultimately reduces visual inputs to captions and continues to
  operate purely in the textual space." No image embeddings are retained as a first-class modality.
- **Provenance/grounding [V]:** Mem0's own multimodal docs give **no** region/location grounding inside the
  image. Memory is the extracted note, detached from the pixels.
- **Limits/types [V]:** JPEG/JPG, PNG, WebP, GIF; images >20 MB rejected; base64 payloads recommended <5 MB.
  Vision model is pluggable ("Connect Vision Models"), specific model unspecified on that page.
- **Consistency wart [V]:** Mem0's vector+graph+KV architecture has documented desync bugs (e.g. issue where
  `delete_all()`/`vector_store.reset()` wiped the entire vector store rather than the targeted memories;
  "Openmemory changes memories before they hit the vector store"). Relevant because images become more
  memories in the same multi-store estate.
- Sources: https://docs.mem0.ai/open-source/features/multimodal-support ,
  https://github.com/mem0ai/mem0/issues/3322 , https://memo.d.foundation/breakdown/mem0
- **Gets right:** dead-simple, keeps one searchable substrate (text), links visual+textual turns in a
  conversation. **Gets wrong:** lossy (caption only, raw not re-derivable as a memory), **no provenance to a
  region**, multi-store consistency exposure.

### 2.2 Cognee — reduce-to-text into a shared knowledge graph
- **Mechanism [V]:** Cognee processes "images through vision models and audio through transcription
  pipelines, extracting entities and relationships from non-text sources and integrating them into the same
  knowledge graph." Built-in transcription for audio; routing via LiteLLM (incl. `hosted_vllm/` for local
  VLMs). 30+ connectors (PDF, Slack, Notion, Drive, images, audio, DBs).
- **Storage [V]:** local-first stack — **SQLite** (metadata), **LanceDB** (vector embeddings), **Kuzu**
  (knowledge graph). So media is reduced to text → entities/relationships → graph + vectors; the embeddings
  stored are of the *derived text/datapoints*, not raw pixels (per the case study / docs I read).
- **Provenance/grounding [?]:** Not documented in the sources I could read — no statement that a region or
  timecode is preserved back to the source media. Flagged.
- Sources: https://github.com/topoteretes/cognee , https://www.lancedb.com/blog/case-study-cognee ,
  https://docs.cognee.ai/setup-configuration/llm-providers , https://vectorize.io/articles/mem0-vs-cognee
- **Gets right:** one knowledge graph across modalities, ontology generation, entity/relationship extraction
  (architecturally the closest to ugm's E2/E3). **Gets wrong:** (apparently) drops media-region provenance;
  the same LLM-derived facts live in *both* Kuzu and LanceDB as authority — the drift surface ugm avoids by
  making the graph a pure projection (D6).

### 2.3 Graphiti / Zep — text-only today; an open "do-both" proposal
- **Mechanism [V]:** Graphiti currently supports **text and JSON episodes only**; no native image/audio/video
  ingestion. Multimodal is an **open feature request** (issue #1327).
- **Proposed design [V]:** a two-layer plan — Layer 1: pass the raw asset to a **vision-capable LLM → struct­
  ured text description** for entity/edge extraction ("LLM graph extraction inherently requires language");
  Layer 2: if the configured embedder is multimodal (e.g. Gemini), store a **native visual/audio vector on
  the node** "alongside or instead of the text-derived embedding," with a `asset_id` pointer to object
  storage. Text-only embedders degrade gracefully to embedding the description.
- **Provenance/grounding [V]:** the proposal stores only an `asset_id` pointer; **no region/timecode**
  grounding is specified. No maintainer response visible.
- Sources: https://github.com/getzep/graphiti/issues/1327 ,
  https://help.getzep.com/graphiti/getting-started/welcome
- **Relevance to ugm:** ugm copied Graphiti's *search* stack and edge-invalidation idea (D3/D9) but
  deliberately diverged on authority (D6). Note the proposal puts a **multimodal embedding directly on a
  graph node** — precisely what ugm's D8 (no vectors in the graph snapshot) and D18/D44 (a value/embedding is
  not a node) forbid. This is a concrete "avoid" example from a system ugm otherwise respects.

### 2.4 Morphik + ColPali — embed-the-pixels, page-image retrieval
- **Mechanism [V]:** "Document → Image → Understanding." Each page is rendered to a high-res image; **ColPali**
  (ViT SigLIP-So400m patches → PaliGemma-3B → linear projection → ColBERT-style **multivector** embedding)
  embeds patches; retrieval is **late interaction (MaxSim)**; at answer time the VLM **sees the actual page
  image**, so it reasons over charts/arrows/colours. Morphik also keeps OCR alongside.
- **Speed/scale engineering [V]:** Morphik applies **MUVERA** (fixed-dimensional encoding to reduce
  multivector search to single-vector) for ~30 ms latency vs 3–4 s naïve; plus binary quantization + Hamming
  distance.
- **Numbers [V, vendor benchmark — treat as vendor-reported]:** ViDoRe **81.3 nDCG@5** vs 67.0 for traditional
  parsing; on Morphik's *own* 45-question financial benchmark: **Morphik 95.56%**, end-to-end competitors
  ~67%, optimized LangChain 72%, OpenAI file search 13.33%. (ColVision leaderboard, independently: ColPali
  v1.3 84.8, ColQwen2-v1.0 89.3, ColQwen2.5-v0.2 89.4, colqwen3 variants ~90+ on ViDoRe. [V])
- **Provenance/grounding [V/I]:** retrieval is **page-grained** (you get the page image back). Finer grounding
  (which patch answered which query token) is *possible* — ColPali ships **interpretability similarity maps**
  over image patches — but this is a debugging visualization, **not** a stored region-provenance per fact. So:
  page-level provenance yes; region-level fact provenance no (not productized). [I]
- **Cost/storage caveats [V]:** ColPali ≈ **1,024 vectors/page** (32×32 patches), 128-dim, fp16 ≈ **256 KB
  per page**; ColQwen ≈ 700–768 vectors/page. HNSW build cost grows **~quadratically** with vectors/page;
  late-interaction scoring is Q×D×d multiply-adds (e.g. ~1.3×10¹⁰ MACs/query at 10k pages). Mitigations:
  **hierarchical token pooling** (pool_factor 3 → −66.7% vectors, **97.8% of performance retained**),
  mean-pool-then-rerank, binary quantization.
- Sources: https://www.morphik.ai/blog/stop-parsing-docs (→ dev.morphik.ai) ,
  https://www.morphik.ai/docs/concepts/colpali , https://arxiv.org/abs/2407.01449 (ColPali paper) ,
  ColPali repo README (`_additional_context/colpali/README.md`) ,
  https://qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/ ,
  https://arxiv.org/abs/2506.21601 (Hierarchical Patch Compression)
- **Gets right:** no brittle parse step; preserves visual semantics (charts/layout) end-to-end; strong
  recall on visually-rich docs. **Gets wrong (for a *memory* system):** the unit is a page image, not an
  assertion — **no atomic claims, no entities, no temporal validity/supersession, no evidence collapse, no
  region-grained fact provenance**; storage/compute is heavy at millions of docs.

### 2.5 LlamaIndex multimodal — dual stores, CLIP joint space
- **Mechanism [V]:** `MultiModalVectorIndex` keeps **two vector stores** — images (CLIP joint text/image
  space) and text (sbert/ada) — plus a docstore; image nodes stored as **base64 or path** with their
  embeddings; at query time it runs **two similarity searches** (images + text) and feeds both to a multimodal
  LLM. Recipes exist for image→image (CLIP) + GPT-4V reasoning, and video (LanceDB).
- **Provenance/grounding [I]:** provenance is whatever the **node metadata** carries (source pointer / path);
  no inherent region or timecode grounding beyond "which node." The framework gives you the slots; it does not
  enforce region-level grounding.
- Sources: https://www.llamaindex.ai/blog/multi-modal-rag-621de7525fea ,
  https://developers.llamaindex.ai/python/examples/multi_modal/image_to_image_retrieval/ ,
  https://www.llamaindex.ai/blog/multimodal-rag-for-advanced-video-processing-with-llamaindex-lancedb-33be4804822e
- **Gets right:** clean separation of image vs text embedding spaces (don't force CLIP on text); composable.
  **Gets wrong:** CLIP single-vector joint space is weak on document images/charts (trained on natural images
  + short captions); coarse node-level provenance; it is a toolkit, not an opinionated memory model.

### 2.6 RAGFlow / DeepDoc — reduce-to-text **but keep the bounding box**
- **Mechanism [V]:** DeepDoc (default parser ≥ v0.17) does **OCR + Document Layout Recognition** (10 component
  classes incl. text/title/figure/figure-caption/table/header/footer/reference/equation) **+ Table Structure
  Recognition**, then **reassembles into LLM-readable sentences**. Figures stored with "caption and text in
  the figures"; tables stored as a cropped image **plus** a natural-language rendering. Alternative parsers:
  MinerU, Docling.
- **Provenance/grounding [V]:** PDF parser output explicitly includes **"text chunks with their own positions
  in PDF (page number and rectangular positions)"** — i.e. page + bbox per chunk, traceable to source.
- Sources: https://github.com/infiniflow/ragflow/blob/main/deepdoc/README.md ,
  https://milvus.io/ai-quick-reference/how-does-ragflow-perform-ocr-on-scanned-documents
- **Gets right:** the model ugm should copy — **convert media to text yet retain a spatial locator**.
  **Gets wrong:** figure *semantics* still bottleneck on OCR/caption quality (a chart's trend may not survive
  to text unless a VLM describes it); reduction is one-way at ingest.

### 2.7 Docling / MinerU (the converters ugm already eyes for D38)
- **Docling [V]:** VLM/layout pipeline emits a typed `DoclingDocument` with `PictureItem`, `BoundingBox`, and
  **provenance (page numbers, origin)** for all items; supports **picture classification** and **picture
  enrichment** (call a remote VLM to *describe/annotate* a figure → text). Figure images extracted only if the
  model emits `PictureItem` references.
- Sources: https://docling-project.github.io/docling/reference/docling_document/ ,
  https://docling-project.github.io/docling/examples/develop_picture_enrichment/ ,
  https://arxiv.org/html/2501.17887v1 (Docling paper)
- **Relevance:** Docling is a concrete implementation of exactly the E0 contract ugm wants — text + bbox +
  provenance + optional VLM figure caption — and it already vends `blocks[] with offsets`-shaped output (D38).

### 2.8 Audio/video tooling (the locator-preserving mechanisms ugm can reuse)
- **whisperX [V]:** 3-stage pipeline — faster-whisper transcribe → **wav2vec2 forced alignment** for
  **word-level timestamps <100 ms** → **pyannote diarization** assigning each aligned word to a **speaker
  label**. So ASR yields verbatim text **with per-word timecode + speaker** — a perfect E0 "block with
  offsets" where the offset is a **time interval** and an extra **speaker** field.
  Source: https://deepwiki.com/m-bain/whisperX/3.3-forced-alignment-system , whisperX repo.
- **Video-RAG (NeurIPS 2025) [V]:** builds **OCR + ASR + object-detection** auxiliary text, each snippet
  **tied to frames/timestamps/boxes**; keyframe gating to save compute; stack = EasyOCR, Whisper, CLIP, APE
  (open-vocab detector), Contriever, FAISS. Demonstrates the "convert video → timecoded text + light visual
  index" pattern.
  Sources: https://video-rag.github.io/ , https://arxiv.org/abs/2411.13093
- **WorldMM (2026) / M3-Agent (ByteDance, 2025) [V]:** entity-centric multimodal memory; WorldMM splits
  **Episodic** (textual event graphs) + **Semantic** (knowledge graph) + **Visual memory** = *hybrid* (feature
  embeddings for semantic search **and** **timestamped frames for precise visual grounding**). Confirms the
  research consensus: **text/graph for reasoning + a separate visual index for recall, with timecode as the
  join key.**
  Sources: https://worldmm.github.io/ , https://m3-agent.github.io/ , https://arxiv.org/abs/2508.09736
- **PySceneDetect [V, tool]:** content/threshold scene-cut detection → gives the **temporal segmentation**
  (scene boundaries) that is the video analog of PageIndex sections.

### Summary table

| System | Reduce→text | Pixel/patch embeddings | Region/timecode provenance | Has claims/entities/temporal supersession |
|---|---|---|---|---|
| Mem0 | Yes (captions) | No | **No** | partial (graph add-on), no media provenance |
| Cognee | Yes | text/datapoint vectors | **Not documented [?]** | Yes (KG), no media provenance |
| Graphiti/Zep | proposed | proposed (on node) | **No** (asset_id only) | Yes (bi-temporal edges), text-only today |
| Morphik/ColPali | optional OCR | **Yes (multivector page)** | page-level only | **No** |
| LlamaIndex | optional | CLIP single-vector | node-level only | No (toolkit) |
| RAGFlow/DeepDoc | **Yes** | no (table crop kept) | **Yes (page+bbox)** | No (retrieval) |
| Docling/MinerU | **Yes** (+VLM caption) | no | **Yes (page+bbox)** | No (parser) |
| whisperX | **Yes (verbatim ASR)** | no | **Yes (word timecode+speaker)** | No (ASR) |
| Video-RAG / WorldMM / M3-Agent | **Yes** | Yes (visual store) | **Yes (frame/timecode/box)** | Yes (graphs), research-grade |

---

## 3. Confidence & gaps

- **High confidence [V]:** the reduce-to-text vs embed-pixels taxonomy; Mem0 caption-only + no provenence +
  20 MB limit; Graphiti text-only-today + the #1327 two-layer proposal; Morphik = ColPali page images + MUVERA
  + the ViDoRe 81.3 number; ColPali storage/compute facts (≈256 KB/page, ~1024 vectors, quadratic HNSW, token
  pooling 97.8%@−66.7%); RAGFlow/Docling page+bbox provenance; whisperX <100 ms word timecodes + diarization.
- **Vendor-reported, not independent [flag]:** Morphik's 95.56% on its *own* 45-question financial benchmark —
  treat as marketing, not a neutral result. ViDoRe leaderboard scores are independent and reproducible.
- **Gaps / unverified [?]:** (1) Whether Cognee preserves any media-region/timecode provenance — not found in
  the docs I read; likely not, but flagged. (2) Exact production model IDs behind Mem0/Cognee "vision models"
  (pluggable; unspecified). (3) Whether any surveyed *memory* product carries region-grained provenance down
  to an individual stored fact — I found none that does (parsers do; memory frameworks don't). (4) I did not
  price ASR/VLM throughput precisely; whisperX is GPU-batched and commonly faster-than-real-time, but I give
  no hard $/hour here — flag as to-be-measured (consistent with ugm's "numbers are starting points").

---

## 4. Recommendation for ugm — STEAL vs AVOID (tied to decisions)

**Framing: ugm needs almost no new architecture.** Multimodality in ugm is an **E0 `convert()` + structure +
grounding-locator** extension. The downstream planes (E1 chunk, E2 Claimify+grounding, E3 relations/
observations, supersession, K, P1/P2/P3) operate on *text + a provenance locator* and should not change. The
text-centric design is the right one; the survey shows the systems that keep provenance (parsers, ASR) are
the ones to imitate, and they keep it *exactly at the convert boundary*.

### STEAL

1. **Generalize the grounding locator (the single most important change), refining D32/D38.** Today a block /
   `source_span` is `{char_start, char_end}` into Markdown. Make the locator a tagged union:
   `{text: char_offsets}` | `{image: page, bbox}` | `{av: t_start, t_end, speaker?}`. RAGFlow/DeepDoc and
   Docling prove page+bbox is cheap to carry; whisperX proves word-level timecode+speaker is cheap to carry.
   This preserves D32's whole apparatus — a claim still has a verbatim `source_span` **and** now a media
   locator, so "where in the source" survives for pixels and audio, not just characters. This is the property
   every memory framework (Mem0/Cognee/Graphiti) *drops* and ugm should keep. (Refines D32 grounding,
   D38 `blocks[]`, D37 section index.)

2. **Make `convert()` modality-aware, staying inside D38's versioned-router pattern.** Add routes:
   - *Scanned/figure-bearing PDF & standalone images* → OCR + layout (Mistral OCR / **Docling** / MinerU,
     which ugm already vendors) emitting Markdown + page+bbox blocks; optionally a **VLM figure-description**
     pass (Docling "picture enrichment") that emits a caption block anchored to the figure bbox, `role=figure`.
   - *Audio* → **whisperX** → verbatim transcript Markdown + per-segment `{t_start, t_end, speaker}` blocks.
   - *Video* → **PySceneDetect** scene cuts (temporal structure) + whisperX ASR + per-scene keyframe VLM
     caption + OCR-on-frame; each block timecoded. The scene tree is the **PageIndex analog** for video
     (D39 structure sub-worker; extend the `role` enum with `scene, frame_caption, transcript, ocr_text`).
   - Keep raw bytes immutable in the raw bucket (D1/D37); version every model step (`asr_version`,
     `vlm_caption_version`, `scene_detect_version`, `ocr_version`) and **replay from stored output on rebuild**
     — identical discipline to `converter_version`/D33. (Realizes D7/D33/D38 for media.)

3. **Route the two kinds of media-text correctly through D32's acceptance layers — this is the crux.**
   - **Verbatim media-text (OCR, ASR)** is *real source text*: it satisfies D32 layer-1 (anchor) and layer-2
     (window-membership) **as written** — the spoken/printed words verbatim-exist in the transcript/OCR
     output, with a timecode/bbox attached. ASR maps beautifully onto D32's existing *"X said Y entails
     'X said Y', not 'Y'"* rule and diarization gives the speaker entity. Treat OCR/ASR text as a first-class
     source body.
   - **VLM-generated descriptions (figure/scene captions)** are *model assertions about a region*, **not**
     verbatim source — epistemically identical to a decontextualized rewrite. So they enter as
     `added_context[]` whose named source is e.g. `vlm_caption(figure 3.2 @ bbox)`, grounded by D32 layer-3
     (entailment self-verdict) + layer-4 (sampled audit) + the bbox provenance, **never** asserted as a
     verbatim span. Stamp their origin so confidence math never treats a model caption as independent
     corroboration (the D42 origin instinct, applied to model-derived media text). This keeps the
     hallucination surface of vision models *quarantined* exactly where ugm already quarantines rewrites.

4. **Speaker diarization → entities; timecodes → claim validity & observations.** A diarized speaker is an
   entity mention (T0–T4 resolution, D17). A claim's spoken-at timecode feeds D41's immutable asserted-validity
   interval (or just the block locator). A measurement read off a chart ("FY2023 revenue $5M") becomes an
   **observation** (D43) anchored to the entity, with the figure bbox / video timecode as evidence provenance —
   no new machinery, the value lives in the NL `statement` as D43 already specifies.

5. **(Optional, measured) a visual recall channel as a P1 projection — never canonical.** For deployments with
   genuinely visually-rich corpora (charts/scanned forms where text reduction loses signal), add a **ColPali/
   ColQwen multivector page-image index as a separate Lance table**, used only as an extra **retrieval channel
   fused by RRF** (D9) to *find the page*, after which the answer is still grounded in text claims. Borrow the
   survival kit: **token pooling** (−66.7% vectors @ 97.8% perf), mean-pool-then-rerank, binary quantization.
   This is the WorldMM/M3-Agent pattern (text for reasoning, visual store for recall). It is a **P-plane
   projection** (derived, rebuildable, no authority), consistent with P1.

### AVOID

1. **Do not put media embeddings on the P2 graph or inside the rebuildable graph snapshot.** Graphiti's
   open proposal stores a multimodal vector *on the node*; ugm's D8 (no vectors in the snapshot) + D18/D44
   (a value/embedding is not a node, a REL endpoint must be a node) + the D8 snapshot economics (heavy
   per-rebuild index build) all forbid it. Any pixel embedding is P1/Lance only.

2. **Do not adopt the Morphik "page image is the memory" model as the canonical layer.** It has no claims, no
   entities, no temporal supersession, no `evidence_count`, no region-grained fact provenance — it is
   structurally incompatible with E2/E3/observations and ugm's "facts not files" core. Use it (if at all) only
   as the optional recall channel in STEAL-5. Reducing-to-text remains ugm's canonical path; ColPali is a
   complement, not a replacement.

3. **Do not copy Mem0/Cognee's "caption and forget the locator."** Caption-only memory is information-lossy
   *and* unauditable: you cannot re-extract on a better model, cannot show *where* in the image/video a fact
   came from, and cannot temporally place it. ugm's immutable-raw + versioned-convert + replay-from-storage
   (D7/D33/D37) plus the generalized locator (STEAL-1) is strictly better and already most of the way there.

4. **Do not let media create a second validity/authority home.** Multi-store memory products (Mem0's
   vector+graph+KV) demonstrate the desync class D6 was written against; adding a modality multiplies it.
   Media-derived facts flow through claims → relations/observations like any other evidence; validity stays
   relation-only (D3/D6); media embeddings stay derived projections (P1).

5. **Do not treat VLM/OCR/ASR output as deterministic or as verbatim ground truth.** It is non-deterministic
   model output → must be versioned + replayed (D7/D33), and VLM captions specifically must be flagged as
   model assertions (STEAL-3), not verbatim spans. CLIP single-vector joint-space embeddings (the LlamaIndex
   default) are additionally weak for document/chart images — avoid as a primary visual index; prefer
   late-interaction (ColPali/ColQwen) if a visual channel is built at all.

**Net:** the survey validates ugm's text-centric, provenance-first, projection-only-for-vectors stance.
Multimodality is an E0-convert problem, solved by stealing the *locator-preserving* mechanics of the document
parsers (page+bbox) and ASR tooling (timecode+speaker), routing verbatim media-text through D32 unchanged and
quarantining VLM descriptions as model assertions — with an optional ColPali recall channel as a P1 projection,
measured before it is built (CLAUDE.md Rule 2: full-scope design, numbers are starting points).
