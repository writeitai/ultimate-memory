# F6 — Cost, Scale, Storage, Privacy, Deletion, Non-Goals (multimodal)

How images, audio, and **video** fit ugm's cost discipline (D4/D25), its GCS raw/artifacts split
(D37), and its deletion obligation (questions.md #24 / O4) — and where the system deliberately draws
a line (non-goals). This is the "what does it cost, where does it live, who is liable, how do we
forget" half of the multimodal extension; the "how do we convert/ground/retrieve" half is F1–F5
(M1–M5). Full-scope design; numbers are starting points to measure (CLAUDE.md Rule 2).

Companion research: `web_research/M2_video_understanding.md` (cost math), `M6_privacy_pii_deletion.md`
(legal + deletion), `M4_visual_retrieval_embeddings.md` (P1 storage), `repo_findings/*`.

---

## 1. Verdict / recommendation

**Video is the only thing here that threatens ugm's economics, and the fix is the cost discipline ugm
already has, applied to pixels.** A 1-hour video is thousands of frames; the only expensive,
non-deterministic operation is *pixels → VLM tokens*. Everything else (demux, shot/scene detection,
ASR, OCR, perceptual-hash dedup) is deterministic, CPU/GPU-cheap, and **paid once**. So the verdict is
a five-rung cheap-first media ladder whose expensive rung is **bounded by shot count, not duration**,
**persisted + versioned + replayed-from-storage** (D7/D33) so it is paid **once per video ever** — not
per query, not per rebuild. At 1M video-hours this is the difference between **~$2.7M re-paid every
query** (native whole-video frontier ingestion) and **tens of thousands of dollars once** (the
deterministic pipeline + selective captioning), after which the memory is plain text + structure that is
free to query forever.

Five decisive positions:

1. **Cost (D45).** Media `convert()` is a deterministic pipeline (`demux → shot/scene-detect → ASR →
   keyframe-dedup → OCR`) followed by **selective VLM captioning of one keyframe per shot/scene** — the
   only expensive step. Frontier native-video is an **escalation reasoner over bounded clips**, never
   the substrate. **No learned per-frame "is this worth captioning" gate** — that would be the video
   reincarnation of the rejected value gate (D25); shot-bounded sampling is *deterministic structural
   reduction* (like content-hash dedup is idempotency, not a value tier), and junk control stays in-call
   at **E2 Selection** over the linearized transcript+captions.
2. **Storage (D46).** Raw media (big, cold) goes to the **raw bucket on an Archive/Coldline storage
   class**, immutable, never mounted (D37). Derived transcript, keyframes, and the MediaIndex sidecar go
   to the **artifacts bucket** (standard, mounted). **Postgres still stores no bodies** — only metadata,
   the temporal MediaIndex/section index, privacy flags, and key IDs. Perceptual-hash keyframe collapse
   keeps artifact growth bounded by *distinct shots*, not frame count.
3. **Privacy (D47).** Faces, voices, and on-screen PII are a **genuinely new, first-class E0 concern**
   (the text pipeline never had pixels or audio). Add a **versioned `redact` sub-worker**; the *redacted*
   derivative is the canonical mounted/indexed artifact, the raw original is quarantined-and-shreddable.
   **Hard invariant: never persist face or speaker (voice) embeddings as durable matchable templates** —
   this is the single design choice that keeps ugm out of GDPR Art. 9 special-category, the EU AI Act's
   prohibited "untargeted biometric database," and BIPA's template hooks.
4. **Deletion (D48), closing #24/O4.** "Forget this source / this person" is resolved through the
   **entity registry** (D17) and executed by **crypto-shredding** (destroy a per-document key → every
   copy, *including immutable PITR backups, bucket-locked raw, GCS soft-delete, and aged P-snapshots*,
   becomes unrecoverable ciphertext) **+ Lance compaction-with-prune** (a tombstone `DELETE` is not
   erasure). ugm escapes the *worst* deletion problem — machine unlearning — for free, because every
   derivative is a replay-from-storage projection (D7), not trained weights.
5. **Non-goals (D49).** Live streams / real-time ingestion; biometric face/voice **recognition** or a
   cross-media identity gallery; emotion / sensitive-trait biometric categorization; and **cross-modal
   belief without text grounding** (no parallel "visual fact" store) are explicit scope boundaries with
   rationale — not future phases.

---

## 2. The design, concretely

### 2.1 The media cost cascade (D45) — `convert()` for `mime: video/* | audio/* | image/*`

Cheapest → most expensive, each rung gated by the previous. This generalizes D38's `convert(bytes,
mime, hints) -> {markdown, blocks[]}` to a media router; every rung is **versioned** and its output
**persisted as a durable artifact**, so rebuild (D7/D33) **replays from storage and never re-calls a
model**.

```
RUNG 0  demux / probe (ffmpeg)              deterministic, CPU            ~free
RUNG 1  shot/scene segmentation             PySceneDetect ContentDetector deterministic, CPU
        (TransNetV2 only on hard content)   → list[(shot_id,start_pts,end_pts)]
RUNG 2  ASR + word-timecodes + diarization  WhisperX (faster-whisper +    ~$0.005–0.05 / audio-hr
        → the primary semantic content      wav2vec2 + pyannote)          (self-host GPU)
RUNG 3  keyframe pick + near-dup collapse    1 frame/shot, perceptual-hash deterministic, CPU
        → distinct keyframes only            (a 5-min static slide → 1 keyframe, not 300)
RUNG 4  OCR on distinct keyframes           MinerU/Docling/dots.ocr        ~$0.0002/page self-host
        → on-screen text / slides / code     page+bbox blocks (D38 shape)
RUNG 5  SELECTIVE VLM caption               1 keyframe/shot, Qwen2.5-VL    THE expensive step;
        → per-shot visual description        /LLaVA-Video self-host         bounded by SHOT COUNT
                                             (Gemini Flash = hosted option)
─────── escalation (D4) ───────
RUNG 6  frontier native-video reasoning     Gemini, bounded to ONE scene's escalation only;
        (ambiguous / high-value scene only)  seconds (stays cheap)         spend ∝ ambiguity, not volume
ROLLUP  scene/chapter tree (PageIndex for    small text LLM over captions  cheap
        video) → linearized document.md      + OCR + diarized transcript
```

**What keeps it affordable at millions-of-docs scale** (the load-bearing properties):

- **Pay-once, replay-forever.** Rungs 0–5 run at ingest, are version-stamped, and their outputs are
  stored artifacts. On every P-rebuild and every query, ugm reads **text + structure** — the VLM is
  never re-invoked (D7/D33). Native whole-video ingestion (Gemini at ~$2.70/video-hour default-res, and
  the price *doubles* past 200k tokens ≈ 11 min of default-res video) is a **per-query** cost you re-pay
  forever; ugm refuses it as the substrate and reserves it for bounded-clip escalation (M2 §2.1).
- **The expensive rung is bounded by edits, not seconds.** Captioning *one keyframe per shot* means a
  1-hour talking-head call (10–40 shots) costs ~the same as a 5-minute one — and a 5-minute static
  screen-share collapses (Rung 3) to a handful of keyframes. Cost scales with *visual change*, the thing
  that actually carries information.
- **The deterministic pipeline dominates and is nearly free.** ASR is ~70× real-time and ~$0.005–0.05 /
  audio-hour; scene detection is HSV pixel-math on downscaled frames (PySceneDetect downscales to ~256px
  width before scoring); OCR runs only on *deduplicated* keyframes. M2's scale arithmetic: pipeline over 1M
  video-hours **< $50k once**, selective captioning **~$10k–$100k once** — vs **~$2.7M per query** for
  native frontier whole-video.

**Tie to D25 (no value gate; junk control in-call).** D25 rejected a pre-extraction salience/novelty
gate and made plane E `E0→E1→E2→E3` with full extraction; junk control lives in-call at **E2 Selection**
(proposition verifiability) + **D2** redundancy collapse. Media obeys this exactly. The thing we
**deliberately do not build** is the media-shaped value gate: a *learned* "which frames are worth
captioning" classifier (the per-frame analog of the rejected D26–D30 salience tier — same self-defeat:
a new fleet-scale model on the hot path for a modest lever). What we **do** build is *deterministic
structural reduction* — shot segmentation + perceptual-hash dedup — which is the media analog of D38
`convert` + D39 `structure`, not of a value gate. The linearized `document.md` (diarized transcript
interleaved with `[visual: …]` captions and `[on-screen: …]` OCR) then flows through E1→E2 unchanged,
and **E2 Selection drops boilerplate at proposition grain** just as it does for text (the dense-uniform
"caption every frame" path is a non-goal, §2.5 / D49 — a *simplification*, correct at any scale, not a
deferral).

### 2.2 Storage tiering (D46) — what lives where, and on which GCS class

The D37 rule is unchanged: **GCS holds bodies, Postgres holds the index, bodies are ID-addressed,
Postgres never stores body text.** Media only sharpens *which storage class* and adds a few metadata
columns + a key ID.

| Artifact | Store | GCS storage class | Notes |
|---|---|---|---|
| Raw video/audio/image bytes | raw bucket | **Archive / Coldline** (cold, immutable, strict IAM, **never mounted**) | big + rarely re-read (re-OCR/legal/audit only); D37 already says raw is cold — media makes the GB-per-file scale matter. **Encrypted under per-doc DEK (D48).** |
| Redacted transcript (`transcript.md`) | artifacts | Standard (mounted) | a body → **never Postgres** (D37). WhisperX word-timecodes + speaker labels. **Sensitive ⇒ encrypted (D48).** |
| Distinct keyframes (`keyframes/*.jpg`) | artifacts | Standard (mounted) | content-addressed (md5 of pixels, MinerU pattern); count bounded by Rung 3 dedup. **Redacted; sensitive ⇒ encrypted (D48).** |
| `mediaindex.json` (scene/chapter tree) | artifacts | Standard (mounted) | the "PageIndex sidecar for video" (M2 §4.2); replayable. |
| Visual / segment embeddings | LanceDB (P1) | — | Tier-A single-vector ~1–4 KB/unit (always-on); Tier-B ColPali pooled ~5–6 KB/page (gated, M4). Derived, no authority. |
| Document/media metadata + temporal section index + **privacy flags** + **key IDs** | **Postgres** | — | the only PG growth; see schema below. |

**Postgres schema deltas (compact metadata only — D37):**

```
documents( … existing … ,
  media_kind,                       -- video | audio | image | document
  duration_s, fps, container, codecs, has_audio,
  redactor_name, redactor_version,  -- redaction provenance (like converter_version, D38)
  asr_version, scene_detect_version, vlm_caption_version, ocr_version,  -- per-rung versions (D7/D33)
  has_faces, has_onscreen_pii, has_third_party_audio,                   -- D47 detect-and-flag
  pii_flag_version,
  dek_id, dek_status )              -- D48 crypto-shred: key handle + {active|shredded}

-- document_sections (D39) gains TEMPORAL locators for media (polymorphic with char/bbox):
document_sections( … existing (node_path,title,role,char_start,char_end) … ,
  t_start_pts, t_end_pts,           -- exact rational PTS (PySceneDetect FrameTimecode model)
  keyframe_uri, speaker_label )     -- relative diarization label (SPEAKER_00), NOT an identity
```

The transcript and keyframes are **bodies/artifacts**, so they live in GCS and are reachable from the
mounted corpus filesystem (P3); Postgres carries only the queryable temporal index + provenance + flags.
This is D37 verbatim, extended with timecodes and privacy flags.

### 2.3 Privacy as a first-class E0 concern (D47)

**Is this new? Yes.** The text pipeline already handles *names* (OCR/ASR text → entity registry). What
is new and first-class is **biometric signal in pixels/audio** (faces, voiceprints) and **PII printed in
the frame** (passwords, IDs, license plates). The legal stakes (M6 §2.1, all [V]): GDPR Art. 4(14)
makes a face/voice "biometric data," but Art. 9 *special-category* status (near-banned, needs explicit
consent) attaches **only when processing is "for the purpose of uniquely identifying a natural person"**;
the EU AI Act (prohibitions live since Feb 2025) **bans** building face-recognition databases by
untargeted scraping and sensitive-trait biometric categorization; **BIPA** (Illinois) carries a private
right of action at **$1,000 / $5,000 per violation** and gates *voiceprints* and *face-geometry scans*,
including shipping them to a cloud API (a regulated §15(d) disclosure).

Two structural moves put ugm on the safe side of all three:

**(a) A versioned `redact` sub-worker in the E0 chain (extends D36).**
```
ingest ─► convert ─► REDACT ─► structure ─► crossref
                     (faces blur via deface/CenterFace;
                      on-screen PII via Presidio image redactor;
                      audio: transcribe then Presidio over transcript text)
```
The **redacted** Markdown / keyframes / transcript become the **artifacts** that get mounted (P3),
chunked (E1), claimed (E2), embedded (P1). The **raw original** stays in the raw bucket — D37 already
makes it *immutable, strict-IAM, never mounted*. So **"any agent or projection can only ever see
redacted media" becomes a structural property of D37**, not a runtime hope. `redactor_name/version` is
stamped like `converter_version`; a better redactor re-redacts by version and rebuilds downstream
(D7) — over-redactions are fixable from the (retained, shreddable) raw, un-redactions are recoverable.
Self-hosted redactors (deface, Presidio, whisperX, PySceneDetect — all OSS, all already in ugm's
research base) are the **default**, because local processing avoids a BIPA §15(d) disclosure and a GDPR
Art. 28 processor relationship; cloud redaction (Rekognition/DLP) is an opt-in-per-deployment choice for
throughput, with a DPA — a documented alternative, not the default.

**(b) Biometric non-storage as a hard invariant.** **Never persist face embeddings or pyannote speaker
embeddings as durable, matchable templates.** Diarization needs speaker vectors only *transiently*, to
cluster speakers *within one file*; the durable output is a transcript with **relative** labels
(`SPEAKER_00`), never a cross-file identity. (WhisperX bolts `speaker_embeddings` onto its result only
when explicitly asked — ugm never asks for durable persistence; the vector is compute-scoped.) This one
rule keeps ugm out of "processing for unique identification" (Art. 9), out of "building a face database"
(AI Act prohibition), and off BIPA's template collection/retention/disclosure hooks. Media-privacy
facts are recorded as **flags, not biometrics** (`has_faces`, `has_onscreen_pii`,
`has_third_party_audio`, `redaction_version`), detected cheap-first (D4) at ingest, and **consulted by
mounting (P3), P1 indexing, and retrieval** to gate exposure (e.g. quarantine a document with
`has_onscreen_pii AND redaction_version IS NULL`).

### 2.4 The deletion cascade (D48) — closing #24 / O4

**The unit of "forget" becomes a person, not only a document, and the index that finds everything is the
entity registry ugm already has.**

```
ERASURE REQUEST ("forget source X" | "forget person P")
   │
   ▼  resolve to entity_id via registry (D17 mentions)        ── the DELETION KEY
   ├─► Postgres rows:  documents · document_sections · chunks(E1) · claims(E2)
   │                    · relations + relation_evidence(E3)
   │                    · observations + observation_evidence + adjudications (D43)
   ├─► GCS blobs:      raw bytes + every derived artifact (transcript, keyframes, mediaindex,
   │                    redaction sidecars) of each implicated document
   ├─► P1 / Lance:     vectors for the doc's chunks/claims/observations/keyframes/segments
   ├─► P2 / P3 / K:    projections — self-heal on next rebuild (Postgres no longer has the rows)
   └─► IMMUTABLE COPIES: PITR backups, GCS soft-delete (7-day floor), bucket-locked raw, aged P-snapshots
```

The hard truth (M6 §2.3, all [V]): **a row/object delete is not erasure.** GCS soft-delete has a 7-day
floor and cannot be purged early; bucket-lock/retention create deliberately immutable windows (and the
raw bucket *wants* long retention for audit/legal); Postgres PITR retains deleted rows for the backup
window; old immutable P-snapshots still contain the data until they age out. Two mechanisms resolve
this:

- **Crypto-shredding (crypto-erasure) — the mechanism that reaches immutable storage.** Encrypt the raw
  bytes and every *sensitive* derivative artifact under a **per-document Data Encryption Key (DEK)**; to
  erase, **destroy the DEK**. Every copy — including PITR backups, bucket-locked raw, soft-deleted
  objects, and aged snapshots — instantly becomes **unrecoverable ciphertext**, with no row rewrite and
  no waiting out retention windows. The **entity registry is the index** (subject → mentions →
  documents → DEKs); the **DEK is the shred unit**. For a **document the subject solely owns**, destroy
  its DEK (full crypto-shred). For a **shared document that must survive** with one subject removed,
  **re-redact that subject and re-derive** (replay-from-storage with the subject masked) rather than
  shredding the whole document — the redact sub-worker (D47) is exactly the tool, and per-subject
  sub-keying of subject-specific derivative artifacts is the documented escalation if even the shared
  raw must be partitioned.
- **Lance prune, not just tombstone.** Lance `DELETE` writes a *deletion file* (soft tombstone) to avoid
  rewriting fragments/rebuilding ANN indices; the vector is physically gone only after **compaction with
  `OptimizeActions::Prune`**. A GDPR hard-delete therefore **triggers prune**, wired into the deletion
  worker — otherwise the embedding survives in fragments.

**P2/P3** need no special action (drop the Postgres rows → the next rebuild omits them), but for
*immediate* effect their snapshot retention is **bounded** (aged out) or their **snapshot keys
crypto-shredded**. **K** (compiled git markdown, the unreproducible source of truth) gets the **O4
input-manifest** (claim/relation/observation IDs per compiled file) so the tombstone reaches exactly the
files referencing the erased subject, which are then recompiled or key-shredded.

**Why ugm escapes the worst deletion problem — state it as an advantage.** Once personal data is baked
into *trained model weights*, removal is "nearly infeasible without costly retraining," and approximate
machine-unlearning suffers "superficial forgetting." ugm **trains no models**: every derivative
(transcript, keyframes, captions, embeddings, claims, relations, observations, snapshots) is a
**versioned, replay-from-storage projection** (D7). Deleting them is an ordinary drop/re-derive, never
weight-scrubbing. The deletion cascade is *tractable precisely because of D7* — and crypto-shredding +
prune are the two additions that make it reach the immutable tail.

> **Note:** crypto-shredding is the general answer to #24 — it works for text-only documents too. Media
> is the *forcing function* (multi-GB cold blobs + biometric liability make plain object-delete
> visibly insufficient), but D48's mechanism (per-document DEK, entity-registry deletion key, Lance
> prune, bounded/keyed snapshots, O4 K-manifest) is the end-to-end cascade the whole system was missing.

### 2.5 Explicit non-goals (D49) — scope boundaries with rationale

Stated as non-goals (CLAUDE.md Rule 2), not phases:

- **Live streams / real-time / online ingestion.** ugm is a batch, replay-from-storage memory whose
  ground truth is *immutable raw bytes* (D1/D7). A live stream has no durable raw to replay until it is
  captured, and "freshness in seconds" contradicts the rebuild-cadence model (D7). Streaming capture is
  an upstream concern; ugm ingests the *recording*. Documented alternative: a per-deployment capture
  shim that lands finished segments as ordinary E0 inputs.
- **Biometric face/voice recognition or a cross-media identity gallery.** Prohibited-by-design:
  building face/voiceprint galleries and matching them is the Art. 9 special-category trigger, the EU AI
  Act's banned "untargeted database," and BIPA's sharpest edge. ugm **detects-and-redacts, never
  recognizes** (D47). Speaker→real-person linking, if a deployment genuinely needs it, is **opt-in with
  explicit consent + a written retention/destruction schedule** — a documented per-deployment
  alternative, never a default.
- **Emotion recognition / sensitive-trait biometric categorization.** EU AI Act prohibited (workplace/
  education emotion recognition; inferring race/politics/religion/sexual-orientation from biometrics).
  Not built.
- **Cross-modal belief without text grounding (no parallel "visual fact" store).** Visual evidence
  produces the *same* claims/relations/observations through the text pipeline; it gets no second belief
  system (that would violate D2/D3/D6/D43 — two homes for belief that drift). Visual retrieval (P1
  Tier-A single-vector + gated Tier-B ColPali, M4) **ranks and locates a page/timecode**; it **never
  asserts a claim**. ColPali-style indices carry no offsets/identity (repo_findings/colpali §4) and stay
  P1-only, never on the P2 graph (D8/D44).
- **Native whole-video frontier ingestion as the default substrate**, and **dense/uniform per-frame
  captioning.** Both are non-goals: native ingestion is an escalation reasoner over bounded clips (cost
  re-paid per query otherwise); frame-exhaustive captioning is strictly dominated by shot-bounded
  selective captioning on both cost and quality (adaptive keyframe selection reports +8–10 points at
  small frame budgets, M2 §2.1). Deleting dense sampling is a **simplification** (correct at any scale),
  not a deferral.

---

## 3. How it preserves ugm invariants

- **D1 / D7 / D33 — immutable raw, replay-from-storage, versioned model steps.** Raw media is immutable
  ground truth; every non-deterministic rung (ASR, scene-detect, OCR, VLM caption, redaction) is
  version-stamped and persisted, replayed on rebuild, never re-invoked. This is what makes the VLM a
  pay-once cost and makes deletion a drop/re-derive (not unlearning).
- **D4 / D25 — cheap-first cascade, no value gate, junk control in-call.** The media ladder is a literal
  cost cascade; the VLM rung escalates by ambiguity/value (D4). No pre-extraction or per-frame value
  gate is built (D25); deterministic shot-dedup bounds the budget, and E2 Selection handles junk over
  the linearized text.
- **D37 — storage split, Postgres holds no bodies.** Transcript/keyframes/mediaindex are
  bodies/artifacts in GCS; Postgres gains only compact metadata, the temporal section index, privacy
  flags, and key IDs. The redacted-derivative-is-canonical rule turns "agents only see redacted media"
  into a property of the existing raw/never-mounted split.
- **D6 / D8 / D44 — one belief home, vectors in Lance not the graph.** Media-derived facts flow through
  claims → relations/observations like any evidence; validity stays relation-only (D3) / observation
  (D43). Visual embeddings are P1/Lance projections with no authority; nothing media-derived enters the
  P2 graph (a value/keyframe is not a node, D18/D44).
- **D17 / D43 — entity registry as join, observations for chart/measurement values.** The registry is
  reused as the **deletion key** (subject → everything). A figure read off a chart/slide ("FY2023
  revenue $5M") becomes an **observation** (D43) anchored to the entity, timecode/bbox as evidence
  provenance — no new belief machinery.
- **D42 — origin stamping.** Re-ingested self-generated media (an agent's own recorded output) is
  stamped `self`, so its captions/transcripts don't inflate `evidence_count` as independent
  corroboration.

---

## 4. Risks / what to measure (spikes)

1. **Redaction recall is the real safety metric — a missed face is an un-redacted face.** Measure
   CenterFace/deface + Presidio recall on a ugm golden set of *adversarial* media (small/occluded faces,
   far-field/overlapping voices, on-screen secrets). Gate mounting on a measured recall floor, not on
   "redactor ran."
2. **Crypto-shred envelope vs. multi-subject blobs.** Validate per-document DEK + KMS at 1M-doc scale
   (key count, rotation, KMS latency/cost on the deletion path) and the re-redact-and-re-derive path for
   shared documents. Confirm destroying one DEK never harms another subject's data (per-subject
   isolation).
3. **Lance prune cost on the deletion path.** Measure compaction-with-prune latency/throughput when a
   GDPR delete must physically remove vectors from large multimodal tables; confirm tombstone→prune
   wiring actually erases.
4. **Snapshot retention window N for immediate erasure.** Pick N (P1/P2/P3 snapshot age-out) vs. the
   alternative of crypto-shredding snapshot keys; measure the freshness-vs-erasure-latency tradeoff.
5. **Shot-count distribution drives the VLM bill.** Real shot counts vary 10×–100× by content type
   (talking-head vs. action vs. screen-share). Measure shots/hour on the real corpus mix to size the
   captioning budget (and validate that perceptual-hash dedup collapses static screen content as
   expected).
6. **Storage-class economics for raw media.** Measure Archive/Coldline retrieval cost + latency for the
   audited re-OCR/legal-access path (cold raw is cheap to store, not free to read).
7. **O4 K input-manifest.** Confirm every compiled K file carries claim/relation/observation IDs so the
   deletion tombstone reaches it; without O4, K is the one place a forgotten subject can survive.

---

## 5. Proposed decisions (D45–D49) and design-doc deltas

**D45 — Media `convert()` is a cheap-first deterministic pipeline + selective VLM; native frontier video is
escalation-only.** The five-rung ladder (§2.1), VLM bounded by shot count, versioned + replayed-from-
storage (D7/D33), no learned per-frame value gate (D25), junk control in-call at E2 Selection. *Delta:*
extend `e0_files_design.md` §3 (D38 router) with media routes + the MediaIndex; cross-ref M2.

**D46 — Media storage tiering on the D37 split.** Raw media → raw bucket on Archive/Coldline (cold,
immutable, never mounted); transcript/keyframes/mediaindex → artifacts bucket (standard, mounted);
Postgres gains `media_kind/duration/fps/...`, per-rung version columns, privacy flags, and `dek_id`;
`document_sections` gains temporal locators (`t_start_pts/t_end_pts`, `keyframe_uri`, `speaker_label`).
*Delta:* `e0_files_design.md` §2 storage table + the `documents`/`document_sections` schema;
`postgres_schema_design.md`.

**D47 — Media privacy is a first-class E0 concern: versioned `redact` sub-worker + biometric
non-storage invariant + detect-and-flag.** Redacted derivative is canonical/mounted/indexed; raw is
quarantined-and-shreddable; never persist face/voice templates; self-hosted redactors default, cloud
opt-in with DPA. *Delta:* add the `redact` stage to the E0 chain in `e0_files_design.md` §1/§3;
new privacy section; flags consumed by P1/P3/retrieval.

**D48 — Subject-level deletion cascade by crypto-shredding + Lance prune, keyed on the entity registry
(closes #24 / O4).** Per-document DEK (destroy → reaches PITR backups, bucket-locked raw, GCS
soft-delete, aged snapshots); entity registry (D17) as deletion key; Lance compaction-with-prune;
bounded/keyed P-snapshot retention; O4 K input-manifest; re-redact-and-re-derive for shared documents.
ugm avoids machine-unlearning by construction (D7). *Delta:* rewrite the deletion paragraph in
`e0_files_design.md` §2 from document-level to subject-level; resolve questions.md #24 and fold O4;
new "Deletion & erasure" section in `overall_design.md` §8.

**D49 — Multimodal non-goals.** Live streams/real-time; biometric face/voice recognition + cross-media
identity gallery; emotion / sensitive-trait categorization; cross-modal belief without text grounding
(no parallel visual fact store); native whole-video-as-substrate and dense per-frame captioning. All
documented as scope boundaries with rationale, with opt-in-per-deployment alternatives where genuine.
*Delta:* non-goals subsection in the multimodal design doc; cross-ref D2/D3/D6/D8/D43/D44.

**questions.md updates:** mark **#24** resolved-by-D48 (crypto-shred + prune + registry key + O4
manifest); mark **O4 / #13** folded into D48 (K input-manifest is now load-bearing for deletion);
add the §4 spikes (redaction recall, KMS at scale, Lance prune cost, snapshot window N, shot-count
sizing, cold-read economics).
