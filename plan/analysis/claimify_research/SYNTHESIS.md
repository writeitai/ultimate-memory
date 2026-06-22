# SYNTHESIS — Claimify-style E2 claim extraction: de-contextualization + claim-level value selection

Lead-architect synthesis of the Claimify research effort (questions C1–C8, repo archaeology over the
3 Claimify reimplementations + 7 memory/graph systems, `verify/{facts,completeness}.md`, and the
independent external-agent runs) against the current design (`overall_design.md` plane E, `decisions.md`
D1–D30, `e1_5_value_gate_design.md`, `value_gate_research/SYNTHESIS.md`) and against the **naive
single-chunk baseline** (the FActScore-shaped anti-pattern) that this redesign replaces. Decisive where
the evidence allows; explicit about what is still a spike.

**Provenance note (load-bearing).** This effort has an asymmetric external cross-check. **Codex
succeeded** (`external_agents/codex_decontext_grounding.md`, 3,168 words, decontextualization +
grounding) and converges independently with the Claude question docs on every structural point.
**Antigravity died** (exit 144, zero bytes, then a retry — the known `agy` agentic-print-loop failure,
not a brief problem). So the **decontextualization/grounding half has a genuine 2-source cross-check
(Codex + Claude) and the selection/integration half is single-source (Claude C4/C8 + the adversarial
completeness critic only)** — confidence on the selection half is held one notch lower accordingly, and
the completeness critic (an *internal* adversary) is doing the cross-check work an external agent would
otherwise do. The five Claude `verify/` re-checks re-opened the paper at file:line and re-derived the
baseline anti-pattern's behavior; **every load-bearing Claimify / Molecular-Facts / DnDScore number and
every baseline defect came back confirmed** (`verify/facts.md` headline), with one framing correction
carried below.

---

## 1. Executive summary (the verdict)

1. **The problem is real and correctly diagnosed: the naive baseline is "FActScore-shaped," the
   configuration Claimify's own ablation proves is worst.** That baseline makes **one structured-output
   call over one chunk in isolation** — no neighbors, no document title, no section path, no context
   prefix — so pronouns, partial names, acronyms, and relative time **cannot** be resolved; and it
   instructs the model to "extract **all** atomic claims … supported by an exact quote copied from this
   chunk", i.e. **no Selection stage at all**. Claimify's ablation: removing Selection causes the
   *largest* quality drop of any component — element-coverage macro-F1 **83.7 → 54.4**
   (`paper_text.md:257,280`). Such a baseline sits permanently in that ablated state.

2. **De-contextualization is a high-precision *feature*, not lost work, and ugm's own design already
   provides the raw materials to do it.** Claimify discards only the sentences it cannot confidently
   interpret — ≤5.4% "cannot disambiguate" (GPT-4o 3.2%), 0.8% "no claims" (`paper_text.md:138,142`) —
   yet reaches **99% entailment** and **87.9% element accuracy** (`paper_text.md:197,207`). It does this
   by reading each sentence **inside its surrounding context** (Selection: 5 preceding + 5 following
   sentences; Disambiguation/Decomposition: 5 preceding + 0 following — `paper_text.md:582-583`) and
   resolving references from that context, never from outside knowledge. ugm's E1 chunk model provides
   the analogue by design: a chunk references its section-parent and carries character offsets, so a
   chunk's same-section neighbors are a sort+index lookup with **zero extra fetches**, and E0 already
   produces PageIndex section path + summaries (`overall_design.md:92`).

3. **Two distinct, orthogonal fixes — keep them separate.** The two problems are different axes at
   different grains and must not be conflated:
   - **De-contextualization** (claims must stand alone) — fixed by giving E2 a **context bundle** +
     in-call coref (D19) + a decontextualization instruction with the **minimality** guardrail.
   - **Claim-level value selection** (don't extract non-relevant content) — fixed by a **verifiability
     gate** inside E2 (Claimify Selection / VeriScore): KEEP specific verifiable propositions, DROP
     opinion / advice / hypothetical / generic / intro-conclusion / lack-of-info. This is the
     **claim-grain dual of the E1.5 chunk-level value gate** (D25–D30): E1.5 decides *whether to pay
     for E2 on a section at all*; Selection decides *which propositions within an extracted chunk
     become claims*. They filter different noise on different units and **do not double-count**.

4. **Grounding must move off the verbatim-substring gate — but the replacement is a LAYERED contract,
   not a single new mechanism.** No surveyed system uses substring containment; Claimify, VeriScore,
   SAFE, and DnDScore all ground by **entailment** ("strongly implied"), and DnDScore keeps **both** an
   atomic claim and its decontextualized form. But the two replacements the research proposed
   independently — C6's in-call entailment self-verdict and C8's window-membership-on-declared-additions
   — **each have a hole the old deterministic substring check did not** (self-grading is circular;
   window-membership only checks additions the model *chose to declare*). The defensible contract
   **layers** them: (i) a deterministic verbatim **anchor span** that *is* a substring of the window
   (the salvaged virtue — a check the model cannot talk past), (ii) window-membership on every declared
   added span (mechanical anti-fabrication), (iii) an in-call `grounded` self-verdict (cheap soft
   signal), (iv) a **sampled independent** entailment audit (never per-claim). Persist a verbatim
   `source_span` + char offsets **and** the standalone `claim_text` (DnDScore's dual-field contract).

5. **The call architecture is the single biggest open design choice, and the better-evidenced default
   is TWO calls, not one.** C8's headline (collapse all stages into one structured-output call) is
   under-evidenced: Claimify *votes* (3 completions, min-2) on exactly Selection + Disambiguation
   because single completions on those judgments are unstable (`paper_text.md:587`), and Selection and
   Disambiguation carry **contradictory in-prompt instructions** (Selection: "it does NOT matter whether
   the proposition contains ambiguous terms"; Disambiguation: resolve ambiguity or discard) that the
   staged design deliberately isolates. No surveyed implementation runs the fully-collapsed 1-call
   variant. **Default to 2 calls** — Selection as its own (optionally voted) call, then a fused
   Disambiguation + Decomposition + coref + grounding call — which is C8's own buried fallback and the
   only shape with implementation precedent. Gate any 1-call collapse on a measured ablation, do not
   assume it.

6. **Selection's recall risk is real and under-carried, and Selection — unlike E1.5 — has no
   defer-don't-DROP backstop.** Selection's measured verifiable-element **recall is 87.6%**
   (`paper_text.md:207`) — a ~12.4% per-element miss. For a **uniquely-attested** fact the relation
   layer's `evidence_count` backstop (D2) is structurally useless (there is no second attestation), and
   a DROP at proposition grain is a **hard delete**. E1.5's recall envelope (defer-don't-DROP, D29) has
   no claim-grain equivalent in the proposals. Selection therefore needs its own envelope: a
   **conservative KEEP bias**, **never-drop lexical classes** (quantities, dates, named-entity +
   predicate, change-of-state markers — the supersession-bearing language D29 already privileges), an
   **append-only DROP ledger** (so a better prompt can re-examine only the drops), and **per-fact**
   (not corpus-average) false-drop measurement against canaries.

7. **The cost story is conditional, not free — and the two "zero marginal cost" claims need an
   asterisk.** In-call coref/grounding adds no *calls*, but the richer context bundle and the audit
   schema add **uncached** cost: prompt-caching only amortizes the *document-shared* block and only
   above the 4096-token Opus minimum, which the **short-source long tail** (chat turns, tool outputs,
   git memory) will rarely clear; neighbor stubs are full-price on every chunk; and the per-claim audit
   fields (`added_context`, `dropped_spans`, offsets, `grounded`) are **output tokens, never cached**.
   Price the bundle **per source-class** before committing, and feed E2's per-claim spend into D30's
   break-even discipline (E2 is the cost center the whole value gate exists to protect).

8. **Verdict: ACCEPT both fixes; formalize the ugm E2 design as D31–D35, gated on two spikes.** The
   decontextualization + selection redesign is the correct full-scope E2 and is implementable against
   data the E1 chunk model already provides by design. Gate two things on measurement before locking:
   the **1-call-vs-2-call** architecture (ablation), and the **Selection recall floor** (per-fact
   false-drop on a canary set). Propose decisions **D31–D35** (the registry round took D17–D24, the
   value gate took D25–D30, so the claim layer starts at D31).

---

## 2. Per-question conclusions (C1–C8)

Confidence reflects `verify/facts.md` + `verify/completeness.md` AND the Codex cross-check (which
covers C1/C2/C3/C5/C6 — the decontextualization + grounding half). The selection half (C4/C7/C8) has
no successful external cross-check (Antigravity died) and is held one notch lower.

### C1 — Claimify method spec → **Adopt the staged contract; the numbers are verified. Confidence: high.**
- **Settled answer:** Claimify = Sentence-splitting → **Selection** (verifiability; 3 outcomes:
  drop / rewrite-to-verifiable / unchanged) → **Disambiguation** (resolve referential + structural
  ambiguity from context; **discard** when a group of readers would not reach consensus) →
  **Decomposition** (atomic, decontextualized, attribution-preserving claims). It **never** sees a
  bare sentence — always sentence + context window + (in its domain) the originating question.
- **Key evidence (VERIFIED at source):** entailment 99.0 (ties VeriScore 99.2, beats SAFE 96.6 / DnD
  89.1); element-coverage macro-F1 83.7 (next best 62.5); Selection-removal ablation 83.7→54.4 (the
  largest drop); cost/yield 58.3% sentence yield, 3.31 claims/sentence, 0.55% invalid
  (`paper_text.md:197,207,257,627`).
- **Agreement:** Codex independently reconstructs the same stage roles, context windows, discard rule,
  and the brackets/attribution conventions from `paper_text.md` + the three impls.

### C2 — De-contextualization design space → **Decontextuality + MINIMALITY; feed context, forbid outside knowledge. Confidence: high.**
- **Settled answer:** A claim is decontextualized when interpretable with no access to the source —
  referential (pronouns/coref), structural (acronyms/elisions/attribution), temporal (relative →
  absolute), entity (named not described). **Minimality (Molecular Facts) is the guardrail:** add the
  *least* context that makes it stand alone; over-contextualization both bloats and injects unsupported
  detail. Critically for ugm, over-contextualization also **breaks dedup and relation-merging** — "Alice
  Smith, the former 2019 interim CFO, approved Y" will not cluster with "Alice Smith approved Y."
- **Key evidence (VERIFIED):** true non-minimality in **1.7%–9.6%** of decontextualizations; avg length
  grows 7.6 → ~15 words across methods; Molecular Facts "argmax evidence set" minimality criterion;
  DnDScore: decontextualization flips the verification verdict on **19.11%** of subclaim pairs (16.25%
  false→true), 48.5% of those via a pronoun replacement (`molecular_facts`, `dndscore` PDFs, confirmed
  in `verify/facts.md` §B/§C). **Claimify forbids external knowledge** and criticizes Molecular Facts
  for using parametric knowledge (`paper_text.md:286`) — ugm follows Claimify here (faithfulness > recall
  via world knowledge).
- **Agreement:** Codex independently surfaces the same minimality trade-off and the same numbers.

### C3 — Baseline diagnosis → **Five real defects in the naive single-chunk anti-pattern; one framing corrected. Confidence: high.**
- **Settled answer (the defect list):** (a) **single-chunk isolation** — no context to resolve
  references (FActScore-shaped); (b) **no Selection** — "extract all" admits opinion/advice/intro as
  claims; (c) **no disambiguation discard** — the model guesses on ambiguous text; (d) **provenance is
  discarded** — the verbatim evidence-quote is checked then thrown away, the claim record stores no
  quote/offsets; (e) **chunk-keyed identity** — a content-derived claim id over (evidence, chunk, claim
  text) makes the same fact in two chunks two ids, and *churns every id* once decontextualization
  rewrites the claim text.
- **Framing correction (`verify/facts.md` ★, MUST carry):** the verbatim-substring validator gates only
  the evidence-quote field, **not** the claim text — a schema that separates the two lets a
  decontextualized claim *pass* as long as the model also returns a substring evidence-quote. So the
  precise fault is **not** "the gate structurally forbids decontextualization"; it is that the **prompt**
  nudges surface-form quotes, the **quote can't point at a neighbor** (none are shown), the **quote is
  discarded**, and there is **no selection/disambiguation**. The fix direction is unchanged; the
  mechanism claim must be stated precisely.

### C4 — Claim-level Selection → **Verifiability gate, orthogonal to E1.5; recall-conservative. Confidence: medium-high.**
- **Settled answer:** Encode Claimify-Selection + VeriScore **verbatim** KEEP/DROP vocabulary. KEEP =
  specific, verifiable proposition (state/event/decision/quantity/policy/relationship) checkable against
  **the project's own evidence** (ugm substitutes "project corpus" for VeriScore's "external world
  knowledge"). DROP = opinion / interpretation / generic-normative / speculation-modal ("could/would/may")
  / instruction-advice / question-meta / intro-conclusion / lack-of-information. **REWRITE, don't drop,**
  a mixed sentence (keep the verifiable span) — the claim-grain mirror of defer-don't-DROP. Selection is
  **in-call** (rides the E2 call, D19/D4), decides verifiability **only** (Claimify's three "does NOT
  matter" decouplings: truth value, relevance, ambiguity), and is the **claim-level dual of E1.5** — it
  cannot drain a section because it drops propositions, not sections.
- **Key evidence (VERIFIED):** the 83.7→54.4 Selection ablation; verbatim DROP/REWRITE example sets
  (`prompts.py:1-46`, `paper_text.md:476-485`); VeriScore DROP list + expository carve-out
  (`extraction_qa_template.txt`).
- **Caveat (`verify/completeness.md`, load-bearing):** Selection's 87.6% verifiable-element recall is a
  real ~12.4% miss; it travels in C4 but **not** in C3/C7/C8, so a reader of those alone adopts Selection
  as pure upside. The never-drop lexical override is C4's own (sensible) construction, not measured.

### C5 — Context provisioning → **A minimal bundle, shared-document prefix + caching; but the prefix is a design prerequisite, and short sources break the economics. Confidence: medium.**
- **Settled answer:** The E2 call receives: document header (title/date/URI/language) + PageIndex
  section path/summary + the E1 context-prefix + **±1 (then ±2) same-section neighbor chunks** +
  optional known-entity hints + the delimited target chunk. Token discipline: a per-document shared
  prefix (cached) varied only by target + neighbor stubs. Neighbors are free to fetch (the chunk's
  section-parent + offsets).
- **Caveats (`verify/completeness.md`, MUST carry):** (i) the E1 `context_prefix` is **design-intent
  only** — `e1_chunks_design.md` is "future", so the cost/coref arguments resting on the prefix are
  partly unbuilt; design E2 to also run on neighbors + PageIndex path when the prefix is absent. (ii)
  prompt-caching does nothing below the 4096-token Opus minimum, which short chat/tool/git sources
  rarely reach; neighbor stubs + audit *output* tokens are uncached regardless. **Price per source-class.**

### C6 — Grounding without verbatim quotes → **Dual-field schema + entailment acceptance, LAYERED with a deterministic floor. Confidence: high on direction, medium on the self-verdict.**
- **Settled answer:** Persist BOTH a verbatim `source_span` + char offsets (provenance/audit; the
  salvageable half of span-pointers) AND the standalone `claim_text` (retrieval/E3). Accept by
  **entailment**, co-emitted in the E2 call (no second model on the hot path) — this is DnDScore's
  dual-field contract + Claimify's LLM-entailment primitive (Claimify **abandoned pretrained NLI** —
  RoBERTa-ANLI under-classified entailed claims and hit the 512-token wall — `paper_text.md:189`).
- **Reconciliation with C8 (the one real design clash — `verify/completeness.md` top-6 #2):** C6's
  `grounded` self-verdict is **circular**; C8's window-membership only checks **declared** additions.
  Neither preserves the substring gate's one virtue (a deterministic check the model cannot bypass). The
  synthesis **layers** them (see §3.4): deterministic anchor substring + window-membership on declared
  additions + in-call self-verdict + sampled independent audit.
- **Overclaim to drop (`verify/completeness.md`):** the 99% entailment number is an *independent judge*
  on *long-form QA* — do not cite it as evidence a *self-verdict* on *B2B project memory* is safe.

### C7 — Comparative systems → **Nobody decontextualizes-with-discard; ugm's E1.5 chunk gate is already unique prior art; borrow Claimify's stages. Confidence: medium-high.**
- **Settled answer:** Across mem0 / graphiti / cognee / graphrag / lightrag / hipporag / letta +
  the Claimify/VeriScore/FActScore/SAFE references: extractor **context windows** vary (FActScore = bare
  sentence, the maximal de-contextualization risk; VeriScore = 3 preceding + 1 following; SAFE = entire
  response; graphiti = episode + prior context; Claimify = 5+5/5+0); **selection** is rare (mem0 drops
  chit-chat; VeriScore/Claimify gate verifiability; the rest extract-everything); the
  **ambiguity-discard** rule is **unique to Claimify**. Borrow: Claimify's staged verifiability +
  discard, VeriScore's fused single-call shape as the efficiency reference, DnDScore's dual-field
  grounding.

### C8 — Integration + reference extractor design → **The actionable core; adopt with two amendments. Confidence: high on the design, medium on the 1-call architecture.**
- **Settled answer:** A Claimify-staged E2 over the context bundle, composing downstream of E1.5 and
  upstream of E3, with selection-drops + decontextualization-deltas persisted in an append-only
  `claim_extraction_decisions` ledger (mirrors D27); an illustrative reference extractor design (staged
  extracted-claim schema, layered grounding validation, neighbor-window assembly, the new prompt);
  proposed D31–D34; an eval plan reusing Claimify's entailment/coverage/decontextualization metrics.
- **Two amendments (from `verify/completeness.md`):** (1) **2-call default**, not C8's 1-call headline
  (§1.5 above); (2) the window-membership gate must be **layered under a deterministic anchor** to close
  the undeclared-addition hole — and Selection needs a **defer-equivalent** (D35) so it never
  hard-deletes a rare fact.

---

## 3. Recommended design — the ugm E2 stage

### Position — plane E, the E2 stage (downstream of E1.5, upstream of E3)
E2 runs only on sections E1.5 routed to FULL (or promoted from DEFERRED, D28) — the value gate is
**unchanged**, E2 is a pure consumer of it. E2's output (decontextualized, selected, grounded atomic
claims) is the input to E3 relation normalization; **decontextualization is a hard precondition for
E3** — a claim carrying "she" or "the company" cannot be entity-resolved (T0 exact match, D17) or
blocked for supersession (D4). This is why D19 mandates coref in-call and why the redesign is
load-bearing for E3, not cosmetic.

### The context bundle (what the E2 call sees) — fixes de-contextualization
One target chunk at a time, **never bare**. Bundle, cheapest-justified-first:
- **Document header** — title, date, source URI, language. Resolves "this report", "the company",
  relative-time anchors. Cheap.
- **PageIndex section path + node summary** — the structural metadata Claimify defines but never used
  (`paper_text.md:112`); ugm has it for free from E0. Resolves the list-item-without-preamble and
  intro/conclusion cases.
- **E1 context-prefix** for the target chunk — the highest-value compact summary *if/when E1 produces
  it*; treat as optional until `e1_chunks_design.md` lands (see open spikes).
- **±1 (then ±2) same-section neighbor chunks** — the ugm analogue of Claimify's 5-preceding/5-following
  window; fetched by the chunk's section-parent + offsets, **same scope only** (never cross project/
  session scope). This is the single most important missing input in the baseline.
- **Known entity hints** — the chunk's entity hints, as *hints* (resolution permission, not fact
  permission).

**Minimality instruction:** add only the context needed to resolve a reference/time/acronym/attribution;
do **not** add true-but-unnecessary descriptors; every added token must be justifiable by one
`added_context` entry. **No external knowledge** (Claimify's faithfulness rule, contra Molecular Facts).

### Selection (verifiability) — fixes "don't extract non-relevant content"
Inside the E2 reasoning, label each candidate proposition KEEP / REWRITE / DROP using the verbatim
Claimify+VeriScore vocabulary (§C4); emit only KEEP/REWRITE, record DROPs (with class) to the ledger.
Selection decides **verifiability only** — not relevance (a K2-scope concern, handled at the section
grain by D16/D28), not salience (E1.5), not ambiguity (the disambiguation step). It is the **claim-grain
dual of E1.5** and is kept **metrically separate** (D34).

### Call architecture — 2 calls by default (D31)
- **Call 1 — Selection** (optionally voted, 3×/min-2 as Claimify does for the unstable judgments).
- **Call 2 — Disambiguation + Decomposition + coref + grounding** fused (one frontier structured-output
  call; graphiti/VeriScore/mem0 all fuse these in one call at production scale).
This is the only shape with implementation precedent and it isolates Selection's "ignore ambiguity"
instruction from Disambiguation's "resolve ambiguity" instruction. **A 1-call collapse is permitted only
after an ablation** shows it does not lose >X pp on Selection precision or decontextualization
desirability (eval plan below). Do **not** run the literal 3-calls-per-sentence Claimify loop (~7–9
calls/sentence) at ugm scale — it is pure latency on the per-document chain (D12).

### Grounding — layered, dual-field (D32) — replaces the substring gate
Schema persists **both** the standalone `claim_text` and a verbatim `source_span` + `source_char_start/
end` (offsets into the target chunk; combined with the chunk's own offset → document offsets for free),
plus the per-claim `added_context` list (each added substring tagged with its in-window source) and an
in-call `grounded` self-verdict. Acceptance **layers four checks**:
1. **Deterministic anchor** — at least one verbatim `source_span` that *is* a normalized substring of
   the window (the salvaged non-circular floor; offsets located in code, never trusted from the model).
2. **Window-membership** — every *declared* added substring verbatim-exists in its declared in-window
   source (mechanical anti-fabrication).
3. **In-call entailment self-verdict** (`grounded`) — a cheap soft signal, co-emitted (D4: no second
   model on the hot path); includes Claimify's **Statements-and-Actions Rule** so attribution-dropping
   ("John says X" → "X") fails.
4. **Sampled independent entailment audit** — an *independent* judge on a sampled stream (never
   per-claim), because self-grading is optimistic; escalate only a borderline-confidence band to a cheap
   judge (D4-style cascade).
A decontextualized claim with no verbatim slice is **accepted** with `span_verbatim=False` (the baseline
hard-rejects it); a claim that invents content with no window source is **rejected**.

### Persistence — the E2 decision ledger (D33), rebuildable per D7, idempotent per D12
Append-only, versioned, mirrors D27's `gate_decisions`:
```
claim_extraction_decisions  (append-only — the E2 transcript)
  decision_id, evidence_id, chunk_id, scope_*,
  stage ∈ {selection, disambiguation, decomposition},
  outcome ∈ {claim_emitted, dropped_unverifiable, dropped_cannot_decontextualize,
             rewritten_to_verifiable, kept_flagged},
  source_span_text, source_char_start, source_char_end,
  decontextualized_text nullable, added_context jsonb nullable,
  claim_id nullable, reason text nullable,
  extractor_version,                 -- pinned model + prompt + window set + call-arch (D12 versioning)
  decided_at
```
**Rebuild semantics (D7):** the deterministic parts (which neighbors were in-window, chunk hashes,
offsets) are recomputable; the **LLM rungs (selection verdict, decontextualization, entailment) are
replay-from-storage only** (model-endpoint drift) — pin `extractor_version` AND store outputs; a rebuild
loads stored claims + decisions and never re-calls the model. **Idempotent** on the chunk content hash +
`extractor_version`; the ledger closes the latent gap where dropped content is invisible to idempotency
in the baseline.

### Recall envelope for Selection (D35) — defer-don't-DROP, one grain down
Selection's DROP is a hard delete with no D29 backstop, and the `evidence_count` backstop is useless for
uniquely-attested facts. So: **conservative KEEP bias** (when in doubt, KEEP — Selection's recall on
verifiable content is high, its precision on excluding junk is the looser side, and over-keep is
recoverable downstream while over-drop is not); **never-drop lexical classes** (quantities, dates,
named-entity+predicate, change-of-state markers — the supersession-bearing language D29 privileges; the
highest-severity thing to lose is a change-of-state sentence → zombie-fact risk); a **`kept_flagged`
outcome** (low-confidence keep, written but marked for re-review — the claim-grain analogue of DEFERRED,
so a rare fact is never silently deleted); the **DROP ledger** (a better prompt re-examines only drops, a
version-filtered batch = D28 at claim grain); and **canary CI** (plant rare verifiable facts in the O6
golden set, fail CI if Selection drops one), tuned against **per-fact** false-drop, never corpus average.

### Cost model (impact on D30)
`Cost_E2 ≈ C_call × (n_select_calls + n_extract_calls) + output_tokens(claims + ledger)`. The bundle's
*input* cost is amortized by prompt-caching **only for documents above the 4096-token Opus minimum**;
the short chat/tool/git tail and the per-claim *output* (audit fields + ledger rows) are uncached. **No
cost multiplier is committed** until a spike measures, per source-class: bundle token cost, neighbor-stub
share, audit-output share, and the cache-hit fraction. Fold E2-per-claim spend into D30's break-even
discipline — E2 is the cost center the E1.5 gate exists to protect, so making E2 richer must be priced
against the gate's savings.

---

## 4. Implications for decisions / objections

### New decisions to propose (continue after the value gate's D25–D30 → start at D31)
- **D31 — E2 is a Claimify-staged extractor over a context bundle, default TWO calls.** Selection
  (verifiability + ambiguity-discard, the voted/conflicting-instruction stages) as its own call; a fused
  Disambiguation + Decomposition + coref + grounding second call. Over the document header + PageIndex
  path + E1 prefix (when present) + ±N same-section neighbors. Satisfies D19 (coref in-call), refines D4
  (cheap-first: 2 calls, not 7–9). The 1-call collapse is a **measured** decision, gated on an ablation.
- **D32 — Claim grounding is a LAYERED, dual-field contract, not chunk-substring.** Persist standalone
  `claim_text` + verbatim `source_span` + offsets + declared `added_context`. Accept by: deterministic
  anchor substring + window-membership on declared additions + in-call entailment self-verdict + sampled
  independent audit. No external knowledge. Replaces the verbatim-substring hard reject.
- **D33 — E2 selection-drops and decontextualization deltas are first-class, append-only, versioned
  Postgres state (`claim_extraction_decisions`), mirroring D27.** Rebuild reads stored claims+decisions,
  never re-calls the model (D7 = stored-and-auditable for the LLM rungs). Idempotent on the chunk content
  hash + `extractor_version` (D12).
- **D34 — E2 Selection is the claim-level dual of the E1.5 section-level value gate, kept metrically
  separate.** E1.5 = pay-or-defer per section (salience, D25); Selection = is-a-verifiable-claim per
  proposition (verifiability). Orthogonal axes; report on separate metrics (gate false-skip vs Selection
  precision/recall) to avoid double-counting.
- **D35 — Selection recall envelope (defer-don't-DROP one grain down).** Conservative KEEP bias,
  never-drop lexical classes, a `kept_flagged` low-confidence outcome (no hard delete), the DROP ledger
  for version-filtered re-examination, and per-fact canary CI. Mirrors D29 at claim grain.

### What changes in D4 / D7 / D12 / D19 / D25–D30
- **D4 (cheap-first)** — extended: a third cheap-first instance (Selection in-call, entailment self-
  verdict in-call, independent judge only on a sampled/borderline stream) sits *inside* E2, downstream of
  E1.5's gate cascade and upstream of E3's supersession cascade.
- **D7 (rebuildable)** — the E2 decision ledger is rebuildable **state**, with the same determinism caveat
  as the gate: deterministic rungs recomputable, LLM rungs replay-from-storage. Add
  `claim_extraction_decisions` to the Postgres-authoritative set.
- **D12 (per-doc chain)** — E2 is still the per-document Cloud Tasks stage; only its internal shape (2
  calls, ledger writes) changes; idempotency key gains `extractor_version`.
- **D19 (coref in-call)** — **realized** by D31's context bundle (intra-document only; cross-document
  coref remains the acknowledged open gap, `decisions.md:400-404`).
- **D25–D30 (value gate)** — **unchanged**; D34 records the claim-level/section-level duality.

### Open risks & what to prototype first
**Spike before locking (highest leverage first):**
1. **Call-architecture ablation (the #1 open choice).** Same golden slice through (i) 1-call, (ii)
   2-call (Selection split), (iii) 3-call Claimify-with-voting; compare entailment, element-coverage F1,
   % desirable decontextualization. Default to 2-call until this clears a 1-call collapse. (C8, completeness a)
2. **Selection recall floor.** Measure per-fact false-drop on a canary set of uniquely-attested rare
   facts; size the canary set against an estimated rare-fact base rate; validate the never-drop lexical
   classes actually bound the 12.4%-element miss. (completeness c; D35)
3. **Grounding-gate safety.** Measure in-call self-verdict precision/recall vs an independent judge on a
   ugm golden slice; confirm the layered floor (anchor + window-membership) rejects fabricated additions
   the self-verdict misses. (completeness b; D32)
4. **Per-source-class cost.** Measure the short-source fraction, document-length distribution vs the
   4096-token cache minimum, neighbor-stub and audit-output token share; decide a cheaper bundle
   (section-path-only, no neighbor stubs) for short sources. (completeness d; D30)
5. **E1 `context_prefix` prerequisite.** Either land `e1_chunks_design.md` with a pinned prefix length
   (which decides the cache-minimum question), or specify the E2 fallback when the prefix is absent
   (neighbors + PageIndex path only).
6. **Decontextualization ↔ identity ↔ temporal loop.** Decide whether the claim id stays content-derived
   (then decontextualization churns every id — version via `extractor_version`, or move identity to a
   stable key); specify E2 behavior when neither chunk nor window dates a temporal claim
   (`paper_text.md:310` blind spot); estimate the cross-document-coref hole for threaded project memory.

---

## 5. Migration from the naive baseline (build order)

The redesign can be reached from the naive single-chunk baseline incrementally; each move is independently
shippable and does not require E1.5 or E3 to exist first. Stated as design moves (the concrete,
implementation-specific version of this plan is maintained separately by the consuming service):

1. **Neighbor window.** Change the per-chunk extraction orchestration to build a **±1 (then ±2)
   same-section, same-scope sibling window** from the chunks already in hand — neighbors are a sort+index
   lookup over the chunk's section-parent + offsets, **zero extra fetches**. The extractor's unit changes
   from a chunk to a window. Intra-document only (cross-document coref stays an open gap).
2. **New prompt + context.** Replace the minimal "extract all … exact quote" system prompt with the
   condensed Selection → Disambiguation/decontextualization → Decomposition instruction (KEEP/DROP
   vocabulary; minimality; no external knowledge; record every added span with its in-window source;
   discard-when-no-consensus). The user message supplies `context_prefix?` + `prev_chunk` + `next_chunk`
   + a delimited `TARGET` chunk. One call now (Selection folded as a labeled field); split into the
   2-call shape (D31) when the ablation says so.
3. **Staged extracted-claim schema.** Carry standalone `claim_text` + `claim_kind` + verbatim
   `source_span` + `source_char_start/end` + `added_context: list[{text, source}]` + `grounded` +
   `confidence`; add `dropped_spans: list[{span, reason}]` + `selection_verdict` to the result. Persist
   the source span + offsets + `span_verbatim` + `grounding_verdict` on the claim record (stop discarding
   provenance).
4. **Layered grounding validation.** Replace the verbatim-substring hard reject with the four-layer
   contract (§3.4): delete the substring reject; accept iff `claim_text` non-empty, scope present,
   `grounded` true, the anchor `source_span` resolves in the window (set offsets + `span_verbatim`; if
   absent, accept with `span_verbatim=False`), and every declared `added_context` span verbatim-exists in
   its declared source. Add the sampled independent audit offline.
5. **Decision ledger (D33).** Add the append-only `claim_extraction_decisions` state; write every
   DROP/REWRITE/decontextualization-delta stamped with `extractor_version`; key idempotency on the chunk
   content hash + `extractor_version`.
6. **Tests.** A decontextualized claim with no verbatim slice now **accepts** (`span_verbatim=False`); an
   attribution-dropping claim is **rejected** by the `grounded`/Statements-and-Actions check; a fabricated
   added span with no window source is **rejected**; add a Selection KEEP/DROP fixture set.

**Eval plan (reuse Claimify's own metrics).** Entailment-rate (grounding health for D32);
element-coverage macro-F1 split into Selection precision (low FP = no opinions/intros) and recall (low
FN = no dropped facts; carry the 87.6% caveat); decontextualization % desirable (Claimify's 7-result-type
test on a labeled subset, plus a cheap proxy = fraction of accepted claims with no dangling reference);
a **neighbor-window ablation** (0/0 = the naive baseline, expected worst) quantifying move 1; the
**call-architecture ablation** (spike 1). Reuse the O6 / D22 golden-set machinery — the claim-
verifiability golden set is a sibling of the gate-verdict golden set (D30).

---

### Source map
Questions: `claimify_research/questions/C1–C8`. Repo archaeology:
`repo_findings/{claimify_impls,mem0_cognee,graphiti_letta,graphrag_lightrag_hipporag}.md`. Verify:
`verify/{facts,completeness}.md`. External agents: `external_agents/codex_decontext_grounding.md`
(SUCCEEDED — decontextualization + grounding cross-check); `external_agents/agy_selection_integration.md`
(Antigravity — died exit 144, see provenance note). Primary papers: `_additional_context/claimify_papers/`
(Claimify 2502.10855, Molecular Facts 2406.20079, DnDScore 2412.13175, VeriScore 2406.19276, VeriFact
2505.09701) + `_additional_context/claimify_deshwalmahesh/paper_text.md`. Design: `overall_design.md`
(plane E), `decisions.md` (D4/D7/D12/D19/D25–D30), `e1_5_value_gate_design.md`,
`value_gate_research/SYNTHESIS.md`, `concepts.md`.
