# Completeness & Coherence Critique — claimify_research (C1–C8 + repo_findings)

**Role.** Adversarial completeness/coherence critic. Default skeptical; every load-bearing claim
below was re-checked against the primary source (paper markdown or ugm design docs) and is cited
where a source exists. VERIFIED = re-read this pass. The eight question docs are **unusually
faithful to source** — I re-checked the Claimify numbers (93.9 / 87.6 / 65.6 at
`paper_text.md:207`; 5.4% / 0.8% discard at `:138`,`:142`; 58.3% yield at `:627`), the naive
single-chunk baseline (a FActScore-shaped extract-everything extractor that performs per-chunk
extraction, a verbatim-substring grounding gate, and a content-derived claim id), and the design
anchors (`overall_design.md:88-110`, `decisions.md` D19 `:384`, D29). They hold. This critique
therefore targets the **residual** gaps, the places where two docs quietly assume opposite things,
and the spots where a recommendation outruns its evidence.

The four pressure-test questions are answered first (they are the brief), then consolidated as
`gaps[] / contradictions[] / overclaims[]` and the top-6 for synthesis.

---

## Pressure-test (a): can ONE structured-output call do Selection + Disambiguation + Decomposition + coref + decontextualization reliably, or are staged calls genuinely needed?

**The corpus is internally split and never resolves it.** C8 §2.1 (D31) commits to **one call per
chunk** with staged *reasoning fields*, explicitly flags it as "the single biggest open question"
(`C8:485-491`), and gates it on an unbuilt eval ablation. C6/C5 lean on the same one-call assumption
to claim "~zero marginal cost" grounding and coref. But **C1 §3 and the repo archaeology supply
three pieces of contrary evidence that the one-call docs do not reckon with**:

1. **Claimify's voting is load-bearing, not decorative.** The paper runs **completions=3,
   min_successes=2** for Selection AND Disambiguation (`paper_text.md:587`), temperature 0.2. These
   are the two stages C8 wants to fuse into one un-voted call. Voting exists precisely because a
   single completion on the verifiability/ambiguity judgment is unstable. C8 acknowledges losing
   voting but treats it as "robustness, mitigated by persisting reasoning" — that is an assertion,
   not a measurement. **Dropping 3×→1× AND staged→fused are TWO independent quality reductions
   stacked in one step; the docs never separate their effects.**

2. **The one impl that already dropped voting did NOT also fuse the stages.** `claimsmcp` runs
   "one structured request per stage, no voting" — i.e. it kept **3 calls** (`claimify_impls.md:156-158`).
   No surveyed implementation runs the fully-collapsed 1-call variant C8 proposes. C8's own
   evidence base contains zero instances of its recommended architecture. This is an **unbuilt
   hypothesis dressed as a refinement of prior art**.

3. **The deliberate decouplings make fusion actively risky.** Selection's prompt hard-codes "it
   does NOT matter whether the proposition contains ambiguous terms… assume the fact-checker can
   resolve all ambiguities" (`paper_text.md:823`, `claimify_impls.md:91`). Disambiguation then DOES
   resolve ambiguity. These are **contradictory instructions to the same model in one call** — stage 1
   says ignore ambiguity, stage 2 says obsess over it. The staged architecture isolates them into
   separate contexts on purpose. C8 hand-waves this as "hold three reasoning modes in one response"
   (`C8:133`) without confronting that two of those modes give opposite instructions about the same
   property. **No doc analyzes the prompt-conflict cost of fusion.**

**Verdict.** The honest answer the corpus *should* state but doesn't: **a single call can plausibly
do coref + decontextualization + Decomposition together** (Graphiti, VeriScore, mem0 all fuse these
in one call at production scale — `graphiti_letta.md:74-99`, `claimify_impls.md:266-278`,
`mem0_cognee.md:42-45`), **but Selection (verifiability) and the ambiguity-discard verdict are the
two pieces with real evidence for separation** — voting protects exactly those two, and the prompt
decoupling exists exactly between those two. The defensible position is a **2-call split: Selection
as its own (optionally voted) call, then a fused Disambiguation+Decomposition+coref+grounding call** —
which C8 itself names as the fallback (`C8:138-139`) but buries. C8's primary recommendation (1 call)
is under-evidenced; its own fallback is the better-evidenced default. **GAP: no doc estimates the
token/latency delta between 1-call and 2-call at fleet scale, so "cost vs quality" is asserted, not
computed** — the brief's exact question is left open.

---

## Pressure-test (b): does dropping the verbatim-quote gate open a hallucination hole? Is span/NLI/self-check grounding sufficient?

**This is the corpus's biggest unforced coherence problem: C6 and C8 propose two DIFFERENT, partly
incompatible replacement gates, and neither is verified safe.**

- **C6** replaces the substring gate with an **in-call entailment self-verdict** (`grounded: bool`),
  demotes the substring check to a soft `span_verbatim` flag, and accepts a claim iff
  `grounded is True` (`C6:240-255`). The gate is the model grading itself.
- **C8** replaces it with **window-membership**: every *added* substring must verbatim-exist in a
  declared in-window source (target/prev/next/prefix), validated deterministically in Python
  (`C8:251-287`). The gate is mechanical string-membership of the *additions*.

These are not the same gate and they catch different failures. **C8's window-membership is
strictly stronger against fabrication** (a hallucinated "in San Francisco" with no window source is
mechanically rejected, `C8:283`) **but requires the model to honestly enumerate every added span
with correct provenance tags** — an instruction-following burden no surveyed system imposes and none
of the docs measure compliance for. **C6's self-verdict is weaker**: the doc itself flags that
"self-grading is known to be optimistic" (`C6:202`,`:288`) and that no ugm entailment number exists
(`C6:195`). C6 then recommends shipping the self-verdict as the *sole gate* anyway, with the audit
deferred to "sampled offline." **A self-graded boolean as the only production faithfulness gate is
precisely the hallucination hole the brief asks about, and C6 half-admits it.**

**The actual hole both miss.** The naive single-chunk baseline's verbatim-substring grounding gate,
whatever its faults, has one property neither replacement preserves: it is **non-circular** — a
deterministic check the model cannot talk its way past. C6's `grounded` is model-self-report
(circular). C8's window-membership only checks the spans the model *chose to declare* in
`added_context`; a model that decontextualizes by adding "the target system" but simply **omits it
from `added_context`** passes C8's gate with an ungrounded addition. **Neither replacement closes
the loop the way the verbatim-substring gate did, and no doc states this regression.** The honest
synthesis position: **keep a deterministic floor** — every claim must still carry at least one
verbatim `source_quote` that IS a substring of the window (not the whole claim, just an anchor),
AND the entailment self-verdict, AND (cheaply) sample-audit with an *independent* judge before
trusting self-grading. C6 gets the schema right (dual field) but the acceptance rule wrong
(self-verdict alone). C8 gets a stronger mechanical gate but trusts the model's self-declared
provenance enumeration completely.

**One more under-stated risk:** Claimify's 99% entailment (`paper_text.md:207`) is measured by an
**independent LLM judge on the question+context+source**, on long-form QA answers — NOT by the
extractor self-grading, and NOT on B2B project-memory chunks. C6 cites the 99% as evidence that
entailment grounding works (`C6:123`) while its own §3 admits the number doesn't transfer to a
*self*-verdict or to ugm's domain (`C6:193-195`). **That is the 99% number doing more rhetorical
work than it earns.** (overclaim, below.)

---

## Pressure-test (c): are claim-level recall safeguards for rare facts sufficient? Do Selection + E1.5 compose without a double-filter recall hole?

**Composition (no double-filter): well-argued and I concur.** C4 §2.4, C4 §4.1, C7 §5, and C8 §2.1
(D34) all establish that E1.5 is **chunk/section-grain salience** and Selection is **proposition-grain
verifiability** — orthogonal axes, different units, sequential not overlapping (E1.5 decides whether
E2 runs; Selection runs inside E2). The "a FULL section cannot be fully drained because Selection
drops propositions not sections" argument (`C4:97`) is correct and the strongest single composition
claim in the corpus. **No double-filter hole on the same axis.** VERIFIED against `decisions.md` D25
(E1.5 withholds the E2/E3 layer) and `overall_design.md:96-98`.

**BUT the recall safeguards are NOT sufficient as written, and C4 is the only doc that even
half-sees it.** Three problems:

1. **The recall hole is SEQUENTIAL, not parallel — multiplied false-negatives.** C4 frames the two
   gates as "multiplicative on *different* noise, not double-filtering on the *same* noise"
   (`C4:68`) — true for precision, but **for a rare/uniquely-attested fact the two false-negative
   rates COMPOUND**: P(fact survives) = P(E1.5 routes its section to FULL) × P(Selection keeps it).
   E1.5's `DEFERRED` (D29 defer-don't-DROP) is recoverable, so its miss is soft. But **Selection's
   DROP is a hard delete with no backstop** unless the audit ledger catches it. A rare fact in a
   low-salience section that E1.5 DEFERS, then later promotes, then Selection DROPS as
   "opinion-phrased," is **gone**. The corpus treats E1.5's defer-don't-DROP as the recall backstop
   but **Selection has no equivalent defer state** — its only safeguard is the append-only audit
   ledger + canary CI (`C4:126`, `C8:411`). That is detection-after-the-fact, not prevention.

2. **The measured Selection recall number is alarming and under-weighted.** Selection's
   verifiable-element **recall is 87.6%** and unverifiable-element **precision is only 65.6%**
   (`paper_text.md:207`, VERIFIED). C4 surfaces this honestly (`C4:77`,`:125`) — ~12.4% of
   verifiable elements are missed at element grain. **For a uniquely-attested rare fact, a 12.4%
   per-fact drop rate is enormous** and the relation-layer `evidence_count` backstop (D2) **does not
   help** because by definition a unique fact has no second attestation. C4 names this exactly
   (`C4:126` "a uniquely-attested fact dropped is gone") but then still recommends Selection as the
   "highest-value single change" without quantifying the recall cost against the precision gain.
   **C3, C7, C8 all cite the 83.7→54.4 ablation as the case FOR Selection and NONE of them carry the
   87.6% recall caveat forward** — so a reader of C3/C7/C8 alone would adopt Selection believing it
   is pure upside.

3. **The "never-drop lexical override" list is invented, not measured.** C4 §4.4 proposes hard
   never-drop classes (quantities, dates, named-entity+predicate, change-of-state) as the recall
   floor (`C4:125`). This is a reasonable instinct but it is **C4's own construction with zero
   evidence it bounds the false-drop rate** — Claimify has no such override and still misses 12.4%.
   The override is presented with the same confidence as the verified KEEP/DROP vocabulary, but it is
   a hypothesis. (overclaim, below.)

**Verdict.** Composition is sound; **recall safeguards are NOT sufficient as specified.** The gap:
Selection needs a **defer-equivalent** (a low-confidence "keep but flag" outcome that does not
hard-delete) to match E1.5's defer-don't-DROP, OR the canary set must be large enough to
*statistically* bound the unique-fact drop rate (which requires knowing the rare-fact base rate —
unmeasured). No doc proposes the former; C4 proposes the latter without sizing it.

---

## Pressure-test (d): cost of the richer context bundle (neighbors + prefix) at millions of docs — is prompt-caching enough?

**C5 is the only doc that engages this, and it is honest about the caveats but optimistic on the
bottom line.** Verified mechanics from C5 §2.5: read ≈0.1×, write ≈1.25×, break-even 2 requests,
4096-token Opus cache minimum, silent invalidators. These are correct per the claude-api skill.

**Where prompt-caching is NOT enough, and C5 under-weights it:**

1. **The cache minimum is a real wall for ugm's likely document shape.** C5 flags the 4096-token
   Opus minimum (`C5:196`) but then assumes documents clear it. **Project-memory sources are
   disproportionately SHORT** — the short source classes (chat turns, tool outputs, git memory). A
   3-chunk chat thread's shared document block will almost never reach 4096 tokens, so **the cache
   silently does nothing for the most common source class**, and every chunk pays full price for the
   neighbor window. C5 says this "degrades gracefully to no-cache, still correct" — correct, yes, but
   **the cost model that justifies the richer bundle quietly evaporates for short sources**, which
   may be the majority of ugm's corpus. No doc estimates the short-source fraction.

2. **The neighbor stubs are the UNcached part and they scale with corpus, not document.** The
   per-chunk suffix (chunk + prefix + 2 neighbor stubs) is full-price on every one of the millions
   of chunks (`C5:184`,`:192`). Caching only amortizes the *document-shared* block. So the bundle's
   marginal cost at fleet scale is **2 neighbor-stub reads × every chunk** — and C6/C8's added output
   tokens (`added_context` list, `dropped_spans` ledger, `grounded` verdict, source offsets) are ALSO
   uncached per-claim output. **Output tokens are never cached.** C5 models input caching and is
   silent on the **output-token inflation** that C8's audit-heavy schema (`C8:205-235`) imposes on
   every claim. At millions of docs the audit ledger is a real, uncached, per-claim output cost that
   no doc prices.

3. **Concurrency timing defeats caching exactly where ugm already parallelizes.** C5 §2.5 caveat 3
   notes the cache is cold for N parallel same-document chunks (`C5:206-211`), and the per-chunk
   extraction orchestration in the naive single-chunk baseline runs a thread pool over chunks. C5's
   fix ("warm one chunk, then fan out") adds latency to the per-document task chain (D12) — a real
   cost traded for the cache, not free. C5 calls it "the simpler win is concurrency across documents,"
   but E2 is triggered **per-document** (`overall_design.md:88` "each completion enqueues the next
   stage for that document"), so within-document concurrency is the natural unit and the cache fights
   it.

**Verdict.** Prompt-caching is **sufficient for large documents (PageIndex-heavy runbooks, board
memos) and insufficient/irrelevant for the short-source long tail** that may dominate ugm's volume.
The bundle's cost story is **conditional on document-length distribution, which is unmeasured**. C5
is the most honest doc in the corpus about its own caveats but its §4 recommendation reads as
"caching makes this cheap" when the verified caveats say "caching makes this cheap *for big docs
only*." **GAP: no per-source-class cost model; the dominant short-source case is the unpriced one.**

---

## gaps[]

1. **No 1-call-vs-2-call-vs-3-call cost/quality estimate.** C8 commits to 1-call, names 2-call as
   fallback, but the brief's "cost vs quality" is never quantified — no token count, no latency
   number, no estimated quality delta. The single most consequential architecture decision is
   deferred entirely to an unbuilt eval (`C8:135`,`:460-464`). (pressure-test a)

2. **Selection has no defer/soft-keep state; its hard-DROP has no recall backstop.** E1.5 gets
   defer-don't-DROP (D29); Selection gets only an audit ledger + canaries (detection, not
   prevention). For uniquely-attested rare facts the `evidence_count` backstop (D2) is structurally
   useless. The 87.6% verifiable-element recall (`paper_text.md:207`) is not carried into C3/C7/C8.
   (pressure-test c)

3. **No grounding gate is non-circular AND fabrication-tight.** C6's self-verdict is circular; C8's
   window-membership only checks model-declared additions (omitted additions escape). Neither
   preserves the verbatim-substring gate's one virtue: a deterministic check the model can't bypass.
   No doc proposes keeping a verbatim *anchor* substring as a deterministic floor under the entailment
   verdict. (pressure-test b)

4. **The E1 `context_prefix` it all depends on is an unbuilt artifact.** C5/C8 build the bundle on a
   stored E1 context-prefix, but ugm's E1 chunk model BY DESIGN provides the chunk's content text,
   its section-parent reference and character offsets, the chunk content hash, and entity hints — and
   **no context-prefix field**. C5 §3 flags `e1_chunks_design.md` as "future" and C8 treats the
   prefix as opaque, but **three docs' cost and coref arguments rest on an unbuilt artifact** whose
   length (the cache-minimum question) is therefore unknowable. Partial mitigation only.

5. **Output-token / audit-ledger cost at fleet scale is unpriced.** C8's `added_context`,
   `dropped_spans`, `source_char_start/end`, `grounded`, `grounding_note` are per-claim *output*
   tokens — never cached — and the `claim_extraction_decisions` ledger is append-only per drop. C5
   prices input caching only. (pressure-test d)

6. **Short-source fraction is unmeasured and breaks the cache economics.** The cost justification
   assumes documents clear the 4096-token cache minimum; the short source classes (chat turns, tool
   outputs, git memory) likely don't. No per-source-class cost model. (pressure-test d)

7. **`claim_id` churn under decontextualization is named but not solved.** C3 defect (e) correctly
   shows that the content-derived claim-id function rekeys every claim when decontextualization
   rewrites the claim text — so the *fix* (decontextualize) churns all ids and looks like mass
   duplication to downstream/idempotency. C3 §4.5 punts this to "E3/D2 owns convergence" but the
   **E2-local idempotency key** (C8 D33: chunk content hash + extractor_version) does not address
   that the *claim* id is content-derived. The interaction between decontextualization and identity
   stability is under-designed.

8. **Temporal-context absence is a known Claimify blind spot inherited wholesale.** Both C1 §3 and
   C4 §3 flag that Claimify does NOT mark "the unemployment rate decreased in California" (no date)
   as un-disambiguable (`paper_text.md:310`, VERIFIED). ugm leans on relation-level bi-temporality
   (D3) to absorb this, but **a claim with no time anchor still enters E3 as a weaker claim**, and no
   doc specifies what E2 does when the neighbor window also lacks a date. The gap is acknowledged but
   not closed.

9. **Cross-document coref recall gap is correctly flagged but its size is unknown.** C7 §4 and C8 §2.2
   both note intra-document coref doesn't solve "the CEO" introduced in another document
   (`decisions.md:400-404`). For project memory (threaded chat, cross-referencing docs) this may be a
   *large* recall hole, not an edge case. No doc estimates how often the antecedent is cross-document.

---

## contradictions[]

1. **One-call (C8) vs. voting-matters (C1/repo_findings).** C8 D31 fuses Selection+Disambiguation
   into one un-voted call as the primary recommendation; C1 §1 and `claimify_impls.md:587` document
   that Claimify *votes 3×/min-2 on exactly those two stages* because single completions are
   unstable. C8 acknowledges the loss but recommends against the evidence; the corpus does not
   reconcile "fuse and drop voting" with "voting was added to those specific stages for a reason."

2. **Grounding gate: self-verdict (C6) vs. window-membership (C8).** Two different replacement gates
   for the verbatim-substring grounding gate, presented in parallel docs as "the" fix, never
   cross-referenced. C6:245 accepts on `grounded is True` (model self-report); C8:267-276 accepts on
   deterministic Python membership of declared additions. A synthesis must pick or layer them; as
   written they are competing, not complementary, and C6 even keeps `evidence_quote`→`source_quote`
   while C8 **removes the verbatim evidence-quote field entirely** (`C8:203` "evidence_quote is
   removed") in favor of offsets. **Direct schema contradiction.**

3. **Question/metadata as the "context": C2 says PageIndex section title is an unmeasured substitute
   for the Claimify question and may not transfer (`C2:249-253`); C5/C8 treat the PageIndex header as
   the paper's *sanctioned* "header hierarchy metadata slot" and a near-free win (`C5:118-119`,
   `C8:104`).** Both cite `paper_text.md:112` — but the paper says metadata was **defined and NOT used
   in the experiments** (`paper_text.md:120`, VERIFIED). So C5/C8's "the paper sanctions this" is
   half-true (defined yes, validated no), and C2's caution is the more accurate reading. The corpus
   speaks with two voices on whether the header-as-question substitute is evidence-backed.

4. **Selection recall framing: C4 (recall-cautious, surfaces 87.6%) vs. C3/C7/C8 (Selection = pure
   upside, cite only 83.7→54.4).** Not a hard contradiction but a coherence drift: the same stage is
   "highest-value single change, do it first" in C3/C7/C8 and "recall-risky, bias conservative,
   instrument the false-drop rate" in C4. A reader following C3's prioritized list (`C3:313`) adopts
   Selection without C4's safeguards.

5. **Whether the naive single-chunk baseline "intends" decontextualization. C7 §3.4 claims the
   extracted-claim schema already separates the claim text from the verbatim evidence-quote field so
   "the design intends" decontextualized claims and the bug is just the prompt nudging the model to
   rewrite the quote (`C7:138-141`). C2/C3/C6 argue the opposite — the verbatim-substring grounding
   gate *structurally forbids* decontextualization and the prompt ("exact quote copied from this
   chunk") enforces contextual claims (`C3:42-44`, `C6:19-28`).** VERIFIED: the grounding gate checks
   the verbatim evidence-quote field (not the claim text) as a substring, so C7 is technically right
   that *only the quote* is validated — but in the extract-everything baseline that evidence-quote is
   then **discarded, never stored** (the claim record has no quote field; the per-chunk extraction
   orchestration never persists it). So C7's "minimal fix: just validate the quote" understates the
   problem C6 correctly identifies (the provenance is thrown away). The two docs disagree on whether
   the baseline design is salvageable-as-is or structurally broken.

---

## overclaims[]

1. **"~zero marginal cost" for the in-call entailment self-verdict (C6:59,176) and in-call coref
   (C5:165, C8:401).** Zero *call* cost, yes; but every per-claim audit field is uncached *output*
   tokens, and a self-verdict the doc itself calls "optimistic" (`C6:202`) has a quality cost that is
   not zero. "Zero marginal cost" conflates call-count with total cost and ignores output-token and
   accuracy costs. (See gap 5.)

2. **The 99% entailment number as evidence the grounding approach is safe (C6:123, C8:455).** The
   99% is an *independent judge* on *long-form QA*; C6/C8 invoke it to justify a *self-verdict* on
   *B2B project memory*. C6 §3 admits the non-transfer (`C6:193-195`) then C6 §4 uses the number
   anyway. The number is real; its applicability to the proposed design is overclaimed.

3. **"The data to build the excerpt already exists; it is simply not passed today" (C1:341, echoed
   C3/C5/C8).** TRUE for neighbor chunks (the chunk's character offsets and section-parent reference
   are properties ugm's E1 chunk model provides by design). FALSE for the **context prefix** half of
   the bundle — there is no context-prefix field in the E1 chunk model. The recurring "everything we
   need already exists" framing is ~half right; the cheaper-and-richer half (the prefix) is unbuilt.
   (See gap 4.)

4. **The never-drop lexical override list bounds recall (C4:125).** Presented with the authority of
   the verified KEEP/DROP vocabulary, but it is C4's own invention, has no evidence it reduces the
   measured 12.4% miss, and Claimify (which lacks it) still misses 12.4%. A hypothesis stated as a
   safeguard. (See pressure-test c, point 3.)

5. **"Selection is the single highest-value change" generalizes the ablation beyond its domain
   (C3/C4/C7/C8, from `paper_text.md:257`).** The 83.7→54.4 element-coverage drop is measured on
   **BingCheck long-form QA answers** (`paper_text.md:202`), a dense-claim encyclopedic distribution.
   ugm's project memory (chat, tool output, threaded internal docs) has a *different* verifiable-vs-
   opinion ratio. The ablation proves Selection matters *on that corpus*; "highest-value for ugm" is
   an extrapolation. Only C2 §3 flags the distribution-transfer caveat at all (`C2:238-245`); the
   Selection docs assert the transfer.

6. **C8's window-membership gate "provides the same grounding guarantee… at added-span granularity"
   (C8:283-284).** It does NOT — it only checks the spans the model chose to *declare* in
   `added_context`. An undeclared added span (model decontextualizes but omits the audit entry)
   passes. The guarantee is conditional on perfect model self-reporting of its own additions, which
   is unmeasured and almost certainly < 100%. Stated as equivalent to the old deterministic guarantee;
   it is strictly weaker on undeclared additions. (See pressure-test b.)

---

## top-6 for synthesis

1. **Resolve the call-architecture split with the better-evidenced default: 2 calls, not 1.** Make
   Selection (verifiability + ambiguity-discard) its own call — the two stages voting protects and
   the two with conflicting prompt instructions — and fuse Disambiguation+Decomposition+coref+
   grounding into a second call. This is C8's own buried fallback (`C8:138-139`), is the *only*
   architecture with implementation precedent (`claimsmcp` 3-call, no surveyed 1-call), and dodges
   the un-analyzed prompt-conflict of fusing "ignore ambiguity" with "resolve ambiguity." Gate the
   1-call collapse on an ablation *before* committing, not after. (pressure-test a; gap 1; contra 1)

2. **Layer the two grounding gates instead of choosing: deterministic anchor + declared-addition
   membership + sampled independent entailment audit.** Require (i) at least one verbatim
   `source_quote` that IS a substring of the window (deterministic floor, the salvaged virtue of the
   naive baseline's verbatim-substring gate), (ii) C8's window-membership check on declared additions
   (mechanical anti-fabrication), (iii) C6's in-call `grounded` self-verdict as a soft signal, (iv)
   an *independent* judge on a sampled stream (never per-claim) before trusting (iii). This closes the
   undeclared-addition hole (gap 3, overclaim 6) and the circularity hole (pressure-test b) that
   neither C6 nor C8 closes alone. Reconcile the C6/C8 schema contradiction (keep `source_quote` AND
   offsets). (contra 2)

3. **Give Selection a defer-equivalent; do not let it hard-delete.** Mirror D29 one grain down: add a
   low-confidence "keep-flagged" Selection outcome that writes the claim but marks it for re-review,
   so a rare/uniquely-attested fact is never silently deleted at proposition grain. The audit ledger
   + canaries (C4/C8) are detection; this is prevention. Size the canary set against an *estimated
   rare-fact base rate* (currently unmeasured). Carry the **87.6% verifiable-element recall** caveat
   (`paper_text.md:207`) into the Selection decision everywhere, not just C4. (pressure-test c; gap 2;
   overclaim 4; contra 4)

4. **Price the bundle per source-class, not in aggregate; the short-source tail breaks caching.**
   Before committing the richer bundle, measure the short-source fraction (chat turns, tool outputs,
   git memory) and the document-length distribution against the 4096-token Opus cache minimum. For
   short sources caching does nothing and the neighbor window is full-price on every chunk; for those,
   consider a cheaper bundle (section path only, no neighbor stubs). Add the uncached *output-token*
   cost of the audit schema (gap 5) to the model. (pressure-test d; gaps 5,6)

5. **Make the E1 `context_prefix` a hard prerequisite with a committed length budget, or design E2
   to run without it.** Three docs' cost and coref arguments depend on a context-prefix field the E1
   chunk model does not provide by design. Either land `e1_chunks_design.md` with a pinned prefix
   length (which decides the cache-minimum question) before building the bundle, or specify the E2
   fallback when the prefix is absent (neighbors + PageIndex path only). Stop asserting "the data
   already exists" for the prefix half. (gap 4; overclaim 3)

6. **Close the decontextualization↔identity↔temporal loop that no single doc owns.** (a) Decide
   whether `claim_id` stays content-derived (then decontextualization churns every id — accept and
   version via `extractor_version`, or move identity to a stable key). (b) Specify E2 behavior when
   neither the chunk nor the window dates a temporal claim (`paper_text.md:310` blind spot inherited).
   (c) Estimate the cross-document-coref recall hole for threaded project memory — it may be large,
   not marginal. These three are each flagged in isolation (C3 e, C1/C4 temporal, C7/C8 cross-doc) but
   no doc treats them as the connected E2→E3 correctness surface they are. (gaps 7,8,9)

---

## Note on corpus quality

The eight docs are **evidence-disciplined and accurate** where they cite the paper and the design
anchors — I re-verified the headline numbers (Table at `paper_text.md:207`, discard rates
`:138`/`:142`, yield `:627`), the anti-pattern defects of the naive single-chunk baseline (the
verbatim-substring grounding gate, the content-derived claim id, the single-chunk extraction unit),
and the design anchors (D19 `:384`, D29, `overall_design.md:88-110`), and they hold. The
weaknesses are **not fabrication** — they are (1) two parallel docs proposing incompatible fixes
without cross-reference (C6 vs C8 grounding), (2) a real measured recall risk (87.6%) that travels in
C4 but not C3/C7/C8, (3) single-domain benchmark numbers extrapolated to ugm's different distribution,
and (4) a cost story conditional on an unmeasured document-length distribution and an unbuilt
`context_prefix`. The synthesis task is primarily **reconciliation and quantification**, not
correction.
