You are an independent systems architect reviewing a design-stage project. Your job is a rigorous,
opinionated analysis — not a survey, not a summary, and NOT an MVP plan. Read the repo first, then
answer. Take positions. Cite decision numbers (Dx). The project explicitly designs the FULL intended
system at scale (millions of documents), so do not propose "phase 1 / for now / later"; propose the
complete design, and mark genuine scope boundaries as non-goals with rationale.

## What the project is (read these first, repo root = /Users/jpuc/code/moje/ultimate_memory/ugm_3/ugm)
- README.md — the three-plane model (E Evidence / K Knowledge / P Projections).
- decisions.md — the architecture decision log D1–D44 (the canonical record). Especially:
  D1 split source of truth; D2 claims≠relations (many-to-many evidence, evidence_count);
  D3 supersession at the relation level; D6 graph is a derived projection (validity has ONE home);
  D7 rebuild-first projections; D12 per-document trigger chain; D14 the three planes;
  D25/D31–D35 claim extraction (Claimify Selection; NO pre-extraction value gate);
  D32 grounding (dual-field: standalone claim_text + verbatim source_span + char offsets + entailment);
  D36–D40 the E0 document layer + the configurable raw→Markdown conversion module + PageIndex
  structure + P3 corpus filesystem; D41 claims carry an immutable asserted-validity interval;
  D43 the observation layer (untyped, entity-anchored, bi-temporal non-graph facts);
  D44 the Postgres→LadybugDB projection contract.
- plan/designs/overall_design.md — the three-plane DAG and the per-document ingestion pipeline.
- plan/designs/e0_files_design.md — THE most relevant: how a raw file becomes a structured document
  (ingest → convert → structure[PageIndex] → crossref), the GCS/Postgres storage split, the
  configurable conversion module convert(bytes, mime, hints) -> {markdown, blocks[]} with offsets,
  PageIndex per-document structure, and the mounted corpus filesystem (P3).
- plan/designs/e2_e3_claims_relations_design.md — Claimify-staged E2 (Selection / decontextualization
  / decomposition), the context bundle, and D32 grounding.
- plan/designs/observations_design.md — non-graph facts about one entity (value/statement), untyped,
  bi-temporal, supersession by entity-blocking + adjudication.
- plan/requirements/requirements_v3.md — the capabilities/constraints.

## Architectural facts you MUST ground the analysis in
- The Evidence plane is TEXT-CENTRIC today. E0 converts every input to Markdown; E1 chunks text;
  E2 extracts atomic natural-language CLAIMS; E3 normalizes claims into typed entity→entity RELATIONS
  (graph) and untyped entity-anchored OBSERVATIONS (values). Postgres is the source of truth for E.
- Raw bytes live immutably in a GCS "raw" bucket; converted bodies + sidecars in a GCS "artifacts"
  bucket; Postgres holds only metadata + a queryable section index — NEVER document bodies (D37).
- The conversion module (D38) is already meant to be configurable/pluggable, routed by input type
  (digital PDF → text extract; scanned/complex PDF + IMAGES → OCR e.g. Mistral OCR; office/html/email
  → markitdown; text → passthrough). It is versioned (converter_version) and reprocessable (D7).
- GROUNDING (D32): a claim stores a standalone claim_text + a verbatim source_span + CHARACTER OFFSETS
  into the converted text, plus added_context[]; acceptance is anchor (the span is a real slice) +
  window-membership + entailment. This is the auditability crown jewel — every claim traces to an
  exact source location.
- Everything LLM/model-derived is VERSIONED and REPLAYED-FROM-STORAGE on rebuild (D7/D33), never
  re-derived nondeterministically; the raw bytes are the immutable ground truth.
- Bi-temporality everywhere: valid-time (true in the world) vs transaction-time (when we learned it);
  claims also carry an immutable source-asserted validity interval (D41).
- Cheap-first cascades everywhere (D4): deterministic checks → small models → frontier models; LLM
  spend scales with ambiguity/value, not volume. There is NO pre-extraction value gate (D25);
  junk-control is in-call at E2 Selection. Scale target: millions of documents.
- Privacy/deletion: hard-delete / GDPR "forget this source" must cascade through every derived layer
  (open risk #24 in questions.md).

## The scenario to analyze
The system today assumes inputs are (or convert cleanly to) TEXT. The author wants to ingest and
remember IMAGES and VIDEOS as first-class inputs — both standalone (a photo, a screenshot, a recorded
meeting, a screen recording, a product video) and embedded (figures/charts inside PDFs and web pages).
Determine the best way to process video and images, and exactly how it fits the existing memory system.

## The questions to answer (be direct, take a position, cite Dx)
1. THE CORE CHOICE. Should media be (a) TRANSCODED-TO-TEXT at E0 so the existing E1→E2→E3 text pipeline
   runs essentially unchanged (a video becomes a transcript + scene tree + per-scene visual
   descriptions; an image becomes OCR + a structured description), OR (b) carried as a PARALLEL
   MULTIMODAL EVIDENCE TRACK with native media segments and multimodal embeddings, OR (c) some precise
   hybrid? Give your verdict and the reasoning, grounded in the pipeline's invariants (claims, grounding,
   auditability, rebuildability, one-belief-home).
2. THE E0 CONVERSION CONTRACT. Today convert() returns {markdown, blocks[] with char offsets}. What is
   the right contract for an IMAGE (OCR + caption/description + region structure) and especially for
   VIDEO (a temporal, multi-track medium: visual frames + audio + on-screen text + speakers)? Video is
   not a single markdown blob with char offsets — it needs segmentation (shot/scene/chapter detection),
   per-segment ASR transcript with timecodes, visual captioning of keyframes/scenes, OCR of on-screen
   text. What is the "PageIndex analogue" for video (a scene/chapter tree with timecodes) and for
   image collections? Be concrete about the output objects and the cheap-first cascade (deterministic
   scene/shot detection + ASR + OCR before any expensive VLM captioning).
3. GROUNDING for non-text evidence (D32). D32's source_span is char offsets into text. Generalize it:
   for an image the locator is a page/region bounding box; for video it is a timecode range (+ optional
   bbox). Propose the polymorphic media-locator contract that preserves the "every claim traces to an
   exact source location" guarantee. What does window-membership/anchor verification mean when the
   source is a pixel region or a video frame, given a description is a lossy non-deterministic rewrite?
4. RETRIEVAL / P1. Should P1/Lance gain a multimodal-embedding sub-index (keyframe / video-segment /
   page-image embeddings for visual similarity — CLIP/SigLIP/Voyage-multimodal/ColPali-style
   late-interaction "embed the page image, skip OCR")? Is reduce-to-text sufficient for a memory
   system, or is native visual retrieval a real capability worth a projection? Keep D6/D8 discipline
   (projections hold no authority, rebuildable, vectors in Lance not the graph).
5. CLAIMS / OBSERVATIONS / ENTITIES from media. Do media-derived claims fit the existing
   E2/E3/D41/D43 model unchanged (NL claims with asserted validity; values → observations; entity
   resolution)? What changes in the E2 context bundle for a video segment vs a text chunk? Should
   entity resolution from media be TEXT-DERIVED only (names in captions/OCR), or do we attempt visual
   entity linking (faces, logos, products)? Weigh against D20 (no biometric/3rd-party authority) and
   privacy.
6. COST & SCALE. Video is the cost driver (a 1-hour video ≈ thousands of frames). Specify the
   cheap-first media cascade and what makes it affordable at millions-of-documents scale (keyframe/shot
   sampling vs every frame; ASR cheap, VLM captioning the cost center; selective deep understanding).
7. STORAGE / PRIVACY / DELETION. Media is large and privacy-loaded (faces, voices, PII). How does this
   fit the GCS raw/artifacts split + storage classes, and the hard-delete/GDPR cascade (open risk #24)?
   Is PII/biometrics a new first-class concern?
8. WHAT STAYS A NON-GOAL. Live streams? Real-time? Biometric face recognition? Cross-modal belief
   without text grounding? Be explicit.

## Output
Write your full analysis as well-structured markdown to this exact path (create/overwrite only this
file; do NOT touch any other repo file):
  /Users/jpuc/code/moje/ultimate_memory/ugm_3/ugm/_feature_planning/multimodal/external_agents/OUTPUT_FILE
Lead with a one-paragraph verdict, then the detailed analysis with a clear recommended design and a list
of proposed decisions (continue the Dx numbering from D45) and design-doc deltas. Be concrete; prefer
recommendations over surveys; flag anything you think the author is missing. Do not change any other files.
