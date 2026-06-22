# C2 — The De-contextualization Problem in Depth

**Question.** Define decontextualization precisely; map the decontextuality-vs-minimality
tradeoff (Molecular Facts) and the decontextualize-then-verify ordering (DnDScore); decide
WHAT context the extractor must receive and HOW MUCH is too much; conclude with concrete
decontextualization rules + the context the extractor needs.

**Sources read for this answer (primary, local).** Claimify paper markdown
(`claimify_deshwalmahesh/paper_text.md`, arXiv 2502.10855) incl. full Selection / Disambiguation /
Decomposition / Entailment prompts and Appendix D/E/K/L; Molecular Facts PDF
(`molecular_facts_2406.20079.pdf`, arXiv 2406.20079) + `molecular_facts/src/prompts/molecular_prompt.py`;
DnDScore PDF (`dndscore_2412.13175.pdf`, arXiv 2412.13175); repo archaeology
(`repo_findings/claimify_impls.md`); the naive single-chunk baseline that ugm's E2 must
avoid (the extract-everything, FActScore-shaped anti-pattern); ugm design
(`overall_design.md`, `e1_5_value_gate_design.md`, `decisions.md` D4/D7/D12/D19/D25–D30).
Citations are `file:line` for code/prompts/paper-markdown and `arXiv:id` + figure/table/§ for the
two PDFs (page images, no stable line numbers).

---

## 1. Key findings (bullets)

- **Decontextualization has a precise, citable definition with two halves.** Choi et al. 2021
  (quoted in Claimify): "(1) each claim should be understandable on its own, without requiring
  additional context, AND (2) each claim should retain the meaning it held in its original
  context" (`paper_text.md:38`). The Choi framework names exactly **four edit types**: name
  completion, pronoun/NP swap, discourse-marker removal, and **addition** (bridging global scope +
  background) (DnDScore arXiv:2412.13175 §2.2). The four axes the question asks for map onto these:
  **referential** (pronouns/coref → pronoun/NP swap), **structural** (acronyms/elisions/attachment
  → name completion + addition), **temporal** (relative→absolute → a sub-case of referential),
  **entity** (named-not-described → name completion). These are VERIFIED, not invented.

- **The half that everyone forgets is half (2): meaning-preservation, enforced by a verbatim-quote
  / entailment guard.** A claim that "stands alone" but drifts from source meaning is WORSE than a
  raw pronoun, because it reads as confidently true while being unsupported. Claimify enforces this
  with "Do NOT use any external knowledge beyond what is stated in the question, context, and
  sentence" in every stage (`paper_text.md:902`, `:986`) plus a self-entailment definition of
  decontextualized ("its meaning in isolation matches its meaning interpreted alongside the
  question, the context, and the other propositions", `paper_text.md:964`). A naive single-chunk
  baseline tends to enforce (2) mechanically via a verbatim-substring grounding gate that requires
  the verbatim evidence-quote field to be a substring of the chunk. **That guard is the right
  instinct but, applied that way, it fights decontextualization** — see §4.

- **The decontextuality–minimality tradeoff is quantified by Molecular Facts and it is large.**
  Molecular Facts (arXiv:2406.20079) defines **two** criteria — Criterion 1 Decontextuality
  ("uniquely specify entities, events, and context such that the claim is interpretable") and
  Criterion 2 **Minimality** (`argmax_m |E(m)|` — pick the decontextualization that **maximizes the
  set of supporting evidence documents**, i.e. add the LEAST/most-widely-attested context). Over-
  contextualization measurably breaks verification: standard decontextualizers flip a **SUPPORTED →
  NOT_SUPPORTED** label on **1.7%–9.6%** of decontextualizations purely by injecting non-minimal
  detail (arXiv:2406.20079 §4.5, Table 1: SAFE-DECONTEXT 3.94% auto / 8.49% potential; SIMPLE-
  DECONTEXT 13.42% auto / 23.39% potential). Human review of the "non-minimal" subset: SIMPLE-
  DECONTEXT is **72.5% truly non-minimal**, SAFE 43.8%, MOLECULAR best at 24.0% non-minimal vs
  52.0% minimal (Table 2, Table 5). Conclusion: **bloat is not free; it costs ~2–10% of correct
  labels and injects unsupported detail.**

- **Ordering matters: decontextualize-then-verify, and verify the SUBCLAIM in the CONTEXT of the
  decontextualization.** DnDScore (arXiv:2412.13175) shows that the naive pipelines both fail:
  decompose-then-decontextualize loses atomicity (which atomic fact is being verified?), and
  decontextualize-then-decompose inflates scores by repeating essential context across subclaims
  (Fig 1). Their fix (DnDScore) passes BOTH the atomic subclaim AND its decontextualized form to the
  verifier. **Numerically decontextualization changes verdicts a lot:** between an atomic subclaim
  and its decontextualized form, FActScore support judgments change on **19.11%** of claims (16.25%
  flip false→true via added entity disambiguation; 48.52% of those involve a pronoun replacement);
  true→false only 3.26% (§6.1). So decontextualization is **net strongly positive for recall** but
  can also mask correctness when the added context is wrong (Table 4, examples 3–5). For ugm this
  means: **decontextualize at extraction, keep the source quote as the verification anchor, and
  never let an added detail become a silently-unverifiable claim.**

- **HOW MUCH context the extractor needs is a measured constant in Claimify: ~5 sentences each
  side, plus the originating question, plus structural metadata — NOT the whole document.**
  Claimify's measured config: `max_preceding=5` for all stages, `max_following=5` for Selection and
  **0** for Disambiguation/Decomposition (`paper_text.md:582-583`). The window is rendered as an
  *Excerpt* with `[...]` truncation markers and the target sentence passed separately
  (`paper_text.md:962`, prompt user templates `:944-956`, `:1050-1058`). The opposite extreme —
  SAFE feeding the **entire response** as decontextualization context (`paper_text.md:609`) — is
  exactly the design Molecular Facts shows over-reaches (`paper_text.md:723-729`). And FActScore's
  **zero-neighbor, single-sentence** prompt is the maximal *under*-contextualization risk
  (`claimify_impls.md:287-294`). **The naive single-chunk baseline sits on the FActScore end: one
  chunk, no neighbors, no document/section context, no question** — this is the core defect this
  question exposes.

---

## 2. Evidence & detail with citations

### 2.1 Precise definition of decontextualization (the four axes, grounded)

The canonical definition is two-part (Choi et al. 2021, restated verbatim in Claimify):
> "(1) each claim should be understandable on its own, without requiring additional context, and
> (2) each claim should retain the meaning it held in its original context" (`paper_text.md:38`).

DnDScore restates Choi's **operational** definition as four concrete edits (arXiv:2412.13175 §2.2):
name completion; pronoun/NP swap; discourse-marker removal; addition (bridging global scope +
background). Mapping to the question's four requested axes (VERIFIED grounding for each):

| Axis (question) | What must be resolved | Claimify mechanism | Source |
|---|---|---|---|
| **Referential** (pronouns, coref, "the policy", "these notes") | replace with the named referent if readers would reach consensus; else DROP | Disambiguation: referential ambiguity; the in-call coref (`he`→`John Smith`, `the company's`→`TurboCorp`) | `paper_text.md:130`, `:906-909` |
| **Structural** (acronyms, elisions, attachment ambiguity, "AI advanced X and Y at A and B") | expand acronyms/partial names *only if defined in question+context*; resolve attachment if consensus, else DROP | Disambiguation: structural ambiguity; partial-name/acronym rule | `paper_text.md:130`, `:146`, `:900` |
| **Temporal** (relative time → absolute; "next year", "at the time") | "at the time"→"2010" if context dates it; otherwise temporal ambiguity → DROP, never invent a date | "Temporal ambiguity is a type of referential ambiguity" | `paper_text.md:898`, `:310`, `:909` |
| **Entity** (named not described; "Jane's leadership", "the court") | use the canonical name, not the role/description; bracket inferred entity context | Decomposition brackets `[...]`; "named not pronoun" | `paper_text.md:144`, `:1042` |

Crucial Claimify subtlety the question's framing should absorb: **"sufficiently decontextualized"
is not a binary the model can self-judge.** Claimify's own §2.3 argument is that whether "John Smith
supports government regulations" is decontextualized **only became apparent after verification**
retrieved opposite evidence from a different context (`paper_text.md:60-64`). Their resolution is
**outcome-based**: missing context is a problem *only if including it would flip the verdict*
(`paper_text.md:66`). The practical consequence for an extractor (no verifier in the loop) is the
**"group of readers would reach consensus"** test (`paper_text.md:134`) — a tractable proxy:
resolve a reference iff a group of readers shown the question+context would agree on the referent;
otherwise mark **"Cannot be decontextualized"** and drop the unit (`paper_text.md:136`,
`prompts.py:96` in deshwalmahesh). This **discard-on-irresolvable-ambiguity rule is unique to
Claimify** among all surveyed systems (`claimify_impls.md:381-383`).

### 2.2 The minimality tradeoff (Molecular Facts), with numbers

Molecular Facts' thesis: "fully atomic facts are not the right representation" — they are *too
atomic* and need decontextualization, **but** decontextualization can be *too minimal* (under) or,
worse, **non-minimal** (over) (arXiv:2406.20079 abstract; §2.1).

- **Criterion 1 (Decontextuality).** "When interpreted as a standalone statement, m_i must have the
  truth-conditional meaning I(c_i | x, r). It should uniquely specify entities, events, and other
  context" (§2.1, Criterion 1 box). Equivalent to Choi 2021 Def 1.
- **Criterion 2 (Minimality).** "Given a set of statements M that all decontextualize a claim c_i,
  we should select `argmax_{m∈M} |E(m)|` to maximize the size of the set of supporting evidence
  documents" (§2.1, Criterion 2 box). I.e. when several elaborations are valid, prefer the one whose
  added descriptor is **more enduring / widely-reported** ("rugby player" beats "former player for
  North Queensland Cowboys"; the latter requires verifying an extra, narrower fact). **Minimality is
  defined by evidence-breadth, not by character count** — a subtle but load-bearing point: the goal
  is "add detail that is itself easy to verify," not merely "add few words."
- **Molecular Fact** = a statement obeying both: "uniquely specify the interpretation of c_i even
  when considered on its own, while adding as little information as possible to do so" (§2.1
  Molecular Fact box).

**The cost of getting minimality wrong (VERIFIED numbers, arXiv:2406.20079):**
- Over-contextualization flips **SUPPORTED→NOT_SUPPORTED** on **3.94%** (SAFE) / **13.42%** (SIMPLE)
  of decontextualizations automatically; **8.49%** / **23.39%** are *potentially* non-minimal
  (Table 1). Authors summarize the realized harm as **1.7%–9.6%** of decontextualizations (§4.5).
- Of the auto-flagged non-minimal cases, humans confirm **72.5%** (SIMPLE) and **43.8%** (SAFE) are
  *truly* non-minimal (Table 2).
- On the ambiguous-biographies set, the human minimality/ambiguity tradeoff (Table 5): SIMPLE
  16% minimal / 56% non-minimal; SAFE 24% / 0% non-minimal but **76% still ambiguous** (too
  minimal!); MOLECULAR **52% minimal / 24% non-minimal / 24% ambiguous** — the only method near the
  Pareto sweet spot. Accuracy (Table 3): ATOMIC 68.7% → SIMPLE 76.2% → MOLECULAR 74.7% overall;
  decontextualization *raises* accuracy, and MOLECULAR does it with shorter sentences (avg 14.96
  words vs SIMPLE 15.55) and far fewer non-minimal errors.

Net: **decontextualize (recall jumps), but bias toward minimal, evidence-breadth-maximizing
additions; non-minimal bloat costs single-to-double-digit % of correct labels.**

### 2.3 Decontextualize-THEN-verify, and the ordering trap (DnDScore)

DnDScore (arXiv:2412.13175) is the systematic study of how decomposition × decontextualization
interact. The two naive orders both fail (Fig 1):
- **Decompose → decontextualize:** the decontextualized subclaim "is no longer atomic … which part
  of the augmented text should be verified?" → redundant subclaims mask correctness of the original.
- **Decontextualize → decompose:** repeats essential context across every subclaim → inflates the
  factuality score; loses atomicity per subclaim.

**DnDScore's fix:** verify the **atomic subclaim** *using its decontextualized form as context*
(prompt is given source document + subclaim + decontextualized claim; §4.2). This is the literal
"decontextualize THEN verify, but keep both representations" the question references.

**Magnitudes (VERIFIED):**
- Decontextualization changes the FActScore support judgment on **19.11%** of subclaim pairs;
  **16.25%** flip false→true (recall gain from entity disambiguation), only **3.26%** true→false
  (§6.1). **48.52%** of the false→true flips involve a pronoun replacement — i.e. resolving coref is
  the single biggest source of recovered recall.
- But added context can be *wrong*: Table 4 examples 3–5 show decontextualization injecting a false
  detail (wrong sitcom, wrong newspaper, wrong wrestler alias) and flipping a true subclaim to
  false. This is the failure mode Claimify's "no external knowledge" rule and ugm's verbatim-quote
  grounding guard are meant to prevent.

### 2.4 HOW MUCH context — the measured window, and the two failure extremes

Measured Claimify configuration (Appendix D/E, all VERIFIED):
- `max_preceding_sentences = 5` (all stages); `max_following_sentences = 5` (Selection),
  `0` (Disambiguation, Decomposition) (`paper_text.md:582-583`).
- Plus the **originating question** in every stage (`paper_text.md:879`, `:946`, `:1052`).
- Plus optional **structural metadata** (Markdown header hierarchy) — *defined but unused* in their
  experiments (`paper_text.md:112`, `:120`); the paper's own Limitations flags wider preceding
  context for bullet-list preambles as likely-beneficial future work (`paper_text.md:306`).
- The window is an **Excerpt with `[...]` truncation markers**; under `[...]` the model is told it
  may NOT see all sentences, so it must NOT assume the sentence answers the question unless strongly
  implied (`paper_text.md:984`). This is a faithfulness lever for partial visibility.

The two extremes that bracket "too much / too little":
- **Too little — FActScore:** one sentence, **no neighbors, no document, no question** — only
  fixed + BM25 demo sentences (`claimify_impls.md:287-294`). Cannot resolve "it"/"the policy"/"the
  court" at all → maximal under-decontextualization.
- **Too much — SAFE:** **entire response** as decontextualization context (`paper_text.md:609`),
  which the Claimify authors show lets claims "incorporate info from beyond the source sentence"
  and over-reach (`paper_text.md:723-729`); Molecular Facts confirms whole-response context drives
  the non-minimality label flips (§4.5).

**Why the question is always included and why metadata helps:** the question disambiguates
verifiability ("- Investing in renewable energy" is advice *or* a fact depending on the list
preamble — `paper_text.md:306`) and supplies entity full-forms / topic scope for the `[...]`
brackets ("John [a celebrity] has called for peace [in the Middle East]", `paper_text.md:144`).
**The single biggest realized lever, though, is local neighbors for coref** (DnDScore: ~half of
recovered recall is pronoun replacement, §6.1; Claimify's own NLI failure case was "it"→Plankalkül
resolvable only from the *preceding* sentence, `paper_text.md:682`).

### 2.5 The naive single-chunk baseline vs. this evidence (the anti-pattern to avoid)

The known anti-pattern (the extract-everything, FActScore-shaped baseline) behaves like this:
- **Single chunk, no neighbors, no document/section, no question** passed to the LLM: only the
  chunk's id/evidence id/text reaches the model, and extraction iterates ONE chunk at a time. The
  system prompt is minimal: "Extract all atomic project-memory claims … Trust the chunk boundary …
  Return only claims … supported by an exact quote copied from this chunk … Do not infer facts not
  stated in the chunk".
- **The verbatim evidence-quote field MUST be a verbatim normalized substring of the chunk**
  (normalized by whitespace + casefold).

The collision: the extractor is told "extract atomic claims, ground each in a verbatim quote from
*this chunk*, do not infer" — which is **FActScore-style decompose-everything with zero
decontextualization context**. There is no mechanism to resolve a pronoun whose antecedent is in
the previous chunk, no question/topic to scope brackets, no neighbor to date "at the time", and the
verbatim-quote rule **actively penalizes** a properly decontextualized claim (e.g. "Alice Novak
[VP Eng] left Acme") because the bracketed/expanded form is no longer a substring of the chunk.
So this baseline optimizes for half (2) meaning-preservation **at the cost of** half (1)
standalone-interpretability — the exact inversion of what retrieval-time memory needs (a claim is
read months later with no chunk in hand).

---

## 3. Confidence & gaps

- **HIGH confidence** on: the two-part definition and four axes (Choi 2021 via Claimify
  `paper_text.md:38`, DnDScore §2.2); Claimify's measured 5/5 → 5/0 window + question + `[...]`
  markers (`paper_text.md:582-583`, prompts read in full); Molecular Facts' two criteria and the
  minimality-flip numbers (Table 1/2/3/5 read directly from PDF); DnDScore's 19.11%/16.25%/3.26%/
  48.52% and the decontextualize-then-verify-with-both-forms method (§6.1, §4.2 read directly); the
  single-chunk / verbatim-quote anti-pattern behavior (analyzed in full).
- **MEDIUM confidence** on: the *transfer* of these single-deployment numbers to ugm's corpora.
  Molecular Facts/DnDScore measure on biographies and ChatGPT long-form answers with Wikipedia
  evidence; ugm's project-memory chunks are a different distribution (internal docs, chat, private
  entities) where (a) entity homonymy is *lower* (internal entity space, D17/D20 — no Wikidata
  needed) so the Molecular-Facts homonym-disambiguation pressure is weaker, but (b) cross-chunk
  coref is *higher* (conversational/threaded sources). The qualitative conclusions transfer; the
  exact percentages are indicative, not committed (consistent with D30's "no constant without a
  measured rate").
- **GAPS / could not verify:** (1) No number anywhere for the *optimal* preceding-window size —
  Claimify used 5 without a sweep and explicitly did not tune it (`paper_text.md:306` Limitations,
  Appendix D "did not conduct an exhaustive search"). So "5 sentences" is a defensible default, not
  a proven optimum. (2) Claimify operates on a **question–answer pair**; ugm chunks have **no
  question**. The question carries real disambiguation load in Claimify (verifiability of
  list-items, bracket scoping). What replaces it for ugm — PageIndex section title/summary +
  document title — is a reasonable substitute but **unmeasured**; the claimeai port already runs
  question-agnostic (`claimify_impls.md:216-219`) and still works, which is weak positive evidence.
  (3) Whether a separate "molecular" disambiguation pass (world-knowledge homonym resolution)
  earns its cost in ugm is unverified and likely **NO** given the internal entity space.

---

## 4. Recommendation for ugm (concrete, tied to decisions + the design fix)

**The conclusion the question asks for, stated as rules + required context.**

### 4.1 The decontextualization rules (what a ugm claim must satisfy)

A ugm claim is decontextualized iff (enforce all; the first four are the four axes, the last two
are the guardrails Molecular Facts/Claimify prove are non-optional):

1. **Referential:** no pronoun or bare definite NP ("the policy", "these notes") without its named
   referent — resolved **in the extraction call** for all languages (this is exactly **D19** coref-
   in-call; coref is the single biggest recall lever, DnDScore §6.1). If the referent is not
   recoverable from the supplied context with reader-consensus, **drop the claim** (Claimify
   discard rule `paper_text.md:136`) rather than guess.
2. **Structural:** expand a partial name / acronym **only if the full form is in the supplied
   context**; otherwise leave it and do not treat it as ambiguity (`paper_text.md:900`). Resolve
   attachment/scope ambiguity only on reader-consensus; else drop.
3. **Temporal:** absolutize relative time only if the context dates it; **never invent a date**
   (`paper_text.md:310`). Store the temporal qualifier in the claim text; bi-temporal *validity
   windows* remain a relation-level concern (D3/D18), not a substitute for in-text time.
4. **Entity:** name, don't describe ("Alice Novak", not "the VP"). The canonical name is what
   flows to entity resolution (D17) — so decontextualization and the registry are the same effort.
5. **Minimality (Molecular Facts Criterion 2):** add the **least, most-widely-attested** context
   needed to stand alone; prefer enduring descriptors over narrow ones; bracket inferred context
   with `[...]` so it is flagged as inferred (`paper_text.md:144`). Do **not** feed the whole
   document as context (the SAFE failure, §2.4) — non-minimal bloat costs ~2–10% of correct labels.
6. **Meaning-preservation (Choi half 2 / faithfulness):** the decontextualized claim must be
   entailed by source+context; **no external knowledge** beyond the supplied context
   (`paper_text.md:902`). This is where the verbatim-quote grounding guard must be **repaired, not
   removed** (see 4.3).

### 4.2 The context the extractor must receive (replace single-chunk)

Minimum viable context window per extraction call — the **D4 cheap-first** instinct says do not
jump to whole-document, use a bounded window:

- **The target chunk** (the baseline already supplies this).
- **±N neighbor chunks** from the same document (N≈1–2 chunks, the chunk-level analogue of
  Claimify's 5 preceding / 5 following sentences) — ugm's E1 chunk model provides BY DESIGN the
  chunk's section-parent reference and character offsets, so neighbors are a cheap ordered fetch,
  no new state. This is the **single highest-value change** (coref recall, §2.3).
- **Section/document scaffold as the question-substitute:** PageIndex **section title + node
  summary + document title** (Claimify's "optional metadata", `paper_text.md:112`, unused by them
  but flagged as helpful). This scopes brackets and verifiability the way Claimify's question does,
  without inventing a question. (Aligns with E1.5 operating per **PageIndex section**, **D25**.)
- **NOT the whole document** (SAFE over-reach, Molecular non-minimality flips). Bounded window only.
- This rides the **existing E2 extraction call (D19)** — no new model, no new stage; coref +
  decontextualization are per-mention understanding that the extraction LLM already does at ~zero
  marginal cost. Cross-*document* coref stays an open recall gap (D19 caveat), unchanged.

### 4.3 The design fix (concrete, minimal)

The defect of the naive single-chunk baseline: the verbatim-substring grounding gate requires the
verbatim evidence-quote field to be a verbatim substring of the chunk text, which is *incompatible*
with a decontextualized claim text. Separate the two concerns — keep grounding, allow
decontextualization:

- **Split the claim into two fields** (the DnDScore "keep both forms" pattern, §2.3): keep
  the verbatim evidence-quote field as the **verbatim source span** (the grounding anchor —
  validation unchanged, still a substring check) and let the claim text be the
  **decontextualized/molecular** assertion (pronouns resolved, names expanded, `[...]` brackets
  allowed). The quote validates *grounding*; the claim text carries *standalone meaning*. A naive
  baseline wrongly holds the claim text to the substring bar transitively because the prompt says
  "supported by an exact quote" — relax the prompt to "**each claim must cite a verbatim evidence
  quote from the supplied context, but the claim text itself must be rewritten to stand alone:
  resolve pronouns and partial names from the neighbor chunks and section context, expand acronyms
  only if defined in context, and never add facts not in the context.**" The verbatim guard then
  proves half-(2) faithfulness on the *quote*, while the *claim* delivers half-(1) standalone-ness.
- **Expand the extractor input** so the per-chunk extraction orchestration passes the ±N neighbor
  chunks and the section/document scaffold alongside the target chunk. The grounding gate should
  accept a verbatim evidence quote found in the **supplied context window**, not only the single
  target chunk — otherwise a claim correctly grounded in a neighbor is rejected. (Record which
  chunk the quote came from for provenance; the claim model's supporting-chunk-id list already
  holds multiple chunk ids.)
- **Add the discard path:** when the LLM cannot resolve a reference from the supplied context (no
  reader-consensus), it should emit nothing for that claim — mirror Claimify's "Cannot be
  decontextualized" → drop (`paper_text.md:136`). A dangling-pronoun claim must never be written
  (this is the **D4** guarantee "no claim leaves E2 with a dangling pronoun").

### 4.4 What to explicitly NOT do (cost discipline, D4/D7/D30)

- **Do not run a separate Molecular-Facts world-knowledge homonym pass.** It *requires* external
  parametric knowledge (`molecular_prompt.py:10` "Utilize your world knowledge"), which (a) violates
  ugm's faithfulness rule and (b) is low-value given ugm's internal entity space (D17/D20 — no
  public-registry homonymy). Disambiguate from supplied context only.
- **Do not adopt the multi-stage 3-completion voting Claimify pipeline wholesale.** ugm is not a
  fact-checking benchmark; the **D4 cheap-first** posture says do the cheap single-call coref+
  decontextualization in the existing E2 call first, and only escalate if a measured quality gap
  appears. The value gate (E1.5, **D25–D30**) already removes the low-salience tail *before*
  extraction, so the per-call budget can afford the bounded neighbor window.
- **Measure before locking the window size.** Per **D30**, ship no N (neighbor count) without a
  measured per-fact false-decontextualization rate on a corpus slice; "±1–2 chunks" and "5
  sentences" are defaults, not constants. Plant canary coref cases (pronoun whose antecedent is in
  the previous chunk) in the golden set — exactly the **D29** canary-fact pattern, extended from
  "false-skip" to "false-decontextualization".
- **Rebuildability (D7) is preserved:** decontextualization is deterministic-given-inputs only up to
  LLM drift — same caveat as the gate's salience rung (D27). The verbatim evidence quote is the
  durable, recomputable anchor; treat the decontextualized claim text as **stored & auditable**,
  not bit-reproducible.
