# MinerU (opendatalab/MinerU) — code archaeology

Source: cloned repo at `_additional_context/mineru/`. Version **3.4.0**
(`mineru/version.py` → `__version__ = "3.4.0"`). License: custom "MinerU Open-Source
License" (`pyproject.toml`, `LICENSE.md`). Self-description (`pyproject.toml`):
"A practical document parsing tool for converting PDF, images, DOCX, PPTX, and XLSX
into Markdown and JSON".

Everything below is read from source; where a thing is not in the code it is marked
**not found**.

---

## 1. Backends (the top-level pipelines)

Entry point: `do_parse()` / `aio_do_parse()` in `mineru/cli/common.py` (lines 668-852).
Four mutually-exclusive backends selected by the `backend=` arg:

| Backend | Code path | What it is |
|---|---|---|
| `pipeline` | `mineru/backend/pipeline/` | Classic modular CV stack (layout → formula → table → OCR). CPU/GPU. Default. |
| `vlm-*` | `mineru/backend/vlm/` | Single vision-language model `MinerU2.5-Pro-2605-1.2B` doing "two-step extract". GPU. |
| `hybrid-*` | `mineru/backend/hybrid/` | Pipeline layout/OCR models fused with the VLM, gated by an `effort` param. |
| `office` (docx/pptx/xlsx) | `mineru/backend/office/` | Native OOXML parsing, no CV. Routed first in `_process_office_doc`. |

VLM/hybrid sub-engines (`mineru/cli/backend_options.py`, `vlm_analyze.py`):
`transformers`, `vllm-engine`, `vllm-async-engine`, `lmdeploy-engine`, `mlx-engine`
(Apple Silicon), `http-client` (OpenAI-compatible remote server via `mineru-vllm-server`
/ `mineru-router`). Image inputs are wrapped to single-page PDFs (`read_fn`,
`images_bytes_to_pdf_bytes`) so everything downstream is "PDF pages".

`hybrid` `effort`: `HYBRID_EFFORT_CHOICES = ("medium", "high")`, default `"medium"`
(`backend_options.py:8-9`). Medium remaps pipeline layout labels into VLM types; high
runs more VLM work (`hybrid_analyze.py` `MEDIUM_EFFORT_LAYOUT_LABEL_TO_VLM_TYPE`,
`HYBRID_ANALYZE_EFFORTS`).

---

## 2. Pipeline stages (the real ordering)

`mineru/backend/pipeline/batch_analyze.py`, `BatchAnalyze.__call__` (line 408+). Per
batch of page images, in this order:

1. **Layout detection** — `PP-DocLayoutV2` (`run_layout_inference`, `model.layout_model.batch_predict`).
   One model emits, per page, a list of boxes each with `bbox`, class `label`, `score`,
   and a reading-order `index`. 25 classes (`pp_doclayoutv2.py:33-59` `PP_DOCLAYOUT_V2_LABELS`):
   `abstract, algorithm, aside_text, chart, content, display_formula, doc_title,
   figure_title, footer, footer_image, footnote, formula_number, header, header_image,
   image, inline_formula, number, paragraph_title, reference, reference_content, seal,
   table, text, vertical_text, vision_footnote`.
2. **Formula recognition (MFR)** — only if `formula_enable`. Crops `display_formula` /
   `inline_formula` boxes, runs `unimernet_small` (default) or `pp_formulanet_plus_m`
   (set via env `MINERU_FORMULA_CH_SUPPORT`, `model_init.py:64-72`) → fills `latex`.
   (Formula *detection* is folded into the layout model, not a separate MFD pass.)
3. **Table recognition** — only if `table_enable`. Sub-stages per table region:
   orientation classify (`MineruTableOrientationClsModel`, rotates 90/270) → wired/wireless
   classify (`PaddleTableClsModel`) → table-internal OCR det → table-internal OCR rec →
   structure model. Wireless = SLANet+ (`PaddleTableModel`, ONNX); a table classified
   wireless with `cls_score < 0.9`, or classified wired, is *also* run through the wired
   UNet model (`UnetTableModel`). Output is an HTML `<table>` string (sliced to the
   `<table>…</table>` span, line 695-699). Inline images/formulas inside tables are
   masked, encoded (`<img src="data:image/jpg;base64,…"/>` / `<eq>latex</eq>`) and
   re-inserted (`_extract_table_inline_objects`, lines 318-405).
4. **Text OCR detection** — PaddleOCR-torch DBNet (`PytorchPaddleOCR`). Boxes are sorted
   (`sorted_boxes`), merged (`merge_det_boxes`), formula regions masked out
   (`mask_formula_regions_for_ocr_det`).
5. **Text OCR recognition** — per-language batched; writes `text` + `score`; drops spans
   with `score < OcrConfidence.min_confidence` (= **0.5**, `ocr_utils.py:11`) plus a
   hard-coded junk-string list (lines 904-912).
6. **Seal OCR** — boxes labelled `seal` are cropped and OCR'd with `lang="seal"`.

For "auto" parse method, `pdf_classify.classify()` decides text-PDF vs scanned → toggles
OCR (`_get_ocr_enable`, `pipeline_analyze.py:88-93`).

Models are downloaded from HF or ModelScope (`enum_class.py ModelPath`):
- VLM: `opendatalab/MinerU2.5-Pro-2605-1.2B` (HF) / `OpenDataLab/MinerU2.5-Pro-2605-1.2B` (MS)
- Pipeline kit: `opendatalab/PDF-Extract-Kit-1.0`
- `models/Layout/PP-DocLayoutV2`, `models/MFR/unimernet_hf_small_2503`,
  `models/MFR/pp_formulanet_plus_m`, `models/OCR/paddleocr_torch`,
  `models/TabRec/SlanetPlus/slanet-plus.onnx`, `models/TabRec/UnetStructure/unet.onnx`,
  `models/TabCls/paddle_table_cls/PP-LCNet_x1_0_table_cls.onnx`.

The VLM backend ("two-step extract") calls `predictor.batch_two_step_extract(images=…,
image_analysis=…)` (`vlm_analyze.py:479`). Step 1 = layout (boxes+types), step 2 =
per-region content recognition. **That logic lives in the external `mineru-vl-utils`
package (`MinerUClient`), not in this repo** — the prompt/token grammar is **not found**
here. The model is Qwen2-VL-class (`Qwen2VLForConditionalGeneration`, line 97).

---

## 3. Output data schema (this is the load-bearing part)

`_process_output` (`common.py:259-348`) writes, per document, into
`{output_dir}/{name}/{parse_method}/`:
`{name}.md`, `{name}_content_list.json`, `{name}_content_list_v2.json`,
`{name}_middle.json`, `{name}_model.json`, `{name}_layout.pdf`, `{name}_span.pdf`
(pipeline only), `{name}_origin.pdf`, and an `images/` dir. Authoritative human doc:
`docs/en/reference/output_files.md`.

### 3a. `model.json` — raw model output
- **Pipeline**: flat list of layout dets: `{cls_id, label, score, bbox:[x0,y0,x1,y1], index}`.
  `bbox` is **pixel coordinates** of the rendered page image. (`output_files.md:68-106`)
- **VLM**: two-level nested list (outer = pages, inner = blocks). Block =
  `{type, bbox, angle, score, block_tags, content, format, content_tags}`. `bbox` is
  **normalized `[0,1]` fractions of page width/height**, origin top-left
  (`output_files.md:509-540`).

### 3b. `middle.json` — canonical structured result
Top level: `{"pdf_info":[…], "_backend":"pipeline"|"vlm"|"office", "_version_name":"3.4.0"}`
(`model_json_to_middle_json.py:235`, `vlm/model_output_to_middle_json.py:79`). Note the
backend + version are stamped into every output — built-in conversion provenance.

Per page (`make_page_info_dict`, line 256): `{preproc_blocks, para_blocks, page_idx,
page_size:[w,h], discarded_blocks}` (VLM also `images/tables/interline_equations`).
Nesting:
```
page → block (Level-1: image|table|chart|code, or leaf text/title/…)
        ├─ type, bbox:[x0,y0,x1,y1], index (reading order), angle (0/90/180/270)
        ├─ blocks[]  (Level-2: *_body, *_caption, *_footnote)
        └─ lines[] → line{bbox, spans[]}
                       └─ span{bbox, type, content | html | image_path, score}
```
`bbox` in middle.json = **pixel coordinates** at the render scale (200 DPI; see §4).
Span `type` ∈ `image|table|chart|text|inline_equation|interline_equation`. Table span
carries `html`; image/chart/equation spans carry `image_path` (a cropped asset); text
spans carry `content` + OCR `score`. Block types enumerated in `utils/enum_class.py`
(`BlockType`, ~50 values incl. `image_caption`, `table_footnote`, `code`, `ref_text`,
`phonetic`, `aside_text`, `page_footnote`, …).

Document-level finalize (`finalize_middle_json`): formula-number merge → `para_split`
(paragraph grouping) → `cross_page_table_merge` → title leveling → block-type
normalization (`doc_title`→`title` level 1, `paragraph_title`→`title` level 2).

### 3c. `content_list.json` — flat, reading-order text projection
Built by `make_blocks_to_content_list` + `union_make`
(`pipeline_middle_json_mkcontent.py:609-1011`). A flat array in reading order. Each item:
`{type, …payload…, bbox, page_idx}`.
- `text` → `{type:"text", text, [text_level]}` (`text_level` 1/2/… = heading depth, absent/0 = body).
- `image` → `{type:"image", img_path, image_caption:[], image_footnote:[], [content], [sub_type]}`.
- `table` → `{type:"table", img_path, table_caption:[], table_footnote:[], table_body:"<html>…"}`.
- `equation` → `{type:"equation", img_path, text:"$$…$$", text_format:"latex"}`.
- `chart`/`code`/`list`/`index` and page-furniture (`header`/`footer`/`page_number`/
  `aside_text`/`page_footnote`) each have their own shape.
- **`bbox` here is rescaled to a normalized 0–1000 grid**:
  `_build_bbox` (lines 478-489) → `int(x0*1000/page_width)`, etc. (resolution-independent).
- `img_path` is `"{image_dir}/{md5}.jpg"` — **content-addressed**: filename = md5 of the
  cropped PIL bytes (`cut_image.py`, `cut_image_and_table` → `return_path` uses
  `page_img_md5`; `bytes_md5(page_pil_img.tobytes())`).

### 3d. `content_list_v2.json` — page-grouped, uniform `type+content`
`make_blocks_to_content_list_v2` (line 745+). Outer list grouped by page; each item is
`{type, content:{…}, bbox(0–1000), [anchor], [sub_type]}`. Inline text becomes **span
lists** (`merge_para_with_text_v2`): `{type:"text"|"equation_inline"|"phonetic", content}`,
and a `hyperlink` span carries `{content, url, [children]}`. Tables get
`table_type: simple|complex` + `table_nest_level`. Marked "development version, subject
to change" (`output_files.md:396`).

### 3e. Markdown (`.md`)
`make_blocks_to_markdown` (line 18+). Two modes: `MM_MD` (multimodal, default — embeds
`![](images/…)`, raw `<table>` HTML, `<details>` blocks for image content) and `NLP_MD`
(drops images/tables/charts). Headings via `#`*level, formulas via `$`/`$$` delimiters
(configurable, `get_latex_delimiter_config`). **The `.md` carries NO bbox / page / offset
metadata — locators exist only in content_list*/middle.json.**

### Locators back to source — summary
There are **bounding boxes + page index + reading-order index**, in three different
coordinate spaces depending on the file:
- pixel @200 DPI (middle.json, pipeline model.json),
- `[0,1]` fractions (VLM model.json),
- `[0,1000]` normalized grid (content_list / v2).
There are **no character offsets** into any canonical text stream, and **no timecodes**
(PDF/image domain). The "ground truth" anchor is geometric (bbox) + ordinal (`index`,
`page_idx`), plus content-hash image filenames.

---

## 4. Key parameters / thresholds / constants (with file refs)

- **Render DPI**: `DEFAULT_PDF_IMAGE_DPI = 200` (`utils/pdf_image_tools.py:35`). All
  middle.json pixel bboxes are at this scale.
- **Processing window**: 64 pages, sliding-window streaming, env
  `MINERU_PROCESSING_WINDOW_SIZE` (`config_reader.py:158-169`,
  `get_processing_window_size(default=64)`). Used by both pipeline and VLM to cap peak
  memory and stream output per-doc.
- **OCR min confidence**: `0.5` (`ocr_utils.py:11`). Post-OCR fallback uses
  `det_db_box_thresh=0.3` (`model_json_to_middle_json.py:175`).
- **OCR det params**: `det_db_box_thresh=0.5`, `det_db_unclip_ratio=1.6` (table OCR det,
  `batch_analyze.py:565-566`).
- **Layout input size**: `DEFAULT_IMAGE_SIZE=(800,800)` (`pp_doclayoutv2.py:30`);
  per-class confidence thresholds 0.4–0.5 (`DEFAULT_CLASS_THRESHOLDS`, lines 62-88);
  built-in **reading-order head** with `class_order` remap (lines 91-117).
- **Table wired/wireless gate**: wireless `cls_score < 0.9` → also run wired model
  (`batch_analyze.py:666-669`).
- **Batch sizes by VRAM** (`pipeline_analyze.py:354-363`): ≥32 GB → ratio 16, ≥16 → 8,
  ≥8 → 4, ≥6 → 2, else 1. Base sizes: `LAYOUT_BASE_BATCH_SIZE=1`, `MFR_BASE_BATCH_SIZE=16`,
  `OCR_DET_BASE_BATCH_SIZE=8` (`batch_analyze.py:38-41`).
- **VLM client defaults** (`vlm_analyze.py:71-75`): `max_concurrency=100`,
  `http_timeout=600s`, `max_retries=3`, `retry_backoff_factor=0.5`,
  `cache_max_entry_count=0.5` (lmdeploy).
- **LaTeX delimiters**: display `$$`, inline `$` (configurable, `mkcontent` lines 209-219).
- **Filename safety**: task stems truncated to `MAX_TASK_STEM_BYTES=200` UTF-8 bytes
  (`common.py:53`).

These are starting values in code, not asserted as tuned constants.

---

## 5. Performance / cost characteristics (as stated)

From `README.md` (claims, not benchmarks reproduced here):
- Pipeline backend scores **86.2 on OmniDocBench v1.5** (`README.md:142`); accuracy table
  uses OmniDocBench v1.6 end-to-end overall.
- **Min VRAM**: pipeline **4 GB**, VLM **8 GB**, OpenAI-API client **2 GB**
  (`README.md:264-268`). GPU accel needs Volta-or-later or Apple Silicon. RAM min 16 GB
  (rec 32 GB), disk min 20 GB.
- Native DOCX parsing claimed "tens of times" faster than DOCX→PDF→parse (`README.md:140`).
- Long-doc handling via sliding window + streaming writes (`README.md:156`); thread-safe
  multi-threaded inference; multi-GPU via `mineru-router`.
- Code logs throughput (`speed: … page/s`, `pipeline_analyze.py:322`) but **no committed
  page/s or $-cost number is found** — these are local models, so there is no per-token /
  per-page price in the repo. Technical reports referenced: arXiv 2509.22186 (MinerU2.5),
  2604.04771 (MinerU2.5-Pro).

---

## 6. Steal vs avoid for ugm

ugm = text-centric memory needing **versioned conversion + grounded locators**.

**Steal:**
- **Provenance stamping**: every `middle.json` carries `_backend` + `_version_name`
  (`init_middle_json`). This is exactly "which converter version produced this" — adopt
  verbatim for ugm's versioned-conversion contract.
- **Three-tier output split** mirrors a clean projection contract: raw `model.json`
  (untouched model output) → `middle.json` (full structural truth) → `content_list.json`
  (flat, reading-order text projection with locators). ugm's "versioned source +
  projection" maps directly onto this.
- **Resolution-independent locator**: the 0–1000 normalized bbox grid (`_build_bbox`)
  decouples the locator from render DPI. Good pattern for a grounding anchor that must
  survive re-rendering.
- **Content-addressed assets**: image filename = md5 of pixel bytes. Dedupes identical
  crops and makes asset references stable across re-runs.
- **Reading order as first-class `index`** plus `page_idx` on every block — a cheap
  ordinal locator independent of geometry.
- **Noise separation**: `discarded_blocks` (headers/footers/page numbers/margin notes) is
  kept but segregated from body, and caption/footnote/body are distinct block types. A
  text memory can drop furniture while keeping captions attached to figures.
- The **markdown-emission layer** (`*_middle_json_mkcontent.py`) is fully decoupled from
  the heavy CV/VLM models — reusable as a "structured-blocks → markdown" renderer without
  importing torch.

**Avoid / watch out:**
- **No character offsets.** Locators are geometric (bbox) + ordinal (`index`,`page_idx`),
  never a `[start,end)` range into a canonical text stream. If ugm wants offsets into
  versioned text, it must derive them itself (the `.md` it emits has no back-pointers at
  all). Plan a mapping step content_list → text-range, since MinerU won't give it.
- **Three inconsistent coordinate spaces** (pixel@200dpi / `[0,1]` / `[0,1000]`) across
  model.json, VLM model.json, and content_list. Any grounding consumer must track which
  space a bbox is in; do not assume uniformity.
- **Reading order is model-predicted** (PP-DocLayoutV2 reading-order head, or the VLM),
  not deterministic across model versions — reinforces the need to pin model version in
  the conversion record; treat `index` as version-scoped, not absolute truth.
- **Heavy runtime**: torch / vllm / lmdeploy / a 1.2B VLM, 4–8 GB VRAM. This is a parsing
  service, not a library to embed inside a text memory core. Consume its JSON outputs out
  of process; don't pull the dependency tree into ugm.
- **Markdown is lossy for grounding** (no bbox/page in `.md`). For grounded locators ugm
  must consume `content_list*`/`middle.json`, not the `.md`.
- **`content_list_v2` is explicitly unstable** ("development version, subject to change")
  — fine to mine for ideas (span-list inline model, hyperlink spans with `url`/`children`),
  but don't bind to its shape.
