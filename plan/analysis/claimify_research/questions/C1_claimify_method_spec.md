# C1 — Claimify method spec (faithful to the paper)

**Question:** Produce a faithful, precise spec of Claimify (Metropolitansky & Larson, Microsoft
Research, *Towards Effective Extraction and Evaluation of Factual Claims*, arXiv 2502.10855). Pin
down each of the four stages, the prompt mechanics, and — critically — the **context** each stage
operates over (Claimify never sees a sentence in isolation). Then the ambiguity-handling /
discard rule, the decontextualization rules, the reported results vs. prior methods (actual
numbers + metric definitions), and conclude with the canonical Claimify contract ugm should adopt.

**Primary source.** `claimify_deshwalmahesh/paper_text.md` (markdown of arXiv 2502.10855). All
`paper_text.md:NNN` citations below are line numbers in that file. Cross-references to the three
reimplementations come from `repo_findings/claimify_impls.md`. The anti-pattern under diagnosis is
the **naive single-chunk baseline** — the extract-everything, no-context extractor shape that ugm's
E2 must avoid — described conceptually below.

---

## 1. Key findings

- **Claimify is a 4-stage per-sentence pipeline over a question–answer pair**, not a one-shot
  extractor: **Sentence-splitting & context creation → Selection → Disambiguation →
  Decomposition** (`paper_text.md:108-142`, Figure 1 `:470`). It is a "decompose-then-verify"
  front-end whose job is to emit *entailed, decontextualized, verifiable* factual claims and to
  **decline** when the source is too ambiguous to interpret confidently.
- **No stage ever sees a bare sentence.** Every stage LLM receives `Question` + an `Excerpt`
  (a multi-sentence window with `[...]` truncation markers) + the **target `Sentence` passed
  separately** (prompt templates `paper_text.md:877-887` Selection, `:944-956` Disambiguation,
  `:1050-1058` Decomposition). The canonical context window is **5 preceding + 5 following**
  sentences for Selection and **5 preceding + 0 following** for Disambiguation and Decomposition
  (`paper_text.md:582-583`). The window is *per-stage configurable* (`p` preceding, `f` following,
  + optional metadata such as Markdown header hierarchy) (`paper_text.md:112`).
- **Selection is an explicit verifiability gate that also rewrites.** It keeps only sentences with
  ≥1 specific & verifiable proposition; for mixed sentences it returns a **rewritten** sentence
  stripped of unverifiable spans; for pure-opinion/advice/speculation/intro/conclusion/
  "lack-of-information" sentences it returns "no verifiable content" and the sentence is dropped
  before Disambiguation (`paper_text.md:116-124`, system prompt `:813-875`).
- **Disambiguation resolves referential + structural ambiguity using the question+context, and
  DISCARDS when there is no confident interpretation.** The decision standard is the
  **"group of readers would likely reach consensus"** test: if any ambiguity is *unresolvable*,
  the sentence is labeled **"Cannot be disambiguated"** and excluded from Decomposition **even if
  it has unambiguous verifiable components** (`paper_text.md:128-136`, prompt `:889-942`).
  Vagueness/generality are explicitly **not** ambiguity; missing full names/acronyms are filled
  from context if available but their *absence* is not ambiguity (`paper_text.md:146`, `:898-900`).
- **Decomposition emits the simplest decontextualized claims with bracketed essential context.**
  Each claim must (1) be understandable in isolation and (2) preserve its in-context meaning;
  inferred-but-essential context is wrapped in `[...]` brackets to flag lower-reliability content
  (`paper_text.md:142-144`, `:964`, `:1042`). Hard faithfulness rules: **no external knowledge,
  no citations** (`:986`, `:901-902`); attribution context ("John highlights X") must be retained
  (`:982`).
- **Reported results (gpt-4o-2024-08-06, headline numbers):** Entailment **99%** (tie with
  VeriScore 99.2%, both ≫ DnD 89.1 / SAFE 96.6); element-level coverage **macro-F1 83.7%**
  (next best DnD 56.2 / VeriScore 62.5) and **accuracy 87.9%**; sentence-level coverage
  **accuracy 91.8% / macro-F1 91.2%** (next best AFaCTA 81.6 / VeriScore F1 78.9);
  decontextualization **80.5–80.6% "desirable" results** (highest of all methods)
  (`paper_text.md:199-202`, Table 2 `:207-214`, Table 3 `:270-275`). Ablation: removing
  **Selection** causes the largest drop (element-coverage F1 83.7→54.4), confirming the
  verifiability gate is the dominant contributor (`paper_text.md:280`, Table 4 `:277-284`).
- **Cost/yield:** Claimify is the most conservative extractor — only **58.3%** of sentences yield
  any claim and **3.31** claims/sentence, vs SAFE 98.7% / DnD 96.5% and VeriScore 40.4%; only
  **0.55%** invalid claims (`paper_text.md:625-631`). Discard rate is small: "Cannot be
  disambiguated" ≤ **5.4%** of sentences, "No verifiable claims" at Decomposition only **0.8%**
  (`paper_text.md:138`, `:142`).

---

## 2. Evidence & detail with citations

### 2.0 What a "claim" is (the contract Claimify targets)

Claimify adopts Ni et al. (2024): a **factual claim** is a statement that "presents verifiable
facts," where a fact "can be objectively verified as true or false based on empirical evidence or
reality" (`paper_text.md:30`). Claim quality is judged on three axes (`paper_text.md:36-38`):

1. **Entailment** — if the source text is true, the claim must be true (a.k.a. faithfulness /
   correctness).
2. **Coverage** — claims capture the verifiable info and *exclude* the unverifiable info.
3. **Decontextualization** — each claim is understandable alone *and* keeps its original meaning.

Atomicity is **deliberately rejected** as a goal (no clear endpoint; doesn't reliably help
fact-checking) (`paper_text.md:40`) — Decomposition aims at "simplest discrete units," not maximal
atomization.

### 2.1 Stage 0 — Sentence splitting & context creation (§3.1, `paper_text.md:110-112`)

- **Input unit:** a **question–answer pair**. NLTK's sentence tokenizer (v3.9.1) splits the
  *answer* into sentences (`paper_text.md:112`). (In their human-study pipeline they first split
  the answer into paragraphs on newlines, *then* NLTK-tokenize each paragraph, because bullet
  lists without terminal punctuation otherwise collapse into one "sentence" — `paper_text.md:452`.)
- **Per-sentence context** `s` is built from `p` preceding + `f` following sentences + optional
  metadata (e.g. Markdown header hierarchy). `p` and `f` are **defined separately per stage**
  (`paper_text.md:112`). Metadata was *not* used in the paper's experiments (`paper_text.md:120`).
- **Canonical hyperparameters** (Appendix D, `paper_text.md:579-589`): `max_preceding = 5` (all
  stages); `max_following = 5` for Selection, **`0` for Disambiguation & Decomposition**;
  `max_retries = 2`; temperature `0` (or `0.2` when `completions > 1`); **completions = 3** for
  Selection & Disambiguation, **1** for Decomposition; **min_successes = 2** for Selection &
  Disambiguation, **1** for Decomposition. "Success" is stage-specific: Selection = verifiable
  content found; Disambiguation = no/only-resolvable ambiguity; Decomposition = ≥1 claim.
- **Excerpt rendering:** the window is shown as an `Excerpt` block; `[...]` markers signal that not
  all response sentences are visible. The **target sentence is supplied separately** in the
  `Sentence:` field (so the model knows exactly which sentence to act on while reading neighbors).

> **This is the crux of the question.** Claimify processes a sentence *within* its surrounding
> passage and originating question — never in isolation. The 3 reimplementations confirm this is
> the load-bearing design element (`claimify_impls.md:30-34`, `:75-78`, `:144-146`,
> `:204-205`). Deviations matter: `claimify_claimsmcp` wrongly uses `f=5` for **all** stages
> (`claimify_impls.md:135-143`); `claimeai` is paper-faithful on windows but drops the question
> from the prompts entirely (`claimify_impls.md:216-219`).

### 2.2 Stage 1 — Selection (§3.2, `paper_text.md:114-124`; prompt `:813-887`)

**Job:** per-sentence verifiability gate **with rewrite**. The LLM picks exactly one of three
outcomes (`paper_text.md:124`):
1. "Sentence does not contain any verifiable content" → labeled **"No verifiable claims"**,
   excluded from later stages.
2. A **rewritten** sentence retaining only the verifiable components (when the sentence mixes
   verifiable + unverifiable content).
3. The original sentence unchanged ("remains unchanged") — no unverifiable content to strip.

**Prompt mechanics** (`paper_text.md:813-875`): role = "assistant to a fact-checker"; explicit
non-verifiable examples (opinions, advice, speculation "AI could lead to advancements in
healthcare", interpretations) and a raw→rewritten map (e.g. *"Smith's advocacy for renewable
energy is crucial…"* → *"Smith advocates for renewable energy"*). Required output format
(`:861-875`): echo `Sentence:` → a **4-step stream-of-consciousness** (reflect on criteria →
objectively describe excerpt/sentence/neighbors → weigh whether it's a verifiable proposition vs.
intro/conclusion/opinion/etc. → only if verifiable, decide what to strip) → `Final submission:`
(Contains / Does NOT contain) → `Sentence with only verifiable information:` (rewritten | "remains
unchanged" | "None").

**Context it sees:** `Question` + `Excerpt` (5 preceding + 5 following) + target `Sentence`. The
prompt *requires* using neighbors (`:826-832`): a sentence is a non-verifiable **introduction** if
following sentences expand it, and a **conclusion** if preceding sentences detail it; a bare
"John" after "Who is the CEO of Company X?" *is* verifiable in context.

**Deliberate decoupling:** Selection **ignores ambiguity** — "It does NOT matter whether the
proposition contains ambiguous terms… Assume that the fact-checker has the necessary information
to resolve all ambiguities" (`paper_text.md:823`). Ambiguity is entirely Stage 3's concern.

### 2.3 Stage 2 — Disambiguation (§3.3, `paper_text.md:126-138`; prompt `:889-956`)

**Job:** (a) substitute partial names / undefined acronyms+abbreviations using question+context;
(b) resolve **linguistic ambiguity** that has a clear resolution; (c) otherwise **discard**.

Two ambiguity types (`paper_text.md:130`):
- **Referential** — unclear what a word/phrase refers to ("They", "the policy", "next year").
  **Temporal ambiguity is a sub-type of referential** (`paper_text.md:898`).
- **Structural** — grammar admits multiple parses ("AI has advanced renewable energy and
  sustainable agriculture at Company A and Company B"). **Special case** (`:132`): distinguishing a
  factual claim from an **author-added interpretation** ("John emphasized X, highlighting the
  importance of mentorship" — did John highlight it, or did the author?) is treated as structural
  ambiguity.

**The discard rule (consensus test).** The model asks whether **"a group of readers shown the
question and the context would likely reach consensus"** on the correct interpretation
(`paper_text.md:134`). If *any* ambiguity is **unresolvable**, output
**`DecontextualizedSentence: Cannot be decontextualized`**; the sentence is labeled "Cannot be
disambiguated" and **excluded from Decomposition — even if it has unambiguous, verifiable
components** (`paper_text.md:136`). If all ambiguity resolves, return a clarified sentence; if there
was none, return the original (`paper_text.md:136`).

**Non-ambiguity guards** (faithfulness levers, `paper_text.md:898-902`): "Vagueness and generality
are NOT linguistic ambiguity"; if a full name/definition is **not** in the question/context, leave
it as-is and **do not** count that as ambiguity (avoids hallucinating identities); "Do NOT use any
external knowledge"; "Do NOT include any citations." The worked examples (`:904-936`) show both
*resolve* outcomes (rewrite "At the time, he led the company's…" → "In 2010, John Smith led
TurboCorp's…") and *discard* outcomes (`Cannot be decontextualized`).

**Context it sees:** `Question` + `Excerpt` (**5 preceding + 0 following**) + target `Sentence`.

### 2.4 Stage 3 — Decomposition (§3.4, `paper_text.md:140-144`; prompt `:958-1058`)

**Job:** split the disambiguated sentence into **decontextualized factual claims**. A proposition
is "decontextualized" iff (1) it is fully self-contained (understandable without the question,
context, or other propositions) AND (2) its isolated meaning matches its in-context meaning; claims
should be "the simplest possible discrete units of information" (`paper_text.md:964`). If no claim
is produced (0.8% of cases) the sentence is labeled "No verifiable claims" (`paper_text.md:142`).

**Decontextualization rules (the explicit ones):**
- **Retain attribution context** — "if the sentence indicates that a specific entity said or did
  something, it is critical that you retain this context"; *"John highlights X"* → keep "John
  highlights"; but *"John's career underscores X"* is interpretation, **not** a verifiable
  proposition (`paper_text.md:982`). (This is the same "Statements and Actions Rule" the
  evaluation enforces at `:1082`.)
- **Bracket inferred essential context with `[...]`** so a fact-checker holding only that one claim
  can still verify it. Each fact-checker is told they will *only* see one proposition — no question,
  no context, no siblings — so all essential clarifications go in brackets (`paper_text.md:1042`).
  Example: *"The local council expects its law to pass in January 2025"* → *"The [Boston] local
  council expects its law [banning plastic bags] to pass in January 2025 – true or false?"*. This
  flags inferred content as inherently less reliable (`paper_text.md:144`).
- **No external knowledge, no citations** (`paper_text.md:986`).
- **Partial-visibility caution:** if the context contains `[...]`, only assume the sentence answers
  the question if strongly implied (`paper_text.md:984`).

**Output format** (`paper_text.md:1032-1048`): echo `Sentence:` → list referential terms needing
clarification → `MaxClarifiedSentence:` (one prose sentence enumerating discrete units, referents
resolved) → an estimated proposition-count range `X-Y` → a first list of decontextualized
propositions → a **final** list "with Essential Context/Clarifications" where each item is
`"<proposition with [...] brackets> -true or false?"`.

**Context it sees:** `Question` + `Excerpt` (**5 preceding + 0 following**) + target `Sentence`.

### 2.5 Reported results vs. prior methods (numbers + metric definitions)

Setup: BingCheck dataset (396 Copilot answers), gpt-4o-2024-08-06, temperature 0, two-proportion
Z-tests with Holm–Bonferroni correction (`paper_text.md:156`, `:185`). Baselines: AFaCTA,
Factcheck-GPT, **VeriScore, DnD, SAFE** (`paper_text.md:164-175`). Methods generated 73,229
de-duplicated claims (`:181`).

**Metric 1 — Entailment** = % of claims entailed by the combined **source sentence + context +
question**, judged by a validated LLM prompt (the pretrained NLI model was rejected for
under/over-classification, `paper_text.md:189`, `:682-684`). Table 1 (`paper_text.md:197-202`):

| Method    | Claims  | %Entailed |
|-----------|---------|-----------|
| **Claimify**  | 12,406 | **99.0** |
| VeriScore | 7,420  | 99.2 |
| SAFE      | 22,786 | 96.6 |
| DnD       | 27,717 | 89.1 |

Claimify vs VeriScore tie (p=0.145); all other pairwise diffs significant (p<0.001)
(`paper_text.md:193`).

**Metric 2 — Coverage** (`paper_text.md:42-54`). **Sentence-level**: does the method correctly
decide a sentence contains ≥1 claim (vs the human annotation study ground truth, 63% of sentences
"verifiable", `paper_text.md:218`). **Element-level** (the paper's novelty): break a sentence into
"elements," label each verifiable/unverifiable, then check whether each is **covered** by the
extracted claims and whether **explicitly or implicitly**. TP = verifiable element covered;
TN = unverifiable element not-covered or only-implicitly-covered; FP = unverifiable element
**explicitly** covered; FN = verifiable element not covered (`paper_text.md:50`). Table 2
(`paper_text.md:207-214`), key columns:

| Method    | Acc. Sent. | Acc. Elem. | macro-F1 Sent. | macro-F1 Elem. |
|-----------|-----------|-----------|----------------|----------------|
| **Claimify**  | **91.8** | **87.9** | **91.2** | **83.7** |
| VeriScore | 79.0 | 64.7 | 78.9 | 62.5 |
| DnD       | 63.7 | 76.9 | 41.4 | 56.2 |
| SAFE      | 65.0 | 74.6 | 45.1 | 57.3 |
| AFaCTA    | 81.6 | — | 78.7 | — |
| Factcheck-GPT | 81.5 | — | 78.0 | — |

Claimify wins every coverage column. Interpretation: it best balances *including* verifiable
content while *excluding* unverifiable content (`paper_text.md:234`).

**Metric 3 — Decontextualization** (`paper_text.md:56-104`). Outcome-based, not a subjective
"is it standalone?" judgment. For each claim `c`: generate `c_max` (maximally decontextualized
version, with `c` entailed by `c_max`) or declare `c = c_max`; retrieve evidence for both; check
veracity; classify into **7 result types** (`paper_text.md:88-94`). **Desirable = types 1, 2, 4, 7**
(verdicts for `c` and `c_max` aligned, or no context was missing) (`paper_text.md:102`,
`:275`). Reported as % desirable over two retrievers (Google `G` / Bing `B`), Table 3
(`paper_text.md:270-275`):

| Method    | Result-1 (c=c_max) | Desirable G | Desirable B |
|-----------|--------------------|-------------|-------------|
| **Claimify**  | **16.3** | **80.6** | 80.5 |
| VeriScore | 13.2 | 78.3 | 79.3 |
| DnD       | 12.9 | 78.4 | 78.6 |
| SAFE      | 10.4 | 78.2 | 78.7 |

Claimify had the most "no missing context" cases (Result-1, p<0.001) and the highest desirable %
(p<0.001 for Google; for Bing it beat all except VeriScore where p=0.159) (`paper_text.md:261`).

**Robustness across models** (Table 8, `paper_text.md:659-674`): macro-averaged over gpt-4o /
mistral-large-2411 / DeepSeek-V3 — Entailment **97.2%**, Element-coverage F1 **78.4%**,
Decontextualization **80.8%**, each the best (or tied-best on entailment) in its row. Conclusion
(`paper_text.md:296-298`): ≥95% entailed across all models, best coverage accuracy+F1, least
likely to omit verdict-critical context.

**Ablation** (Table 4, `paper_text.md:277-284`): full Claimify wins entailment + element-coverage
(p<0.001). Removing **Selection** is the most damaging (element-coverage F1 83.7 → 54.4); "Selection
as detector only" (no rewrite) → 74.7; removing **Disambiguation** → 75.9. Decontextualization is
unaffected by ablations (p>0.05) — i.e. the gain there comes from Decomposition's bracketing, while
coverage/entailment gains come from Selection's verifiability gate + rewrite (`paper_text.md:257`,
`:280-282`).

### 2.6 The naive single-chunk baseline vs. the spec (the anti-pattern E2 must avoid)

The **naive single-chunk baseline** — the extract-everything, FActScore-shaped extractor that ugm's
E2 must NOT become — is a **single structured-output call per chunk** with a ~5-line system prompt
("Extract all atomic project-memory claims from the provided chunk… Return only claims supported by
an exact quote copied from this chunk… Do not infer"). The per-chunk extraction orchestration feeds
**one chunk's text at a time with no neighbors and no question/context**. Its grounding gate is a
**verbatim-substring check**: the verbatim evidence-quote field must be a **verbatim normalized
substring of the chunk**. That strict grounding guard is *incompatible* with Claimify's whole
design, which **rewrites** (Selection), **substitutes referents** (Disambiguation), and emits
**bracketed inferred context** (Decomposition) — none of which are verbatim substrings.

Gaps vs. the spec: (1) **no surrounding context** — chunk is processed in isolation, the exact
failure mode the paper is built to avoid (`paper_text.md:682` shows NLI failing on "However, it was
not implemented until 1998" precisely because the antecedent is in the *preceding* sentence);
(2) **no verifiability/Selection gate** — it extracts from every chunk, the "decompose-everything"
behavior the ablation shows is the single biggest quality loss; (3) **no ambiguity discard** — no
"decline when not confident" path; (4) the verbatim-substring grounding gate structurally **rejects
decontextualized claims**, so any Claimify-style rewrite would be discarded for failing to appear
verbatim in the chunk.

---

## 3. Confidence & gaps

**Confidence: HIGH** for the method spec, the per-stage context windows, the discard rule, the
decontextualization rules, and the headline result numbers — all read **directly** from the paper
text and prompts (`paper_text.md:108-144`, `:579-589`, `:813-1058`, Tables 1-4 + 8) and
cross-checked against three independent reimplementations (`repo_findings/claimify_impls.md`).

What I could **not** fully verify / caveats:
- **Figure 1 / Table contents** were OCR'd to markdown; the *narrative* numbers I quote are from
  the prose and table rows in `paper_text.md`, which are legible and internally consistent (e.g.
  99% / 83.7 / 80.5 recur in §5, §6, Table 8). I did not open the source PDF
  (`claimify_papers/claimify_2502.10855.pdf`) to re-verify pixel-level table cells; the markdown
  tables (`:197-214`, `:270-284`, `:659-674`) are clean enough to trust.
- **"Decontextualization desirable %" is retriever-dependent and absolute differences are small**
  (Claimify 80.6 vs DnD 78.4) — the paper's own claim is "most desirable + significantly more
  Result-1," not a large margin. The decontextualization *advantage* is modest; the **coverage**
  advantage (F1 83.7 vs ≤62.5) is the large, decisive one.
- **The exact min-successes / voting mechanics** are specified in Appendix D prose
  (`paper_text.md:579-589`); I did not see a code listing in the paper for the voting loop (the
  reimplementations implement it variously — `claimsmcp` drops voting entirely,
  `claimify_impls.md:156-158`).
- **Generalization** is single-dataset (BingCheck, LLM long-form QA answers); the authors flag this
  (`paper_text.md:302`) and flag **temporal under-specification** as an unsolved gap — Claimify
  does *not* flag "The unemployment rate decreased in California" (no temporal qualifier) as
  un-disambiguable (`paper_text.md:310`).

---

## 4. Recommendation for ugm (canonical Claimify contract + the design fix)

### 4.1 The canonical Claimify contract to adopt

A faithful ugm E2 should treat claim extraction as **four obligations**, in order, over a
**context-bearing call** — not a one-shot per-chunk extraction:

1. **Context obligation (the non-negotiable one).** The extraction call must see, per target unit:
   the **target chunk/sentence marked**, a **bounded preceding+following window**, and the
   **source/query framing**. Paper canon = 5 preceding/5 following for the verifiability judgment,
   5 preceding/0 following for resolution+decomposition. This directly serves **D19** (coref
   resolved *inside* the E2 call, all languages — the LLM can only resolve "the CEO"/"it" if it
   reads the neighbors) and the E1 **context-prefix** design (`overall_design.md:94`,
   `:101-102`). By design, ugm's E1 chunk model carries the chunk's section-parent reference and
   character offsets, so adjacent chunks of the same section parent are cheaply recoverable as the
   window — **the data to build the excerpt is provided by the chunk model BY DESIGN; the obligation
   is simply to pass it into the E2 call.**
2. **Selection obligation (verifiability gate + rewrite).** Drop opinion/advice/speculation/intro/
   conclusion/lack-of-info; rewrite mixed sentences to keep only verifiable spans. The ablation
   (`paper_text.md:280`) says this is the **single biggest quality lever** — and it is the **only
   claim-level selection analog** to the value gate in the surveyed repos
   (`claimify_impls.md:393`). It is **complementary to, not a replacement for, E1.5 / D25–D30**:
   the **value gate (E1.5) is a CHUNK/section-level salience gate** that decides *whether to run E2
   at all* (`e1_5_value_gate_design.md`, D25); **Selection is a CLAIM-level verifiability gate**
   *inside* E2 that decides *which spans become claims*. ugm needs **both**, at two different
   altitudes — do not conflate them.
3. **Disambiguation obligation (resolve-or-decline).** Resolve referential (incl. temporal) +
   structural ambiguity from question/context; **decline ("cannot be disambiguated") rather than
   guess**. This "defer-don't-fabricate" stance is the same philosophy as D29's **defer-don't-DROP**
   recall envelope and D4's **cheap-first, escalate-on-ambiguity** — and it is the feature *no*
   other surveyed extractor has (`claimify_impls.md:381-383`). Forbid external knowledge
   (`paper_text.md:901-902`) — this is what separates faithful Claimify from Molecular Facts (which
   *requires* world knowledge) and keeps E2 rebuildable/auditable in the **D7/D1** sense (claims
   provenance-stamped to source text, not to model parametric memory).
4. **Decomposition obligation (simplest decontextualized claims, bracketed inferred context).**
   Retain attribution; mark inferred context with `[...]`. Decontextualization is exactly the E2
   property that makes a claim **resolvable to an entity by the T0–T4 cascade (D17)** and
   **normalizable into a relation (D2/E3)** without a dangling pronoun — a `[...]`-bracketed,
   coref-resolved claim is the clean input the downstream registry/relation steps assume.

### 4.2 The concrete design fix (in priority order)

- **FIX #1 — pass context into the extraction call.** The naive single-chunk baseline passes only
  the target chunk text. The E2 design must add the originating source/section framing and a bounded
  window of neighboring chunk text (same section parent, ordered by character offset) rendered as an
  `Excerpt` with the target chunk marked, mirroring the paper's `Question / Excerpt / Sentence`
  template (`paper_text.md:877-887`). Without this, **coref (D19) is unsatisfiable** and the
  isolation failure the paper documents (`:682`) is guaranteed.
- **FIX #2 — relax / re-found the verbatim-quote grounding gate.** A verbatim-substring grounding
  gate (evidence quote must appear literally in the chunk text) is **structurally incompatible**
  with a faithful Claimify pipeline: Selection rewrites, Disambiguation substitutes referents,
  Decomposition adds `[...]` — none are verbatim substrings. Options, cheapest-first (D4 spirit):
  (a) require the verbatim evidence-quote field to be a verbatim span of the **chunk or its context
  window** (not the rewritten claim) and let the claim text be the decontextualized form; or
  (b) replace substring-matching with an **entailment check** (claim entailed by chunk+context),
  which is the paper's *own* validation metric (`paper_text.md:189-191`) and is exactly how it
  scored 99% — substring containment is a cruder proxy that will silently reject correct
  decontextualized claims.
- **FIX #3 — add a claim-level verifiability gate (Selection) before emitting claims**, separate
  from and downstream of the chunk-level value gate (E1.5/D25). Start as the paper's Selection
  prompt; this is the highest-yield single change per the ablation. Keep it **distinct** from
  E1.5 in design and config so the two gates' thresholds are tuned independently (D26/D30).
- **FIX #4 — add the ambiguity-decline path.** Allow E2 to emit *zero* claims for an
  un-disambiguable unit (a first-class outcome, not an error), consistent with **defer-don't-DROP
  (D29)**: the chunk stays in E0/E1, so a future re-extraction with better context can recover it.

**Sequencing note tied to D12/D25.** E0 and E1 always run; the value gate (E1.5) decides FULL vs
DEFERRED vs CHUNKS-ONLY (D25); **only then** does this Claimify-shaped E2 run on FULL/promoted
sections. The four obligations above live *inside* E2 — they refine *how* E2 extracts, they do not
move or duplicate the E1.5 gate. Selection (claim-level) and the value gate (section-level) are two
cheap-first cascades at two altitudes (D4 philosophy applied twice, per D26).
