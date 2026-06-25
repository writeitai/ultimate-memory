# Completeness verdict — multimodal feature planning

**Role.** Adversarial completeness critic over `web_research/M1–M6`, `repo_findings/*`,
`design_fit/F1–F6`, and `external_agents/{codex_architecture,codex_landscape}`. Default stance:
skeptical. A claim is "confirmed" only with a traceable source. I distinguish **[V]** verified from a
cited source, **[I]** inference/engineering judgment, **[?]** could not verify.

**Bottom line.** The corpus is strong on the *pipeline-fit* argument (transcode-to-text belief + P1
visual projection, polymorphic locator, cheap-first cascade, deletion-by-crypto-shred) and the work is
internally consistent across six independent F-docs. But it is a **video-and-document-figure design
wearing a "multimodal" label.** Whole classes of input the brief names are unrouted; several failure
modes that the design's own framing creates are unexamined; the cost model omits the largest new cost;
and there are two legal/safety obligations (illegal-content reporting, content authenticity) that are
absent entirely. Most seriously, the six F-docs each mint their **own conflicting D45+ numbering** — the
synthesis cannot ship until that is reconciled.

---

## What IS adequately covered (so I don't relitigate it)

- Core choice (transcode-to-text belief; native-media as P1 retrieval projection, never a belief
  home) — F1, codex_architecture; well-grounded in D2/D3/D6/D8/D9/D43/D44. **[V against the design docs]**
- The polymorphic grounding locator (`text | image(page,bbox) | av(t_start,t_end,speaker)`) and the
  transcription-vs-description provenance split — F2/F3/F5, M5 STEAL-1/3. Genuinely good.
- The cheap-first video cascade (demux → shot-detect → ASR → keyframe-dedup → OCR → selective VLM
  caption → roll-up), shot-bounded caption budget, native-video-as-escalation-only — M2/F2/F6. Solid
  cost reasoning. **[V for the unit primitives; I for the 1M-hour extrapolations, correctly flagged]**
- ASR/diarization stack (WhisperX + pyannote + NeMo swap; Gemini-not-a-timecode-source) — M3.
- Biometric-template non-storage as the GDPR Art. 9 / EU-AI-Act / BIPA lever; crypto-shred + Lance
  prune deletion cascade — M6/F6. The strongest privacy reasoning in the set.

---

## missing-cases[] — modalities / inputs the brief named that the design under-routes

1. **Animated GIFs (and other multi-frame image containers): unrouted.** [V — absent from all docs]
   The pipeline routes by MIME. `image/gif`, multi-frame WebP/APNG, and **multi-page TIFF** (fax/scan
   bundles) are image-shaped but temporally or multi-page structured. F2 §2.2 explicitly models a
   single image as "the degenerate single-page case … a synthetic root page" — which silently discards
   animation and collapses a multi-page TIFF to one page. A GIF reaction, an animated chart, or a
   30-page scanned TIFF contract would lose all but one frame. Decision needed: route `image/gif` and
   multi-frame/multi-page containers through the **video** cascade (shot/frame-dedup) or a **page-set**
   enumerator, not the single-image route.

2. **Audio-only files with non-speech content: no DESCRIBE path exists.** [V — M3/F2 cover only ASR]
   Podcasts and voice memos are handled (ASR). But the design's whole "READ vs DESCRIBE" symmetry
   (F1 §1.1) has **no audio analogue of the VLM DESCRIBE rung**: a music track, a concert recording, an
   environmental/voice-memo with humming, a sound effect, or *non-speech segments inside a video*
   produce empty ASR and therefore **no evidence at all**. There is no audio-captioning / sound-event
   description tier. Either state audio-scene understanding as an explicit non-goal (with rationale) or
   add it; today it is an unstated silent gap. Also: a 3-hour **podcast has no MediaIndex** — the
   scene/chapter tree (D48-analogue) is defined for *video* via PySceneDetect; pure audio has no shot
   detector, so a long podcast linearizes to one flat transcript with no chapter structure for E2 to
   read (the F5 "scene_path" bundle element is null). Topic/chapter segmentation for long audio is
   undesigned.

3. **Scanned handwriting / degraded scans break the "transcription = faithful by construction"
   premise.** [V — premise stated in F1 §1.1, F3 §2.3; HTR reliability not addressed]
   F1 §1.1 and F3's provenance-class binary assert OCR output **is** verbatim source text that "satisfies
   D32 anchor + window-membership *as written*" and (F5 §2.3) "may **confident-supersede**" a prior
   belief. That is safe for clean print; it is false for **handwriting (HTR), degraded scans, and
   low-confidence OCR**, where the transcription is itself a lossy, uncertain guess — epistemically much
   closer to a DESCRIPTION than to a quote. The binary `transcription | description` has **no
   low-confidence/uncertain-transcription class**, so a hallucinated OCR reading of a handwritten "$5M"
   would be anchored as verbatim fact and allowed to supersede. M1 itself flags MinerU's "no
   hallucination" as a vendor claim "must be measured" — the design banks on it. Needs a confidence
   axis on transcription (and a rule that low-confidence transcription cannot confident-supersede).

4. **Non-English on-screen/spoken text: no canonical-language policy.** [V — Czech ASR covered; pipeline
   language undecided] M3 handles Czech ASR and MinerU does 109-lang OCR, but nowhere is it decided
   **which language `document.md` is in** — source language, or normalized-to-English. This is
   load-bearing downstream: E2 claim extraction, T0–T4 entity resolution (D17), and cross-document
   `evidence_count` dedup (D2) all depend on it. Two videos asserting the same fact in English and Czech
   will **not** collapse to one observation with `evidence_count=2` (F1 §2.6's promise) unless a
   normalization/translation step is specified. RTL scripts and the verbatim-substring window-membership
   check under Unicode normalization are also unexamined.

5. **Embedded *video/audio* inside container documents: only embedded *images* are handled.** [V — the
   brief names "embedded video in docs"; docs cover only PDF figures] Docling `PictureItem` handles
   figures-in-PDF. But a `<video>` on a web page, a video embedded in a PPTX, or an audio attachment in
   an email has **no recursive child-media extraction / crossref** story. How an embedded clip becomes
   its own `media_id` nested under the parent doc's locator tree is undesigned (D36 crossref is mentioned
   but not exercised for embedded time-based media).

6. **Diagrams / schematics (graph-structured figures) collapse to lossy prose.** [I] Charts get
   `chart→table` extraction (M1); **flowcharts, org charts, circuit/architecture/network diagrams, ER
   diagrams** have node/edge structure that a flat VLM caption destroys, yet they often carry the
   document's most extractable relations. Treated implicitly as "just a figure caption." At minimum flag
   diagram→structure as a known recall limitation.

7. **Screenshot vs photo vs scan routing exists in research, dropped from the synthesis.** [V]
   codex_landscape §9 step 2 prescribes an image-class router (natural / screenshot / scan / chart /
   handwriting / low-quality). The F-series replaced this with "route on the OCR pass's block category,"
   which presumes you already ran OCR — wasteful on a vacation photo and unhelpful for the
   handwriting/low-quality classes that need *different* handling, not just a category tag.

---

## gaps[] — failure modes, cost blind spots, privacy/legal holes, missing non-goals

### Cost blind spots

8. **The biggest new cost — downstream E2/E3 over media-derived text — is uncounted.** [V — every cost
   table (M2 §2.2, F6 §2.1, codex_landscape §"cost-ordered") prices only conversion (ASR/OCR/VLM
   caption); none price the pipeline.] Media is a **text-amplifier**: a 1-hour meeting yields a massive
   transcript; F5 §spike-7 itself concedes a dashboard screen-recording emits "hundreds of value
   observations per minute." Every one of those runs **E2 Claimify (LLM), E3 normalization, T0–T4 entity
   resolution, and D43 observation adjudication** — the real per-document LLM bill, and it scales with
   media verbosity, not with the (cheap) conversion. The "<$50k once" framing (M2) covers only
   conversion and is misleading about total cost. The cost model must add the belief-extraction tier.

9. **Re-conversion / re-embedding amortization is ignored.** [I] D7 rebuild-first means a
   `vlm_caption_version` / `asr_version` / `embedder_version` bump **re-runs the expensive rung over the
   entire media corpus** — the "paid once" becomes "paid once per version bump." For millions of
   video-hours and a fast-moving model landscape (M1/M4 both stress checkpoints turn over monthly), bump
   cadence is a first-order budget item with no policy.

10. **Keyframe/page-image artifact storage at scale is unsized.** [V — F6 §2.2 sizes raw (Coldline) and
    embeddings (Lance), but keyframe JPEGs must live in the *Standard/mounted* artifacts bucket as the
    D7 rebuild source for P1 (F4 §2.1, §3).] Millions of videos × dozens of redacted keyframe crops ×
    page-image rasters is a large, hot (Standard-class) cost that no table accounts for.

### Failure modes the design's own structure creates

11. **OCR/ASR hallucination is treated as a measurement caveat, not a design hazard — despite the design
    granting transcription supersession authority.** [V] F3 §1.4 honestly notes "verbatim is w.r.t. the
    converted text, not the pixels," and spike #4 says measure WER. But the *design* still routes all OCR
    as trusted transcription that "may confident-supersede" (F5 §2.3). A hallucinated OCR token is
    verbatim-in-its-own-output and passes every deterministic rung — the anchor guarantee is **hollow for
    exactly the inputs (handwriting, degraded scans, stylized on-screen text) where OCR fails most.** The
    severity is mismatched to the treatment.

12. **Intra-document cross-track contradiction is unhandled.** [I] One video frame: OCR reads "600", the
    VLM caption says "≈60", the speaker says "six hundred." These are three evidence rows at one locator
    that **conflict inside a single document**. `evidence_count`/dedup (D2) and the D43 adjudicator are
    framed for cross-document agreement; intra-document multi-track disagreement (and which track wins)
    is unspecified.

13. **Partial / failed conversion has no defined semantics.** [I] The cascade is a 10-stage sequential
    pipeline (F2 §2.3). If ASR succeeds but the VLM-caption stage crashes or times out (or a video is
    truncated/corrupt), is the document partially ingested, retried, or quarantined? Per-stage
    idempotency (D12) helps re-entry but says nothing about **partial-evidence belief extraction** — do
    claims from the ASR-only linearization get committed before captions exist, then shift offsets when
    captions arrive? (Couples to risk 17.)

### Privacy / legal holes

14. **Illegal-content (CSAM) detection + mandatory reporting is entirely absent.** [V] A memory system
    that ingests arbitrary user images/video can obtain "actual knowledge" of apparent CSAM, which
    triggers a **federal duty to report to NCMEC's CyberTipline under 18 U.S.C. § 2258A**, with
    knowing-failure penalties up to **$150,000 (first) / $300,000 (subsequent)**; PhotoDNA-style hash
    matching is the standard mechanism, and uploading/backing-up alone is a triggering event.
    (congress.gov LSB10713; 18 U.S.C. § 2258A.) M6/F6 cover GDPR/BIPA/AI-Act biometrics thoroughly but
    are **silent on illegal-content obligations** — a strictly larger legal exposure than biometrics for
    a media-ingesting system. codex_architecture's `media_privacy_findings.finding_type` enum even lists
    `child` and `id_document`, but F6 dropped it. This must be at least a stated obligation + a hook in
    the redact/detect sub-worker (and a non-goal boundary if scanning is deliberately deferred to the
    capture layer — but then say so).

15. **Content authenticity / synthetic-media provenance is unaddressed.** [V] The system treats ingested
    media as **evidence** and grounds remembered claims to it, but never asks whether the bytes are
    authentic. **C2PA / Content Credentials** is now a real, adopted standard (spec v2.2, May 2025;
    Samsung Galaxy S25 native camera signing; OpenAI signs generated media; Sony Camera Verify for
    press) — i.e., authenticity manifests are increasingly *present in the input* and the design ignores
    them. (en.wikipedia.org/wiki/Content_Credentials; spec.c2pa.org 2.2; NSA CSI "Content Credentials,"
    Jan 2025.) D42 stamps *self vs external* origin (did **we** generate it) but there is **no axis for
    "is this external media authentic / AI-generated / manipulated."** A deepfaked "Alice said X" video
    would be transcribed, grounded, entity-resolved, and remembered as ordinary evidence. At minimum:
    ingest and persist any C2PA manifest as evidence metadata; flag absence/break; decide whether
    synthetic-media confidence feeds D42/confidence math. Treat deepfake *detection* as a non-goal if you
    must, but the C2PA manifest passthrough is nearly free and is currently missing.

### Missing / understated non-goals

16. **Non-goals are stated six times, never as one reconciled list, and omit several.** [V] Live/real-time
    (good), biometric recognition (good), dense per-frame captioning (good), cross-modal-belief-without-
    text (good) appear — but **3D/spatial media (point clouds, LiDAR, 360°/VR), interactive content
    (HTML canvas/live dashboards), and non-speech audio understanding** are never bounded. The
    "documented alternative, not a phase" discipline (CLAUDE.md Rule 2) is applied well per-doc but the
    union is never assembled.

---

## unaddressed-risks[] — design risks

17. **The dual-locator design couples the deterministic char-offset pipeline to nondeterministic VLM caption
    text.** [I — the sharpest structural risk] D46/F2 make `md_span` (char offsets into `document.md`)
    **mandatory for every block**, and the linearization *interleaves VLM captions inline* with the
    transcript/OCR (F2 §2.3 example). A VLM caption is nondeterministic and re-run on version bump — and
    because it sits *inside* the offset-bearing markdown, a single caption re-run **shifts the char
    offsets of every block after it**, invalidating the `source_span` of unrelated, fully-deterministic
    transcription claims. F2 spike #3 ("linearization determinism") and F3 spike #1 gesture at this but
    treat it as a tuning concern; it is an architectural coupling between the nondeterministic DESCRIBE
    output and the TRANSCRIPTION anchor that the whole auditability story rests on. Needs a structural
    fix (e.g., stable per-block IDs as the anchor with offsets derived, or captions in a separate
    addressing space), not a spike.

18. **The P1 visual index can become a de-facto biometric identification tool — directly contradicting
    the no-biometric non-goal.** [I — flagged as inference, not asserted as legal fact] F4's
    `visual_similarity` recipe ("find frames/pages that look like this," image→image ANN over keyframe
    embeddings) over a corpus of person-containing keyframes **is** "find other frames of this person" —
    functionally cross-media face matching, the exact capability F5/F6 forbid as a GDPR Art. 9 /
    EU-AI-Act / BIPA trigger. The design says "we store no face *templates*," but a general visual
    embedding of a face-containing keyframe is template-adjacent and the similarity search is the
    matching step. The boundary between "visual retrieval projection" (allowed) and "biometric gallery"
    (forbidden) is asserted but never examined where it actually blurs. Needs an explicit rule (e.g.,
    person-dominant keyframes excluded from / gated in the visual index, or `visual_similarity` barred
    from person queries).

19. **Decision-numbering collision across the six F-docs is a blocking synthesis defect.** [V] `D45`
    denotes **six different decisions**: F1 D45 = core choice; F2 D45 = convert contract; F3 D45 =
    locator; F4 D45 = P1 two-tier; F5 D45 = belief-layer-over-bundle; F6 D45 = cost cascade; and
    codex_architecture independently proposes D45–D52. Continuing from the canonical log (last entry
    D44) requires **one** reconciled, deduplicated D45+ sequence. Until then the proposed-decisions
    sections are mutually contradictory as written.

20. **"No pre-extraction value gate" (D25) vs the visually-rich Gate-2 and role-drop.** [I] F4 Gate-2
    (only visually-rich units get Tier-B), F2's `role`-based Selection drop of `credits`/`onscreen_text`,
    and the selective-caption rung are each argued to be "structural reduction, not a value gate." The
    argument is plausible but is made *independently* in F1/F2/F4/F6 with slightly different framings; a
    skeptic will read the visually-rich gate as a salience classifier on the hot path (the very thing
    D25/D26–D30 rejected). The synthesis needs **one** crisp statement of why deterministic
    structural/role reduction is categorically not a value gate, applied uniformly.

21. **Redaction recall is the real safety metric and is only a spike.** [V — F6 spike #1] "A missed face
    is an un-redacted face." The whole "redacted-derivative-is-canonical" guarantee (D47) is only as good
    as detector recall on adversarial media (small/occluded faces, far-field/overlapping voices,
    on-screen secrets). It is correctly flagged but remains a measurement TODO underpinning a *structural
    safety claim* — the gating policy ("mount only above a measured recall floor") should be a design
    rule, not a spike outcome.

---

## Top 5 things the synthesis MUST add

1. **Reconcile the decision log into ONE D45+ sequence.** Merge the six F-doc proposals and the codex
   D45–D52 into a single deduplicated set (core choice / convert contract+MediaIndex / polymorphic
   locator+provenance classes / P1 two-tier visual / media belief-layer+capture-time / cost+storage /
   privacy-redact+biometric-non-storage / deletion crypto-shred+prune / unified non-goals). This is a
   blocking defect (risk 19), not a polish item.

2. **Add the two absent legal/safety obligations: illegal-content (CSAM) reporting and content
   authenticity (C2PA).** A `detect`/`redact` hook for hash-matched illegal content with a stated
   §2258A/NCMEC reporting posture (gap 14), and C2PA-manifest passthrough as evidence metadata plus a
   synthetic/manipulated-media flag feeding D42/confidence (gap 15). Both are currently total blanks for
   a system whose premise is "remember ingested media as evidence."

3. **Add a third provenance/confidence tier and the downstream cost tier.** Break the
   `transcription | description` binary with a **low-confidence/uncertain transcription** class (HTR,
   degraded scans, garbled OCR) that cannot confident-supersede (gaps 3, 11); and add the
   **belief-extraction (E2/E3/entity-res/observation-adjudication) cost** of verbose media to the cost
   model, alongside re-conversion/re-embedding amortization and hot keyframe-artifact storage
   (gaps 8–10).

4. **Close the modality routing matrix.** Explicit routes for animated GIF / multi-frame / multi-page
   TIFF (→ video or page-set, not single-image), long audio-only (chapter/topic segmentation + an
   audio-scene DESCRIBE tier or an explicit non-goal), embedded video/audio child-media crossref, a
   canonical-language/translation policy for the text pipeline, and diagram→structure as a stated limit
   (missing-cases 1–7). Reinstate codex_landscape's image-class router.

5. **Fix the dual-locator coupling and the visual-index-as-biometric boundary, and harden three failure
   modes.** Decouple the deterministic char-offset anchor from nondeterministic inline caption text
   (risk 17); rule on whether `visual_similarity` over person-containing keyframes is permitted given the
   biometric non-goal (risk 18); and specify intra-document cross-track contradiction resolution,
   partial/failed-conversion semantics, and a redaction-recall *gating rule* (gaps 12–13, risk 21).

---

### Sources (external verification of the two novel legal/safety gaps)

- C2PA / Content Credentials: https://en.wikipedia.org/wiki/Content_Credentials ·
  https://spec.c2pa.org/specifications/specifications/2.2/specs/_attachments/C2PA_Specification.pdf ·
  https://media.defense.gov/2025/Jan/29/2003634788/-1/-1/0/CSI-CONTENT-CREDENTIALS.PDF (NSA CSI)
- CSAM reporting duty (18 U.S.C. § 2258A; PhotoDNA; NCMEC CyberTipline; penalties):
  https://www.congress.gov/crs-product/LSB10713
- Internal design corpus: `design_fit/F1–F6`, `web_research/M1–M6`,
  `external_agents/{codex_architecture,codex_landscape}`, `decisions.md` (D2/D6/D7/D20/D25/D42/D43/D44),
  `questions.md` (#24 / O4).

*All numbers cited from the research notes are starting points to measure (CLAUDE.md Rule 2), not
committed constants. Items tagged [I] are engineering inferences flagged as such, not verified facts.*
