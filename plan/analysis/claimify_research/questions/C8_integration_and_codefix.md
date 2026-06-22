# C8 — Integration + reference E2 extractor design: Claimify-style E2 vs. the naive single-chunk baseline

Question C8 asks for (A) a ugm E2 redesign as a Claimify-style multi-stage pipeline over
E1 context-prefixed chunks with neighbor context + in-call coref (D19), composing with the
E1.5 value gate (D25–D30) and feeding E3 relations — including the one-call-vs-staged tradeoff
at millions-of-docs scale, and persistence of selection/decontextualization decisions for
audit/rebuild (D7) and idempotency (D12); (B) a concrete reference E2 extractor design that
moves past the naive single-chunk baseline (new claim schema, the grounding gate that replaces
verbatim-substring checking, new prompt, neighbor/document context plumbing); (C) new decisions
D31+; (D) an eval plan reusing Claimify's own metrics.

Citations use `file:line` for the public comparison repos and `paper_text.md:line` for the
Claimify paper (`claimify_deshwalmahesh/paper_text.md`, arXiv 2502.10855). VERIFIED = read at
source. INFERENCE = reasoned, flagged.

---

## 1. Key findings

- **The naive single-chunk baseline is "FActScore-shaped," which Claimify's own ablation says is
  the worst configuration.** It is a single structured-output call over **one chunk with no
  neighbors, no document, no question/header**. FActScore — the only surveyed system that extracts
  a bare sentence with no surrounding context — is flagged in the archaeology as "the maximal
  de-contextualization risk" (`repo_findings/claimify_impls.md:287-294`). And the paper's
  ablation found **removing the Selection stage "caused the largest performance drop"**
  (`paper_text.md:257`) — the extract-everything baseline has *no* Selection stage at all, so it
  inherits exactly the failure Claimify isolates: it extracts non-verifiable opinions/intros/
  conclusions as if they were facts, and emits claims with dangling pronouns the lone-chunk call
  cannot resolve.

- **The verbatim-substring grounding gate is actively in tension with decontextualization and is
  the single biggest blocker to a Claimify-style E2.** That anti-pattern requires the verbatim
  evidence-quote field to be a verbatim substring of the chunk (normalized casefold+whitespace).
  But a *decontextualized* claim ("Alice Novak joined Acme as VP of Engineering in March 2024") is
  by construction **not** a substring of any single chunk — the date came from a header, "Acme"
  from a preceding sentence, "Alice Novak" from a full-name mention three sentences up. The
  verbatim-substring gate mechanically rejects every well-decontextualized claim and only admits
  copy-paste fragments. This must be replaced with a span-offset + entailment-style grounding
  check, not a substring check.

- **At millions-of-docs scale, do NOT do the literal 3-separate-calls-per-sentence Claimify
  loop, and do NOT keep the naive 1-call-per-chunk baseline.** The right point on the curve is
  **one structured-output call per chunk** that runs Selection → Disambiguation → Decomposition
  as labeled *fields of a single typed response* over the **context-prefixed chunk + bounded
  neighbor window** (the E1 context prefix already supplies the document/header metadata
  Claimify renders as "metadata", `overall_design.md:94`, `paper_text.md:112`). Claimify uses
  separate stages because gpt-4o-2024-08-06 at temp 0 was the frontier in early 2025
  (`paper_text.md:185`); a current frontier model can carry the staged *reasoning* inside one
  response while a Pydantic schema enforces the staged *structure* — this is exactly what
  `claimsmcp` does (one structured request per stage, no voting, `repo_findings/claimify_impls.md:156-158`)
  collapsed one step further to one request per chunk. The tradeoff is **latency/cost (1 call
  vs ~3N) bought at the price of losing per-stage voting** (Claimify votes 3×/min-2 on Selection
  and Disambiguation, `repo_findings/claimify_impls.md:97,110`). The mitigation is to keep the
  *intermediate-reasoning fields* in the schema (selection verdict, ambiguity analysis,
  `cannot_decontextualize` flag) so the single call is auditable and the discard rules still
  fire — you lose voting robustness, not the staged logic. **This is the only economically sound
  shape** given E2 already runs over every FULL/promoted section at fleet scale (D25).

- **Selection (the verifiability + ambiguity-discard gate) is CLAIM-level and is distinct from
  the E1.5 CHUNK-level value gate — they compose, they don't overlap.** E1.5 decides *whether to
  pay for E2 at all* on a section (cheap-first cascade, defer-don't-DROP, D25–D30,
  `e1_5_value_gate_design.md:30-41`). Claimify-Selection decides, *inside* an E2 call that E1.5
  already greenlit, *which sentences/spans of that chunk become claims* and *drops* ambiguous
  ones. The archaeology states this precisely: "The CHUNK-level value gate (E1.5, D25–D30) is a
  distinct earlier filter; the only CLAIM-level selection analog in these repos is Claimify's
  Selection stage" (`repo_findings/claimify_impls.md:393`). So E2 gains its *own* discard
  reasons that must be persisted (audit), and they are orthogonal to the gate verdict.

- **Decontextualization decisions and selection drops must be persisted as first-class E2 state,
  exactly mirroring D27's treatment of gate verdicts** — append-only, versioned, replay-from-
  storage (the LLM rung is not deterministically recomputable, `e1_5_value_gate_design.md:104`,
  `SYNTHESIS.md:309-313`). The naive baseline stores nothing about *why a span was dropped* or
  *what was added during decontextualization*: dropped content simply vanishes (the per-chunk loop
  just skips it), and accepted claims store only final text. For D7 rebuild + D12 idempotency +
  the eval plan (D), E2 needs an append-only `claim_extraction_decisions` ledger.

---

## 2. Evidence & detail

### 2.1 (A) The E2 redesign: staged logic, one call, over context-prefixed chunks + neighbors

**Canonical Claimify shape (the target).** A 4-stage decompose-then-verify extractor over a
question–answer pair, processed sentence-by-sentence (`repo_findings/claimify_impls.md:16-53`):

- **Selection** (§3.2): per-sentence verifiability gate; returns *drop* / *rewrite-to-verifiable*
  / *unchanged* (`paper_text.md:116-124`, prompt `claimify_deshwalmahesh/src/prompts.py:1-46`).
  Decoupled from ambiguity on purpose — Selection judges verifiability only, assuming the
  fact-checker can resolve ambiguities (`prompts.py:6`).
- **Disambiguation/decontextualization** (§3.3): resolve partial names, undefined acronyms,
  referential + structural ambiguity using *question + context*; **discard rule** — if a group
  of readers would fail to reach consensus, output "Cannot be decontextualized" and drop the
  sentence (`paper_text.md:128-136`, `prompts.py:49-97`, discard at `:96`). Forbids external
  knowledge (`prompts.py:60`) — the deliberate contrast with Molecular Facts, which the paper
  criticizes for using parametric knowledge and "risk[ing] introducing factual inaccuracies"
  (`paper_text.md:286`).
- **Decomposition** (§3.4): split into simplest decontextualized propositions, each annotated
  with `[...]` essential-context brackets (`paper_text.md:142`, `prompts.py:99-184`).

**Context windows (VERIFIED).** Selection = 5 preceding + 5 following sentences;
Disambiguation/Decomposition = 5 preceding + 0 following (`paper_text.md:582-583`,
`repo_findings/claimify_impls.md:21-34`). The target sentence is passed *separately* from the
excerpt, and the originating question + document metadata (Markdown header hierarchy) are always
in-prompt (`paper_text.md:112`). **The LLM never sees the bare sentence alone** — this is the
crux the naive single-chunk baseline violates.

**How this maps onto ugm's units.** Claimify's "sentence" → ugm's **chunk** (semchunk, D-E1).
Claimify's "question" → there is none in a memory-ingestion setting; the analog is the
**document/section header + E1 context prefix** (the contextual-retrieval prefix E1 already
prepends per chunk, `overall_design.md:94`). The archaeology notes claimeai already runs a
**question-agnostic** Claimify (drops the "question" framing entirely,
`repo_findings/claimify_impls.md:216-218`) — proof the pipeline works without a question, which
is what ugm needs. Claimify's "5 preceding/5 following sentences" → ugm's **neighbor chunks**,
which are trivially fetchable because ugm's E1 chunk model carries, by design, a section-parent
reference plus character offsets: neighbors are the chunks with the same section-parent reference
whose character offsets bracket the target.

**One call vs staged calls — the scale argument.** Claimify runs 3 calls per sentence (plus
voting: 3 completions on Selection + Disambiguation), i.e. ~7–9 LLM calls per sentence
(`repo_findings/claimify_impls.md:97,110,123`). At ugm's target (1M docs × N sections × M
chunks/section, all FULL/promoted sections through E2 per D25), that multiplier is unaffordable
and is *pure latency on the per-document Cloud Tasks chain* (D12). The recommended shape:

- **One `responses.parse` call per chunk**, schema = a single response object whose fields are
  the staged Claimify reasoning (selection verdict + rewritten span, ambiguity analysis +
  `cannot_decontextualize`, then the list of decontextualized claims). This is `claimsmcp`'s
  "one structured request per stage, no voting" (`repo_findings/claimify_impls.md:156-158`)
  fused to one request per chunk.
- **Tradeoff, stated honestly:** you lose Claimify's multi-completion voting (its robustness
  lever against a single bad completion) and you ask the model to hold three reasoning modes in
  one response. You keep: the staged *logic*, the discard rules, full auditability (the
  intermediate fields are persisted), in-call coref (D19), and a ~7–9× call reduction. INFERENCE
  (flagged): a current frontier model at temp 0 with the staged fields *as scaffolding* will
  approximate staged quality; this must be **measured against a 3-call variant on a golden slice**
  (eval plan D) before committing — do not assume it for free. If the one-call variant loses
  >X pp on Selection precision or decontextualization desirability, fall back to splitting
  Selection (the highest-value stage per `paper_text.md:257`) into its own call and keeping
  Disambiguation+Decomposition fused.

**Composition with E1.5 (D25–D30).** E1.5 runs *before* E2 and emits FULL / DEFERRED /
CHUNKS-ONLY / dup at the **section** level (`e1_5_value_gate_design.md:30-75`). E2 only ever
runs on FULL sections (now) or DEFERRED sections at promotion (D28). So the E2 redesign is a
pure consumer of the gate — no change to the gate. The *new* coupling: E2's Selection stage is
the claim-level dual of E1.5's section-level salience — E1.5 says "this section is worth LLM
extraction," Selection says "this *span* is a verifiable claim." Both must persist their drops
so the eval plan can measure them separately (D). One subtlety to record: E1.5's "change-of-state
lexical up-weight" (the supersession-bearing-content proxy, `e1_5_value_gate_design.md:65`) and
E2's Selection both touch verifiability — keep them distinct (gate = pay-or-defer; Selection =
is-a-claim) to avoid double-counting in metrics.

**Feeding E3 (relations).** Decomposed, decontextualized claims are the input to E3
normalization (`concepts.md:26-54`): each claim → 0..n `(subject, predicate, object)` relations
via the predicate registry (D5/D18), with `(entity_id, predicate)` blocking for supersession
(D4, `concepts.md:147-164`). **Decontextualization is a hard precondition for E3 to work**: a
claim with a dangling "she" or a bare "the company" cannot be entity-resolved (T0 exact match on
the LLM-emitted canonical name form, D17) and cannot block for supersession. Lone-chunk claims
will routinely carry such danglers — which is *why* D19 mandates coref-in-call and why the
redesign is load-bearing for E3, not cosmetic.

**Persistence for audit / rebuild (D7) / idempotency (D12).** Mirror D27 exactly. The E2 call
produces, per chunk: (a) accepted claims (already → the claim record), and (b) **decisions** —
every sentence/span that was dropped at Selection (reason: intro/conclusion/opinion/no-verifiable-
content) or at Disambiguation (`cannot_decontextualize`), plus the decontextualization delta
(original span → decontextualized text + what was added and from where). Store (b) in an
append-only, versioned ledger:

```
claim_extraction_decisions  (append-only — the E2 transcript, mirrors gate_decisions)
  decision_id, evidence_id, chunk_id, scope_*,
  stage ∈ {selection, disambiguation, decomposition},
  outcome ∈ {claim_emitted, dropped_unverifiable, dropped_cannot_decontextualize,
             rewritten_to_verifiable},
  source_span_text, source_char_start, source_char_end,   -- offsets into the chunk/neighbors
  decontextualized_text nullable, added_context jsonb nullable,  -- the delta (what/where)
  claim_id nullable,            -- set when outcome=claim_emitted
  reason text nullable,
  extractor_version,            -- pinned model+prompt+window set (D12 versioning)
  decided_at
```

- **D7 (rebuildable):** like the gate, the deterministic parts (which neighbors were in-window,
  the chunk hashes) are recomputable, but the **LLM rung is replay-from-storage only**
  (`SYNTHESIS.md:309-313`) — so "rebuildable E2" means *stored & auditable*, not *recomputed*.
  Pin `extractor_version` AND store outputs. A rebuild loads stored claims + decisions; it does
  not re-call the model.
- **D12 (idempotency):** the worker is idempotent on the chunk content hash + `extractor_version`
  (the E1 chunk model carries a content hash by design); re-running an unchanged chunk at the same
  extractor version is a no-op (decisions + claims already present). This also fixes a latent gap
  in the extract-everything baseline: a content-derived claim-id function (stable hash of
  `evidence_id|chunk_id|claim_text`) keeps accepted claims idempotent, but **dropped content is
  invisible to idempotency** — the ledger closes that.

### 2.2 (B) Reference E2 extractor design (illustrative)

This is the *minimal, shippable* version — single chunk + neighbors, one structured call, staged
fields, span-grounded validation. It does **not** require E1.5 or E3 to exist; it is the
reference E2 extractor that supersedes the naive single-chunk baseline. The Python below is
illustrative ugm E2 DESIGN pseudocode.

**B.1 — Extracted-claim schema.** Supersede a bare extracted-claim schema with a staged response
that carries the audit fields. The verbatim evidence-quote field (a verbatim copy field) is
**removed** and replaced by `source_char_start`/`source_char_end` offsets + the
decontextualization delta:

```python
class SelectionVerdict(StrEnum):
    contains_verifiable = "contains_verifiable"
    no_verifiable_content = "no_verifiable_content"

class ExtractedClaim(BaseModel):
    claim_text: str                       # decontextualized, atomic, standalone
    claim_kind: ClaimKind
    # grounding: offsets into the TARGET chunk's text for the span this claim derives from
    source_char_start: int = Field(ge=0)
    source_char_end: int = Field(ge=0)
    # decontextualization audit: substrings the model ADDED that are NOT in the target chunk,
    # each tagged with which in-window source it came from (target | prev | next | prefix)
    added_context: list[AddedContext] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

class AddedContext(BaseModel):
    text: str
    source: Literal["target_chunk", "prev_chunk", "next_chunk", "context_prefix"]

class DroppedSpan(BaseModel):
    source_char_start: int = Field(ge=0)
    source_char_end: int = Field(ge=0)
    reason: Literal["intro", "conclusion", "opinion", "speculation",
                    "no_information", "cannot_decontextualize"]

class ClaimExtractionResult(BaseModel):
    selection_verdict: SelectionVerdict          # staged-reasoning field (audit + discard)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    dropped_spans: list[DroppedSpan] = Field(default_factory=list)   # the E2 transcript
```

Rationale, tied to the research: `added_context` is the *operationalization* of Claimify's
`[...]` essential-context brackets (`paper_text.md:142`) — but instead of free-text brackets we
record the added substring **and its in-window provenance**, which is what makes the substring
validator replaceable (B.2) and what feeds the decontextualization-rate metric (D). `dropped_spans`
is the Selection/Disambiguation transcript (mirrors `claimsmcp`'s structured stages,
`repo_findings/claimify_impls.md:148-166`).

**B.2 — The verbatim-substring grounding gate, replaced by window-grounding.** The verbatim-
substring rule is replaced by a **window-grounding** check: every character span the claim
asserts must come from *either* the target chunk *or* a declared in-window neighbor/prefix source.
This permits decontextualization while still rejecting hallucinated additions (the failure mode
Claimify guards against by forbidding external knowledge, `prompts.py:60`):

```python
@dataclass(frozen=True)
class GroundingResult:
    accepted: bool
    reason: str | None = None

def validate_claim_grounding(
    *,
    target_chunk: ChunkModel,
    window_texts: dict[str, str],      # {"target_chunk":..., "prev_chunk":..., "next_chunk":..., "context_prefix":...}
    claim: ExtractedClaim,
) -> GroundingResult:
    if not claim.claim_text.strip():
        return GroundingResult(False, "claim_text_empty")
    if target_chunk.scope_project is None:
        return GroundingResult(False, "project_claim_requires_project_scope")
    # 1. the cited source span must be a real, in-bounds slice of the TARGET chunk
    if not (0 <= claim.source_char_start < claim.source_char_end <= len(target_chunk.text)):
        return GroundingResult(False, "source_span_out_of_bounds")
    # 2. every ADDED substring must verbatim-exist in its DECLARED in-window source
    #    (this is the anti-hallucination gate that replaces the old whole-claim substring rule)
    for added in claim.added_context:
        src = window_texts.get(added.source)
        if src is None or _normalize(added.text) not in _normalize(src):
            return GroundingResult(False, f"added_context_not_in_{added.source}")
    return GroundingResult(True)
```

Key property: a decontextualized claim like *"Alice Novak joined Acme in March 2024"* now passes
because its `source_char_start/end` point at the verbatim span *"Alice joined"* in the target
chunk, and the additions `"Novak"` (→ prev_chunk), `"Acme"` (→ context_prefix), `"March 2024"`
(→ prev_chunk) each verbatim-exist in their declared in-window source. A claim that invents
`"in San Francisco"` (in no window source) is rejected — exactly the grounding guarantee the
verbatim-substring rule provided, but at the *added-span* granularity instead of the whole-claim
granularity. The `_normalize` helper is reused unchanged. (Note: `_normalize`'s casefold+whitespace
collapse makes offsets approximate after normalization — keep the offsets on the *raw* chunk text
and normalize only for the membership test, as above.)

**B.3 — Extractor prompt.** Replace a minimal system prompt with a Claimify-condensed system
prompt and a user prompt that supplies the **context prefix + neighbor window + target chunk**,
with the target clearly delimited (Claimify's `<SOS>…<EOS>` / "Sentence:" pattern,
`repo_findings/claimify_impls.md:75,205`):

> **System prompt** (condensed Selection→Disambiguation→Decomposition; derived from
> `prompts.py:1-184`, not hand-waved):
>
> "You extract atomic, verifiable, decontextualized project-memory claims from a TARGET chunk,
> using its surrounding context only to resolve references — never to add outside facts.
>
> SELECTION — A claim is *verifiable* if it states a specific proposition that could be checked
> true or false. Do NOT emit: introductions, conclusions/summaries, opinions, generic advice,
> speculation ('could lead to…'), or statements about a lack of information. If a sentence mixes
> verifiable and unverifiable content, keep only the verifiable part. If the TARGET contains no
> verifiable proposition, set selection_verdict=no_verifiable_content and return no claims.
>
> DECONTEXTUALIZATION — Each claim must stand alone. Resolve every pronoun, partial name,
> acronym, and 'the <thing>' reference using the context prefix and neighbor chunks. Substitute
> full entity names when they appear in context. You MUST record each substring you ADD (that is
> not already in the TARGET chunk) in added_context, tagged with which source it came from
> (prev_chunk, next_chunk, or context_prefix). Vagueness and generality are NOT ambiguity — do
> not invent precision. If a sentence has multiple plausible interpretations and the context does
> not let a careful reader pick one, DROP it: add a dropped_spans entry with
> reason=cannot_decontextualize. Do NOT use any knowledge beyond the provided text.
>
> DECOMPOSITION — Split into the simplest standalone propositions. If a sentence says a specific
> entity said/did something, retain that attribution. For each emitted claim, set
> source_char_start/source_char_end to the character offsets (into the TARGET chunk text) of the
> span it derives from. Record every dropped or rewritten span in dropped_spans."

> **User prompt:**
> ```
> context_prefix:
> {chunk.context_prefix_or_document_header}
>
> prev_chunk:
> {prev_text or "(none)"}
>
> next_chunk:
> {next_text or "(none)"}
>
> TARGET chunk (chunk_id={chunk.chunk_id}, evidence_id={chunk.evidence_id}):
> <<<
> {chunk.text}
> >>>
> ```

This realizes D19 (coref satisfied *inside* the extraction call, all languages,
`decisions.md:384-398`) and the paper's "target + neighbors + metadata, never bare"
(`paper_text.md:112`). It is one call — no per-stage fan-out — keeping the per-document chain fast.

**B.4 — Passing neighbor/document context into the call.** The per-chunk extraction orchestration
extracts one chunk at a time with no neighbors in the naive baseline. Change it to build a
per-chunk window from the chunks it already has in hand. Because all chunks of a document share
the section-parent reference and carry character offsets, neighbors are a sort + index lookup,
no extra fetch:

```python
def extract_claims_from_chunks(chunks, embeddings, extractor, *, claim_extraction_concurrency=1):
    by_parent: dict[str, list[ChunkModel]] = defaultdict(list)
    for c in chunks:
        by_parent[c.parent_id].append(c)
    for siblings in by_parent.values():
        siblings.sort(key=lambda c: (c.char_start if c.char_start is not None else 0))
    index = {c.chunk_id: (c.parent_id, i)
             for sibs in by_parent.values() for i, c in enumerate(sibs)}

    def window_for(chunk: ChunkModel) -> ChunkWindow:
        parent_id, i = index[chunk.chunk_id]
        sibs = by_parent[parent_id]
        return ChunkWindow(
            target=chunk,
            prev=sibs[i - 1] if i > 0 else None,
            next=sibs[i + 1] if i + 1 < len(sibs) else None,
        )
    # extractor.extract_claims(window_for(chunk)) per chunk; validate via validate_claim_grounding;
    # persist accepted claims AND result.dropped_spans into claim_extraction_decisions.
```

The `ClaimExtractor` Protocol changes from `extract_claims(chunk)` to `extract_claims(window)`.
**Scope guard (VERIFIED constraint):** only chunks sharing the same section-parent reference and
the same scope may be neighbors — never cross `scope_project`/`scope_session` (the grounding gate
already enforces project scope). **Cross-document coref remains an open recall gap** — D19
explicitly says intra-document coref does not solve it (`decisions.md:400-404`); this design is
intra-document only, which is correct and in-scope.

### 2.3 Why the verbatim-substring rule and lone-chunk call are the diagnosable defects

- The verbatim-substring grounding gate rejects any claim whose evidence isn't a verbatim chunk
  substring. Decontextualized claims are never verbatim substrings → either the model is being
  pushed to emit copy-paste fragments (defeating decontextualization) or good claims are silently
  dropped by the per-chunk loop. Both are bad; both are fixed by B.2.
- The lone-chunk call is FActScore-shaped — the archaeology's "maximal de-contextualization risk"
  (`repo_findings/claimify_impls.md:287-294`) — and has no Selection stage, the ablation's
  most-costly omission (`paper_text.md:257`). Fixed by B.1+B.3.

### 2.4 (C) New decisions to propose (D31+)

> Continues the log after D30 (`decisions.md:566`). Numbers/thresholds are golden-set placeholders
> per the D17–D30 provenance note (`decisions.md:338-343`).

- **D31 — E2 is a Claimify-staged extractor in ONE structured-output call per chunk, over the
  E1 context-prefix + bounded neighbor window.** Stages = Selection (verifiability + rewrite) →
  Disambiguation (decontextualization + consensus-discard) → Decomposition (atomic standalone
  claims), expressed as fields of a single typed response, not as 3 separate calls. Justification:
  staged *logic* preserved + auditable; ~7–9× fewer calls than canonical Claimify; voting traded
  away (mitigated by persisting intermediate reasoning). The one-call-vs-staged split point is a
  measured decision, re-evaluated per `extractor_version` on the golden set (D); fall back to a
  dedicated Selection call if one-call loses >X pp. Composes downstream of E1.5 (D25), upstream of
  E3 (D2). (Refines D4's cheap-first philosophy and satisfies D19 in-call coref.)

- **D32 — Claim grounding is window-membership, not chunk-substring.** Every emitted claim cites
  a verbatim source span (char offsets into the target chunk) and declares every added substring
  with its in-window provenance (`prev_chunk`/`next_chunk`/`context_prefix`); validation accepts
  iff the source span is in-bounds and every addition verbatim-exists in its declared source.
  Replaces the verbatim-whole-claim-substring rule, which is incompatible with decontextualization.
  No external knowledge (Claimify faithfulness, contra Molecular Facts — `paper_text.md:286`).

- **D33 — E2 selection-drops and decontextualization deltas are first-class, append-only,
  versioned Postgres state (`claim_extraction_decisions`), mirroring D27.** Every dropped span
  (with reason) and every decontextualization addition is persisted, stamped with
  `extractor_version`. Rebuild reads stored claims+decisions and never re-calls the model
  (D7 = stored & auditable for the LLM rung, not recomputed). Idempotent on the chunk content hash
  + `extractor_version` (D12). Enables the decontextualization-rate + selection precision/recall
  metrics (D) with no extra labeling of dropped content.

- **D34 — E2's Selection gate is the claim-level dual of E1.5's section-level value gate and is
  kept metrically separate.** E1.5 decides pay-or-defer per section (D25); Selection decides
  is-a-verifiable-claim per span. They never substitute for each other; metrics report them on
  separate axes (gate false-skip rate vs. Selection precision/recall) to avoid double-counting.

### 2.5 (D) Eval plan — reuse Claimify's own metrics

Claimify's framework evaluates three factors: **entailment, coverage, decontextualization**
(`paper_text.md:34-38`). Reuse all three; add ugm-specific selection + neighbor-window probes.

- **Decontextualization rate (Claimify §2.3, outcome-based).** For a sample of emitted claims `c`,
  generate `c_max` (maximally decontextualized, with `c` entailed by `c_max`), retrieve evidence
  for both, and classify into the **7 result types** (`paper_text.md:72-96`); the desirable types
  are **1, 2, 4, 7** and the headline metric is the **% desirable**
  (`paper_text.md:275,284`). ugm shortcut using D33's stored state: a cheap proxy
  decontextualization-rate = fraction of accepted claims whose `added_context` resolved all
  pronouns/partial-names (no dangling reference remains) — run the full 7-type eval on a labeled
  subset, the proxy on the full stream. This directly measures whether B.1–B.3 fixed the
  lone-chunk dangling-reference problem.

- **Selection precision / recall (Claimify §5.2 coverage).** Use **element-level coverage**
  (`paper_text.md:48-52`): break each source sentence into elements, label each verifiable /
  unverifiable, then score the extracted claims — TP = verifiable element covered, FP =
  unverifiable element *explicitly* covered, FN = verifiable element not covered
  (`paper_text.md:50`). Report **macro-F1** as Claimify does (it hit 91.2% sentence-level,
  `paper_text.md:226`). Selection *precision* = of emitted claims, fraction that are genuinely
  verifiable (low FP = not extracting opinions/intros); Selection *recall* = of verifiable
  elements, fraction covered (low FN = not dropping real facts). D33's `dropped_spans` give the
  *predicted* negatives for free, so only the gold element labels need annotation.

- **Coverage (Claimify §2.2).** Element-level coverage as above is the coverage metric; also
  report **sentence-level coverage** (does the extractor correctly decide a sentence contains ≥1
  claim, `paper_text.md:222-226`) as the cheaper aggregate. The golden set is the human-annotated
  verifiable/unverifiable element labels; reuse the D22 / O6 golden-set machinery
  (`decisions.md:442-457`) — the gate-verdict golden set (D30) and this claim-verifiability golden
  set are siblings.

- **Entailment (Claimify §5.1).** % of emitted claims entailed by the source text
  (`paper_text.md:187,277`). This is the **grounding metric for D32**: a claim that adds
  unwindowed content should fail entailment; track entailment-fail rate as the leading indicator
  that the grounding validator (B.2) is too loose or too strict.

- **One-call-vs-staged ablation (the D31 decision evidence).** Run the same golden slice through
  (i) one-call (D31), (ii) Selection-split + Disamb/Decomp-fused, (iii) full 3-call Claimify with
  voting. Compare on entailment, element-level coverage F1, and % desirable decontextualization
  — this is the measured basis for D31's one-call commitment, replicating the paper's own
  variant ablation (`paper_text.md:257,284`) which found Selection removal most costly.

- **Neighbor-window ablation.** Vary the window (0/0 = lone-chunk baseline; ±1 chunk;
  ±2 chunks; + context prefix) and measure decontextualization desirability + entailment.
  Expect the 0/0 baseline (the naive single-chunk shape) to be worst on decontextualization — this
  quantifies the value of B.4 and ties to the archaeology's FActScore-is-riskiest finding
  (`repo_findings/claimify_impls.md:287-294`).

---

## 3. Confidence & gaps

**HIGH confidence:**
- The naive single-chunk baseline is single-chunk, neighbor-free, Selection-less, and uses a
  verbatim-substring grounding rule incompatible with decontextualization (this is the documented
  FActScore-shaped anti-pattern E2 must avoid).
- Claimify's stage roles, context windows, discard rules, and eval metrics (VERIFIED at
  `paper_text.md` and the three impl ports via the archaeology).
- The B.1–B.4 design is implementable with the data ugm's E1 chunk model provides by design (the
  section-parent reference, character offsets, and content hash).

**MEDIUM confidence (INFERENCE, flagged):**
- That a single frontier-model structured call reliably reproduces staged Claimify quality
  *without* voting. The paper used separate stages + voting on an early-2025 model
  (`paper_text.md:185`); `claimsmcp` already drops voting per stage but still keeps 3 calls
  (`repo_findings/claimify_impls.md:156-158`). The one-call collapse is a reasonable bet but
  **must be measured** (eval D's ablation) — do not lock D31 as committed until the golden-slice
  ablation clears it. This is the single biggest open question in the integration design.
- The exact E1 context-prefix contents (I read its *purpose* — contextual-retrieval prefix,
  `overall_design.md:94` — but the E1 design doc is marked "future", `overall_design.md:178`, so
  the precise prefix string the user prompt should render is not yet specified). The design treats
  it as an opaque `context_prefix` field; finalize once `e1_chunks_design.md` lands.

**GAPS / could-not-verify:**
- No Claimify benchmark number is invented here; all cited numbers (91.2% macro-F1, 89.6% etc.)
  are from the read sources (`paper_text.md:226`, `SYNTHESIS.md:34`). I did **not** independently
  reproduce them.
- E1.5, E3, and the `claim_extraction_decisions` table are surrounding ugm stages and proposed
  target state, not yet-existing components (the schema is the proposed target). The B-design is a
  self-contained reference E2 extractor; D31–D34 are proposals.
- Cross-document coref recall (D19's acknowledged gap, `decisions.md:400-404`) is **not** addressed
  by this design and remains open.
- Token-budget impact of the neighbor window on the per-call cost at fleet scale is not modeled
  here (out of C8 scope; should be folded into D30's break-even discipline since E2 is the cost
  center, `e1_5_value_gate_design.md:11`).

---

## 4. Recommendation for ugm

**Adopt the reference E2 extractor design now, in this order, as a self-contained unit** (no
E1.5/E3 dependency):

1. **B.2 + B.1 first (unblock decontextualization):** replace the verbatim-substring grounding
   gate with `validate_claim_grounding` (window-membership, D32) and adopt the staged
   extracted-claim schema. This alone stops the verbatim-substring rule from silently rejecting
   good claims.
2. **B.4 (neighbor window):** make the per-chunk extraction orchestration build the ±1 (then ±2)
   sibling window from the section-parent reference + character offsets — zero extra fetches,
   satisfies D19 coref-in-call.
3. **B.3 (prompt):** install the condensed Selection→Disambiguation→Decomposition system prompt
   + delimited target/neighbor user prompt; one call per chunk (D31).
4. **D33 ledger:** add `claim_extraction_decisions` (append-only, `extractor_version`-stamped) so
   drops + decontextualization deltas are auditable and idempotency keys on the chunk content hash
   + `extractor_version` (D7/D12).

**Tie-back to the decision log:** this advances D4 (cheap-first: one call, not 3N), honors D7
(stored-and-auditable, replay-not-recompute for the LLM rung), honors D12 (idempotent per-doc
chain, content-hash + version), realizes D19 (coref inside the E2 call, all languages), and
composes cleanly with D25–D30 (E1.5 is unchanged; Selection is the claim-level dual of the
section-level gate, D34). **Gate D31's one-call commitment on the eval-D ablation** — that is the
one place the design must be measured, not asserted, before it is locked. Then propose D31–D34 to
the log and wire the eval harness (D) into the same O6 golden-set program that D22/D30 already
require.
