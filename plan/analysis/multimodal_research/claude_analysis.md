# Multimodal (image + video) — Binding Analysis & Synthesis

**Status:** lead-architect synthesis, ready to mint decisions from. It reconciles the six design-fit
notes (`design_fit/F1–F6`), the two external reviews (`external_agents/codex_*`), the landscape and
mechanism research (`web_research/M1–M6`, `repo_findings/*`), and the three verification passes
(`verify/{numbers_facts,invariant_coherence,completeness}.md`) against the current design
(`decisions.md` D1–D44; `plan/designs/{e0_files,e2_e3_claims_relations,observations}_design.md`;
`questions.md`).

The six F-docs were drafted independently and **never reconciled**: they collide on decision numbers
(each mints its own `D48+`), specify the load-bearing locator three incompatible ways, and carry four
overclaims — one (`Tier-B storage`) contradicted by the research it cites. The two critics agree the
*core move* is sound and invariant-preserving; what was missing was a single coherent spec. This
document is that spec. Where it departs from an F-doc it says so and why. Numbers are starting points
to measure (CLAUDE.md Rule 2), not committed constants.

---

## 1. Executive verdict (the core choice + why)

1. **Belief is text in the E pipeline; native media is a P-plane retrieval projection; there is no
   parallel multimodal evidence track.** Every model-derived belief — claim (D2), relation,
   observation (D43) — is a text assertion produced from a *grounded-text transcoding* of the media
   at E0, exactly as a digital PDF's text is today. Pixels and audio become beliefs **only** through
   that transcoding; they are first-class *retrieval entries*, never first-class *evidence*. The
   single load-bearing word in the "parallel track" option is **evidence** — we accept native media
   segments and embeddings as a *retrieval projection* and reject them as *belief*. That asymmetry is
   the whole verdict (F1; codex_architecture §1).

2. **"Describe media to text" is not a new epistemic hazard — it is the third instance of a discipline
   the pipeline already runs twice.** OCR is *already* a versioned, nondeterministic `convert()` output
   replayed-from-storage on rebuild (D38/D33); E2 decontextualization is *already* a lossy,
   nondeterministic rewrite of source text quarantined by D32 grounding. A VLM description is the same
   shape of artifact, governed by the same apparatus (immutable raw bytes D1/D37; versioned + replayed
   model output D7/D33; locator + entailment grounding D32; origin stamp D42). Nothing about pixels
   breaks the contract; they extend it by one locator type.

3. **One schema change carries most of the feature: the grounding locator generalizes from a
   char-offset to a tagged union** `text(char_span) | image(page,bbox) | av(t_start,t_end[,speaker,
   keyframe])`, and *every block of every modality additionally keeps a mandatory char-offset
   (`md_span`) into a deterministically linearized markdown.* The char-offset pipeline keeps E1 chunking
   and E2/D32 grounding **modality-blind**; the native locator is additive provenance. D32's four
   acceptance rungs map onto it.

4. **Be honest about what media does to the auditability crown jewel — it splits in two.**
   *Provenance traceability improves* (a claim now grounds to a chart region or a spoken timecode — you
   can always draw the box). But *per-claim deterministic faithfulness is genuinely softened for
   model-described content*: a VLM caption's substring anchor fixes provenance-to-the-caption, **not**
   that the caption is true to the pixels. Faithfulness for descriptions moves to in-call entailment +
   an **offline sampled audit**, whose per-class sample rate is a first-class measured safety
   parameter. We adopt F3's honest account and **reject F1's "auditability improves" framing** as an
   overclaim (the invariant critic is right; this is the single most important nuance in the feature).

5. **Three provenance classes, not two.** Verbatim **transcription** (clean OCR/ASR) is real source
   text and may confident-supersede a prior belief. **Description** (VLM/audio caption, chart→prose) is
   a model assertion, never confident-supersedes, audited harder. The third class the F-docs missed:
   **uncertain transcription** (handwriting/HTR, degraded scans, low-confidence OCR/ASR) is
   verbatim-in-its-own-output yet the *read itself is a lossy guess* — it may **not** confident-supersede
   and is routed to higher audit. Without this class a hallucinated OCR of a handwritten "$5M" would be
   anchored as verbatim fact and allowed to overwrite a real one (completeness gap 3/11).

6. **Cheap-first throughout (D4), with the expensive rung bounded by edits, not seconds.** Media
   `convert()` is a deterministic pipeline (demux → shot/topic segmentation → ASR+align+diarize →
   perceptual-hash keyframe dedup → OCR) followed by **selective VLM/audio captioning of one keyframe
   per shot/scene** — the only expensive, nondeterministic rung, whose budget is **shot/scene count,
   not duration**. Native whole-video frontier ingestion is an *escalation reasoner over bounded clips*
   (cost re-paid per query), never the substrate. No learned per-frame value gate (that is the video
   reincarnation of the rejected D25 gate); deterministic shot-dedup is *structural reduction*, like
   content-hash idempotency.

7. **The deterministic transcription pipeline is the offset anchor; descriptions are a block-ID
   side-channel — never spliced inline into the offset-bearing markdown.** This is the structural fix
   for the sharpest risk in the feature: if VLM captions sat inline in the markdown that carries char
   offsets, a single caption re-run (on a `vlm_caption_version` bump) would shift the offsets of every
   later block and silently invalidate the `source_span` of unrelated, fully-deterministic
   transcription claims. We decouple them: char offsets only ever index deterministic content;
   descriptions are addressed by stable `block_id` + their native locator and enter E2 as named
   bundle context, so a caption re-run never churns a transcription claim's anchor (completeness
   risk 17).

8. **One belief home holds (D6); visual recall is a Lance projection with zero authority.** All
   beliefs are text claims/relations/observations in Postgres; `evidence_count`, dedup, and
   supersession work at the fact grain *after* transcoding (a chart-fact and a prose-fact of the same
   thing collapse to one observation/relation with N evidence rows). P1 gains a two-tier visual
   sub-index (always-on single-vector + gated multi-vector late-interaction); a visual hit returns a
   **locator**, never a belief; vectors never enter the P2 graph (D8/D18/D44).

9. **Privacy is a genuinely new, first-class E0 concern, and the safe posture is structural.** Add a
   versioned **detect/redact** stage; the *redacted derivative is the canonical mounted/indexed/embedded
   artifact*, the raw original is quarantined-and-shreddable. **Never persist face or voice templates** —
   the single rule that keeps ugm out of GDPR Art. 9, the EU AI Act's prohibited untargeted-biometric
   database, and BIPA template liability. Because the P1 visual index embeds *redacted* keyframes,
   image→image similarity is structurally **not** a face-matching gallery (closing the "visual index
   becomes a biometric tool" hole). Two obligations the F-docs omitted are added: a hash-matched
   **illegal-content (CSAM) detection hook** with a stated §2258A/NCMEC reporting posture, and **C2PA /
   Content-Credentials authenticity passthrough** (an axis distinct from D42 self/external origin).

10. **Deletion is finally end-to-end, and ugm escapes the worst version of it for free.** Subject-level
    "forget" is keyed on the entity registry (D17) and executed by **crypto-shredding a per-document key**
    (reaching PITR backups, bucket-locked raw, GCS soft-delete, aged snapshots as unrecoverable
    ciphertext) **+ Lance compaction-with-prune** (a tombstone is not erasure) **+ an O4 K input-manifest**.
    Because every derivative is a versioned replay-from-storage projection (D7), there are no trained
    weights to scrub — deletion is an ordinary drop/re-derive. Media is the *forcing function* (multi-GB
    cold blobs + biometric liability), but the mechanism closes `questions.md #24` for text too.

---

## 2. The recommended design (concrete, per concern)

### 2.1 The generalized `convert()` contract

`convert()` stays the versioned, pluggable router of D38; its return type grows, and the load-bearing
`{markdown, blocks[] with offsets}` of today is a strict subset (text routes are untouched):

```
convert(bytes, mime, hints) -> {
  document_markdown,   # deterministic LINEARIZATION of the TRANSCRIPTION pipeline only; the sole thing E1/E2 chunk
  blocks:    Block[],  # content units, each dual-located
  structure: StructureTree,   # PageIndex (text) | page→region (image) | MediaIndex scene/chapter (av)
  manifest:  ConversionManifest   # every stage's tool+version+params+prompt+policy+artifact_uris (D7/D33)
}

Block = {
  block_id,                              # STABLE, content-addressed; the anchor identity (not the char offset)
  kind, role,
  md_span: { start, end } | null,        # offsets into document_markdown — PRESENT iff provenance_class is transcription
  native_locator: Locator,               # polymorphic source anchor (below)
  provenance_class: "transcription" | "uncertain_transcription" | "description",
  text?, payload?: { table_html? | latex? | chart_csv? },
  producer: { engine, model, version, prompt_version, confidence }
}

Locator =                                # tagged union — the D32 generalization
  | { kind:"text",  char_span:[start,end] }
  | { kind:"image", page, bbox:[l,t,r,b], coord_space:"norm_0_1000_topleft", region_kind }
  | { kind:"av",    t_start_pts, t_end_pts, time_base:[num,den],
                    track:"video"|"audio"|"onscreen", speaker?, keyframe_uri?, frame_bbox? }
```

Two invariants make it work, resolving the three-way locator disagreement in F1/F2/F3:

- **The offset pipeline is the deterministic transcription linearization only.** `document_markdown` is
  built from transcription blocks (OCR/ASR text) in a total order (sort by `t_start_pts`/page, then a
  fixed track priority for ties), so it is byte-stable across re-runs at pinned versions. **VLM/audio
  captions are not spliced inline** — they hang off their structure node, are addressed by `block_id` +
  `native_locator`, and reach E2 as named `added_context[]` elements. A description re-run therefore
  never shifts a transcription claim's `source_span` (the risk-17 fix). E1/E2 stay modality-blind: they
  read `document_markdown` + char offsets exactly as today.
- **Bbox is normalized at the boundary to one canonical space** — `[l,t,r,b]` on a 0–1000 grid,
  origin top-left (MinerU's resolution-independent `_build_bbox` pattern; verified). Gemini's
  `[ymin,xmin,…]/1000`, Claude's post-resize pixels, Docling's bottom-left PDF boxes, MinerU's
  pixel@dpi all collapse to this one space at convert time; the **raw producer-space bbox +
  `coord_space` + `producer_version` are recorded in `conversion.json`** (artifacts/GCS) for lossless
  audit. This adopts F3's normalize-at-boundary model and **drops F1's store-native/normalize-on-read**
  (so no downstream consumer must know every parser's coordinate convention). Time is **exact rational
  PTS + `time_base`**, never a frame number (frame indices drift on variable-frame-rate video). Speaker
  labels are document-relative (`SPEAKER_00`), never a person identity.

### 2.2 The IMAGE route (a cheap-first cascade with an image-class router first)

An image is the degenerate single-page document. Order:

| Rung | What | Default → escalation | Provenance class |
|---|---|---|---|
| **−1** image-class route | natural / screenshot / scan / chart / handwriting / low-quality (cheap heuristics + a small classifier, *before* OCR) | local | — |
| **0** READ (always) | layout + OCR + tables→HTML + formulas→LaTeX + reading order | MinerU `pipeline`/`hybrid`, Docling, PaddleOCR-VL/Surya → Mistral OCR (hosted tail) | `transcription`, or `uncertain_transcription` when OCR confidence is low / HTR / degraded |
| **1** DESCRIBE (selective) | grounded prose for `picture`/`chart`/`figure` regions; chart→table | Qwen2.5/3-VL self-host → Gemini Flash-tier | `description` |
| **2** ESCALATE (flagged tail) | dense infographics / hard charts / degraded scans | Opus/Gemini-Pro class | `description` |

The **image-class router is reinstated from codex_landscape §9** (the F-series dropped it in favour of
"route on the OCR block category", which presumes you already paid for OCR on a vacation photo and gives
handwriting/low-quality the wrong handler). Rung 1 fires only on regions Rung 0 marked non-text; Rung 2
only on the self-flagged low-confidence minority. **Spend scales with non-text regions and ambiguity,
not pixel count** (D4/D25).

### 2.3 The VIDEO route and the MediaIndex (the PageIndex analogue for time-based media)

Video is a multi-track temporal object, **never a single markdown blob**. The cascade is strictly
cheapest→most-expensive, each stage gated by the previous and **independently versioned**:

```
1  demux / probe (ffmpeg)              deterministic, CPU            container_probe_version
2  shot detection                      PySceneDetect Content/Adaptive → TransNetV2 (edited/high-motion)   shot_detect_version
3  ASR + word-align + diarization      WhisperX (faster-whisper + wav2vec2 + pyannote)                    asr_version
                                       → NeMo Canary-1B-v2 for Czech/accuracy; Deepgram Nova-3 no-GPU
4  keyframe select + pHash near-dup    1 frame/shot; a 5-min static slide → 1 keyframe, not 300           keyframe_policy_version
5  OCR on dedup'd keyframes            MinerU/Docling/PaddleOCR-VL                                         ocr_version
6  DETECT + REDACT (faces, on-screen   deface/CenterFace + Presidio (image) + Presidio over transcript;   redactor_version
   PII, illegal-content hash, C2PA)    redacted derivative becomes canonical
7  scene merge (shots→scenes)          deterministic clustering by visual + transcript similarity         scene_merge_version
8  SELECTIVE VLM caption               1 keyframe / shot-or-scene (the cost center; budget = shot count)   vlm_caption_version
9  chapter roll-up                     small text LLM (= the D39 structurer) → titles/summaries/roles     structurer_version
10 escalation (bounded clip)           Gemini, scene-bounded, ambiguity-gated, rare                        escalation_version
```

The persisted **MediaIndex** sidecar (`mediaindex.json`) is the scene/chapter tree:
`chapters[] → scenes[] → shots[]` with `{t_start_pts, t_end_pts, keyframe_uris, keyframe_phash}`, a
diarized word-timecoded `transcript[]` (the verbatim pipeline, `transcription`), per-scene `ocr_runs[]`
(`transcription`), per-scene `visual_caption{text, model_version}` (`description`), and the
`conversion_manifest`. The linearized `document_markdown` is the deterministic flattening of the
transcript + on-screen OCR (the transcription pipeline); scene captions ride the tree by `block_id`. A
claim E2 extracts therefore grounds to a **timecode (+ optional keyframe bbox)**, not merely to a
generated sentence.

**Long audio-only** has no shot detector, so it gets the same tree built from **acoustic-change +
ASR-topic-shift segmentation** (so a 3-hour podcast is not one flat transcript), and a **sound-event /
audio-caption DESCRIBE rung** is the audio analogue of the VLM caption for non-speech segments (music,
environmental audio) — a `description`-class model assertion, identically quarantined (closing
completeness gap 2).

### 2.4 The polymorphic structure tree and storage (D37 unchanged in rule)

`document_sections` (D39) generalizes to a polymorphic tree with a `locator_kind` discriminator;
**`char_start/char_end` stay mandatory across all modalities for transcription nodes** (the modality-blind
pipeline), native-locator columns are additive and nullable-by-kind, and the `role` enum extends with image
and av roles (`chapter, scene, shot, transcript, visual_caption, onscreen_text, intro, demo, qa, credits`)
so E2 Selection can drop low-value roles **at proposition grain in-call** (D25/D31), never as a pre-E2
section skip.

```
raw bucket   (immutable, Archive/Coldline, strict IAM, NEVER mounted, encrypted under per-doc DEK):
  .../raw/<doc_id>/<content_hash>/original.<ext>
artifacts bucket (Standard, mountable via P3; redacted derivatives only):
  document.md · conversion.json (blocks+dual locators) · mediaindex.json|pageindex.json
  · keyframes/<phash>.jpg (redacted, content-addressed) · meta.json
Postgres (D37: index only, never bodies):
  documents += media_kind, duration_pts, time_base, fps_rational, container, codecs, has_audio,
               + per-stage version stamps, captured_at/precision/source,
               + has_faces/has_onscreen_pii/has_third_party_audio/content_safety_flag/authenticity,
               + dek_id, dek_status, redaction_recall_class
  document_sections += locator_kind, t_start_pts/t_end_pts/time_base, page_no/bbox/coord_space,
               track, keyframe_uri, keyframe_phash, speaker_label
LanceDB (P1): rebuildable visual vectors keyed by visual_unit_id (no authority, no bodies)
```

### 2.5 Grounding generalization (D32 → all modalities), three provenance classes

Every claim keeps `claim_text` + a `source_span` (char offsets into `document_markdown`, the D32 floor,
**unchanged**) **and** a `native_locator` inherited from the block(s) the span overlaps (a claim spanning
a transcript line + an on-screen OCR line carries two locators — handled by a locator child table so a
claim can carry a *set*). Acceptance gains **L0 (locator resolves: in-bounds for its medium)** and the
L1/L2 layers branch on provenance class:

| | `transcription` (clean OCR/ASR) | `uncertain_transcription` (HTR/degraded/low-conf) | `description` (VLM/audio caption) |
|---|---|---|---|
| L0 locator resolves | required | required | required |
| L1 anchor | verbatim slice of `document_markdown` = real source text | verbatim slice, but the *read* is a lossy guess | slice of the **caption** → fixes provenance-to-caption, **not** faithfulness |
| L2 window-membership | added substrings verbatim-exist in bundle | same | region **overlaps detected content** + any quoted on-region text matches co-located OCR/ASR |
| L3 entailment | chunk+bundle entail claim ("*X said* Y" ⇒ "X said Y") | same | **primary honesty gate**: region content entails caption entails claim |
| L4 sampled audit | baseline rate | **higher** rate; the read is measured | **highest** rate; per-class-tuned safety parameter |
| supersession power | may confident-supersede | **may not** confident-supersede | **may not** confident-supersede |

`derivation ∈ {digital_text, ocr, asr, uncertain_ocr, chart_extraction, vlm_description, audio_caption}`
propagates: a claim touching a `description` block is `vlm_description` and is **never counted as
independent corroboration** (N captions of one frame by one model are not N evidence rows — the D42
self-confirmation guard applied to pixels). **"Verbatim" is always w.r.t. the converted text, never the
pixels/signal** — signal fidelity (did OCR/ASR read correctly) is the separate, measured L4 axis.

### 2.6 Media facts in the belief layer (E2/E3/D41/D43 unchanged)

The belief layer is media-agnostic: it sees text + a locator. The E2 **bundle** (D31) gains media-typed
elements referenced by `block_id` — transcript window (the "chunk"), MediaIndex scene path + summary,
scene caption (`description`), on-screen OCR block (`transcription`), ±1/±2 neighbour transcript
segments, mapped speaker labels (the attribution "X" in "*X said* Y") — and the extractor mechanism is
unchanged. A measurement read off a chart/dashboard ("Acme FY2023 revenue $5M") → an **observation**
(D43) on the resolved entity, with the figure's `(page,bbox)` / `(t_start,t_end)` as evidence
provenance; **no typed value/period column** (value lives in the NL `statement`, D43). Two documents
asserting the same fact (one chart, one prose) collapse to **one** observation/relation with
`evidence_count = 2` because both arrive at E2 as text.

**Intra-document cross-track contradiction** (one frame: OCR "600", VLM "≈60", speaker "six hundred")
resolves through the *same* D43 adjudicator with **provenance class as the confidence dial**: verbatim
`transcription` > `uncertain_transcription` > `description`; a model-read value never confident-supersedes
an OCR/ASR-verbatim value; conflicting same-locator values coexist/flag. **Entity resolution is
text-mediated only**: names from OCR/transcript and mapped *relative* speaker labels flow through T0–T4
(D17) unchanged; visual content may *emit candidate name strings* (a logo→"Acme" caption into the
OCR/caption stream), never assign `entity_id`s. A person on camera never named in any text is an
**acknowledged recall gap** (the visual twin of cross-document coref, `questions.md #22`), remediable
only by opt-in, consent-gated enrolment per deployment — never default.

**Capture time** (EXIF `DateTimeOriginal`, container clock) is a **new, immutable E0 evidence metadatum**
(`captured_at` + `capture_precision` + `capture_source`) that seeds depicted/valid-time as a
*lower-precedence default*: **content-asserted grounded date (D41) > capture time > ingestion time**. It
is immutable, many-valued-by-document, fact-identity-free — D41's three non-authority properties hold, so
it is **not** a third validity clock. Other EXIF (GPS, device serials) is PII, stripped at redaction,
never auto-promoted to observations.

### 2.7 The P1 multimodal retrieval sub-index (two-tier, cheap-first)

One sub-index in the existing Lance estate, per **visual unit** (page-image from the OCR/figure route,
standalone image, video keyframe, video segment):

- **Tier A (always-on):** one single-vector unified-encoder cross-modal embedding (Cohere Embed v4 /
  Voyage multimodal-3 hosted, or Jina-CLIP-v2 / SigLIP-2 self-host). ~1–4 KB/unit, HNSW/IVF,
  millisecond ANN — the millions-scale baseline that gives real text→image and image→image search.
  *Unified-encoder* matters: it crushes classic two-tower CLIP on document/figure retrieval by closing
  the modality gap (+26.5% doc-screenshot / +41.4% table-figure vs CLIP-L; verified).
- **Tier B (gated):** a ColQwen2.5 / ColNomic **multi-vector late-interaction** column, materialized
  **only for units flagged visually-rich** (tables/charts/figures/scanned/dense layout) — the slice
  where a single pooled vector blurs the answer and ColPali wins decisively (ViDoRe nDCG@5 **81.3 vs
  67.0** vs the best OCR+caption+text pipeline; verified). *Late interaction* = keep one ~128-dim vector
  per image patch and score each query token against its best-matching patch (MaxSim), so a rare query
  word lands on the exact table cell. Two-stage at query time (ANN candidate-gen → MaxSim rerank).

**Storage correction (the invariant critic's O1, load-bearing).** Lance multivector is **cosine-only,
float16/32/64 — no binary/hamming**. The "~5–6 KB/page, single-vector-comparable" figure in F1/F4
**requires binary quantization Lance does not have** and is wrong for Lance. With the Lance-available
lever (token-pool factor 3 → −67% vectors @ 97.8% accuracy + fp16): ~343 vectors × 128 dim × 2 bytes ≈
**~86 KB/page ≈ ~20× a single vector** on the gated visually-rich slice. We **accept ~20× on that gated
slice** (still one vector estate, D8); a hamming-capable engine (Vespa/Qdrant) is a *documented
alternative*, triggered only if a measured Tier-B latency/storage requirement ever forces it — not a
phase.

**The visual index is structurally not a biometric tool** (closing completeness risk 18). It embeds the
**redacted** keyframes/page-images (faces already blurred per D57), so `visual_similarity` over
person-containing frames sees blurred faces and cannot become a face-matching gallery; person-dominant
queries are additionally barred from the face-matching recipes. New recipes — `visual_similarity`
(image→image), `find_visual` (text→image), `find_frame` (video timecode), `visual_maxsim_rerank`
(Tier-B precision) — are **RRF candidate generators returning locators, zero LLM on the query path**
(D9), no authority, never project to P2. A visual hit *locates*; the text claim *asserts*; the locator
hydrates to the grounded text claims already extracted at that page/timecode.

### 2.8 Execution model — checkpointed long-running conversion (the D12/D36 strain, resolved)

The E0 chain shape is preserved — `ingest → convert → redact → structure → crossref` — but the media
weight inside `convert` is a **checkpointed sequence of independently-versioned stages**, each persisting
its artifact to GCS and recording completion in the `conversion_manifest`. The idempotency grain is
refined from D36's `content_hash + sub-worker-version` to **`content_hash + stage + stage_version`**: a
stage re-runs only if its inputs or its own version changed; completed upstream stages are
**replayed-from-storage** (this **explicitly extends D33's replay discipline — written for E2 — to the E0
media stages**, which the F-docs assumed but D33 does not yet say). `convert` for a multi-hour asset
dispatches as a **durable, stage-checkpointed job**, not the fast-text Cloud-Task envelope (D12's 2-retry
+ dead-letter would lose a whole video on a stage-8 failure after stage-3 ASR succeeded). A late-stage
failure resumes from the last checkpoint.

**Partial / failed conversion semantics:** belief extraction proceeds on the **stable deterministic
transcription pipeline** the moment it is complete; descriptions *enrich but never block* (because they are
block-ID side-channel, §2.1, ASR-only claims commit with stable offsets and captions later add bundle
context for an E2 re-run of only the affected scenes, with no offset churn). A corrupt/truncated asset
that fails a *deterministic* stage is **quarantined** (`status=conversion_failed`), never partially
mounted.

### 2.9 Storage, privacy, deletion

- **Storage tiering (D37 unchanged in rule).** Raw media → raw bucket on Archive/Coldline (cold,
  immutable, never mounted, per-doc-DEK encrypted). Redacted transcript / keyframes / MediaIndex →
  artifacts bucket (Standard, mounted). Postgres gains compact metadata + the temporal section index +
  privacy flags + key IDs only. **Note the hot cost the F-docs under-sized:** keyframe JPEGs + page-image
  rasters are the D7 rebuild source for P1, so they live in the *Standard/mounted* class — millions of
  videos × dozens of crops is a real hot-storage line item (completeness gap 10).
- **Privacy as a first-class, versioned E0 concern (D57).** A `detect/redact` stage; the **redacted
  derivative is canonical** (so "agents only ever see redacted media" is a *structural property of D37's
  never-mounted-raw split*, not a runtime hope). **Hard invariant: never persist face or pyannote voice
  embeddings as durable matchable templates** — diarization uses speaker vectors only transiently to
  cluster within one file; the durable output is relative labels. Detect-and-flag records *flags, not
  biometrics*. Self-hosted redactors (deface, Presidio, WhisperX, PySceneDetect) default (local
  processing avoids a BIPA §15(d) disclosure and a GDPR Art. 28 processor relationship); cloud redaction
  is opt-in-per-deployment with a DPA. **Mounting/P1/retrieval are gated on a measured redaction-recall
  floor** — a *binding rule*, not a spike outcome: a document whose redaction did not clear the floor is
  quarantined until re-redacted ("a missed face is an un-redacted face").
- **Two obligations the F-docs omitted, now added (D57).** (a) **Illegal-content (CSAM):** a
  PhotoDNA-style hash-match hook in `detect`, `finding_type ∈ {…, csam_suspected, id_document, child}`
  (reinstating codex_architecture's enum that F6 dropped), with a stated **18 U.S.C. §2258A / NCMEC**
  posture — the system provides the detection hook + audit trail + flag-and-quarantine; the actual
  CyberTipline report is a deployment-operational obligation wired to that hook (a strictly larger legal
  exposure than biometrics for a media-ingesting system). (b) **Content authenticity:** ingest and
  persist any **C2PA / Content-Credentials** manifest as `authenticity` evidence metadata, flag
  absence/break; this is an axis *distinct from D42 self/external origin* ("did **we** make it" ≠ "is the
  external media authentic / AI-generated / manipulated"). Standalone deepfake *detection* is a non-goal;
  the manifest passthrough is nearly free.
- **Subject-level deletion (D58, closes #24 / folds O4).** Resolve "forget source X / person P" to an
  `entity_id` via the registry (D17) — the deletion key (subject → mentions → documents → DEKs).
  **Crypto-shred** the per-document DEK (every copy, including PITR backups, bucket-locked raw,
  soft-deleted objects, aged snapshots, becomes unrecoverable ciphertext — no row rewrite, no waiting out
  retention). **Lance compaction-with-prune** physically removes vectors (a `DELETE` tombstone is not
  erasure). **Bounded/keyed P-snapshot retention** + the **O4 K input-manifest** (claim/relation/observation
  IDs per compiled file) reach the immutable tail and the unreproducible K markdown. For a shared document
  that must survive with one subject removed, **re-redact-and-re-derive** (per-subject sub-keying as the
  escalation) rather than shredding the whole document. ugm avoids machine-unlearning by construction
  (D7): every derivative is a replay-from-storage projection, not trained weights.

---

## 3. How it preserves the invariants

| Invariant | How the design honors it |
|---|---|
| **D1/D37 — immutable raw, storage split** | Raw media → cold/immutable/never-mounted/DEK-encrypted; redacted derivatives + linearization + sidecars → artifacts; Postgres holds index + flags + key IDs, **never bodies** (transcript/captions in GCS). |
| **D2 — claims = atomic NL assertions; `evidence_count`/dedup** | OCR/ASR text and captions all flow into E2 as the same atomic claims; a chart-fact and a prose-fact collapse to one relation/observation with N evidence rows. No new claim type. `evidence_count` stays **raw**; the model-echo discount lives in confidence/K3 (the seam the critic flagged — stated explicitly here, reconciled in one place). |
| **D3/D43 — supersession on relations/observations, never claims** | Media claims are immutable evidence; the window closes on the observation/relation. A model-read value may *not* confident-supersede (provenance-class dial); the no-cap rule is media-agnostic. |
| **D6 — one belief home; graph holds no authority** | Beliefs are text-only in Postgres. Pixel/audio embeddings are P1 projections with zero authority — the explicit AVOID of the Mem0/Graphiti desync class. No second belief store. |
| **D7/D33 — rebuildable, versioned model-derived artifacts, replay-from-storage** | Every media stage is versioned and replayed; D33's replay discipline is **explicitly extended from E2 to the E0 media stages** (the one place the F-docs over-asserted what D33 already says). A media description is exactly an OCR/PageIndex-class artifact. |
| **D8/D18/D44 — vectors in Lance, not the graph** | The multimodal sub-index extends the Lance estate; LadybugDB stays embedding-free; observations/visual vectors never project to P2 (a value/embedding is not a node, and a REL endpoint must be a node). |
| **D9 — zero-LLM query path** | Visual retrieval is embedding lookup + RRF fusion; the describe-LLM cost is paid once at ingest, never on the query path. |
| **D12/D36 — per-doc chain, sub-worker idempotency** | The media cascade stays inside the E0 chain; idempotency grain is refined to `content_hash + stage + stage_version` with **checkpointed, resumable** long-running execution for multi-hour video (the strain the critic flagged, now *designed* rather than asserted away). |
| **D25/D34 — no pre-extraction value gate; junk-control in-call** | Selective DESCRIBE and shot-bounded captioning are **cost cascades inside `convert` (D4)**, not value gates; deterministic shot-dedup is structural reduction (like content-hash idempotency). **Every scene reaches E2**; `role` drops happen **at proposition grain in-call**, never as a pre-E2 section skip. The visually-rich Gate-2 and `role`-drop are deterministic structural/role reduction, **not** a salience classifier on the hot path — stated once, uniformly. |
| **D32 — grounding/auditability** | Char-offset floor unchanged; locator generalizes; four rungs map. **Honest split adopted:** provenance traceability *improves* (draw the box); per-claim deterministic *faithfulness* is *softened for descriptions* (provenance-to-caption, not truth-to-pixels) and rides entailment + a per-class-tuned offline audit. F1's "auditability improves" overclaim is dropped. |
| **D41 — asserted vs adjudicated time** | Capture time is an immutable, many-valued, fact-identity-free *seed* (lower precedence than content-asserted dates); the adjudicated window stays relation/observation-only. The locator timecode (*when said*) and the asserted window (*when true*) are distinct, both stored, never conflated. |
| **D42 — origin stamping** | Extended with the verbatim-vs-model-asserted discrimination and a *new* authenticity axis (C2PA), so confidence math never counts a caption — or a self-generated re-ingested media echo — as independent corroboration. |

---

## 4. Proposed decisions (ready to become D48–D59)

One reconciled, non-overlapping sequence continuing from the canonical log's last entry (D47 — the
K-plane design minted D45–D47 after this analysis was drafted, so the sequence starts at D48). This
**replaces** the six conflicting per-doc `D45+` proposals and the codex `D45–D52`.

**D48 — The core multimodal choice: transcode-to-text belief; native-media retrieval as a P1
projection; no parallel multimodal evidence track.** *Decision:* belief (claims/relations/observations)
is text produced from grounded-text transcoding of media at E0; native-media segments/embeddings are a
P-plane retrieval *entry channel* with zero authority. *Context:* "describe media to text" is the same
discipline as OCR (versioned `convert()`, D38) and E2 decontextualization (lossy rewrite quarantined by
D32), not a new hazard; a second belief home would drift (the D6 Mem0/Graphiti class). *Consequences:*
no `VisualClaim`/`ImageFact`/`VideoRelation`; one belief home (D6) holds; supersession/`evidence_count`
work at the fact grain after transcoding. *Binds* D2/D3/D6/D43.

**D49 — `convert()` generalizes to `{document_markdown, blocks[], structure, manifest}` with a dual
locator; the offset pipeline is the deterministic transcription linearization, descriptions are block-ID
side-channel.** *Decision:* every block carries a mandatory `md_span` into a deterministically linearized
markdown (built from transcription blocks only) **plus** a polymorphic `native_locator`; VLM/audio
captions are addressed by `block_id` + native locator and enter E2 as named context, **never spliced
inline** into the offset-bearing markdown. *Context:* keeps E1/E2/D32 modality-blind, and structurally
prevents a nondeterministic caption re-run from shifting the char offsets of deterministic transcription
claims (completeness risk 17). *Refines* D38.

**D50 — The polymorphic grounding locator + three provenance classes (the honest D32 generalization).**
*Decision:* locator union `text(char_span) | image(page,bbox,coord_space) | av(t_start,t_end,time_base
[,speaker][,keyframe,bbox])`; bbox **normalized at the boundary** to one 0–1000 top-left space (raw
producer space recorded in provenance for audit); time = exact rational PTS; relative speaker labels.
Three provenance classes — `transcription` (verbatim source, full D32 substring stack, may
confident-supersede), `uncertain_transcription` (HTR/degraded/low-confidence — verbatim-in-its-own-output
but the read is a lossy guess; **may not** confident-supersede; higher audit), `description` (model
assertion: L0 in-bounds + region-overlap + quoted-text-match + entailment + origin stamp; **never**
confident-supersedes). *Context:* "verbatim" is always w.r.t. the converted text, never the signal;
per-claim deterministic faithfulness is genuinely *softened* for descriptions, so faithfulness rides
in-call entailment + an **offline sampled audit whose per-class rate is a first-class measured safety
parameter** — F1's "auditability improves" is dropped, F3's account adopted, and the third class added
(completeness gaps 3/11). *Refines* D32 and D42; *annotates* D41 (when-said ≠ when-true), D43, D44
(locator is still never a graph node). *Chooses one schema*, ending the F1/F2/F3 three-way disagreement.

**D51 — MediaIndex: the temporal/structural analogue of PageIndex; `document_sections` becomes a
polymorphic structure tree.** *Decision:* video → shots→scenes→chapters tree; long audio →
acoustic/topic-segmented chapter tree (no shot detector); image/page-set → page→region tree; single image
→ synthetic root. `document_sections` gains a `locator_kind` discriminator; `char_start/char_end` stay
mandatory for transcription nodes; native-locator columns are additive; the `role` enum extends with image
and av roles for in-call Selection. *Context:* the scene/chapter tree is the structural backbone E1 chunks
along (one scene ≈ one chunk) and the path/role signal E2 reads — the PageIndex role with temporal
locators. *Sibling of / refines* D39.

**D52 — The media cheap-first cascade is fixed and per-stage versioned; long-running `convert` is
checkpointed and resumable.** *Decision:* order = demux → image-class-route/shot-detect →
ASR+align+diarize → keyframe+pHash dedup → OCR → detect/redact → scene-merge → **selective VLM/audio
caption** → chapter roll-up → bounded-clip escalation; the caption rung is the only expensive,
nondeterministic stage, **budget = shot/scene count, not duration**; native whole-video frontier ingestion
is escalation-only. Each stage independently versioned in a `conversion_manifest`; idempotency grain =
`content_hash + stage + stage_version` (refining D36); D33's replay-from-storage is **explicitly extended
to these E0 media stages**; `convert` runs as a durable, stage-checkpointed job (not the fast-text
2-retry/dead-letter envelope), resuming from the last checkpoint on a late-stage failure. **No learned
per-frame value gate** (the video reincarnation of the rejected D25 gate); partial conversion proceeds on
the stable deterministic pipeline (descriptions enrich, never block); a deterministic-stage failure
quarantines. *Refines* D38, D12/D36, D33; *binds* D4/D25.

**D53 — The modality routing matrix (close the input space).** *Decision:* explicit routes —
image-class router (natural/screenshot/scan/chart/handwriting/low-quality) *before* OCR; animated GIF /
multi-frame WebP/APNG / multi-page TIFF → the video cascade or a page-set enumerator (never single-frame
collapse); long audio → topic/acoustic-segmented MediaIndex + a sound-event/audio-caption DESCRIBE rung;
embedded child-media (video-in-PPTX, audio-in-email, `<video>` in HTML) → its own nested `media_id` under
the parent via the `crossref` sub-worker; diagram→structure (flowcharts/org-charts/ER-diagrams) flagged as
a known recall limitation (a flat caption loses node/edge structure). Canonical-language policy:
`document.md` is **source-language-faithful** (verbatim grounding), while E2 emits `claim_text` in the
deployment's canonical working language with `source_span` kept in source language — so cross-language
`evidence_count` collapses while window-membership stays honest. *Context:* the brief named these inputs;
the F-series under-routed them (completeness missing-cases 1–7). *Extends* D38/D49.

**D54 — P1 two-tier visual sub-index (single-vector always-on + gated late-interaction); embeds redacted
pixels; ~20× Tier-B storage on the gated slice.** *Decision:* Tier A single-vector unified-encoder
(always-on) + Tier B ColQwen/ColNomic multi-vector MaxSim (gated to visually-rich units), one Lance
estate, `embedder_version`-stamped, replayed from stored E0 image artifacts; recipes `visual_similarity`,
`find_visual`, `find_frame`, `visual_maxsim_rerank` are RRF candidate generators returning locators (zero
LLM, no authority, never project to P2). *Context (storage correction, the critic's O1):* Lance
multivector is cosine-only/no-binary, so pool-3+fp16 ≈ **~86 KB/page ≈ ~20× single-vector** on the gated
slice — **not** the "~5–6 KB comparable" of F1/F4 (which needs binary quant Lance lacks); accept ~20× on
the gated slice, hamming-engine a documented alternative. *Biometric boundary:* the index embeds
**redacted** keyframes (D57), so image→image similarity is structurally not a face-matching gallery, and
person-dominant queries are barred from the face recipes (completeness risk 18). *Extends* D8/D9; *binds*
D6/D18/D44.

**D55 — Media-derived facts use the unchanged E2/E3/D41/D43 belief layer over a polymorphic context
bundle; intra-document cross-track contradiction resolves by provenance-class confidence; entity
resolution is text-mediated only.** *Decision:* the E2 bundle gains media-typed elements (transcript
window, scene path, scene caption, OCR block, neighbour segments, mapped speaker labels) by `block_id`,
extractor unchanged; a media-read value → observation (D43) with bbox/timecode evidence provenance, no
schema change; conflicting same-locator tracks order by `transcription > uncertain_transcription >
description` (a model-read value never confident-supersedes a verbatim one); names from OCR/transcript/
relative speaker labels resolve via T0–T4, visual content emits candidate name strings only (never
`entity_id`s); a person on camera never named in text is an acknowledged recall gap (`#22` twin).
*Refines* D31, D43, D42; *binds* D17.

**D56 — Capture time is an immutable, lower-precedence validity seed (refines D41).** *Decision:*
precedence content-asserted grounded date > capture time (`captured_at`/`capture_precision`/
`capture_source`) > ingestion time; immutable, many-valued-by-document, fact-identity-free (D41's
non-authority properties hold); other EXIF (GPS/device) is PII, stripped at redaction, never auto-promoted.
*Context:* a screenshot depicts the state at capture, the media analogue of a document header date.
*Refines* D41.

**D57 — Media privacy: the versioned detect/redact sub-worker + biometric non-storage invariant +
content-safety + authenticity; mounting gated on a measured redaction-recall floor.** *Decision:* a
versioned `detect/redact` stage; the redacted derivative is the canonical mounted/indexed/embedded
artifact, raw is quarantined-and-shreddable; **never persist face/voice templates** (the GDPR Art. 9 /
EU-AI-Act / BIPA lever); detect-and-flag (`has_faces`, `has_onscreen_pii`, `has_third_party_audio`) **plus
an illegal-content hash-match hook** (`csam_suspected`/`id_document`/`child` findings, stated §2258A/NCMEC
posture: flag+quarantine+route to the deployment reporting workflow) **plus C2PA authenticity passthrough**
(distinct from D42 origin; deepfake detection a non-goal); self-hosted redactors default, cloud opt-in
with DPA; **mounting/P1/retrieval gated on a measured redaction-recall floor (binding rule, not a spike
outcome)**. *Context:* faces/voices/on-screen PII are a genuinely new first-class concern the text pipeline
never had; CSAM reporting is a strictly larger legal exposure than biometrics and was absent from F6
(completeness gaps 14/15/21). *Extends* D36/D37.

**D58 — Subject-level deletion by crypto-shred + Lance prune, keyed on the entity registry (closes #24,
folds O4).** *Decision:* resolve subject → `entity_id` (registry = deletion key); destroy the per-document
DEK (reaches PITR backups, bucket-locked raw, GCS soft-delete, aged snapshots as unrecoverable ciphertext);
Lance compaction-with-prune (tombstone ≠ erasure); bounded/keyed P-snapshot retention; the O4 K
input-manifest (claim/relation/observation IDs per compiled file) reaches K; re-redact-and-re-derive (with
per-subject sub-keying) for shared documents. *Context:* ugm trains no models, so it escapes
machine-unlearning by construction (D7); crypto-shred is the general answer to #24 (works for text too),
media is the forcing function. *Extends* D37; resolves `#24`; folds O4/`#13`.

**D59 — Multimodal non-goals (the one reconciled list, with rationale + opt-in alternatives).**
*Decision, as scope boundaries (CLAUDE.md Rule 2):* no parallel multimodal belief track; no single-blob
video conversion; no per-frame/dense-uniform captioning (shot-bounded selective is the design); no
biometric face/voice recognition or cross-media identity gallery; no emotion/sensitive-trait
categorization; no native-whole-video-as-substrate (escalation-only); no live/real-time/streaming ingestion
(immutable bounded asset only); no open-world visual entity linking; generated captions are never source
truth; raw media is never on the default mounted browse path; **and the union the per-doc lists missed —
3D/spatial media (point clouds, LiDAR, 360°/VR), interactive content (live HTML canvas/dashboards), and
standalone deepfake detection.** Each carries an opt-in-per-deployment alternative where genuine. *Binds*
D2/D3/D6/D8/D20/D43/D44.

> **Decision-numbering note for the editor.** F1–F6 and codex each independently numbered from `D45`;
> `D45` alone meant six different things across the corpus. The block above is the single reconciled
> sequence; when transcribing into `decisions.md`, ignore the per-doc numbers and use D48–D59 here.
> (Originally D45–D56; renumbered +3 after the K-plane design took D45–D47 in the canonical log. The
> archived `design_fit/` and `external_agents/` docs keep their historical D45+ numbers.)

---

## 5. Design-doc deltas (exactly what changes)

**`decisions.md`** — append **D48–D59** (§4). Annotate as *refined in wording, not substance*: **D32**
(polymorphic locator + the honest faithfulness split, char floor kept), **D38** (richer block + media
routes), **D41** (capture-time seed), **D42** (verbatim-vs-asserted + authenticity axes), **D43**
(observation evidence carries a media locator), **D12/D36** (stage-grain idempotency + checkpointed
long-running `convert`), **D33** (replay-from-storage explicitly generalized to E0 media stages), **D44**
(a locator/value is still never a graph node).

**`plan/designs/e0_files_design.md`** — the largest delta. §1 chain: add the `redact` sub-worker
(`ingest → convert → redact → structure → crossref`) and the checkpointed long-running-`convert` execution
model (§2.8). §2 storage: `documents` media columns + per-stage version stamps + `captured_at`/privacy
flags/`content_safety_flag`/`authenticity`/`dek_id`/`redaction_recall_class`; the polymorphic
`document_sections` DDL; the video artifacts layout (`mediaindex.json`, `keyframes/`); Archive/Coldline raw
class; rewrite the deletion paragraph from document-level to **subject-level crypto-shred + Lance prune**
(D58). §3 `convert()`: generalize the signature to `{document_markdown, blocks[], structure, manifest}`;
add the image-class router, image route, and the video/audio cascade tables; pin the dual-locator + the
deterministic-pipeline/block-ID-side-channel rule (D49). §4 PageIndex: generalize to a per-document structure
tree incl. the MediaIndex shape and extended `role` enum (D51). New **privacy** section (D57): redact
sub-worker, biometric non-storage invariant, detect-and-flag incl. CSAM hook + C2PA passthrough, the
mount-gating recall floor. §7: add a worked **video** walkthrough.

**`plan/designs/e2_e3_claims_relations_design.md`** — §3.1: the polymorphic E2 bundle (media-typed
elements by `block_id`). §3.3: grounding becomes triple-field (`claim_text` + `source_span`/char offsets +
`native_locator`); add the **three-provenance-class** acceptance branch (§2.5 table) and the
`derivation`/`verbatim_groundable` stamp; state the honest faithfulness split. §5: a chart/spoken
measurement → observation with bbox/timecode evidence provenance; intra-document cross-track contradiction
by provenance-class confidence; cross-language `evidence_count` via the canonical-working-language policy.

**New `plan/designs/media_design.md`** (the binding media doc) — owns the cross-cutting media spec so the
above three docs reference rather than duplicate: the `convert()` media contract + cascade tables (image,
video, long-audio); the MediaIndex; the three provenance classes + the honest grounding account; the
**P1 two-tier visual sub-index** (the two Lance tables, the two gates, the recipes, the locator bridge,
the corrected ~20× Tier-B number, the redacted-embedding biometric boundary); the modality routing matrix;
privacy (redact/detect, biometric non-storage, CSAM, C2PA, recall-floor gating); the subject-level deletion
cascade; and the reconciled non-goals. (Absorbs what F4 called `p1_visual_retrieval_design.md` — keep it
one doc to avoid re-fragmenting.)

**`plan/designs/overall_design.md`** — plane diagram: media enters at E0, the E pipeline is unchanged, P1
gains a multimodal retrieval channel (reinforce D6: beliefs text-only). §2 stores table: P1 row += visual
units; raw bucket += Archive/Coldline + DEK. §6 retrieval: add the four visual recipes + the locator-bridge
rule (no recipe answers "what is true" alone). New **"Deletion & erasure"** section (D58). README: E0 says
"converted to textual + structured media artifacts"; auditability mentions text spans **plus** media
locators **and** the honest faithfulness caveat.

**`plan/designs/postgres_schema_design.md`** — the `document_sections` polymorphic columns; `documents`
media columns + version stamps + privacy/key/authenticity columns; claim/`relation_evidence`/
`observation_evidence` gain the locator fields (a **locator child table** for multi-locator claims) +
`derivation`; P1/Lance scalar locator columns; the deletion-worker responsibilities (DEK destroy + Lance
prune + snapshot/K reach).

**`plan/requirements/requirements_v3.md`** — name *multimodal ingestion (image/audio/video)* as in-scope;
restate the deletion-cascade requirement as **subject-level crypto-shred reaching every derived layer**
(D58); add the *biometric non-storage*, *redaction-recall-floor*, *CSAM-reporting posture*, and
*C2PA-authenticity* obligations; record the reconciled non-goals (D59).

**`questions.md`** — mark **#24 resolved-by-D58** (crypto-shred + prune + registry key + O4 manifest) and
**O4/#13 folded into D58**; update **#3** (embedding model/dim) to also cover the cross-modal Tier-A
embedder + the Tier-B late-interaction model; add to **#22** "visual-only entities (on camera, never named
in text)"; log the §6 spikes (flagging the Lance multivector latency and the redaction-recall floor as
decision gates); cross-reference the new `media_design.md`.

---

## 6. Open risks & what to prototype first (highest-leverage first)

1. **Grounding catches VLM-description hallucination on ugm's real image mix.** The whole "describe to
   text is safe" claim rests on the bbox-anchor + OCR-window-membership + entailment floor actually
   rejecting bad captions, and on the **description-class L4 sample rate** being right. The
   "grounded-captioning −25–28% hallucination" result is task-dependent (the research already flags a
   counter-paper). *Spike:* measure on a golden image set before trusting DESCRIBE output as claim source;
   set the per-class L4 rate. **Gates** the honesty story (D50).

2. **The dual-locator decoupling actually holds across re-conversion.** Verify that the deterministic
   transcription linearization is byte-stable at pinned versions, that descriptions live purely in the
   block-ID side-channel, and that a `vlm_caption_version` bump re-runs *only* the affected E2 scene
   calls without churning any transcription claim's `source_span`. Also: a `shot_detect_version`/
   `scene_merge_version` bump moves scene boundaries → pin locators to the producing stage version and
   confirm old claims resolve against their own `conversion_generation`. **Gates** D49/D52.

3. **The three-provenance-class supersession rule is correct and measurable.** Measure how often a numeric
   observation comes from verbatim OCR/ASR vs an `uncertain_transcription` (HTR/degraded) vs a model-read
   chart, and confirm the adjudicator margin so neither an `uncertain_transcription` nor a `description`
   value can confident-supersede a clean-`transcription` prior. Includes OCR/ASR WER/CER on the
   handwriting/degraded slice (the inputs where the anchor is hollowest). **Gates** D50/D55.

4. **Lance multivector latency + the real Tier-B storage at scale (the load-bearing P1 unknown).** No
   published LanceDB-at-scale multivector number exists. *Spike:* load Tier B for a realistic
   visually-rich slice (pool-3 + fp16, IVF_PQ), measure two-stage P95 vs the Tier-A baseline, and confirm
   the **~20×** (not ~5–6 KB) storage is acceptable. **Decision gate** for whether Tier B stays in Lance
   or triggers the documented hamming-engine alternative (D54).

5. **Redaction recall on adversarial media (the real safety metric).** "A missed face is an un-redacted
   face." Measure CenterFace/deface + Presidio recall on small/occluded faces, far-field/overlapping
   voices, on-screen secrets; set the **mount-gating recall floor**. Validate the CSAM hash-match hook and
   the C2PA manifest passthrough end-to-end. **Gates** the structural D57 safety claim (which is otherwise
   only as good as detector recall).

6. **Crypto-shred + Lance-prune at 1M-doc scale.** Validate per-document DEK + KMS (key count, rotation,
   latency/cost on the deletion path), confirm destroying one DEK never harms another subject, exercise
   the re-redact-and-re-derive path for shared documents, and measure compaction-with-prune
   latency/throughput. **Gates** D58 / `#24`.

7. **ASR time-anchor + Czech + intra-document attribution.** WhisperX word-timecode precision and pyannote
   DER on *real* video (music/overlap/far-field) and the Czech path (Canary-1B-v2 swap, 7.86% vs 11.33%
   WER) — and the speaker→entity false-attribution rate ("Alice said X" when Bob spoke), which poisons "X
   said Y" claims. Confirm Gemini is never the timecode source (documented >10-min drift). **Gates**
   D52/D55.

8. **The downstream belief-extraction cost (the cost the F-docs never counted).** Media is a
   text-amplifier: a 1-hour meeting → a massive transcript; a dashboard screen-recording → hundreds of
   value observations/minute. The "<$50k once" framing prices only conversion; the real per-document LLM
   bill is **E2 Claimify + E3 + T0–T4 + D43 adjudication** over verbose media-derived text, plus
   re-conversion/re-embedding amortization on version bumps and the hot keyframe/page-image storage class.
   *Spike:* measure the pipeline cost per media-class and the version-bump re-run cadence as first-order
   budget items. **Gates** the cost model in requirements_v3 / `questions.md #2`.

9. **Cross-modal & cross-language dedup / `evidence_count`.** Confirm the same fact stated in a chart and
   in prose collapses to one observation/relation (not two), and that English + Czech videos asserting the
   same fact collapse under the canonical-working-language policy (RTL/Unicode-normalization of the
   window-membership substring check is a sub-spike). **Gates** D2's media promise + D53.
