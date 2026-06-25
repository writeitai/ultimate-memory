# F1 — The core choice: how multimodal media binds to the ugm pipeline

**Design-fit question.** Should media (images, audio, video) be **(a)** transcoded-to-text at E0 so the
existing E1→E2→E3 text pipeline runs essentially unchanged; **(b)** carried as a parallel multimodal
*evidence* track (native media segments + multimodal embeddings as first-class evidence); or **(c)** a
precise hybrid? This is the load-bearing decision the rest of the multimodal design hangs off.

Research base: `web_research/M1–M6`, `repo_findings/{docling,mineru,whisperx,pyscenedetect,colpali}`.
Pipeline docs: `decisions.md` (D1–D44), `plan/designs/{overall_design,e0_files_design,
e2_e3_claims_relations_design,observations_design}.md`. Numbers here are starting points to measure
(CLAUDE.md Rule 2), not committed constants.

---

## 1. Verdict

**A precise hybrid — but the precision is the whole point, so state it as a split, not a blend:**

> **Belief is transcode-to-text at E0 (option a). Retrieval gains a native-media projection in the P
> plane (the *good* idea inside option b, quarantined to where it belongs). There is NO parallel
> multimodal *evidence* track — pixels and audio never become first-class beliefs.**

Concretely:

1. **The Evidence pipeline (E0→E1→E2→E3) is text.** Every model-derived belief — claim (D2), relation,
   observation (D43) — is a text assertion produced from a **grounded-text transcoding** of the media,
   exactly as a digital PDF's text is produced today. Media changes E0's `convert()` (D38) and the
   grounding *locator* (D32); it changes nothing downstream of E1.
2. **The Projection plane (P1/Lance) gains a multimodal *retrieval* sub-index.** Visual/cross-modal
   search ("find the slide with the revenue waterfall chart") is a real capability that pure text
   reduction loses — but it is a **retrieval entry point, not a belief.** It returns a *locator*
   (doc + page/timecode/bbox), never an assertion. So it lives in P1 as a derived, rebuildable,
   authority-free projection (D6/D8/D9), beside the relation/claim vectors D8 already commits to.

The single load-bearing word in option (b) is **"evidence."** We accept native media *segments and
embeddings* as a **retrieval projection**; we reject them as **first-class evidence/belief.** That
asymmetry is the verdict.

### 1.1 Is "describe media to text" fatally lossy/nondeterministic? No — it is the third instance of a discipline the pipeline already runs twice.

This is the objection that decides the whole question, so it gets answered head-on. Split conversion
into the two jobs every document parser in the research (Docling, MinerU, RAGFlow/DeepDoc, WhisperX)
actually performs (M1 §2.1):

- **Job A — READ (transcription).** OCR of on-page text, ASR of speech, on-screen-text OCR of video
  frames. This recovers text/words **already present in the pixels or audio**; the ground truth exists,
  the model transcribes rather than invents, and faithfulness is achievable by construction (MinerU's
  `pipeline` backend is explicitly "no hallucination"; M1 §2.2). **Crucially, OCR/ASR output is verbatim
  source text** — it satisfies D32's anchor + window-membership rungs *as written*, with a locator
  attached, identically to born-digital text (M5 STEAL-3). Job A is not epistemically suspect; a scanned
  invoice's OCR text is no more a "rewrite" than a digital PDF's extracted text — both are versioned
  `convert()` output over immutable bytes (D38).

- **Job B — DESCRIBE (caption a figure/scene).** *New prose* about what an image or scene shows. This
  **is** a lossy, nondeterministic rewrite — and the system **already accepts exactly this kind of
  rewrite in two existing places**:
  - **OCR itself is already a versioned, nondeterministic model output** routed by `convert()` and
    **replayed-from-storage on rebuild** (D7/D33/D38). A VLM description is the same shape of artifact:
    a versioned converter output over immutable raw bytes — *"a media description is exactly like
    OCR/PageIndex."*
  - **E2 decontextualization is already a lossy, nondeterministic rewrite of source text** — "a
    decontextualized claim is a rewrite, so it can no longer be a verbatim substring of the source"
    (e2_e3 §3.3). The pipeline already turns source text into model-rewritten standalone claims and accepts
    them. It quarantines that rewrite with a specific apparatus, and **the same apparatus covers VLM
    descriptions unchanged**: provenance + entailment grounding (D32's four rungs), version + replay
    (D7/D33), and origin-stamping so a model's own assertion never counts as independent corroboration
    (D42).

So "describe media to text" is **not** a new epistemic hazard — it is the **third instance** of a
pattern the pipeline runs twice already (nondeterministic OCR in `convert()`; nondeterministic rewrite in
E2). The discipline that makes it safe is the discipline ugm already pays: **immutable raw bytes are
ground truth (D1/D37); every model-derived artifact is versioned and replayed-from-storage, never
re-derived nondeterministically on rebuild (D7/D33); the lossy DESCRIBE rewrite is grounded by a
locator + entailment (D32) and origin-stamped as a model assertion (D42).** Nothing about pixels breaks
that contract; they extend it by one locator type.

### 1.2 Where pure text reduction *does* lose a capability — and why P, not E, is the fix.

Pure text reduction loses **visual / cross-modal retrieval.** Late-interaction page-image retrieval
(ColPali / ColQwen — embed the *page image*, skip OCR, score each query token against every image patch
and keep the best match: "MaxSim late interaction") beats OCR-then-embed-text on visually-rich pages
(ViDoRe nDCG@5 **81.3 vs 67.0**; M4 §2.1, M5 §2.4). "Find the slide that *looks like* a waterfall chart"
is a layout query whose answer is a region, not a sentence — unreachable from a text index.

But this is a **retrieval** capability, not a **belief.** A visual hit returns a *locator* into E0
artifacts (doc + page + bbox, or timecode), after which the answer is still a text claim with D32
grounding. The fix therefore belongs in the **P plane**, decisively, for four pipeline reasons:

- **D6 — one belief home.** Putting pixel embeddings on the belief substrate would create a *second*
  authority that drifts against Postgres — the exact Mem0/Graphiti desync class D6 was written against
  (M5 §2.1, §2.3). A P1 retrieval index holds no authority by construction.
- **D8 — vectors live in Lance, not the graph; one vector estate.** A multimodal sub-index is the
  natural extension of the estate D8 already commits to. LadybugDB stays embedding-free.
- **D9 — Lance is the entry channel, then ID-keyed hop to canonical storage.** A visual hit is just one
  more RRF channel that locates a page/timecode; truth is decided downstream in text.
- **D7 / D4 — rebuildable + cheap-first.** Page-images/keyframes persist as E0 artifacts; the index
  re-embeds from them with a pinned `embedder_version` (deterministic given the version), and the
  expensive multi-vector path is gated to visually-rich pages only.

**Verdict in one line:** *belief is text on the E pipeline (transcode-to-text); visual recall is a P1
projection; pixels are evidence only through their grounded-text transcoding, never as a parallel
belief track.*

---

## 2. The design, concretely

### 2.1 Architecture (one diagram)

```
              IMMUTABLE RAW BYTES  (D1/D37 — ground truth, strict IAM, never mounted)
                                       │
        ┌──────────────────────────────┴───────────────────────────────────┐
        │   E0 · convert()  — modality-aware, VERSIONED (D38), cheap-first (D4)│
        │                  part of the per-doc sub-worker chain (D12/D36)      │
        │                                                                     │
        │  READ rung (deterministic, low-hallucination — Job A):              │
        │     image → OCR+layout (MinerU/Docling/dots.ocr)  → text + (page,bbox)
        │     audio → ASR+word-align+diarize (WhisperX)     → text + (t0,t1,spk)
        │     video → scene-detect (PySceneDetect)+ASR+frame-OCR → text + timecodes
        │  DESCRIBE rung (selective VLM, only non-text regions/keyframes — Job B):
        │     figure/scene caption, chart→table  → MODEL-ASSERTION text + locator
        └───────────────┬──────────────────────────────────┬─────────────────┘
                        │                                   │
        grounded text + POLYMORPHIC LOCATORS      persisted media artifacts
        linearized into document_markdown          (page-images, keyframes,
        + MediaIndex (scene tree, D39 sibling)      segment thumbs) + manifests
                        │                                   │
                        ▼                                   │
   E1 ─► E2 (Claimify, D31/D32) ─► E3 (D2/D43)   ◄═ TEXT PIPELINE UNCHANGED      │
   chunks  claims                  relations + observations                   │
                        │                                   │                 │
                        ▼                                   ▼                 ▼
   ╔══════════════════════════════════════╗      ╔══════════════════════════════════╗
   ║  POSTGRES — THE ONE BELIEF HOME (D6)  ║      ║  P-plane PROJECTIONS (derived,    ║
   ║  claims · relations · observations    ║ ───► ║  no authority, rebuildable, D7)   ║
   ║  evidence_count · supersession (D2/D3)║      ║  P1 Lance: text vectors +         ║
   ║  grounding locators (D32, polymorphic)║      ║   MULTIMODAL retrieval sub-index  ║
   ╚══════════════════════════════════════╝      ║   (entry only; locator, no belief)║
                                                  ║  P2 graph (D6/D8) · P3 corpus-fs  ║
       beliefs: TEXT ONLY                         ╚══════════════════════════════════╝
                                            retrieval: text + native media (LOCATOR, never belief)
```

### 2.2 The polymorphic grounding locator (the one load-bearing schema change)

Today a block (D38) and a claim's `source_span` (D32) carry `{char_start, char_end}` into the converted
Markdown. Generalize that single locator into a **tagged union** so "where in the source" survives for
pixels and audio (every research note converged on this — M1 §4.2, M2 §4.3, M3, M5 STEAL-1):

```
media_locator =
  | { kind: "text",  char_start, char_end }                       # born-digital, OCR/ASR markdown
  | { kind: "image", page, bbox, coord_space }                    # bbox = [l,t,r,b]; space ∈ {pixel@dpi, frac, norm0-1000}
  | { kind: "av",    t_start, t_end, [speaker], [keyframe_uri,bbox] }  # exact PTS preferred; frame_num approx for VFR
```

`coord_space` is mandatory because the parsers disagree (MinerU emits pixel@200dpi *and* `[0,1]` *and*
`[0,1000]` across its files; M1/mineru.md) — store the space, normalize on read. For audio/video, store
the **exact rational PTS** as canonical and derive display timecodes (WhisperX/PySceneDetect discipline:
`frame_num` is an approximation under variable frame rate; pyscenedetect.md §6).

D32's four acceptance rungs map onto the new locators **with no new mechanism**:

| D32 rung | text (today) | image | audio/video |
|---|---|---|---|
| 1 · anchor (deterministic) | span is a real slice of the chunk | bbox in-bounds **and** overlaps a detected content block | timecode in-bounds of the segment |
| 2 · window-membership (deterministic) | added substring verbatim-exists in its bundle source | any quoted on-image text verbatim-exists in that region's OCR transcript | quoted speech verbatim-exists in the ASR transcript at that timecode |
| 3 · entailment self-verdict (in-call) | chunk+bundle entail the claim | description follows from OCR text + detected objects in the region | claim follows from transcript + caption at that timecode |
| 4 · sampled audit (offline) | unchanged | unchanged | unchanged |

A VLM description that points at empty/out-of-image pixels fails **anchor** — the pixel-equivalent of a
non-substring span. This is why grounding/auditability *improves* with media rather than degrading: a
claim now grounds to *the chart region at this bbox* or *the speech at this timecode*, not merely to a
generated sentence (M2 §4.3).

### 2.3 The modality-aware `convert()` cascade (extends D38, honors D4)

`convert()` stays the versioned router of D38; it gains modality routes, each a **READ-then-selective-
DESCRIBE** cascade so spend scales with ambiguity, not volume (D4):

- **Image / scanned-or-figure PDF.** Rung 0 (always): self-hosted layout+OCR (MinerU `hybrid`/`pipeline`,
  or Docling+DocTags) → Markdown + `blocks[]` each `{page, bbox, category, reading_order}`, tables→HTML,
  formulas→LaTeX (~$0.0002/page self-host; M1 §2.2). The block `category` (`picture`/`chart`/`figure` vs
  `text`) is the routing signal. Rung 1 (selective): a cheap describer (Gemini Flash-tier or self-hosted
  Qwen3-VL-8B) writes a grounded description **constrained to that region's bbox** for non-text regions
  only. Rung 2 (flagged tail): frontier escalation (Opus/Pro/GPT-5-class) for dense infographics /
  degraded scans. Keep the D38-named hosted default (Mistral OCR) as the buy option; the open stack is
  the scale path.
- **Audio.** WhisperX = `faster-whisper` ASR + wav2vec2 **forced alignment** (aligns each transcribed
  word back to its ±~50 ms audio window) + pyannote **diarization** (clusters *who spoke* into relative
  `SPEAKER_00…` labels) → verbatim transcript with `{word, t_start, t_end, speaker}` (M3; whisperx.md).
  Czech alignment ships by default. **Do not use Gemini as the time-anchor source** — documented
  progressive timestamp drift >10 min on hour-long audio (M3 §2.4).
- **Video.** Deterministic pipeline first: PySceneDetect (cheap HSV/pHash per-frame change score → shot
  cuts; M2 §2.2) → WhisperX ASR → perceptual-hash keyframe dedup (collapses a 5-minute static slide to
  one frame) → frame-OCR → **selective** VLM caption of *one keyframe per shot* (budget = shot count, not
  duration). Native frontier whole-video ingestion is an **escalation reasoner over a bounded clip**, not
  the substrate (its cost is re-paid *per query* and produces no durable structure; M2 §2.1).

**Verbatim media-text (OCR/ASR) is a first-class source body** (routes through D32 as written). **VLM
descriptions enter as `added_context[]` whose source is named `vlm_caption(region@bbox)` / `scene_caption
(@timecode)`** — model assertions, grounded by entailment + region/timecode provenance, **never asserted
as verbatim spans**, and origin-stamped (D42) so confidence math never treats a model caption as
independent evidence (M5 STEAL-3). Every stage is versioned (`ocr_version`, `asr_version`,
`vlm_caption_version`, `scene_detect_version`) and replayed-from-storage on rebuild (D7/D33).

### 2.4 MediaIndex — the PageIndex (D39) analogue for time-based media

D39 gives every document a per-document structure tree. Time-based media gets a **MediaIndex** of the
same shape with **temporal locators** (M2 §4.2): `chapters[] → scenes[] → shots[]` with `{start_tc,
end_tc, keyframe_uri}`, a diarized `transcript[]`, per-scene `visual_caption{text, model_version}`, and a
`conversion_manifest` (every model+version+prompt+policy+artifact_uri). The `document_markdown` that
E1/E2 consume is a **deterministic linearization** of this tree: diarized transcript interleaved with
per-scene `[visual: …]` captions and `[on-screen: …]` OCR, under chapter/scene headings. Each linearized
line carries **both** a char-offset (for the existing E1/E2/D32 anchor path) **and** a `media_locator`
into the MediaIndex node — the true native anchor. A short/simple image gets a synthetic single-section
structure, exactly as D39 already does for short documents.

### 2.5 The P1 multimodal retrieval sub-index (extends D8, two-tier, cheap-first per D4)

A single sub-index in the existing Lance estate (LanceDB supports multi-vector MaxSim natively; M4 §2.4),
per visual unit (page-image | keyframe | video-segment | standalone image):

- **Tier-A (always-on): one single-vector cross-modal embedding** (Cohere Embed v4 / Voyage multimodal-3
  hosted, or Jina-CLIP-v2 / SigLIP-2 self-host) — ordinary HNSW/IVF, ~1–4 KB/unit, millisecond ANN, real
  text→image and image→image search. This is the millions-scale baseline.
- **Tier-B (selective): a ColQwen2.5/ColNomic multi-vector late-interaction column**, materialized **only
  for pages flagged visually-rich** (the OCR pass marked tables/charts/figures, or it routed to scanned
  OCR). Token-pool (pool factor ~3 → −67% vectors @ 97.8% accuracy retained) + fp16, two-stage query
  (ANN coarse → MaxSim rerank). A universal ColPali index would be ~130× single-vector storage — gating
  it to the slice that needs it is D4.

Per-unit columns: `doc_id, segment_id, modality, page_or_timecode, bbox?, mm_vec, [colvecs],
ocr_text/caption (BM25 bridge into the text pipeline), embedder_version, pool_quant_params`. The index holds
**zero authority** (D6): a hit returns a locator into E0 artifacts; beliefs remain text claims (D32).

### 2.6 Where media facts land downstream (no new machinery)

- A measurement read off a chart — "Acme's FY2023 revenue was $5M" — becomes an **observation** (D43)
  anchored to the resolved entity, with the figure's `(page, bbox)` as evidence provenance. A spoken
  "Acme's headcount is 600" becomes an observation with the `(t_start, t_end, speaker)` locator. No typed
  value/period column is added — the value lives in the NL `statement` exactly as D43 specifies.
- A diarized speaker is an **entity mention** (resolved via T0–T4, D17); a spoken date feeds D41's
  immutable asserted-validity interval.
- Two documents asserting the same fact — one in a chart, one in body prose — collapse into **one**
  relation/observation with `evidence_count = 2` (D2), because both arrive at E2 as text. Dedup and
  evidence-collapse work at the fact grain, post-transcoding, unchanged.

---

## 3. How it preserves ugm invariants

| Invariant | How the design honors it |
|---|---|
| **Claims = atomic NL assertions (D2)** | OCR/ASR text and VLM captions both flow into E2 and become the same atomic claims. No new claim type. |
| **Claims ≠ relations; evidence_count/dedup (D2)** | Fact-collapse happens at the text grain after transcoding; a chart-fact and a prose-fact of the same thing become one relation/observation with N evidence rows. |
| **Relation-only supersession (D3)** | Media-derived claims feed relations/observations; supersession adjudicates there, never on claims. Unchanged. |
| **Grounding / auditability (D32)** | The locator generalizes from char-offset to a tagged union; D32's four rungs map cleanly (§2.2). VLM descriptions quarantined as model-assertions; verbatim OCR/ASR are first-class source. Auditability *improves* (region/timecode provenance). |
| **One belief home (D6)** | Beliefs are text only, in Postgres. Pixel/audio embeddings are P1 retrieval projections with zero authority. No second belief store — the explicit AVOID in M5 (Mem0/Graphiti desync; "page image is the memory"). |
| **Rebuild-first; versioned model-derived artifacts (D7/D33)** | Every media stage is versioned (`ocr/asr/vlm_caption/scene_detect/embedder_version`) and replayed-from-storage. Raw bytes immutable (D1/D37). A media description is exactly an OCR/PageIndex-class artifact. |
| **Vectors in Lance, not the graph (D8)** | The multimodal sub-index extends the Lance estate; LadybugDB stays embedding-free; observations/claims never project to P2 (D44). |
| **Zero-LLM query path (D9)** | Visual retrieval is an embedding lookup + RRF fusion channel; the describe-LLM cost is paid once at ingest, never on the query path. |
| **Per-document trigger chain ends at E2 (D12/D36)** | The media cascade is the `convert` (and `redact`) sub-worker of E0's chain, each idempotent on `content_hash + its_own_version`. Aggregates (P1/P2/P3) stay debounced. |
| **No pre-extraction value gate (D25/D34)** | Selective DESCRIBE and shot-bounded captioning are *cost cascades inside convert()* (D4), not value gates on the pipeline; every converted document still fully extracts at E2. |
| **Cheap-first cascades (D4)** | READ (deterministic, near-free) before DESCRIBE (selective VLM) before frontier escalation; Tier-A vectors before selective Tier-B multi-vector. |

### 3.1 Non-goals / scope boundaries (stated, not phased — CLAUDE.md Rule 2)

- **No parallel multimodal evidence/belief track.** Pixels/audio never get their own belief system —
  that is two belief homes that drift (violates D2/D3/D6/D43; the Mem0 `delete_all`/desync class, M5).
  This is a *simplification* (correct at any scale), not a deferral.
- **"Page image is the memory" (Morphik/ColPali-as-canonical) is rejected as the belief layer.** It has
  no claims, entities, temporal supersession, `evidence_count`, or region-grained fact provenance (M5
  AVOID-2). It is admitted only as the P1 Tier-B recall channel.
- **Caption-and-forget-the-locator (Mem0/Cognee) is rejected.** Lossy + unauditable; the generalized
  locator + replay-from-storage is strictly better and the system is already most of the way there (M5
  AVOID-3).
- **Native whole-video frontier ingestion is not the substrate** — it is an escalation reasoner over
  bounded, already-segmented clips (its cost is re-paid per query; M2 §4.5). Documented alternative.
- **Frame-exhaustive / dense-uniform captioning is a non-goal** — shot-bounded selective captioning is
  strictly better on both cost and accuracy (+8–10 pts at small frame budgets; M2 §4.5).
- **Biometric face/voice identification and any cross-media face/voice gallery is a non-goal** (aligns
  with D20's registry-self-contained stance and Claude's own people-refusal policy). The system
  *detects and redacts* faces/PII; it never builds matchable face/voice templates — which keeps it out
  of GDPR Art. 9 / EU-AI-Act / BIPA template liability (M6). Speaker labels stay *relative*
  (`SPEAKER_00`), never resolved to a real person by voiceprint.
- **Lance multivector is cosine-only** (no hamming/binary MaxSim today; M4 §2.4) — pooling + fp16 is the
  accepted lever; a hamming-capable engine is a documented alternative, not a phase.

---

## 4. Risks / what to measure (spikes)

1. **Does grounding actually catch VLM-description hallucination on ugm's image mix?** The "grounded
   captioning reduces hallucination ~25–28%" result is task-dependent (one paper finds it conditional;
   M1 §2.5). Measure the bbox-anchor + OCR-window-membership + entailment floor on a golden image set
   before trusting DESCRIBE output as claim source.
2. **Conversion cascade thresholds.** Which images need the DESCRIBE rung; which escalate to frontier;
   OCR `pipeline`-backend "no hallucination" claim on ugm's real document mix. Extends e0 spike #1.
3. **Linearization + dual-locator contract.** How the MediaIndex (transcript + captions + frame-OCR)
   linearizes into `document_markdown`, and that every line carries both a char-offset (D32 anchor) and a
   `media_locator`. Verify E2 grounding accepts both.
4. **Cross-modal dedup / evidence_count.** Confirm the *same fact* stated in a chart and in body prose
   actually collapses to one relation/observation (D2) rather than two — measure on a planted set.
5. **ASR time-anchor + Czech.** WhisperX word-timecode precision and diarization DER on *real* video
   (music/overlap/far-field), and the Czech alignment path; confirm Gemini is used only as a
   cheap auxiliary, never as the timecode source (drift, M3 §2.4).
6. **P1 multimodal at scale in Lance.** Single-vector vs selective multi-vector storage/latency at ugm
   scale; cross-modal model + dimension choice (the hardest thing to change later — ties to questions.md
   #3); two-stage MaxSim query latency (no published LanceDB-at-scale number; M4 §2.4).
7. **Video cost arithmetic.** Shot-bounded selective captioning vs dense sampling on a representative
   corpus; the 1M-video-hour budget (deterministic pipeline <$50k one-time vs native ingestion millions
   per-query; M2 §2.2).
8. **Deletion cascade reaches media (couples to questions.md #24).** A hard-delete must now also prune
   P1 media vectors (Lance: compaction-with-prune, not a tombstone) and the persisted media artifacts
   (keyframes/page-images); crypto-shred reaches immutable backups/snapshots (M6 R3).

---

## 5. Proposed decisions and design-doc deltas

### 5.1 Proposed decisions (continue from D44)

- **D45 — The core multimodal choice: transcode-to-text on the E pipeline; native-media retrieval as a P1
  projection; no parallel multimodal evidence track.** Belief is text (claims/relations/observations) produced
  from grounded-text transcoding of media at E0; native-media segments/embeddings are a P-plane retrieval
  *entry channel* with zero authority (D6/D8/D9). Rationale: §1 — "describe media to text" is the same
  discipline as OCR (versioned `convert()`, D38) and E2 decontextualization (lossy rewrite quarantined by
  D32 grounding), not a new hazard; a second belief home would drift (D6).
- **D46 — Polymorphic grounding/locator.** Generalize D32's `source_span`/offsets and D38's `blocks[]`
  locator from `{char_start,char_end}` to a tagged union `text | image(page,bbox,coord_space) |
  av(t_start,t_end[,speaker][,keyframe,bbox])`. D32's four acceptance rungs map per §2.2. (Refines D32, D38.)
- **D47 — Modality-aware `convert()` as a READ-then-selective-DESCRIBE cascade (D4).** Job A
  (OCR/ASR/scene-detect) is deterministic verbatim source text routed through D32 as written; Job B (VLM
  caption) is a quarantined model-assertion entering as `added_context[]`, origin-stamped (D42), never a
  verbatim span. Every stage versioned + replayed-from-storage (D7/D33). (Refines D38.)
- **D48 — MediaIndex: the temporal/structural analogue of PageIndex (D39) for time-based media.** A
  scene/chapter tree with timecode spans + diarized transcript + per-scene captions + conversion manifest;
  linearized into the `document_markdown` E1/E2 consume, with dual char-offset + `media_locator` lines.
  (Sibling of D39; same versioning/replay discipline.)
- **D49 — P1 multimodal retrieval sub-index (two-tier, cheap-first).** Tier-A single-vector cross-modal
  (always-on) + Tier-B ColQwen/ColNomic multi-vector (selective, visually-rich only), in the Lance estate,
  `embedder_version`-stamped, rebuildable from persisted media artifacts. Holds no authority; never
  projects to P2. (Extends D8; obeys D6/D7/D9.)

(Media privacy — the versioned `redact` E0 sub-worker, the no-biometric-template invariant, and the
entity-keyed crypto-shred + Lance-prune deletion cascade — is real and pipeline-touching but belongs to the
privacy design-fit question; flagged here as a non-goal boundary (§3.1) and a delta (§5.2), not folded
into D45–D49.)

### 5.2 Design-doc deltas this implies

- **`decisions.md`** — add D45–D49.
- **`e0_files_design.md`** — `convert()` (§3) becomes modality-aware with image/audio/video routes; the
  `blocks[]` locator becomes the D46 tagged union; add a **MediaIndex** subsection (D48) beside PageIndex
  (§4); add persistence of media artifacts (page-images/keyframes/segment thumbs) for P1 + replay; add a
  `redact` sub-worker slot to the §1 chain (`ingest → convert → redact → structure → crossref`, cross-ref
  the privacy F-question); the §2 deletion cascade gains P1 media-vector prune + artifact hard-delete.
- **`e2_e3_claims_relations_design.md`** — §3.3 grounding: `source_span`/offsets → polymorphic locator;
  name `vlm_caption`/`scene_caption` as an `added_context[]` source class quarantined to D32 rung-3/4;
  note OCR/ASR text is first-class verbatim source. §5: a chart/spoken measurement → observation with
  bbox/timecode evidence provenance.
- **`observations_design.md`** — note the evidence provenance for an observation may be an image bbox or a
  video timecode (no schema change; the value stays in the NL `statement`, D43).
- **P1 search-index design (currently `planned`, questions.md #19)** — add the §2.5 two-tier multimodal
  sub-index as a first-class section.
- **`overall_design.md`** — plane diagram: media enters at E0; the E pipeline is unchanged; P1 gains a
  multimodal retrieval channel; reinforce D6 (beliefs text-only).
- **`questions.md`** — #24 (end-to-end delete) explicitly includes P1 media vectors + media artifacts;
  add the §4 multimodal spikes; #3 (embedding model/dim) now also covers the cross-modal embedder choice.

---

## Recommended architecture — summary

**Diagram:** §2.1 above. **Five bullets:**

1. **Transcode-to-text on the E pipeline (belief), native-media retrieval in P1 (recall) — a precise
   hybrid, stated as a split.** Pixels/audio become beliefs only through grounded-text transcoding; they
   are first-class *retrieval entries*, never first-class *evidence*. (D45)
2. **"Describe media to text" is the SAME discipline ugm already runs for OCR (versioned `convert()`,
   D38) and E2 decontextualization (lossy rewrite quarantined by D32 grounding) — not a new hazard.**
   Raw bytes immutable (D1/D37); model artifacts versioned + replayed-from-storage (D7/D33); DESCRIBE
   output grounded + origin-stamped (D32/D42). (D47)
3. **One schema change carries the whole thing: the grounding locator generalizes from char-offset to a
   tagged union (text | image page+bbox | av timecode+speaker), and D32's four acceptance rungs map onto
   it unchanged.** Auditability improves — claims ground to a chart region or a spoken timecode. (D46)
4. **One belief home holds (D6).** All beliefs are text claims/relations/observations in Postgres;
   evidence_count, dedup, and supersession work at the fact grain after transcoding; no second belief
   store. Visual recall is a Lance projection with zero authority (D8/D9). (D45/D49)
5. **Cheap-first throughout (D4):** deterministic READ (OCR/ASR/scene-detect) before selective DESCRIBE
   before frontier escalation; Tier-A single-vector before selective Tier-B multi-vector — spend scales
   with ambiguity and visual richness, not media volume. (D47/D48/D49)
