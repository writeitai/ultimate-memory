# C3 — Diagnosis of the naive single-chunk baseline extractor vs Claimify

**Question.** Diagnose the naive single-chunk baseline claim extractor — the extract-everything,
FActScore-shaped anti-pattern that ugm E2 must avoid — against Claimify's 4-stage design. Enumerate
every way it causes de-contextualization or junk; map each defect to the Claimify stage/mechanism
that fixes it; conclude with a prioritized defect list.

**Method.** Characterized the naive single-chunk baseline as a design anti-pattern; cross-referenced
against the Claimify paper (`claimify_deshwalmahesh/paper_text.md`), the three reimplementations
(repo_findings `claimify_impls.md`), and the ugm design/decision log. Paper and public-repo
citations are `file:line`; baseline behavior is described conceptually as the anti-pattern E2 must
not reproduce.

---

## 1. Key findings (bullets)

- **The naive single-chunk baseline is a single-stage "decompose-everything-on-one-chunk" extractor
  — it implements roughly the *opposite* of Claimify on every axis.** It has **no Selection gate, no
  Disambiguation discard, no Decomposition-with-essential-context bracketing, and no inter-sentence
  context window.** Claimify is 4 stages over a question + multi-sentence excerpt; the baseline is 1
  LLM call over one isolated chunk with a 5-line prompt.

- **Defect (a) — single-chunk isolation → unresolved refs/time → non-standalone or wrong claims.**
  The extraction orchestration feeds **exactly one chunk, no neighbors, no document, no
  question/title** (the per-chunk extraction orchestration runs once per chunk; the user message is
  only the chunk id + evidence id + chunk text). Claimify *always* gives every stage the target
  sentence **plus p preceding + f following sentences + the originating question**
  (`paper_text.md:112`, `:582-583`). The ugm chunk model already carries the chunk's section-parent
  reference and character offsets — so the neighbor-fetch is mechanically available by design and
  must not be left unused. Leaving it unused directly contradicts ugm **D19** (coref satisfied
  *inside* the E2 call) and the E1/E2 design line "context prefix … coref" (`overall_design.md:17-18`,
  `:101`): coref cannot be satisfied in-call when the call cannot see the antecedent.

- **Defect (b) — the verbatim-substring grounding gate is hostile to decontextualization.**
  The verbatim-substring grounding gate rejects any claim whose evidence-quote field is not a
  normalized substring of the *single* chunk. A genuinely decontextualized rewrite ("Stephen Miller
  advocates for renewable energy") is **not** a substring of a chunk that said "He advocates for it",
  so the contract forces one of two bad outcomes: the model keeps claims **contextual (pronouns,
  "it", "the policy", "next year") to pass the check**, or good standalone claims **get silently
  dropped** (rejected claims are simply skipped). This is the single most damaging defect: it is a
  structural incentive *against* the very property (standalone claims) the system says it wants. It
  also can never validate a cross-sentence/cross-chunk decontextualization because the quote search
  is scoped to the single chunk's text only.

- **Defect (c) — "extract ALL atomic claims" with no verifiability Selection → opinions /
  boilerplate / unverifiable become claims.** The baseline's system prompt says **"Extract all atomic
  project-memory claims"** with no instruction to drop non-verifiable content. Claimify's Selection
  stage (`paper_text.md:116-124`) is exactly the missing gate: it drops sentences with no verifiable
  proposition and **rewrites mixed sentences to keep only the verifiable span**. Worse, the baseline
  schema *invites* junk: its claim-kind labels include preference, observation, and relationship
  kinds, and the extracted-claim schema carries a free `confidence` float — there is no filter that
  turns low-verifiability/low-confidence output into a discard. This is the per-claim analog of the
  gap ugm already accepted at chunk level in **D25–D30**; the value gate is CHUNK/section-level
  (`e1_5_value_gate_design.md:43-45`) and does **not** substitute for claim-level Selection.

- **Defect (d) — no Disambiguation discard → the model guesses on ambiguous text.** There is no
  stage that detects unresolvable referential/structural ambiguity and labels it "Cannot be
  disambiguated" (`paper_text.md:128-136`, discard rule `:136`). With only one isolated chunk and a
  "do not infer" instruction, the model faces ambiguous spans with *no* context to resolve them and
  *no* sanctioned way to abstain — so it either fabricates a resolution or emits a still-ambiguous
  claim. Claimify's "group of readers would reach consensus" test (`paper_text.md:134`) is the
  precise mechanism absent here.

- **Defect (e) — claim id derived from claim text + per-chunk support → fragile identity and
  no cross-chunk dedup.** The content-derived claim-id function hashes the raw claim text scoped to
  one chunk (keyed on evidence id + chunk id + claim text), and the supporting chunk ids / supporting
  evidence ids are always the single originating chunk. Consequences: (1) the same fact stated in two
  chunks produces **two different claim ids** (different chunk id in the hash) → no convergence,
  defeating the **D2** "N documents → one fact, N evidence rows" redundancy-collapse premise and the
  free `evidence_count` signal (**D2**, `decisions.md:29-45`); (2) because the id is keyed on the
  *raw* claim text, any decontextualization rewrite changes the id, so a fix to defect (b)/(a) churns
  ids; (3) a trivial wording change = a new "claim".

- **Net effect.** The baseline pipeline maximizes *recall of raw atomic statements tied to one chunk*
  and actively penalizes *standalone, verifiable, deduplicated* claims — the inverse of what E2 is
  specified to produce. Claimify's four stages map 1:1 onto the four behavioral defects (a)→context
  creation, (c)→Selection, (d)→Disambiguation, plus Decomposition's bracket notation as the
  reconciliation for (b).

---

## 2. Evidence & detail with citations

### 2.0 What the naive single-chunk baseline actually is

One structured-output LLM call per chunk:

- System prompt, full text: *"Extract all atomic project-memory claims from the provided chunk.
  Trust the chunk boundary exactly as given. Do not split or merge chunks. Return only claims that
  are directly supported by an exact quote copied from this chunk. Do not infer facts that are not
  stated in the chunk."*
- User message: only the chunk id, evidence id, and chunk text. **No question, no title, no
  neighboring chunks, no preceding/following sentences, no metadata.**
- Output schema: an extraction-result wrapper `{claims: list[...]}` where each extracted claim
  carries a claim-text field, a claim-kind label, a verbatim evidence-quote field, and a
  `confidence` float.
- The per-chunk extraction orchestration iterates chunks independently; the unit of work is one
  chunk model (the extraction protocol takes a single chunk); concurrency just runs more *isolated*
  chunks in parallel — it never widens any single call's context.

Contrast Claimify canonical shape (repo_findings `claimify_impls.md:21-53`; `paper_text.md:106-148`):
4 stages (Selection → Disambiguation → Decomposition; the paper's pipeline) over a
**question + excerpt(p preceding / f following) + target sentence**, with two discard points and
essential-context bracket notation. The baseline collapses all of this into a single "breakdown into
facts" call — which `claimify_impls.md:284-306` identifies as the **FActScore** shape
(single-sentence, neighbor-free, no verifiability filter, "the maximal de-contextualization risk"),
except the baseline is even thinner (no in-context demos, no decontextualization instruction at all).

### 2.1 Defect (a): single-chunk isolation (maps to Claimify §3.1 Context Creation + §3.3 Disambiguation; ugm D19)

- The anti-pattern is per-chunk isolation in orchestration and in the call payload: no code path
  assembles neighbors despite the chunk's character offsets and section-parent reference being
  available by design on every chunk record.
- Claimify mechanism that fixes it: **Context Creation** — "Context is created for each sentence s
  based on … p preceding sentences, f following sentences, and optional metadata"
  (`paper_text.md:112`); canonical p=5 all stages, f=5 Selection / f=0 Disamb+Decomp
  (`paper_text.md:582-583`). The target sentence is passed *separately* from the excerpt and the
  question is *always* in-prompt (`claimify_impls.md:32-34`, `:74-78`).
- Symptom: a chunk reading "He shipped it in Q3 after the outage" yields a claim with unresolved
  `he`/`it`/`Q3`/`the outage` — exactly the referential-ambiguity class Claimify names
  (`paper_text.md:130`, "They will update the policy next year"). The model literally cannot resolve
  these because the antecedents live in neighboring chunks it never sees.
- ugm tie: **D19** (`decisions.md:384-398`) requires coref to be satisfied *inside* the E2 call for
  all languages — "the LLM reads the chunk/document and writes claims with referents resolved." A
  single-chunk call cannot honor D19 because it is handed only one chunk. The fix is **not** a new
  model (D19 forbids that); it is widening the *input* of the E2 call to the document/section +
  neighbors (the `overall_design.md:17` "ctx prefix" / contextual-retrieval lever, and D19's
  "reads the chunk/document").

### 2.2 Defect (b): verbatim-substring grounding gate is hostile to decontextualization (maps to Claimify §3.4 Decomposition bracket notation; ugm D7/D2)

- The verbatim-substring grounding gate rejects unless the normalized evidence-quote field is
  contained in the normalized chunk text (normalization = whitespace-collapse + casefold), scoped to
  **one chunk's text**. Rejected claims are dropped.
- The contradiction: the system prompt simultaneously demands "an exact quote copied from this chunk"
  AND (implicitly, per E2's purpose) standalone claims. These are mutually exclusive for any claim
  needing a pronoun/temporal/entity rewrite — a decontextualized rewrite is by definition **not a
  substring** of the source. So the gate either (i) trains the model to keep the claim text close to
  the surface form (contextual, with pronouns intact) so the quote matches, or (ii) silently deletes
  the good standalone claims. Both are bad; (i) is the likely steady state because the model
  optimizes to pass.
- Claimify mechanism that reconciles grounding with decontextualization: **Decomposition emits the
  claim with bracketed essential context**, e.g. `John [a celebrity] has called for peace [in the
  Middle East]` (`paper_text.md:144`). The *unbracketed* spans remain traceable to the source while
  the *bracketed* spans flag inferred/contextual additions — "a benefit of bracketing is that it
  flags inferred content, which is inherently less reliable" (`paper_text.md:144`). The right
  grounding contract is therefore **claim-is-entailed-by / faithful-to the source span**, NOT
  claim-text-contains-verbatim-quote. The verbatim evidence-quote field is fine as a *provenance
  pointer*; it must not gate on being a literal substring of the rewritten claim, and it must be
  allowed to point at the **neighbor/section** text once (a) is fixed.
- ugm tie: keeping a verbatim quote *pointer* is compatible with **D7/D1** auditability (store the
  span you grounded on); making *acceptance* require substring-of-chunk is what breaks. INFERENCE:
  the safe replacement is "the evidence-quote field must be a verbatim span of the **context actually
  shown to the extractor** (chunk ∪ neighbors), and the claim must be faithful to it" — not "the
  claim text is a superset of the quote."

### 2.3 Defect (c): "extract ALL atomic claims", no Selection (maps to Claimify §3.2 Selection; ugm D25–D30 are chunk-level, NOT this)

- The baseline prompt says "Extract **all** atomic project-memory claims"; the only guards are
  "directly supported by an exact quote" and "do not infer" — both are *grounding* guards, neither is
  a *verifiability/check-worthiness* gate. Nothing instructs the model to drop opinions, generic
  advice, speculation, intros/conclusions, or boilerplate.
- Claimify mechanism: **Selection** (`paper_text.md:116-124`) is a per-sentence verifiability gate
  with three outcomes — (1) "no verifiable content" → drop; (2) rewrite to keep only verifiable
  spans; (3) keep as-is. The reimplementations enumerate the non-verifiable types to drop (opinions,
  generic advice, speculation, intros/conclusions) and provide raw→rewritten maps
  (`claimify_impls.md:80-96`, `:148-158`, `:212-222`). VeriScore fuses the same filter
  ("story, personal experiences, hypotheticals, subjective statements, suggestions, advice …
  should not be included", `claimify_impls.md:266-273`).
- Symptom in the baseline schema: preference / observation / relationship claim-kind labels plus a
  `confidence` float mean opinionated/subjective material is *first-class output*, not filtered. A
  chunk of meeting boilerplate ("Thanks everyone, great call, let's circle back") yields claims.
- ugm tie / IMPORTANT distinction: **D25–D30** add a value/salience gate, but it is **chunk/section-
  level (E1.5), gating whether to *pay for E2 at all*** (`e1_5_value_gate_design.md:43-45`,
  `decisions.md:485-501`). That is upstream and coarse. The **claim-level Selection** gate Claimify
  provides has **no analog in ugm yet** — `value_gate_research/SYNTHESIS.md` and the design note that
  "the only CLAIM-level selection analog in these repos is Claimify's Selection stage"
  (`claimify_impls.md:392-393`). So this defect is **not** covered by D25–D30; it needs a Selection
  step (or Selection-style instructions folded into the E2 prompt) inside E2.

### 2.4 Defect (d): no Disambiguation discard (maps to Claimify §3.3 Disambiguation + consensus discard)

- No abstain/discard path exists in the baseline. The schema has no "cannot be disambiguated" state;
  every emitted claim flows to validation and, if grounded, is stored. The only filter is the
  substring check (defect b), which is orthogonal to ambiguity.
- Claimify mechanism: **Disambiguation** identifies referential + structural ambiguity, tests
  resolvability with the "group of readers would likely agree" standard, and **discards** the
  sentence ("Cannot be disambiguated", excluded from Decomposition) when ambiguity is unresolvable —
  *even if it has verifiable components* (`paper_text.md:128-138`; discard rule `:136`). All three
  ports enforce the discard in code (`claimify_impls.md:107-109`, `:160-166`, `:224-229`).
- Why it bites *harder* here than in Claimify: Claimify can often *resolve* ambiguity from its 5
  preceding sentences + question; the baseline has neither, so its ambiguous-input rate is higher AND
  it has no sanctioned abstention — it must guess. The combination of (a)+(d) is what produces
  confidently-wrong standalone-looking claims.

### 2.5 Defect (e): claim id from claim text + per-chunk support (maps to D2 fact convergence; not a Claimify stage per se)

- The content-derived claim-id function hashes evidence id + chunk id + claim text
  (`sha256("{evidence}|{chunk}|{text}")`), invoked with the single chunk's ids; the supporting chunk
  ids and supporting evidence ids are `[chunk_id]` / `[evidence_id]`. The claim record requires
  support but only ever gets the one originating chunk.
- Consequences (INFERENCE from the hashing scheme): the *same fact* in two chunks/documents →
  two distinct claim ids (chunk id differs in the hash) → no merge, no growing `evidence_count`.
  This defeats **D2** (`decisions.md:29-45`): "N documents asserting the same fact = one relation
  with N evidence rows … `evidence_count` becomes a free confidence/salience signal." It also makes
  identity **text-fragile** — fixing defects (a)/(b) (which rewrite claim text) silently rekeys
  every claim, so improvements look like churn/duplication to anything downstream.
- Claimify framing: Claimify itself does not assign cross-document claim identity (out of its scope),
  so this defect maps to ugm's **D2/E3** layer rather than a Claimify stage: claim convergence is a
  *relations*-level concern (normalize claims → `(subject, predicate, object)`), and the extractor's
  job is to emit clean, decontextualized claim text that the E3 normalizer can converge. The fix is
  to (i) not bake the chunk id into permanent identity for *fact convergence*, and (ii) ensure
  claim text is decontextualized so two chunks asserting the same fact produce *comparable* text
  for E3 blocking (`decisions.md:66-83`, D4 entity-keyed blocking).

### 2.6 Defect → Claimify-stage map (summary table)

| # | Baseline defect | Symptom | Claimify stage / mechanism that fixes it | ugm hook |
|---|---|---|---|---|
| a | one chunk, no neighbors/question | unresolved pronouns/time/refs; non-standalone or wrong claims | §3.1 Context Creation: target + p preceding/f following + question (`paper_text.md:112`, `:582-583`) | D19 (coref in-call), E1 ctx-prefix (`overall_design.md:17`,`:101`) |
| b | substring-of-chunk grounding gate; drop on fail | decontextualized rewrites can't pass → claims stay contextual or get dropped | §3.4 Decomposition: bracketed essential context + entailment grounding, not literal-substring (`paper_text.md:144`) | D7/D1 (keep quote as provenance pointer, not acceptance gate) |
| c | "Extract **all** atomic claims"; preference/observation kinds | opinions/boilerplate/unverifiable become claims | §3.2 Selection: drop-or-rewrite-to-verifiable (`paper_text.md:116-124`) | **gap** — D25–D30 is CHUNK-level (`e1_5…:43-45`), no claim-level analog yet (`claimify_impls.md:392-393`) |
| d | no abstain/discard state | guesses on ambiguous spans | §3.3 Disambiguation: consensus test + "Cannot be disambiguated" discard (`paper_text.md:128-138`) | strengthens D19; complements c |
| e | id from claim text + chunk id; single-chunk support | same fact ≠ same id; no `evidence_count`; text-fragile ids | (E3-level) D2 fact convergence — extractor must emit decontextualized, comparable claim text | D2 (`decisions.md:29-45`), D4 blocking (`:66-83`) |

---

## 3. Confidence & gaps

- **Confidence: HIGH** that defects (a)–(e) characterize the naive single-chunk baseline as
  described — each maps to a definable property of the extract-everything anti-pattern and to the
  Claimify paper text. The structural facts (single-chunk input; substring acceptance gate; "extract
  all"; no discard state; text+chunk-keyed id) are the defining features of this anti-pattern.
- **INFERENCE (medium) — runtime behavior under defect (b).** This analysis does not include an
  empirical run of the baseline, so it cannot quote the empirical *rate* at which good standalone
  claims are dropped vs. the model keeping claims contextual to pass the substring check. The two
  failure modes are both *possible* given the contract; which dominates is an empirical question
  (needs a golden-set run). Likewise the opinion/boilerplate junk rate from defect (c) on a given
  corpus is not measured — the O3 premise (`decisions.md:494-501`) supports the *direction* but the
  magnitude is deployment-specific.
- **Not specified — what consumes `confidence` and `claim_kind` downstream.** This diagnosis covers
  extraction and its immediate grounding/record creation; it does not assume any later stage filters
  on `confidence` or drops preference/observation kinds. If such a downstream filter were added it
  would partially mitigate (c); the baseline anti-pattern has none, but flag it as an open design
  point.
- **To confirm at E1 — coref/context-prefix.** `overall_design.md:17`,`:101` describe a "context
  prefix per chunk" at E1. Whether that prefix is *persisted into the chunk's text field* (which
  would partially mitigate (a) and (b) by putting resolved context inside the substring search space)
  is a design decision that **materially changes the severity of (a)/(b)**. The chunk model's text
  field is what the grounding gate searches; whether it already contains a contextual prefix is the
  single most important thing to settle before implementing.
- **Scope note.** Claimify also uses multi-completion voting (3 completions, min-2) for Selection/
  Disambiguation (`claimify_impls.md:97`, `:221`); the baseline does a single call. Voting is treated
  as a robustness lever, not a core defect, and is left out of the prioritized list.

---

## 4. Recommendation for ugm (concrete, tied to decisions + the design fix)

Ordered by leverage. Each item names the exact behavior to change and the decision it serves.

1. **[Defect b — DO FIRST, it blocks everything else] Relax the acceptance contract from
   "substring-of-chunk" to "verbatim span of the *shown context* + claim faithful to it."**
   The containment check in the verbatim-substring grounding gate must run against the **context
   actually presented to the extractor** (chunk ∪ neighbors/section), not the single chunk's text
   alone; and it must gate the evidence-quote field (a provenance pointer), **never** require the
   claim text to be a superset of it. Until this changes, *any* decontextualization fix is silently
   reverted by the gate. Serves **D7/D1** (keep the grounded span as an auditable pointer) without
   penalizing standalone claims. Add the Claimify bracket convention (`paper_text.md:144`) so
   inferred spans are flagged, not banned.

2. **[Defect a — highest *quality* leverage] Widen the E2 call input to the section/document +
   neighbor chunks; resolve refs in-call.** Use the chunk's section-parent reference + character
   offsets to assemble p preceding + f following chunks (Claimify p=5/f=0 for the
   extract+decontextualize equivalent, `paper_text.md:582-583`) and pass them as an excerpt with the
   target chunk marked, plus any section title/metadata. This is the literal implementation of
   **D19** (coref satisfied *inside* the E2 call, no new model) and the `overall_design.md:17`,`:101`
   "ctx prefix → coref" line. It does **not** violate D25–D30: the value gate decides *whether* to
   run E2; this changes *what E2 sees* when it runs.

3. **[Defect c — propose a NEW decision] Add a claim-level Selection step (or fold Selection
   instructions into the E2 prompt).** This is a **genuine gap**: D25–D30 gate at chunk/section level
   (`e1_5_value_gate_design.md:43-45`), and no ugm decision yet covers per-claim verifiability
   (`claimify_impls.md:392-393`). Replace "Extract **all** atomic claims" with Claimify's
   drop-or-rewrite-to-verifiable instructions (`paper_text.md:116-124`); have the schema emit a
   per-claim `verifiable`/`selection` outcome so unverifiable/opinion spans are dropped at the
   boundary. Recommend a short decision (e.g. "D31: claim-level Selection inside E2, cheap-first
   per D4") so this is tracked, not folklore.

4. **[Defect d] Add a Disambiguation discard outcome.** Give the schema a "cannot be disambiguated"
   verdict and **drop** those claims (`paper_text.md:136`). Cheaper than it looks once (a) is fixed,
   because most ambiguity becomes *resolvable* from the now-visible neighbors; the discard only fires
   on the residual unresolvable set (Claimify saw ≤5.4%, `paper_text.md:138`). Complements **D4**'s
   cheap-first philosophy (don't pay downstream E3/relation cost on garbage claims).

5. **[Defect e] Stop baking the chunk id into fact identity; make claim text comparable for E3.**
   Keep the chunk id only inside the supporting-chunk-ids list (provenance), and let **E3/D2** own
   fact convergence: a decontextualized claim text (from fixes 1–2) is what lets D2 collapse "N
   documents → one relation, N evidence rows" (`decisions.md:29-45`) and lets D4 entity-keyed
   blocking work (`decisions.md:66-83`). At minimum, do not let id churn (from re-extraction)
   masquerade as new facts — version the extractor (D12 processing version) so re-extracted claims
   supersede, not duplicate.

**Pre-flight check before coding (gap from §3):** settle whether the E1 "context prefix" is written
into the chunk's text field. If yes, defects (a)/(b) are *partially* pre-mitigated and fixes 1–2
shrink to "extend the substring search space to neighbors" + "instruct in-call coref"; if no, fixes
1–2 are as scoped above. This is the one open fact that changes the implementation plan.

**Prioritized defect list (conclusion):**
**(b) substring-gate hostility → (a) single-chunk isolation → (c) no Selection → (d) no
Disambiguation discard → (e) text+chunk-keyed identity.** (b) leads because it structurally blocks
the others; (a) is the largest quality win once (b) is unblocked; (c)/(d) remove junk and guessing;
(e) is downstream-of-E3 hygiene that the first four enable.
