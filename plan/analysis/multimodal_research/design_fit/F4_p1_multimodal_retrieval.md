# F4 — P1 Multimodal Retrieval: a visual sub-index for Lance

**Design-fit question.** Should P1/Lance gain a multimodal-embedding sub-index — keyframe /
video-segment / page-image embeddings, single-vector (CLIP/SigLIP/Voyage/Cohere) and/or ColPali-style
late-interaction "embed the page image, skip OCR"? Is *reduce-to-text* enough for a memory system, or
is *native visual retrieval* a real capability worth a projection?

Research base: `web_research/M4_visual_retrieval_embeddings.md` (the core), `M5_multimodal_memory_systems.md`,
`M2_video_understanding.md`, `M6_privacy_pii_deletion.md`; `repo_findings/colpali.md`. ugm anchors: D4,
D6, D7/D33, D8, D9, D18, D32, D37, D42, D43, D44. Companion design-fit questions: the **E0 `convert()`
media routing** and the **generalized grounding locator** (M5 STEAL-1: a tagged-union locator
`{text: char-offsets} | {image: page,bbox} | {av: t_start,t_end,speaker?}`, refining D32/D38) — F4
*consumes* that locator and does not redefine it.

---

## 1. Verdict

**Yes. Add a multimodal visual sub-index to P1/Lance — but as a two-tier, cheap-first projection, not a
monolithic ColPali index, and never as an evidence authority.**

Three claims, decided:

1. **Reduce-to-text is necessary but not sufficient.** ugm's canonical path stays text: every belief is
   a text claim (E2) grounded by char offsets (D32), and that is correct — a page-image cannot host a
   claim, an entity identity, temporal validity, or supersession (M5 §2.4: Morphik/ColPali "is a
   retrieval index, not a knowledge substrate"). **But** a memory that ingests photos, screenshots,
   slides, scanned forms and video has a real retrieval capability text alone cannot serve: "find the
   slide with the revenue waterfall," "find the frame where the whiteboard shows X," "find images that
   look like this one." These are *visual recall* queries whose answer is a layout or a timecode, not a
   sentence. OCR-then-embed-text loses exactly the signal they need (charts, layout, scans, handwriting;
   M4 §2.1). Native visual retrieval is a genuine new capability — worth a projection.

2. **It is a pure P-plane projection, holding no authority.** A visual hit returns a **locator**
   (`doc_id` + page/bbox, or video timecode range + bbox) into E0 artifacts — never a belief. Truth
   stays in text claims grounded at that locator (D6/D8/D9/D32). Vectors live in Lance, never in the
   P2 graph (D8/D18/D44). The whole sub-index is rebuildable from stored image artifacts (D7/D33) and
   cascades on hard-delete for free (D37).

3. **Two tiers, gated by the cheap-first cascade (D4).** **Tier A** — one *single-vector* multimodal
   embedding per real visual unit (page-image from the OCR/figure route, standalone image, video
   keyframe, video segment) — is the always-on, millions-of-units baseline that gives cross-modal
   text↔image search. **Tier B** — a *multi-vector late-interaction* (ColQwen2.5 / ColNomic) column —
   is materialized **only for units flagged visually-rich** (tables/charts/figures/scanned/dense
   layout), where single-vector underperforms and OCR-then-text is weakest. Both live in one Lance
   estate; both carry no authority.

---

## 2. The design, concretely

### 2.1 What gets embedded — the *visual unit*, and the two gates

The indexed object is a **visual unit**: one image-shaped thing produced by E0 that carries content not
fully captured by the text pipeline. Four kinds (locator shapes in parentheses):

| Modality | Produced by (E0 route) | Locator |
|---|---|---|
| `page_image` | scanned/complex/figure-bearing PDF → OCR route renders a page raster | `{image: page, bbox?}` |
| `standalone_image` | image file ingested directly | `{image: bbox?}` (whole image = whole "page") |
| `video_keyframe` | one representative frame per detected shot (PySceneDetect → keyframe select; M2) | `{av: t_mid, bbox?}` |
| `video_segment` | a shot/scene span (the "PageIndex-analogue for video," M2/M5) | `{av: t_start, t_end}` |

Two gates decide what is materialized — this is the D4 cheap-first cascade made concrete, and a
deliberate scope boundary (not phasing):

- **Gate 1 — "is there a meaningful image artifact whose content the text pipeline does not already
  hold?" → Tier A (single-vector), always-on.** Fires for standalone images, video keyframes, video
  segments, and page-images **from the OCR/figure-bearing convert route**. It does **not** fire for
  born-digital text PDF pages: ugm never rasterizes a clean-text page just to embed it — the text pipeline
  (chunks/claims) already covers it, and D38 already routes born-digital PDFs to text extraction, not
  OCR (M4 §2.1). Spend scales with *visual content*, not document count.

- **Gate 2 — "does text reduction lose signal here?" → Tier B (multi-vector late interaction),
  selective.** Fires on the subset of Tier-A page-images / keyframes the E0 converter/structurer flags
  **visually-rich** (`role ∈ {table, figure, ...}`, scanned, dense/multi-column layout, chart/diagram
  detected). This is precisely the slice where a single pooled vector blurs the answer and where ColPali
  wins decisively (M4 §2.1: nDCG@5 81.3 vs 67.0 for the best OCR+caption+text pipeline; gap largest on
  tables/charts/infographics).

The **page-image / keyframe / segment-thumbnail rasters themselves are E0 artifacts** (D37 artifacts
bucket), persisted because they are the deterministic *rebuild source* for the embeddings (D7, §3
below) — not P1 state. F4 does not invent them; the E0 `convert()`/video companion question already
emits them.

### 2.2 The two tiers — and what "late interaction" means

**Tier A — single-vector multimodal embedding (the affordable default).** One ~1024-dim vector per
visual unit from a *unified-encoder* model — **Cohere Embed v4** (Matryoshka 256/512/1024/1536,
int8/binary output, hosted) or **Voyage multimodal-3** (1024-dim); self-host option Jina-CLIP v2 /
SigLIP 2 / nomic-embed-vision. "Unified encoder" matters: classic CLIP runs text and image through
*separate* towers, creating a **modality gap** (vectors cluster by modality, hurting true cross-modal
ranking); the unified models put both through one backbone and so crush CLIP on document/figure
retrieval (M4 §2.3: Voyage +26.5% doc-screenshot, +41.4% table/figure vs CLIP-L). Storage is tiny:
~4 KB/unit fp32, ~1 KB at 256-dim Matryoshka or int8. This is an ordinary Lance vector column
(HNSW/IVF + scalar filters), millisecond ANN — the D9 "Lance = entry" pattern, now cross-modal.

**Tier B — multi-vector late interaction (the precision tier, gated).** *Late interaction* in plain
language (the ColBERT/ColPali mechanism; colpali.md §3): instead of squashing a whole page into one
vector, keep **one small (128-dim) vector per image patch** (a ~14-px tile → ~1,000 patch vectors per
page). A text query is likewise encoded to one vector per token. Relevance is **MaxSim** — for each
query token, take its single best-matching patch (max cosine over all patches), then sum those bests
across query tokens. The effect: a rare query word can "land on" the exact table cell or chart region
that answers it — precision a single pooled page-vector destroys. The cost is the inverse: ~1,000
vectors per page instead of 1 (~528 KB/page fp32; M4 §2.2), plus a rerank-time MaxSim pass that is
O(query-tokens × page-patches) per candidate, so retrieval **must be two-stage** (cheap ANN
candidate-gen → MaxSim rerank).

Model: **ColQwen2.5** (Apache-2.0, ViDoRe-v1 ~89) or **ColNomic** (single source-family with a
single-vector sibling, stronger on the harder out-of-domain ViDoRe-v2 ~62.7). The headline storage
lever is **hierarchical token pooling** — cluster redundant patch vectors before storing: pool-factor 3
cuts vectors ~67% while retaining 97.8% of accuracy (colpali.md §6), landing Tier B near ~5–6 KB/page,
*single-vector-comparable storage* with rank-time MaxSim compute. (All numbers are starting points to
measure per D-discipline, not committed constants.)

### 2.3 LanceDB: multi-vector late interaction vs single-vector (decided)

LanceDB supports **both** natively, so both tiers live in the **one vector estate** D8 already commits
to — no second store, no new engine (M4 §2.4):

- **Single-vector (Tier A):** an ordinary Lance vector column; HNSW/IVF; scalar filters; BM25 over
  OCR/caption text. Exactly today's chunk/claim/relation-label pattern.
- **Multi-vector (Tier B):** a Lance column holding a **list of vectors per row**, with **MaxSim
  computed natively** and an **IVF_PQ** index over the multi-vectors. LanceDB explicitly warns that
  indexing "matters more for multivector tables" (un-indexed = brute force over rows × vectors-per-row),
  and recommends **two-stage** (coarse retrieve → MaxSim rerank) at scale — matching the Vespa pattern.
- **One hard constraint:** Lance multivector is **cosine-only** (float16/32/64). Vespa's
  binary/hamming-MaxSim trick (~32× compression) is **not** a first-class Lance metric. So the
  compression lever in Lance is **token-pooling + fp16**, not binary quantization. (Scope boundary,
  §4/§5.)

### 2.4 Schema / contracts

Two Lance tables in the existing P1 estate (mirroring how chunks / claims / relation-labels are separate
Lance tables), joined by `visual_unit_id`. Both are derived, rebuilt with the same guarantees as the
rest of P1.

```
-- P1.V-A : the always-on single-vector visual index (Tier A)
p1_visual(
  visual_unit_id    PK,                      -- stable id (doc_id + modality + ordinal/shot)
  deployment, doc_id,                        -- scalar filters; deletion/cascade key
  modality          enum{page_image, standalone_image, video_keyframe, video_segment},
  -- generalized locator (companion question; the RETURN payload, never a belief):
  page, bbox,                                -- image units
  t_start, t_end, shot_id, scene_path,       -- video units
  artifact_uri,                              -- the persisted raster in the E0 artifacts bucket (rebuild source, D37)
  visually_rich     bool,                    -- Gate-2 flag; true => a row exists in p1_visual_li
  origin            enum{external, self},     -- carried from D42 (self-generated echoes flagged)
  ocr_text, caption,                          -- BM25 + the bridge into the text pipeline (NOT authority)
  mm_vec            vector<f32|int8>[d],      -- Tier-A single-vector embedding (Matryoshka-truncatable)
  embedder_name, embedder_version,           -- D7/D33 versioning (mirrors converter_version)
  source_versions   json                     -- upstream {render|keyframe|scene_detect|ocr|caption}_version (D7 replay)
)
-- index: HNSW/IVF over mm_vec ; BM25 over ocr_text/caption ; scalar filters on modality/doc_id/visually_rich

-- P1.V-B : the selective multi-vector late-interaction index (Tier B)
p1_visual_li(
  visual_unit_id    PK  -> p1_visual.visual_unit_id,   -- only for visually_rich units
  colvecs           list<vector<f16>[128]>,            -- pooled patch vectors (ColQwen2.5 / ColNomic)
  li_model, li_version, pool_factor                    -- D7 versioning + the pooling/quant params
)
-- index: IVF_PQ multivector (cosine) ; queried two-stage (coarse ANN -> native MaxSim rerank)
```

Notes: (1) `ocr_text`/`caption` are present for BM25 and as the *bridge* into E2 — but the claim is
extracted from that text by E2 with D32 grounding, not asserted by P1 (verbatim OCR satisfies D32
layers 1–2 as real source text; VLM captions enter as `added_context[]`, model assertions stamped with
origin per D42, never verbatim — M5 STEAL-3). The vector columns assert nothing. (2) No column ever
projects to P2/Ladybug (D8/D18/D44 — a value/embedding is not a node).

### 2.5 New search recipes (D9 style — zero LLM on the query path)

Visual channels are **additional entry channels** fused by RRF into the existing retrieval, then
hydrated to a locator and onward to the grounded text. New named recipes:

- **`visual_similarity`** (image→image): given a query image or an existing `visual_unit_id`, ANN over
  `mm_vec` → ranked visual-unit locators. Use: "find frames/pages that look like this," near-duplicate
  detection, "more like this slide."
- **`find_visual`** (cross-modal text→image): embed the text query with the unified model's text side →
  ANN over `mm_vec` → visual-unit locators. Use: "the slide about the revenue waterfall," "the photo of
  the whiteboard." This is the capability the text pipeline structurally cannot serve.
- **`find_frame`** (video locator): `find_visual`/`visual_similarity` scoped to
  `modality ∈ {video_keyframe, video_segment}` → returns `doc_id` + **timecode range** (+bbox?). The
  video analog of a page locator; the join key into ASR transcript + scene tree.
- **`visual_maxsim_rerank`** (the precision recipe, Tier B): two-stage — candidate-gen via `mm_vec`
  (Tier A) or BM25 over `ocr_text` → **MaxSim rerank over `colvecs`** for the visually-rich subset. Use:
  "which page/region answers this question about the table/chart."

All four are *candidate generators / rerankers* feeding the same D9 fusion (RRF → graph-distance +
evidence-count rerank). A visual hit never wins on its own — it contributes a candidate, then **hydrates
to its locator, and the locator pulls the grounded text claims** already extracted at that page/timecode.

### 2.6 The locator bridge — how a pixel hit becomes grounded truth

```
query (text or image)
   │
   ├─ find_visual / visual_similarity / find_frame  (Tier A, ANN over mm_vec)
   │        │  optional: visual_maxsim_rerank  (Tier B, MaxSim over colvecs)
   │        ▼
   │   visual-unit hits ──► LOCATOR {doc_id, page+bbox | t_start..t_end}
   │                              │
   ├─ (parallel) text channels (chunks/claims/relations)   │
   │        └──────────── RRF fusion (D9) ─────────────────┤
   │                                                        ▼
   │                              hydrate locator ──► text claims grounded AT that page/timecode (D32)
   │                                                  └─ entity/relation expansion (P2) ─ PG ─ GCS bytes
   ▼
ANSWER: belief = the TEXT CLAIM ;  the visual unit only said "look here"
```

The visual index *locates*; the text claim *asserts*. That separation is the whole safety story.

---

## 3. How it preserves ugm invariants

- **No authority — ever (D6).** P1-visual holds zero source-of-truth, no validity state, and is
  deletable/rebuildable. A visual hit is a locator, not a belief; current-belief validity still has
  exactly one home (Postgres relations/observations). This is the explicit contrast with the memory
  frameworks that drop the locator and keep only a caption (M5 §2.1 Mem0, §2.2 Cognee) and with
  Graphiti's open proposal to hang a multimodal vector on a graph node — which ugm forbids.

- **Vectors in Lance, never the graph (D8/D18/D44).** Both tiers are new Lance tables in the one vector
  estate; LadybugDB stays embedding-free. "A value/embedding is not a node, and a REL endpoint must be a
  node" (D44) — the same rule that bars `observations` from P2 bars visual vectors.

- **Rebuildable from stored artifacts, versioned and replayed (D7/D33).** The page-image / keyframe /
  segment rasters persist as **E0 artifacts** (D37); P1-visual stores `embedder_version` +
  upstream `source_versions`. Rebuild = re-embed from the stored rasters (deterministic given a fixed
  model version), never re-derive non-deterministically. An embedder bump re-embeds the affected units
  by version filter — the same discipline as `converter_version`. The model checkpoint is a **swappable,
  versioned component**, not a committed constant.

- **Retrieval through projections, zero LLM on the query path (D9).** Visual channels are entry/rerank
  primitives fused by RRF; no generation on the hot path. Latency stays bounded by retrieve+rerank.

- **Cheap-first cascade (D4).** Deterministic E0 layers (scene-detect, OCR, perceptual-hash keyframe
  dedup) feed BM25 + Tier A first; Tier A single-vector is the always-on cheap baseline; Tier B
  multi-vector MaxSim is gated to visually-rich units; per-region similarity-map grounding (colpali.md
  §4) is on-demand only. Spend scales with visual value, not volume.

- **Truth stays in grounded text (D32), captions quarantined (D42).** Claims come from the text
  rendering routed through E2: verbatim OCR/ASR is first-class source text (D32 layers 1–2); VLM
  captions are model assertions → `added_context[]` with an origin stamp, never verbatim, never counted
  as independent corroboration. The visual vectors never assert.

- **Deletion / privacy cascades for free (D37; M6).** P1-visual is pure projection keyed by
  `doc_id`/`visual_unit_id`: hard-delete a document and its visual units simply aren't materialized on
  the next rebuild; the source rasters live in the artifacts bucket the E0 delete cascade already
  hard-deletes. This matters because face/scene embeddings are biometric-adjacent (M6) — keeping them a
  derived projection (not authority) is what makes GDPR-style erasure a non-event.

**Genuine non-goals (scope boundaries with rationale, not phasing):**

1. **Visual belief without text grounding.** The index ranks and locates; it never asserts a claim.
   Rationale: claims need entity identity, temporal validity, supersession, `evidence_count` — none of
   which a page-image hosts (M5 §2.4). Adopting Morphik's "page-image *is* the memory" as canonical is
   rejected.
2. **Vectors on the P2 graph.** Forbidden by D8/D18/D44, not deferred.
3. **Rasterizing born-digital text pages to embed them.** The text pipeline already covers them; the visual
   index targets only the slice where text reduction loses signal (D4).
4. **Hamming/binary-MaxSim compression.** Not available in Lance multivector (cosine-only); we accept
   token-pooling + fp16. A hamming-capable engine (Vespa/Qdrant) is a **documented alternative**, adopted
   only if a measured Tier-B latency requirement at scale ever forces it — one vector estate (D8) is the
   default, not a phase.
5. **Late interaction over arbitrary *text* chunks** (ColBERT for the text pipeline) is a separate
   retrieval-quality question; here multi-vector is only over page-images.

---

## 4. Risks / what to measure (spikes)

1. **Lance multivector latency at scale (the load-bearing unknown).** Public Lance numbers for
   multivector MaxSim at ugm scale don't exist (M4 §3). Spike: load Tier B for a realistic visually-rich
   slice (pooled fp16, IVF_PQ), measure two-stage P95 vs. the Tier-A-only baseline; confirm the
   cosine-only/no-hamming penalty is acceptable. **Decision gate** for whether Tier B stays in Lance or
   the documented hamming-engine alternative is triggered.
2. **Does Tier B earn its cost over Tier A + OCR-BM25?** On *our* corpus's visually-rich slice, measure
   recall@k of `find_visual` (Tier A) + BM25-over-OCR vs. adding `visual_maxsim_rerank` (Tier B). If the
   uplift is small on real data, Gate 2 narrows or Tier B stays dormant — measured, not assumed
   (ViDoRe-v1 is saturated/in-domain; v2 OOD scores ~60s show novel corpora are still hard, M4 §2.1).
3. **Single-vector model choice + Matryoshka truncation point.** Cohere Embed v4 vs Voyage mm-3 vs
   self-host (SigLIP 2 / Jina-CLIP v2); where Matryoshka truncation (256 vs 1024) starts costing recall.
   Hosted-vs-self-host is also a privacy/cost call (M6) — biometric content may force self-host.
4. **Token-pool factor sweet spot.** pool-factor 3 → 97.8%@−67% is a starting point (colpali.md §6);
   measure the accuracy/storage curve on our pages before committing.
5. **Visually-rich gate precision.** Gate 2 depends on the E0 converter/structurer flag
   (`role`/scanned/chart-detected). Measure false-negative rate (a chart page mis-flagged as text loses
   Tier B) and false-positive cost.
6. **Video keyframe granularity.** One keyframe per shot vs per scene; how `find_frame` precision
   degrades with coarser segments (M2). Embedding cost is bounded by shot count, not duration — confirm.

---

## 5. Proposed decisions (continue from D44) and design-doc deltas

### D45 — P1 gains a two-tier visual sub-index (single-vector always-on + late-interaction gated)

**Decision.** P1/Lance gains a **multimodal visual sub-index** over *visual units* (page-images from the
OCR/figure route, standalone images, video keyframes, video segments). It is **two-tier, cheap-first
(D4)**: **Tier A** = one *single-vector* unified-encoder multimodal embedding per visual unit (Cohere
Embed v4 / Voyage mm-3 class), always-on, an ordinary Lance vector column — the cross-modal baseline.
**Tier B** = a *multi-vector late-interaction* column (ColQwen2.5 / ColNomic), Lance-native MaxSim +
IVF_PQ, **materialized only for units flagged visually-rich**, token-pooled + fp16, queried two-stage.
Born-digital text pages are **not** rasterized to embed (text pipeline covers them). Both tiers are pure
**P-plane projections** (D6): no authority, vectors in Lance only — never P2 (D8/D18/D44) — versioned by
`embedder_version` and **replayed from stored E0 image artifacts** on rebuild (D7/D33); hard-delete
cascades for free (D37). Lance multivector being **cosine-only** is accepted; token-pooling+fp16 is the
compression lever, and a hamming-capable engine is a documented alternative, not a phase.

### D46 — Visual retrieval returns locators, never beliefs; new recipes fuse into D9

**Decision.** A visual hit returns a **locator** (`doc_id` + page/bbox, or video timecode range + bbox)
into E0 artifacts — **never an assertion**. Beliefs remain text claims grounded at that locator (D32);
verbatim OCR/ASR is first-class source text, VLM captions are quarantined as model assertions with an
origin stamp (D42), and the visual vectors assert nothing. New named search recipes —
**`visual_similarity`** (image→image), **`find_visual`** (cross-modal text→image), **`find_frame`**
(video timecode), **`visual_maxsim_rerank`** (Tier-B precision) — are **candidate generators / rerankers
fused by RRF into the existing D9 path, with zero LLM on the query path**. The visual index *locates*;
the text claim *asserts*. P1-visual **never becomes an evidence authority** — this is a binding invariant,
not a tuning choice.

### Design-doc deltas this implies

- **New design doc** `plan/designs/p1_visual_retrieval_design.md` (or a §"visual sub-index" in the
  planned `e1_chunks_design.md`/`retrieval_design.md`): the two Lance tables (§2.4), the two gates (§2.1),
  the recipes (§2.5), and the locator bridge (§2.6).
- **`overall_design.md`**: §2 stores table — P1/LanceDB row gains "+ visual units (page-image / keyframe /
  segment embeddings)"; §4 P1 note and §6 retrieval — add the visual entry channels + the four recipes to
  the recipe list and the retrieval diagram; §3 data-model — note visual units are projection-only,
  locator-bearing, non-asserting.
- **`e0_files_design.md`**: §3 `convert()` and the (companion) video route must **persist the page-image /
  keyframe / segment-thumbnail rasters as artifacts** (the D7 rebuild source for embeddings) and emit a
  **`visually_rich` flag + `role`** per page/keyframe that Gate 2 reads; §2 storage — the rasters are
  artifacts-bucket objects, deletion-cascaded.
- **`retrieval_design.md`** (planned): register `visual_similarity`, `find_visual`, `find_frame`,
  `visual_maxsim_rerank`; the recipe linter records that none of them may answer a "what is true" query
  on their own — they return locators that must hydrate to grounded text.
- **`decisions.md`**: append **D45**, **D46**; cross-reference D6/D7/D8/D9/D18/D32/D37/D42/D44.
- **`questions.md`**: log the six spikes (§4), flagging spike 1 (Lance multivector latency) as the gate
  for the Tier-B-engine decision.
