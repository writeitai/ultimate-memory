# colpali (illuin-tech/colpali) — code archaeology

Scope read: `colpali_engine/` (models, processors, scoring/MaxSim, losses, token-pooling,
interpretability), plus `README.md`, `CHANGELOG.md`, `pyproject.toml`, and the test suite.
Repo is the **training + inference engine** for ColPali / ColQwen2 late-interaction *visual*
document retrieval: embed the **page image directly** (no OCR), produce one small vector **per
image patch**, and score with ColBERT-style MaxSim. Everything below is from the actual source;
where I derive a number not stated in the repo I say so.

---

## 1. Core pipeline / stages

The whole thing is deliberately tiny — there is **no OCR, no layout parser, no chunker**. A page
is a PIL image in, a multi-vector tensor out.

**Indexing (per page):**
1. `process_images(images)` — converts to RGB, prepends a fixed text prompt, runs the HF
   processor. ColPali: `visual_prompt_prefix = "<image><bos>Describe the image."`
   (`colpali_engine/models/paligemma/colpali/processing_colpali.py:15`). ColQwen2:
   `"<|im_start|>user\n<|vision_start|><|image_pad|><|vision_end|>Describe the image.<|im_end|><|endoftext|>"`
   (`processing_colqwen2.py:22`). ColPali always resizes to **448×448**
   (`test_processing_colpali.py:36` asserts `pixel_values.shape == [1,3,448,448]`); ColQwen2 uses
   dynamic resolution via Qwen2-VL `smart_resize` bounded by `max_num_visual_tokens` (`processing_colqwen2.py:59`,
   `get_n_patches` at `:127`).
2. `model.forward(**batch)` — VLM backbone (`output_hidden_states=True`) → take **last hidden
   state** `(B, seq_len, hidden)` → a learned `custom_text_proj` linear layer down to
   `dim=128` → **L2-normalize per token** → zero out padding via attention mask
   (`modeling_colpali.py:59-78`, `modeling_colqwen2.py:50-77`). Output is the multi-vector page
   embedding `(B, seq_len, 128)`.
3. Optional `mask_non_image_embeddings=True` keeps only image-patch token vectors and drops the
   prompt-token vectors (`modeling_colpali.py:74-77`).
4. Optional compression: `HierarchicalTokenPooler.pool_embeddings(..., pool_factor=N)` clusters
   redundant patch vectors (see §6).

**Query (per query):** `process_queries` / `process_texts` tokenize the text and append a
**query-augmentation suffix** of 10 pad/`<|endoftext|>` tokens (`processing_utils.py:86-90`:
`suffix = self.query_augmentation_token * 10`) — "reasoning buffers" so the query also becomes a
multi-vector `(n_query_tokens, 128)`.

**Scoring:** `score_multi_vector(qs, ps)` → MaxSim (see §3).

The model classes are thin wrappers over HF backbones. Registered models
(`colpali_engine/models/__init__.py`): ColPali (PaliGemma), ColQwen2 / ColQwen2.5 / ColQwen3 /
ColQwen3.5, ColQwen2.5-Omni, ColIdefics3, ColGemma3, ColModernVBert, plus single-vector "Bi*"
siblings (BiPali, BiQwen2, …) for comparison.

---

## 2. What is stored per page (multi-vector representation)

- **Embedding dim is hard-coded to 128** for both ColPali and ColQwen2:
  `self.dim = 128; self.custom_text_proj = nn.Linear(hidden_size, 128)`
  (`modeling_colpali.py:52-53`, `modeling_colqwen2.py:36-37`). Comment at
  `modeling_colpali.py:50-51` notes dim is fixed because changing it would break checkpoint
  loading (awaiting "ColPali2"). Newer third-party variants differ — TomoroAI colqwen3 uses
  320-dim (`README.md:43`) — but the engine default is 128.
- **Vectors per page = one per image patch token (+ prompt tokens, unless masked).**
  - ColPali: 448×448 image, PaliGemma `patch_size=14` ⇒ 32×32 = **1024 image-patch vectors**,
    plus the few prompt tokens. (Patch math derived from `patch_size` property
    `modeling_colpali.py:115-117` and the fixed 448×448; the ColPali paper's canonical figure is
    **~1030 vectors**.)
  - ColQwen2: dynamic; **trained at 768 image patches per page** (`README.md:39-41`), tunable via
    `max_num_visual_tokens` (`max_pixels = max_num_visual_tokens * 28 * 28`, `processing_colqwen2.py:59`).
- Each vector is **L2-normalized**, dtype typically bf16/fp16 at inference (`README.md:91` loads
  `torch_dtype=torch.bfloat16`).
- **Derived storage cost (not stated in repo):** ~1030 × 128 × 2 bytes ≈ **264 KB/page (fp16)**,
  ~527 KB/page (fp32). Contrast a single-vector text embedding: one 768-/1024-d vector ≈ 1.5–4 KB.
  So a ColPali page is roughly **two-to-three orders of magnitude larger** in the index than a
  single dense vector — this is the central storage trade-off.

---

## 3. How scoring works (MaxSim late interaction)

`BaseVisualRetrieverProcessor.score_multi_vector` (`utils/processing_utils.py:133-188`) and the
dispatcher `utils/maxsim.py`:

- Reference torch kernel (`maxsim.py:29-31`):
  `torch.einsum("bnd,csd->bcns", query, doc).amax(dim=3).sum(dim=2)`.
  In words: for each **query token**, take its dot-product against **every page patch vector**,
  keep the **max** (the best-matching patch), then **sum those maxima over query tokens**. That
  sum is the page score. This is ColBERT late interaction: matching is per-token, not a single
  pooled vector, so a query term can "find" the one patch that answers it.
- Backend is selectable via env `COLPALI_SCORES_BACKEND` ∈ {`auto`,`torch`,`lik`}
  (`maxsim.py:18-27`); `lik` = fused Triton "late-interaction-kernels" on CUDA Ampere+/Apple
  Silicon, avoiding materializing the `[B,B,Lq,Ld]` score tensor (`README.md:64-66`,
  `CHANGELOG.md:13`). Pad tokens **must be exactly zero** — both paths rely on zero-padding, no
  explicit mask (`maxsim.py:11`).
- Batched, padded with `torch.nn.utils.rnn.pad_sequence(..., padding_value=0)`, default
  `batch_size=128`, scores returned on CPU as `(n_queries, n_passages)` fp32
  (`processing_utils.py:171-188`).
- Single-vector baseline for the Bi* models: `score_single_vector` = plain `einsum("bd,cd->bc")`
  dot product (`processing_utils.py:104-131`).
- **Experimental ANN path:** `create_plaid_index` / `get_topk_plaid` wrap `fast_plaid`
  (PLAID/FastPlaid) for large corpora (`processing_utils.py:190-245`) — optional dependency.

Training losses (`loss/late_interaction_losses.py`) use the same MaxSim: ColBERT InfoNCE
(`ColbertLoss`, `temperature=0.02`), pairwise, sigmoid, and explicit-hard-negative variants;
optional smooth-max (logsumexp, `tau=0.1`), length normalization, and pos-aware negative
filtering (`filter_threshold=0.95`, `filter_factor=0.5`).

---

## 4. OUTPUT DATA SCHEMA — and the locator gap (important for ugm)

**There is no rich output object and, critically, no offsets / bounding-boxes / timecodes back
to the source.** A grep across `colpali_engine/` for `bbox|bounding|coordinate|offset_mapping|
char_offset|timecode|timestamp` returns **nothing**. The artifacts are:

- **Page embedding:** a bare `torch.Tensor` `(seq_len, 128)` (or padded 3D batch). No metadata,
  no page id, no source pointer is attached by the engine — the caller owns that mapping.
- **Score matrix:** `torch.Tensor (n_queries, n_passages)` fp32 (`processing_utils.py:159-161`).
- **Corpus/dataset schema** (`data/dataset.py`): training/eval rows are just
  `{"query", "pos_target", "neg_target"}` (`ColPaliEngineDataset`, `dataset.py:68-71`) and a
  `Corpus` keyed by `doc_column_name="doc"` mapping `docid → image/str` (`dataset.py:50-64`).
  `doc` is a `Union[str, Image.Image]` (`dataset.py:8`). So the only "locator" is an opaque
  `docid` the user assigns to a whole page; nothing finer-grained.
- **Token-pooling output** (`compression/token_pooling/base_token_pooling.py:10-22`):
  `TokenPoolingOutput(pooled_embeddings, cluster_id_to_indices)` — the dict maps each pooled
  cluster id → the original token indices it absorbed. This is the only "provenance" structure in
  the repo, and it links pooled-vector → original-patch-index, **not** to pixels or source text.

**The closest thing to a grounded locator** is the **interpretability similarity map**
(`interpretability/similarity_map_utils.py:9-56`): for a chosen query token it reshapes the page
patch vectors into the 2D grid `(n_patches_x, n_patches_y)` (via
`get_n_patches(image_size, patch_size)`, `processing_colpali.py:108-116`) and computes
`einsum("nk,ijk->nij", query, image_grid)` → a per-patch heatmap that can be upsampled and
overlaid on the page (`interpretability/similarity_maps.py:13-72`). This **can** be converted to
an approximate pixel region (patch (i,j) ↔ a `patch_size×patch_size` image tile), but it is a
**visualization computed on demand at inference, patch-resolution, and not persisted** — it is
not a stored offset and never points back to source text/characters.

---

## 5. Key parameters / model names / thresholds

- Embedding dim: **128** (hard-coded). Query suffix length: **10** augmentation tokens.
- ColPali fixed input **448×448**, patch 14 → 32×32 grid. ColQwen2 dynamic, **768** patches
  trained, `max_pixels = max_num_visual_tokens·28·28`.
- Scoring default `batch_size=128`; backend env `COLPALI_SCORES_BACKEND` (`auto|torch|lik`).
- Loss defaults: `temperature=0.02`, `tau=0.1`, `norm_tol=1e-3`, `filter_threshold=0.95`,
  `filter_factor=0.5`, `max_batch_size=1024` (`late_interaction_losses.py:140-157`).
- Token pooling `pool_factor` controls `max_clusters = max(token_length // pool_factor, 1)`,
  Ward-linkage HAC on `1 - cosine` distance, cluster mean re-normalized
  (`hierarchical_token_pooling.py:118-138`).
- **Models & ViDoRe scores** (`README.md:35-47`): `vidore/colpali` 81.3 (PaliGemma-3b-mix-448,
  paper checkpoint), colpali-v1.2 83.9, colpali-v1.3 84.8; `vidore/colqwen2-v1.0` 89.3
  (Qwen2-VL-2B), `vidore/colqwen2.5-v0.2` 89.4 (Qwen2.5-VL-3B); colSmol-256M 80.1, colSmol-500M
  82.3. Deps (`pyproject.toml`): `transformers>=5.3.0,<6`, `torch>=2.2`, `peft`, `scipy` (HAC).

## 6. Performance / cost characteristics (as stated)

- **Token pooling trade-off (measured, `README.md:239`):** at `pool_factor=3`, "the total number
  of vectors is reduced by **66.7%** while **97.8%** of the original performance is maintained."
  This is the engine's headline answer to the multi-vector storage blow-up — described as
  CRUDE-compliant (add/delete-friendly).
- **Fused MaxSim kernel (`README.md:64-66`, PR #412):** on an 80 GB H100, ColQwen2+LoRA, the
  `[lik]` kernel raised the largest trainable batch size from **64 → 128** with unchanged
  throughput, by not materializing the `[B,B,Lq,Ld]` score tensor (quadratic in batch).
- No explicit per-page latency or index-size numbers are given in the repo; the README instead
  points to external vector DBs that support multi-vector/late-interaction at scale: Vespa,
  Qdrant, Weaviate, Elasticsearch, plus PLAID via `fast_plaid` (`README.md:368-381`).

---

## 7. Steal vs avoid for ugm

ugm is text-centric memory needing **versioned conversion + grounded locators**. Read against that:

**Avoid / does not fit ugm's locator need:**
- ColPali deliberately **throws away the text layer and any character/coordinate provenance** —
  the index is patch vectors, the only locator is a page-level `docid`. ugm's "grounded locators"
  (offsets/spans back into source) **cannot be recovered** from a ColPali index. The
  similarity-map heatmap is patch-resolution and inference-only — not a stored span.
- The per-page footprint (~1030 vectors × 128-d ≈ hundreds of KB/page, §2) is ~100–300× a single
  dense vector. For a text-first memory this is a heavy index to carry for content that is already
  digital text.
- No versioning/conversion-provenance concept anywhere — a page is re-embedded from scratch
  (rebuild-first); there is no incremental "this region changed" notion.

**Steal / genuinely useful:**
- **Late-interaction MaxSim itself** (`maxsim.py`, `score_multi_vector`) is a clean, ~2-line
  reusable scoring primitive: store per-chunk token vectors, `einsum(...).amax().sum()`. Worth
  considering for ugm chunks where single-vector pooling loses term-level recall — late
  interaction lets a rare query term match the one chunk-token that carries it.
- **Hierarchical token pooling with a `cluster_id_to_indices` provenance map**
  (`hierarchical_token_pooling.py`, `base_token_pooling.py`) — the pattern of compressing a
  multi-vector set while **keeping a back-pointer from pooled vector → original token indices** is
  exactly the kind of locator-preserving compression ugm would want (and is precisely what
  ColPali's own page schema lacks at the pixel level). pool_factor=3 → 66.7% smaller @ 97.8% perf
  is a concrete starting point.
- **The OCR-free fallback is the right tool only for non-textual/scanned pages** (charts, tables,
  figures, scans, handwriting) where OCR-then-embed loses layout/visual signal. For ugm, the
  defensible use is: keep text-native locators for born-digital text, and reserve a ColPali-style
  visual embedding as a *secondary* representation for image-only pages — never as the primary
  index, because it erases the locators ugm depends on.
- **Backend-pluggable scoring via env flag** (`COLPALI_SCORES_BACKEND`) and the zero-padding/mask
  contract are a tidy engineering pattern if ugm builds its own multi-vector scorer.
