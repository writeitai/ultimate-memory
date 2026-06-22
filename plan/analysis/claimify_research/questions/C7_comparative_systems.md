# C7 — Comparative: context window, decontextualization, claim-level selection, grounding

**Question.** Across mem0, graphiti, cognee, graphrag, lightrag, hipporag, letta (+ the
Claimify / VeriScore / FActScore / SAFE references): for each — (1) what **context window**
the extractor sees, (2) whether it **decontextualizes** (coref / time / entities), (3) whether
it does **claim/fact-level selection** (relevance/verifiability filtering), (4) how it
**grounds** claims. Who does context-aware decontextualized extraction best, and what should
ugm borrow?

Sources: the four archaeology files in `../repo_findings/` (each VERIFIED at file:line against
the checked-out source), the Claimify paper markdown
(`_additional_context/claimify_deshwalmahesh/paper_text.md`), and the **naive single-chunk
baseline** — the extract-everything anti-pattern that ugm's E2 must avoid. Citations below are
reproduced from those VERIFIED findings; I did not re-open every upstream file, so a few are
tagged **[per repo_findings]** = trust-the-archaeology rather than re-verified here.

---

## 1. Key findings

- **Two clean families.** *Extract-everything per chunk, no surrounding context*: cognee,
  GraphRAG, LightRAG, HippoRAG (and FActScore). *Context-aware extraction with selection +
  decontextualization*: Claimify, VeriScore, mem0 (live fork), graphiti, letta. The first
  family is exactly the gap ugm's E1 context-prefix + E1.5 value gate + E2 Claimify+coref are
  designed to close — the archaeology confirms **none of the graph-RAG systems ship a
  pre-extraction value gate** (`graphrag_lightrag_hipporag.md:300-307`, `e1_5_value_gate_design.md:21-24`).
- **Best context-aware decontextualized extraction = Claimify, then graphiti.** Claimify is
  the only system with an explicit *per-stage* context window (Selection 5+5, Disambiguation/
  Decomposition 5+0), an explicit verifiability **Selection** gate, an explicit decontextual-
  ization stage with a **drop-on-unresolvable-ambiguity** rule, and a forbid-external-knowledge
  faithfulness lever (`claimify_impls.md:21-54`). Graphiti is the best *production* realization:
  it always extracts with surrounding context (current episode + 3–10 prior episodes carrying
  timestamps), resolves pronouns/bare kinship terms to entity names in-call, resolves time via
  `REFERENCE_TIME` + `valid_at`/`invalid_at`, and filters aggressively at node+edge level — all
  **fused into the extraction prompt**, not separate passes (`graphiti_letta.md:17-136`).
- **Two distinct "selection" axes, often conflated.** (a) **Verifiability/opinion filter at
  claim level** — Claimify Selection, VeriScore (drops stories/opinions/advice/hypotheticals),
  graphiti (drops feelings/generic nouns/vague single-entity states), mem0 (drops phatic
  chit-chat). (b) **Relevance-to-a-query filter** — SAFE (post-hoc relevance gate), GraphRAG's
  off-by-default claim/covariate extractor (topic-gated by `claim_description`). ugm's E1.5 is a
  *third, earlier* axis — a **chunk/section-level value gate before extraction** — which **no
  surveyed system has** (`graphrag_lightrag_hipporag.md:186-188`, `claimify_impls.md:385-393`).
- **The naive single-chunk baseline sits in the WEAKEST family and embodies a grounding
  anti-pattern that blocks decontextualization.** It sees one bare chunk, no neighbors, no
  document, no question; orchestration is strictly one-chunk-at-a-time. It carries **no
  decontextualization instruction** and **no claim-level selection** beyond "atomic + supported
  by an exact quote." Worst: its verbatim-substring grounding gate requires the verbatim
  evidence-quote field to be a **verbatim normalized substring of the chunk** — so the moment the
  model resolves a pronoun in the quote it is rejected. Coref (D19) and a naive verbatim
  grounding check are **mutually exclusive as written**, which is precisely the failure mode E2
  must design around.

---

## 2. Comparative table

**(1) Context window** = what text the extraction LLM literally sees. **(2) Decontextualize** =
resolves coref / time / entity names so a claim stands alone. **(3) Claim/fact-level selection**
= drops opinions/boilerplate/unverifiable/irrelevant *content* (not just malformed structure).
**(4) Grounding** = how a claim is tied to the source.

| System | (1) Context window at extraction | (2) Decontextualizes? | (3) Claim/fact-level selection? | (4) Grounding |
|---|---|---|---|---|
| **Claimify** (paper / deshwalmahesh) | Target sentence **+ question + excerpt**: Selection 5 prec/5 foll, Disamb/Decomp 5 prec/0 foll, with `[...]` markers; target passed separately (`claimify_impls.md:21-35,62-78`) | **YES, strongest** — dedicated Disambiguation stage: partial names, undefined acronyms, referential + structural + temporal ambiguity; **drops** sentence if "readers fail to reach consensus" (`claimify_impls.md:44-50,99-110`) | **YES, strongest** — dedicated Selection stage: per-sentence verifiability gate, drops non-verifiable sentences AND **strips** unverifiable spans from mixed sentences (`claimify_impls.md:38-43,80-98`) | Forbid external knowledge ("Do NOT use any external knowledge beyond the question, context, and sentence"); `[...]` essential-context brackets; 3-way voting (`claimify_impls.md:51-54,105-110`) |
| **VeriScore** | Focus sentence `<SOS>..<EOS>` + ~3 prec / 1 foll (+ lead sentence for long paras) (+ question for QA) (`claimify_impls.md:259-265`) | **YES**, inline — pronouns→names, definite phrases→names, situate in time+location, single prompt (`claimify_impls.md:274-278`) | **YES**, verifiable-only **fused** into the decompose call — drops stories/opinions/advice/hypotheticals; emits "No verifiable claim" (`claimify_impls.md:266-273`) | Verbatim quotes w/ source; "do not extract claims from the question"; verifiable against external world knowledge (`claimify_impls.md:279-281`) |
| **FActScore** | **ONE sentence, NO neighbors/doc** — just fixed demos + 1 BM25 demo (`claimify_impls.md:287-294`) | **NO** — no context to resolve from; demos show pre-resolved coref only (`claimify_impls.md:302-303`) | **NO** — "breakdown into independent facts" = decompose everything; only boilerplate-line skipping (`claimify_impls.md:295-301`) | Defers veracity to downstream retrieval; no extraction-time grounding (`claimify_impls.md:300-301`) |
| **SAFE** | Split = 1 sentence (FActScore). Decontextualize/revise = **ENTIRE RESPONSE** as context (widest) (`claimify_impls.md:313-323`) | **YES, but over-reaching** — revises vague refs against the *whole* response; "MUST NOT change/add factual claims" guard; paper flags over-reach (`claimify_impls.md:315-323`) | **Relevance** filter (not verifiability), **post-hoc** — drops facts whose subject is unrelated to the question; defaults to "relevant" on parse failure (`claimify_impls.md:324-331`) | Faithfulness guard in revise prompt; relevance vs question; no ambiguity-discard (`claimify_impls.md:318-331`) |
| **Molecular Facts** | Stage1: claim **alone** + **world knowledge** (homonym enumeration); Stage2: claim + **full passage** (`claimify_impls.md:340-358`) | **YES** — injects the one distinguishing detail (occupation/location/lifespan) to make a fact "molecular"; **uses external world knowledge** (departs from Claimify) (`claimify_impls.md:344-353`) | **NO** — transforms every input fact; assumes upstream already filtered (`claimify_impls.md:353-354`) | "Should not omit info / only minimally modify"; grounds detail in passage but seeds disambiguation from world knowledge (`claimify_impls.md:352-353,379-380`) |
| **mem0** (live V3 fork) | **Rich**: new turn(s) + **last 10 messages** (coref) + **top-10 retrieved memories** (dedup/link); single call (`mem0_cognee.md:25-33`) | **YES** — "Replace all pronouns with specific names or 'User'"; relative→absolute time vs an Observation-Date anchor (machinery present but unfed on default add) (`mem0_cognee.md:42-45`) | **YES, inclusion-biased** — drops only **purely phatic** chit-chat; deliberately KEEPS casual personal facts; "when in doubt, extract" (`mem0_cognee.md:35-40`) | "No Fabrication … if you can't point to where it came from, don't include it"; "No Detail Contamination from Context"; preserve proper nouns/numbers (`mem0_cognee.md:45`) |
| **mem0** (classic, design ref) | Extractor sees current batch only (system stripped); separate UPDATE call sees facts + retrieved memories (`mem0_cognee.md:47-50`) | Partial — fact-extraction normalizes; ADD/UPDATE/DELETE/NONE handles novelty (`mem0_cognee.md:48-50`) | **YES** — `FACT_RETRIEVAL_PROMPT` is the canonical chit-chat dropper ("Hi." → `{facts:[]}`) (`mem0_cognee.md:49`) | Two-call: extract then 4-op novelty controller (`mem0_cognee.md:50`) |
| **cognee** | **ONE chunk, ZERO surrounding context** — user msg = exactly `chunk.text` (`mem0_cognee.md:56-63`) | **In-chunk only** — "use the most complete identifier"; cannot resolve a pronoun introduced in a neighbor chunk (`mem0_cognee.md:71-72`) | **NO** — default "extract all entities + relationships", no value/salience/chit-chat gate; cascade only prunes malformed/redundant *triples* (`mem0_cognee.md:65-69`) | "Do not add outside knowledge" + structured schema; no source-span trace (`mem0_cognee.md:74`) |
| **GraphRAG** | **1 text-unit** (`{input_text}`, default 1200 tok, 100 overlap) + entity-type list; gleaning replays same chunk (`graphrag_lightrag_hipporag.md:18-61`) | **Weak/none** — no pronoun/acronym/date rule; cross-chunk identity via name-keyed merge after extraction (`graphrag_lightrag_hipporag.md:81-90`) | **NO** — "identify **all** entities … **all** relationships"; only a type allow-list + structural/orphan filters (`graphrag_lightrag_hipporag.md:63-79`) | "Comprehensive description"; off-by-default claim extractor grounds to verbatim quotes + ISO date + TRUE/FALSE/SUSPECTED (`graphrag_lightrag_hipporag.md:92-107`) |
| **LightRAG** | **1 chunk + its OWN section breadcrumb** (h1→h2→h3, ≤256 tok, "background only, untrusted") (`graphrag_lightrag_hipporag.md:113-155`) | **YES, in-chunk** — third person, **pronoun ban**, consistent naming; no date rule; no cross-chunk coref (`graphrag_lightrag_hipporag.md:190-200`) | **NO** chunk value gate — "meaningful"/"high-value"/"most significant" nudges + per-response volume caps; structural filters only (`graphrag_lightrag_hipporag.md:168-188`) | "based **solely** on the input text"; cross-chunk consolidation = downstream name-merge + LLM re-summary (`graphrag_lightrag_hipporag.md:202-213`) |
| **HippoRAG** | **1 passage (= whole input doc; no internal chunker)**, seen twice (NER, then NER-conditioned RE) (`graphrag_lightrag_hipporag.md:219-246`) | **In-passage coref only** — "Clearly resolve pronouns to their specific names"; no acronym/date rule (`graphrag_lightrag_hipporag.md:270-277`) | **NO** — only "≥1 named entity per triple"; post-hoc keeps exactly-3-element unique triples; "do not preprocess" (`graphrag_lightrag_hipporag.md:248-268`) | NER-conditioning is the grounding mechanism; no entailment/verify step (`graphrag_lightrag_hipporag.md:279-288`) |
| **graphiti** | **Current episode + 3–10 prior episodes** (with timestamps) as `<PREVIOUS_MESSAGES>`, used for coref/continuity only; can pack multiple episodes into `<CURRENT_MESSAGE>` (`graphiti_letta.md:17-72`) | **YES, in-call** — pronouns→entity names, qualify bare kinship terms ("Nisha's dad"), keep specifics; `valid_at`/`invalid_at` + `REFERENCE_TIME`, no-hallucinate-dates, contradiction→invalidate (`graphiti_letta.md:74-99`) | **YES, aggressive, fused** — node-level drops pronouns/feelings/generic nouns ("Wikipedia-article test"); edge-level drops vague single-entity states; attributes "only explicitly stated" (`graphiti_letta.md:101-124`) | Every concrete noun/number survives into `fact` (paraphrase, no verbatim quote); endpoint-in-ENTITIES validation rejects hallucinated subjects/objects; "only explicitly stated" (`graphiti_letta.md:126-136`) |
| **letta** | **Full recent transcript** (prior + recent msgs) + existing memory blocks, line-indexed Older/Newer (`graphiti_letta.md:148-168`) | **Agent's job** — "use specific dates, not 'today'/'recently'"; permits *light inference*; no structured coref/temporal fields (`graphiti_letta.md:170-181`) | **SOFT** — "not every observation warrants a memory edit … aim for high recall"; archival = compress-by-topic, not drop-vs-keep (`graphiti_letta.md:183-207`) | Prompt-instructed only ("do not invent unsupported details"); no validation/verification step found (`graphiti_letta.md:209-215`) |
| **Naive single-chunk baseline** (the anti-pattern E2 must avoid) | **1 bare chunk, no neighbors/doc/question**; one-chunk-at-a-time orchestration | **NONE** — system prompt has no coref/time/entity instruction | **NONE** — "extract all atomic claims … directly supported by an exact quote"; no opinion/boilerplate/verifiability filter | **Verbatim-substring** check: the evidence-quote must be a normalized substring of the chunk text — strong grounding but **blocks** any rewritten/decontextualized quote |

---

## 3. Who does it best, and the borrowable mechanisms

**Claimify is the design reference; graphiti is the production reference.** They are
complementary:

- **Claimify** gives the *decomposed pipeline*: a bounded **p preceding / f following** sentence
  window per stage (`paper_text.md:112,582-583`, mirrored `claimify_impls.md:21-35`); a
  **verifiability Selection** stage that both drops and *trims* (`claimify_impls.md:80-98`); a
  **decontextualization** stage with the **consensus drop rule** ("Cannot be decontextualized")
  (`claimify_impls.md:99-110`); a **forbid-external-knowledge** faithfulness lever; and
  **voting** for stability. Of the three ports, **claimeai** matches the paper's exact per-stage
  windows (5/5 → 5/0) and adds a final complete-declarative-sentence validation stage
  (`claimify_impls.md:186-247`); **deshwalmahesh** is the closest line-by-line transcription of
  the prompts (`claimify_impls.md:57-126`).
- **Graphiti** proves the *single-call contextual* variant at production scale: surrounding
  context is **always present** (prior episodes + timestamps) but **scoped to disambiguation**
  ("extract facts from the CURRENT MESSAGE … use PREVIOUS MESSAGES only to disambiguate",
  `graphiti_letta.md:50-58`); coref + temporal resolution + selection are **fused into the one
  extraction call** (matches D19 "coref-in-call"); grounding is by **endpoint-in-ENTITIES
  validation** rather than verbatim quoting (`graphiti_letta.md:126-136`).
- **mem0 (live fork)** is the closest analog to ugm's intended runtime: one call that sees the
  new content + recent history (coref) + retrieved memories (dedup), with an *inclusion-biased*
  selection gate that keeps casual personal facts (`mem0_cognee.md:25-45`) — a useful counter to
  Claimify's aggressive verifiability filter when the corpus is conversational rather than
  encyclopedic.

**Borrow list (concrete):**

1. **Context window (E1 prefix / D19, fixes the bare-chunk anti-pattern).** Adopt
   Claimify's bounded **p preceding / f following** framing, *or* graphiti's prior-context block.
   ugm's E1 chunk model provides, by design, the chunk's section-parent reference and character
   offsets, so neighbors are cheap to fetch deterministically. Pass the target chunk
   **separately** from the context block (Claimify's "Excerpt:" + "Sentence:" split,
   `claimify_impls.md:74-78`) and label the context **"background for disambiguation only — do
   not extract from it"** (graphiti `extract_edges.py:132-139` per `graphiti_letta.md:50-58`;
   LightRAG's untrusted-breadcrumb framing `graphrag_lightrag_hipporag.md:144-152`). This
   directly closes the gap that `e1_5_value_gate_design.md:21-24` and `overall_design.md:94`
   name.
2. **Decontextualize in-call (D19).** Add graphiti/LightRAG/VeriScore-style instructions:
   pronouns→entity names, qualify bare relational terms, third person, **no external knowledge**
   (Claimify `claimify_impls.md:105-106`) — *except* the deliberate Molecular-Facts carve-out if
   homonym disambiguation is ever needed (`claimify_impls.md:344-353`), which ugm should NOT adopt
   by default (it breaks faithfulness). Resolve relative→absolute time against an explicit
   document/observation date (graphiti `REFERENCE_TIME`, mem0 Observation-Date,
   `graphiti_letta.md:87-99`, `mem0_cognee.md:42-45`).
3. **Claim-level selection — but keep it OFF the E1.5 path.** Claimify's Selection (verifiability
   drop + span-trim, `claimify_impls.md:80-98`) and graphiti's node/edge selection
   (`graphiti_letta.md:101-124`) are **E2 claim-level** filters and are distinct from ugm's
   **E1.5 chunk/section value gate** (D25). The archaeology confirms the value gate is unbuilt
   prior art (`graphrag_lightrag_hipporag.md:186-188`, `e1_5_value_gate_design.md:21-24`), so keep
   the two layers separate: E1.5 = *should we pay for E2 on this section* (cheap cascade, D26);
   E2-internal selection = *which spans in this chunk are verifiable claims*. Borrow Claimify's
   verifiability rubric into the **E2 prompt**, not the gate.
4. **Grounding that survives decontextualization (the design contract).** A naive verbatim-substring
   grounding gate is incompatible with coref (D19) and with any rewrite. Move to graphiti's
   contract — **the source span need not appear verbatim in the claim; instead validate that the
   claim's entities/quantities are present in the (chunk + context) span** — *or* keep a verbatim
   evidence-quote field that points at the **original** chunk text while letting the
   decontextualized claim text diverge (i.e. validate the quote, not the rewritten claim). The
   extracted-claim schema should separate the claim text from the verbatim evidence-quote field,
   so the minimal design is: **decontextualize the claim text, keep the evidence-quote verbatim
   from the chunk, and validate only the evidence-quote** (which is the right intent — the
   failure mode is a prompt that silently nudges the model to rewrite the quote too). Add a
   verifiability Selection step before persisting, and (Claimify) **voting** for stability on the
   residue.
5. **Drop-on-unresolvable-ambiguity (Claimify only).** Adopt the "Cannot be decontextualized →
   drop" rule (`claimify_impls.md:107-109`) for E2: a dangling-pronoun claim is worse than a
   missing one. This is the recall-conservative bias D29 already mandates for E1.5, applied one
   layer down at the claim level.

---

## 4. Confidence & gaps

- **Confidence: HIGH** on the comparative shape and on every cell sourced to a VERIFIED
  file:line in the four archaeology files (the heavy lifting was done there with adversarial
  flags). HIGH on the baseline-extractor diagnosis — the naive single-chunk anti-pattern (bare
  chunk in, one-chunk-at-a-time, verbatim-substring grounding gate) is a well-understood
  FActScore-shaped extractor whose failure modes are characterized directly here.
- **Could not verify (flagged):** I did **not** re-open the upstream repos this turn; cells
  tagged `[per repo_findings]` (none load-bearing) and all upstream file:line citations are
  trusted from the archaeology, which itself flagged its own INFERENCE/COULD-NOT-VERIFY items
  (e.g. mem0's Observation-Date/summary inputs being *wired-but-unfed* on the default add path,
  `mem0_cognee.md:31,44`; graphiti being a modified fork, `graphiti_letta.md:6`). No benchmark
  numbers are asserted anywhere — none were measured.
- **Open design question (not answerable from these repos):** the *exact* p/f window and whether
  ugm should use Claimify's sentence-level decomposition or graphiti's whole-chunk single-call
  extraction. The repos show both work; the choice is a ugm spike (cost vs. atomicity), and the
  E1.5 cost/break-even spike (`e1_5_value_gate_design.md:167-185`) is the gating one.
- **Cross-document coref** (e.g. "the CEO" introduced in another document) is solved by **none**
  of these systems and explicitly remains an open ugm recall gap (D19 consequences,
  `decisions.md:400-404`) — do not assume the borrow list closes it.

---

## 5. Recommendation for ugm (tied to decisions + the E2 design contract)

- **D19 / E1.5 / overall_design E1-E2** — implement the context window first. The single highest-
  value change is to stop extracting from a **bare chunk** (the naive single-chunk baseline's
  defining weakness). Fetch deterministic neighbors via the chunk's section-parent reference and
  character offsets that ugm's E1 chunk model provides by design, pass them as a
  **disambiguation-only background block** (graphiti/LightRAG framing), and add coref + temporal +
  entity-name instructions to the E2 prompt (D19: coref-in-call, no separate model). This is the
  literal realization of `overall_design.md:94,101-102`.
- **The grounding anti-pattern is the blocker for D19 and must be designed out from the start.**
  A verbatim-substring grounding gate rejects any decontextualized quote. Design: **decontextualize
  the claim text, keep the evidence-quote a verbatim span of the chunk, validate only the
  evidence-quote** — and write the E2 system prompt to say so explicitly (a naive prompt saying
  "supported by an exact quote copied from this chunk" is reasonably applied by the model to the
  *whole* claim, re-introducing the bug). State the invariant in the ugm E2 design: *claims are
  decontextualized; quotes are verbatim; only the quote is substring-validated.*
- **D4 / cheap-first** — selection stays a cascade, but at the right layer: E1.5 chunk value gate
  (D25-D30, cheap classifier, `e1_5_value_gate_design.md`) decides *whether to run E2*; Claimify-
  style **verifiability Selection** lives *inside* E2 deciding *which spans are claims*. Keep them
  separate (the archaeology proves no one fuses them, and they answer different questions).
- **D7 / rebuildable** — keep grounding deterministic and re-derivable from E0/E1: a verbatim
  evidence-quote + recorded character offsets means a rebuild can re-verify provenance
  without the LLM, preserving D7 even though the decontextualized claim text itself is LLM
  output (consistent with D1's "L3–L5 not reproducible from Postgres, but provenance is").
- **D12 / per-doc triggers** — the neighbor-context fetch is per-document and local (E1→E2 on the
  Cloud Tasks chain), so it does not change the trigger model; it just enriches the existing E2
  call. No new aggregate dependency is introduced.
- **D25-D30 / value gate** — do **not** let the E2 borrow list bleed into the gate. The gate is
  the *unbuilt* differentiator (`e1_5_value_gate_design.md:21-24`); claim-level verifiability
  selection is the *well-trodden* Claimify/graphiti mechanism. Borrow the latter into E2; build
  the former as designed. Apply Claimify's **drop-on-unresolvable-ambiguity** at the claim level
  as the E2 analog of D29's recall-conservative defer-don't-extract-garbage bias.
