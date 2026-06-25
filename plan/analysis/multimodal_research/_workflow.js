export const meta = {
  name: 'multimodal-media-analysis',
  description: 'Analyze the best way to process video+images and how it fits the ugm memory system: repo archaeology + web landscape, ugm design-fit analysis, adversarial verification, Claude synthesis',
  phases: [
    { title: 'RepoAndWeb', detail: 'read cloned repos (docling/MinerU/colpali/PySceneDetect/whisperX) + web landscape research' },
    { title: 'DesignFit', detail: 'map findings onto ugm planes/decisions — the 6 ugm-specific architecture answers' },
    { title: 'Verify', detail: 'adversarially check numbers/facts, invariant-preservation, completeness' },
    { title: 'Synthesize', detail: 'consolidated Claude analysis: verdict, recommended design, proposed D45+, deltas, spikes' },
  ],
}

const BASE = '/Users/jpuc/code/moje/ultimate_memory/ugm_3/ugm'
const CTX = `${BASE}/_additional_context`
const OUT = `${BASE}/_feature_planning/multimodal`
const WEB = `First load web tools: call ToolSearch with query "select:WebSearch,WebFetch" then use WebSearch/WebFetch freely. Cite URLs. Distinguish verified fact from inference; flag anything you cannot verify rather than inventing model names, benchmark numbers, or prices.`
const DESIGN = `THE CONSUMING SYSTEM (ugm): a text-centric memory pipeline, designed at full scale (millions of docs). Three planes — E Evidence (per-document; Postgres is truth: E0 files -> E1 chunks -> E2 atomic NL claims -> E3 typed entity->entity relations [graph] + untyped entity-anchored observations [values]); K Knowledge (git, LLM-compiled); P Projections (derived, rebuildable: P1 Lance vector/FTS, P2 LadybugDB graph, P3 mounted corpus filesystem). KEY DECISIONS to read in ${BASE}/decisions.md: D2 claims!=relations + evidence_count; D3 supersession on relations; D6 graph is a projection, validity has ONE home; D7 rebuild-first; D12 per-document trigger chain; D25/D31-D35 Claimify claim extraction (Selection, NO pre-extraction value gate); D32 grounding (dual-field: standalone claim_text + verbatim source_span + CHAR OFFSETS + entailment); D36-D40 E0 doc layer + configurable VERSIONED conversion module convert(bytes,mime,hints)->{markdown,blocks[] with offsets} + PageIndex per-doc structure + P3 corpus filesystem; D37 storage split (raw bytes + artifacts in GCS, Postgres only metadata+section index, never bodies); D41 claims carry immutable asserted-validity interval; D43 observation layer; D44 Postgres->Ladybug projection. Everything model-derived is VERSIONED + replayed-from-storage on rebuild (D7/D33), raw bytes are immutable ground truth. Cheap-first cascades (D4). Read the design docs you need: ${BASE}/plan/designs/overall_design.md, ${BASE}/plan/designs/e0_files_design.md, ${BASE}/plan/designs/e2_e3_claims_relations_design.md, ${BASE}/plan/designs/observations_design.md, ${BASE}/decisions.md, ${BASE}/questions.md.`

// ---------------- Phase 1: repo archaeology + web landscape (one barrier) ----------------

const REPOS = [
  { slug: 'docling', note: 'docling-project/docling — document conversion to Markdown/JSON with figures/tables/pictures. READ: docling/datamodel/ (document model, provenance/bbox), docling/backend/, picture description/classification enrichment, how it emits Markdown + element bounding boxes + provenance offsets, OCR routing, the DoclingDocument schema. We care about: what the convert() output object looks like, how figures/charts/tables are represented, whether per-element offsets/bbox exist (load-bearing for grounding).' },
  { slug: 'mineru', note: 'opendatalab/MinerU — PDF/document extraction. READ how it extracts text/figures/formulas/tables with bounding boxes + reading order, layout analysis, output schema. We care about: figure/region bbox locators, markdown emission, and the cost/stages.' },
  { slug: 'colpali', note: 'illuin-tech/colpali — late-interaction VISUAL document retrieval (ColPali/ColQwen2): embed the PAGE IMAGE directly, skip OCR. READ colpali_engine/ (models, processors, scoring/late-interaction MaxSim, the multi-vector representation). We care about: what is stored per page (number of vectors, dim), how scoring works, storage/latency cost vs single-vector text embeddings, when this beats OCR-then-embed.' },
  { slug: 'pyscenedetect', note: 'Breakthrough/PySceneDetect — shot/scene detection. READ scenedetect/detectors/ (ContentDetector, AdaptiveDetector, ThresholdDetector, HashDetector), how scene boundaries + keyframes are computed, performance characteristics. We care about: cheap DETERMINISTIC video segmentation before any model call, parameters, and what a "scene list" object contains (timecodes).' },
  { slug: 'whisperx', note: 'm-bain/whisperX — ASR + forced alignment (word-level timecodes) + speaker diarization (pyannote). READ the pipeline: transcribe -> align -> diarize, the output segment/word schema with timestamps + speaker labels. We care about: the transcript object shape (word-level timecodes + speakers) that becomes the video "text rendering" with time locators, and the cost/stage ordering.' },
]

const WEBQS = [
  { id: 'M1', slug: 'image_vlm_landscape', q: `Best 2026 approaches to turn an IMAGE into faithful, GROUNDED structured text for a memory system: dense captioning / structured description, chart+figure+table understanding, and OCR. Compare frontier VLM APIs (Claude, GPT, Gemini) vs strong open VLMs (Qwen-VL family, InternVL, etc.). What gives faithful descriptions (low hallucination) at scale, and at what approximate cost per image? How to keep image descriptions GROUNDED/auditable (region references). RECOMMEND a concrete image-understanding approach + the cheap-first cascade (OCR/layout first, VLM description selectively).` },
  { id: 'M2', slug: 'video_understanding', q: `Best 2026 approaches to understand VIDEO for a memory system at scale. Compare: (a) native long-context video models (Gemini ingesting video directly), (b) keyframe-sampling-then-VLM, (c) open video-LLMs (Qwen2.5-VL video, LLaVA-Video). Where is the real COST (tokens/frames), and what is affordable at millions-of-documents scale? How do production systems segment + summarize long video? RECOMMEND the video pipeline: scene/shot segmentation -> ASR transcript -> selective keyframe/scene VLM description -> a scene/chapter structure tree. Be concrete about what is cheap+deterministic vs expensive.` },
  { id: 'M3', slug: 'asr_diarization', q: `Best 2026 ASR + speaker diarization + word-level alignment for video/audio: Whisper / whisperX / faster-whisper / NVIDIA Parakeet+Canary / pyannote / Gemini audio / commercial (Deepgram, AssemblyAI). Accuracy (WER), speed/throughput, cost, self-host vs API, multilingual (incl. Czech). RECOMMEND a self-hostable-first default that yields word-level timecodes + speaker labels, with an API fallback. This becomes the time-anchored TEXT rendering of a video's audio track.` },
  { id: 'M4', slug: 'visual_retrieval_embeddings', q: `Visual document retrieval + multimodal embeddings, 2026. (1) Late-interaction visual retrieval (ColPali/ColQwen2/ColNomic/DSE): embed page images, skip OCR — when does it beat OCR-then-embed-text, and what are the storage/latency costs (multi-vector MaxSim, vectors per page)? (2) Single-vector multimodal embeddings (Voyage multimodal-3, Cohere Embed v4 multimodal, CLIP/SigLIP/Jina-CLIP/nomic-embed-vision) for cross-modal search. Which to put in a vector store (LanceDB) for a memory system, and does LanceDB support multi-vector late interaction? RECOMMEND what a multimodal P1 sub-index should store.` },
  { id: 'M5', slug: 'multimodal_memory_systems', q: `How do existing AI MEMORY / RAG systems handle images and video? Survey Mem0, Cognee (multimodal), Morphik, LlamaIndex multimodal, Graphiti, RAGFlow, and any notable multimodal-RAG frameworks. For each: do they reduce media to text, store multimodal embeddings, or both? Do they keep provenance/grounding to a region/timecode? What do they get right and wrong. RECOMMEND what ugm should STEAL vs AVOID, grounded in ugm's claim/grounding/evidence model. ${DESIGN}` },
  { id: 'M6', slug: 'privacy_pii_deletion', q: `Privacy, PII, biometrics, and deletion for IMAGES + VIDEO at scale in a memory system. Faces and voices are biometric data (GDPR Art.9 special category; BIPA); on-screen PII; the right to be forgotten / hard delete of media + all derivatives. What are the legal/operational constraints, and the engineering pattern for: PII/face detection+flagging, redaction, biometric non-storage, and a deletion cascade that reaches large media blobs + their derived transcripts/keyframes/embeddings/snapshots. RECOMMEND how media privacy should be a first-class concern. ${DESIGN}` },
]

const phase1 = await parallel([
  ...REPOS.map(r => () => agent(
`You are a code archaeologist. Read the ACTUAL source of the cloned repo "${r.slug}" under ${CTX}/${r.slug}/ and extract what is REAL (cite file paths, quote code/schemas, give concrete numbers/params). Do not speculate; if something isn't in the code, say "not found".

Repo focus: ${r.note}

Extract, with file references: the core pipeline/stages; the OUTPUT DATA SCHEMA (what object/fields it produces — esp. any offsets/bounding-boxes/timecodes back to the source); key parameters/thresholds/model names; performance/cost characteristics if stated; and a "steal vs avoid for ugm" note (ugm is a text-centric memory system that needs versioned conversion + grounded locators).

Write findings as markdown to ${OUT}/repo_findings/${r.slug}.md (Write tool). Return ONLY: file path + 5 bullet highlights.`,
    { label: `repo:${r.slug}`, phase: 'RepoAndWeb' }
  )),
  ...WEBQS.map(Q => () => agent(
`You are a rigorous multimodal-ML research analyst. Answer EXHAUSTIVELY with EVIDENCE (cite URLs; give concrete model names, approximate costs/throughput, benchmark numbers; mark verified vs inferred). ${WEB}

QUESTION ${Q.id}: ${Q.q}

You may also read the cloned repos under ${CTX}/ (docling, MinerU, colpali, PySceneDetect, whisperX) for mechanism. Structure: (1) Key findings bullets; (2) Evidence & detail with citations; (3) Confidence & gaps; (4) Recommendation for ugm (concrete, tied to its decisions where relevant).

Write to ${OUT}/web_research/${Q.id}_${Q.slug}.md (Write tool). Return ONLY: file path + 5 bullet highlights + a confidence label.`,
    { label: `${Q.id}:${Q.slug}`, phase: 'RepoAndWeb' }
  )),
])
log(`Phase 1 (repo+web) done: ${phase1.filter(Boolean).length}/${REPOS.length + WEBQS.length}`)

// ---------------- Phase 2: ugm design-fit analysis (the heart) ----------------

const FITS = [
  { id: 'F1', slug: 'core_choice', q: `THE CORE CHOICE (the load-bearing decision). Should media be (a) TRANSCODED-TO-TEXT at E0 so the existing E1->E2->E3 text pipeline runs essentially unchanged; (b) carried as a PARALLEL MULTIMODAL EVIDENCE TRACK (native media segments + multimodal embeddings as first-class evidence); or (c) a precise HYBRID? Give a decisive verdict and reason it from the pipeline's invariants: claims (D2), grounding/auditability (D32), one-belief-home (D6), rebuildability with versioned model-derived artifacts (D7/D33 — note: a media description is exactly like OCR/PageIndex, a versioned converter output over immutable raw bytes), evidence_count/dedup (D2), the per-document trigger chain (D12). Address head-on: is "describe media to text" fatally lossy/nondeterministic, or is it the SAME discipline the system already accepts for OCR and claim extraction? Where (if anywhere) does pure text reduction lose a capability the system should keep (visual retrieval), and is that better served by a P-plane projection than by changing the E pipeline? Conclude with the recommended architecture in one diagram + 5 bullets.` },
  { id: 'F2', slug: 'e0_conversion_contract', q: `THE E0 CONVERSION CONTRACT for media. Today convert(bytes,mime,hints)->{markdown, blocks[] with char offsets} (D38). Define the right contract for an IMAGE (OCR text + structured VLM description + region structure with bboxes) and especially for VIDEO (a temporal, multi-track medium). Video is NOT a single markdown blob: specify the segmentation (deterministic shot/scene/chapter detection a la PySceneDetect/TransNetV2), the per-segment ASR transcript with timecodes (whisperX-style), selective keyframe/scene VLM descriptions, and on-screen-text OCR. Define the VIDEO "PageIndex analogue": a scene/chapter tree with timecode spans + roles + summaries (the structural backbone E1 chunks along and E2 reads). Specify the artifact objects (what lands in the GCS artifacts bucket and what queryable index lands in Postgres document_sections, generalized). Specify the cheap-first cascade ordering and where each model call sits. Keep it a VERSIONED converter (converter_version) reprocessable per D7. Be concrete about the output schema.` },
  { id: 'F3', slug: 'grounding_locator', q: `GROUNDING generalization (D32). D32 stores standalone claim_text + a verbatim source_span + CHAR OFFSETS into the converted text, accepted by anchor (the span is a real slice) + window-membership + entailment. Generalize source_span into a POLYMORPHIC MEDIA LOCATOR that preserves "every claim traces to an exact source location": for text = char range; for an image = page/region bounding box; for video = timecode range (+ optional bbox). Define what anchor/window-membership verification MEANS when the source is a pixel region or a video frame and the "text" was produced by a lossy nondeterministic VLM/ASR — e.g. ASR transcript spans ARE verbatim-checkable + time-anchored (like text), whereas a VLM description is NOT a verbatim slice (so it grounds to a region/frame locator + entailment, not a substring). Propose the locator schema and the per-modality acceptance layers. This is the auditability crown jewel — get it right.` },
  { id: 'F4', slug: 'p1_multimodal_retrieval', q: `RETRIEVAL / P1 multimodal projection. Should P1/Lance gain a multimodal-embedding sub-index (keyframe / video-segment / page-image embeddings; CLIP/SigLIP/Voyage-multimodal single-vector, and/or ColPali-style late-interaction "embed the page image, skip OCR")? Decide: is reduce-to-text retrieval sufficient for a memory system, or is native visual retrieval a real capability worth a projection? Design it as a pure P-plane projection (D6/D8: no authority, rebuildable, vectors in Lance never the graph). Address LanceDB's support for multi-vector late interaction vs single-vector. Define exactly what gets embedded and the new search recipes (e.g. visual_similarity, find_frame). Make clear this NEVER becomes an evidence authority — claims still come from the text rendering.` },
  { id: 'F5', slug: 'claims_observations_entities', q: `CLAIMS / OBSERVATIONS / ENTITIES from media. Do media-derived facts fit E2/E3/D41/D43 unchanged? Specify: how the E2 CONTEXT BUNDLE changes for a VIDEO SEGMENT (transcript window + scene visual description + scene path + neighbor segments + speaker labels) vs a text chunk; how a value read from media ("the dashboard shows headcount 600") becomes an OBSERVATION (D43); how D41 asserted-validity interacts with media TIME (capture/recording time vs depicted time vs EXIF — a screenshot depicts a state at T; a photo's EXIF = capture time). ENTITY RESOLUTION from media: argue for TEXT-DERIVED only (names in captions/OCR/transcript resolve via the T0-T4 cascade) vs attempting VISUAL entity linking (faces/logos/products), weighed against D20 (no biometric/3rd-party authority) and privacy. State what is a recall gap vs a deliberate non-goal.` },
  { id: 'F6', slug: 'cost_storage_privacy_nongoals', q: `COST, SCALE, STORAGE, PRIVACY, DELETION, NON-GOALS. (1) Cost cascade: video is the cost driver (1h video ~ thousands of frames). Specify the cheap-first ladder (deterministic shot/scene detect + ASR + OCR before any VLM; keyframe sampling not every frame; selective deep VLM only where warranted) and what keeps it affordable at millions-of-docs scale; tie to D4/D25 (no value gate — junk control is in-call). (2) Storage: how media fits the GCS raw/artifacts split + storage classes (raw media is big + cold); what goes to Postgres (only metadata/section index). (3) Privacy: are PII/faces/voices/biometrics a NEW first-class concern; flagging/redaction; tie to GDPR. (4) Deletion: how hard-delete/GDPR "forget this source" cascades through large media blobs + derived transcripts/keyframes/embeddings/snapshots (open risk #24). (5) Explicit NON-GOALS (live streams, real-time, biometric face recognition, cross-modal belief without text grounding). Be decisive.` },
]

const fitResults = await parallel(FITS.map(F => () => agent(
`You are the lead architect mapping multimodal research onto the ugm design. Be decisive, concrete, and grounded in ugm's decisions (cite Dx). Full-scope design — NO MVP/phasing language; mark genuine scope boundaries as non-goals with rationale (CLAUDE.md rules). Explain, don't just name techniques.

${DESIGN}

READ FIRST: all of ${OUT}/web_research/*.md and ${OUT}/repo_findings/*.md (glob+read — they are the research base), plus the ugm design docs named above relevant to this question.

DESIGN-FIT QUESTION ${F.id}: ${F.q}

Structure your markdown: (1) Verdict/recommendation up top; (2) The design, concretely (schemas/contracts/diagrams where useful); (3) How it preserves ugm invariants (cite Dx); (4) Risks / what to measure (spikes); (5) Proposed decisions (continue Dx from D45) and design-doc deltas this implies.

Write to ${OUT}/design_fit/${F.id}_${F.slug}.md (Write tool). Return ONLY: file path + 6 bullet highlights.`,
  { label: `${F.id}:${F.slug}`, phase: 'DesignFit' }
))).then(rs => rs.filter(Boolean))
log(`Phase 2 (design-fit) done: ${fitResults.length}/${FITS.length}`)

// ---------------- Phase 3: adversarial verification ----------------

const VERIFIERS = [
  { slug: 'numbers_facts', q: `Verify NUMERIC + factual claims across ${OUT}/web_research/*.md and ${OUT}/repo_findings/*.md: model names, capabilities, costs/prices, throughput, benchmark numbers (WER, retrieval scores), ColPali vectors-per-page/storage, context-window/video-token claims. For each load-bearing claim: traceable to a real source (repo file, vendor doc, paper) or folklore/unverifiable? Web-verify the most load-bearing ones. Output a table: claim | where stated | verdict (confirmed/unverified/likely-wrong) | corrected note.` },
  { slug: 'invariant_coherence', q: `Invariant + coherence critic over ${OUT}/design_fit/*.md (and the research base). Does the recommended design ACTUALLY preserve ugm invariants? Check each: D6 one-belief-home / graph holds no authority; D7 rebuildability with versioned model-derived artifacts; D32 grounding (does the media-locator really keep "every claim traces to an exact source"?); D2 evidence_count/dedup (do duplicate media facts still collapse?); D12 per-document trigger chain (does video's multi-stage cost break per-doc fan-out?); D37 storage split; D25 no-value-gate (is a "process this frame?" decision a smuggled value gate?). Where do the design_fit docs CONTRADICT each other or a decision? What is OVERCLAIMED vs the verified research? Output: invariant-violations[], contradictions[], overclaims[], top-5 things synthesis must resolve.` },
  { slug: 'completeness', q: `Completeness critic over ALL of ${OUT}/web_research, ${OUT}/repo_findings, ${OUT}/design_fit. What MODALITY or CASE is under-covered? Consider: audio-only files (podcasts/voice memos), animated GIFs, slide decks/presentations, scanned handwriting, diagrams/schematics, screenshots vs photos vs scans, multi-page TIFFs, embedded video in docs, very long video (hours), low-quality/blurred media, non-English on-screen text, EXIF/metadata extraction, deepfake/authenticity. What FAILURE MODE, COST blind spot, PRIVACY gap, or NON-GOAL is missing? What design risk is unaddressed? Output: gaps[], missing-cases[], unaddressed-risks[], and the top 5 things the synthesis must add.` },
]

const vResults = await parallel(VERIFIERS.map(V => () => agent(
`You are an adversarial fact-checker / design critic. Default to skepticism; a claim is "confirmed" only with a traceable source. ${WEB}

Task: ${V.q}

Read what you need from ${OUT}/web_research/, ${OUT}/repo_findings/, ${OUT}/design_fit/, and the cloned repos under ${CTX}/. Also read ${BASE}/decisions.md as needed for invariant checks. Write your verdict report to ${OUT}/verify/${V.slug}.md (Write tool). Return ONLY: file path + the 5 most important verdicts.`,
  { label: `verify:${V.slug}`, phase: 'Verify' }
))).then(rs => rs.filter(Boolean))
log(`Phase 3 (verify) done: ${vResults.length}/${VERIFIERS.length}`)

// ---------------- Phase 4: consolidated Claude synthesis ----------------

const synth = await agent(
`You are the lead architect synthesizing a multimodal (image+video) processing analysis into an actionable, binding-quality analysis for the ugm memory system. Write to the standard set by ugm's existing SYNTHESIS docs and obey CLAUDE.md: explain-don't-name; FULL-scope (no MVP/phasing — scope boundaries are non-goals with rationale); understandable cold by a future agent or non-specialist human.

READ EVERYTHING:
- ${OUT}/web_research/*.md   (landscape: image/VLM, video, ASR, retrieval/embeddings, memory systems, privacy)
- ${OUT}/repo_findings/*.md  (docling/MinerU/colpali/PySceneDetect/whisperX mechanism)
- ${OUT}/design_fit/*.md     (F1-F6 ugm-specific answers)
- ${OUT}/verify/*.md         (fact-check + invariant + completeness — DOWNWEIGHT anything flagged unverified/likely-wrong; INCORPORATE the gaps)
- ${BASE}/decisions.md, ${BASE}/plan/designs/e0_files_design.md, ${BASE}/plan/designs/e2_e3_claims_relations_design.md, ${BASE}/plan/designs/observations_design.md, ${BASE}/questions.md (the current design)

Write ${OUT}/01_claude_analysis.md with:
1. "Executive verdict" — the recommended architecture in ~10 bullets (the core choice + why).
2. "The recommended design" — concrete, per concern: E0 conversion contract for image + video (incl. the video scene/chapter structure tree); grounding/media-locator generalization (D32); the E2 bundle + claims/observations/entities from media; the P1 multimodal retrieval projection; the cost-ordered cascade; storage/privacy/deletion.
3. "How it preserves the invariants" — D2/D6/D7/D12/D32/D37 etc., explicitly.
4. "Proposed decisions" — a numbered list ready to become D45+ (and which existing decisions/designs they refine), each a crisp decision + context + consequences in the repo's decision-log style.
5. "Design-doc deltas" — exactly what changes in e0_files_design.md, e2_e3_claims_relations_design.md, a new media design doc, overall_design.md, requirements_v3, questions.md.
6. "Open risks & what to prototype first" — the spikes, highest-leverage first.

Be decisive; prefer recommendations over surveys; cite the research docs + Dx. Return ONLY a 12-bullet executive summary of the recommended design.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { phase1: phase1.filter(Boolean).length, fits: fitResults.length, verifiers: vResults.length, synthesis: '01_claude_analysis.md', summary: synth }
