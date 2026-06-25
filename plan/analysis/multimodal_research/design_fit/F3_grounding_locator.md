# F3 — Grounding generalization: the polymorphic media locator (D32 → all modalities)

**Design-fit question.** D32 grounds every claim to an exact source location: a standalone
`claim_text`, a verbatim `source_span` with **character offsets** into the converted text, accepted
by **anchor** (the span is a real slice), **window-membership** (added substrings verbatim-exist in
their bundle source), and **entailment**. Generalize `source_span` into a **polymorphic media
locator** that keeps the invariant *"every claim traces to an exact source location"* when the source
is a pixel region or a video frame — and when the intervening "text" was produced by a **lossy,
non-deterministic VLM/ASR**. This is the auditability crown jewel; it must not soften when pixels
enter the system.

Grounded in D2, D6, D7, D12, D32, D33, D37, D38, D39, D41, D42, D43. Research base:
`web_research/M1–M6`, `repo_findings/{docling,mineru,whisperx,pyscenedetect,colpali}`. Numbers are
starting points to measure (CLAUDE.md Rule 2).

---

## 1. Verdict / recommendation

**Generalize D32 by splitting one field into two coordinated parts, and splitting one acceptance
stack into two provenance classes. Do not weaken the char-offset floor — extend it.**

1. **Keep the char-offset pipeline exactly as D32 has it.** E1/E2 always operate on the converted
   Markdown, so *every* claim still carries a `source_span` = char offsets into that Markdown. This
   is the universal, deterministic anchor for **all** modalities — text, image, audio, video — and it
   does not change. The Markdown is a deterministic *linearization* of the conversion (transcript
   interleaved with bracketed captions/OCR), so offsets exist for pixels and audio too (M2/M5).

2. **Add a polymorphic `native_locator` carried by every conversion block and inherited by every
   claim/evidence row.** A tagged union: `text` → char span; `image` → `page + bbox`; `av` →
   `timecode range (+ optional keyframe bbox + relative speaker label)`. The claim's native locator is
   *derived* — the block(s) its `source_span` falls into hand down their locator. The char offset
   says *where in the converted text*; the native locator says *where in the pixels / the timeline*.

3. **Split grounding into two provenance classes, because "verbatim-checkable" splits the world** —
   this is the heart of F3:
   - **Transcription** text (digital extraction, OCR, ASR) **is real source text**: the printed glyphs
     / spoken words verbatim-exist in the converted Markdown. It grounds via the **full D32 substring
     stack (anchor + window-membership)** *plus* the native locator as an additional spatial/temporal
     pin. ASR maps onto D32 unchanged — a transcript span is a verbatim, time-anchored slice (M3/M5).
   - **Description** text (VLM image/figure caption, chart→prose, video scene caption) **is a model
     assertion about a region — not a slice of anything**. It cannot pass a verbatim source-substring
     anchor. It grounds via **locator-membership + entailment + an origin stamp**, and its substring
     anchor fixes only *provenance-to-this-caption*, never faithfulness. The honesty guarantee moves to
     "the region is real, in-bounds, and overlaps detected content" + "the caption is entailed by the
     OCR/ASR + detected objects in that region" + "this claim is marked model-derived so confidence
     math never treats it as independent corroboration" (M1 §2.5, M5 STEAL-3, D42 instinct).

4. **State the one honesty caveat loudly.** "Verbatim" is always *with respect to the converted text*,
   never the pixels/signal. A verbatim OCR slice proves `claim ⊆ OCR-output`; whether the OCR *read
   the glyphs correctly* is a **separate fidelity axis**, measured by the sampled audit (D32 layer 4),
   not asserted by the anchor. Same for ASR. This keeps the guarantee precise instead of overclaiming.

This is a refinement of D32/D38, not a new plane (M5's central finding: multimodality is an
E0-`convert()` + grounding-locator problem). The downstream pipeline — E1 chunk, E2 Claimify, E3
relations/observations, supersession, K, P — runs unchanged on `text + a locator`.

---

## 2. The design, concretely

### 2.1 The universal substrate: converted Markdown stays the text pipeline

The converter (D38) already returns `{ markdown, blocks[] }`. Generalized, **the Markdown is a
deterministic linearization of the native medium**, and every block records *both* where it lives in
the Markdown *and* where it came from in the source:

```
block := {
  block_id,
  markdown_span:    [char_start, char_end),   # offsets into document.md  (the D32 floor, unchanged)
  native_locator:   <MediaLocator>,           # where in the source medium (below)
  provenance_class: "transcription" | "description",
  role:             body | figure_caption | table | transcript | ocr_text | scene_caption | ...,
  producer:         { engine, model, version, prompt_version },   # D7/D33 — replay key
}
```

For a PDF this is what Docling/MinerU already emit (page + bbox per element; `repo_findings`). For a
video the Markdown is the diarized transcript interleaved with `[on-screen: …]` OCR lines and
`[visual: …]` scene captions, each line carrying a timecode (M2 §4.2). E1/E2 never need to know the
modality — they read Markdown and char offsets, exactly as today.

### 2.2 The polymorphic MediaLocator (the schema)

```
MediaLocator := {
  kind: "text" | "image" | "av",
  doc_id, content_hash,                 # which document / which immutable bytes (D37)
  conversion_generation,                # (converter_version, + asr/ocr/vlm version) — locator is pinned to it (D7)

  # --- kind == "text" -----------------------------------------------------
  char_span:  [start, end),             # offsets into document.md  (digital extract: lossless)

  # --- kind == "image" ----------------------------------------------------
  page:       int,                      # 0-based page / image index
  bbox:       { l, t, r, b },           # ONE canonical space: 0–1000 grid, origin TOP-LEFT (see §2.5)
  region_kind: text|table|formula|picture|chart|figure,   # the layout category that owns this box

  # --- kind == "av" -------------------------------------------------------
  t_start, t_end: rational PTS,         # EXACT presentation timecodes (Fraction), not frame numbers (VFR-safe)
  t_display:      "HH:MM:SS.mmm",       # derived human form
  keyframe_uri?:  gs://…,               # content-addressed keyframe crop (md5), if a frame pin exists
  frame_bbox?:    { l, t, r, b },       # optional spatial pin inside the keyframe (0–1000)
  speaker_label?: "SPEAKER_02",         # ASR: DOCUMENT-RELATIVE diarization label, never a person identity
}
```

Design choices, each lifted from a verified source:
- **0–1000 normalized bbox, top-left origin** as the single canonical space (MinerU's `_build_bbox`
  pattern: resolution-independent, survives re-render). Convert *normalizes at the boundary* —
  Gemini's `[ymin,xmin,ymax,xmax]/1000`, Claude's post-resize pixels, Docling's `BOTTOMLEFT` PDF
  boxes, MinerU's pixel@200dpi all collapse to this one space, with the original space recorded in
  `producer` for audit (M1; repo_findings/{docling,mineru}).
- **Rational PTS, not frame numbers**, as the durable temporal address (PySceneDetect's
  `FrameTimecode`: `frame_num` is an *approximation* for variable-frame-rate video; PTS+`time_base` is
  exact). A scene's `(start,end)` maps straight back to a byte/frame offset in the original (M2;
  repo_findings/pyscenedetect).
- **Content-addressed keyframe crops** (md5 of pixel bytes) so identical frames dedup and references
  stay stable across re-runs (MinerU pattern).
- **Relative speaker labels only** — `SPEAKER_02`, never a real identity (M6/D20; §3).

The locator is **derived from blocks, stored on the claim/evidence row.** A claim's `source_span`
(char offsets) is resolved to the conversion block(s) it overlaps; those blocks hand down their
`native_locator`. One claim may carry several (a sentence spanning a transcript line + an on-screen
OCR line → two locators, one `av` timecode + one `image` frame bbox).

### 2.3 Acceptance layers, per provenance class (the crux)

D32's four layers generalize. The cheap deterministic floor gains a **Layer 0 (locator resolves)**,
and Layers 1–2 branch on provenance class. Layers 3–4 are unchanged in spirit.

```
                         TRANSCRIPTION block                  DESCRIPTION block
                         (digital text / OCR / ASR)           (VLM caption / chart→prose / scene caption)
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  L0  locator resolves   native_locator well-formed & IN-BOUNDS for its medium (deterministic, ALL):
      (NEW, all)           text: char_span ⊆ [0,len(md))
                           image: page∈range ∧ bbox⊆page-geom ∧ area>0
                           av:   0≤t_start<t_end≤duration ∧ keyframe_uri exists ∧ frame_bbox in-bounds
                         → off-page / past-EOF / zero-area / negative-duration  ⇒ REJECT
                           (the pixel/temporal equivalent of a non-substring span)
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  L1  anchor             source_span is a real, in-bounds      source_span is a real slice of THE CAPTION
      (deterministic)    VERBATIM slice of document.md.        text in document.md → fixes provenance
                         = source text. (D32 UNCHANGED.)       *to this caption only*, NOT faithfulness.
                         av extra: the slice's words carry      The faithfulness anchor is L0 + L2(a).
                         word-timecodes ⊆ [t_start,t_end]
                         (WhisperX word alignment).
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  L2  window-            (a) every added_context substring     (a) the locator's region OVERLAPS a detected
      membership             verbatim-exists in its declared       content block (Rung-0 layout/shot found
      (deterministic)        bundle element. (D32 UNCHANGED.)      something there — not empty pixels / dead air);
                         (b) bundle elements may include the   (b) any QUOTED on-region text in the caption
                             co-located transcription              verbatim-exists in the OCR/ASR transcript
                             (same-page OCR, same-shot ASR).       of that same region/timecode
                                                                   (rejects fabricated on-screen quotes).
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  L3  entailment         chunk + bundle entail the claim;      the region/clip content (OCR text + detected
      (in-call)          "X said Y" ⇒ "X said Y" not "Y"       objects + co-located transcript) entails the
                         (ASR: diarized speaker → after T0–T4   caption, and the caption entails the claim.
                         resolution, "Alice said Y").          This is the PRIMARY honesty gate here.
  ──────────────────────────────────────────────────────────────────────────────────────────────────
  L4  sampled audit      independent re-check of a sample      independent re-check re-examines the
      (offline)          (D32 UNCHANGED).                      NATIVE region/frame (did the caption follow
                                                               from the pixels?) at a HIGHER sample rate —
                                                               this is where lossy-nondeterministic risk
                                                               is actually measured.
```

**Why this is correct, in one line each.** A transcription block *is* a quotable source, so the old
substring machinery applies verbatim and the locator is a bonus pin. A description block is *not* a
quotable source, so the substring anchor degenerates to "which caption did this come from", and the
real guarantee becomes geometric/temporal (the region is real and contains detected content) +
logical (entailment) + epistemic (marked model-derived). Quoted text inside a caption is the one
bridge back to verbatim — it is checked against the co-located transcription (M1 §2.5).

### 2.4 Origin propagation → confidence (the D42 instinct, applied to pixels)

Every claim inherits a `derivation` from the block(s) it grounds in:

```
derivation ∈ { digital_text, ocr, asr, chart_extraction, vlm_description }
verbatim_groundable := derivation ∈ { digital_text, ocr, asr }      # L1 anchor is a faithfulness guarantee
```

A claim whose anchor **or** added-context touches a `description` block is stamped
`derivation = vlm_description` (taint propagates) and is **never counted as independent
corroboration**: N captions of the same frame by the same model are not N evidence rows (D2's
`evidence_count` must not be inflated by model echoes — exactly the D42 self-confirmation guard,
here for pixels). `chart_extraction` (chart→CSV values the VLM *read off a plot*, not printed glyphs)
is classed `description`, because the numbers are model-inferred, not transcribed — unless the value
was an OCR'd printed cell, which is `ocr`.

### 2.5 Worked examples

**(a) Scanned invoice, OCR.** Rung-0 OCR emits a block `role=text, provenance=transcription,
native_locator={image, page:2, bbox:[120,300,880,340], region_kind:text}`, markdown
`"Total due: $4,200 by 2024-03-01"`. E2 yields claim *"Invoice INV-77 total due is $4,200."* L1: the
span `"Total due: $4,200"` is a verbatim slice of the OCR Markdown ✓. L2: added `"INV-77"` traces to
the same page's OCR header block ✓. Locator → `(page 2, bbox …)`. Auditor can draw the box on the raw
page. `derivation=ocr`, counts as evidence.

**(b) Bar chart, VLM description.** Rung-1 VLM writes a block `role=figure_caption,
provenance=description, native_locator={image, page:5, bbox:[60,400,560,760], region_kind:chart}`,
caption `"[visual: revenue grew from $5M (FY2022) to $7M (FY2023)]"`. Claim *"Acme FY2023 revenue was
$7M."* L0: bbox in-bounds, area>0 ✓. L1: the span is a slice of the caption → provenance fixed to
*this* caption (not faithfulness). L2(a): the bbox overlaps a `chart` block the layout pass detected ✓
(not blank margin). L2(b): if the caption quoted `"$7M"` and the axis label `"$7M"` was OCR'd in that
region, it matches ✓. L3: the chart region + OCR'd axis labels entail the caption ✓. → accepted, but
`derivation=vlm_description`; in E3 this becomes an **observation** on Acme (D43) with the chart bbox
as evidence provenance, **not** independent corroboration of a separately-OCR'd $7M.

**(c) Meeting video, ASR + scene caption.** WhisperX block: `role=transcript,
provenance=transcription, native_locator={av, t_start:00:12:03.250, t_end:00:12:07.900,
speaker:"SPEAKER_02"}`, text `"we shipped Atlas in March"`. Claim *"SPEAKER_02 said Atlas shipped in
March 2024."* L1: verbatim slice of transcript ✓; words' timecodes ⊆ the block range ✓ (M3 word
alignment — *not* a drifting Gemini timestamp). L3: "X said Y" ⇒ "SPEAKER_02 said Y", and after T0–T4
resolution the speaker label resolves to a person mention (M5 STEAL-4). The asserted-validity interval
(D41, *March 2024* = when Atlas shipped) is a **different axis** from the locator timecode (12:03 = when
it was *said*) — both stored, never conflated. A parallel `[visual: a slide titled "Atlas GA"]` block
at the same timecode is `provenance=description` and grounds by frame-membership + entailment.

---

## 3. How it preserves ugm invariants (cite Dx)

- **D32 — generalized, not replaced.** The char-offset `source_span` and the four acceptance layers
  survive verbatim for transcription; the locator is additive and the description branch is a strict
  *tightening* (it adds L0 in-bounds + L2(a) content-overlap that text never needed). The crown-jewel
  property — *every claim traces to an exact location* — now reaches pixels and timecodes.
- **D38 — same router, richer block.** `convert(bytes, mime, hints)` still returns `{markdown,
  blocks[]}`; blocks gain `native_locator + provenance_class + producer`. New routes (image→OCR+VLM,
  audio→ASR, video→scene-detect+ASR+keyframe-VLM) return the *same* shape. Markdown stays the offset
  pipeline.
- **D7 / D33 — versioned, replay-from-storage.** Every non-deterministic producer (OCR, ASR, VLM
  caption, scene-detect) is versioned and its output persisted; the locator is **computed once and
  stored**, pinned to a `conversion_generation`, and **replayed on rebuild — never re-derived
  nondeterministically**. A converter/model bump mints a new generation; old claims' offsets remain
  valid against the conversion that produced them (D12 idempotency on `content_hash + producer
  version`).
- **D37 — raw immutable, locator resolves into artifacts.** The locator addresses the *artifact*
  (converted Markdown, `conversion.json`, content-addressed keyframe crops) for the normal audit path,
  and the same `(page,bbox)` / `(timecode)` addresses the **immutable raw bytes** for deep audit —
  the raw is the ultimate ground truth, never mounted, reached only on demand.
- **D41 — when-said ≠ when-true.** For AV the locator timecode is *utterance time*; the asserted
  validity interval is *world time*. Distinct, both immutable evidence, never conflated (example c).
- **D43 — values become observations with a locator-bearing evidence row.** A chart-read figure or a
  spoken measurement becomes an entity-anchored observation; the figure bbox / video timecode rides
  the **evidence** row, not a new belief home.
- **D6 / D8 — locator carries no belief.** It is provenance, stored on Postgres evidence rows and as
  **scalar columns in P1/Lance** (page/timecode/bbox as filters and as the join key from a visual hit
  back to the canonical claim — M4). Visual vectors (ColPali/ColQwen) stay a P1 retrieval projection,
  never authority; a visual hit returns a *locator*, never a fact (M4/M5). Nothing locator-related
  enters the P2 graph (D44: a value/locator is not a node).
- **D2 / D42 — no echo inflation.** `derivation` propagation (§2.4) keeps model-described claims out
  of independent-evidence counts.

**Non-goal (stated, with rationale — CLAUDE.md Rule 2).** Locators address **spatial/temporal
regions, never persistent identities**. ASR speaker labels are document-relative (`SPEAKER_02`); no
durable, matchable **face or voice template** is ever a locator key. Building a cross-media
face/voice gallery is a documented non-goal of the core system (it is the GDPR Art. 9 / BIPA / EU AI
Act "build a biometric database" trigger; M6), consistent with D20's biometric non-goal — an opt-in,
explicit-consent per-deployment capability, never a default of the grounding layer.

---

## 4. Risks / what to measure (spikes)

1. **Locator stability across re-conversion.** Char offsets and reading-order indices shift when a
   converter/structurer version bumps; bboxes are model-predicted (MinerU reading-order is
   version-scoped). Tag every locator with `conversion_generation`; measure citation churn per version
   bump and confirm old claims resolve against their own generation.
2. **Coordinate-space round-trip error.** Normalizing Gemini 0–1000 / Claude post-resize-pixels /
   Docling bottom-left / MinerU pixel@dpi into one 0–1000 top-left space loses precision on
   resize/pad. Measure box drift after round-trip on a golden set; pin the resize math per engine.
3. **"Overlaps a detected content block" threshold.** L2(a) needs an IoU/containment cutoff (caption
   bbox vs detected layout/shot). Too loose accepts captions of blank margins; too tight rejects valid
   wide-context descriptions. Golden-set tune per `region_kind`.
4. **OCR/ASR fidelity vs anchor verbatim-ness.** The anchor proves `claim ⊆ OCR/ASR output`; it does
   **not** prove the read was correct. Measure transcription WER/CER on a golden slice and route a
   confidence-weighted sample to L4 audit; never let the verbatim anchor imply signal fidelity.
5. **Description-class audit rate.** Lossy-nondeterministic captions need a higher L4 sample than
   transcription. Measure caption-hallucination on ugm's own mix (CHAIR/DetailVerify-style) and set
   per-class sampling; the grounded-captioning hallucination reduction (~25–28%, M1) is task-dependent
   — measure, don't assume.
6. **ASR timestamp source.** Use word-aligned timecodes (WhisperX/Parakeet-TDT native) as the time
   anchor; **never** a Gemini-style transcript whose timestamps drift >10 min on long audio (M3). Spike
   the chosen ASR's word-timecode precision on representative (noisy, overlapping) video.
7. **Locator storage at 10⁸.** Per-claim/evidence locator is a few ints/floats (btree-friendly,
   D23-class); keyframe crops are content-addressed/dedup'd. Confirm the column/child-table choice and
   the Lance scalar-filter cost on a corpus slice.
8. **Multi-locator claims.** A claim spanning transcript + on-screen OCR carries ≥2 locators; confirm
   E3/observation evidence rows and the retrieval projections handle a *set* of locators per evidence.

---

## 5. Proposed decisions (continuing from D44) and design-doc deltas

**D45 — Claim grounding carries a polymorphic media locator (generalizes D32 `source_span`).**
Every claim/evidence row keeps `claim_text` + a `source_span` of **char offsets into the converted
Markdown** (the D32 floor, unchanged) **and** a `native_locator` — a tagged union `text(char_span) |
image(page,bbox,region_kind) | av(t_start,t_end[,keyframe_uri,frame_bbox][,speaker_label])` — inherited
from the conversion block(s) the span overlaps. Bboxes are normalized to one 0–1000 top-left space;
timecodes are exact rational PTS; speaker labels are document-relative. The locator is pinned to a
`conversion_generation` and is provenance, never belief (D6).

**D46 — Two grounding provenance classes decide which layers carry the faithfulness guarantee.**
Each block is `transcription` (digital text / OCR / ASR — real source text) or `description` (VLM
caption / chart→prose / scene caption — a model assertion about a region). Transcription grounds via
the **full D32 substring stack (anchor + window-membership) + locator**. Description grounds via
**L0 locator-in-bounds + L2(a) region-overlaps-detected-content + L2(b) quoted-text-matches-co-located-
transcription + L3 entailment + origin stamp**; its substring anchor fixes *provenance-to-the-caption*
only, not faithfulness. **"Verbatim" is always w.r.t. the converted text; signal fidelity (did
OCR/ASR/VLM read correctly) is a separate, measured axis (D32 L4), never asserted by the anchor.**

**D47 — `convert()` blocks generalized; Markdown stays the deterministic offset pipeline (refines D38).**
A block is `{markdown_span, native_locator, provenance_class, role, producer{engine,model,version,
prompt_version}}`. The Markdown is a deterministic linearization (transcript interleaved with bracketed
OCR/captions) so E1/E2/D32 char offsets are unchanged. Image/audio/video routes return the same shape;
every model producer is versioned and **replay-from-storage** (D7/D33), the locator computed once and
stored.

**D48 — Origin propagation + region-aware audit (extends D42 instinct to pixels).** A claim whose
anchor or added-context touches a `description` block is stamped `derivation=vlm_description` and is
**never independent corroboration** (no `evidence_count` inflation, D2). The sampled independent audit
(D32 L4) re-examines the **native region/frame** for description-class claims at a higher,
per-class-tuned sample rate.

**Design-doc deltas this implies:**
- `plan/designs/e2_e3_claims_relations_design.md` §3.3 — grounding becomes **triple-field**
  (`claim_text` + `source_span`/char offsets + `native_locator`); add the provenance-class branch to
  the acceptance layers (the §2.3 table) and the `derivation`/`verbatim_groundable` stamp.
- `plan/designs/e0_files_design.md` §3 (D38) — `blocks[]` gains `native_locator + provenance_class +
  producer`; add the image/audio/video converter routes; note the Markdown-as-linearization contract
  and the MediaIndex/scene-tree (PageIndex analogue, D39) as the locator source for video.
- `decisions.md` — add **D45–D48**; annotate **D32** (generalized, char floor kept), **D38** (richer
  block), **D41** (when-said vs when-true axes), **D43** (observation evidence carries a locator),
  **D44** (locator/value still never a graph node) as *refined in wording, not substance*.
- `postgres_schema_design.md` — `claims` / `relation_evidence` / `observation_evidence` gain the
  locator fields (column set or a locator child table) + `derivation`; P1/Lance gains scalar
  locator columns (page / timecode / bbox) as filters and as the visual-hit → canonical-claim join key
  (M4), no authority.
