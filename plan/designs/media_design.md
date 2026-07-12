# Media — Pictures, Video, Audio (Design)

How the memory system ingests, grounds, searches, and serves **media**: standalone images,
audio recordings, video. Binding design for decision **D65**, realizing the requirement that
drove it: *the memory ingests the **derived** information (transcripts, descriptions); the
consuming agent keeps access to the **raw** files whenever it decides it needs them.*
Research: `plan/analysis/media_handling/` (internal + Codex parallel analyses + SYNTHESIS).
This document is the one self-contained home for media; the touched designs (e0, e1,
lifecycle, e2_e3, retrieval) carry surgical cross-edits pointing here. Numbers and tool picks
are starting points to measure (CLAUDE.md).

> **Reading this cold (CLAUDE.md Rule 1) — the vocabulary, because none of it is assumed:**
>
> - **ASR** (automatic speech recognition) — a model that turns audio into a text
>   *transcript* (Whisper-class). Modern ASR also emits **timestamps** per segment or word.
> - **Diarization** — determining *who spoke when* in a recording ("Speaker 1: …, Speaker 2:
>   …"), and, where identity is resolvable, *which person* each speaker is. Without it a
>   transcript is a wall of unattributed speech.
> - **VLM** (vision-language model) — a model that can *look at an image* and produce text
>   about it: describe it, read text visible in it, answer questions about it. (Claude and
>   GPT-4 with vision are VLMs.) In this pipeline the VLM is the tool that turns a photo into
>   its text description, the way ASR turns audio into a transcript.
> - **OCR** vs **description** — OCR extracts *text that is literally visible* in an image (a
>   scanned page, a slide); a description is the VLM's *account of what the image shows* ("a
>   workshop bench with a disassembled pump"). The first is a rendering of symbols; the
>   second is a model's observation. The distinction matters all the way down (§5).
> - **Embedding** — a vector representation of content such that similar meanings land near
>   each other; the system's semantic search already works this way over *text* (D8/D63).
>   **Cross-modal embedding models** (CLIP-class) map *images* (or audio) and *text queries*
>   into the *same* vector space — so the query text "small red connector" can be compared
>   directly against the pixels of stored images, no description involved.
> - Existing machinery this design builds on: every input becomes `document.md` (clean
>   Markdown — the immutable coordinate system all offsets point into, D57) via a versioned
>   **converter** (D38); the **blockizer** derives blocks; PageIndex draws sections; E2
>   extracts **claims** whose `source_span` offsets point into document.md (grounding, D32);
>   the **raw mount** (D51) serves immutable originals read-only, *off* the navigation path,
>   via explicit pointers; `media/` in the artifacts bucket holds *derived* media on the
>   browse path; facts count **distinct source lineages** (D54).

## 1. The conceptual model (confirmed, now bound against media)

**A media file is a source whose testimony reaches the system through a lossy, versioned
transcription, with the original always one explicit pointer away.** Three objects, three
jobs — never conflated:

1. **The source asset** — the immutable raw bytes (`raw/<doc_id>/<content_hash>/original.ext`).
   The audit target, and what a multimodal agent inspects when it decides the derivation
   isn't enough (listen to the tone; look at the picture). Never copied into browse trees,
   never replaced by its derivation.
2. **The representation** — the Markdown-first, model-derived *reading* of the asset:
   `document.md` + its sidecars, produced by a pinned converter route (§2). This is what E1
   blockizes, E2 extracts from, P1 text-searches, and P3 summarizes. **All text eligible for
   extraction/search lives in `document.md`** — text existing only in a sidecar (e.g. a
   `.vtt` subtitle file) is invisible to the blockizer, E2, search, and grounding, and
   therefore does not exist as testimony.
3. **Derived media assets** — regenerable children in `media/`: extracted figures, video
   keyframes, crops, thumbnails, optional interchange transcripts (`.vtt`/JSON —
   *interchange*, never canonical). Each carries its own hash and a locator (§4) back to the
   source region/time it came from.

**Media is an E0 input modality, not a new plane or a parallel pipeline.** Once the converter
has produced the representation, nothing downstream is media-specific except the provenance it
carries (§4) and the disclosure it inherits (§5). PageIndex is *not* extended to media:
structure is drawn over the derived text; media assets hang off it as linked artifacts.

## 2. Converter routes (extends the D38 router table)

The router gains three media routes, each a versioned converter like every other
(`converter_name`/`converter_version`; a model upgrade is a version bump — §6):

| Input | Route | document.md carries | media/ carries |
|---|---|---|---|
| **Audio** (`audio/*`) | **diarized ASR** | the transcript, one block per speaker turn, speakers resolved to entities where possible ("**Bob:** …"), unresolved speakers kept as stable labels ("**Speaker 2:** …") | optional `.vtt` interchange copy |
| **Video** (`video/*`) | ASR (audio track) + **adaptive keyframes** + optional VLM shot notes | the transcript as the document spine, keyframe references at their time positions (exactly like figures in a paper), shot notes as clearly-sectioned blocks | keyframes (adaptive: per shot, not per frame — coverage is a measured knob), thumbnails |
| **Standalone image** (`image/*` that is a *picture*) | **VLM description** (+ OCR of any visible text) | the description + a "Visible text" section, clearly sectioned | a normalized preview/thumbnail |
| *(image that is a document* — a scanned page, a slide deck export*)* | the existing OCR route | as today | as today |

Notes an implementer needs:

- **The image discriminator.** MIME alone cannot distinguish "image that is a document" (→
  OCR route) from "image that is a picture" (→ description route); the route includes a
  cheap classifier (or the VLM's own routing call). Misroutes are recoverable — both routes
  are versioned conversions of immutable bytes; a route fix is a version bump.
- **Diarization is load-bearing, and conservative.** Attributed stance (D59) requires a
  holder: without speakers, every opinion in a meeting recording is holderless and Selection
  drops it. But *wrong* attribution corrupts stance memory, while *missing* attribution
  merely loses claims — so the route resolves a speaker to a person only on positive evidence
  (self-introduction, calendar/participant metadata in the bundle, registry match) and
  otherwise keeps the stable anonymous label. A later, better diarization is a version bump.
- **The sectioned Markdown shape.** Each route emits `document.md` with **structurally
  separated sections by derivation kind** — `## Transcript`, `## Visual description`,
  `## Visible text (OCR)`, `## Shot notes` — so that §5's disclosure labels are properties of
  *sections the converter wrote*, not per-claim judgments anyone has to make.
- **The generalized converter contract** (refines D38 a second time):
  `convert(bytes, mime, hints) → { document.md, source_map, derived_assets[], manifest }` —
  the *page map* generalizes to a **source map** (§4), `derived_assets` are the `media/`
  children with their locators, and the `manifest` records the route, models, versions, and
  section→derivation-kind labeling.

## 3. What "already works" and stays untouched

The representation flows the standard pipeline with **no media-specific machinery**: blocks
(one per speaker turn / description paragraph), sections (PageIndex topical segments over the
transcript; the synthetic root covers short clips; the existing `role` enum suffices), chunks,
claims, facts, K pages, P3 stubs. Counting needs nothing new: a caption and a transcript of
the same video are two views of **one** source lineage — D54's distinct-lineage rule already
keeps them one witness, not two.

## 4. Source locators — grounding to a *moment*, on every surface

**The problem:** block provenance was `{page?, bbox?}` — built for paper. A claim extracted
from minute 14 of a recording could only point at *the whole file*; the agent following the
raw pointer got 90 minutes to scrub. **The fix — the typed `SourceLocator` union:**

```
SourceLocator =
  | { kind: page,         page, bbox?,                     precision: page | region }
  | { kind: image_region, region (normalized rect),        precision: image | region }
  | { kind: time,         start_ms, end_ms, track?,        precision: word | segment | shot }
  | { kind: video_region, start_ms, end_ms, region?, keyframe? }
```

Rules, each load-bearing:

- **Version-pinned, always.** A locator names the document **version** (`version_id` /
  `content_hash`) — never the lineage, never a P3 path. A claim extracted from the 2024
  version of a living file must deep-link into *those* bytes, not this week's replacement.
- **Precision-honest.** ASR provides at least segment timestamps (word-level where the tool
  supports it); the locator says which (`precision: word | segment`). The system never
  fabricates word timing by interpolating characters across a segment.
- **Integer milliseconds in a declared time base** — never formatted strings, never frame
  numbers (variable-frame-rate video makes frames non-portable). `00:14:33` is a *rendering*
  of `start_ms=873000`.
- **The source map** connects `document.md` character intervals to locators — the page map
  generalized. The **grounding chain becomes two hops**: claim → `source_span` (exact,
  deterministic — D32 unchanged) → source-map intersection → raw locator (converter
  precision, disclosed). The first hop proves the claim derives from the representation; it
  **cannot** prove the ASR heard correctly — which is why D32's sampled independent audit
  becomes **modality-aware**: the auditor of an ASR claim *listens to the referenced
  interval*; of a VLM claim, *looks at the referenced frame/region*. Auditing only the
  derived Markdown would grade the converter against its own output.
- **Deep links on every surface.** P3 stubs and `document.md` frontmatter render locators as
  raw-mount-relative links with media fragments (`original.mp3#t=873`); the retrieval
  envelope's provenance handles carry the locators; and unmounted parity requires a
  **locator-aware serving operation** (`hydrate depth=bytes` with a time-range/region, or a
  `source_open` primitive) returning a seekable, codec-aware segment — a naive byte-range is
  a false promise for arbitrary video codecs. Clip extraction is a *serving* operation, never
  a new stored artifact.
- **Three kinds of time, named apart** (schemas, API fields, the consumption skill):
  `start_ms` = where in the *file* the evidence occurs; `claim_valid_from` (D41) = when the
  fact held *in the world*; `ingested_at` = when the *system* learned it. Calling any two of
  these "the timestamp" invites wrong as-of queries.

## 5. Derivation disclosure — the reader always knows how mediated the text is

Claims extracted from media-derived text are **model-mediated testimony**: the ASR may
mishear; the VLM may hallucinate a detail. The mediation is already *auditable* (converter
versions + the raw audit path) and *correctable* (§6); this section makes it **visible at
read time**, because three kinds of media-derived text have genuinely different relationships
to the source:

| `evidence_mode` | Meaning | Example |
|---|---|---|
| `source_expression` | a fallible rendering of symbols/speech *present in the source* | a transcript sentence; OCR'd slide text; an embedded caption |
| `model_observation` | the model's account of what the source *shows* | "the image shows a red valve"; "Alice enters the room" |
| `model_interpretation` | the model's *reading into* the source | "the speaker sounds hesitant"; "the chart implies strong growth" |

Implementation is deliberately cheap and deterministic — **no per-claim judgment exists
anywhere**: the converter's sectioned Markdown (§2) labels each section with its
`derivation_kind` (asr | vlm_description | ocr | shot_notes | passthrough …) and
`evidence_mode` in the manifest; **claims inherit the labels through their `source_span` →
block → section mapping**, cached on the evidence link. The retrieval envelope surfaces both
in the provenance block, so an agent reading "Alice looked hesitant" sees `model_
interpretation (vlm)` and weighs it accordingly. Two boundaries kept explicit: the mode is
**disclosure, never a verdict** (Selection's verifiability rules still decide what is kept —
a model's interpretation faces the same bar as any evaluative text); and `evidence_count`
still counts **source lineages**, never derivation runs — with one caveat the envelope keeps
visible: ten images captioned by *one VLM family* are ten sources sharing one systematic
perception error, so derivation-family provenance stays queryable for any future confidence
policy (composes with D42's independence thread).

## 6. Lifecycle: a better model is a version bump (and the basis now says so)

An ASR/VLM upgrade re-converts unchanged bytes → new `document.md` → new blocks → reuse keys
miss → re-extraction. That is the **processing-driven** ruleset of D54, exactly as for an
extractor upgrade: new claims replace old ones in currency, counts don't move (same lineage),
a fact the new conversion doesn't re-derive is flagged `support_withdrawn` — **never**
retracted (nothing about the *source* changed). This design fixes the precision gap the
analyses found: the extraction basis is now defined over the **full representation
generation** — `(content_hash, converter_version, blockizer_version, extractor_version)` —
so "the toolchain changed" and "the source changed" are formally distinct events
(`evidence_lifecycle_design.md` §1/§3 updated). Old representations remain immutable
(historical grounding must keep resolving); re-runs replay stored output per D7 — a
nondeterministic model is never silently re-called for the same version.

## 7. Media search — because a description can't mention everything

**The discovery problem, stated plainly (this is why §7 exists):** the system can only
text-search what the derivation *wrote down*. A description is a few sentences about a
picture containing thousands of details; the VLM writes what it considered important. Ask
later for "the photo with the small red connector" and text search finds nothing — the
description never mentioned it. **And raw access does not help, because access is not
discovery**: an agent can always open a file *it has found*, but it cannot decide to open a
file it never retrieved. Without this section, anything a description omits is invisible
forever. (Same for sound: transcripts capture speech; the alarm in the background exists in
no text.)

**The mechanism — one more P1 target, riding existing machinery (D8/D63 unchanged):**

- `search(channel=semantic, target=media_segments, query=<text | image | audio>, …)` — a
  Lance table of **cross-modal embeddings**: one row per standalone image, per adaptive video
  keyframe/shot, per bounded audio segment; each row keyed by its **immutable locator** (§4)
  and hydrating to the representation passage + preview + raw deep link.
- The embedding model is **port configuration** exactly like the text embedder (D63): a
  versioned, per-deployment choice. **A deployment without a configured media embedder
  advertises the missing channel as D49's typed `boundary`** — configuration absence, never
  design absence, and never silently pretending description-search covered it.
- Results fuse with the text channels through the existing RRF operator; **zero LLM calls on
  the query path** (D9 holds — embedding lookup, same as text semantic search). When derived
  text and pixels disagree (the caption says "blue car", the visual match says otherwise),
  both candidates return with channel labels — fusion never synthesizes agreement; the agent
  audits raw when it matters.
- Rebuildable projection like all of P1; eval measures each task separately (text→image,
  image→image, text→acoustic, text→shot) — they are different capabilities.

## 8. What P3 and the mounts show

Media documents are ordinary lineages in the corpus tree: a **stub** (frontmatter: lineage,
current version, raw pointer with locator format) + **previews** (keyframes/thumbnails from
`media/`). Never whole raw media in the tree; never per-keyframe pseudo-documents. The raw
mount serves originals as bound in D51 (off-path, explicit pointers, audit-logged,
mime-routed storage classes — media likely to be read sits in standard/nearline, §e0).

## 9. Decision interactions

| Decision | Effect |
|---|---|
| D38/D57 | **refined**: converter contract generalizes (source map, derived assets, manifest); routes added; canonical-text rule (document.md, sidecars are interchange) fixes the e0 §2 transcript-placement ambiguity |
| D51 | **confirmed and completed**: the raw mount + `media/` derived-only rule was the right half; locators + deep links complete the requirement's "agent gets raw when needed" with second-precision |
| D32 | **extended**: two-hop grounding; modality-aware layer-4 audits |
| D54–D56 | **precision fix**: the basis names the full representation generation; upgrades flow the processing-driven ruleset |
| D59 | **served**: diarization is what makes recorded stance attributable; conservative resolution protects it |
| D8/D9/D63 | **unchanged**: media embeddings are one more Lance target + one more port config; zero-LLM query path holds |
| D49 | **extended**: envelope provenance carries locators + derivation disclosure; missing media channel is a typed `boundary` |
| D42 | **composes**: derivation-family provenance kept visible for future independence/confidence math |

## 10. Spikes (measure before locking; merged list from both analyses)

1. **Route-quality golden corpus** — WER/diarization-error/speaker-attribution-precision/OCR
   accuracy/VLM factuality/time-region alignment, multilingual incl. Czech; overlapping
   speech, screen recordings, charts, music, corrupt tracks.
2. **Grounding precision** — word vs segment timestamps: how often does the interval suffice
   for a quick audit; how often do claims need multiple locators.
3. **Modality-aware audit policy** — sampling rates and escalation bands per modality.
4. **Representation-lifecycle drills** — upgrades that (a) change text, (b) change only
   timestamps/speakers, (c) are identical: verify basis swap, reuse, `support_withdrawn`,
   `claims_as_of`, K triggers.
5. **Transcript/video structure quality** — PageIndex boundaries over long recordings.
6. **Description granularity** — whole-image vs region captions vs OCR-first: claim recall vs
   hallucination rate.
7. **Video coverage policy** — shot detection + adaptive sampling vs transient-event recall
   and index size; keyframe-count knobs.
8. **Direct media search recall** per task, sized against what text-over-derivations misses.
9. **Seek & parity** — codec-aware serving, gcsfuse reads, storage-class cost on large files;
   S59 must pass without downloading gigabytes to inspect ten seconds.
10. **Cost & retention** — per-hour ASR/VLM/embedding spend; representation-generation
    growth; hard-forget latency at target scale.
11. **Provider/privacy routes** — which adapters run locally vs send media to a provider;
    the manifest records the execution context (D61 ports).
12. **Image discriminator accuracy** (document vs picture) and misroute cost.
13. **S58 media extension** — a cold agent must distinguish source expression / model
    observation / media time / world time / current fact from the skill alone.

## References

Research: `plan/analysis/media_handling/` (internal, Codex, SYNTHESIS). Decisions: **D65**
(this design), D8, D9, D32, D38, D41, D42, D49, D51, D54–D57, D59, D61, D63.
Cross-edited designs: `e0_files_design.md` §2–§3, `e1_chunks_design.md` §2,
`evidence_lifecycle_design.md` §1/§3, `e2_e3_claims_relations_design.md` §3.3,
`retrieval_design.md` §3/§5/§8. Scenarios: S56, S59 (strengthened), S62–S63 (new).
Eval checks: `plan/implementation_evals/eval_checks/media_*.yaml`.
