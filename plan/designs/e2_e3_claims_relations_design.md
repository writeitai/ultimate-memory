# E2 / E3 — Claim Extraction and Relation Normalization (Design)

How the system turns a chunk of source text into **claims** (atomic, standalone, verifiable
assertions) and then into **relations** (the distinct facts those claims are evidence for). This is
the cost center and the quality bottleneck of plane E, so the design is opinionated about *what* to
extract and *how* to keep it faithful. Decisions: **D31–D35** (this layer), building on D2, D4, D7,
D12, D17–D19. Full research + evidence: `plan/analysis/claimify_research/SYNTHESIS.md`.

## 1. Where this sits

```
E0 ─────────► E1 ──────────► E2 ───────────────► E3
files         chunks         claims              relations
(Markdown,    (semchunk +    (Claimify-staged:   ( (subject,predicate,object) facts;
 PageIndex     a context      Selection →         entity resolution T0–T4;
 hierarchy +   prefix per     decontextualize →   supersession; evidence_count )
 summaries)    chunk; embed)  decompose; coref
                              in-call)
```

Every document that survives chunking goes all the way through — **there is no pre-extraction "value
gate"** deciding what is worth processing (§4 explains why). E0 and E1 are covered elsewhere; this
document is E2 and E3.

## 2. The problem E2 has to solve

A claim is only useful if a reader (human or agent) can understand it **without going back to the
source**, and only trustworthy if it is **actually supported** by that source. The obvious approach —
"show the model one chunk, ask it to extract every fact, and require each fact to be a verbatim quote"
— fails both tests at once. Take a chunk that reads:

> *"It launched last year in three markets. The team considers it a runaway success."*

- **Understandability fails.** In isolation the model cannot know what *It* is or when *last year*
  was, so it emits `"It launched last year in three markets"` — a claim no downstream step can use
  (you can't resolve an entity called "It" or a date called "last year").
- **Faithfulness is mis-aimed.** A *verbatim-quote* requirement rewards copying surface text, which is
  the opposite of making a claim standalone — and it has no opinion about whether `"The team considers
  it a runaway success"` (an opinion, not a checkable fact) should be a claim at all.

E2 fixes both by giving the extractor **context** and a **three-stage job** (D31), and by replacing
verbatim-quoting with **provenance + entailment** grounding (D32).

## 3. E2 — claim extraction

### 3.1 What the extraction call sees (the context bundle)

The extractor never sees a bare chunk. For each target chunk it receives a small, ordered bundle
(D31):

| Element | Why it earns its tokens |
|---|---|
| **Document header** — title, date, source, language | resolves "this report", "the company", and absolute time for "last year" |
| **PageIndex section path + summary** | tells the model it is inside *Results* vs *References*; makes intro/conclusion and list-item-without-preamble decidable |
| **The chunk's E1 context prefix** | the compact "where this sits" sentence E1 already wrote |
| **±1 (then ±2) neighbour chunks**, same section | the antecedents for pronouns / partial names — fetched for free from the chunk's section-parent + offsets, **same scope only** |
| **Known entity hints** | canonical names already on the chunk, as *hints* (permission to resolve, not to invent) |

Cost is controlled by sharing one cached per-document prefix across that document's chunks. (Open
question: very short sources — chat turns, tool output — don't reach the prompt-cache minimum; see §7.)

### 3.2 The three jobs, in one call's reasoning

Over that bundle the model does three things, in order (the "Claimify" shape). Each is a distinct
*decision*, not just a rewrite, and each is recorded:

1. **Selection — is this even a claim?** Keep statements that make a **specific, verifiable**
   proposition (a state, event, decision, quantity, policy, relationship). **Drop** opinions, advice,
   hypotheticals/speculation ("could lead to…"), generic truisms, questions, section intros/
   conclusions, and "we don't know X" statements. If a sentence mixes the two, **keep only the
   verifiable part**. In the example: `"launched last year in three markets"` is kept; `"considers it
   a runaway success"` is dropped as opinion. *(This stage is the single biggest quality lever — in the
   source research, removing it was the largest quality drop of any component.)*

2. **Decontextualization — make it stand alone.** Resolve every pronoun, partial name, acronym, and
   relative date **using the bundle, never outside knowledge**, and add the **minimum** context needed
   — over-stuffing both bloats the claim and risks asserting something the source didn't. Coreference
   is handled right here, in the same call (D19): no claim leaves E2 with a dangling pronoun. The
   discipline that makes this safe: **if a careful reader could not pick one interpretation from the
   bundle, drop the candidate** rather than guess. In the example, the neighbours name *Project Atlas*
   and the header dates the document to 2024, so "It launched last year" becomes "Project Atlas
   launched in 2024."

3. **Decomposition — split into atoms.** Break the disambiguated sentence into the simplest standalone
   claims, preserving attribution ("*X said* Y" stays attributed, it does not become a bare "Y"). The
   example yields two: `"Project Atlas launched in 2024."` and `"Project Atlas launched in three
   markets."`

**Two calls, not one (D31).** Selection is run as its own (optionally voted) call, then
decontextualization + decomposition + grounding run as a second fused call. Selection is split out
because it is the highest-leverage stage and because it carries the opposite instruction to
decontextualization ("ignore ambiguity" vs "resolve ambiguity"), which is cleaner to keep in separate
contexts. Collapsing to a single call is allowed only if an ablation shows it doesn't lose quality —
see §7. Running the literal three-calls-per-sentence form is *not* done; it is pure latency at scale.

### 3.3 Grounding — staying honest while rewriting (D32)

A decontextualized claim is a *rewrite*, so it can no longer be a verbatim substring of the source.
Grounding therefore stores **two things per claim** and accepts via **layered checks**:

- `claim_text` — the standalone assertion (what retrieval, E3, and reasoning use).
- `source_span` + character offsets — the verbatim slice the claim derives from (provenance / audit).
- `added_context[]` — each substring the model *added* during decontextualization, tagged with which
  bundle element it came from (neighbour / header / prefix).

Acceptance layers four checks, cheapest first:

1. **Anchor** (deterministic): the `source_span` must be a real, in-bounds slice of the target chunk —
   a check the model cannot talk its way past.
2. **Window-membership** (deterministic): every *added* substring must verbatim-exist in the bundle
   element it was attributed to. A claim that invents "in San Francisco" with no bundle source is
   rejected.
3. **Entailment self-verdict** (in-call, ~free): the model asserts the chunk + bundle entail the
   claim; includes the rule that "*X said* Y" entails "X said Y", not "Y".
4. **Sampled independent audit** (offline, not per-claim): a separate judge re-checks a sample, because
   self-grading is optimistic; only a borderline band ever escalates to a per-claim judge.

So in the example, `"Project Atlas launched in 2024"` is accepted: its anchor is the verbatim "It
launched last year", and the additions "Project Atlas" (→ neighbour) and "2024" (→ header) both exist
in the bundle. The dropped opinion never reaches grounding.

### 3.4 Nothing is silently lost (D33, D35)

Two safeguards keep aggressive Selection safe:

- **A decision ledger (D33).** Every Selection drop and every decontextualization edit is written to an
  append-only, version-stamped `claim_extraction_decisions` table. A better prompt can later re-examine
  *only the drops*; a rebuild reads stored claims + decisions and never re-calls the model (the LLM
  rungs are replay-from-storage, like any non-deterministic stage — D7); the per-chunk worker is
  idempotent on content-hash + extractor version (D12).
- **A recall envelope (D35).** Selection biases toward KEEP when unsure; **never-drop classes**
  (quantities, dates, named-entity + predicate, change-of-state language) are protected even if phrased
  opinionatedly; a low-confidence `kept_flagged` outcome marks-for-review instead of hard-deleting; and
  planted rare-fact canaries fail CI if Selection drops them. Drop-rates are tuned against **per-fact**
  loss, never a corpus average — a uniquely-attested fact has no second copy to fall back on.

## 4. Why there is no value gate (the non-goal)

It is tempting to put a cheap "is this section even worth extracting?" gate *before* E2. We
deliberately do **not** (D25). The reasoning, in full, lives in the value-gate research
(`plan/analysis/value_gate_research/`); the short version:

- The only rung that actually discriminated *value* was a salience classifier that needs a labelled
  golden set that doesn't exist; the novelty rung was a corpus-scale similarity query — i.e. the gate's
  own worst risk was becoming a new expensive stage.
- The honest cost saving from skipping was ~1.5–2×, not the imagined 10×; the 10× lived entirely in an
  elaborate deferred-extraction subsystem (state tables, a promotion queue, a reconciler, four triggers)
  out of proportion to the lever.
- A pre-extraction skip is also where the worst correctness bug hides: skip the one section that
  supersedes an old fact and you serve a stale fact as current.

Instead, **junk-control happens where it is cheap and safe** (D34): E2 **Selection** drops low-value
statements in-call (§3.2), **D2** collapses duplicate facts into a single relation with an evidence
count (§5), and exact-duplicate inputs are a no-op re-ingest (idempotency, D12). The one real signal a
gate would have used — *this is a references section* — is **fed into Selection** (§3.1) instead of
thrown away as a binary skip; there it does more work.

*Documented add-back, not built:* if a corpus slice ever shows extraction cost is dominated by
structurally-skippable sections, the cheap fix is a single deterministic filter that keeps the
`references / bibliography / nav / boilerplate / legal` PageIndex node-types out of E2 — a metadata
branch, **not** a salience classifier and **not** a deferred-extraction machine.

## 5. E3 — claims become relations

Claims are *what a source said*; relations are *the distinct facts*. E3 normalizes eligible claims
into `(subject, predicate, object)` records and is where redundancy and supersession are handled. The
internals (entity resolution, predicate registry, the supersession cascade) are designed in
`registries_design.md` (D17–D24); the pipeline view:

- **Normalize.** Each claim yields 0..n relations via the governed predicate registry (D5, D18). "Project
  Atlas launched in 2024" → `(Project Atlas, launched_in_year, 2024)`. A claim that is pure opinion or a
  single-entity attribute may yield no relation — and that is fine; the claim still exists as evidence.
- **Resolve entities.** Subjects/objects are resolved to canonical entities through the tiered T0–T4
  cascade (D17). This is *why* decontextualization matters: "Project Atlas" resolves; "It" cannot. A
  claim with a dangling reference is dead weight here — which is the whole point of §3.2.
- **Collapse redundancy (D2).** The same fact asserted by 200 documents becomes **one** relation with
  **200 evidence rows**, not 200 edges. `evidence_count` is then a free confidence/salience signal —
  the thing a value gate tried to compute up-front, obtained for free after the fact.
- **Adjudicate supersession (D3, D4).** New facts close the validity windows of the ones they replace,
  via `(entity_id, predicate)` blocking + a cheap-first cascade — adjudicated on **relations**, never on
  claims (claims stay immutable records of what was asserted).

## 6. End-to-end, in one example

> Source chunk (inside a *Results* section of a 2024 product memo): *"It launched last year in three
> markets. The team considers it a runaway success."* Neighbour text names **Project Atlas**.

| Stage | What happens |
|---|---|
| **E1** | chunk + a context prefix ("…from the Results section of the Project Atlas 2024 memo…") |
| **E2 Selection** | keep "launched last year in three markets"; **drop** "considers it a runaway success" (opinion) → logged |
| **E2 Decontextualize** | "It"→Project Atlas (neighbour), "last year"→2024 (header) → *"Project Atlas launched in 2024 in three markets"* |
| **E2 Decompose** | `"Project Atlas launched in 2024."` + `"Project Atlas launched in three markets."` |
| **E2 Grounding** | each accepted: anchor span present, additions trace to bundle, entailed |
| **E3** | `(Project Atlas, launched_in_year, 2024)`; if a later memo says it launched in 2023, that relation's window is closed — the original claim is untouched |

## 7. Decisions, and what is still a spike

**Decisions:** **D31** (Claimify-staged E2 over a context bundle, two calls), **D32** (layered,
dual-field grounding), **D33** (append-only versioned decision ledger), **D34** (E2 Selection is the
value filter — no pre-extraction gate), **D35** (Selection recall envelope). Foundations: D2, D3, D4,
D5, D7, D12, D17–D19, D25.

**Spikes to clear before locking numbers** (full list in `claimify_research/SYNTHESIS.md` §4):

1. **One-call vs two-call** — measure on a golden slice before any collapse to a single call.
2. **Selection recall floor** — per-fact false-drop on a canary set; validate the never-drop classes.
3. **Grounding safety** — in-call self-verdict vs an independent judge; confirm the anchor +
   window-membership floor catches fabricated additions.
4. **Bundle cost per source-class** — the short-source tail breaks prompt-caching; decide a cheaper
   bundle (section path only, no neighbours) for chat/tool/git inputs.
5. **The E1 context prefix** — pin its length (or specify the E2 fallback when it is absent).

## References

Research: `plan/analysis/claimify_research/SYNTHESIS.md` (+ questions C1–C8, verify/, the Codex
cross-check). Adjacent designs: `registries_design.md` (E3 internals, D17–D24), `overall_design.md`
(plane E), `concepts.md` (claims vs relations, bi-temporality). Decisions: `decisions.md`
(D31–D35 and the foundations above; D25 records why there is no value gate).
