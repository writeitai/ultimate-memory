# Multimodal Evidence Architecture Review

**Verdict:** choose a strict hybrid: media becomes first-class **E0 evidence** with native media structure, exact media locators, and rebuildable media artifacts, but it does **not** become a parallel belief system. E0 must transcode images/video into a textual surrogate so the existing E1 -> E2 -> E3 pipeline still produces natural-language claims, relations, observations, validity windows, and evidence counts (D2, D3, D31-D35, D41, D43). At the same time, E0 must preserve native image/video segments and P1 must index them with multimodal embeddings, because reducing everything to text loses retrieval power and breaks D32's auditability promise for visual evidence. The line is: **text is the reasoning interface; native media is the evidence anchor; P1 multimodal vectors are projection-only entry points; Postgres remains the one evidence/belief ledger.**

## 1. Core Choice: Hybrid, Not Text-Only and Not a Parallel Track

The wrong answer is "just OCR/caption everything into Markdown and pretend media is text." That keeps the current E1/E2/E3 machinery superficially unchanged, but it collapses the most important invariant in the system: every claim must trace to an exact source location (D32). A VLM caption is not a source span. It is a model-derived description of pixels. If a claim says "the chart shows revenue declining after 2022," the audit anchor is the chart region in the page or frame, not the generated sentence "the chart shows...".

The other wrong answer is a separate multimodal evidence track that owns media facts directly: native media segments -> multimodal embeddings -> visual graph or visual observations. That violates the plane discipline. D6 says projections hold no authority, and D2/D3/D43 define where beliefs live. A parallel media fact store would create two homes for belief: text-derived relations/observations in Postgres and media-derived visual facts elsewhere. They would drift, and supersession would become ungovernable.

The correct design is:

- E0 ingests media as raw immutable bytes in the same raw bucket pattern as documents (D37).
- E0 converts media into **two synchronized artifacts**:
  - a textual linearization for E1/E2: transcript, OCR text, captions, descriptions, tables, chart summaries, and segment headings;
  - a native **MediaIndex**: image regions, video scenes/shots, audio turns, OCR runs, keyframes, timecodes, bounding boxes, hashes, and provenance.
- E1 chunks the textual surrogate, but chunks carry pointers into MediaIndex nodes, not only character offsets.
- E2 produces the same thing it always produces: immutable, standalone natural-language claims with asserted validity (D31-D35, D41).
- E3 normalizes those claims into the same relations and observations model (D2, D3, D43).
- P1 adds multimodal indexes over media regions/pages/keyframes/segments, but those vectors are entry points only, exactly like relation fact-label embeddings in Lance (D8, D9). They never decide truth.

This preserves the pipeline's invariants:

- **Claims stay natural-language assertions** (D2), even when source evidence is pixels/audio/video.
- **Supersession stays on relations and observations**, not on source media or captions (D3, D43).
- **Validity has one belief home** in Postgres (D6).
- **Rebuildability is versioned and replayed from stored artifacts**; VLM captions and media segmentation outputs are persisted with converter/model versions and not re-derived nondeterministically during rebuild (D7, D33, D38).
- **Auditability improves rather than degrades** because claims can hydrate to a frame/time/region, not merely to a generated caption.

## 2. E0 Conversion Contract: Generalize `convert()` to Structured Media

D38's current `convert(bytes, mime, hints) -> { markdown, blocks[] }` is the right spirit but too narrow. It assumes a single text body with character offsets. Media needs a generalized contract:

```text
convert(bytes, mime, hints) -> {
  document_markdown,
  text_blocks[],
  media_index,
  conversion_manifest
}
```

`document_markdown` remains mandatory because E1/E2 are text-pipeline stages. But it is now a **linearized view**, not the whole evidence object. `text_blocks[]` carry character offsets into the generated Markdown and source links into the MediaIndex. `media_index` is the native structure. `conversion_manifest` records every converter, model, prompt, sample policy, and artifact URI used to produce the outputs.

### Image Contract

For a standalone image, scanned page, screenshot, photo, chart, or embedded figure, E0 should emit:

```text
media_assets:
  media_id
  doc_id
  content_hash
  kind = image | page_image | embedded_image | screenshot | figure | chart | table_image
  mime
  width_px
  height_px
  color_space
  orientation
  raw_uri
  artifact_uris
  converter_name/version

media_regions:
  region_id
  media_id
  parent_region_id
  region_type = full_image | text_line | text_block | figure | chart | table | ui_panel | object | face_detected | logo_candidate
  bbox = {x, y, w, h, unit=pixel|normalized, coordinate_space}
  page_number?             # for PDF/web page images
  confidence
  detector_name/version
  region_hash              # hash of crop bytes after deterministic decode

media_text_runs:
  text_run_id
  region_id
  source = ocr | chart_extractor | table_extractor | vlm_caption | human_caption | alt_text
  text
  markdown_char_start/end
  model/prompt/version
  confidence

media_descriptions:
  description_id
  region_id
  description_type = terse_caption | detailed_caption | chart_summary | table_summary | screenshot_ui_summary
  text
  markdown_char_start/end
  model/prompt/version
  grounding_policy
```

The Markdown linearization should be boring and machine-friendly:

```markdown
# Image: IMG_0421

[Region image:full @ bbox=0,0,1,1]
Description: A product shelf photo with three labeled packages.

[OCR @ bbox=0.11,0.32,0.48,0.08]
"ACME PRO 12"

[Chart @ bbox=0.05,0.12,0.9,0.6]
Summary: The plotted revenue series rises from 2020 to 2022 and declines in 2023.
```

The `Description:` and `Summary:` lines are model-derived artifacts, not source text. They are eligible context for E2, but claims derived from them must anchor to the underlying region locator.

### Video Contract

Video is not a document with pages. It is a multi-track temporal object. E0 should emit:

```text
media_assets:
  media_id
  kind = video
  duration_ms
  container
  codecs
  width_px
  height_px
  fps
  audio_tracks
  raw_uri
  proxy_uri?               # deterministic low-res proxy for review, not a source of truth
  converter_name/version

media_tracks:
  track_id
  media_id
  track_type = video | audio | asr | ocr | speaker | keyframe | caption | chapter
  language?
  model/version?

media_segments:
  segment_id
  media_id
  parent_segment_id
  segment_type = video | chapter | scene | shot | clip | audio_turn | screen_text_run | keyframe
  t_start_ms
  t_end_ms
  ordinal
  role = meeting | screen_share | slide | demo | product_shot | talking_head | b_roll | unknown
  representative_keyframe_id?
  summary
  detector/model/version
  confidence

keyframes:
  keyframe_id
  segment_id
  t_ms
  image_uri
  frame_hash
  perceptual_hash

video_text_runs:
  text_run_id
  segment_id
  track_type = asr | ocr | caption | chapter_title | speaker_label
  text
  t_start_ms
  t_end_ms
  bbox?                    # for on-screen text
  speaker_local_id?
  markdown_char_start/end
  model/version

video_descriptions:
  description_id
  segment_id
  source_keyframe_ids[]
  source_region_ids[]
  description_type = scene_caption | action_summary | screen_summary | visual_change_summary
  text
  markdown_char_start/end
  model/prompt/version
  confidence
```

The PageIndex analogue is **MediaIndex**, with a **SceneIndex** tree for video:

```text
video root
  chapter 00:00-08:34 "Quarterly roadmap discussion"
    scene 00:00-02:11 "intro / participants visible"
      shot 00:00-00:17
      shot 00:17-00:42
      audio_turn 00:21-00:39 speaker=S1
      screen_text_run 00:25-00:39 bbox=...
    scene 02:11-08:34 "screen share: launch dashboard"
      shot ...
```

For image collections, the analogue is an **AlbumIndex** or **ImageSetIndex**:

```text
image collection root
  group "same capture burst"
  group "screenshots from same application"
  group "figures extracted from report.pdf"
    image/page/figure nodes
      region nodes
      OCR/caption/table/chart nodes
```

Do not overload PageIndex with time. Keep PageIndex for textual/page-structured documents and introduce MediaIndex as a sibling E0 structure. Both feed E1/E2 as context.

### Cheap-First E0 Media Cascade

The media converter should route by source type and pay for understanding in this order:

1. **Deterministic metadata:** MIME sniff, EXIF, dimensions, duration, codec, page/figure extraction, hash/perceptual hash, ffprobe-like metadata.
2. **Deterministic segmentation:** page image extraction, shot boundary detection, scene grouping, slide/screen-change detection, silence/speech spans, keyframe selection.
3. **Cheap text extraction:** ASR for audio; OCR for images, frames, slides, screenshots, and detected text regions; table/chart extractors where available.
4. **Cheap classifiers:** document/page/scene role classification, screen-share/talking-head/product-shot detection, chart/table/UI detection, blur/blank/duplicate filters.
5. **Embeddings as projection inputs:** page image/keyframe/region embeddings for P1, batched and versioned.
6. **VLM captioning/visual reasoning:** only for visually informative regions/segments where OCR/ASR/metadata do not already provide enough E2 context, or where the media type requires visual understanding.

This is not a forbidden pre-extraction value gate (D25). Every source still gets a structured E0 representation and a textual surrogate. The cascade controls **conversion depth and frame sampling**, not whether a document's propositions are allowed into E2. Junk-control remains E2 Selection (D31-D35).

## 3. Grounding: Generalize D32 to Polymorphic Source Locators

D32 should be generalized, not replaced. A claim should still store a standalone `claim_text`, a source anchor, added context, and entailment/audit state. The source anchor must become polymorphic:

```text
source_locator:
  locator_id
  kind = text_span | image_region | video_time | video_region | audio_time | page_region | generated_text_span
  doc_id
  content_hash
  media_id?
  segment_id?
  region_id?
  text_block_id?
  char_start?
  char_end?
  page_number?
  bbox?
  t_start_ms?
  t_end_ms?
  keyframe_id?
  frame_hash?
  crop_hash?
  track_type?
  artifact_version
```

A media-derived claim should normally carry **two linked anchors**:

- `derived_text_anchor`: the exact generated text span the extractor read, such as an OCR run, ASR transcript span, or VLM scene description.
- `native_source_locator`: the exact media region/time range that generated text describes.

For OCR and ASR, the generated text is close to source text. For VLM captions, the generated text is model output. That distinction must be explicit in the schema. The audit UI should show both: "claim came from this caption line" and "caption line came from this crop/time range."

### Anchor Verification

For text:

- Same as D32: `source_span` must be a real character slice.

For image/page regions:

- `media_id` exists and belongs to `doc_id/content_hash`.
- Bounding box is in bounds for the decoded image dimensions.
- Region hash matches the deterministic crop of the raw/artifact image under the recorded decoder version.
- If the claim relies on OCR text, the OCR text span must belong to that region.

For video/audio:

- `t_start_ms` and `t_end_ms` are in bounds and aligned to a valid media asset.
- Referenced keyframes/segments are children of that time range.
- Optional bounding boxes are in bounds for the referenced frame/keyframe.
- Frame/crop hashes match the deterministic decoded frame/keyframe artifact.
- ASR/OCR text spans fall within the declared time range.

This gives the same hard floor as D32: the model cannot invent a source location. It either points to bytes/frames/regions that exist, or the claim is rejected.

### Window-Membership for Media

D32's window-membership says every added substring must verbatim-exist in the declared bundle source. For media, split this into two checks:

- **Textual membership:** added names, dates, numbers, labels, and quoted phrases must verbatim-exist in ASR, OCR, document header, neighboring transcript, filename metadata, or other declared text bundle elements.
- **Media membership:** added visual context must be tied to a declared media locator inside the segment/window. This is a membership check over locator containment, not over semantics.

Example: a video segment caption says "Alice presents the Q4 launch plan on a slide." If "Alice" is only inferred from a face, reject or downgrade the entity mention. If "Alice" appears in ASR, OCR, meeting metadata, or a speaker roster in the bundle, it can pass textual membership. "Q4 launch plan" must come from slide OCR, transcript, or grounded VLM description with a region/time locator.

### Entailment for Visual Evidence

For media-only claims, deterministic checks can prove location but not semantic truth. Pixels do not contain a verbatim proposition. Therefore acceptance must add a **visual entailment tier**:

1. deterministic anchor/location checks;
2. deterministic textual membership for all added text;
3. in-call media entailment verdict over the crop/frame/time range;
4. sampled independent media entailment audit, with higher sampling for visual-only claims than for text claims;
5. human-review routing for high-impact visual claims and identity claims.

This is the honest extension of D32. It does not pretend a generated caption is equivalent to a source quote. It says: exact native evidence location is mandatory; semantic support is judged and audited.

## 4. Retrieval / P1: Add Multimodal Indexes in Lance

Reducing media to text is not sufficient for a memory system. It loses:

- visual similarity: "find screenshots that look like this error dialog";
- layout retrieval: "find pages with this kind of chart";
- product/logo/package matching;
- visual state retrieval: "find the moment the dashboard showed the red alert";
- figures and tables where OCR is incomplete;
- image collections where no meaningful text exists.

P1 should add rebuildable multimodal Lance tables:

```text
p1_media_segments:
  segment_id
  doc_id
  media_id
  t_start_ms/t_end_ms
  role
  embedding_model/version
  vector
  scalar filters: source, origin, privacy_flags, converter_version

p1_keyframes:
  keyframe_id
  segment_id
  doc_id
  t_ms
  vector
  frame_hash

p1_image_regions:
  region_id
  media_id
  doc_id
  bbox
  region_type
  vector

p1_page_images:
  page_id/region_id
  doc_id
  page_number
  vector or late-interaction page representation
```

Use CLIP/SigLIP-style image-text embeddings for broad visual search, ColPali-style late-interaction page-image retrieval for documents/figures, and domain-specific models only as configured projection builders. These models are not authorities. They can return `region_id`, `keyframe_id`, or `segment_id`, after which the system hydrates from Postgres and GCS.

This is fully consistent with D6/D8:

- vectors live in Lance, not LadybugDB;
- P1 is rebuildable from Postgres + artifacts;
- no validity or supersession state lives in vectors;
- the graph remains entity/relation only (D18, D44);
- no LLM call is needed on the core search path (D9).

Recommended P1 recipes:

- `media_visual_similar(image|region)` -> regions/keyframes;
- `media_text_to_visual(query)` -> regions/keyframes/segments via multimodal text embedding;
- `video_moment_search(query, filters)` -> segments, reranked by ASR/OCR/caption BM25 + visual embedding;
- `page_image_search(query)` -> page images/figures with optional ColPali-style late interaction;
- `claim_to_media_evidence(claim_id)` -> native locators for audit hydration.

## 5. Claims, Observations, Relations, and Entities from Media

Media-derived claims fit the existing model. Do not create `VisualClaim`, `ImageFact`, or `VideoRelation`. A claim is still a natural-language assertion by a source (D2), with immutable asserted validity (D41), and E3 still decides whether it becomes:

- a relation: entity -> governed predicate -> entity (D2, D5, D18);
- an observation: entity-anchored value/statement (D43);
- neither, if it is pure description, opinion, generic content, or not verifiable enough (D31-D35).

Examples:

- Meeting video ASR: "Alice joined Acme in March 2024" -> claim -> relation `(Alice, works_for, Acme)` with `valid_from` seeded from D41.
- Slide OCR: "FY2023 revenue: $5M" on an Acme slide -> claim -> observation "Acme's FY2023 revenue was $5M" (D43).
- Product photo VLM caption: "The package label says ACME PRO 12" -> claim grounded to OCR/region; may produce a `Product` entity if text-derived.
- Visual-only frame: "The dashboard gauge is red" -> possibly an observation about a resolved dashboard/system entity if the entity is grounded by surrounding text/metadata; otherwise it remains a claim with weak/no entity normalization.

### E2 Context Bundle for Media

The E2 bundle should extend D31 as follows:

- document/media header: title, source, origin (D42), capture date, upload date, MIME, duration/dimensions, language;
- MediaIndex path: chapter/scene/shot/region path and role;
- target textual block: ASR/OCR/caption/description span;
- native locator: image bbox or video time range/keyframe;
- neighboring same-scene/same-section blocks: previous/next ASR turns, OCR runs, scene captions, adjacent shots;
- entity hints from text: names in ASR/OCR/metadata, document source, file path, known source system;
- speaker labels as local labels only: `speaker_1`, not canonical identity unless text/metadata resolves it;
- optional thumbnails/crops for visual-only segments, but only as support for extracting textual claims with native locators.

### Entity Resolution from Media

Take a hard line:

- **Entity resolution is primarily text-derived.** Names in ASR, OCR, captions, metadata, filenames, slide titles, email/web context, and existing document source metadata are valid mention evidence.
- **No open-world face recognition.** Face detection can exist for privacy/risk classification and redaction, not identity. Cross-document face clustering and face-to-person resolution are biometric processing and should be a non-goal.
- **No open-world speaker recognition.** Diarization may create local speaker labels inside one media item. Cross-document voiceprints are biometric processing and should be a non-goal.
- **No third-party visual authority path.** D20 already rejects third-party authorities on the write path. Do not add "recognize this person/logo/product from the internet" as a media loophole.
- **Scoped internal visual matching may be allowed for non-biometric entities.** If a deployment provides an internal product catalog, packaging image set, or approved logo library, visual matches can become weak entity mentions with method/version/confidence. They still go through the registry cascade and should not bypass D17. This is an internal alias source, not an external authority.

For people, require text, metadata, or human confirmation. A face in a frame is PII evidence, not an identity.

## 6. Cost and Scale: Video Must Be Sampled, Not Frame-Exhausted

At millions of documents, "caption every frame" is architecturally unserious. A one-hour 30 fps video has 108,000 frames. The system should reason over a temporal pyramid:

- full media asset;
- chapters/scenes;
- shots;
- representative keyframes;
- audio turns;
- OCR text runs;
- selected regions.

Recommended video cascade:

1. Decode metadata and audio/video streams deterministically.
2. Run ASR over audio. This is usually the highest-value, lowest-cost semantic signal for meetings and product videos.
3. Detect shot boundaries and screen/slide changes. Sample representative keyframes per shot/scene and additional frames only when visual change is detected.
4. Run OCR on keyframes and screen-change frames, not every frame. For screen recordings, sample on perceptual/text-change, not fixed fps.
5. Deduplicate near-identical frames/regions by perceptual hash. This is conversion idempotency/compression, not a value gate.
6. Embed keyframes/page images/regions in batches for P1.
7. Run VLM captioning at scene/shot/region granularity only where ASR/OCR/metadata are insufficient, where visual content is central, or where cheap classifiers identify charts/tables/UI/product imagery.
8. Run E2 over the textual surrogate blocks produced by ASR/OCR/captions/descriptions with E2 Selection doing proposition-level keep/drop.

For a one-hour recorded meeting, this might mean one ASR transcript, hundreds of shots, tens of scene summaries, OCR only during screen-share/slide changes, and VLM calls only for visually meaningful scenes. For a screen recording, OCR and UI-change detection dominate; ASR may be absent. For a product video, visual captions are more important, but still at shot/scene granularity, not frame granularity.

The cost levers should be first-class E0 configuration:

- per-deployment media routing table;
- max keyframes per minute by media class;
- OCR frame sampling policy;
- VLM caption granularity;
- confidence thresholds for "ASR/OCR sufficient";
- model/prompt/version for each rung;
- cost ledger per document/media asset/segment;
- replay policy keyed by `content_hash + converter_version + media_policy_version`.

The key principle from D4 survives: expensive models see ambiguity and visually necessary content, not raw volume.

## 7. Storage, Privacy, and Deletion

Media fits the existing GCS split but raises the stakes.

### Storage Layout

Raw bucket:

- original image/video/audio bytes;
- immutable, strict IAM, cold/archival where appropriate;
- not mounted on the normal browse path (D37).

Artifacts bucket:

- `document.md` textual linearization;
- `mediaindex.json`;
- `transcript.json` / `.vtt`;
- `ocr.json`;
- `captions.json`;
- `keyframes/`;
- `regions/` crops only when needed for audit/retrieval;
- `proxy.mp4` or preview images only if needed for review, with lifecycle controls;
- `conversion_manifest.json`.

Postgres:

- media metadata, segment/region indexes, locator records, artifact URIs, processing versions, privacy flags, costs;
- never raw media bodies, frame blobs, transcript bodies beyond compact/query-critical spans where already accepted by the schema discipline;
- no embeddings (D8).

Lance:

- rebuildable multimodal vectors keyed by media/segment/region IDs.

### Privacy and Biometrics

Yes: media makes PII/biometrics a first-class concern. Text documents contain PII, but media adds faces, voices, locations, screens, badges, addresses, device IDs, license plates, children, bystanders, and private environments. The design needs explicit metadata:

```text
media_privacy_findings:
  finding_id
  doc_id/media_id/segment_id/region_id
  finding_type = face | voice | license_plate | address | screen_pii | id_document | child | sensitive_location | unknown_person
  detector/version
  confidence
  locator_id
  policy_action = allow | restrict | redact_artifact | exclude_from_projection | human_review
```

Do not store biometric templates. Do not store cross-document face or voice embeddings. Detection for privacy routing is acceptable; recognition is not.

### Deletion / Forget

Open risk #24 becomes non-negotiable before media is enabled. Current docs say P1/P2/P3 cascade "for free" on rebuild, while `questions.md` correctly notes that immutable snapshots, Lance indexes, backups, stale corpus stubs, and K markdown references still need a coherent mechanism. Media makes "eventual rebuild" insufficient because old keyframes/proxies/crops may expose faces or voices.

Add a **source derivation manifest** as part of E0:

```text
source_derivations:
  doc_id
  content_hash
  derived_kind = gcs_raw | gcs_artifact | postgres_row | lance_vector | p2_snapshot_ref | p3_stub | k_reference | backup_scope
  derived_id_or_uri
  created_by_stage
  version
  contains_source_payload bool
  contains_pii bool
  deletion_status
```

Hard forget must:

- delete raw media and all artifact objects, including keyframes, crops, transcripts, captions, OCR, proxies, and MediaIndex sidecars;
- delete/scrub Postgres source-bearing rows and media locators per the schema's hard-forget discipline;
- delete Lance vectors by media/segment/region keys, then compact or rebuild;
- rebuild P3 latest without stubs and ensure old serving pointers cannot expose stale stubs;
- rebuild P2 latest where relations/entities are retired or retained according to the existing evidence-count rules (D44);
- emit K tombstones and remove/recompile K markdown references;
- make old immutable P snapshots non-serving immediately and expire them under a documented retention limit;
- treat backups/PITR explicitly, either through bounded backup expiry or per-document encryption keys that can be destroyed for immediate crypto-erasure of source payloads.

For media, per-document or per-source encryption keys are strongly recommended. They do not replace deletion, but they give an immediate erasure lever for raw/artifact blobs and old snapshots that accidentally retain source payloads.

## 8. Non-Goals

These should be explicit scope boundaries, not things left fuzzy:

- **No live streams or real-time memory.** The system ingests completed media files. Live stream indexing has different latency, consent, deletion, and partial-evidence semantics.
- **No surveillance use case.** Continuous camera/audio monitoring is outside the memory system's intended document-ingestion model.
- **No biometric face recognition.** Face detection for privacy/redaction is allowed; identity recognition and cross-document face clustering are not.
- **No cross-document speaker recognition.** Diarization inside one video/audio file is allowed; voiceprint identity is not.
- **No open-world visual entity linking.** No "identify this person/product/logo from the internet" authority path. D20 applies.
- **No frame-by-frame exhaustive captioning.** Sampling and segmentation are the design.
- **No graph facts directly from embeddings.** P1 can retrieve media; E2/E3 still create claims/relations/observations.
- **No cross-modal belief without natural-language claim grounding.** A visual model output can become a claim only with a persisted generated-text anchor and native media locator.
- **No generated captions as source truth.** Captions/descriptions are derived artifacts. The source is the raw media region/time range.
- **No raw media on the mounted browse path by default.** P3 can expose stubs, previews, and controlled artifact links, but raw bytes stay behind audited retrieval.

## Proposed Decisions

### D45. Multimodal inputs use a hybrid E0-native / E2-text-pipeline design

Media is first-class E0 evidence with native structure and locators, but all beliefs still enter through natural-language E2 claims and E3 relations/observations. There is no parallel media belief store. This preserves D2, D3, D6, D31-D35, D41, and D43.

### D46. E0 conversion returns a textual linearization plus MediaIndex

D38 is generalized from `markdown + blocks` to `document_markdown + text_blocks + media_index + conversion_manifest`. PageIndex remains for page/text structure; MediaIndex covers images, video, audio, regions, scenes, shots, keyframes, OCR, ASR, captions, and generated descriptions. Both are versioned and replayed from storage (D7, D33, D38).

### D47. Claim grounding uses polymorphic source locators

D32 is extended from character offsets to `source_locator` records: text spans, image/page regions, video/audio time ranges, and video regions. Media-derived claims carry both a generated-text anchor and a native source locator. Anchor checks prove the location exists; entailment/audit checks handle the semantic gap for visual evidence.

### D48. P1 includes multimodal Lance indexes

Lance gains rebuildable media indexes for page images, image regions, keyframes, and video segments. These indexes support visual and cross-modal retrieval but hold no authority, no validity, and no graph state (D6, D8, D9, D44).

### D49. Media-derived facts use the existing relation/observation model

Media claims normalize through the same E3 pipeline. Entity-to-entity facts become relations; single-entity values/statements become observations; pure visual/textual descriptions that do not resolve to facts remain claims or are dropped by Selection. No `VisualFact` layer is added.

### D50. Visual entity linking is constrained; biometrics are non-goal

Entity resolution from media is text/metadata-derived by default. Scoped internal matching for non-biometric entities such as products/logos may produce weak mentions when configured. Open-world visual entity linking, face recognition, and cross-document speaker recognition are non-goals. Face/voice detection exists only for privacy/routing/redaction.

### D51. Media conversion follows a cheap-first temporal/region cascade

The media converter uses deterministic metadata, segmentation, ASR, OCR, table/chart/UI detectors, keyframe sampling, deduplication, and embeddings before VLM captioning. VLM work happens at scene/shot/region granularity, not every frame. This controls conversion cost without reintroducing the rejected pre-extraction value gate (D25).

### D52. Media requires a source-derivation manifest and stricter deletion semantics

Every raw media object, artifact, keyframe, crop, transcript, caption, vector key, P3 stub, K reference, and snapshot membership must be traceable from the source document. Hard forget must delete or crypto-shred all source-bearing media artifacts and remove them from serving projections. Open risk #24 must be resolved before media is considered complete.

## Design-Doc Deltas

Update `README.md`:

- E0 should say "converted to textual and structured media artifacts," not simply Markdown.
- P1 should mention multimodal media indexes.
- Auditability should mention text spans plus media locators.

Update `decisions.md`:

- Add D45-D52 above.
- Amend D32 wording to "polymorphic source locator" while preserving the current text case.
- Amend D38 to generalize the converter contract.
- Amend D37/D40 deletion language to stop claiming P1/P2/P3 deletion is free without addressing immutable snapshots and vector compaction.

Update `plan/designs/e0_files_design.md`:

- Add MediaIndex beside PageIndex.
- Define image, video, audio, region, segment, keyframe, OCR, ASR, caption, and manifest artifacts.
- Add media routing and cheap-first cascade.
- Clarify Markdown is a linearization for E1/E2, not the sole converted body for media.

Update `plan/designs/e2_e3_claims_relations_design.md`:

- Extend the E2 context bundle for media.
- Extend D32 grounding to media locators.
- Add visual entailment audit and identity restrictions.
- State that media claims normalize unchanged into relations/observations.

Update `plan/designs/postgres_schema_design.md`:

- Add tables for `media_assets`, `media_tracks`, `media_segments`, `media_regions`, `media_text_runs`, `media_descriptions`, `source_locators`, `media_privacy_findings`, and `source_derivations`.
- Add claim grounding references to `source_locator_id` and generated-text anchor IDs.
- Add deletion worker responsibilities for media artifacts and vectors.

Update retrieval/P1 design:

- Add Lance tables and recipes for visual search, video moment search, page-image retrieval, and claim-to-media hydration.
- Keep the zero-LLM query-path rule (D9).

Update `questions.md`:

- Split #24 into a concrete deletion design task with media-specific acceptance criteria.
- Add evaluation tasks for visual entailment grounding, OCR/ASR quality, VLM caption precision, and visual entity-linking false positives.

## What the Author Is Missing

The biggest missing point is that **generated descriptions are not evidence**. They are derived artifacts. The evidence is still the raw bytes plus exact pixel/time locators. If the design treats captions as the media equivalent of `source_span`, it will quietly destroy the auditability that currently makes D32 the strongest part of the system.

The second missing point is deletion. The repo already knows #24 is open, but media turns it from a bookkeeping issue into a privacy blocker. Old keyframes, crops, proxy videos, visual embeddings, and K summaries can all retain sensitive source content. A multimodal design without a derivation manifest and hard-forget story is not complete.

The third missing point is identity. It is tempting to make media feel powerful by recognizing faces, voices, logos, and products. That would import an external-authority and biometric system through the side door, conflicting with D20 and with the privacy posture. Keep identity text-first and registry-first. Let visual search find evidence; do not let it become an identity oracle.
