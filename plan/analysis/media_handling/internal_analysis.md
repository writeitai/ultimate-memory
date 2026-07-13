# Media Handling — Pictures, Video, Audio (Internal Analysis)

A review of how the design treats media, requested against one stated requirement: **the
memory system ingests the *derived* information (transcripts, descriptions, extracted
figures), while the consuming agent retains access to the *raw* files whenever it decides it
needs them** (look at the picture, listen to the call). Verdict up front: the design's
*conceptual* model already matches that requirement exactly — it was built in the D51
raw-mount round — but the machinery below it has four genuine gaps, one of them (temporal
provenance) load-bearing for the requirement's second half. A parallel independent analysis
(Codex, gpt-5.6) lives in `external_agents/codex.md`; a SYNTHESIS follows if we diverge.

> **Reading this cold.** E0 converts every input to `document.md` (clean Markdown — the
> immutable coordinate system all offsets point into) plus sidecars; the **blockizer** derives
> paragraph-grain blocks from it (D57); PageIndex draws sections over blocks; E2 extracts
> claims whose `source_span` offsets point into document.md (grounding, D32). Two mounted
> media surfaces exist (D51): the **artifacts** bucket's `media/` folder (*derived* media —
> figures extracted from documents, thumbnails, transcripts) on the browse path, and the
> **raw** bucket (whole-file originals — the video, the MP3, the photo) mounted read-only
> **off** the navigation path, reached only via explicit pointers, audit-logged, with storage
> classes routed by mime so agent reads never hit archive fees.

## 1. What is already designed — and it is the right conceptual model

The stated requirement decomposes into two halves, and both are bound:

- **"Ingest the derived information."** Conversion is the designed boundary where any input
  becomes text-the-pipeline-can-eat: `convert(bytes, mime, hints) → {document.md, page_map,
  media[]}` (D38 as refined by D57). Everything downstream — blocks, sections, chunks,
  claims, facts, search — operates on `document.md`. For media, the derived text (a
  transcript, a description) *is* the document.md; the pipeline needs no special media path.
- **"The agent can drop to raw."** Markdown-first navigation with **explicit raw pointers**
  (D51): P3 stubs and document.md frontmatter carry `raw_uri`; the raw mount is read-only,
  off-path, audited. Scenario **S59** is exactly the requirement's example: find the meeting
  via P3/K → read the transcript → follow the raw pointer → *listen to the MP3 yourself*,
  because the transcript is lossy and tone matters. Derived media inside documents (figures)
  are even closer: `media/` sits on the browse path, linked from the Markdown (S56 — read the
  paper, open the figure).

So conceptually: **a media file is a source whose testimony reaches the system through a
lossy transcription, with the original always one explicit pointer away.** That stance is
coherent with everything else (claims are testimony; conversion is versioned; raw is
immutable). Nothing needs re-architecting. What's missing is below the concept.

## 2. Gap 1 — the converter router has no media routes (binding gap)

The D38 router table stops at documents: *digital PDF → text extraction; scanned PDF/images →
OCR; office/html/email → markitdown; text → passthrough*. "Images" appears only as
*scanned-document* OCR. There is **no route at all** for:

- **Audio** (`audio/*`): needs ASR (Whisper-class) → transcript as document.md. **Speaker
  diarization is not optional garnish** — without it, every attributed-stance claim (D59)
  from a meeting recording is unattributable ("*someone* said the launch slips" is exactly
  the holderless-opinion class Selection drops). Diarized turns also give the blockizer its
  natural paragraph grain: one block per speaker turn.
- **Video** (`video/*`): three derived artifacts — the ASR transcript (the document.md
  spine), **keyframes** into `media/` (linked from the transcript at their positions, exactly
  like figures in a paper), and optionally VLM shot/scene notes as clearly-marked blocks. A
  video is, structurally, "an audio document with figures."
- **Standalone images** (`image/*` that is a *photo/diagram*, not a scanned text page): a
  **VLM description** becomes document.md (marked as description, §4), the original reachable
  via the raw pointer (per the D51 rule, whole-file originals are *not* copied into
  `media/`). The router needs a discriminator here — "image that is a document" (→ OCR)
  versus "image that is a picture" (→ description); mime alone can't tell, so this is a
  cheap classifier or a VLM's own call inside the route.

All of this is *router table content* — per-deployment config in the exact shape D38 already
defines, plus tool slots (`asr_*`, `vlm_*` converter names/versions). No new architecture;
one design-table extension in `e0_files_design.md` §3.

## 3. Gap 2 — temporal provenance: the load-bearing one

Block provenance today is `{page?, bbox?}` (e1 §2) — built for paper. For time-coded media
the analog is **`{t_start?, t_end?}`**, and it is not cosmetic; it is the second half of the
requirement done properly. Without it, S59's agent gets the raw pointer to a *90-minute file*
and scrubs blindly. With it:

- ASR output arrives with per-segment timestamps for free (every Whisper-class tool emits
  them); the converter's page map generalizes to a **time map** (char-range of document.md →
  [t_start, t_end] of the source).
- The blockizer stamps blocks with their time range exactly as it stamps pages today —
  provenance tiers were *designed* to be extensible ("best-effort per converter capability").
- The grounding chain then ends at a *moment*, not a file: claim → `source_span` →
  block → `t=873s` → the raw pointer **with a timestamp fragment** (e.g.
  `original.mp3#t=873`). P3 stubs and the retrieval envelope's provenance handles carry the
  deep link. An agent checking "what was actually agreed" jumps to 14:33 instead of
  listening to an hour.

Cost: one optional field pair on the block record + the time-map variant of the page map +
deep-link formatting in stubs/envelope. This is the single highest-value fix in this
analysis.

## 4. Gap 3 — the epistemics of machine-derived testimony (mostly already handled; one marker missing)

Claims extracted from a transcript or an image description are **model-mediated testimony**:
the ASR may mishear, the VLM may hallucinate a detail. Three questions:

1. *Is the mediation auditable?* **Yes, already**: `converter_name`/`converter_version` are
   stamped per version (D38); the grounding chain ends at the raw file (and with Gap 2, at
   the timestamp); a human or agent can always re-listen/re-look.
2. *Is the mediation correctable?* **Yes, already — and this is elegant**: a better ASR/VLM
   is a `converter_version` bump → re-convert → new blocks → reuse keys miss → re-extraction
   → the old claims stop being current. The lifecycle machinery treats a re-transcription of
   unchanged bytes exactly as it should: *same testimony, better transcription* — the D54
   re-transcription ruleset. **But see Gap 4: the basis definition doesn't actually name
   converter_version yet.**
3. *Is the mediation visible at read time?* **Not yet — the one missing piece.** A claim from
   a VLM's description reads, in retrieval, exactly like a claim from authored text. For most
   uses that's fine (the source doc discloses `converter_name`), but description-derived
   claims are one epistemic step further from the source than transcript-derived ones (a
   description is the model's *interpretation*, not a rendering of speech). Proposal, kept
   minimal: a **`derivation` marker on the document version** (`verbatim | transcribed |
   described` — set by the route, not per-claim machinery), surfaced in the retrieval
   envelope's provenance block. Agents then know "this fact came from a described image"
   without any new claim-level structure. Deliberately *not* proposed: per-claim confidence
   scores from ASR/VLM — unactionable precision, and the correction path (version bump) is
   the real mechanism.

## 5. Gap 4 — the lifecycle basis should name the whole toolchain (precision fix)

`evidence_lifecycle_design.md` defines the extraction basis as *(content_hash,
extractor_version)*. A **converter bump** (new ASR) changes document.md → new blocks → new
chunks → re-extraction — mechanically it flows (reuse keys miss), but the *basis definition*
and the currency-reason vocabulary don't name it: `reextracted` is defined as "a newer
extraction generation covers the chunk," which is not literally what happened (the
*transcription* generation changed). For media corpora this is the **common** upgrade path
(ASR models improve fast), so the definition should be exact: basis = *(content_hash,
converter_version, blockizer_version, extractor_version)* — the full toolchain whose change
means "same testimony, re-transcribed" — with `reextracted` covering any toolchain-driven
re-derivation (or a sibling reason `reconverted`, cosmetic choice). One-paragraph fix in the
lifecycle design + a comment in the schema's currency enum.

## 6. Gap 5 — search over media: text-first is right; direct media embeddings are a boundary

P1 indexes text (chunks, claims, labels). For media, discovery therefore rides the
*derivations*: transcripts and descriptions are chunked, embedded, claim-extracted like any
text — "find the call where the cutover slipped" works via the transcript. Is that enough?

- **For this system's consumers, yes as the default**: the agents are multimodal — once
  navigation lands them on the media (via text search + deep links), *they* can look/listen.
  The system's job is finding and grounding, not seeing.
- **Direct cross-modal search** (CLIP-class image embeddings; audio embeddings — query-by-
  image, "find photos that look like this") is real capability the design does not have and
  currently has no consumer for. It should be a **documented boundary** with a named
  admission condition — measured retrieval failures on an image-heavy corpus where
  descriptions demonstrably under-serve (e.g., visual-similarity queries) — implemented, if
  ever, as additional P1 Lance tables keyed by media id (the P1 estate already handles
  multiple embedding spaces; D8 unchanged).

## 7. Smaller notes

- **PageIndex over transcripts** works as-is: sections = topical segments over speaker-turn
  blocks; the synthetic-root fallback covers short clips; the `role` enum needs nothing new
  (turns are `body`; a `figure_caption` role already fits keyframe notes). Standalone images
  get the synthetic root (their description is one short document).
- **P3 placement**: media documents are ordinary lineages — the tree places them by
  topic/source like anything else; stubs' frontmatter carries the raw pointer (+ timestamp
  deep-link format from Gap 2). Nothing new needed beyond the stub link format.
- **`media/` provenance rows**: extracted media (keyframes, figures) should carry
  `{page?|t_start/t_end?, caption?}` in `conversion.json`/`meta.json` so figures are
  themselves time/page-anchored — currently implied, worth one line in e0 §3.
- **Requirements wording**: §E0 says "normalized to a common text form via a configurable
  conversion module (OCR where needed)" — should say media too ("OCR / transcription /
  description where needed"), one-line fix.
- **Storage cost**: raw video is the storage-class story's whole reason (already designed —
  mime-routed classes); keyframe count per video is a knob → spike.

## 8. Recommendations (candidate binding, likely one decision)

1. **Extend the D38 router table** with the three media routes (audio → diarized ASR;
   video → ASR + keyframes + optional shot notes; image → OCR-vs-description discriminator),
   tool slots versioned like every converter. *(e0 §3)*
2. **Add the temporal provenance tier**: time map alongside the page map; `{t_start?,
   t_end?}` on blocks; timestamp deep links in raw pointers (stubs + envelope provenance
   handles). *(e0 §3, e1 §2, p3 stub contract, retrieval envelope — small touches each)*
3. **`derivation: verbatim | transcribed | described`** on document versions, surfaced in the
   envelope provenance. *(schema §6, retrieval §5)*
4. **Fix the lifecycle basis** to name the full toolchain; clarify the currency reason.
   *(lifecycle §1/§3)*
5. **State the search boundary** (no direct media embeddings; admission condition named).
   *(retrieval §12 or e0)*

## 9. Spikes

1. ASR/diarization tool bake-off (quality per language incl. Czech; timestamp fidelity;
   diarization accuracy feeding D59 stance attribution).
2. Image discriminator (document-image vs picture) accuracy; route misclassification cost.
3. Keyframe policy (count/selection per video length) vs storage + browse usefulness.
4. VLM description quality → claim quality on a photo corpus (does described testimony
   produce acceptable extraction precision?).
5. Timestamp deep-link format portability across players/harnesses (`#t=` media fragments).

## References

Bound today: D37/D38/D51/D57 (+ refinement notes), `e0_files_design.md` §2–§5,
`e1_chunks_design.md` §2, `retrieval_design.md` §5/§7, scenarios S56/S59,
`p3_agent_navigation.md`. Related decisions: D32 (grounding), D42 (origin), D54–D56
(lifecycle), D59 (attributed stance — why diarization matters). Prior art: PR #25
(closed unmerged; superseded by the D51 round and this analysis).
