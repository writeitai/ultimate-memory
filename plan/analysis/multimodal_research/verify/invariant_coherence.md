# Invariant + Coherence Critic — multimodal `design_fit/` (F1–F6)

**Role.** Adversarial fact-checker / design critic over
`_feature_planning/multimodal/design_fit/{F1..F6}.md`, checked against `decisions.md` (D1–D44),
the research base (`web_research/M1–M6`, `repo_findings/*`), and external primary sources.
Skeptical default: a claim is "confirmed" only with a traceable source.

**Overall verdict.** The *core architectural move* is sound and genuinely invariant-preserving:
belief = text on the E pipeline (transcode-to-text), native media = a P1 retrieval projection with
zero authority, one polymorphic grounding locator. D6, D37, D44, and (with caveats) D2/D7/D25 hold.
But the six docs were drafted **independently and never reconciled**: they collide on decision
numbers, specify the *same* schema three incompatible ways, and contain four load-bearing overclaims
— one of which (Tier-B storage) is contradicted by the very research it cites and by the vendor docs.
The design is not yet coherent enough to mint decisions from; it needs a synthesis pass.

Legend: **[V]** verified against a primary source / decisions.md; **[I]** inference; **[?]** unverifiable.

---

## invariant-violations[]

Format: invariant → verdict → evidence.

1. **D32 (grounding: "every claim traces to an exact source") → PARTIALLY PRESERVED; the
   crown-jewel guarantee is genuinely *weakened* for description-class claims, and F1 overclaims it
   as *improved*.** [V]
   - *Traceability* (provenance) is preserved and even extended: a VLM-description claim carries a
     real, in-bounds region/timecode (F3 L0 + L2a). You can always draw the box.
   - *Per-claim deterministic faithfulness* is **not** preserved for VLM captions. F3 §2.3 is honest:
     the substring anchor "fixes provenance-to-this-caption only, NOT faithfulness"; the faithfulness
     guarantee moves to in-call entailment (L3, nondeterministic) + an **offline sampled audit
     (L4, not per-claim)**. For the text pipeline, D32 rung-1 (anchor) is a *deterministic per-claim*
     check; for descriptions that determinism is gone. So D32's strong promise holds in the **weak
     (where) sense, not the strong (is-it-true-to-source) sense** for the description class.
   - **Contradiction inside the corpus:** F1 §1.1/§2.2 claims "grounding/auditability *improves* with
     media rather than degrading." F3 §1.4/§2.3 correctly states the opposite for fidelity: "Verbatim
     is always w.r.t. the converted text, never the pixels/signal… signal fidelity is a separate,
     measured axis (D32 L4), never asserted by the anchor." F3 is right; **F1 is an overclaim.** This
     is the single most important nuance for the auditability story.

2. **D12/D36 (per-document trigger chain; sub-worker idempotency) → STRAINED + UNDER-SPECIFIED, not
   formally broken.** [V/I]
   - The video cascade is 10 stages (F2 §2.3: demux→shot-detect→ASR→keyframe→OCR→redact→scene-merge→
     **VLM-caption**→roll-up→escalation) but D36's idempotency grain is the **sub-worker**
     (`content_hash + its own version`), and F1/F2/F6 stuff all ten stages inside the single `convert`
     (+`redact`) sub-worker. The docs simultaneously require **per-stage** versioning + replay
     (`asr_version`, `vlm_caption_version`, …). That is **stage-level checkpoint/idempotency**, which
     D12/D36 do not provide. The grain mismatch is asserted away, not designed.
   - D12's execution envelope ("Cloud Tasks; max 2 retries + dead-letter") was tuned for fast text
     `convert`. A multi-hour video (hour-long ASR + hundreds of shot captions) can exceed task
     dispatch deadlines; a late-stage (stage-8 VLM) failure that dead-letters after stage-3 ASR
     succeeded either loses the whole video or re-runs ASR. **No doc addresses timeout, long-running
     execution, or stage-resume.** This is a real gap, not a violation — but it must be resolved
     before "the media cascade is just another `convert` sub-worker (D12/D36)" (F1 §3) is true.

3. **D2 (evidence_count / dedup) → PRESERVED at mechanism, UNDER-SPECIFIED at two seams.** [V/I]
   - Same fact via chart and via prose collapses to one observation/relation with `evidence_count`
     incrementing, because both reach E2 as text (F1 §2.6, F5 §3). Correct, and consistent with D2.
   - **Seam A — cross-frame value dedup.** F5 §3 claims "five keyframes showing Headcount 600 + the
     speaker collapse to one observation." But five keyframes captioned by the *same* VLM are not five
     independent evidences (D42/F3 §2.4: "N captions of the same frame by the same model are not N
     evidence rows"). The collapse mechanism (pHash dedup at E0 + evidence-collapse at E3) is named as
     a **spike (F5 #7)**, not a designed guarantee — so `evidence_count` *can* be inflated by
     frame-redundancy until that is built.
   - **Seam B — raw count vs origin-discount.** The docs keep `evidence_count` raw and push the
     "model caption ≠ independent corroboration" discount to confidence math (consistent with D42).
     Defensible, but it is **stated twice and reconciled nowhere**: synthesis must say explicitly that
     `evidence_count` stays raw and the discount lives in K3/confidence, or two docs will be read as
     decrementing the count.

4. **D25 (no pre-extraction value gate; "process this frame?" smuggled gate) → PRESERVED in letter;
   one overclaim + one wording risk.** [V]
   - The strongest defense (F6 §2.1) is sound: shot detection + pHash dedup = *deterministic
     structural reduction* (the media analogue of content-hash idempotency), **not** a learned
     salience gate; **every scene reaches E2** via the linearized markdown; junk control stays at E2
     Selection. The DESCRIBE rung fires by deterministic **layout category** (picture/chart vs text),
     and the frontier rung is **escalation-up** (D4), not skip-down. None is a value gate. ✓
   - **Recall-hole nuance (deterministic, not learned):** captioning one keyframe per shot can miss
     within-shot visual/text change (a gradual reveal, mid-shot on-screen text). This is the
     *deterministic* cousin of the value-gate recall hole. It is acknowledged only as a threshold
     spike (F2 #6, F6 #5) yet sold as **"strictly better at any scale"** (F2 D50, F6 §2.5) — an
     overclaim (see overclaims #3).
   - **Wording risk:** F2 §2.4 says the extended `role` enum lets "E2 Selection drop low-value roles
     (credits, onscreen_text)." This is only D25-safe if it is `role`-fed-into-the-E2-call dropping at
     **proposition grain** (D31/D25's explicit rule), *not* a pre-E2 section skip. The phrase "drop
     low-value roles" reads dangerously close to a binary pre-skip; synthesis must pin it to in-call.

5. **D6 (one belief home / graph holds no authority) → PRESERVED.** [V] Beliefs are text
   claims/relations/observations in Postgres; P1 visual sub-index returns a *locator*, never a belief,
   holds no authority, is rebuildable, and LadybugDB stays embedding-free (F4 §3; consistent with
   D6/D8/D44). Residual watch-item, not a violation: F4 stores VLM `caption` in `p1_visual` as a BM25
   bridge — nothing may read that column as belief (F4 is careful; keep it that way).

6. **D7 (rebuildability with versioned model-derived artifacts) → PRESERVED in principle; CITATION is
   imprecise and the replay discipline is asserted beyond where it is written.** [V]
   - D7 is specifically the **P2 graph rebuild** (Postgres→Parquet→snapshot). The "every
     nondeterministic model output is versioned and **replayed from storage, never re-derived**"
     discipline the docs lean on is actually **D33** (E2-extraction-specific) + **D37** (artifacts in
     GCS) + **D1**. All six docs shorthand it as "D7/D33."
   - More substantively: D33's replay rule is written for *E2 extraction*. Extending it to OCR/ASR/VLM
     `convert`-stage models is the right move but is **new** — synthesis must state that D33's
     replay-from-storage is generalized to E0 media stages (or that D38's `converter_version` +
     D37 artifact persistence already cover it). Today the docs imply D33 already says this; it does
     not.

7. **D37 (storage split) → PRESERVED.** [V] Raw→raw bucket (cold/immutable/never-mounted),
   markdown+conversion.json+mediaindex.json+keyframes→artifacts bucket, Postgres holds only
   metadata/section-index/version-stamps/privacy-flags/key-IDs; bodies (transcript/captions) never in
   Postgres (F2 §2.4, F6 §2.2). Faithful to D37; Archive/Coldline class + `dek_id` are clean
   extensions. No violation.

---

## contradictions[]

**C0 — Decision-number collision (blocking, mechanical, corpus-wide).** [V]
All six docs independently number from D44+1, so the *same* number encodes *different* decisions:

| Doc | Proposes | D45 means… |
|---|---|---|
| F1 | D45–D49 | core transcode-to-text choice |
| F2 | D45–D50 | `convert()` contract `{markdown,blocks,structure,manifest}` |
| F3 | D45–D48 | polymorphic media locator |
| F4 | D45–D46 | P1 two-tier visual sub-index |
| F5 | D45–D48 | media-derived facts over polymorphic bundle |
| F6 | D45–D49 | media `convert()` cost cascade |

D45 is claimed six times, D46 six times, D47/D48 five times each — for non-identical content.
This is not just renumbering: several docs cover the **same surface** (the locator, the convert
cascade, the MediaIndex, non-goals, deletion) with **different details** (below), so synthesis must
both mint one non-overlapping block *and* pick one spec per surface.

**C1 — The polymorphic locator is specified three incompatible ways.** [V] This is the load-bearing
schema and it does not agree across F1/F2/F3:
- *Coordinate-space strategy:* F1 §2.2 = **store native space per locator, normalize on read**
  (`coord_space ∈ {pixel@dpi, frac, norm0-1000}`). F3 §2.2 = **normalize at the boundary to ONE
  canonical 0–1000 top-left space**, keep the original only in `producer` for audit. F2 §2.1 keeps a
  `coord_space` field but hardcodes it to `"norm_0_1000"`. F1 and F3 are **mutually exclusive**
  storage models.
- *Field shape:* F1 treats char-offset as the **text arm of one polymorphic locator** (single field).
  F2/F3 carry a **separate, always-present** `md_span`/`markdown_span` **plus** an additive
  `native_locator`. Different table shape.
- *Canonical home:* F2 §2.4 puts the locator on **`document_sections`**; F3 §5 puts it on
  **`claims`/`relation_evidence`/`observation_evidence`** (column-set or child table); F4 §2.4 puts
  scalar copies in **P1/Lance**. Complementary in principle, but no doc says which is canonical or
  whether it is columns vs a child table.
- *bbox type:* array `[l,t,r,b]` (F1/F2) vs object `{l,t,r,b}` (F3). Minor but real.

**C2 — "Auditability improves" (F1) vs "fidelity is a separate, *degraded*, sampled axis" (F3).**
[V] See invariant-violation #1. The two docs make opposite epistemic claims about what media does to
D32. F3 is correct.

**C3 — MediaIndex vs generalized `document_sections`.** [V] F1 §2.4 introduces **MediaIndex as a D39
*sibling*** (a separate scene-tree sidecar). F2 §2.4 instead **generalizes `document_sections` itself**
into a polymorphic structure tree with a `locator_kind` discriminator *and* keeps a `mediaindex.json`
sidecar. Whether the media structure lives in a generalized `document_sections` or a parallel
MediaIndex (or both, with one canonical) is unresolved.

**C4 — Czech ASR path.** [V] F1 §2.3 asserts "Czech alignment ships by default" with WhisperX,
implying WhisperX is sufficient for Czech. F2 stage-3 + risk #5 says you must **swap to NeMo
Canary-1B-v2** for Czech accuracy (7.86% vs 11.33% WER). WhisperX provides Czech *alignment*
(wav2vec2) but not necessarily competitive *transcription* — F1 conflates the two.

**C5 — Non-goals / deletion appear in multiple docs as different decisions.** [V] "No parallel visual
belief track," "no biometric templates," "no dense per-frame captioning," and the deletion cascade
are stated as **D45/D49/D50 in F1, D50 in F2, D48/D49 in F6** with overlapping-but-not-identical
scope. Must be unified into one non-goals decision + one deletion decision.

---

## overclaims[] (vs the cited research / primary sources)

**O1 — Tier-B "≈5–6 KB/page, single-vector-comparable storage in Lance." FALSE for Lance.** [V]
F1 §2.5 ("pool factor ~3 → −67% vectors @ 97.8% … + fp16") and F4 §2.2 ("landing Tier B near ~5–6
KB/page, single-vector-comparable storage") inherit M4 §4.1's own arithmetic slip. The ~5–6 KB figure
**requires binary quantization** (16 bytes/vector: 343 × 16 ≈ 5.5 KB). But **LanceDB multivector is
cosine-only, float16/32/64 — no binary/Hamming** (M4 §2.4 [V]; confirmed at
<https://docs.lancedb.com/search/multivector-search> and
<https://lancedb.com/docs/concepts/search/multivector-search/>, June 2026). With the Lance-available
lever (pool-3 + fp16): 343 vectors × 128 dim × 2 bytes ≈ **~86 KB/page ≈ ~21× a 4 KB single-vector**,
**not** "single-vector-comparable." Both F1 and F4 even *acknowledge* Lance is cosine-only two
paragraphs away, then quote the binary-achievable number as the Lance budget. This is load-bearing:
it changes the Gate-2 cost/benefit and the "one vector estate" economics.

**O2 — "Grounding/auditability *improves* with media."** [V] F1 §1.1/§2.2. Provenance traceability
improves; per-claim faithfulness verification *degrades* for the description class (from deterministic
per-claim anchor to sampled offline audit). F3 says so explicitly. Overclaim; adopt F3's framing.

**O3 — "Shot-bounded selective captioning is strictly better at any scale (+8–10 pts at small frame
budgets, M2 §4.5)." MIS-CITED + overstated.** [V] M2 §2.1's +8–10 pts is for **learned adaptive
keyframe selection vs uniform sampling** (arXiv:2502.21271), **not** for deterministic PySceneDetect
shot-boundary sampling — a different method. The benchmark does **not** validate shot-bounded
captioning specifically. And "strictly better at any scale" ignores the within-shot recall hole
(invariant-violation #4). The **cost** argument (budget = shot count, not duration) is sound and well
supported; the **quality-superiority** claim is overstated and attributed to the wrong result.

**O4 — "$2.7M re-paid every query vs tens of thousands once."** [I, hedged in M2; presented as fact in
F6] F6 §1/§2.1. M2 tags every 1M-hour figure **[I] medium-confidence**, explicitly "ignore prompt/
output overhead, batching discounts, and **context caching** (which would further cut re-query cost on
native ingestion)" and flags caching for video as "probable, would change the (a) calculus,
**unverified**." Taken literally, "$2.7M every query" implies re-ingesting all 1M video-hours on every
query, which no one does. The **direction** (native = per-query, pipeline = amortized pay-once) is
correct and decisive; the **specific number** is a hedged extrapolation dressed as a hard result.
(The >200k-token price doubling underneath it — $1.25→$2.50/1M input — *is* verified:
<https://ai.google.dev/gemini-api/docs/pricing>, June 2026.)

**Correctly hedged (NOT overclaimed), credit where due:**
- "Grounded captioning reduces hallucination ~25–28%" is flagged by F1 (#1) and F3 (#5) as
  task-dependent / measure-don't-assume — properly handled, not asserted. [V]
- ColPali nDCG@5 **81.3 vs 67.0**, ColQwen ViDoRe-v1 ~89–91, Voyage +26.5%/+41.4% vs CLIP-L, pool-3
  → −67% @ 97.8%, ~130× single-vector storage for a naive ColPali index — all faithfully carried from
  M4, which tags them [V] with primary sources. F4's numbers match its research. [V]
- WhisperX ~70× real-time, ~$0.005–0.05/audio-hr; Gemini 1 fps / 258·66 tok-frame; pipeline <$50k once —
  faithfully carried from M2 (which tags the cost extrapolations [I]). [V/I]

---

## top-5 things the synthesis MUST resolve

1. **Mint one non-overlapping decision block and pick one spec per shared surface (C0–C5).** Six docs
   claim D45+ for different content and triple-specify the locator, the convert cascade, the
   MediaIndex, non-goals, and deletion. Until this is done, no decision can be added to `decisions.md`
   without a collision. This is the gating coherence task.

2. **Choose ONE polymorphic-locator schema (C1).** Decide: (a) normalize-at-boundary to a single
   0–1000 top-left space (F3) vs store-native+normalize-on-read (F1); (b) char-offset as the text arm
   of one field (F1) vs a separate always-present `md_span` + additive `native_locator` (F2/F3);
   (c) canonical home — `document_sections` vs `claims`/evidence rows vs P1 scalar columns, and
   columns-vs-child-table; (d) bbox array vs object. This is the load-bearing schema for the whole
   feature.

3. **Adopt F3's honest grounding account and drop F1's "auditability improves" (invariant #1, O2,
   C2).** State plainly that for VLM-description claims, D32's deterministic per-claim anchor does NOT
   establish faithfulness — only provenance-to-region — and faithfulness rides in-call entailment +
   an **offline sampled audit (L4)**. Make the description-class L4 sample rate a first-class,
   golden-set-measured safety parameter, not a footnote. The auditability "crown jewel" is genuinely
   softened for media; say so.

4. **Specify the media execution model against D12/D36 (invariant #2).** Decide whether the 10 media
   stages become first-class sub-workers (amending D36's 4-stage chain) or stay inside `convert` with
   explicit stage-level checkpoint/idempotency, and define the long-running execution + retry envelope
   for multi-hour video (Cloud Tasks' 2-retry/dead-letter model dead-letters a whole video on a
   late-stage failure). Also explicitly extend D33's replay-from-storage discipline to E0 media stages
   (today it is E2-only).

5. **Re-decide the Tier-B storage budget with the real Lance number (O1).** Lance multivector is
   cosine-only → no binary quant → pool-3 + fp16 ≈ **~86 KB/page ≈ ~20× single-vector**, not the
   claimed ~5–6 KB "comparable." Either accept ~20× on the visually-rich slice (and re-justify
   Gate-2's economics) or trigger the documented hamming-capable-engine alternative — a real decision,
   not a footnote. Fix the inherited M4 arithmetic at the same time.

**Honorable mentions (not top-5 but flag in synthesis):** cross-frame VLM-value dedup + the
`evidence_count`-vs-origin-discount seam (invariant #3, must be a designed guarantee, not a spike);
the "drop low-value roles" wording must be pinned to in-call proposition-grain Selection, never a
pre-E2 section skip (invariant #4); the Czech ASR path (C4); and the "$2.7M/query" framing should be
softened to the verified, caching-aware direction (O4).
