# C6 — Grounding a DECONTEXTUALIZED claim back to source WITHOUT the verbatim-substring gate

**Question.** Replace the verbatim-substring grounding gate's substring-containment rule. Survey +
recommend among (a) character-span pointers into the chunk for a verbatim SOURCE span, kept separate
from the standalone `claim_text`; (b) entailment/NLI verification ("is claim C entailed by chunk text
T?") as DnDScore/VeriScore/SAFE do; (c) keep BOTH a verbatim `source_span` (provenance/audit) AND a
decontextualized `claim_text` (retrieval/reasoning); (d) an LLM self-check faithfulness pass. What
does Claimify itself do to stay faithful? Cost/precision tradeoffs at scale. Conclude with a
concrete grounding contract (acceptance rule + schema fields) to replace the verbatim-substring
grounding gate.

Scope of evidence: Claimify paper + 3 reimpls, DnDScore, VeriScore, SAFE, FActScore, Molecular
Facts (all read at source); the naive single-chunk baseline as a known anti-pattern E2 must avoid.
`file:line` for the public comparison repos; `paper_text.md:line` for the Claimify paper (markdown of
arXiv 2502.10855).

---

## 1. Key findings

- **The substring gate is fundamentally incompatible with decontextualization, and the
  extract-everything baseline already proves it.** The naive single-chunk baseline rejects a claim
  unless a model-emitted verbatim evidence-quote field is a verbatim (whitespace/case-normalized)
  substring of the chunk. But the entire *point* of E2 (D19 coref, Claimify decontextualization) is
  that `claim_text` is **rewritten** to stand alone — pronouns resolved, names completed, context
  injected. A decontextualized claim is, by construction, almost never a verbatim span. The gate
  therefore pushes the prompt toward extracting *quotable* (contextual, non-standalone) claims — the
  exact opposite of the design goal. The FActScore-shaped extractor's system prompt even hard-codes
  this tension: "Return only claims that are directly supported by an **exact quote** copied from this
  chunk." You cannot have both "exact quote" and "decontextualized."

- **Claimify itself NEVER uses substring containment to stay faithful. It uses (1) generation-time
  faithfulness constraints and (2) an LLM ENTAILMENT check** ("if S is true, must C be true?") — a
  semantic relation, not string overlap (`paper_text.md:36`, `:187-193`, full prompt `:1070-1082`).
  Its evaluation framework's first pillar is literally *Entailment*: "if the source text is true, the
  extracted claims must also be true … described in previous works as faithfulness" (`:36`). Claimify
  explicitly **tried** a pretrained NLI model (RoBERTa-large ANLI) and **abandoned it** for an
  LLM-prompt entailment classifier because NLI under-classified entailed claims (couldn't resolve
  "it"→Plankalkül across sentences) and blew the 512-token limit (`:189`, Appendix H `:680-684`).
  So among the surveyed methods the answer to "what is the right grounding primitive" is decisively
  **entailment-by-LLM over (claim, source-sentence + context)** — option (b), not (a)-as-a-gate.

- **DnDScore is the single most on-point prior art for ugm, and it endorses option (c): keep BOTH
  an atomic subclaim AND its decontextualized form, and feed BOTH to verification.** DnDScore
  (Wanner, Van Durme, Dredze 2024, arXiv 2412.13175) verifies the *atomic decomposed subclaim* while
  supplying its *decontextualized form as the relevant context* — "the prompt is provided with the
  source document, the subclaim and the augmented, decontextualized claim … verify the specific
  subclaim using the relevant context" (p.6, §4.2; Table 1 shows the paired subclaim↔decontextualized
  columns). Its whole motivating problem is ours: decontextualization makes a claim "less atomic,
  making it unclear which part of the new claim requires verification" (p.1 abstract/intro). The
  resolution is **two coupled fields, not one** — precisely option (c).

- **Recommendation: option (c) schema + option (b) acceptance rule, NOT (a)-as-gate and NOT (d)
  alone.** Persist BOTH a verbatim `source_span` (char offsets into the chunk, for provenance/audit
  — the salvageable half of (a)) AND the decontextualized `claim_text` (for P1 retrieval / E3
  reasoning). The *acceptance rule* becomes **entailment** of `claim_text` by the chunk-window text
  (option b), produced **in the same E2 call** as a per-claim self-verdict (a cheap form of option d),
  with the substring gate **demoted from a hard reject to a soft `span_verbatim` boolean flag**. This
  replaces the verbatim-substring grounding gate while honoring D4 (cheap-first: no extra model call),
  D7 (span offsets recompute from immutable E0/E1; the entailment verdict is replay-from-storage like
  D27's salience rung), and D19 (coref already happens in-call). Cost at scale ≈ **zero marginal**
  versus a separate NLI/judge pass, because the verdict rides the extraction call that already runs.

---

## 2. Evidence & detail

### 2.1 What the naive single-chunk baseline does (and why it breaks decontextualization)

The verbatim-substring grounding gate accepts a claim iff:
1. `claim_text` non-empty,
2. the verbatim evidence-quote field non-empty,
3. the normalized evidence-quote is contained in the normalized chunk text — substring containment
   after whitespace-collapse + casefold,
4. chunk has a project scope.

The extracted-claim schema carries `claim_text, claim_kind`, a verbatim evidence-quote field, and a
confidence. Crucially: **the evidence-quote is consumed by the gate and then DISCARDED** — it is never
written to the claim record. The claim model has chunk-granularity supporting-pointer fields
(`supporting_chunk_ids` / `supporting_evidence_ids`) but **no span offsets, no stored quote, no
`source_span`**. So this baseline's provenance is "which chunk," never "which characters," and the
verbatim text the gate checked is thrown away. Meanwhile the chunk model *already* carries character
offsets into its section parent — the offset substrate for option (a) exists at the chunk level but is
not propagated to claims.

The anti-pattern's contract behavior pins the broken design: a claim whose evidence-quote is NOT a
literal substring is rejected with an "evidence-quote not found in chunk" error, and the only "accept"
case uses a quote that is a verbatim slice of the chunk. A genuinely decontextualized claim ("The
target ERP is NetSuite." standing alone, no surrounding sentence) would fail unless the model
cherry-picks a quotable fragment — which is what such a prompt forces.

**Single-chunk caveat (interacts with C-context questions).** The extract-everything baseline sees
ONE chunk, no neighbors. Any entailment-based rule can only be honest about the text actually shown to
the model; the "source window" for the acceptance rule = the chunk (and, once neighbor context lands,
the chunk + its prefix/neighbors). This is *narrower* than Claimify (5 preceding sentences +
question) — see §4.

### 2.2 What Claimify does to stay faithful (NOT substring matching)

Two mechanisms, both semantic:

**(i) Generation-time faithfulness constraints** baked into every stage prompt:
- "Do NOT use any external knowledge beyond what is stated in the question, context, and sentence"
  (Disambiguation, all 3 impls — `repo_findings/claimify_impls.md:105-106`, `:379`).
- The `[...]` bracket convention flags inferred-not-stated content, "which is inherently less
  reliable than content explicitly stated in the source sentence" (`paper_text.md:144`) — a
  *graded* provenance marker, the spiritual ancestor of a `span_verbatim` flag.
- Decomposition retains attribution ("if the sentence indicates a specific entity said/did
  something … retain this context", `claimify_impls.md:115-116`) so claims don't silently promote
  "John highlights X" to a bare "X".

**(ii) Evaluation-time ENTAILMENT check** — the load-bearing faithfulness primitive:
- Definition: "Entailment means that if the source text is true, the extracted claims must also be
  true" (`paper_text.md:36`). This is the relation, full stop.
- Implementation: an **LLM prompt**, after a pretrained NLI model failed (`paper_text.md:189-191`,
  Appendix H `:680-684`). The prompt (N.2.1, `paper_text.md:1064-1082`) instructs the judge to
  (a) restate S and C verbatim, (b) enumerate ALL elements of C, (c) check each element: "If
  <maximally clarified S given its context>, does this necessarily mean <element of C>?",
  (d) "You CANNOT use any external information," and (e) the **Statements and Actions Rule**: "John
  highlights X" does NOT entail "X" — it entails "John highlights X" — so decontextualization that
  drops attribution is caught as non-entailment (`:1082`). Critically: "**if the context of S
  entails C, but S itself does not, you should still conclude that S entails C**" (`:1080`) — i.e.
  entailment is judged over **sentence + context + question**, never the sentence string alone.
- Result: Claimify reaches **99% entailed** (≥95% across models) (`paper_text.md:193`, `:296`),
  tying VeriScore, beating DnD/SAFE — and the ablation shows removing Selection (the verifiability
  gate) causes the largest entailment drop (`:257`). Faithfulness comes from *generation
  discipline + an entailment judge*, never from string containment.

There is **no substring/verbatim-quote requirement anywhere in Claimify** — the design is the
opposite: the output is deliberately *not* a span of the input.

### 2.3 Option (b) in DnDScore / VeriScore / SAFE — entailment/"strongly implied," explicitly NOT explicit-match

- **DnDScore** (arXiv 2412.13175, read pp.1-6): verifies the atomic subclaim *with its
  decontextualized form as context* against the source document (§4.2, p.6; Appendix A.5 prompt).
  Motivation = our exact problem: decompose-then-decontextualize makes the unit "no longer atomic …
  which portion of the claim is being validated?" (p.6). Their DecompScore correlates with **NLI
  entailment** (§3.4) — the grounding primitive is entailment, and the *contract* is a (subclaim,
  decontextualized-claim) **pair** (option c).
- **SAFE** (`rate_atomic_fact.py:51-65`): the verdict prompt says "Determine whether the given
  STATEMENT is supported by the given KNOWLEDGE. The STATEMENT **does not need to be explicitly
  supported** by the KNOWLEDGE, but **should be strongly implied** by the KNOWLEDGE" → final answer
  `Supported`/`Not Supported`. Explicitly an entailment ("strongly implied") test, the antithesis of
  substring containment.
- **VeriScore** (`prompt/verification_instruction_binary.txt:5`): "**Supported**: everything in the
  claim is supported and nothing is contradicted by the search results" — supported, not quoted.
- **FActScore / Molecular Facts**: verification is retrieval-then-support against an external KB
  (`claimify_impls.md:249`, `:333-358`) — never against a verbatim source span.

Across **all** decompose-then-verify systems, the grounding relation is **support/entailment**
("strongly implied"), never literal containment. The substring gate is unique to the
extract-everything baseline and has no analog in the surveyed literature.

### 2.4 The four options, scored for ugm at scale

| Option | What it is | Precision | Recall (vs decontextualized claims) | Cost @ scale | Provenance/audit | Verdict for ugm |
|---|---|---|---|---|---|---|
| **(a) char-span pointers** char-start/char-end for a verbatim SOURCE span, separate from `claim_text` | Find the chunk slice the claim derives from; store offsets | High *as a pointer*; **0 as a gate** for standalone claims | **Catastrophic as a gate** (most decontextualized claims have no verbatim slice) | ~0 (string search / model-returned offsets, deterministic) | **Excellent** — exact bytes, D7-recomputable | **Keep the FIELD, drop the GATE.** Span is the audit half of (c); never the acceptance rule. |
| **(b) entailment / NLI** "is C entailed by chunk T (+context)?" | Semantic support check | High (Claimify 99%; SAFE/VeriScore "strongly implied") | High — *built for* standalone claims | Pretrained NLI ≈ free but **inadequate** (Claimify abandoned it, `:189`); LLM judge = +1 call/claim if separate | Weak alone (a boolean, no locator) | **The right ACCEPTANCE RULE** — but run it *inside* the E2 call (free), not as a separate pass. |
| **(c) BOTH `source_span` + decontextualized `claim_text`** | Provenance span ∥ retrieval/reasoning text | High | High | ~0 marginal over (a)+(b) | **Excellent** | **Recommended schema.** Exactly DnDScore's (subclaim ∥ decontextualized) contract. |
| **(d) LLM self-check faithfulness pass** | A second LLM judges each claim | High | High | **+1 call/claim if a separate pass** (most expensive); ~0 if folded into extraction | Boolean | **Adopt the SIGNAL, not the extra pass.** Emit a per-claim self-verdict in the *same* structured output (no second call) — preserves D4. |

**Why not (a) as the gate:** it is the baseline's bug. A verbatim span cannot exist for a claim whose
text was rewritten for standalone-ness; gating on it either rejects good decontextualized claims
(false negatives, recall collapse) or forces the prompt to emit non-standalone "quotable" claims
(defeats E2). The span is *provenance*, never *acceptance*.

**Why not (d) as a separate pass:** a dedicated faithfulness model call per claim is the most
expensive option and duplicates work the extraction LLM already does in-context — it violates D4
(cheap-first) and D19's "ride the call you're already making" logic. Claimify's entailment check is
an *evaluation* tool run offline on samples (80 claims, `:191`), not a per-claim production gate;
ugm should not put a full second model on the hot write path when the verdict can be co-emitted.

**Cost arithmetic.** At 1M docs × ~k chunks × ~m claims, a separate entailment/judge call per claim
roughly **doubles** E2 LLM spend (E2 is already the expensive layer the D25-D30 value gate exists to
withhold). Folding a per-claim `grounded` self-verdict + `source_span` offsets into the single
existing structured-output call is **~0 extra tokens of output and zero extra calls** — the only
sustainable choice at this scale and the one consistent with the value gate's whole economic premise.

---

## 3. Confidence & gaps

- **HIGH** — Claimify uses entailment (LLM prompt), not substring matching, and abandoned pretrained
  NLI. Read directly: `paper_text.md:36`, `:187-193`, `:1064-1082`, Appendix H `:680-684`. The
  extract-everything baseline's substring gate and discarded evidence-quote are a known anti-pattern:
  it gates on normalized substring containment, carries the verbatim evidence-quote only on the
  extracted-claim schema, and never persists it onto the claim record.
- **HIGH** — DnDScore keeps and verifies BOTH atomic subclaim and decontextualized form
  (option c); SAFE/VeriScore use "strongly implied"/"supported" not containment. Read at source
  (DnDScore pp.1-6; `rate_atomic_fact.py:51-65`; `verification_instruction_binary.txt:5`).
- **MEDIUM** — DnDScore's exact verification prompt wording is in its Appendix A.5, which I did not
  page to; I relied on the §4.2 body description (p.6) + Table 1. The *contract shape* (pair of
  fields) is verified; the precise prompt template is inferred from the body.
- **MEDIUM** — Claimify's reported 99% entailment is a benchmark on long-form QA answers
  (`paper_text.md:193`), **not** measured on B2B project-memory chunks; transfer to ugm's domain is
  an assumption. No ugm golden-set entailment number exists yet (it should — see §4, ties to D22).
- **GAP / could not verify** — whether a model can reliably emit *correct* char-start/char-end
  offsets directly (LLMs are notoriously poor at character counting). **Recommend** computing offsets
  deterministically post-hoc (locate the model-emitted `source_quote` in the chunk via normalized
  search → derive offsets), *not* trusting model-emitted integers. This needs a spike.
- **GAP** — entailment-judge precision on the ugm domain, and the false-accept rate of an
  *in-call self-verdict* vs an *independent judge* (self-grading is known to be optimistic). The
  honest mitigation is a sampled offline independent-judge audit (Claimify's own 80-claim
  methodology), exactly like D29's sampled deferred-stream audit — not a per-claim second call.

---

## 4. Recommendation for ugm — the concrete grounding contract to replace the verbatim-substring gate

Replace string-containment with a **dual-field, entailment-accepted** contract. This is option (c)
schema + option (b) acceptance + option (d)-as-in-call-signal, and it is DnDScore's pattern adapted
to ugm's single-chunk-now / windowed-later E2 extraction.

### 4.1 Schema changes

**`ExtractedClaim`** (the extracted-claim schema) — what the E2 LLM emits per claim:
```python
class ExtractedClaim(BaseModel):
    claim_text: str            # DECONTEXTUALIZED, standalone (D19 coref already applied)
    claim_kind: ClaimKind
    source_quote: str          # verbatim span the claim derives from (best-effort; provenance)
    grounded: bool             # SELF-VERDICT: is claim_text entailed by THIS chunk's text? (option b/d, in-call)
    grounding_note: str | None # one-line rationale when grounded is borderline/false (audit)
    confidence: float = Field(ge=0, le=1)
```
(Name the verbatim evidence-quote field `source_quote` to signal "provenance span," not "acceptance
token.")

**The claim record / claim model** — what is PERSISTED (this is the real fix: stop
discarding provenance):
```python
    source_quote: str | None = None        # verbatim chunk slice (audit / highlight)
    source_char_start: int | None = None   # offset into supporting chunk (deterministic, D7-recomputable)
    source_char_end: int | None = None
    span_verbatim: bool = False            # was claim_text itself a verbatim substring? (soft signal, NOT a gate)
    grounding_verdict: bool = True         # stored entailment self-verdict (replay-from-storage, D27-style)
```
`source_char_start/end` are offsets into the supporting chunk; combined with the chunk's own
section-parent character offsets (a property the ugm E1 chunk model provides by design) they yield
document offsets for free. This finally propagates the span substrate that already exists at the chunk
level down to the claim level.

### 4.2 Acceptance rule (the new grounding gate → `validate_claim_grounding`)

```
accept(claim, chunk) iff:
  1. claim_text non-empty                                    # unchanged
  2. claim.grounded is True                                  # ENTAILMENT self-verdict (option b/d), the gate
  3. chunk.scope_project is not None  (for project claims)   # unchanged project-scope check
  # NOTE: NO substring requirement on claim_text.
```
Then **deterministically** (no model trust for integers): locate `source_quote` in `chunk.text` via
the existing normalized search. If found → set `source_char_start/end` and `span_verbatim=True`. If
NOT found → `span_verbatim=False`, `source_char_start/end=None`, **and accept anyway** (a
decontextualized claim legitimately has no verbatim slice). The old "evidence-quote not found in
chunk" **hard reject is deleted** and becomes a recorded soft flag. Empty `source_quote` is allowed
(pure-inference claims), only down-weights `span_verbatim`.

Acceptance hinges on **entailment** (`grounded`), produced in the existing single E2 structured-output
call by adding a per-claim instruction modeled on Claimify's entailment rule (`paper_text.md:1070-1082`)
— including the **Statements and Actions Rule** so attribution-dropping ("John says X" → "X") is
caught — and the hard faithfulness constraint "use ONLY this chunk; do not use external knowledge"
(`claimify_impls.md:105-106`). The "exact quote" framing of an extract-everything prompt must be
**rewritten**: it should ask for a standalone claim PLUS a best-effort supporting quote PLUS a grounded
self-verdict — never demand the claim be quotable.

### 4.3 How this satisfies the decision log

- **D4 (cheap-first cascade):** entailment verdict + span are **co-emitted in the call that already
  runs** — zero extra model calls, zero extra round-trips. No separate NLI model (Claimify proved it
  inadequate, `:189`), no separate judge pass (option d's expensive form). A *frontier* independent
  entailment judge is reserved, D4-style, for the **offline sampled audit**, never the hot path.
- **D7 (rebuildable):** `source_char_start/end` and `span_verbatim` recompute deterministically from
  immutable E0/E1 (chunk text + offsets) on every rebuild. `grounding_verdict` is **stored &
  auditable, replay-from-storage** — exactly D27's treatment of the non-deterministic salience rung
  ("rebuildable" = stored, not recomputed, for model-endpoint-drift rungs).
- **D12 (per-doc trigger) / D19 (coref-in-call):** grounding rides the same per-document E2
  extraction call that already does coref; no new stage, no new infra.
- **D25-D30 (value gate economics):** the whole gate exists to withhold the expensive E2 layer; adding
  a *second* per-claim LLM grounding call would undo that saving. The in-call self-verdict keeps E2 a
  single call, consistent with the gate's break-even discipline (D30).
- **Replacing the anti-pattern:** delete the substring hard-reject; persist `source_quote` + offsets +
  flags on the claim record (stop the discard); update the grounding contract — flip "decontextualized
  claim with no verbatim slice" from *reject* to *accept with `span_verbatim=False`*, and add a case
  asserting an attribution-dropping claim is rejected by the `grounded` verdict (Claimify's
  Statements-and-Actions case). Add a golden set of (chunk, claim, expected-grounded) pairs for the
  entailment self-verdict, tied to D22's golden-eval discipline; CI fails if the self-verdict regresses
  on planted faithful/unfaithful canaries (mirrors D29's canary-fact harness).
- **Open spike (ties to §3 gaps):** measure in-call self-verdict precision/recall vs an independent
  entailment judge on a ugm golden slice before trusting `grounded` as the sole gate; if self-grading
  proves optimistic, escalate only the borderline-confidence band to a cheap independent judge
  (a D4-style cascade), never every claim.
