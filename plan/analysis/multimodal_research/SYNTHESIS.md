# Synthesis — processing video & images, and how it fits the memory system

Combines three **independent** analyses of the same brief (`question_brief.md`):

- **`claude_analysis.md`** — a 21-agent Claude research workflow (repo archaeology over
  docling / MinerU / ColPali / PySceneDetect / whisperX → six web-research threads → six ugm
  design-fit answers `design_fit/F1–F6` → three adversarial verification passes
  `verify/{numbers_facts,invariant_coherence,completeness}.md`) reconciled into one binding-quality
  spec. **This is the deepest document; read it for the full design and the D45–D56 decision text.**
- **`external_agents/codex_architecture.md`** — Codex (`gpt-5.5`) answering the eight design-fit
  questions against the repo. Independent verdict, proposed D45–D52.
- **`external_agents/codex_landscape.md`** — Codex (`gpt-5.5`) producing the 2026 model/tool/cost
  landscape (image VLMs, document parsers, visual retrieval, multimodal embeddings, ASR, video
  understanding, scene detection, OCR), with a cost-ordered pipeline.

Supporting evidence: `web_research/M1–M6` (landscape, cited), `repo_findings/*` (mechanism from the
five cloned repos under `_additional_context/`), `design_fit/F1–F6` (per-question ugm answers),
`verify/*` (fact-check + invariant + completeness critics).

All three tracks reached the **same core verdict independently.** The Claude workflow then went
materially deeper on five points the two Codex runs under-specified or missed (the three-class
provenance model, the offset-stability fix, the Lance storage correction, the CSAM/C2PA obligations,
the crypto-shred deletion story). This document records the consensus, the divergences and how they
reconcile, the recommended position, the honest verification status, and the spikes. Numbers are
starting points to measure (CLAUDE.md Rule 2), not committed constants.

---

## Consensus verdict

**Process media by transcoding it to a *grounded, versioned text rendering* at E0 so the existing
E1→E2→E3 belief pipeline runs essentially unchanged — but keep the native media (pixels, audio,
timecodes) as the *evidence anchor* and add an optional native-media *retrieval* projection in P1.
Belief is text; native media is provenance + retrieval; there is no parallel multimodal evidence
track.** This is a **strict hybrid**, and the load-bearing word is *evidence*: native media segments
and multimodal embeddings are accepted as a **retrieval entry channel with zero authority** and
rejected as a **belief home**. The asymmetry is the whole answer.

The key intellectual move — agreed by all three — is that **"describe media to text" is not a new
epistemic hazard.** It is the third instance of a discipline the pipeline already runs twice: OCR is
*already* a versioned, nondeterministic `convert()` output replayed-from-storage on rebuild
(D38/D33); E2 decontextualization is *already* a lossy, nondeterministic rewrite of source text
quarantined by grounding (D32). A VLM caption or an ASR transcript is the same shape of artifact over
immutable raw bytes (D1/D37), governed by the same apparatus. Pixels do not break the contract; they
extend it by **one locator type**.

The corollary all three insist on: **a generated description is never the grounding anchor.** A VLM
caption is a model-derived assertion *about* pixels, not a source span. So a media-derived claim
grounds to the **native locator** (the chart's pixel region, the spoken timecode), with the generated
text only a secondary anchor. Treating a caption as the media equivalent of `source_span` would
quietly destroy the auditability that makes D32 the strongest part of the system.

---

## The points all three analyses agree on

1. **One belief home holds (D6).** All beliefs — claims (D2), relations, observations (D43) — stay
   text in Postgres, produced from the transcoded text. `evidence_count`, dedup, and supersession work
   at the fact grain *after* transcoding: a chart-fact and a prose-fact of the same thing collapse to
   one observation/relation with N evidence rows, because both reach E2 as text. **No `VisualClaim` /
   `ImageFact` / `VideoRelation`.** A second, media-derived belief store would drift against the text
   store (the documented Mem0/Graphiti desync class) and make supersession ungovernable.

2. **The grounding locator generalizes from a char-offset to a polymorphic tagged union**
   `text(char_span) | image(page,bbox) | av(t_start,t_end[,speaker,keyframe])` (D32 → D47). The
   char-offset floor is *kept* (it is what keeps E1 chunking and E2 grounding modality-blind); the
   native locator is additive provenance. Verification gains a deterministic *locator-resolves*
   layer (the model cannot invent a region/frame/time that does not exist).

3. **`convert()` generalizes** from `{markdown, blocks[]}` to `{document_markdown, blocks[],
   structure, manifest}` (D38 → D46), and the **PageIndex gets a temporal sibling, the MediaIndex**:
   a `chapters → scenes → shots` tree for video (with timecode spans, roles, summaries), the
   structural backbone E1 chunks along and E2 reads — exactly the PageIndex role with time-based
   locators (D48). An image is the degenerate single-page document; a single standalone image gets a
   synthetic root.

4. **Cheap-first, with the expensive rung bounded by edits, not seconds (D4).** The media converter
   is a deterministic pipeline — demux → shot/scene detection (PySceneDetect, default `ContentDetector`
   threshold 27.0) → ASR + word-alignment + diarization (WhisperX/faster-whisper + pyannote) →
   perceptual-hash keyframe dedup → OCR — followed by **selective VLM captioning of one keyframe per
   shot/scene** (the only expensive, nondeterministic rung; budget = shot/scene count, *not*
   duration). Native whole-video frontier ingestion (Gemini-class) is an **escalation reasoner over
   bounded clips**, re-paid per query, never the substrate. This is **not** a value gate (D25):
   shot-dedup is *structural reduction* (the media analogue of content-hash idempotency); every scene
   still reaches E2; junk-control stays at in-call E2 Selection.

5. **P1 gains a multimodal retrieval projection, never a belief authority (D6/D8/D9).** Visual
   embeddings (page-images, keyframes, segments) live in the existing Lance estate, are rebuildable,
   carry no validity, never enter the P2 graph, and a visual hit returns a **locator** that hydrates
   to the already-extracted text claims. Zero LLM on the query path (D9). Reduce-to-text alone is
   *not* sufficient for a memory system — visual similarity, layout/figure retrieval, and "find the
   frame where the dashboard went red" are real capabilities — but they belong in a projection, not
   the E pipeline.

6. **Identity stays text-first (D20).** Entity resolution runs on names from OCR / transcript /
   metadata / mapped *relative* speaker labels through the T0–T4 cascade (D17). Visual content may
   *emit candidate name strings* (a logo → "Acme" caption into the OCR stream), never assign an
   `entity_id`. **No open-world face or voice recognition, no cross-media identity gallery** — that
   would import a biometric/external-authority system through the side door (GDPR Art. 9, EU AI Act,
   BIPA). A person on camera never named in any text is an acknowledged recall gap (the visual twin of
   cross-document coref, `#22`), remediable only by opt-in, consent-gated enrolment per deployment.

7. **Deletion is the hard part, and media is the forcing function.** A face/voice is biometric and a
   "forget this source/person" request must reach multi-GB cold blobs, derived transcripts, keyframes,
   embeddings, immutable snapshots, and backups. All three rank this the most under-built area
   (`questions.md #24`). The mechanism: **crypto-shred a per-document key** + Lance compaction-with-prune
   + a K input-manifest. Because ugm trains no model weights, it escapes machine-unlearning by
   construction (every derivative is a replay-from-storage projection, D7).

8. **The landscape position (both Codex landscape and the M-research agree):** never make a frontier
   VLM the default converter. Default to self-hostable deterministic parse/OCR/ASR (docling or MinerU
   for documents; PaddleOCR-VL/Surya for frames; WhisperX for audio) with layout/time provenance, and
   reserve VLM calls for routed exceptions (charts, figures, screenshots needing UI semantics,
   low-confidence OCR, representative keyframes). For video the cost driver is *frames inspected*, so
   ASR + shot-detection + keyframe-OCR is the backbone and native video models are escalation-only
   (verified: a 1-hour video at Gemini's 1 fps / ~300 tok/s ≈ ~$2.70/hr input — affordable per asset,
   ruinous as an unconditional million-video default).

---

## Divergences (and how they reconcile)

- **"Auditability improves" vs "auditability splits."** Codex-architecture and the F1 design-fit note
  framed media as *improving* auditability ("you can always draw the box"). The Claude invariant
  critic and F3 caught this as an **overclaim** and the synthesis adopts the honest account:
  auditability **splits in two**. *Provenance traceability improves* (a claim now grounds to a chart
  region or a spoken timecode). But *per-claim deterministic faithfulness is genuinely softened for
  model-described content*: a caption's anchor fixes provenance-to-the-caption, **not** truth-to-the-
  pixels. Faithfulness for descriptions moves to in-call entailment + an **offline sampled audit whose
  per-class rate is a first-class measured safety parameter**. This is the single most important
  nuance in the feature, and the synthesis states it plainly rather than selling media as a pure
  auditability win.

- **Two provenance classes (Codex) vs three (Claude).** Codex-architecture distinguished verbatim
  `transcription` from model `description` and gave each a different acceptance path — correct as far
  as it goes. The Claude completeness critic found the missing third class: **`uncertain_transcription`**
  (handwriting/HTR, degraded scans, low-confidence OCR/ASR). It is verbatim-in-its-own-output yet the
  *read itself* is a lossy guess, so it must **not** be allowed to confident-supersede a real value and
  is audited harder. Without it, a hallucinated OCR of a handwritten "$5M" would be anchored as
  verbatim fact and could overwrite a true one. **Adopt three classes** (D47), with supersession power
  `transcription > uncertain_transcription > description`.

- **The offset-stability risk (Claude only — the sharpest structural fix).** If VLM captions sat
  *inline* in the markdown that carries char offsets, a single caption re-run (on a `vlm_caption_version`
  bump) would shift the offsets of every later block and silently invalidate the `source_span` of
  unrelated, fully-deterministic transcription claims. Neither Codex run caught this. The fix (D46):
  **the offset pipeline is the deterministic transcription linearization only; descriptions are a
  block-ID side-channel**, addressed by stable `block_id` + native locator and entering E2 as named
  context — so a caption re-run never churns a transcription claim's anchor.

- **Tier-B visual-index storage (Claude correction, load-bearing).** The F-docs claimed late-interaction
  (ColPali-style) page vectors compress to "~5–6 KB/page, single-vector-comparable" in Lance. The
  invariant critic proved this **false for Lance**: that figure needs *binary quantization*, and
  **LanceDB multivector is cosine-only, float16/32/64 — no binary/Hamming** (verified at the LanceDB
  docs). With the Lance-available lever (token-pool factor 3 → −67% vectors @ 97.8% accuracy, fp16),
  it is **~86 KB/page ≈ ~20× a single vector** on the gated visually-rich slice. Accept ~20× on that
  gated slice (still one vector estate, D8); a Hamming-capable engine (Vespa/Qdrant) is a *documented
  alternative*, triggered only by a measured Tier-B latency/storage requirement — not a phase.

- **Decision numbering.** All six F-docs and Codex each independently numbered from `D45`, so `D45`
  meant *seven* different things across the corpus. The Claude synthesis mints **one reconciled,
  non-overlapping D45–D56 sequence** that supersedes every per-doc proposal and Codex's D45–D52. Use
  `claude_analysis.md §4` as the canonical decision text.

- **CSAM + C2PA (Claude only — two absent obligations).** Codex-architecture's privacy enum listed
  `child`/`id_document` but F6 dropped them. The completeness critic reinstated two obligations both
  Codex and the F-series under-covered: a PhotoDNA-style **illegal-content (CSAM) detection hook** with
  a stated 18 U.S.C. §2258A / NCMEC flag-quarantine-and-route posture (a strictly larger legal exposure
  than biometrics for a media-ingesting system), and **C2PA / Content-Credentials authenticity
  passthrough** as an evidence axis distinct from D42 self/external origin (standalone deepfake
  *detection* stays a non-goal; the manifest passthrough is nearly free).

On everything else — the core hybrid choice, the polymorphic locator, the cheap-first cascade, the
text-first identity rule, the P1 projection discipline, the deletion mechanism — the three tracks
**converged independently.**

---

## Recommended position (the reconciled design, in brief)

Full spec and schema in `claude_analysis.md §2`; decision text in §4. The shape:

1. **`convert()` returns `{document_markdown, blocks[], structure, manifest}`.** `document_markdown`
   is the deterministic linearization of the **transcription pipeline only** (OCR/ASR text in a stable
   total order); every block carries a mandatory `md_span` (char offset, the D32 floor) **plus** a
   polymorphic `native_locator`; descriptions hang off the structure tree by `block_id`, never spliced
   inline. Bbox normalized at the boundary to one 0–1000 top-left space (raw producer space kept in
   provenance); time as exact rational PTS, never a frame index.

2. **Image route:** image-class router (natural / screenshot / scan / chart / handwriting / low-quality)
   *before* OCR → always-on READ (layout + OCR + tables→HTML + formulas→LaTeX) → selective DESCRIBE
   (grounded prose for figure/chart regions; chart→table) → escalation tail. Spend scales with non-text
   regions and ambiguity, not pixel count.

3. **Video route (and long audio):** demux → shot detection → ASR+align+diarize → keyframe+pHash dedup
   → OCR → **detect/redact** → scene-merge → selective VLM caption (one keyframe/shot) → chapter
   roll-up → bounded-clip escalation. Long audio gets the same tree from acoustic/topic segmentation
   plus a sound-event/audio-caption DESCRIBE rung (the audio analogue of the VLM caption). The
   persisted `mediaindex.json` is the scene/chapter tree with a diarized word-timecoded transcript,
   per-scene OCR runs, and per-scene captions.

4. **Grounding (D32 → D47):** every claim keeps `claim_text` + `source_span` (char offsets, unchanged)
   + a `native_locator` (a *set*, via a locator child table, when a claim spans e.g. a transcript line
   and an on-screen OCR line). Acceptance gains an L0 *locator-resolves* layer; L1–L4 branch on the
   three provenance classes; "verbatim" is always w.r.t. the converted text, never the signal —
   signal fidelity (did OCR/ASR read correctly) is the separate, measured L4 axis.

5. **Belief layer unchanged (E2/E3/D41/D43).** The E2 bundle gains media-typed elements by `block_id`
   (transcript window, scene path + summary, scene caption, OCR block, neighbour segments, mapped
   speaker labels); the extractor is unchanged. A chart/spoken measurement → an **observation** (D43)
   with bbox/timecode evidence provenance, no schema change. Intra-document cross-track contradiction
   (OCR "600" vs caption "≈60" vs speaker "six hundred") resolves through the same D43 adjudicator with
   **provenance class as the confidence dial**. Capture time (EXIF/container clock) is an immutable,
   lower-precedence validity *seed* — `content-asserted date > capture time > ingestion time` — not a
   third clock (D53).

6. **P1 two-tier visual sub-index:** Tier A always-on single-vector unified-encoder cross-modal
   embedding (Cohere Embed v4 / Voyage multimodal / Jina-CLIP / SigLIP self-host; ~1–4 KB/unit,
   millisecond ANN); Tier B gated ColQwen/ColNomic multi-vector late-interaction (~20×/page) only for
   visually-rich units (tables/charts/figures/scans). The index embeds **redacted** keyframes, so
   image→image similarity is structurally not a face-matching gallery. Recipes (`visual_similarity`,
   `find_visual`, `find_frame`, `visual_maxsim_rerank`) are RRF candidate generators returning locators.

7. **Execution:** the media weight inside `convert` is a checkpointed sequence of independently-versioned
   stages; idempotency grain refined to `content_hash + stage + stage_version`; D33's replay-from-storage
   explicitly extended to E0 media stages; a multi-hour `convert` runs as a durable, stage-checkpointed
   job (not the fast-text 2-retry/dead-letter envelope) and resumes from the last checkpoint. Belief
   extraction proceeds over the stable transcription output the moment it is complete; descriptions enrich
   but never block.

8. **Privacy & deletion:** a versioned `detect/redact` stage makes the **redacted derivative canonical**;
   **never persist face/voice templates**; mounting/indexing is gated on a *measured redaction-recall
   floor* (a binding rule — "a missed face is an un-redacted face"); a CSAM hash-match hook with a
   §2258A/NCMEC posture; C2PA authenticity passthrough. Subject-level "forget" resolves to an
   `entity_id` (the registry is the deletion key) and crypto-shreds the per-document key + prunes Lance
   + reaches K via an input-manifest — closing `#24` for text too.

### The reconciled decision set (D45–D56)

One non-overlapping sequence; full text in `claude_analysis.md §4`:

| | Decision | Refines |
|---|---|---|
| **D45** | Core choice: transcode-to-text belief; native-media retrieval as a P1 projection; no parallel multimodal evidence track | D2/D3/D6/D43 |
| **D46** | `convert()` → `{document_markdown, blocks[], structure, manifest}`; offset pipeline = deterministic transcription, descriptions = block-ID side-channel | D38 |
| **D47** | Polymorphic grounding locator + three provenance classes (transcription / uncertain_transcription / description); the honest faithfulness split | D32, D41, D42, D44 |
| **D48** | MediaIndex: temporal/structural PageIndex analogue; `document_sections` becomes a polymorphic tree | D39 |
| **D49** | Fixed, per-stage-versioned cheap-first media cascade; checkpointed resumable long-running `convert`; no learned per-frame value gate | D38, D12/D36, D33, D4/D25 |
| **D50** | Modality routing matrix (image-class router; GIF/multi-frame/multi-page → video or page-set; long-audio segmentation; embedded child-media; diagram→structure limit; canonical-language policy) | D38/D46 |
| **D51** | P1 two-tier visual sub-index; embeds redacted pixels; ~20× Tier-B storage on the gated slice | D8/D9 |
| **D52** | Media facts use the unchanged E2/E3/D41/D43 belief layer over a polymorphic bundle; cross-track contradiction by provenance class; entity resolution text-mediated only | D31, D43, D42, D17 |
| **D53** | Capture time is an immutable, lower-precedence validity seed | D41 |
| **D54** | Media privacy: versioned detect/redact + biometric non-storage invariant + CSAM hook + C2PA passthrough; mounting gated on a redaction-recall floor | D36/D37 |
| **D55** | Subject-level deletion by crypto-shred + Lance prune, keyed on the entity registry; closes `#24`, folds O4 | D37 |
| **D56** | The one reconciled non-goals list (incl. 3D/spatial media, interactive content, standalone deepfake detection), each with an opt-in alternative | D2/D3/D6/D8/D20/D43/D44 |

Design-doc deltas (which files change and how) are itemized in `claude_analysis.md §5`: the largest
delta is `e0_files_design.md`; a new **`plan/designs/media_design.md`** owns the cross-cutting media
spec; `e2_e3_claims_relations_design.md`, `overall_design.md`, `postgres_schema_design.md`,
`requirements_v3.md`, and `questions.md` get targeted edits; `decisions.md` appends D45–D56 and
annotates D32/D38/D41/D42/D43/D12/D36/D33/D44 as refined-in-wording.

---

## Verification status (honest)

The three adversarial passes (`verify/*`) found **no fabricated claims** — the research is unusually
disciplined about tagging confidence. What is solid vs flagged:

- **Confirmed against primary sources:** Gemini video tokenization (1 fps, ~258 tok/frame, ~300 tok/s,
  1M-ctx ≈ 1 h default); ColPali nDCG@5 **81.3 vs 67.0** and ColQwen ViDoRe ~89–91; ColPali ~1,030
  vectors/page × 128-dim and the pool-3 → −67% @ 97.8% lever; WhisperX ~70× realtime + Czech alignment;
  PySceneDetect detector defaults; Mistral OCR pricing ($2/1k pages, $1 batch); Cohere Embed v4
  ($0.12/$0.47 per 1M text/image); Czech ASR ordering (Canary-1B-v2 7.86% < Whisper-large-v3 11.33%
  FLEURS WER); Anthropic/Gemini/Deepgram/AssemblyAI prices; LanceDB cosine-only multivector. All
  surveyed model names (Opus 4.8, Sonnet 4.6, Gemini 3.x, Qwen2.5-VL, Mistral OCR 3/4, Deepgram Nova-3,
  Parakeet-TDT-v3, Canary-1B-v2, pyannote community-1) are real and correctly versioned as of 2026-06-25.
- **Flagged / measure-before-committing (all already hedged in the docs):** GPT-5-family per-image
  pricing (unverified — no canonical figure); olmOCR self-host $/page and Mistral's "undercuts X%"
  (secondary/marketing — order-of-magnitude only); the exact Czech FLEURS decimals (trust the primary
  paper, not independently re-surfaced); the "$2.7M re-paid every query" framing (the *direction* —
  native = per-query, pipeline = pay-once — is verified and decisive; the specific number is a
  caching-unaware extrapolation, soften it); "grounded captioning −25–28% hallucination" (task-dependent;
  measure on ugm's own image mix).

The invariant critic's load-bearing corrections (auditability splits not improves; Tier-B is ~20× not
~5–6 KB in Lance; the D12/D36 long-running strain; the D33 replay-discipline extension being *new*) and
the completeness critic's additions (the third provenance class; the downstream E2/E3 cost; the
modality-routing gaps; CSAM/C2PA; the offset-coupling and visual-index-as-biometric risks) are **all
folded into `claude_analysis.md`** and the D45–D56 set.

---

## Open risks & what to prototype first (highest-leverage first)

Full list in `claude_analysis.md §6`. The gating spikes:

1. **Does grounding actually catch VLM-description hallucination on ugm's real image mix?** The whole
   "describe-to-text is safe" claim rests on bbox-anchor + OCR-window-membership + entailment rejecting
   bad captions, and on the description-class offline-audit sample rate being right. Measure on a golden
   image set; set the per-class rate. *Gates the honesty story (D47).*
2. **Does the dual-locator decoupling hold across re-conversion?** Verify the transcription linearization
   is byte-stable at pinned versions, descriptions live purely in the block-ID side-channel, and a
   caption/scene-boundary version bump re-runs only affected E2 calls without churning any transcription
   claim's `source_span`. *Gates D46/D49.*
3. **Is the three-class supersession rule correct and measurable?** Measure how often a numeric
   observation comes from clean OCR/ASR vs uncertain-transcription vs a model-read chart; confirm the
   adjudicator margin so neither an uncertain nor a description value can confident-supersede a clean
   one. Includes OCR/ASR WER/CER on the handwriting/degraded slice. *Gates D47/D52.*
4. **Lance multivector latency + the real Tier-B storage at scale** (the load-bearing P1 unknown — no
   published LanceDB-at-scale multivector number exists). Load Tier B for a realistic visually-rich
   slice (pool-3 + fp16, IVF_PQ), measure two-stage P95 vs the Tier-A baseline, confirm ~20× is
   acceptable. *Decision gate for Lance-vs-Hamming-engine (D51).*
5. **Redaction recall on adversarial media** (the real safety metric — "a missed face is an
   un-redacted face"). Measure detector recall on small/occluded faces, far-field/overlapping voices,
   on-screen secrets; set the mount-gating recall floor; validate the CSAM hash-match hook and C2PA
   passthrough end-to-end. *Gates the structural D54 claim.*
6. **Crypto-shred + Lance-prune at 1M-doc scale** (per-document DEK + KMS key count/rotation/latency;
   confirm destroying one key never harms another subject; the re-redact-and-re-derive path for shared
   documents). *Gates D55 / `#24`.*
7. **The downstream belief-extraction cost the cost tables never counted.** Media is a text-amplifier (a
   1-hour meeting → a massive transcript; a dashboard screen-recording → hundreds of value observations
   per minute), each running E2 Claimify + E3 + T0–T4 + D43 adjudication. The "<$50k once" framing
   prices only conversion. Measure the pipeline cost per media-class and the version-bump re-run cadence as
   first-order budget items. *Gates the cost model (`#2`).*
8. **ASR time-anchor + Czech + intra-document attribution** (WhisperX word-timecode precision and
   pyannote DER on real video with music/overlap/far-field; the Canary-1B-v2 Czech swap; the
   speaker→entity false-attribution rate that poisons "X said Y" claims; confirm Gemini is never the
   timecode source). *Gates D49/D52.*

---

## The one thing the author is most at risk of missing

All three tracks converge on it: **a generated description is not evidence — it is a derived artifact,
and the evidence is still the raw bytes plus an exact pixel/time locator.** If the design ever treats a
VLM caption as the media equivalent of `source_span`, it quietly destroys the auditability that makes
D32 the strongest part of the system. Get the **locator + three-provenance-class** model right and the
whole feature is "OCR, again" — a versioned converter over immutable bytes that the rebuild discipline
already knows how to handle. Get it wrong and you have a confident, well-cited hallucination machine.

Two close seconds, both genuinely new for a media-ingesting system and both initially under-covered:
**deletion** (media turns `#24` from bookkeeping into a privacy/biometric/CSAM blocker — crypto-shred is
the answer, and it happens to close the text case too) and **legal exposure** (CSAM reporting under
§2258A is a strictly larger obligation than the biometric concern the privacy analysis led with).
Identity is the trap to avoid: it is tempting to make media feel powerful by recognizing faces, voices,
logos, and products — that would import a biometric/external-authority oracle through the side door,
against D20 and the privacy posture. Let visual search *find* evidence; never let it *assert* identity.
