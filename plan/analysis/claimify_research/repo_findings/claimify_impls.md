# Claimify reimplementations + decontextualization/selection references — repo findings

Scope: 3 Claimify reimplementations + 4 reference systems (Molecular Facts, VeriScore,
FActScore, SAFE). Focus on the two cross-cutting questions:
(1) CONTEXT WINDOW — what text does the extraction LLM actually see per claim?
(2) SELECTION/FILTERING — does it decide WHICH content becomes a claim, or extract everything?
Plus: decontextualization instructions, ambiguity discard rule, grounding/faithfulness, output schema.

All citations are `file:line` for code/prompts and `paper_text.md:line` for the Claimify paper.
VERIFIED = read directly in source. INFERENCE = reasoned from code, flagged.

Primary paper: `claimify_deshwalmahesh/paper_text.md` (markdown of arXiv 2502.10855, Microsoft "Claimify").

---

## 0. Claimify paper — canonical design (the spec the 3 impls target)

Claimify is a **4-stage** "decompose-then-verify" claim extractor that takes a
**question–answer pair** and processes the answer **sentence by sentence**.

VERIFIED canonical context windows (`paper_text.md:112`, `:582-583`):
- `paper_text.md:112`: "Context is created for each sentence s based on a configurable combination of
  **p preceding sentences, f following sentences, and optional metadata** (e.g., the header
  hierarchy in a Markdown-style answer). The parameters p and f are defined separately for the
  stages outlined in §3.2–§3.4, allowing each stage to have a distinct context."
- `paper_text.md:582`: "max_preceding_sentences ... We set it to **5 for all stages**."
- `paper_text.md:583`: "max_following_sentences ... We set it to **5 for the Selection stage and
  0 for the Disambiguation and Decomposition stages**."

So the canonical window is: Selection = 5 preceding + 5 following; Disambiguation/Decomposition
= 5 preceding + 0 following. The window is rendered as an **Excerpt** with `[...]` markers when
not all sentences are shown, and the **target sentence is passed separately** ("Sentence:" field).
The **question** is always in-prompt. This is the crux: every stage LLM sees the target sentence
PLUS a multi-sentence excerpt PLUS the originating question — never the bare sentence alone.

VERIFIED stage roles:
- Selection (§3.2, `paper_text.md:116-124`): per-sentence verifiability gate. LLM picks one of
  3 options: (1) "no verifiable content" → sentence dropped; (2) return a **rewritten** sentence
  retaining only verifiable components; (3) return original (already fully verifiable). This is an
  explicit **selection/filtering** step — it decides which content becomes a claim AND strips
  unverifiable spans out of mixed sentences.
- Disambiguation (§3.3, `paper_text.md:128-136`): decontextualize the sentence — resolve partial
  names, undefined acronyms, referential + structural ambiguity. **Discard rule** (`:136`): "If any
  ambiguity is unresolvable, the sentence is labeled 'Cannot be disambiguated' and excluded from
  the Decomposition stage ... even if it has unambiguous, verifiable components." Special case
  (`:132`): distinguishing factual claims from author interpretation = structural ambiguity.
- Decomposition (§3.4, `paper_text.md:142`): split the disambiguated sentence into the simplest
  decontextualized factual claims, each annotated with `[...]` essential-context brackets so an
  isolated fact-checker can verify it.

Grounding/faithfulness levers (VERIFIED in prompts, see §1.1): "Do NOT use any external knowledge
beyond what is stated in the question, context, and sentence"; "Do NOT include any citations";
the "group of readers would reach consensus" test for disambiguation; voting across completions.

---

## 1. claimify_deshwalmahesh  (faithful single-file port, regex-parsed plain-text prompts)

Files: `claimify_deshwalmahesh/src/prompts.py`, `claimify_deshwalmahesh/src/claimify.py`.
Self-described as a port of the Microsoft paper with minor additions (`claimify.py:1-8`).

### Context window (VERIFIED)
Hyperparameters mirror the paper exactly (`claimify.py:44-49`):
```
self.max_preceding_sentences = 5
self.max_following_sentences_selection = 5
self.max_following_sentences_disambiguation = 0
self.max_following_sentences_decomposition = 0
```
`_create_context` (`claimify.py:196-232`) builds an excerpt = `sentences[start_idx:end_idx]` with
`[...]` prepended if `start_idx>0` and appended if `end_idx<len`. The **target sentence is sent
separately** from the excerpt and the question (user prompt template `claimify.py:242-247`,
identical for all 3 stages):
```
Question:\n{question}\nExcerpt:\n{context}\nSentence:\n{sentence}
```
=> Selection sees target + up to 5 preceding + 5 following + question. Disambiguation &
Decomposition see target + up to 5 preceding + 0 following + question. **Not the bare sentence.**

### Selection / filtering (VERIFIED — yes, it filters)
System prompt `prompts.py:1-46`. It is a verifiability gate, not extract-everything. Key rules:
- `prompts.py:3`: "If the sentence is about a lack of information ... it does NOT contain a specific
  and verifiable proposition."
- `prompts.py:9-14`: MUST consider preceding/following sentences; intros and conclusions do NOT
  contain a verifiable proposition (examples given).
- `prompts.py:16-22`: explicit list of non-verifiable sentence types (opinions, generic advice,
  speculation "AI could lead to advancements in healthcare").
- It also **rewrites** mixed sentences to keep only verifiable content (`prompts.py:24-37` map raw→
  rewritten, e.g. "Smith's advocacy for renewable energy is crucial..." → "Smith advocates for
  renewable energy"). Output keyword "remains unchanged" / "None" handled in parser.
- NOTE the deliberate decoupling (`prompts.py:6`): "It does NOT matter whether the proposition
  contains ambiguous terms ... Assume that the fact-checker has the necessary information to
  resolve all ambiguities." → Selection judges verifiability only; ambiguity is deferred to stage 3.
Output format (plain text, regex-parsed `_parse_selection_response` `claimify.py:305-372`):
4-step thought process → `Final submission:` (Contains / Does NOT contain) → `Sentence with only
verifiable information:` (rewritten | "remains unchanged" | "None").
Voting: 3 completions, min 2 successes, temp 0.2 (`claimify.py:54-55`, `:260`).

### Disambiguation / decontextualization (VERIFIED)
System prompt `prompts.py:49-97`. Two jobs: (1) resolve partial names + undefined acronyms using
question+context; (2) resolve referential + structural (incl. temporal) ambiguity. Hard rules:
- `prompts.py:56`: "Vagueness and generality are NOT linguistic ambiguity."
- `prompts.py:58`: full name from question/context MUST be substituted; missing full name does NOT
  count as ambiguity (leave as-is).
- `prompts.py:60`: "Do NOT use any external knowledge beyond what is stated in the question,
  context, and sentence." (faithfulness lever — contrast Molecular Facts which DOES use world knowledge.)
- **Discard rule** = the "group of readers would likely fail to reach consensus" test (`prompts.py:96`):
  if readers can't agree on the interpretation → output `DecontextualizedSentence: Cannot be
  decontextualized` and the sentence is dropped (`claimify.py:123-124`, parser `:445-514`).
Voting: 3 completions, min 2, temp 0.2.

### Decomposition (VERIFIED)
System prompt `prompts.py:99-184`. Produces "the simplest possible discrete units of information,"
each fully decontextualized. Notable instructions:
- `prompts.py:119`: retain attribution context ("if the sentence indicates a specific entity said/
  did something ... retain this context"); distinguishes "John highlights X" (claim) from "John's
  career underscores X" (NOT verifiable).
- `prompts.py:121`: `[...]` in context → only assume the sentence answers the question if strongly
  implied (faithfulness under partial visibility).
- Output (plain text, `claimify.py:568-642`): a final list "Specific, Verifiable, and
  Decontextualized Propositions with Essential Context/Clarifications" where each claim carries
  `[...]` brackets and a `- true or false?` suffix (parser strips both). 1 completion, temp 0
  (`claimify.py:56-57`, `:542`).
Pipeline glue: `extract_claims` (`claimify.py:59-149`) runs Selection→Disambiguation→Decomposition
per sentence, short-circuiting on `no_verifiable_claims` / `cannot_disambiguate` / empty claims.

---

## 2. claimify_claimsmcp  (structured-output port; Pydantic-enforced JSON; MCP server)

Files: `claimify_claimsmcp/structured_prompts.py`, `structured_models.py`, `pipeline.py`.
Same 3 Claimify stages but with simplified prompts + JSON schemas (structure enforced by Pydantic
rather than text format keywords), and an added multilingual requirement.

### Context window (VERIFIED — DIVERGES from the paper for disambiguation/decomposition)
`pipeline.py` builds context with `create_context_for_sentence(sentences, i, p, f)`
(`pipeline.py:56-80`) which returns `"\n".join(sentences[start:end])` — note: **NO `[...]`
markers are inserted here** (unlike impl #1 and the paper), though prompts still mention `[...]`.
The pipeline calls it with a **fixed p=5, f=5 for ALL THREE stages** (`pipeline.py:377` async,
`pipeline.py:445` sync — comment "Using a fixed context window as per the paper's experiments").
=> This is a FAITHFULNESS DEVIATION: the paper sets f=0 for Disambiguation/Decomposition
(`paper_text.md:583`); claimsmcp gives all stages 5 preceding + **5 following**. So its
disambiguation/decomposition LLM sees MORE forward context than canonical Claimify.
User prompt identical shape to impl #1 (`pipeline.py:96`, `:152`, `:203`):
`Question:\n{question}\n\nExcerpt:\n{excerpt}\n\nSentence:\n{sentence}` — target sentence still
passed separately, question always present. **Not the bare sentence.**

### Selection / filtering (VERIFIED — yes, it filters)
`structured_prompts.py:7-60`. Same verifiability-gate logic + rewrite rules as impl #1
(`:11-16` rules, `:18-23` intro/conclusion, `:25-31` non-verifiable list, `:33-45` rewrite map).
Adds a CRITICAL LANGUAGE REQUIREMENT (`:9`) to answer in source language for content but keep
keywords English. Output schema (`structured_models.py:10-26`): `SelectionResponse{sentence,
thought_process, final_submission: Literal["Contains...","Does NOT contain..."],
sentence_with_only_verifiable_information: str|None}`. Parser `pipeline.py:111-136`: maps
"remains unchanged" → original, "none" → unverifiable, else → rewritten.
NOTE: `pipeline.py` runs **a single structured request per stage** (`make_structured_request`) —
there is no voting/min-successes loop here (unlike impl #1 and impl #3). INFERENCE: structured
JSON reliability is being traded for the paper's multi-completion voting.

### Disambiguation (VERIFIED)
`structured_prompts.py:62-122`. Same decontextualization rules + consensus discard test (`:106`:
"If a group of readers ... would likely fail to reach consensus ... then the sentence 'Cannot be
decontextualized'"). Schema (`structured_models.py:29-48`): `DisambiguationResponse{
incomplete_names_acronyms_abbreviations, linguistic_ambiguity_analysis, changes_needed: str|None,
decontextualized_sentence: str|None}`. Parser `pipeline.py:167-187`: literal
"Cannot be decontextualized" → dropped.

### Decomposition (VERIFIED)
`structured_prompts.py:124-184`. Same atomic-proposition + `[...]`-bracket-clarification logic
as impl #1. Schema (`structured_models.py:51-86`): `DecompositionResponse{sentence,
referential_terms, max_clarified_sentence, proposition_range, propositions: list[str],
final_claims: list[Claim]}` where `Claim{text, verifiable: bool=True}`. Final output =
`[claim.text for claim in final_claims]` (`pipeline.py:218-232`). The `verifiable: bool` field is
prompt-described as "Always set to true (this helps you focus on creating claims that can be
fact-checked)" (`structured_prompts.py:154-157`) — i.e. a thinking aid, not a real filter at this
stage; filtering already happened in Selection.
Pipeline de-dups final claims (`pipeline.py:413`, `:481`).

---

## 3. claimeai  (LangGraph port; adds a 5th VALIDATION stage; structured outputs + voting)

Files: `claimeai/apps/agent/claim_extractor/{prompts.py,schemas.py,nodes/*,config/nodes.py,utils/text.py}`.
5 nodes: sentence_splitter → selection → disambiguation → decomposition → **validation**.

### Context window (VERIFIED — paper-faithful, but built once then trimmed per stage)
Context is built ONCE in the splitter and reused. `config/nodes.py:30-43` `CONTEXT_WINDOWS`:
- selection: 5 preceding, 5 following
- disambiguation: 5 preceding, 0 following
- decomposition: 5 preceding, 0 following  (matches `paper_text.md:582-583`).
Mechanism: `sentence_splitter_node` builds `context_for_llm` for every sentence using the
**selection** window (5+5) (`nodes/sentence_splitter.py:144-153`). The context string is labeled
markup (`sentence_splitter.py:89-113`):
```
[Document Metadata: ...]            (only if metadata)
[Preceding Sentences:] <up to 5>
[Sentence of Interest for current task:] <sentence>
[Following Sentences:] <up to 5>
```
Disambiguation and Decomposition then call `remove_following_sentences(context_for_llm)`
(`utils/text.py:11-36`) which splits on the `\n[Following Sentences:]` marker and keeps only the
prefix → effectively forces f=0 for those two stages (`nodes/disambiguation.py:57-59`,
`nodes/decomposition.py:53-57`). So the realized windows match the paper. The
**original sentence is also passed separately** as `{sentence}` via `HUMAN_PROMPT`
(`prompts.py:3-8`: "Excerpt:\n{excerpt}\nSentence:\n{sentence}"). **Not the bare sentence.**
CAVEAT (VERIFIED bug, low impact): `sentence_splitter.py:61` splits paragraphs on the literal
2-char string `"\\n"` (escaped backslash-n), not a real newline `"\n"`; the deshwalmahesh and
claimsmcp ports split on real `"\n"`. INFERENCE: claimeai will usually treat the whole input as
one paragraph unless it literally contains backslash-n, slightly changing sentence boundaries.
Also unique: short fragments (<5 chars) are merged forward (`sentence_splitter.py:69-83`).

### Selection / filtering (VERIFIED — yes, it filters)
Prompt `prompts.py:17-68`. Same verifiability gate as the paper (`:21-24` rules, `:26-31`
intro/conclusion, `:33-39` non-verifiable list, `:41-54` rewrite map). NOTE this port's selection
prompt **drops the "question"** framing — it is phrased purely as "an excerpt from a text" and
"a particular sentence of interest from the text" (`prompts.py:18`); the disambiguation and
decomposition prompts likewise say "the context" without a question (`prompts.py:71`, `:122`).
INFERENCE: claimeai is question-agnostic at the prompt level; the originating question is not a
first-class input the way it is in impl #1/#2 and the paper. Schema (`nodes/selection.py:24-35`):
`SelectionOutput{processed_sentence: str|None, no_verifiable_claims: bool, remains_unchanged: bool}`.
Voting: 3 completions, min 2, temp 0.2 (`config/nodes.py:7-11`, `nodes/selection.py:128-139`
via `process_with_voting`).

### Disambiguation (VERIFIED)
Prompt `prompts.py:70-119`. Same name/acronym + referential/structural rules + consensus test;
"Do NOT use any external knowledge beyond ... the context and sentence" (`:79`). Schema
(`nodes/disambiguation.py:30-38`): `DisambiguationOutput{disambiguated_sentence: str|None,
cannot_be_disambiguated: bool}`. **Discard rule** enforced in code (`nodes/disambiguation.py:81-88`,
comment "better to drop them than have unclear claims"). Voting 3/min-2/temp 0.2.

### Decomposition (VERIFIED)
Prompt `prompts.py:121-180`. Same atomic-claim + `[...]`-bracket logic. NOTE `prompts.py:135`
softens the paper's "directly answering the question" rule (no question here) to "focus on
extracting claims that are self-contained based on the available context." Schema
(`nodes/decomposition.py:25-33`): `DecompositionOutput{claims: list[str], no_claims: bool}`.
1 completion, temp 0 (`config/nodes.py:19-23`). Runs all disambiguated sentences in parallel
(`nodes/decomposition.py:124-132`).

### Validation (VERIFIED — extra 5th stage, NOT in the paper's pipeline proper)
Prompt `prompts.py:182-200`: given a claim C in isolation, decide "C is a complete, declarative
sentence" or not. Schema (`nodes/validation.py:18-23`): `ValidationOutput{is_complete_declarative:
bool}`. `validation_node` (`nodes/validation.py:74-115`) drops claims that are not complete
declarative sentences AND de-dups. INFERENCE: this is a syntactic well-formedness filter on the
final claims (the paper mentions a similar entailment/validity notion only in its evaluation
appendix, not as a generation stage). Final state object `schemas.py:82-105` accumulates
`validated_claims`.

---

## 4. Reference systems — decontextualization + selection contrasts

### 4A. VeriScore  (verifiable-ONLY; single-prompt classify+decompose+decontextualize)
Files: `veriscore/veriscore/claim_extractor.py`, `veriscore/prompt/extraction_qa_template.txt`,
`extraction_non_qa_template.txt`. Paper cross-ref `paper_text.md:171` ("combines sentence
classification, decomposition, and decontextualization in a **single prompt**. It returns either
'No verifiable claim' or a list of claims") and `paper_text.md:603` ("The context consists of
**three preceding sentences and one following sentence**").

- CONTEXT WINDOW (VERIFIED): per-sentence snippet. `qa_scanner_extractor`
  (`claim_extractor.py:101-155`) / `non_qa_scanner_extractor` (`:36-99`): split with spaCy, then
  `context1 = sentences[max(0,i-3):i]` (up to **3 preceding**), focus sentence wrapped
  `<SOS>...<EOS>`, `context2 = sentences[i+1:i+2]` (**1 following**). For non-QA, if the paragraph
  has >5 sentences the **lead/1st sentence** is also prepended (`:67-68`). QA variant prepends the
  **question** (`:125`). So the extractor LLM sees: focus sentence (marked) + ~3 preceding + 1
  following (+ lead sentence for long paras) (+ question for QA). **Not the bare sentence.**
- SELECTION/FILTERING (VERIFIED — strongly verifiable-only): prompt
  `extraction_qa_template.txt:1` / `extraction_non_qa_template.txt:1`: "Any **story, personal
  experiences, hypotheticals** (e.g., 'would be' or subjunctive), **subjective statements** (e.g.,
  opinions), **suggestions, advice, instructions** ... should not be included." Each fact must be
  "verifiable against reliable external world knowledge (e.g., via Wikipedia)" and describe a
  single event/state with time+location. If nothing qualifies → literal "No verifiable claim."
  (`claim_extractor.py:183-184`, `:194-195`). This is selection FUSED into the same call as
  decomposition (no separate stage).
- DECONTEXTUALIZATION (VERIFIED): instructed inline (`extraction_qa_template.txt:3`): "Other
  sentences are only context for you to recover pronouns, definite phrases (e.g., 'the victims' or
  'the pope') ... all entities must be referred to by name but not pronoun. Use the name of
  entities rather than definite noun phrases ... Each fact must be situated within relevant
  temporal and location." QA variant adds "always relate the extracted claims to the question."
- GROUNDING: "Do not extract claims from the question" (QA); quotations verbatim with source;
  listed references ignored. No discard-on-ambiguity rule (single shot).
- OUTPUT: newline-separated claim strings (parsed `claim_extractor.py:197-201`), de-duplicated
  across the response (`:85-96`, `:141-152`). No schema object.

### 4B. FActScore  (decompose-EVERYTHING; sentence-only context; no verifiability filter at extraction)
Files: `factscore/factscore/atomic_facts.py`. Paper cross-ref `paper_text.md:173`, `:392`.

- CONTEXT WINDOW (VERIFIED — narrowest): the extraction prompt operates on **ONE sentence at a
  time** with **NO surrounding document context**. `get_init_atomic_facts_from_sentence`
  (`atomic_facts.py:96-145`) builds the prompt from (a) `n` fixed in-context demonstration
  sentences (n=7 for bio) + (b) `k`=1 BM25-retrieved demo most similar to the target
  (`:111`, `:148-151`) + (c) the literal instruction `"Please breakdown the following sentence
  into independent facts: {sentence}"` (`:125`). The demos are unrelated example sentences, NOT
  neighbors from the same passage. => The LLM never sees the target sentence's neighbors,
  document, summary, or question. This is the maximal de-contextualization risk.
- SELECTION/FILTERING (VERIFIED — essentially none at extraction): the prompt is
  "breakdown ... into independent facts" — it decomposes everything; there is no verifiable-vs-
  unverifiable judgment in the extraction prompt. Filtering that exists is heuristic post-
  processing, not content selection: boilerplate-sentence skipping ("Sure"/"Here are"/"Please"/
  "I hope") (`atomic_facts.py:64-84`) and entity-based fact cleanup in `postprocess_atomic_facts`
  (`:232-289`). INFERENCE: FActScore's design assumption is that generated bios are dense with
  verifiable facts, so it extracts atomic facts wholesale and defers veracity to retrieval.
- DECONTEXTUALIZATION: NOT done in this extraction step (the demos show coref already resolved,
  but no explicit "resolve pronouns from context" instruction and no context to resolve from).
- OUTPUT: `atomic_facts_pairs = list[(sentence, [facts])]` + `para_breaks` (`:73-93`); facts parsed
  from `- `-bulleted InstructGPT output via `text_to_sentences` (`:155-163`).

### 4C. SAFE  (decompose-everything via FActScore, THEN separate revise + relevance filter)
Files: `safe_long_form_factuality/eval/safe/get_atomic_facts.py`, `eval/safe/classify_relevance.py`.
Paper cross-ref `paper_text.md:173` ("SAFE adds instructions to FActScore's decomposition prompt
... and performs decontextualization in a **separate prompt**") and `paper_text.md:609` ("SAFE
uses the **entire response as context** during decontextualization").

- SPLITTING context window (VERIFIED): SAFE reuses FActScore's `AtomicFactGenerator`
  (`get_atomic_facts.py:20-21`, `:37-41`) → same **sentence-at-a-time, neighbor-free** split as 4B.
- DECONTEXTUALIZATION context window (VERIFIED — widest of all): `revise_fact`
  (`classify_relevance.py:252-272`) feeds the `_REVISE_FORMAT` prompt (`:105-224`) the atomic
  STATEMENT plus the **entire RESPONSE** as context (`main` passes `response=response`,
  `:275-286`). So SAFE's decontextualizer sees the WHOLE document — claims may incorporate info
  from far beyond the source sentence (the paper flags this as why SAFE claims can over-reach,
  `paper_text.md:609`, `:723-729`). Instruction: replace vague references (pronouns, unknown
  entities, non-full names) with the proper entity FROM THE RESPONSE; "You MUST NOT change/add any
  factual claims" (`classify_relevance.py:117-118`) — a faithfulness guard. Output wrapped in a
  markdown code block (`:126-127`, parsed `:267-269`).
- SELECTION/FILTERING (VERIFIED — relevance filter, applied AFTER extraction): `check_relevance`
  (`classify_relevance.py:227-249`) uses `_RELEVANCE_FORMAT` (`:31-104`) to decide whether the
  atomic fact's subject is related ("Foo") to the QUESTION's subject, given the response; irrelevant
  facts are dropped. This is a relevance filter, NOT a verifiability/opinion filter (contrast
  VeriScore which drops opinions/advice at extraction, and Claimify which drops unverifiable spans).
  NOTE default-on-failure assumes relevant (`:248-249` "if no parsed answer, assume relevant").
- So SAFE = decompose-everything (FActScore) + per-claim decontextualize-against-full-response +
  per-claim relevance gate. No ambiguity-discard rule; ambiguous facts get best-effort revised.

### 4D. Molecular Facts  (post-hoc disambiguation of already-decontextualized claims; uses WORLD KNOWLEDGE)
Files: `molecular_facts/src/pipeline_molecular_gpt4.py`, `src/prompts/molecular_prompt.py`,
`src/prompts/decontext_prompt.py`. (Paper: arXiv 2406.20079, "Molecular Facts".)

- INPUT: operates on facts that are ALREADY decontextualized (`decontext_gpt4` field,
  `pipeline_molecular_gpt4.py:89-96`). It does not split sentences itself; it refines a fact's
  "molecularity" (right amount of standalone disambiguating detail).
- CONTEXT WINDOW (VERIFIED — full passage + world knowledge):
  - Stage 1 `ambiguity_check` (`pipeline_molecular_gpt4.py:42-63`, prompt
    `molecular_prompt.py:1-60`): sees the **claim ALONE** (no passage). Identifies the SUBJECT and
    enumerates real-world homonyms **from the model's own world knowledge** ("Utilize your world
    knowledge to enumerate potential DISAMBIGUATIONS") → returns
    `{subject, disambiguation_criteria}` (e.g. "Occupation or Nationality"). This is the explicit
    DEPARTURE from Claimify/SAFE faithfulness, which forbid external knowledge.
  - Stage 2 `decontextualize_ambiguity` (`pipeline_molecular_gpt4.py:24-39`, prompt
    `molecular_prompt.py:63-131`): sees the claim + the `{subject, disambiguation_criteria}` dict +
    the **full CONTEXT = `context = elem['llm_gen']`**, i.e. the entire LLM generation
    (`pipeline_molecular_gpt4.py:79`, `:96`). It substitutes pronouns/partial names AND injects the
    one distinguishing detail (profession/location/lifespan) the criteria call for, drawn from the
    context — "Should not omit information," "Should only minimally modify" (`molecular_prompt.py:68-69`).
- SELECTION/FILTERING: none — it transforms every input fact; it does not drop opinions/boilerplate
  (that filtering is assumed to have happened upstream in the decontext_gpt4/SAFE pipeline).
- ALSO PRESENT (reference decontextualizers, VERIFIED): `decontext_prompt.py` contains
  `DECONTEXT_PROMPT` (`:1-76`, classic context→standalone-claim, 7 worked examples) and a verbatim
  copy of SAFE's revise prompt `SAFE_DECONTEXT_PROMPT` (`:79-198`) — both pass the full passage as
  CONTEXT/RESPONSE and resolve vague references against it.

---

## 5. Cross-method summary — the two crux questions

| System | Context window the extraction LLM sees | Selection: which content becomes a claim? |
|---|---|---|
| Claimify (paper / impl #1 deshwalmahesh) | Target sentence + question + excerpt: 5 prec/5 foll (Selection), 5 prec/0 foll (Disamb/Decomp), with `[...]` markers | YES — explicit Selection stage drops non-verifiable sentences AND strips unverifiable spans; Disamb drops unresolvable-ambiguity sentences |
| Claimify impl #2 (claimsmcp) | Target + question + 5 prec/**5 foll for ALL stages** (deviation; no `[...]` markers inserted) | YES — same Selection gate; single call per stage (no voting) |
| Claimify impl #3 (claimeai) | Target + 5 prec/5 foll (Sel), 5 prec/0 foll (Disamb/Decomp via `remove_following_sentences`); **question-agnostic**; +5th validation stage | YES — Selection gate + Disamb discard + final complete-declarative-sentence filter |
| VeriScore | Target sentence (`<SOS>..<EOS>`) + ~3 prec / 1 foll (+ lead sent for long paras) (+ question for QA) | YES, verifiable-ONLY, FUSED into one prompt — drops stories/opinions/advice/hypotheticals; "No verifiable claim" |
| FActScore | **Single sentence only**, NO neighbors/doc — just BM25 demo + fixed demos | NO real filter — decompose-EVERYTHING into atomic facts; only boilerplate-line skipping |
| SAFE | Split: single sentence (FActScore). Decontextualize/revise: **ENTIRE RESPONSE** as context | Decompose-everything (FActScore) + post-hoc **relevance** filter (not verifiability) |
| Molecular Facts | Stage1: claim alone + **world knowledge**. Stage2: claim + **full passage** | NO selection — refines every input fact's disambiguation granularity |

Key faithfulness/decontext contrasts:
- "Verifiable-only at extraction": VeriScore + Claimify-Selection. "Decompose-everything":
  FActScore + SAFE (SAFE filters later, by relevance not verifiability). (`paper_text.md:171-175`.)
- Decontext context breadth: FActScore = none (riskiest) < Claimify = 5 preceding sentences
  < SAFE / Molecular Facts = entire response (`paper_text.md:609`).
- External knowledge: Claimify FORBIDS it ("Do NOT use any external knowledge", all 3 impls);
  Molecular Facts REQUIRES it for homonym disambiguation (`molecular_prompt.py:11`).
- Ambiguity discard rule (drop the unit): only Claimify (the "group of readers fail to reach
  consensus" → "Cannot be decontextualized"). VeriScore/FActScore/SAFE/Molecular do best-effort
  revision instead of dropping.

### Relevance to ugm design (per design context, INFERENCE)
- ugm E2 = "Claimify+coref": of the 3 ports, claimeai is the only one matching the paper's exact
  per-stage windows (5/5 → 5/0) while being question-agnostic; claimsmcp deviates (5/5 everywhere);
  deshwalmahesh is the closest line-by-line transcription of the paper prompts.
- E1 context-prefix / D19 coref-in-call: SAFE and Molecular Facts demonstrate the "feed the whole
  surrounding text as context, resolve refs in one call" pattern; Claimify demonstrates the
  bounded-window (p/f sentences) + consensus-discard pattern. The CHUNK-level value gate (E1.5,
  D25-D30) is a distinct earlier filter; the only CLAIM-level selection analog in these repos is
  Claimify's Selection stage (verifiability) and SAFE's relevance gate.
