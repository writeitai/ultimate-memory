# Docling — repo findings (code archaeology)

Source read: `_additional_context/docling/` — package `docling-slim` **v2.107.0**
(`pyproject.toml`). The unified output object **`DoclingDocument`** is defined in the
external dependency **`docling-core` v2.84.0** (`uv.lock:1355`), which is NOT vendored in
this repo (`find` for `docling_core/types/doc/document.py` returned nothing — **not found
locally**). Everything below about `DoclingDocument` is reconstructed from how `docling`
*constructs and consumes* it (the `add_*`/`ProvenanceItem`/`PictureMeta` call sites), which
is concrete and load-bearing, but the field-by-field pydantic schema lives in docling-core.

IBM/Zurich authored (`pyproject.toml` authors: Auer, Dolfi, Lysak, Livathinos, Nassar,
Vagenas, Staar).

---

## 1. Entry point & what `convert()` returns

`DocumentConverter.convert(source, ...)` (`docling/document_converter.py:402`) →
`convert_all()` → yields **`ConversionResult`**. Signature also takes
`max_num_pages=sys.maxsize`, `max_file_size=sys.maxsize`, `page_range=DEFAULT_PAGE_RANGE`,
`raises_on_error=True`, `headers`. There is also `convert_string(content, format, name)`
(`:546`) limited to MD / HTML / XML_DOCLANG.

`ConversionResult` (`docling/datamodel/document.py:563`) extends `ConversionAssets`
(`:370`). The full output object:

```
ConversionResult(ConversionAssets):
    input:      InputDocument         # file, document_hash, format, filesize, page_count, valid
    assembled:  AssembledUnit         # INTERNAL per-page elements (not the final doc)
    # inherited from ConversionAssets:
    version:    DoclingVersion        # docling/-core/-ibm-models/-parse versions + platform + python
    timestamp:  str|None              # ISO, set on save()
    status:     ConversionStatus      # pending/started/failure/success/partial_success/skipped
    errors:     list[ErrorItem]
    pages:      list[Page]            # INTERNAL per-page model (layout clusters, cells, predictions)
    timings:    dict[str, ProfilingItem]
    confidence: ConfidenceReport
    document:   DoclingDocument       # <-- THE OUTPUT, exported to MD/JSON/etc.
```

Two distinct layers matter for grounding:
- **`document` = `DoclingDocument`** — the durable, serialized output (refs, provenance).
- **`pages` / `assembled`** — internal scaffolding (pydantic models in
  `docling/datamodel/base_models.py`: `Cluster`, `TextElement`, `Table`, `FigureElement`,
  `ContainerElement`, `Page`, `PagePredictions`). These hold per-page layout clusters with
  bboxes/cells but are cleared/not the public contract. Don't build on them.

**Versioned conversion**: `ConversionAssets.save(filename)` (`document.py:407`) writes a ZIP
of separate JSON members: `version.json`, `status.json`, `errors.json`, `pages.json`,
`timings.json`, `confidence.json`, `document.json` (the latter via
`document.export_to_dict()`), plus a `timestamp.json`. `.load()` (`:479`) round-trips them.
`DoclingVersion` (`document.py:359`) records `docling_version`, `docling_slim_version`,
`docling_core_version`, `docling_ibm_models_version`, `docling_parse_version`,
`platform_str`, `py_lang_version` — i.e. provenance of *the converter itself*.

Exports (called on `result.document` in `docling/cli/main.py`): `save_as_json` (`:368`),
`save_as_markdown` (`:418`, `:428`), and `OutputFormat` enum (`base_models.py:97`):
`md, json, yaml, html, html_split_page, text, doctags, vtt, doclang`. The Markdown/DocTags
serializers themselves live in docling-core (**not found** in this repo).

---

## 2. The grounding / provenance schema (load-bearing for ugm)

Every body item in `DoclingDocument` is a `DocItem` carrying a list `prov:
list[ProvenanceItem]`. Construction is explicit throughout
`docling/utils/glm_utils.py` (the GLM→DoclingDocument builder):

```python
# docling/utils/glm_utils.py:157
prov = ProvenanceItem(
    page_no=pelem["page"],
    charspan=(0, len(text)),
    bbox=BoundingBox.from_tuple(pelem["bbox"], origin=CoordOrigin.BOTTOMLEFT),
)
doc.add_text(label=..., text=text, prov=prov)        # also add_picture/add_table/add_heading/...
```

So `ProvenanceItem` = **`{ page_no: int, charspan: (int,int), bbox: BoundingBox }`**.

- **`bbox`** = `BoundingBox(l, t, r, b, coord_origin)` (`docling-core`, used everywhere).
  Origin is explicit: `CoordOrigin.BOTTOMLEFT` (PDF-native, from the parser) or `TOPLEFT`.
  Conversions are first-class: `bbox.to_top_left_origin(page_height)`, `.scaled(scale)`,
  `.area()`, `.intersection_over_self()`, `.to_tuple()`
  (`models/stages/page_assemble/page_assemble_model.py:89`,
  `pipeline/standard_pdf_pipeline.py:1041`). Page geometry is in `document.pages[page_no]`
  (`PageItem.size`, `.image`).
- **`charspan`** = a `(start, end)` character range **local to that item's own text**, NOT a
  global document character offset. Evidence: text items get `charspan=(0, len(text))`
  (`glm_utils.py:159`); captions get `charspan=tuple(nelem["span"])` then the text is sliced
  `caption["text"][span_i:span_j]` (`glm_utils.py:135-153`). There is **no document-global
  character offset** stored, and **no stored map from the exported Markdown string back to
  element offsets** — `export_to_markdown` is a separate render pass. This is the single most
  important gap for a text-centric grounding system.

`DocItemLabel` taxonomy (used as the cluster/layout labels,
`document.py:82`, `models/stages/layout/layout_model.py:29`): TITLE, SECTION_HEADER,
TEXT, PARAGRAPH, LIST_ITEM, CAPTION, PAGE_HEADER, PAGE_FOOTER, FOOTNOTE, CODE, FORMULA,
TABLE, DOCUMENT_INDEX, PICTURE, FORM, KEY_VALUE_REGION, CHECKBOX_SELECTED/UNSELECTED.
Layout groupings: `TEXT_ELEM_LABELS`, `TABLE_LABELS=[TABLE, DOCUMENT_INDEX]`,
`FIGURE_LABEL=PICTURE`, `CONTAINER_LABELS=[FORM, KEY_VALUE_REGION]`.

---

## 3. How figures / charts / tables are represented

- **Tables** → `TableItem` with `TableData` (internal `Table` model:
  `otsl_seq: list[str]`, `num_rows`, `num_cols`, `orientation`, `table_cells:
  list[TableCell]`; `base_models.py:338`). OTSL = a structure token sequence for the cell
  grid. `prov` (bbox + page) attached. Caption refs linked. Table-structure model is a
  separate stage (`models/stages/table_structure/`).
- **Pictures/figures** → `PictureItem` with `prov` (single bbox; code asserts "PictureItems
  have at most a single provenance", `picture_description_base_model.py:82`), `captions`
  (list of refs to caption text items, `glm_utils.py:165`), and a structured `meta:
  PictureMeta`:
  - `meta.classification = PictureClassificationMetaField(predictions=[
    PictureClassificationPrediction(class_name, confidence, created_by)])`
    (`document_picture_classifier.py:193-208`).
  - `meta.description = DescriptionMetaField(text=..., created_by=provenance)`; optional
    `usage` custom field under namespace `"docling"`/name `"usage"`
    (`picture_description_base_model.py:113-125`).
  - Deprecated parallel `item.annotations` list (`PictureClassificationData`,
    `PictureDescriptionData`) still written when `_keep_deprecated_annotations=True`
    (default True; flagged FIXME to remove).
- **Charts** → handled as pictures plus a **chart-extraction** stage
  (`models/stages/chart_extraction/`). `ChartExtractionModelOptions`
  (`datamodel/chart_extraction_options.py`): model default
  `ChartExtractionModelKind.GRANITE_VISION_V4`; `chart2csv=True` (default), `chart2code=False`,
  `chart2summary=False`. Converts bar/pie/line charts to tabular CSV. Enabling
  `do_chart_extraction` auto-enables picture classification.
- **Image bytes**: `ImageRef.from_pil(pil, dpi=int(72*images_scale))` attached to
  `PageItem.image` (full page) and to `PictureItem.image`/`TableItem.image` by **cropping the
  page raster with the element's `prov[0].bbox`** (`standard_pdf_pipeline.py:1041-1052`).
  Only emitted when `generate_page_images` / `generate_picture_images` are on (both default
  **False**).

---

## 4. Pipeline & stages

Pipelines (`docling/pipeline/`): `StandardPdfPipeline` (threaded, default for PDF/IMAGE/
METS_GBS), `VlmPipeline` (whole-page VLM), `SimplePipeline` (DOCX/PPTX/XLSX/ODF/HTML/MD/CSV/
XML/VTT/LaTeX/Email/EPUB/JSON), `AsrPipeline` (audio), `legacy_standard_pdf_pipeline`.
Default format→pipeline/backend wiring in `document_converter.py:235-271`.

StandardPdfPipeline is a thread-safe, back-pressured, per-page staged pipeline
(`standard_pdf_pipeline.py:1-13` docstring; bounded `ThreadedQueue`, per-run `run_id`).
Stage models (`docling/models/stages/`): `page_preprocessing` → `ocr` → `layout` →
`table_structure` → `page_assemble` → `reading_order` → `heading_hierarchy`, plus
enrichment stages `code_formula`, `picture_classifier`, `picture_description`,
`chart_extraction`, and `vlm_convert`. Document assembly:
`_assemble_document` (`:991`) builds `AssembledUnit`, then
`reading_order_model(conv_res)` produces the `DoclingDocument`, then
`heading_hierarchy_model`. **Failed pages are still added to `document.pages`** to preserve
page numbering / page-break markers (`:1086`).

Backends (`docling/backend/`) — one per input family: `docling_parse_backend` (PDF, default
`DoclingParseDocumentBackend`), `pypdfium2_backend`, `msword_backend` (110KB),
`mspowerpoint_backend`, `msexcel_backend`, `html_backend` (185KB), `md_backend`,
`opendocument_backend`, `epub_backend`, `asciidoc_backend`, `csv_backend`, `webvtt_backend`,
`email_backend`, `image_backend`, `mets_gbs_backend`, plus `xml/` (USPTO/JATS/XBRL/DocLang),
`latex/`, `json/`. Input formats enum (`base_models.py:69`) covers 20+ formats. Format
detection is content+extension based (`document.py:_guess_format`, magic-byte + ZIP-member
inspection for OOXML/ODF).

---

## 5. Key params / thresholds / model names (concrete defaults)

**Layout** (`datamodel/layout_model_specs.py`): default model **`DOCLING_LAYOUT_HERON`**
(`pipeline_options.py:1427`, repo `docling-project/docling-layout-heron`, revision `main`).
Alternatives: `heron_101`, `egret_medium/large/xlarge`, `docling_layout_v2`
(`docling-project/docling-layout-old`). Runs via `docling_ibm_models.LayoutPredictor`
(`layout_model.py:56`). Devices: CPU/CUDA/MPS/XPU.

**OCR** (`models/base_ocr_model.py`, `pipeline_options.py:164`): `do_ocr` default... PDF
pipeline default `ocr_options = OcrAutoOptions()` (`:1700`) — `kind="auto"`, probes runtime
and picks **EasyOCR if installed** (`auto_ocr_model.py:117`), else falls back. Engines
available: easyocr, tesseract (cli + lib), rapidocr, ocr_mac, nemotron, kserve_v2.
Routing constants: `BITMAP_COVERAGE_TRESHOLD = 0.75` (full-page OCR if bitmaps cover >75% of
page), `bitmap_area_threshold` default **0.05** (skip bitmaps under 5% page area),
`force_full_page_ocr` default False. OCR cells overlapping programmatic text cells are
dropped via an **R-tree** spatial index (`_filter_ocr_cells`, `:116`).

**Picture classification** (`do_picture_classification` default **False**;
`pipeline_options.py:1239`): model spec `IMAGE_CLASSIFICATION_DOCUMENT_FIGURE`,
`images_scale = 2`, engines transformers / onnxruntime / api_kserve_v2.

**Picture description** (`do_picture_description` default **False**;
`pipeline_options.py:617-696, 1257`): default preset **smolvlm** =
`HuggingFaceTB/SmolVLM-256M-Instruct` (`:907`); granite preset =
`ibm-granite/granite-vision-3.3-2b`, prompt `"What is shown in this image?"` (`:917`).
`scale=2.0`, `batch_size=8`, **`picture_area_threshold=0.05`** (pictures < 5% of page area
are NOT described, `:658` + gate in `picture_description_base_model.py:81-89`),
`classification_allow/deny` + `classification_min_confidence=0.0` filtering. API backend
(`PictureDescriptionApiModel`) requires `enable_remote_services=True` or raises
`OperationNotAllowed`.

**Image output**: `images_scale` default **1.0** (`pipeline_options.py:1721`);
DPI = `72 * images_scale`. `generate_page_images`/`generate_picture_images` default False.

**Confidence** (`base_models.py:504-647`): per-page `PageConfidenceScores{parse, layout,
table, ocr}`; grade bands POOR `<0.5`, FAIR `<0.8`, GOOD `<0.9`, EXCELLENT `>=0.9`.
Document `parse_score` uses the 10th percentile (worst-10%) of pages
(`standard_pdf_pipeline.py:1068`); `low_score` uses the 5% quantile.

**Code/formula enrichment**: `do_code_enrichment`, `do_formula_enrichment` (default False),
VLM-based (`code_formula` stage). VLM-convert presets (`pipeline_options.py:1006-1023`)
include SmolDocling, Granite-Docling, DeepSeek-OCR, Pixtral, GOT-OCR, Phi4, Qwen,
Nanonets-OCR2, Gemma 12B/27B, Dolphin, GLM-OCR, LightOnOCR, Falcon-OCR, Chandra, dots-OCR.

---

## 6. Performance / cost characteristics (as stated in code)

- Doc-level batching/concurrency via `settings.perf.doc_batch_size` /
  `doc_batch_concurrency` (ThreadPoolExecutor, `document_converter.py:625-656`).
- StandardPdfPipeline parallelizes *stages and models* across pages with bounded queues and
  explicit back-pressure (docstring `standard_pdf_pipeline.py:1-13`); models initialized once
  per pipeline instance, pipelines cached by `(class, md5(options))`
  (`document_converter.py:374`, `_get_pipeline`).
- Limits: `DocumentLimits(max_num_pages, max_file_size, page_range)`; oversize/over-page docs
  rejected with categorized `ErrorItem` (`FailureCategory.POLICY`) rather than crashing
  (`document.py:198-215, 281-289`).
- `ProfilingItem` timings captured per stage (`timings` dict). No hardware throughput numbers
  or $-costs are stated in the code — **not found** (perf scripts exist in `perfs/` but no
  committed benchmark numbers).

---

## 7. Steal vs avoid for ugm (text-centric memory needing versioned conversion + grounded locators)

**Steal:**
- **`ProvenanceItem` shape** `{page_no, charspan, bbox(origin)}` attached per element — clean,
  serializable grounding primitive. Mirror it.
- **Versioned conversion assets**: `DoclingVersion` capturing converter/model/parser versions
  + platform, and the `save()`/`load()` ZIP-of-JSON split (`version/status/errors/pages/
  timings/confidence/document.json`). Directly maps to ugm's "versioned conversion" need —
  re-conversions are diffable and the toolchain version is part of the record.
- **Per-page confidence scoring** (parse/layout/table/ocr → grade) with worst-percentile
  document aggregation — a ready-made quality gate for deciding when to re-OCR / re-convert.
- **Unified `DoclingDocument`** as the single text contract with refs + groups + reading
  order + heading hierarchy computed as explicit stages; pictures carry structured `meta`
  (classification + description + usage) rather than free text.
- **Failed-page preservation** in `document.pages` to keep stable page indexing — good
  pattern for stable locators across re-runs.
- The **OCR routing heuristics** (bitmap coverage 0.75 / area 0.05, R-tree dedup of OCR vs
  native text) if ugm ever ingests scanned PDFs.

**Avoid / watch out:**
- **`charspan` is element-local, not document-global**, and there is **no stored map from the
  serialized Markdown back to element char offsets**. For ugm grounding you must compute and
  persist global offsets yourself during serialization (or maintain an element↔span index);
  Docling does not give you "Markdown byte/char range ↔ source bbox" out of the box.
- **VLM / dots / chandra paths zero out grounding**: bbox is faked to `(0,0,0,0)` and
  `charspan=[0,0]` (`pipeline/vlm_pipeline.py:706-711`, `utils/dots_utils.py:172`,
  `utils/chandra_utils.py:301`). If ugm needs bboxes, the whole-page VLM pipeline is
  unusable for grounding — stick to the StandardPdfPipeline (layout+OCR) path.
- Don't depend on the **internal per-page models** (`base_models.py` `Cluster`/`Page`/
  `AssembledUnit`) — they're scaffolding, partly cleared after assembly, and not the public
  contract.
- `DoclingDocument`'s exact pydantic schema lives in **docling-core** (separate repo,
  v2.84.0). Pin/track that version; this `docling` repo only constructs and consumes it.
- Deprecated `annotations` list on pictures coexists with the new `meta` fields — read from
  `meta.classification` / `meta.description`, not `annotations`.
- Heavy optional deps for full multimodal (onnxruntime, mlx-vlm/mlx-whisper on Apple silicon,
  gliner, transformers VLMs). For a text-centric system most of this is avoidable; enrichment
  (classification/description/chart/code/formula) is **off by default**.
