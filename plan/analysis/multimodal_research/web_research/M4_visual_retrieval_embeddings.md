# M4 — Visual Document Retrieval + Multimodal Embeddings (2026)

Scope: (1) late-interaction visual retrieval (ColPali / ColQwen2 / ColNomic / DSE) — when it beats
OCR-then-embed-text, and its storage/latency cost; (2) single-vector multimodal embeddings (Voyage
multimodal-3, Cohere Embed v4, CLIP/SigLIP/Jina-CLIP/nomic-embed-vision); (3) what goes in LanceDB,
whether LanceDB does multi-vector late interaction; (4) a concrete recommendation for a ugm P1
multimodal sub-index, tied to D6 / D8 / D9 / D7.

Verification tags: **[V]** = verified from a primary/vendor source; **[I]** = inferred or
synthesized; **[?]** = could not verify / flagged.

---

## 1) Key findings (bullets)

- **Late interaction (ColPali-family) embeds the page *image* and skips OCR, and it wins decisively
  on visually-rich pages.** ColPali reported nDCG@5 = **81.3** on ViDoRe v1 vs **67.0** for the best
  OCR+captioning+text-embedding pipeline; the gap is largest on tables/charts/infographics, and it
  still wins on text-centric pages. **[V]** The current ViDoRe-v1 leaderboard top is ColQwen-family at
  **~89–91** nDCG@5. **[V]**
- **The cost is multi-vector storage and rank-time compute.** A ColPali page = **~1,030 vectors ×
  128-dim** (32×32 = 1,024 patches + ~6 instruction tokens). Float32 ≈ **~528 KB/page**; binary
  quantization → **~16 KB/page (~32×)**; hierarchical token pooling (pool factor 3) cuts vectors
  ~67% while keeping **97.8%** of accuracy; combined compression reaches up to **32×** with **<2%**
  nDCG drop. **[V]** Retrieval must be **two-stage** (ANN candidate-gen → MaxSim rerank); MaxSim is
  O(query_tokens × page_patches) per candidate.
- **Single-vector multimodal embeddings (Voyage multimodal-3, Cohere Embed v4) are the
  scale-affordable default.** One 1,024-dim vector per page/image (≈4 KB fp32, ≈1 KB at 256-dim
  Matryoshka) goes straight into an ordinary HNSW/IVF index, enables **cross-modal** text↔image
  search, and beats CLIP by large margins on document-screenshot and table/figure retrieval
  (Voyage: **+26.5%** doc-screenshot, **+41.4%** table/figure vs CLIP-L). **[V]** They trade ~a few
  points of top-end accuracy for ~30–100× less storage and far lower query latency vs late
  interaction.
- **LanceDB natively supports multi-vector late interaction.** A column can hold a *list of vectors*
  per row; LanceDB computes **MaxSim** natively, builds an **IVF_PQ** index over the multi-vectors,
  supports **float16/32/64**, but **only the cosine metric** for multivector. So both the
  single-vector and the ColPali-style sub-index can live in the *same* Lance estate ugm already
  commits to (D8). **[V]**
- **Recommendation for ugm's P1 multimodal sub-index: a two-tier, cheap-first Lance projection.**
  Tier-A (always-on): one **single-vector multimodal embedding per page-image / keyframe /
  video-segment** (Cohere Embed v4 or Voyage multimodal-3), stored as a normal Lance vector column
  with scalar filters and a Matryoshka-truncated coarse index — this is the millions-of-docs
  baseline and gives cross-modal retrieval. Tier-B (selective): a **ColQwen2.5 / ColNomic
  multi-vector late-interaction** column, materialized **only for pages flagged visually-rich**
  (tables/charts/figures/scanned), stored **binary-quantized + token-pooled**, queried two-stage.
  Both are derived, rebuildable-from-artifacts projections holding **no authority** (D6), vectors in
  **Lance not the graph** (D8), versioned and replayed on rebuild (D7). Visual retrieval surfaces a
  *page/timecode locator*, never a belief — truth stays in text claims (D32).

---

## 2) Evidence & detail

### 2.1 Late-interaction visual retrieval — what it is and when it beats OCR-then-embed-text

**Mechanism.** ColPali (Faysse et al., 2024, arXiv:2407.01449) feeds a document *page image* through
a VLM (PaliGemma-3B in the original; Qwen2/Qwen2.5-VL in ColQwen) and projects each ViT output patch
to a small 128-dim vector, producing a **multi-vector** page representation in the **ColBERT
"late interaction"** style. Query text is likewise encoded to per-token vectors. Relevance is
**MaxSim**: for each query token, take the max cosine over all page patches, then sum across query
tokens. This keeps patch-level granularity (a query term can "land on" the exact table cell / chart
region) instead of pooling the page to one vector. It removes the OCR + layout-analysis + captioning
pipeline entirely — "screenshots are all you need."
[colpali README; arXiv:2407.01449] [V]
(https://arxiv.org/abs/2407.01449)

**When it beats OCR-then-embed-text (verified):**
- **Visually-rich pages**: tables, charts, infographics, figures, slides, complex multi-column
  layout, scanned pages. ColPali's reported advantage is *largest* on InfographicVQA / ArxivQA /
  TabFQuAD-type tasks, but it also wins on text-centric pages "across all evaluated domains and
  languages." nDCG@5 **81.3** (ColPali) vs **67.0** (best OCR+caption+text-embed); vs **65–75** for
  BM25 / BGE-M3 text baselines. **[V]**
  (https://arxiv.org/html/2407.01449v5 ; https://huggingface.co/blog/manu/colpali)
- **When OCR is the bottleneck**: scanned docs, handwriting, dense layout, non-Latin scripts — OCR
  errors propagate into the text index; the page-image path avoids that. Industry framing: "~80% of
  enterprise PDFs contain at least one table, chart, or complex layout element," where OCR-based RAG
  "starts with corrupted or structurally degraded input." **[V/industry-claim]**
  (https://www.spheron.network/blog/colpali-multimodal-document-rag-gpu-cloud/)
- **Queries about visual/spatial structure** ("the slide with the revenue waterfall chart") where the
  answer is a layout, not a sentence.

**When OCR-then-embed-text is competitive / preferable (verified-leaning):** clean *digital* text
documents where OCR/text-extraction is near-perfect — there a single text embedding is cheaper, lower
latency, and roughly as good; the reproducibility study notes "traditional dense retrieval remains
competitive… particularly when documents are text-heavy without complex visual elements."
(arXiv:2505.07730, "Reproducibility, Replicability, and Insights into Visual Document Retrieval with
Late Interaction") [V]
**ugm relevance:** D38 already routes *digital* PDFs to text-extraction and only scanned/complex PDFs
+ images to OCR. So ugm's text pipeline is already strong exactly where OCR-then-text is competitive; the
incremental value of visual retrieval concentrates on the scanned/complex/image-heavy slice — which is
also where the cost cascade should gate the expensive multi-vector path.

**Model landscape & ViDoRe scores (from colpali README leaderboard column = ViDoRe v1, in-domain):**
[V]

| Model | Backbone | ViDoRe v1 nDCG@5 | License | Notes |
|---|---|---|---|---|
| colpali-v1.3 | PaliGemma-3B | 84.8 | Gemma | original family |
| colqwen2-v1.0 | Qwen2-VL-2B | 89.3 | Apache-2.0 | dynamic resolution |
| colqwen2.5-v0.2 | Qwen2.5-VL-3B | 89.4 | Apache-2.0 | dynamic resolution |
| colSmol-256M / 500M | SmolVLM | 80.1 / 82.3 | Apache-2.0 | tiny, edge-friendly |
| tomoro-colqwen3-embed-4b | Qwen3-VL | 90.6 | Apache-2.0 | 320-dim multi-vectors |
| colqwen3.5-4.5B-v3 | Qwen3.5-4B | 90.9 | Apache-2.0 | 320-dim multi-vectors |

**ViDoRe v2 (out-of-domain, much harder; scores are far lower):** ColNomic Embed Multimodal 7B =
**62.7** nDCG@5 (+2.8 over prior SOTA at release). Nomic ships **single-vector** (nomic-embed-
multimodal 3B/7B) and **multi-vector late-interaction** (ColNomic 3B/7B) variants from one family.
Newer top late-interaction entrants (e.g., **Nemotron ColEmbed V2**, arXiv:2602.03992) push v2 higher.
[V] (https://www.nomic.ai/news/nomic-embed-multimodal ; https://huggingface.co/blog/manu/vidore-v2)
**Caveat:** ViDoRe v1 numbers are in-domain and saturated near 90; v2 is the better signal for OOD
generalization, and the absolute scores (~60s) show this is still a hard problem on novel corpora.
**[I]**

**DSE (Document Screenshot Embedding)** is the *single-vector* page-image approach: same "embed the
screenshot, skip OCR" idea, but a bi-encoder pools all patches to **one** vector per page. It is the
bridge between ColPali and CLIP-style models: cheaper than ColPali, richer than CLIP for documents,
but less precise than ColPali's multi-vector. Reported storage: **DSE ≈ 6 KB/doc** vs single-vector
text BGE ≈ 3 KB vs **ColPali ≈ 256 KB/doc** (the 256 KB figure assumes fewer/quantized patches; see
the 528 KB fp32 figure below). One benchmark cites DSE online latency **0.115 s** at **0.235 FLOPs**
vs ColQwen2.5 at **~2006 FLOPs** — i.e., single-vector is orders-of-magnitude cheaper at query time.
[V, single source — treat FLOPs ratio as indicative] (https://zilliz.com/blog/colpali-…)

### 2.2 Storage & latency cost of multi-vector late interaction (verified, Vespa)

From Vespa's "Scaling ColPali to billions of PDFs" [V]
(https://blog.vespa.ai/scaling-colpali-to-billions/):
- **Vectors/page:** ~**1,030** (1,024 patches + ~6 instruction tokens), **128-dim** each.
- **Float32 storage:** 1,030 × 128 × 4 B ≈ **~528 KB/page**.
- **Binary quantization:** pack 128-dim → 16 bytes/vector → **~16 KB/page (~32× smaller)**.
- **Hamming MaxSim ≈ 3.5× faster** than float dot product; ~200M 128-bit hamming distances/s/core
  → ~100 ms over 1,000 pages × 20 query vectors.
- **Accuracy (DocVQA nDCG@5):** float-float **52.4**, binary-binary **49.5**, **binary + float
  rerank 51.6** — "small price for the efficiency gain."
- **Two-phase retrieval:** ANN candidate-gen → MaxSim rerank, to avoid moving large vector blobs.

**Compression to fewer vectors/page (verified):**
- **Hierarchical token pooling, pool factor 3:** **−66.7% vectors**, retains **97.8%** of accuracy.
  [V] (search-confirmed; method from ViDoRe authors / PyLate)
- **Hierarchical Patch Compression for ColPali** (arXiv:2506.21601): K-Means quantization +
  attention-guided dynamic pruning → **up to 32× compression, ~50% latency reduction, <2% nDCG@10
  drop.** [V]

**Bottom line on cost:** A naive ColPali index is ~130× larger than a single-vector index per page
(528 KB vs ~4 KB). With binary-quant + pool-factor-3 you land near **~5–6 KB/page**, i.e.
*single-vector-comparable storage* but with rank-time MaxSim compute and mandatory two-stage
retrieval. That is the engineering price of the accuracy bump on visually-rich pages.

### 2.3 Single-vector multimodal embeddings (cross-modal)

| Model | Out dim | Single/multi | Cross-modal | Pricing (verified-ish) | Notes |
|---|---|---|---|---|---|
| **Voyage multimodal-3** | **1024** | single | text↔image, interleaved | ~$0.12 / 1M tokens; image billed by pixels (50K–2M px) **[V dim/ctx; I price]** | one unified transformer encoder (no modality gap); 32K ctx; +26.5% doc-screenshot, +41.4% table/figure vs CLIP-L **[V]** |
| **Cohere Embed v4** | Matryoshka **256/512/1024/1536** | single | text↔image, PDF screenshots | **$0.12 / 1M text**, **$0.47 / 1M image** tokens **[V]** | 128K ctx; int8/uint8/binary/ubinary output; image ≤5 MB; "production multimodal" **[V]** |
| **Jina-CLIP v2** | **1024** (Matryoshka→256 keeps >99%) | single | text↔image, multilingual | open weights (self-host) | 865M params; CLIP-style dual tower **[V]** |
| **SigLIP 2 (SO400M)** | **1152** | single | text↔image | open weights | strongest *open* image-text similarity model class as of 2026 **[V/claim]** |
| **nomic-embed-vision (v1.5)** | **768** **[I]** | single | text↔image (shares latent space w/ nomic-embed-text-v1.5) | open weights | LiT-style: frozen text tower, tuned vision tower; unified text+image latent space **[V mechanism; I dim]** |
| **OpenAI CLIP / classic CLIP** | 512–768 | single | text↔image | open weights | baseline; suffers **modality gap** (text aligns to text, image to image) — weaker for true cross-modal doc search **[V]** |

Sources: https://blog.voyageai.com/2024/11/12/voyage-multimodal-3/ ;
https://www.mongodb.com/docs/voyageai/models/multimodal-embeddings/ (dim=1024, 32K ctx, single-vec) ;
https://docs.cohere.com/changelog/embed-multimodal-v4 ;
https://jina.ai/news/jina-clip-v2-multilingual-multimodal-embeddings-for-text-and-images/ ;
https://arxiv.org/html/2406.18587v1 (nomic-embed-vision LiT). All [V] except dims marked [I].

**Why single-vector multimodal > classic CLIP for documents:** CLIP's separate text/image towers
create a **modality gap** — vectors cluster by *modality*, hurting true cross-modal ranking. Voyage,
Cohere v4, and (architecturally) DSE/ColPali process text+image through one backbone, which is why
they crush CLIP on document-screenshot and table/figure retrieval. **[V]** For ugm's "find the photo
that matches this text" / "find the slide about X" use cases, a unified single-vector model (Voyage
multimodal-3 or Cohere Embed v4) is the right cross-modal primitive.

### 2.4 LanceDB: does it do multi-vector late interaction?

**Yes — natively.** From LanceDB docs [V]
(https://docs.lancedb.com/search/multivector-search ;
https://lancedb.com/docs/concepts/search/multivector-search/):
- A column can store **multiple vectors per row** (a *list of lists of float*).
- **MaxSim late interaction is computed natively** ("max similarity between each query embedding and
  all document embeddings, summed").
- **Index: IVF_PQ**; LanceDB warns indexing "matters more for multivector tables than single-vector"
  (un-indexed = brute force that scales with rows × vectors-per-row).
- **Value types: float16 / float32 / float64.**
- **Only the cosine metric** is supported for multivector (note: binary/hamming quantization à la
  Vespa is **not** a first-class multivector metric in Lance — flag for the two-stage design;
  pooling to fewer fp16 vectors is the lever available in Lance today). **[V]**
- LanceDB's own blog ("Late Interaction & Efficient Multi-modal Retrievers Need More Than a Vector
  Index") cautions that at scale a single ANN index is insufficient — you want **two-stage**
  (coarse retrieve → MaxSim rerank), matching the Vespa pattern. **[V]**

**Implication for ugm:** Both proposed tiers fit one Lance estate. Single-vector page/keyframe
embeddings are an ordinary Lance vector column (HNSW/IVF + scalar filters + BM25 on any OCR/caption
text — exactly the D9 "Lance = entry" pattern). The ColPali-style column is a Lance **multivector**
column with native MaxSim. No second store, no new engine — consistent with D8's "one vector estate,
one embedding budget."

### 2.5 ugm decision anchors (read from decisions.md)

- **D6** — graph (P2/LadybugDB) holds **no embeddings**, is a derived projection, deletable/
  rebuildable. Any visual vectors must NOT go there.
- **D8** — relation/observation embeddings live in **LanceDB**, not the graph; "Lance exists
  regardless for L1 chunks and L2 claims; one vector estate." A multimodal sub-index is the natural
  extension of this estate.
- **D9** — retrieval is through projections; "Lance = entry (semantic + BM25 + scalar-filtered)" then
  ID-keyed hop to canonical storage. The multimodal sub-index is an *entry channel*, not authority.
- **P1 = Lance search indexes**, a Projection-plane artifact: derived, no authority, rebuilt on
  schedule, immutable snapshots (README three-plane model).
- **D7 / D33** — everything model-derived is **versioned and replayed-from-storage** on rebuild. Image
  embeddings need an `embedder_version` (mirroring `converter_version`) and the page-image/keyframe
  artifacts must be persisted so the projection can be rebuilt without re-deriving non-deterministic
  outputs.

---

## 3) Confidence & gaps

- **High confidence [V]:** ColPali mechanism and ~1,030×128 vectors/page; ColPali 81.3 vs 67.0 OCR
  baseline; ColQwen ViDoRe-v1 ~89–91; binary-quant ~32× / hamming ~3.5× / pool-3 → −67% @ 97.8%
  retained / up-to-32× @ <2% drop; Voyage multimodal-3 = 1024-dim single-vector, 32K ctx, +26.5%/
  +41.4% vs CLIP-L; Cohere Embed v4 Matryoshka 256–1536, $0.12 text / $0.47 image per 1M tokens, 128K
  ctx; LanceDB native multivector + MaxSim, IVF_PQ, cosine-only, float16/32/64.
- **Medium / inferred [I]:** nomic-embed-vision = 768-dim (inferred from nomic-embed-text-v1.5
  pairing; not directly confirmed in fetched pages — verify on the HF model card before relying).
  DSE 6 KB vs ColPali 256 KB and the DSE-vs-ColQwen2.5 FLOPs ratio come from single secondary sources;
  directionally reliable, exact magnitudes not independently confirmed. The "80% of enterprise PDFs"
  claim is an industry blog figure, not a measured statistic.
- **Could not fully verify [?]:** Exact Voyage multimodal-3 *image* pricing (per-pixel→token
  conversion) — the $0.12/1M figure is a marketplace aggregate; confirm at voyageai.com/pricing for
  current rates. ViDoRe-v2 full leaderboard per-model single-vs-multi numbers for Voyage/Cohere were
  not pulled cleanly (the public MTEB ViDoRe v1+v2 leaderboard is the authoritative source if exact
  head-to-heads are needed). Real-world *query latency in LanceDB specifically* for multivector at
  ugm scale is not published — needs a local load test.
- **Moving target:** This space turns over fast (Nemotron ColEmbed V2, Qwen3-VL Col-models,
  jina-embeddings-v4 unified single/multi-vector). Treat any specific checkpoint as a swappable,
  versioned component (D7), not a committed constant.

---

## 4) Recommendation for ugm

**Verdict: Yes — add a multimodal sub-index to P1/Lance, but as a two-tier, cheap-first projection,
not a single monolithic ColPali index. Reduce-to-text is NOT sufficient for a memory system that
ingests photos/screenshots/slides/video; native visual retrieval is a real capability. But it is a
retrieval projection only — it carries no belief and no grounding authority.**

### 4.1 The two-tier P1 multimodal sub-index (the full-scope design)

**Tier-A — single-vector multimodal embedding (always-on baseline).**
- **What:** exactly one multimodal embedding per **page-image**, per **video keyframe**, and per
  **video segment/shot** (and per standalone image). Use a **unified-encoder single-vector model**
  — **Cohere Embed v4** (Matryoshka 256–1536, int8/binary output, 128K ctx, hosted) or **Voyage
  multimodal-3** (1024-dim, 32K ctx). Self-host option: Jina-CLIP v2 / SigLIP 2 / nomic-embed-vision.
- **Why this is the baseline:** it is the only tier that is unconditionally affordable at
  millions-of-docs scale. ~4 KB/page fp32 (or ~1 KB at 256-dim Matryoshka, or int8 for ~1 KB),
  ordinary HNSW/IVF, millisecond ANN, and it gives genuine **cross-modal** text→image and image→image
  search that the text pipeline cannot. Store it as a standard Lance vector column alongside scalar
  filters (doc_id, page/timecode, modality, source) and BM25 over any OCR/caption text — the D9
  "Lance = entry" pattern, now multimodal.
- **Cross-modal store choice:** put the **single-vector** model in Lance for cross-modal search. This
  is the one to commit to first because it is cheap, hosted-or-open, and HNSW-native.

**Tier-B — multi-vector late interaction (selective, gated by the cheap-first cascade, D4).**
- **What:** a **ColQwen2.5** (Apache-2.0, ~89 ViDoRe-v1) or **ColNomic** multi-vector column,
  materialized **only for pages/segments flagged visually-rich** — i.e., where E0's converter
  detected tables/charts/figures/complex-layout or routed the page to OCR (scanned/complex). This is
  precisely the slice where single-vector underperforms and where OCR-then-text is weakest.
- **How to store it sanely in Lance:** token-pool (pool factor ~3 → ~340 vectors/page) and keep fp16;
  build the IVF_PQ multivector index; query **two-stage** (ANN coarse retrieve over Tier-A or a
  pooled coarse vector → MaxSim rerank over Tier-B). Target ~5–6 KB/page so Tier-B storage is
  single-vector-comparable. (Note: Lance multivector is **cosine-only**, so Vespa's binary/hamming
  trick is not directly available there — pooling + fp16 is the lever; if hamming MaxSim becomes a
  hard requirement, that is the one reason to consider a second engine — document as an open
  question, not a commitment.)
- **Why gated, not universal:** a universal ColPali index is ~130× the single-vector storage and adds
  rank-time MaxSim everywhere; that violates D4 (cheap-first; spend scales with value, not volume).
  Gate it so the expensive multi-vector path only touches the pages that actually need it.

### 4.2 How it obeys ugm's invariants

- **No authority (D6):** P1-multimodal holds zero source-of-truth. A visual hit returns a **locator**
  (doc_id + page/region bbox, or video timecode range + optional bbox) into E0 artifacts — the exact
  thing M-question-3's polymorphic media-locator needs — never a belief. Beliefs remain text claims
  with D32 grounding.
- **Vectors in Lance, not the graph (D8):** both tiers extend the existing Lance estate; LadybugDB
  stays embedding-free. One vector estate, one embedding budget — Tier-A/B are new columns/tables,
  not a new store.
- **Rebuildable projection (D7, P1 semantics):** persist the **page-images / keyframes / segment
  thumbnails** as E0 artifacts (GCS "artifacts" bucket) and store an `embedder_version` +
  `pool/quant params` per vector. Rebuild = re-embed from the stored images (deterministic given
  fixed model version), never re-derive from scratch nondeterministically. Hard-delete/GDPR (#24)
  cascades to these vectors because they are pure projection keyed by doc_id/segment_id.
- **Cheap-first cascade (D4):** Tier-A always; Tier-B only on visually-rich flag; deepest
  (per-region propagation / spatial grounding) only on demand. ASR/OCR/scene-detect (the deterministic
  layers) feed BM25 + Tier-A first; expensive VLM/multi-vector compute is the gated tail.

### 4.3 What to store — concise

Single multimodal P1 sub-index in Lance with, per visual unit (page-image | keyframe | video-segment |
standalone image):
- `doc_id`, `segment_id`, `modality`, `page_or_timecode`, `bbox?` (scalar filters / locator),
- `mm_vec` — **single-vector** multimodal embedding (Cohere Embed v4 / Voyage mm-3), Matryoshka-
  truncatable, the always-on cross-modal column,
- `ocr_text` / `caption` — for BM25 + as the bridge into the text pipeline (E1→E2 can still extract
  claims from these strings; grounding locator points back at the region/timecode),
- `colvecs?` — **multi-vector** ColQwen2.5/ColNomic column (pooled fp16), present only for
  visually-rich units,
- `embedder_version`, `pool_quant_params` — for D7 versioned rebuild.

**Non-goal to state explicitly:** binary/hamming MaxSim is not available in Lance multivector today
(cosine-only); we accept pooling+fp16 instead and treat a hamming-capable engine as a documented
alternative, not a phase. Visual *belief* without text grounding stays a non-goal — visual retrieval
ranks and locates; it never asserts a claim.

---

### Sources
- ColPali paper: https://arxiv.org/abs/2407.01449 ; https://arxiv.org/html/2407.01449v5
- ColPali blog: https://huggingface.co/blog/manu/colpali
- ColVision leaderboard (local repo): `_additional_context/colpali/README.md`
- ViDoRe v2: https://huggingface.co/blog/manu/vidore-v2 ; https://arxiv.org/abs/2505.17166
- Reproducibility/late-interaction insights: https://arxiv.org/pdf/2505.07730
- Hierarchical Patch Compression: https://arxiv.org/html/2506.21601v1
- Nemotron ColEmbed V2: https://arxiv.org/html/2602.03992v1
- Vespa scaling ColPali (storage/latency/quant): https://blog.vespa.ai/scaling-colpali-to-billions/
- Nomic Embed Multimodal / ColNomic: https://www.nomic.ai/news/nomic-embed-multimodal
- DSE vs ColPali storage/latency: https://zilliz.com/blog/colpali-enhanced-doc-retrieval-with-vision-language-models-and-colbert-strategy
- Voyage multimodal-3: https://blog.voyageai.com/2024/11/12/voyage-multimodal-3/ ; https://www.mongodb.com/docs/voyageai/models/multimodal-embeddings/
- Cohere Embed v4: https://docs.cohere.com/changelog/embed-multimodal-v4 ; https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v4.html
- Jina-CLIP v2: https://jina.ai/news/jina-clip-v2-multilingual-multimodal-embeddings-for-text-and-images/
- nomic-embed-vision: https://arxiv.org/html/2406.18587v1
- LanceDB multivector: https://docs.lancedb.com/search/multivector-search ; https://lancedb.com/docs/concepts/search/multivector-search/ ; https://www.lancedb.com/blog/blog/late-interaction-efficient-multi-modal-retrievers-need-more-than-just-a-vector-index/
