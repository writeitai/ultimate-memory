# Media Handling — SYNTHESIS (internal × Codex)

Two independent analyses of media treatment (pictures, video, audio) against the owner's
requirement — *ingest the derived information; the agent keeps access to the raw files* —
were produced in parallel: `internal_analysis.md` (Claude) and `external_agents/codex.md`
(Codex, gpt-5.6-sol, xhigh). This synthesis records the convergence (the conceptual model and
all four core gaps), the adoptions (Codex went deeper on several mechanisms), the two genuine
divergences and their resolutions — **one resolved against the internal analysis** — and the
merged candidate decision package.

## 1. Convergent — treat as settled direction

| Point | Substance |
|---|---|
| **The policy is already right** | D51's model *is* the requirement: derived text (transcript/description) becomes `document.md` and feeds the normal pipeline; whole-file originals live on the raw mount, off-path, one explicit pointer away; `media/` holds only derived assets. Media is an **E0 input modality, not a new plane** — no parallel media pipeline. |
| **The four gaps** | Both found, independently: (1) the D38 router has **no media routes** (audio/video/standalone images); (2) provenance lacks a **time dimension** — claims must trace to a moment, not a file; (3) model-mediated testimony is auditable and correctable but **not visible at read time**; (4) the lifecycle **basis omits the converter/representation generation** (the common upgrade path for media is ASR/VLM improvement, and it must flow the *processing-driven* ruleset — currency swap, `support_withdrawn` on non-rederivation — never source-retraction). |
| **Diarization is load-bearing, and conservative** | Without speakers, meeting-recording stances are holderless and D59 drops them. Both analyses choose the conservative failure: an unresolved `Speaker 2` stays unresolved — wrong speaker *attribution* corrupts stance memory, missing attribution merely loses claims. |
| **Counting already protects against derivation double-counting** | A caption and a transcript of the same video are two views of one source: D54's distinct-lineage rule keeps them one witness. |
| **Text search is the cheap-first default** | Transcripts/descriptions/OCR make media discoverable by the existing text channels; "where did anyone say the cutover slipped" needs no audio embeddings. |

## 2. Adopted from Codex (deeper than the internal analysis)

1. **A binding-text bug caught**: `e0_files_design.md` §2 lists "transcripts" *inside*
   `media/` while §3 makes the converter's Markdown the downstream body. Resolution: **the
   canonical ingestible transcript text lives in `document.md`** (text existing only in a
   `.vtt` sidecar is invisible to the blockizer, E2, P1, and D32 anchors); `media/` may hold
   a `.vtt`/JSON *interchange* copy, provenance-linked, never canonical.
2. **The typed `SourceLocator` union** — supersedes the internal analysis's bare
   `{t_start, t_end}`: `page | image_region | time | video_region` (+ pageless source-range),
   each with an honest **`precision`** field (`word | segment | shot`; never fake word timing
   by interpolation), integer milliseconds in a declared time base (frame numbers are
   non-portable under variable frame rates), and — critically — **pinned to a document
   *version*** (never a lineage or a P3 path: a claim from the 2024 version must not deep-link
   into this week's replacement file). The converter's page map generalizes to a **source
   map** (char-interval → locators).
3. **Two-hop grounding + modality-aware audits**: the D32 anchor proves the claim derives
   from the *representation*; it cannot prove the ASR heard right. Layer-4 sampled audits
   must therefore audit **the raw modality** (listen to the interval, look at the region) —
   "auditing only the derived Markdown would grade the converter against its own output."
4. **The generalized converter contract**: `document.md + source_map + derived_assets +
   manifest`, with a sectioned Markdown shape per route (Transcript / acoustic events /
   visual description / visible text / regions) so derivation kinds are *structurally*
   separated in the text itself.
5. **Representation generations as identified immutable objects** joining the D54 basis —
   with upgrade semantics exercised as a first-class spike (text changed / only timestamps
   changed / identical output).
6. **Serving reality**: deep links need a **locator-aware serving operation**
   (`hydrate depth=bytes` + time-range, or `source_open`) with codec-aware segment serving —
   a bare byte-range promise is false for arbitrary video; mounted and unmounted parity both
   required (S59 must not force an unmounted agent to download 2 GB to check ten seconds).
7. **Three kinds of time, named apart** in schemas/skill: media-timeline position
   (`start_ms`) ≠ asserted world-validity (D41) ≠ transaction time. Calling all three
   "timestamp" invites wrong as-of queries.
8. **The correlation caveat**: ten images captioned by one VLM are ten lineages sharing one
   systematic perception error — the count is the correct *source* count but not a calibrated
   probability; the envelope keeps derivation-family provenance visible so confidence policy
   can see the correlation (composes with D42's independence thread).
9. Smaller: adaptive keyframe policy (not every frame; coverage reports); P3 holds stubs and
   previews, never whole raw media nor per-keyframe pseudo-documents; EXIF/embedded-metadata
   extraction is deployment policy through D61 ports (one-trust-domain unchanged); S58
   extension testing whether a cold agent distinguishes source expression / model observation
   / media time / world time / current fact.

## 3. The two divergences, resolved

**D1 — direct media search: internal said "documented boundary"; Codex said "design it in".
Resolved FOR Codex.** The internal analysis proposed text-over-derivations as the design and
CLIP-class media embeddings as a boundary with an admission condition. Codex's counter is
correct on both grounds: (a) **discovery is not solved by reachability** — an agent cannot
decide to open a file it never retrieved, and descriptions are *selective* (the VLM omits the
small red connector; ASR says nothing about the alarm sound); (b) under CLAUDE.md Rule 2 the
admission-condition framing was **deferral dressed as a boundary** — the mechanism is cheap by
design (one more P1 Lance target, `media_segments`, keyed to immutable locators; embeddings
are already versioned port configuration per D63; zero LLM on the query path; RRF-fusable).
Resolution: the **complete design includes the `media_segments` semantic target** (image /
keyframe / acoustic-segment embeddings, locator-bearing rows, rebuildable projection); a
deployment without a configured media embedder advertises the missing channel as D49's typed
`boundary` — configuration absence, not design absence.

**D2 — where derivation metadata lives: internal said a version-level marker; Codex said
claim/evidence-grain metadata. Resolved as a middle with Codex's semantics.** The internal
version-level `derivation: verbatim|transcribed|described` fails for video — one document
mixes literal transcript, VLM observation, and interpretation, and a version-level flag
cannot distinguish "Alice said X" from "Alice looked hesitant" inside the same file. Codex's
trichotomy is adopted — **`source_expression | model_observation | model_interpretation`** +
`derivation_kind` — but implemented without per-claim machinery: the converter's sectioned
Markdown (adoption #4) makes derivation kind a **block/section-grain, deterministic label**
(from the route manifest), and claims **inherit it through their `source_span` → block
mapping** — derivable, cacheable on the evidence link, no new judgment call anywhere. The
mode is disclosure, never a verdict; Selection's existing verifiability rules still govern
what is kept (a model's *interpretation* faces the same bar as any unattributed evaluative
text), and whether high-impact `model_observation` claims need a stricter K3 admission dial
is left as an open policy spike (Codex failure-mode 1).

## 4. Merged candidate decision package (likely one decision, D65-class)

1. **Media is an E0 input modality** — Markdown-first representation + one reachable
   immutable raw asset; no new plane. *(confirms existing policy, binds it against media)*
2. **Canonical text lives in `document.md`**; `media/` = derived support assets only
   (keyframes, crops, thumbnails, interchange transcripts); whole-file originals stay raw.
3. **Converter contract generalizes** to `document.md + source_map + derived_assets +
   manifest`, with bound routes: audio → diarized ASR; video → ASR + adaptive keyframes
   (+ optional shot notes); standalone image → document-vs-picture discrimination → OCR or
   VLM description. Sectioned Markdown shape per route.
4. **Typed source locators** (page/region/time/video-region, precision-honest, ms-based,
   version-pinned) flow claim → span → source map → raw locator; deep links on every surface
   (stub frontmatter, envelope provenance, locator-aware serving op); modality-aware D32
   audits.
5. **Derivation disclosure**: block-inherited `derivation_kind` + `evidence_mode`
   (expression/observation/interpretation) on evidence, surfaced in the envelope; three kinds
   of time named apart.
6. **Representation generation joins the D54 basis**; ASR/VLM upgrades are processing-driven
   re-transcriptions (currency swap; `support_withdrawn` on non-rederivation; never
   retraction).
7. **P1 gains the `media_segments` target** (visual/acoustic embeddings, locator-keyed,
   rebuildable, RRF-fused); absent media embedder ⇒ typed `boundary`.
8. **P3**: media stubs + previews only; raw off-path but fully reachable, mounted and
   unmounted.

## 5. Spikes (merged; Codex's list adopted nearly whole)

Route-quality golden corpus (WER/DER/attribution/OCR/VLM-factuality/alignment, multilingual
incl. Czech); grounding precision (word vs segment audit-interval usefulness); modality-aware
audit sampling policy; representation-lifecycle upgrade drills; transcript/video PageIndex
structure quality; visual-description granularity vs hallucination; video coverage policy;
direct-media-search recall per task (text→image, image→image, text→acoustic, text→shot);
seek/parity + storage-class cost on large files; per-hour cost + hard-forget latency at scale;
provider/privacy execution-context recording (D61); S58 media-comprehension extension;
image discriminator accuracy; keyframe policy knobs.

## 6. Bottom line

Unanimous: the conceptual model the owner asked for is already the design's stance — *the
memory ingests derivations; the agent can always drop to raw* — and it survives both analyses
untouched. The work is below the concept: routes, locators, disclosure, one basis fix, one
new P1 target, and one binding-text bug. The internal analysis conceded both real divergences
in Codex's favor (media search designed-in; claim-grain disclosure semantics), each on
arguments its own framing should have caught: reachability isn't discovery, and a
version-level marker can't describe a video.
