# F5 — Claims, Observations & Entities from Media (design-fit)

**Question.** Do media-derived facts fit ugm's belief layer — E2 claim extraction (D31–D35),
E3 relations/observations (D2/D43), claim asserted-validity (D41) — **unchanged**? Concretely:
(1) how the E2 *context bundle* changes for a **video segment** vs a text chunk; (2) how a value
**read from media** ("the dashboard shows headcount 600") becomes an **observation** (D43); (3) how
D41 asserted-validity interacts with **media time** (capture/recording time vs depicted time vs EXIF);
(4) **entity resolution** from media — text-derived-only vs visual entity linking (faces/logos/products),
weighed against D20 and privacy — and what is a *recall gap* vs a *deliberate non-goal*.

Grounded in the research base (`../web_research/M1–M6`, `../repo_findings/{whisperx,pyscenedetect}`) and
the ugm designs (`decisions.md`, `e2_e3_claims_relations_design.md`, `observations_design.md`,
`e0_files_design.md`).

---

## 1. Verdict / recommendation

**Yes — the belief layer is media-agnostic and stays unchanged.** Claims, relations, observations,
supersession, `evidence_count`, bi-temporal validity, and the T0–T4 entity cascade all operate on
**text + a provenance locator**. Media reduces to exactly that at E0 (transcript, OCR text, scene
caption, each with a timecode/bbox locator — F1–F4), so E2/E3/D41/D43 run **with no new tables, no new
belief home, and no media-specific branch in the supersession engine.** A photo's "headcount 600" and a
PDF's "headcount 600" produce the *same* observation row on the *same* entity, adjudicated by the *same*
cascade.

Four targeted refinements make the fit honest — none is a new plane, none is MVP/phasing:

- **One cross-cutting contract change (shared with F1–F4, not owned here): the D32 locator goes
  polymorphic** — `char_span` | `{page, bbox}` | `{t_start, t_end, speaker?}`. The belief tables don't
  change; only the *grounding locator* on a claim generalizes.
- **The E2 bundle becomes polymorphic (content, not mechanism — D31 unchanged).** For a video segment
  the bundle is the transcript window as the "chunk" plus media-typed context elements (scene caption,
  OCR block, scene-tree path, neighbour segments, speaker labels). The extractor still does
  Selection → Decontextualize → Decompose → Ground.
- **Grounding routes by bundle-element origin (refines D32, extends D42).** Verbatim media-text
  (OCR/ASR) is first-class source text; a VLM scene-caption is a *model assertion*, origin-stamped and
  never usable as a verbatim anchor or as independent corroboration.
- **D41 gains capture-time as a lower-precedence, immutable metadata seed for depicted/valid-time** —
  not a third clock, not a new authority. Precedence: *content-asserted grounded date* > *capture time
  (EXIF/container)* > *ingestion time*.

**Entity resolution is text-mediated only.** Names in OCR / transcript / mapped speaker labels resolve
through T0–T4 (D17) unchanged. **Visual biometric identity linking (faces, cross-file voiceprints) is a
deliberate non-goal** on D20 + GDPR Art. 9 + EU AI-Act + BIPA grounds (M6). Visual content may *emit
candidate name strings* (a logo→"Acme" caption) into the OCR/caption stream, which then resolve via the
one cascade — it may never assign `entity_id`s directly. Entities that appear **only on screen and are
never named in any text** are an **acknowledged recall gap**, the visual twin of the cross-document
coref gap (questions.md #22).

---

## 2. The design, concretely

### 2.1 Where media enters the belief layer

E0 (F1–F4) renders a media file into the same shape every other document produces — Markdown text + a
section/scene structure + `blocks[]` with locators — so E1/E2/E3 are downstream of a **uniform
contract**. For a video the linearized Markdown is the diarized transcript interleaved with per-scene
`[visual: …]` captions and `[on-screen: …]` OCR (M2 §4.2); for a standalone image it is OCR Markdown +
optional figure caption (M1). The belief layer never sees pixels — it sees text with locators.

```
E0 (media-aware convert, F1–F4)              E1            E2 (Claimify, D31)        E3 (D2/D43)
 video ─ demux/scene-detect (deterministic)  chunk =       Selection →               claim → 0..n
       ─ ASR+diarize (WhisperX) ─ verbatim   transcript    Decontextualize →           relations
       ─ OCR on keyframes ─ verbatim          window +      Decompose →               claim → 0..n
       ─ selective VLM caption ─ ASSERTION    a context     Ground (D32, by-origin)     observations
       → linearized Markdown + blocks[]        prefix      ─────────────────────────►  (entity-anchored,
         each block: {text, locator, origin}                                            bi-temporal, D43)
```

The two **origin** classes of media-text are the load-bearing distinction (M5 STEAL-3):

| block origin | examples | is it source text? | D32 grounding path |
|---|---|---|---|
| **verbatim media-text** | ASR transcript, on-screen OCR, slide text | **yes** — the words verbatim-exist at a timecode/bbox | anchor (L1) + window-membership (L2) **as written** |
| **model description** | VLM scene/figure caption, chart→prose | **no** — a lossy non-deterministic rewrite | entailment (L3) + locator provenance + sampled audit (L4); **origin-stamped** |

### 2.2 The E2 context bundle for a VIDEO SEGMENT (vs a text chunk)

D31's bundle is already "target chunk + header + section path + E1 prefix + ±N neighbours + entity
hints, never a bare chunk." The video bundle is the **same shape with media-typed elements** — the
transcript window is the "chunk"; the visual/OCR/speaker streams are the *context* that makes a spoken
fragment decontextualizable.

| text-chunk bundle element (D31 §3.1) | VIDEO-SEGMENT analogue | why it earns its tokens |
|---|---|---|
| target **chunk** (Markdown) | the segment's **diarized transcript window** (the primary text unit; M2/M3) | the spoken words are the semantic pipeline of most video |
| **document header** (title, date, source, lang) | video header: title, **`captured_at`** (recording date), source, duration, language(s) | resolves "this meeting", and supplies the depicted-time default (§2.4) |
| **PageIndex section path + summary** | **MediaIndex scene-tree path** (chapter → scene) + scene/chapter summary (the "PageIndex analogue for video", M2 §4.2) | tells the model it is in "Q3 review › headcount slide" vs idle chatter; drives Selection |
| **E1 context prefix** | the segment's context prefix ("…screen-share of the headcount dashboard during the Q3 review…") | the compact "where this sits" sentence |
| **±1/±2 neighbour chunks, same section** | **±1/±2 neighbour transcript segments**, same scene/chapter (time-adjacent) | antecedents for "as you can see", "that number" |
| **known entity hints** | hints from **mapped speaker labels** + OCR'd names on the keyframe | permission to resolve "the CFO" → Alice, not to invent |
| *(no text analogue)* | **scene visual description** `[visual: …]` (VLM caption, **model-assertion origin**) | grounds deixis the transcript leaves implicit ("this chart") |
| *(no text analogue)* | **on-screen OCR** `[on-screen: Headcount 600]` (verbatim origin, bbox+timecode) | the actual on-screen facts; often the *only* place a value appears |
| *(no text analogue)* | **speaker labels** (`SPEAKER_00` → resolved entity where text permits) | supplies the **attribution** "X" in D32's "*X said* Y entails *X said Y*" rule |

**Concrete bundle contract** (one ordered object handed to E2; the extractor is unchanged):

```jsonc
{
  "target": { "kind": "transcript_window", "text": "...as you can see we're at 600 now...",
              "locator": { "video_id": "v1", "t_start": 1832.4, "t_end": 1849.1, "speaker": "SPEAKER_00" } },
  "header": { "title": "Q3 review", "captured_at": "2025-10-02", "capture_precision": "day",
              "capture_source": "container", "source": "meet-recording", "lang": ["en"] },
  "scene_path": "Q3 review › Financials › headcount slide",
  "prefix": "screen-share of the headcount dashboard during the Q3 review",
  "neighbours": [ { "t_start": 1820.0, "t_end": 1832.4, "speaker": "SPEAKER_00", "text": "...let's look at people..." } ],
  "context_blocks": [
    { "origin": "ocr",     "text": "Headcount  600",  "locator": { "video_id":"v1","t_start":1834.0,"bbox":[120,80,360,140] } },
    { "origin": "caption", "text": "a dashboard panel labeled Headcount showing 600", "model_version": "qwen3vl-8b@...",
      "locator": { "video_id":"v1","t_start":1834.0,"bbox":[100,60,800,520] } }
  ],
  "entity_hints": [ { "surface": "SPEAKER_00", "candidate": "Alice Novak", "from": "agenda+self-intro OCR" } ]
}
```

E2 then runs unchanged: **Selection** keeps "we're at 600" (verifiable quantity; never-drop class, D35)
and drops idle chatter / a vacuous caption like "a person stands near a screen" (generic, D31);
**Decontextualization** resolves "we're at 600" using the OCR block + scene path + speaker → "Acme's
headcount is 600"; **Decomposition** keeps attribution if the value is reported speech ("Alice stated…");
**Grounding** anchors on the verbatim OCR "Headcount 600" (L1/L2) and treats the caption only as
entailment support (L3) — the model-read pixels, not the generated sentence, are the anchor.

### 2.3 A value read from media → an OBSERVATION (D43), end to end

"the dashboard shows headcount 600" is a value about **one** entity (object = a number, not a second
entity) → **observation** by D43's definition. It is *the D43 running example*, reached via media:

| step | what happens | invariant |
|---|---|---|
| **E0** | OCR block `Headcount 600` @ `{t,bbox}` (verbatim) + caption `[visual: headcount panel 600]` (assertion) | D38 convert; D7 versioned |
| **E2 Selection** | KEEP "headcount 600" (quantity = never-drop, D35) | D31/D35 |
| **E2 Decontext.** | subject ← scene/header → **Acme**; "now" ← `captured_at` (§2.4) | D31, D19 in-call |
| **E2 Ground** | `source_span` = OCR "Headcount 600"; `locator` = `{video_id, t, bbox}`; anchor+window-membership pass | **D32 (polymorphic locator)** |
| **E3 normalize** | single-entity value claim → **no relation** → **observation** on Acme, `statement` = "Acme's headcount is 600" | D2/D18/D43 |
| **E3 supersede** | block on entity Acme → adjudicate vs prior headcount; *changing effective state* → **cap prior, insert** | D4/D43, no-cap rule |

**No schema change.** The value + any period live in `statement` exactly as D43 specifies — no structured
`value` column, the untyped premise holds. The *only* media-specific signal is carried as **provenance +
origin on the evidence claim**, and it feeds the adjudicator's confidence, not the schema:

- value from **verbatim OCR / transcript** → strong, anchor-grounded → may **confident-supersede**.
- value **read by a VLM from a chart** with no OCR text (the model *estimated* a bar as "≈600") →
  **model-assertion origin**, grounded only by entailment → **must not confident-supersede** (clears no
  supersede margin alone); it lands as a low-confidence observation that **coexists / flags**, never
  silently caps a text-grounded prior. This is the D43 §3.4 adjudicator contract honoured against the
  M1 chart-hallucination risk — origin is the dial.

The **no-cap rule (D43)** is media-agnostic: "headcount 600" is a *changing state* → cap; "Q3 revenue
$5M shown on the dashboard" is a *fixed-period figure* → never cap, conflicting same-period figures
coexist. The adjudicator decides state-vs-measurement from `statement` semantics; media changes nothing
here. The **depicted time** (§2.4) is what seeds `valid_from`.

### 2.4 D41 asserted-validity vs MEDIA TIME (capture vs depicted vs content-asserted)

Media introduces a time text rarely had: **capture/recording time** (when the bytes were made). Three
times must be kept distinct, and only one is new:

| time | source | example | role in ugm |
|---|---|---|---|
| **content-asserted** | a date *in the content* (OCR'd "as of 2025-03-31"; spoken "last quarter") | slide labeled "Headcount as of Q1 2025" | **D41 unchanged** — extracted in-call, **grounded by window-membership** (date verbatim-exists in the OCR/transcript), seeds `claim_valid_*` |
| **capture / recording** | EXIF `DateTimeOriginal`, container/stream metadata, screen-rec clock | photo shot 2019, ingested 2026; the dashboard render time | **NEW** — immutable **E0 evidence metadata** (`captured_at`); seeds depicted-time *default* |
| **transaction** | when *we* ingested | the 2019 photo's `ingested_at` = 2026 | already exists (D3/D43); **capture is NOT this** |

**The precedence rule (refines D41, no new authority):**

```
content-asserted grounded date (D41)   >   capture time (EXIF/container)   >   ingestion time
   "Headcount as of Q1 2025"                 captured_at = 2025-10-02            last resort
```

- **Capture time seeds depicted/valid-time when the content asserts no date.** A screenshot *depicts the
  state at the moment it was captured* — so for "the dashboard shows headcount 600" with no on-screen
  "as of", `valid_from = captured_at`. This is the exact media analogue of how a text document's **header
  date** resolves "now"/"current" during decontextualization (E2 §3.1). For media, the header date *is*
  the capture time.
- **Content-asserted dates override capture (D41 unchanged).** If the dashboard is labeled "as of
  2025-03-31", that grounded date wins — capture time is only the fallback prior.
- **Capture time is untrusted and lower-precedence.** EXIF is editable/strippable; a re-screenshotted or
  forwarded asset loses or corrupts it; a screen-recording clock may be the recording machine's wrong
  time. So it is stored as `captured_at` + `capture_precision` (exif-second … filesystem-day … none) +
  `capture_source` {exif|container|filesystem|none} and is a **best-effort seed**, explicitly weaker than
  any verbatim-in-content date — a spoofed "2019" EXIF can never override an OCR'd "2024" in the frame.

**Why this is not a third validity authority (D41's three properties hold).** Capture time is (1)
**immutable** (no UPDATE/invalidation), (2) **many-valued by document** (every asset has its own; the
signature of *evidence*), (3) **no fact-identity** (keyed to the document/claim, never addressable as
"the validity of fact F"). It *feeds* the asserted window the way the header date does; the **adjudicated,
current-belief** window still lives only on relations/observations (D3/D6/D43). D41 is refined in wording
(now sourced from EXIF/container, not only from in-text dates), not in substance.

**EXIF beyond the timestamp is PII, not validity.** GPS coordinates and device serials (M6) are stripped
at the redaction sub-worker and are **not auto-promoted to observations** (an EXIF-GPS "Acme is located
in …" inference is an unconsented locational inference — a non-goal unless a deployment opts in). Only
`captured_at` is durably retained as time evidence.

### 2.5 ENTITY RESOLUTION from media — text-mediated only

**Recommendation: all identity is resolved from text the media yields; visual content contributes
*candidate name strings*, never identities.** Sources, all flowing into the existing T0–T4 cascade
(D17) unchanged:

- **OCR names** — slide titles, name tags, lower-thirds, captions, logos→a name string ("Acme").
- **Transcript names** — "Alice, can you…", self-introductions.
- **Speaker labels** — pyannote's *relative* `SPEAKER_00`, mapped to an entity **only via co-occurring
  text** (the transcript addresses them by name, or a name tag is OCR'd in their frame). The label gives
  the **attribution** "X" in D32's "*X said Y* entails *X said Y*, not *Y*" — diarization is how a
  spoken claim becomes attributed, not asserted as ground truth.

A name OCR'd from a slide is just a string: it blocks (T1 pg_trgm), phonetic (T2), embeds (T3),
LLM-adjudicates (T4) like any mention. **No new resolution machinery, no second entity space.**

**Visual entity linking is rejected — and it collapses into the text path anyway:**

| candidate | verdict | rationale |
|---|---|---|
| **face recognition** (who is this person) | **deliberate non-goal** | = "processing for unique identification" → GDPR Art. 9 special category; **EU AI-Act *prohibited*** untargeted-database pattern; **BIPA** face-geometry, private right of action $1k/$5k (M6). Builds a *second, biometric* identity authority next to the registry — the exact drift D6/D20 reject. |
| **cross-file voiceprints** (same speaker across videos) | **deliberate non-goal** | pyannote speaker embeddings are biometric templates; kept **transient** inside the diarize worker, **never** a durable matchable gallery (M6 R2). |
| **logo / product visual ID** (not biometric) | **subsumed, not built as a subsystem** | correct shape: the tagger **emits a text label** ("Acme") into the OCR/caption stream → resolves via T0–T4. Writing `entity_id`s from a visual classifier would create a second resolution path that can disagree with text — forbidden by the one-cascade invariant (D17). |
| **EXIF-GPS → entity location** | **non-goal (default)** | unconsented locational inference (M6); opt-in per deployment only. |

So "visual entity linking" is **not a missing feature** — it reduces to "the VLM/OCR emits a name, the
one cascade resolves it." That is a *simplification* (CLAUDE.md), correct at any scale, not a deferral.
No biometric template is ever persisted as durable matchable state — a **hard invariant**.

**Recall gap vs non-goal (state explicitly):**

- **Deliberate non-goals (designed out, with rationale):** biometric face/voice identity; a cross-file
  face/voice gallery; auto-promoting EXIF-GPS to facts. Refused at *any* scale on privacy/legal +
  one-authority grounds.
- **Genuine recall gaps (acknowledged, measurable, not designed out):**
  - **A person on camera who is never named in any text** (no lower-third, no OCR tag, not addressed by
    name) is **unresolved** — there is no name string to feed T0–T4. This is the *visual twin of the
    cross-document coref gap* (questions.md #22, D19). The only sanctioned remedy is **opt-in,
    consent-gated speaker/face enrolment per deployment** (M6 R2 documented alternative) — never default.
  - **A logo/product shown but never named** is similarly unresolved; lower stakes (non-biometric), so
    the measured-demand upgrade is a non-biometric visual tagger that **emits a text label** into the
    OCR/caption stream (then T0–T4 resolves it) — still text-mediated, still one authority.

---

## 3. How it preserves ugm invariants

- **D2 (claims ≠ relations; `evidence_count`).** Five keyframes showing "Headcount 600" + the speaker
  saying it collapse to **one** observation with multiple evidence rows; corpus redundancy across media
  is free. ✓
- **D3 / D43 (supersession on relations/observations, never claims).** Media claims are immutable
  evidence; the window closes on the observation/relation. A 2025 video superseding a 2024 filing's
  headcount is one observation cap. ✓
- **D6 (one belief home).** No parallel "visual fact" store; media → text pipeline → the same
  claims/observations. Visual retrieval (F4, P1/Lance) carries **no belief**. ✓
- **D7 / D33 (versioned, replay-from-storage).** ASR/OCR/scene-detect/VLM-caption are model-derived →
  each versioned (`asr_version`, `ocr_version`, `scene_version`, `caption_version`) and replayed, never
  re-derived nondeterministically; Selection drops/edits on media-text land in the same
  `claim_extraction_decisions` ledger (D33). ✓
- **D12 (per-doc chain, `content_hash` idempotency).** A media file is a document; same chain, same key. ✓
- **D18 / D44 (graph holds only entities; observations never project; time is never a node).**
  Observations from media never reach P2; `captured_at` is metadata, never a Date-node. ✓
- **D20 (no biometric / 3rd-party authority).** Resolution is text-mediated; no face/voice gallery. ✓
- **D25 / D31–D35 (Claimify; no pre-extraction value gate).** Same E2 over a richer bundle; **every
  scene is extracted** (no media value-gate); Selection drops a vacuous caption as generic exactly as it
  drops text boilerplate; quantity/date never-drop classes (D35) protect OCR'd numbers. ✓
- **D32 (grounding, dual-field + offsets).** Generalized to a polymorphic locator (shared with F1–F4);
  verbatim media-text uses anchor + window-membership as written; captions use entailment + provenance +
  audit. ✓ (refined — §5)
- **D41 (asserted-validity).** Content-asserted dates unchanged; capture-time added as an immutable,
  many-valued, fact-identity-free metadata seed — D41's non-authority properties intact. ✓ (refined — §5)
- **D42 (origin at ingest, for confidence math).** Extended: the existing external/self stamp gains the
  verbatim-media-text vs model-asserted-caption discrimination, so `evidence_count`/K3 never count a VLM
  caption as independent corroboration — the natural home for the M5 caption-quarantine. ✓ (refined — §5)
- **D43 (observations).** The dashboard value lands as the canonical D43 row; no schema change. ✓

---

## 4. Risks / what to measure (spikes)

1. **Value-provenance gate (the top correctness risk).** Measure how often a numeric observation comes
   from **verbatim OCR/transcript** vs a model-**read** chart value; tune the D43 adjudicator margin so a
   model-read value can never confident-supersede a text-grounded prior (ties D43 §3.4 + M1 chart
   hallucination).
2. **Capture-time reliability.** On a media golden set, measure EXIF/container presence + edit/strip
   rate; validate the precedence (content-asserted > capture > ingest) and the *depicted ≈ capture*
   default on screenshots vs old photos; fix the `capture_precision` buckets.
3. **Speaker→entity attribution.** False-attribution rate ("Alice said X" when Bob spoke) on real
   diarized video (overlap/far-field worse, M3) — attribution errors poison "X said Y" claims.
4. **Bundle cost/quality per media-class.** The video bundle (transcript window + caption + OCR +
   neighbours + scene path) is token-heavy; measure extraction quality vs bundle size; define a leaner
   bundle for low-value scenes (mirrors the E2 short-source spike, e2_e3 §7.4).
5. **Selection on captions.** Confirm Selection DROPs vacuous captions ("a slide is shown") while
   KEEPing OCR'd facts; per-fact canaries (D35) on planted on-screen quantities.
6. **Unnamed-on-screen recall-gap size.** Quantify how many salient entities appear only visually before
   deciding whether opt-in enrolment is ever worth building.
7. **Observation volume from dense media.** A dashboard-heavy screen recording can emit hundreds of value
   observations per minute; size `observations`/`observation_evidence` against media volume (D43 §7.4);
   rely on evidence-collapse to dedup the same value across frames.

---

## 5. Proposed decisions (continuing from D44) + design-doc deltas

**D45 — Media-derived facts use the unchanged E2/E3/D41/D43 belief layer over a *polymorphic context
bundle*.** Claims, relations, observations, supersession, `evidence_count`, and T0–T4 are media-agnostic;
the only structural change is the D32 locator generalization (owned by F1/F2). The E2 bundle (D31) gains
media-typed elements — transcript window (the "chunk"), scene-tree path, scene caption, OCR block,
neighbour segments, mapped speaker labels — with the extractor mechanism unchanged. *One extractor, one
belief home.*

**D46 — Grounding routes by bundle-element origin (refines D32; extends D42).** Verbatim media-text
(OCR/ASR) is first-class source: anchor (L1) + window-membership (L2) as written, with a media locator.
VLM-generated descriptions are model assertions: cited in `added_context[]`, grounded by entailment (L3)
+ locator provenance + sampled audit (L4), **origin-stamped** so confidence math never treats a caption
as independent corroboration. Observation values inherit it: an OCR/transcript-verbatim value may
supersede; a model-**read** value may not confident-supersede (it coexists/flags).

**D47 — Capture time is immutable E0 evidence metadata that seeds depicted/valid-time as a
lower-precedence default; it is neither transaction-time nor a new validity authority (refines D41).**
Precedence: *content-asserted grounded date (D41)* > *capture time (`captured_at` + `capture_precision`
+ `capture_source`)* > *ingestion time*. Capture time is untrusted (spoofable/missing/wrong),
many-valued-by-document, immutable, fact-identity-free — D41's three non-authority properties hold. Other
EXIF (GPS, device) is PII, stripped at redaction (M6), never auto-promoted to observations.

**D48 — Entity resolution from media is text-mediated only; visual biometric identity linking is a
non-goal.** Names from OCR/transcript and mapped relative speaker labels resolve via T0–T4 (D17)
unchanged. Faces / cross-file voiceprints as identity are refused (D20 + GDPR Art. 9 + EU AI-Act + BIPA;
M6); no durable biometric template gallery (transient compute only). Visual content may only *emit
candidate name strings* into the OCR/caption stream (then resolved by the one cascade), never assign
`entity_id`s. **Acknowledged recall gap:** entities that appear only on screen and are never named in any
text are unresolved — the visual twin of the cross-document coref gap (questions.md #22); the only
sanctioned remedy is opt-in, consent-gated enrolment per deployment (documented alternative, not default).

**Design-doc deltas this implies:**

- `e2_e3_claims_relations_design.md` §3.1 — add the polymorphic bundle (media-typed elements); §3.3 —
  the grounding-by-origin split (verbatim media-text vs model caption).
- `observations_design.md` §2/§3 — note the value-provenance (OCR-verbatim vs model-read) origin stamp on
  evidence and its effect on the §3.4 supersede margin.
- `decisions.md` — add D45–D48; append refinement notes to D41 (capture-time precedence) and D42
  (caption-origin discrimination).
- `e0_files_design.md` §2 — `documents` gains `captured_at` / `capture_precision` / `capture_source`;
  redaction strips other EXIF (cross-ref the privacy design-fit doc / M6).
- `decisions.md` D32 — record the polymorphic-locator generalization as a cross-cutting change owned by
  F1/F2 and consumed here.
- `questions.md` #22 — add "visual-only entities (on camera, never named in text)" as a named sibling of
  the cross-document coref recall hole.
