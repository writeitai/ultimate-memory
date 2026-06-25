# F2 — The E0 conversion contract for media (image + video)

Design-fit note for the multimodal extension of `ugm`. Scope: the **E0 `convert()` contract** for
an IMAGE and (the hard case) a VIDEO. This is full-scope design at the millions-of-documents target,
not an MVP — build-sequencing is out of scope here. Numbers (thresholds, frame budgets, model picks)
are starting points to measure (CLAUDE.md Rule 2), not committed constants.

Research base: `web_research/M1`–`M6`, `repo_findings/{pyscenedetect,whisperx,docling,mineru,colpali}.md`.
Sibling questions (cross-referenced, not re-answered here): grounding generalization in depth (F3),
P1 multimodal retrieval (F4), media claims/observations/entities (F5), privacy/deletion (F7).

---

## 1. Verdict / recommendation

**Generalize the existing E0 contract; do not invent a new plane.** Today
`convert(bytes, mime, hints) -> {markdown, blocks[] with char offsets}` (D38) and the per-document
structure tree (PageIndex, D39) already have exactly the right bones. Media slots in by **two
generalizations and nothing else**:

1. **The converter return type grows to `{markdown, blocks[], structure, manifest}`**, where each
   block carries a **dual locator**: a mandatory `md_span` (char offsets into a deterministically
   **linearized markdown**, so the E1→E2→E3 text pipeline runs *byte-for-byte unchanged*) **plus** a
   **polymorphic native locator** — `text:{char_span}` | `image:{page, bbox}` | `av:{t_start, t_end,
   track, speaker?}` — which is the true source anchor (D32 generalized).
2. **`structure` (PageIndex, D39) generalizes to a per-document tree whose nodes carry the polymorphic
   locator.** For a document it is the section tree; for an image/page-set it is a **page→region
   tree**; for a video it is a **scene/chapter tree with timecode spans + roles + summaries** — the
   "PageIndex analogue" the brief asks for. I call the persisted video form the **MediaIndex**.

A video is therefore **not** a single markdown blob. The converter runs a **cheap-first cascade**
(D4/D25) that produces a multi-track timeline — deterministic shot/scene segmentation, a word-timecoded
diarized ASR transcript, on-screen-text OCR on deduplicated keyframes, and **selective** VLM captions
(one keyframe per shot/scene, the *only* expensive step) — then **linearizes** that timeline into the
markdown E1 chunks along and E2 reads. Every model-derived stage is **independently versioned** in a
`conversion_manifest` and **replayed from stored artifacts** on rebuild (D7/D33); raw bytes stay the
immutable ground truth (D1/D37). Frontier native-video models (Gemini) are an **escalation reasoner
over bounded clips**, never the ingestion substrate (the per-query token cost is the wrong place to
spend for a store queried many times — M2 §2.2).

This is hybrid choice (c) from the brief at the conversion layer: **text pipeline is canonical and
auditable; the native locator preserves exact provenance; the visual index is a separate P1 projection
(F4)**. It keeps one belief home (D6), one grounding apparatus (D32), and full rebuildability (D7).

---

## 2. The design, concretely

### 2.1 The generalized `convert()` contract

```
convert(bytes, mime, hints) -> {
  markdown:  str,            # deterministic LINEARIZATION; the only thing E1/E2 read
  blocks:    Block[],        # content units, each dual-located
  structure: StructureTree,  # per-doc tree (section | page→region | scene/chapter)
  manifest:  ConversionManifest   # every stage's tool+version+params+prompt+artifact_uris (D7/D33)
}

Block = {
  block_id, kind, role,
  md_span: { start: int, end: int },     # offsets into `markdown` — ALWAYS present (uniform pipeline)
  locator: Locator,                      # polymorphic native anchor (below)
  text?:    str,                         # verbatim source text (OCR / ASR) OR model caption text
  payload?: { table_html? | latex? | chart_csv? | … },
  provenance: { producer, producer_version, prompt_version?, model?, asserted: bool }
  # asserted=false → verbatim source (OCR/ASR);  asserted=true → model rewrite (VLM caption)
}

Locator =                                  # tagged union — the D32 generalization
  | { kind: "text",  char_span: [start, end] }
  | { kind: "image", page_no: int, bbox: [l, t, r, b], coord_space: "norm_0_1000" }
  | { kind: "av",    t_start_pts: int, t_end_pts: int, time_base: [num, den],
                     track: "video"|"audio"|"onscreen", speaker?: str, keyframe_uri?: str, bbox? }
```

Two invariants make this work:

- **`md_span` is mandatory for every block, of every modality.** The converter emits a single
  linearized markdown string and every block points into it. This is why **E1 chunking and E2/D32
  grounding do not change** — they see char offsets exactly as today. The native `locator` is
  *additive* provenance, not a replacement.
- **`provenance.asserted` cleanly splits verbatim source from model rewrite** (the M5 STEAL-3 crux):
  OCR text and ASR transcript are *real source bodies* (`asserted=false`); VLM captions are *model
  assertions about a region/frame* (`asserted=true`). D32 routes them differently (§3.2 below).

The native locator for time is an **exact rational PTS + `time_base`** (e.g. `Fraction(24000,1001)`),
**never a frame number** — frame indices drift on variable-framerate video, PTS does not (pyscenedetect
findings §6; whisperx findings §6).

### 2.2 IMAGE contract (a 3-rung cheap-first cascade)

An image (standalone photo, screenshot, slide, scanned page) is the degenerate single-page case of the
document structure tree. The structure tree's top level is **pages**; each page has a **region
sub-tree**; a single image gets a **synthetic root page** (mirrors D39's synthetic-root rule).

| Rung | What | Tool (default → escalation) | Cost | Deterministic? | Emits |
|---|---|---|---|---|---|
| **0** Read (always) | layout + OCR + tables→HTML + formulas→LaTeX + reading order | MinerU `pipeline`/`hybrid`, Docling, dots.ocr (self-host) → Mistral OCR (hosted tail) | ~$0.0002/page self-host (M1) | yes-in-spirit (transcribing) | `text/table/formula` blocks, each `image:{page,bbox,reading_order}`; markdown |
| **1** Describe (selective) | grounded prose for `picture`/`chart`/`figure` regions; chart→table | Gemini 2.5/3 Flash or Qwen3-VL-8B (self-host) | ~$1–3 / 1k regions (M1) | **no** (model rewrite) | `figure_description` block, `asserted=true`, anchored to the region bbox, `model_version` |
| **2** Escalate (flagged tail) | hard charts / dense infographics / degraded scans | Claude Opus 4.8 / Gemini 3 Pro | ~$0.01–0.03/region | no | same shape, higher-quality caption |

Rung 1 only fires on regions Rung 0 marked non-text (`picture`/`chart`/`figure`); Rung 2 only on the
self-flagged low-confidence minority. **Spend scales with non-text regions and ambiguity, not pixel
count** (D4/D25). `block.kind` ∈ `{text, table, formula, picture, chart, figure_description}`.

### 2.3 VIDEO contract — the multi-track cascade and the MediaIndex

Video is a temporal, multi-track medium (video stream(s) + audio stream(s) + a derived on-screen-text
"track"). The converter produces a **MediaIndex** (the scene/chapter tree — the video PageIndex
analogue) plus the linearized markdown and dual-located blocks. The cascade is ordered strictly
cheapest→most-expensive (D4); each stage is gated by the previous and **independently versioned**:

| # | Stage | Tool (default → escalation) | Cost class | Deterministic? | Model call? | Version stamp |
|---|---|---|---|---|---|---|
| 1 | **Demux + probe** | ffmpeg | CPU, ~free | yes | no | `container_probe_version` |
| 2 | **Shot detection** | PySceneDetect `ContentDetector`/`AdaptiveDetector` → TransNetV2 (hard/high-motion) | CPU, ~free (~22–37 s/long-clip) | yes | no (TransNetV2=ONNX, escalation) | `shot_detect_version` (+detector+params) |
| 3 | **ASR + word-align + diarization** | WhisperX (faster-whisper large-v3 + wav2vec2 + pyannote) → NeMo Canary-1B-v2 (Czech/accuracy) / Parakeet-v3 (throughput); Deepgram Nova-3 (no-GPU API) | GPU-cheap (~70× RT, ~$0.005–0.05/audio-hr) | yes (pinned model) | yes (cheap, deterministic-given-version) | `asr_version` (+model+align+diarize) |
| 4 | **Keyframe select + near-dup collapse** | PySceneDetect deterministic sampling + pHash | CPU, ~free | yes | no | `keyframe_policy_version` |
| 5 | **OCR on dedup'd keyframes** | MinerU/Docling/dots.ocr | cheap | yes-in-spirit | no | `ocr_version` |
| 6 | **Redact** (faces + on-screen PII) | deface/CenterFace + Presidio | cheap | yes-in-spirit | no | `redactor_version` |
| 7 | **Scene merge** (shots→scenes by visual+transcript similarity) | deterministic clustering | CPU, ~free | yes | no | `scene_merge_version` |
| 8 | **Selective VLM captioning** (1 keyframe / shot or scene) | Qwen2.5-VL / LLaVA-Video (self-host) → Gemini (escalation) | **the cost center**; cents/video-hr, budget = **shot count not duration** | **no** | **yes (expensive, nondeterministic)** | `vlm_caption_version` (+prompt+sample policy) |
| 9 | **Chapter roll-up** (scenes→chapters: titles/summaries/roles) | small text LLM | cheap text call | no | yes (cheap) | `structurer_version` (= D39 structurer) |
| 10 | **Escalation** (bounded clip → native-video reasoner) | Gemini, scene-bounded to stay cheap/low-res | per-query, ambiguity-gated | no | yes (rare) | `escalation_version` |

Stages 1–7 are the **convert** sub-worker (D36) producing the deterministic multi-track timeline +
captions; stages 9 (and the placement hint) are the **structure** sub-worker — the same LLM
"structurer" D39 already defines, here rolling scenes into a chapter tree with roles/summaries. The
E0 chain `ingest → convert → structure → crossref` (D36) is **unchanged in shape**.

Redaction (stage 6) sits *before* captioning/mounting so the redacted derivative is the canonical
artifact and the raw bytes stay quarantined (detail in F7); it is listed here because it gates what
later stages and P1 ever see.

**The MediaIndex (`mediaindex.json` sidecar — the video PageIndex analogue):**

```
MediaIndex = {
  video_id, content_hash, duration_pts, time_base, fps_rational, raw_uri, tracks: Track[],
  chapters: [                              # stage 9 LLM roll-up — the "sections"
    { chapter_id, node_path, title, summary, role, t_start_pts, t_end_pts,
      scenes: [                            # stage 7 merged shots — the structural backbone E1 chunks along
        { scene_id, node_path, t_start_pts, t_end_pts,
          keyframe_uris: [...], keyframe_phash,
          visual_caption: { text, model, model_version, prompt_version },   # stage 8, asserted=true
          ocr_runs:  [ { text, bbox, frame_pts, ocr_version } ],            # stage 5, asserted=false
          shots:     [ { shot_id, t_start_pts, t_end_pts } ] }              # stage 2
      ] }
  ],
  transcript: [                            # stage 3 — the verbatim text pipeline, asserted=false
    { seg_id, t_start_pts, t_end_pts, speaker, text,
      words: [ { word, t_start_pts, t_end_pts, score } ] }
  ],
  conversion_manifest: { <every stage>: { tool, version, params, prompt_version?, artifact_uris } }
}
```

**The linearized markdown** E1/E2 consume is a **deterministic flattening** of the MediaIndex (sort by
`t_start_pts`, then a fixed track priority for ties), e.g.:

```
# Chapter 1 — Introduction   ⟨00:00:00.000–00:04:30.000⟩

## Scene 1.1   ⟨00:00:00.000–00:01:12.000⟩
[visual: A presenter at a podium; slide titled "Q3 Results".]   (qwen2.5-vl-7b@v3, asserted)
[on-screen: Q3 Results — Revenue $5M]                            (ocr@v2, bbox=…, verbatim)
SPEAKER_00 ⟨00:00:03.100–00:00:11.480⟩: Welcome everyone, today we'll cover the third quarter.
SPEAKER_01 ⟨00:00:12.000–00:00:20.330⟩: …
```

Every line is a `Block`: its `md_span` indexes this string (uniform pipeline); its `locator` is the
`av:{t_start,t_end,track,speaker,keyframe?}` (true anchor). A claim E2 extracts therefore grounds to a
**timecode (+ optional keyframe bbox)**, not merely to a generated sentence — auditability *improves*
over text-only.

### 2.4 Where artifacts and the queryable index land (D37)

**Storage split, unchanged in rule, generalized in content:**

```
raw bucket  (immutable, cold, strict IAM, NEVER mounted):
  gs://ugm-<dep>-raw/<doc_id>/<content_hash>/original.<ext>     # the source video/image bytes

artifacts bucket (standard class, mountable via P3):
  gs://ugm-<dep>-artifacts/<doc_id>/<content_hash>/
    document.md            # the linearization (E1/E2 read this)
    conversion.json        # blocks[] with dual locators + transcript (the "blocks + offsets" body)
    mediaindex.json        # the scene/chapter tree sidecar (video) | pageindex.json (doc/image)
    keyframes/<phash>.jpg   # content-addressed redacted keyframe crops (P1 embed + audit + caption src)
    meta.json
```

Per D37, **Postgres never stores bodies** — transcript text, captions, and OCR live in
`conversion.json`/`mediaindex.json` in GCS. Postgres holds only the **queryable index**:

- **`documents`** gains media columns (all `NULL` for non-media): `duration_pts, time_base,
  fps_rational, n_streams`, plus the per-stage version stamps (`shot_detect_version, asr_version,
  keyframe_policy_version, ocr_version, redactor_version, scene_merge_version, vlm_caption_version,
  escalation_version`) — generalizing the existing `converter_*`/`structurer_*` provenance columns.
- **`document_sections` generalizes to the polymorphic per-document structure tree** (the single most
  load-bearing schema delta):

```
document_sections(
  section_id, doc_id, parent_section_id, node_path,     -- '0' chapter / '0.2' scene / '0.2.1' shot
  title, role, ordinal,
  locator_kind,                       -- 'text' | 'image_region' | 'av_segment'   ← NEW discriminator
  char_start, char_end,               -- span into document.md — ALWAYS present (uniform E1/E2 pipeline)
  -- native locator, additive, nullable-by-kind:
  page_no, bbox, coord_space,         -- image_region
  t_start_pts, t_end_pts, time_base,  -- av_segment
  track, keyframe_uri, keyframe_phash,
  summary, placement_path, structurer_version)
```

`role` extends D39's enum with video kinds (`chapter, scene, shot, transcript, visual_caption,
onscreen_text, intro, demo, qa, credits`) so E2 Selection can drop low-value roles (e.g. `credits`,
`onscreen_text` boilerplate) at proposition grain — exactly D25's "section role fed into E2 Selection,
not a binary pre-skip." **Keeping `char_start/char_end` mandatory across all modalities is what lets
the pipeline stay modality-blind.**

---

## 3. How it preserves ugm invariants

- **D37 (storage split + Postgres-metadata-only).** Raw video bytes → raw bucket (immutable, never
  mounted); linearized markdown + `conversion.json` + `mediaindex.json` + keyframe crops → artifacts;
  Postgres gets metadata + the section index only. Bodies (transcript/captions) never enter Postgres.
- **D38 (versioned, pluggable converter router) — generalized, not replaced.** The router gains media
  routes (image → OCR+VLM cascade §2.2; `video/*` → the cascade §2.3). The return type grows to
  `{markdown, blocks[], structure, manifest}`; the *load-bearing* `{markdown, blocks[] with offsets}`
  is a strict subset, so existing text routes are untouched. A version bump on any stage re-converts
  exactly the affected docs (D7) and rebuilds downstream.
- **D39 (per-document structure tree) — generalized to the MediaIndex.** The scene/chapter tree is the
  structural backbone E1 chunks along (one scene ≈ one chunk; never split mid-scene) and the path/role
  signal E2 reads — identical role to PageIndex sections, with temporal locators.
- **D32 (grounding) — generalized to a polymorphic locator, apparatus unchanged.** §3.2 below.
- **D7 / D33 (versioned, replay-from-storage; never nondeterministically re-derived).** ASR and VLM
  captions are nondeterministic; both are persisted artifacts stamped with model+version+prompt+policy
  in the `conversion_manifest`. On a plain rebuild they are **replayed from storage**, never re-run; on
  a stage version bump, only that stage (and downstream) re-runs while upstream deterministic outputs
  are reused — the D33 discipline (stored output + decisions, never re-call the model) applied to media.
- **D36 (E0 sub-worker chain) — shape unchanged.** `ingest → convert → structure → crossref`; the
  media weight lives inside `convert` (stages 1–8) and the LLM roll-up lives in `structure` (stage 9 =
  the D39 structurer). Each sub-worker stays separately idempotent on `content_hash + its own version`
  (D12).
- **D4 / D25 (cheap-first; no pre-extraction value gate).** The deterministic pipeline (shots + ASR + OCR)
  is near-free and carries most semantics; the VLM is the single gated cost center, bounded by **shot
  count, not duration**. There is still **no value gate** — junk-control stays in E2 Selection in-call,
  now also able to drop `credits`/`onscreen_text` roles at proposition grain.
- **D6 / D8 (one belief home; vectors in Lance not the graph).** The converter produces *text + a
  locator*, not beliefs. Visual retrieval (keyframe/scene embeddings, ColPali-style page images) is a
  **separate P1/Lance projection** (F4), holding no authority, rebuildable from the persisted keyframe
  crops — never on the P2 graph.
- **D40 / P3.** A video document gets a generated stub in the corpus filesystem like any document; the
  **mounted** artifacts are the **redacted** derivatives, never the raw bytes.

### 3.2 Grounding the two kinds of media-text (D32 generalized)

Anchor/window-membership generalize by the `provenance.asserted` split:

- **Verbatim media-text (ASR transcript, OCR) — `asserted=false` — strict D32.** The span is a real
  slice of the transcript/OCR body, so **anchor** = the slice is in-bounds and **window-membership** =
  the quoted text verbatim-exists in that segment's transcript/OCR — *exactly as today*, with a
  timecode/bbox attached. ASR maps onto D32's "*X said* Y entails *X said Y*, not *Y*" rule directly
  (diarization gives the speaker). This is fully auditable.
- **VLM captions — `asserted=true` — model assertion, never a verbatim span.** A caption is a lossy
  nondeterministic rewrite, so it enters E2 as `added_context[]` with named source
  `vlm_caption(scene S @ t)`, grounded by D32 **layer-3 entailment** + **layer-4 sampled audit** + the
  **timecode/keyframe-bbox provenance**, and is **origin-stamped (D42)** so confidence math never
  counts a caption as independent corroboration. The audit guarantee is "claim derived by model
  M(version v) from the frame(s) at this timecode/region," and the keyframe crop is persisted and
  replayable.
- **Anchor verification for media** = locator in-bounds: a timecode within `[0, duration]` and
  overlapping a detected shot; a bbox within the frame/page and overlapping a detected region. A
  caption that references out-of-bounds pixels or a timecode past the end fails anchor — the
  media-equivalent of a non-substring span.

(Full grounding treatment is F3; this section states only what the conversion contract must guarantee.)

---

## 4. Risks / what to measure (spikes)

1. **VFR timecode drift.** Canonical locator must be exact rational PTS + `time_base`, never
   `frame_num` (drifts on variable-framerate; pyscenedetect §6, whisperx §6). Spike: round-trip
   PTS→display→PTS on a VFR corpus slice.
2. **Locator stability across re-conversion.** A `shot_detect_version`/`scene_merge_version` bump
   shifts scene boundaries → `section_id`s and timecode spans move. Pin locators to the producing
   stage version; downstream references are version-scoped. Spike: diff two converter versions on the
   same video, measure reference churn.
3. **Linearization determinism.** Interleaving order of caption/OCR/transcript must be a total order
   given fixed versions (sort by `t_start_pts`, then fixed track priority). Spike: verify byte-stable
   markdown across re-runs at pinned versions (the D33 replay relies on this).
4. **Shot-count variance (the budget driver).** Shots/hour vary 10×–100× by content (talking-head vs
   action). Caption budget = shots, so cost variance is large. Spike: measure shot-count distribution
   on the real mix; set a per-doc caption cap + escalation policy; consider scene-level (merged) rather
   than shot-level captioning for high-cut content.
5. **ASR/diarization on real video** (music, overlap, far-field) is materially worse than clean-benchmark
   DER (M3 §3). Spike: measure WER/DER on representative content; wire the Canary-1B-v2 ASR swap for
   Czech (7.86% vs 11.33% Whisper) and Deepgram Nova-3 as the no-GPU fallback.
6. **Keyframe near-dup threshold.** pHash collapse of held/static frames (slides) is the biggest free
   win for screen recordings; threshold (PySceneDetect `HashDetector` ~0.395) is corpus-tuned. Spike:
   tune on slide-deck/screen-recording slice.
7. **Selective-caption quality vs frontier.** Self-hosted Qwen2.5-VL/LLaVA-Video captions vs Gemini
   escalation — measure on a golden caption set; set the escalation trigger (self-reported low
   confidence / high-value scene).
8. **MediaIndex size for long video.** A multi-hour video's `mediaindex.json` + transcript can be large;
   confirm it stays a GCS sidecar (not Postgres) and that P3 stubs reference rather than inline it.
9. **Keyframe storage vs re-extract.** Recommend storing content-addressed redacted crops (deterministic
   anchor for D33 replay + P1 embedding + redaction audit) over re-extracting on rebuild; measure the
   storage cost at scale.
10. **Redaction recall** (a missed face is an un-redacted face) — golden set; detail in F7.

---

## 5. Proposed decisions (continue from D44) and design-doc deltas

**Proposed decisions:**

- **D45 — Media is transcoded-to-text at E0; the `convert()` contract generalizes to
  `{markdown, blocks[], structure, manifest}` with a dual locator.** Every block carries a mandatory
  `md_span` into a deterministically linearized markdown (so the E1→E2→E3 pipeline is unchanged) plus a
  polymorphic native `Locator` (`text|image|av`). Hybrid choice (c): text pipeline canonical + native
  locator for provenance; native media is never a parallel belief track (D6 preserved).
- **D46 — The video PageIndex analogue is the MediaIndex scene/chapter tree.** Deterministic shots
  (PySceneDetect) → merged scenes → LLM chapter roll-up (the D39 structurer), persisted as a
  `mediaindex.json` sidecar + generalized `document_sections` rows. The canonical temporal locator is
  exact rational **PTS + `time_base`**, never a frame number.
- **D47 — `document_sections` generalizes to a polymorphic structure tree** with a `locator_kind`
  discriminator; `char_start/char_end` (markdown span) stays **mandatory across all modalities**; native
  locator columns (`page_no/bbox`, `t_start_pts/t_end_pts/time_base`, `track`, `keyframe_uri`) are
  additive and nullable by kind. The `role` enum extends with image and video roles.
- **D48 — The media cheap-first cascade order is fixed and each stage independently versioned in a
  `conversion_manifest`** (demux → shot-detect → ASR → keyframe+pHash → OCR → redact → scene-merge →
  **selective VLM caption** → chapter roll-up → escalation). VLM captioning is the only expensive,
  nondeterministic stage; its budget is **shot count, not duration**. Nondeterministic stages (ASR, VLM)
  are **replay-from-storage** on rebuild (D7/D33), re-run only on a stage version bump. Frontier
  native-video ingestion is an escalation reasoner over bounded clips, **not** the substrate.
- **D49 — D32 grounding generalizes to a polymorphic media-locator, apparatus unchanged.** Verbatim
  media-text (ASR/OCR, `asserted=false`) routes through strict D32 anchor + window-membership with a
  timecode/bbox; VLM captions (`asserted=true`) enter as `added_context[]` model-assertions grounded by
  entailment + sampled audit + region provenance + D42 origin, never as verbatim spans.
- **D50 — Conversion-layer non-goals (scope boundaries, not phases).** (a) **No single-blob video
  conversion** — video is always the multi-track MediaIndex. (b) **No per-frame / dense-uniform
  captioning** — shot-bounded selective captioning is strictly better at any scale (M2 §4.5;
  *simplification*, not deferral). (c) **No biometric face/voice identity templates** at convert time —
  diarization labels are relative (`SPEAKER_00`); cross-media identity is a documented per-deployment
  opt-in, not the system (D20-aligned; F7). (d) **No live/real-time stream ingestion** — the unit is an
  immutable bounded asset with a `content_hash` (D1/D12). (e) **No cross-modal belief without text
  grounding** — pixels produce claims only through the text pipeline.

**Design-doc deltas this implies:**

- `plan/designs/e0_files_design.md`: §3 (D38) — generalize the `convert()` signature to
  `{markdown, blocks[], structure, manifest}` + add the image and `video/*` router routes and the
  cascade table; §4 (D39) — generalize "PageIndex" to a per-document structure tree incl. the MediaIndex
  shape and the extended `role` enum; §2 (D37) — extend the `documents` columns + the generalized
  `document_sections` DDL + the video artifacts layout (`mediaindex.json`, `keyframes/`); §7 — add a
  worked video example to the end-to-end walkthrough.
- `decisions.md`: append **D45–D50**.
- `plan/designs/e2_e3_claims_relations_design.md`: §3.3 (D32) — add the polymorphic locator and the
  verbatim-vs-asserted routing (cross-ref F3); note the video E2 context bundle composition (scene
  transcript + caption + OCR + chapter summary + ±N neighbour scenes) is covered in F5.
- `plan/designs/postgres_schema_design.md`: the `document_sections` polymorphic columns + `documents`
  media columns + per-stage version stamps.
- Cross-refs only (out of F2 scope): P1 multimodal sub-index (F4), media claims/observations/entities
  (F5), privacy/redaction/deletion cascade (F7).
