# C4 — Claim-level SELECTION (the "do not extract non-relevant content" half)

Scope: the sentence/proposition-grain KEEP-vs-DROP decision — *which* propositions become claims, and *which* are discarded as opinion / hypothetical / question / instruction / generic-truism / boilerplate / meta / pure-example. How Claimify-Selection and VeriScore decide **verifiability** (verbatim quotes, file:line). How this **composes** with the chunk-level E1.5 value gate (D25–D30) so the two don't double-filter and a kept section isn't then fully drained. Recall risk + safeguards. Concludes with a claim-level selection design + recall envelope for ugm and a concrete contrast against the naive single-chunk baseline that E2 must avoid.

Citations are `file:line` for the public comparison repos / prompts, `paper_text.md:line` for the Claimify paper. VERIFIED = read in source; INFERENCE = reasoned, flagged.

---

## 1. Key findings

- **Selection is a real, separable, measured stage — and it is the single highest-value part of Claimify.** Ablating Selection causes the *largest* quality drop of any component: element-level coverage macro-F1 falls from **83.7 → 54.4** when Selection is removed, and even "Selection-as-detector" (decide presence, don't rewrite mixed sentences) only recovers to 74.7 (`paper_text.md:280-281`, Table 4). "Removing the Selection stage caused the largest performance drop, indicating the benefit of checking verifiability prior to extracting claims" (`paper_text.md:257`). This is the empirical case for adding a claim-level gate at all.

- **The KEEP test is precise and lexical, not "importance/check-worthiness".** Claimify and VeriScore both gate on **verifiability** (objectively true/false against evidence), *explicitly rejecting* check-worthiness/salience as subjective (`paper_text.md:263` "we agree ... that check-worthiness is subjective"). Claimify's DROP classes are enumerated verbatim: introductions, conclusions, broad/generic statements, opinions, interpretations, speculation, statements about a lack of information (`prompts.py:13-22`, `paper_text.md:478-483`). VeriScore's DROP classes are also verbatim: "Any story, personal experiences, hypotheticals (e.g., 'would be' or subjunctive), subjective statements (e.g., opinions), suggestions, advice, instructions, and other such content should not be included" (`extraction_qa_template.txt:1`). These two lists are the concrete KEEP/DROP vocabulary ugm should adopt.

- **Two deliberate decouplings make Selection safe to run as a narrow gate.** Claimify's Selection prompt states three "does NOT matter" rules: truth value, **relevance to the question**, and ambiguity are all explicitly out of scope for the verifiability decision (`prompts.py:4-6`). So Selection (verifiability) is *orthogonal* to a relevance filter (SAFE) and to disambiguation (Claimify stage 3). This is the clean seam ugm needs: **E1.5 = chunk-level salience/dedup/novelty; claim-level Selection = per-proposition verifiability; neither is the other.** They filter on different axes and at different grains, so they do not double-count.

- **A mixed sentence is rewritten, not dropped — this is the recall-preserving core of Selection.** Selection's option (2) keeps the verifiable span and strips the unverifiable remainder ("The explosion can spin the neutron star to **mind blowing speeds** - up to 600 rotations per second" → "...to speeds up to 600 rotations per second", `paper_text.md:481`). Whole-sentence DROP (option 1) only fires when **nothing** is verifiable. This rewrite-not-drop behavior is the claim-grain analog of E1.5's defer-don't-DROP (D29), and it is exactly what the naive single-chunk baseline lacks.

---

## 2. Evidence & detail

### 2.1 The naive single-chunk baseline has NO claim-level selection — only a quote-grounding gate

The extract-everything baseline that ugm's E2 must avoid is best understood as a FActScore-shaped extractor whose entire system prompt amounts to:

> "Extract **all** atomic project-memory claims from the provided chunk. Trust the chunk boundary exactly as given. Do not split or merge chunks. Return only claims that are directly supported by an exact quote copied from this chunk. Do not infer facts that are not stated in the chunk."

This is a **decompose-everything** prompt (FActScore-class, `claimify_impls.md:284-301`): "extract all". Its only filter is *grounding* — every claim must carry a verbatim evidence-quote field that is later checked to be a verbatim substring of the chunk (normalize = whitespace-collapse + casefold) via the verbatim-substring grounding gate. That filter answers "is this claim copied from the text?", **not** "should this proposition be a claim at all?". An opinion, an instruction, a hypothetical, or a section intro that is quoted verbatim passes grounding and becomes a durable claim record. There is no verifiability/opinion/boilerplate gate anywhere in the per-chunk extraction orchestration. The extract-everything baseline also runs **one chunk at a time with no neighbors**, so even the "intro vs fact" judgment that Selection makes from surrounding sentences is impossible under that design.

INFERENCE: claim-kind labels (FACT, DECISION, POLICY, PREFERENCE, PROCEDURE, INCIDENT, RELATIONSHIP, OBSERVATION) are *not* a selection gate — they label kept claims; nothing forbids an OBSERVATION that is pure opinion. The KEEP/DROP decision has no home in a decompose-everything schema.

### 2.2 Claimify Selection — the verbatim KEEP/DROP rules (VERIFIED)

System prompt `claimify_deshwalmahesh/src/prompts.py:1-46`. The decision is a 3-way: (1) "Does NOT contain a specific and verifiable proposition" → DROP; (2) rewrite to retain only verifiable info; (3) "remains unchanged" (already fully verifiable) (`prompts.py:38-46`, `paper_text.md:124`).

KEEP test (`prompts.py:1`): the sentence "contains at least one **specific and verifiable** proposition". Decoupling rules that scope the test narrowly:
- `prompts.py:3` — "If the sentence is about a **lack of information** ... it does NOT contain a specific and verifiable proposition." (never-extract class)
- `prompts.py:4` — "It does NOT matter whether the proposition is **true or false**."
- `prompts.py:5` — "It does NOT matter whether the proposition is **relevant to the question**." (← verifiability ≠ relevance; the seam vs SAFE)
- `prompts.py:6` — "It does NOT matter whether the proposition contains **ambiguous terms** ... Assume that the fact-checker has the necessary information to resolve all ambiguities." (← verifiability ≠ disambiguation; ambiguity is stage 3's job)
- `prompts.py:7` — "You will NOT consider whether a sentence contains a **citation**."

Context-dependent DROP classes — **intros and conclusions require neighbors to detect** (`prompts.py:9-14`, `paper_text.md:480`):
- intro: "Guests interviewed on the podcast suggest several strategies..." followed by examples → "is an introduction and does NOT contain a specific and verifiable proposition" (`prompts.py:13`)
- conclusion: "In summary, a wide range of topics ... are covered in the dataset" preceded by the details → "is a conclusion and does NOT contain a specific and verifiable proposition" (`prompts.py:14`)

Pure DROP examples (no neighbors needed) (`prompts.py:16-22`, `paper_text.md:478-483`): "Technological progress should be inclusive"; "Leveraging advanced technologies is essential for maximizing productivity"; "AI could lead to advancements in healthcare" (speculative "could", `paper_text.md:478`); "This could revolutionize transplantation..." (DROP, reason: "uses the word 'could,' indicating a potential or speculative outcome", `paper_text.md:478`); "When you reach your destination, try to use public transportation..." (DROP, reason: "is a recommendation ... advising a course of action rather than stating a fact", `paper_text.md:479` — an **instruction**); "There have been many archaeological discoveries..." (DROP, reason: "broad and general ... serves as an introduction", `paper_text.md:480`).

REWRITE examples (mixed → keep verifiable span) (`prompts.py:24-37`, `paper_text.md:481-483`): "Smith's advocacy for renewable energy is **crucial in addressing these challenges**" → "Smith advocates for renewable energy"; "...mind blowing speeds - up to 600 rotations per second" → "...speeds up to 600 rotations per second" ("'mind blowing speeds' is subjective, but the specific claim of 'up to 600 rotations per second' is verifiable", `paper_text.md:481`); "...may not survive much longer without conservation efforts" → drops the speculative tail, keeps "Some of these organisms are threatened by human activities, such as logging, mining, grazing, and climate change" (`paper_text.md:482`).

The three impls implement this identically; claimsmcp enforces it via a Pydantic `final_submission: Literal["Contains...","Does NOT contain..."]` + `sentence_with_only_verifiable_information: str|None` (`claimify_impls.md:152-155`); claimeai uses `SelectionOutput{processed_sentence, no_verifiable_claims, remains_unchanged}` (`claimify_impls.md:219`). Voting (3 completions, min 2, temp 0.2) is used in impls #1/#3 (`claimify_impls.md:97`, `:221`).

### 2.3 VeriScore — verifiability fused into one call (VERIFIED)

VeriScore collapses classify + decompose + decontextualize into one prompt (`paper_text.md:171`). Its KEEP bar is **external-world verifiability**: "Each of these fine-grained facts should be verifiable against reliable external world knowledge (e.g., via Wikipedia)" and each fact "describing either one single event ... or single state ... with necessary time and location information" (`extraction_qa_template.txt:1`). Its DROP list (verbatim, `extraction_qa_template.txt:1`): "Any story, personal experiences, hypotheticals (e.g., 'would be' or subjunctive), subjective statements (e.g., opinions), suggestions, advice, instructions". Note the explicit carve-out so it doesn't over-drop expository prose: "Biographical, historical, scientific, and other such texts are not personal experiences or stories. You should extract verifiable facts from them." If nothing qualifies → literal "No verifiable claim." (`extraction_qa_template.txt:1`, parsed at `claim_extractor.py:183-184`).

VeriScore's worked examples are the cleanest DROP demonstrations of *instructions/advice* in the corpus: "Online search: You can search online using keywords..." → **"No verifiable claim."** (it is advice, `extraction_qa_template.txt`); "Ah yes, tomatoes, this is a big problem with tomato plants." → "No verifiable claim." (conversational meta). Entailment-wise VeriScore and Claimify are statistically tied at the top (99.2% / 99% entailed, `paper_text.md:202`, `:199`), confirming the verifiability bar is what drives precision, not the staged-vs-fused architecture.

### 2.4 The composition seam — Claimify Selection explicitly is NOT relevance, NOT salience

VERIFIED triangulation across the corpus (`claimify_impls.md:374-383`):
- **Verifiability gate** (drops opinion/advice/hypothetical): Claimify-Selection + VeriScore.
- **Relevance gate** (drops off-topic-but-verifiable): SAFE only, *after* extraction, against the question's subject (`classify_relevance.py:227-249`, `claimify_impls.md:324-329`). Default-on-failure = relevant (`:248-249`).
- **Salience / check-worthiness**: nobody at claim grain — Claimify explicitly rejects it as subjective (`paper_text.md:263`).
- **CHUNK-level value/salience**: this is ugm's E1.5 (D25), which has **no analog in any surveyed repo** — "all extract-everything" (`decisions.md:498-500`).

This is the load-bearing finding for ugm: **E1.5 (chunk salience) and claim Selection (proposition verifiability) operate on different axes and at different grains.** A section can be high-salience (KEEP at E1.5) yet contain mostly opinion (heavy claim-level DROP), and vice versa. They are not redundant; chaining them is multiplicative on *different* noise, not double-filtering on the *same* noise.

---

## 3. Confidence & gaps

- **HIGH** that Selection is a verifiability gate with the exact KEEP/DROP vocabulary above (read verbatim in 3 prompt files + the paper + Table 5 examples), and that it is the highest-leverage Claimify stage (Table 4, `paper_text.md:280-281`).
- **HIGH** that the naive single-chunk baseline performs no claim-level selection — only verbatim-quote grounding — and processes one neighbor-free chunk at a time. This is the documented FActScore-class anti-pattern E2 must improve on.
- **HIGH** that Selection and E1.5 are orthogonal axes (verifiability vs salience), each explicitly disclaiming the other's job (`prompts.py:5`, `decisions.md:485-501`, `paper_text.md:263`).
- **MEDIUM** on quantified recall risk of Selection. Claimify reports only that "Cannot be disambiguated" maxed at 5.4% and Decomposition returned nothing in 0.8% (`paper_text.md:138`, `:142`) — these bound the *stage-3* drops, not Selection's whole-sentence DROP rate. The paper gives Selection's class-level precision/recall on its own annotation set (verifiable recall 93.9% sentence / 87.6% element; **unverifiable** precision only 65.6% at element level, `paper_text.md:207`) — i.e. Selection is recall-strong on keeping verifiable content but *imperfect at cleanly excluding* unverifiable content, which for ugm is the safe direction (over-keep, not over-drop). I could NOT find a measured "verifiable fact wrongly DROPPED by Selection" rate; the 6.1% verifiable-element miss (1 − 87.6/100 ≈ 12.4% at element grain) is the closest proxy and is **not** negligible — this is the recall risk to instrument.
- **GAP / known Claimify weakness, relevant to ugm DROP classes**: list items without their preamble ("- Investing in renewable energy sources.") are genuinely ambiguous between recommendation (DROP) and stated-action (KEEP); the paper flags this as a *context-window* failure, not a rule failure ("The correct interpretation is likely clarified by the preamble for the list ... but it might not have been included in our narrow context window", `paper_text.md:306`). ugm's PageIndex header hierarchy is the available fix (Claimify supports header metadata but did not use it, `paper_text.md:112`, `:120`).
- **GAP**: temporal-context absence ("The unemployment rate decreased in California" — no date) is NOT caught by Selection or Disambiguation (`paper_text.md:310`). ugm's relation-level bi-temporality (D3) partly absorbs this downstream, but a claim with no time anchor is still a weaker claim.
- I did NOT independently re-verify the SAFE/Molecular file:line claims beyond what `claimify_impls.md` already recorded; they are consistent with the paper's §7 descriptions (`paper_text.md:171-175`, `:286`).

---

## 4. Recommendation for ugm — a claim-level Selection design that composes with E1.5

### 4.1 Division of labor (the anti-double-filter contract)

Pin this as the binding seam so E1.5 and Selection never re-decide the same thing:

| Filter | Grain | Axis it decides | Output on reject | Decision owner |
|---|---|---|---|---|
| **E1.5 value gate** (D25–D30) | PageIndex **section / chunk** | **salience + dedup + novelty** ("is this section worth paying E2 for *now*?") | DEFERRED / CHUNKS-ONLY / dup (defer-don't-DROP, D29) | distilled classifier, LLM off hot path |
| **E2 claim Selection** (new, this doc) | **proposition / sentence** | **verifiability** ("is this proposition objectively true/false-checkable?") | sentence DROP (record audit row) **or** rewrite-to-verifiable-span | the E2 extraction LLM, in-call |

Rules that keep them from draining each other:
1. **Selection runs only on sections E1.5 already routed to FULL (or promoted from DEFERRED).** E1.5 gates *whether to pay for E2 at all*; Selection runs *inside* E2 on the sections that survived. There is no path where both gates see the same unit on the same axis. (Ties to D25: "E1.5 withholds only the expensive E2/E3 LLM layer".)
2. **Selection decides verifiability, never relevance and never salience.** Copy Claimify's three "does NOT matter" decouplings verbatim into the E2 prompt (`prompts.py:4-6`): truth value, question/scope relevance, and ambiguity are out of scope for Selection. Relevance to a K2 scope is handled by D16/D28 scope-interest at the *section* grain (E1.5/promotion), not by dropping claims. This prevents the failure the question names — "a FULL section fully drained by Selection": Selection cannot drop a section, only individual non-verifiable propositions; a section of 20 facts + 5 opinions yields 20+ claims, not 0.
3. **Selection is in-call, not a new stage** — consistent with D19 (coref rides the E2 call) and D4/D26 cheap-first (no extra LLM pass). The E2 extraction LLM already reads the chunk; have it *label* each emitted proposition `KEEP | REWRITE | DROP` and *not emit* DROPs, rather than running a separate Selection model. This keeps the gate ≪ extraction (the D30 spike-1 discipline) because it is zero marginal calls.

### 4.2 The KEEP/DROP rule set to encode (verbatim-derived)

KEEP if the proposition is **specific and verifiable** — a state, event, decision, quantity, policy, or relationship that could be checked true/false against the project's own evidence. (For ugm the verification target is the **project corpus**, not Wikipedia — replace VeriScore's "external world knowledge" with "the project's evidence" so internal/private facts qualify; this is the same substitution `claimify_impls.md` flags between FActScore world-knowledge and ugm grounding.)

DROP (never-extract classes, from `prompts.py:13-22` + `extraction_qa_template.txt:1`):
- opinions / subjective statements / interpretations ("X is crucial", "this implies X is courageous")
- generic truisms / normative "should" statements ("Technological progress should be inclusive")
- speculation / hypotheticals — modal "could/would/may", subjunctive ("AI could lead to advancements")
- instructions / advice / suggestions / recommendations ("try to use public transportation")
- questions and conversational meta ("Ah yes, tomatoes...")
- section intros and conclusions (require neighbor context — see 4.3)
- statements about a *lack* of information ("the dataset does not contain X")
- pure restated examples already covered by a more specific sibling claim (de-dup, `pipeline.py:413`)

REWRITE (do NOT drop) if mixed: emit only the verifiable span, drop the unverifiable modifier — the neutron-star / renewable-energy pattern (`paper_text.md:481-482`). This is the claim-grain mirror of defer-don't-DROP.

### 4.3 Fix the neighbor-blindness (precondition for intro/conclusion detection)

The extract-everything baseline extracts one chunk with no neighbors, so intro/conclusion DROP (the context-dependent classes, `prompts.py:9-14`) is impossible. Two cheap, D19/D-coref-aligned moves:
- Pass the chunk's **E0 PageIndex header hierarchy + section summary** into the E2 call as `metadata` context (Claimify's own unused lever, `paper_text.md:112`). By design, ugm's E1 chunk model carries a section-parent reference into the PageIndex node, so this metadata is already available. This resolves the list-item-without-preamble ambiguity the paper flagged (`paper_text.md:306`) at near-zero cost — it is already computed in E0.
- Optionally include the **±N adjacent chunks of the same section** as read-only excerpt context (the Claimify 5-preceding/5-following window, `paper_text.md:582-583`), prompt-cached behind the E1 context-prefix already specified in overall_design (`overall_design.md:94`). INFERENCE: this is the C2/C3 context-window question; for C4 the point is only that Selection's intro/conclusion rules *need* this input, which the naive single-chunk design does not provide.

### 4.4 Recall envelope (compose with D29)

Bias the claim gate **recall-conservative**, mirroring E1.5's defer-don't-DROP:
- **Conservative KEEP bias / never-drop lexical classes.** When in doubt, KEEP. Hard never-drop overrides regardless of the verifiability verdict: **quantities/numbers, named entities + a predicate, dates, decisions, policies, and change-of-state markers** (the same change-of-state up-weight E1.5 uses as the supersession proxy, D26/D29). A change-of-state sentence is the highest-severity thing to lose (zombie-fact risk, D29) — it must never be DROPped by Selection even if phrased opinionatedly. This directly tracks the paper's finding that Selection's *recall on verifiable content* is high (93.9% sent / 87.6% elem, `paper_text.md:207`) while its precision on excluding junk is the looser side (65.6% elem) — so leaning further toward KEEP costs precision (recoverable downstream by the relation layer's `evidence_count`, D2) but protects recall (unrecoverable once dropped).
- **DROP is auditable, append-only, never silent** — the analog of D27's `gate_decisions`. Record every DROP as a row: `(chunk_id, dropped_span, drop_class ∈ {opinion,instruction,hypothetical,intro,conclusion,lack_of_info,question,generic}, selection_version, decided_at)`. Two reasons: (i) **rebuildability** — a better Selection prompt can re-examine only the DROP set (version-filtered batch, exactly D28's gate-version re-classification, applied at claim grain); (ii) **canary safety** — plant rare verifiable facts in the O6 golden set and **fail CI if Selection DROPs a canary** (the claim-grain copy of D29's canary rule). The relation layer also gives a free safety net: a fact wrongly dropped from one document is recoverable if *any other* document asserts it (D2 `evidence_count`), so single-doc DROP is not single-fact loss — but a *uniquely-attested* fact dropped is gone, which is precisely what the canary set must cover.
- **Tune against per-fact false-drop rate, never the corpus average** (D29's exact discipline, one grain down). Sample the DROP stream; measure how often a DROPped span was actually a uniquely-attested verifiable fact.

### 4.5 Concrete E2 design (contrast with the extract-everything baseline)

The naive single-chunk baseline's prompt says "Extract **all** atomic claims ... Return only claims supported by an exact quote". E2 must replace that bare decompose-everything instruction with a **Selection-then-extract** instruction in the same single call (no new stage, D19-aligned):

1. Prompt change: instruct the model to first judge each candidate proposition as `KEEP | REWRITE | DROP` using the §4.2 rule set + the three "does NOT matter" decouplings, emit only KEEP/REWRITE claims, and emit DROPs into a *separate* `dropped: list[DroppedSpan]` field for audit. Keep the existing verbatim evidence-quote grounding requirement (it is orthogonal and correct — it answers "copied from text", §2.1).
2. Schema change: extend the extracted-claim schema with `dropped: list[DroppedSpan]` where `DroppedSpan{span: str, drop_class: DropClass, evidence_quote: str}`; persist these to a new append-only `claim_selection_decisions` table (D27-shaped). Add a `DropClass` StrEnum alongside the claim-kind labels.

   ```python
   # ugm E2 Selection design — illustrative pseudocode, not impl-bound
   class DropClass(StrEnum):
       OPINION = "opinion"
       INSTRUCTION = "instruction"
       HYPOTHETICAL = "hypothetical"
       INTRO = "intro"
       CONCLUSION = "conclusion"
       LACK_OF_INFO = "lack_of_info"
       QUESTION = "question"
       GENERIC = "generic"

   class DroppedSpan(BaseModel):
       span: str
       drop_class: DropClass
       evidence_quote: str  # verbatim substring, kept for audit

   class ExtractedClaim(BaseModel):
       text: str
       evidence_quote: str  # verbatim-substring grounding gate target
       claim_kind: ClaimKind

   class ClaimExtractionResult(BaseModel):
       claims: list[ExtractedClaim]
       dropped: list[DroppedSpan]  # Selection audit trail, append-only
   ```
3. Validation unchanged: the verbatim-substring grounding gate still requires the verbatim substring — Selection changes *which* propositions are emitted, not the grounding contract. Add one assertion at the boundary: a KEEP claim whose `evidence_quote` is a pure opinion-marker span should still pass grounding (grounding ≠ verifiability), so do **not** try to enforce verifiability in the grounding gate; keep the two gates separate exactly as Claimify keeps Selection separate from entailment.
4. Feed PageIndex header/section metadata into the E2 call (§4.3) so the intro/conclusion classes are decidable; ugm's E1 chunk model provides the section-parent reference and section-kind path by design.

Net effect: ugm moves from FActScore-class decompose-everything (precision-poor, the very thing D25 says "the extraction prompt, not the model, is the bottleneck", `decisions.md:496-498`) to Claimify-class verifiability-gated extraction — the change the value-gate research already implies but which the naive single-chunk baseline leaves ungated at the proposition grain, having addressed value only at the chunk grain (E1.5).

---

## References
Paper: `claimify_deshwalmahesh/paper_text.md` (arXiv 2502.10855) — Selection §3.2 (`:114-124`), ablation Table 4 (`:277-284`), Table 5 examples (`:476-485`), verifiability vs check-worthiness (`:263`), context window (`:112`, `:582-583`), list-item/temporal gaps (`:306`, `:310`). Prompts: `claimify_deshwalmahesh/src/prompts.py:1-46` (Selection), `claimify_claimsmcp/structured_prompts.py:7-60`, `veriscore/prompt/extraction_qa_template.txt` + `extraction_non_qa_template.txt`, `safe.../classify_relevance.py:227-249` (relevance). Repo synthesis: `repo_findings/claimify_impls.md`. ugm design: `e1_5_value_gate_design.md`, `decisions.md` D2/D3/D4/D7/D12/D16/D19/D25–D30, `concepts.md`, `overall_design.md:88-110`.
