# TY3 — Should there be a TYPING CASCADE analogous to the resolution cascade (D17)?

**Question.** A cheap-first typing cascade for assigning the D18 core type (Person /
Organization / Place / Document / Event / Concept / Project / Product, + extension-pack types)
to a mention/entity. Candidate rungs: external-authority type (DOI→Document, ORCID→Person,
GLEIF LEI→Organization, Wikidata P31→type); deterministic gazetteer/suffix signals
(`Inc./Ltd.`→Organization); a small zero-shot typed-NER model (GLiNER-style); the extraction
LLM; human review for high blast-radius. Where does each earn its place, what confidence, how
does it escalate, and how does it interact with the resolution cascade (whose T0 already hits
the same authorities)?

---

## 1. Key findings

1. **Yes — build a typing cascade, but it is NOT a clone of D17. The two cascades are
   *orthogonal*, not parallel.** Resolution answers "**which** entity is this mention?"
   (mention→`entity_id`); typing answers "**what kind** of entity is this?"
   (mention→type∈core). They share the T0 authority layer but diverge immediately after:
   resolution escalation runs along a *string/embedding-similarity* axis (lemma→fuzzy→
   phonetic→embedding→LLM, D17 §3) because identity is a same-or-different judgement against a
   growing registry; typing escalation runs along a *semantic-signal-strength* axis
   (authority→deterministic-surface→learned-NER→LLM) because typing is a fixed K-way
   classification (K≈8-11) against a *closed* set with no registry to grow into. A near-miss in
   resolution means "maybe the same entity, ask harder"; a near-miss in typing means "maybe a
   different *type*, ask harder". Copying D17's tier *mechanisms* (pg_trgm, Daitch-Mokotoff)
   into typing would be a category error — those are similarity operators, and typing is not a
   similarity problem.

2. **The cascade is justified by the SAME asymmetry that governs D17 — but the asymmetry
   points the *opposite way*, which changes the default.** D17 is recall-conservative because
   over-merging poisons catastrophically (registries_design §1). For typing, the load-bearing
   failure is **D18 domain/range over-rejection**: a *wrong* type silently makes every
   predicate on that entity fail the `edge_type_map` gate (a mis-typed Person→Organization
   drops `works_for`), while a *missing* type (the `Concept`/catch-all fallback) merely makes
   the permissive `related_to` (any→any) the only legal predicate — degraded but not wrong. So
   typing must be **precision-conservative**: prefer "fall back to the catch-all and let
   `related_to` carry it" over "guess a specific type and silently kill real relations." This
   is the typing analogue of D17's block-loose/decide-tight, inverted: **type-tight, fall-back-
   loose.** Every rung that can't decide *escalates*, and the terminal fallback is `Concept`
   (the D18 core parent), never a drop and never a guess.

3. **The T0 sharing with D17 is real and should be exploited, but the authority gives type
   "for free" only when it *hits* — and D20 says most real entities are long-tail misses.** A
   GLEIF LEI is *by construction* an Organization (every LEI record carries an ISO 20275
   Entity-Legal-Form code — a legal entity is the only thing that can have one); a Wikidata
   P31=Q5 (human) is a Person; a resolved DOI is a registered work (Document⊂CreativeWork); an
   ORCID identifies a researcher (Person). When D17-T0 produces an external-ID match, the type
   falls out of the *same* lookup at *near-certain* confidence and zero extra cost. But because
   D20 makes T0 an accelerator that "never gates" and most entities miss it, the authority rung
   covers a *small head* of the type distribution. Typing therefore can't lean on it — it must
   have strong cheap rungs *below* the authority for the long tail, exactly where D17 also does
   its real work.

4. **The cheapest *broad-coverage* rung is the one D17 does not have: a small zero-shot
   typed-NER model (GLiNER) that emits a real per-span confidence score.** Across the six
   surveyed systems (Graphiti, Cognee, LightRAG, GraphRAG, mem0, GLiNER), GLiNER is the **only**
   one that produces a numeric, golden-set-thresholdable type confidence
   (`{start,end,text,label,score}`, `GLiNER/gliner/model.py:2279-2285`), runs on CPU, and takes
   the closed label set at call time — letting UGM pass its 8 core types directly as labels.
   Every LLM-extraction system (Graphiti/Cognee/LightRAG/GraphRAG) binds type at extraction with
   **no confidence and no list-validation** — the "fixed list" is a fiction the parser doesn't
   enforce (LightRAG `operate.py:533-557`, GraphRAG `graph_extractor.py:147`). So GLiNER is the
   natural confidence-bearing middle rung that makes a *tuned* typing cascade (D22-style) even
   possible; the extraction LLM is the rung above it, and only the residue reaches the LLM/human.

---

## 2. Evidence & detail with citations

### 2.1 What the surveyed systems actually do (and why none of them is a *cascade*)

Every production system reviewed assigns type at **one** rung — the extraction LLM — with no
escalation and (almost universally) no confidence:

- **Graphiti** types inside the extraction call against a *closed integer-ID list*
  (`ExtractedEntity.entity_type_id`, `graphiti/graphiti_core/prompts/extract_nodes.py:28-38`),
  with a reserved catch-all `Entity` (ID 0) and **out-of-range coercion to it**
  (`node_operations.py:303-306`). It also ships a standalone `classify_nodes` prompt
  (`extract_nodes.py:347-380`) — evidence that a *separate* typing pass is a recognised pattern
  — but the normal path types inline. Crucially, it has a **monotonic generic→specific
  promotion on merge** (`dedup_helpers.py:170-189`): a node still labelled `Entity` is upgraded
  when a more specific mention arrives, never downgraded. (repo_findings/graphiti_cognee.md)
- **Cognee** lets the LLM emit a *free-string* `type` (`cognee/shared/data_models.py:49-60`),
  then an ~0.8 difflib fuzzy match only *canonicalizes the name*
  (`matching_strategies.py:23-53`) — it does **not** classify into a taxonomy, and there is no
  domain/range enforcement (confirming D18's read of Cognee). This is the anti-pattern: an
  unbounded type space that D18's `edge_type_map` cannot gate against.
- **LightRAG** types in-prompt against soft guidance with an `Other` fallback (`prompt.py:62`)
  but the parser accepts any string (`operate.py:533-557`); merge reconciliation is
  **majority-vote** (`operate.py:1671-1674`), defaulting to `UNKNOWN`.
- **GraphRAG** makes type **part of the identity key** (`groupby(["title","type"])`,
  `extract_graph.py:104-115`) — so a type disagreement *forks the entity*. This is the explicit
  AVOID for UGM: it contradicts D17 (type is an attribute, not identity) and D21 reversibility.
- **mem0** (this checkout) does **no semantic typing** — only spaCy POS categories
  (`entity_extraction.py:346-351`); not a model for typing.
- **GLiNER** is the only confidence-bearing, closed-label, CPU-cheap typed-NER:
  `model.predict_entities(text, labels, threshold=0.5)`; sub-threshold spans are silently
  **dropped** (`model.py:2128,2255`) — so UGM must add an explicit catch-all, GLiNER won't.
  (repo_findings/lightrag_graphrag_gliner.md)

**Inference (flagged):** No surveyed system runs a *cheap-first typing cascade* with
escalation. The cascade is therefore a UGM synthesis, not a borrowed pattern — but every
*rung* of it is independently validated (authority-typing from D20's identifiers, closed-list
extraction typing from Graphiti, confidence-scored zero-shot from GLiNER, catch-all coercion
from Graphiti's ID-0). The novel part is *ordering them cheap-first and escalating on
low-confidence*, which is exactly what D17 did for resolution.

### 2.2 External-authority typing — verified type-bearing-ness of each authority

- **GLEIF LEI → Organization (near-certain).** Every LEI record carries an ISO 20275 Entity
  Legal Form (ELF) code; the ELF list has 3,250+ legal forms across 175 countries, and an ELF
  *is* "the type of legal company or organization." A thing with an LEI is, by construction, a
  legal organization. ([GLEIF ISO 20275 ELF Code
  List](https://www.gleif.org/en/about-lei/code-lists/iso-20275-entity-legal-forms-code-list))
- **Wikidata P31 (instance of) → core type (near-certain when P31 resolves to a head class).**
  P31=human (Q5) ⇒ Person; the class hierarchy makes an item implicitly an instance of more
  general classes (Angela Merkel → person), and entity-linking systems already use "P31 object
  = selected class or subclass" for automatic type identification.
  ([Wikidata Property talk:P31](https://www.wikidata.org/wiki/Property_talk:P31);
  [Help:Properties](https://www.wikidata.org/wiki/Help:Properties)) **Caveat (inference):** P31
  can point at a niche class (e.g. "fictional human", "business" vs "nonprofit") that needs a
  P31→UGM-core *mapping table*; the type is near-certain only after that map resolves to one of
  the 8. Mapping accuracy is an open item — flagged in §3.
- **DOI → Document⊂CreativeWork (near-certain).** A DOI that resolves is a registered
  work/object; for the corpora UGM targets it is a CreativeWork. (Crossref/DataCite carry a
  finer `type` — journal-article, dataset — which can refine the core type if a future pack
  needs it.) Verified at the design level via D20's DOI validator; the type is structural, not
  inferred from text.
- **ORCID → Person (certain).** An ORCID iD identifies a *researcher* — a person — by
  definition (D20 lists ORCID as a deterministic validator).

**Key consequence for the T0 interaction:** when D17-T0 fires, **typing is a side-effect of
the same authority lookup, at the same confidence, for zero marginal cost** — store it as the
entity `type` alongside the `external_ids` alias row (registries_design §2). The authority is
*never* the canonical `entity_id` (D20) — and likewise it is the *evidence* for the type, with
the type itself stored in `entities.type`. But per D20 most entities miss T0, so this rung
covers only the head; the cascade must not depend on it.

### 2.3 Deterministic surface signals (gazetteer/suffix) — high precision, narrow recall

`Inc./Ltd./LLC/GmbH/PLC/Corp.` suffixes ⇒ Organization; honorifics (`Dr./Mr./Ms.`) and
`firstname lastname` gazetteer hits ⇒ Person; quoted titles / file-extension / DOI-shaped
strings ⇒ Document. This is the **typing analogue of D17-T1 (exact match)**: deterministic,
near-zero cost, high precision on the patterns it covers, **silent on everything else**. It
earns its place as a cheap *accelerator* between authority and the learned model — it confirms
a type the LLM/NER would likely also get, but at zero model cost and with an auditable rule
(useful for D22 golden-set error analysis). It must **never reject** — absence of a suffix is
not evidence of non-Organization. **Inference:** the ISO 20275 ELF list (2.2) doubles as the
gazetteer source for the Org-suffix rung — a free, authoritative, 175-country suffix lexicon.

### 2.4 GLiNER (small zero-shot typed-NER) — the confidence-bearing broad rung

GLiNER takes the 8 core types as its label set, returns `{label, score}` per span
(`model.py:2279-2285`), runs on CPU (`README.md:32`), and is "competitive with LLMs several
times its size." Its `threshold` (default 0.5) is exactly the knob D22 golden-set tuning sets
**per type** — mirroring D17's per-type thresholds. It is the first rung that gives *broad*
coverage *and* a real confidence number, so it is where the cascade's "decide vs escalate" band
lives. Sub-threshold spans are dropped by GLiNER itself, so the cascade wraps it: below the
accept band → escalate, don't drop.

### 2.5 The extraction LLM rung & the merge-time reconciliation

Per Graphiti, the LLM can type inline against the **closed** core list (force the
integer-ID/enum schema, `extract_nodes.py:28-38`; never Cognee's free string). In a typing
cascade the LLM is the rung **above** GLiNER (more expensive, better at long-tail/ambiguous
context), reached only for the residue GLiNER couldn't confidently type. Two design choices:

- **Mention-level typing, entity-level reconciliation.** Type each mention, then reconcile at
  the entity once mentions merge (D17/D21). **Recommended rule = Graphiti's monotonic
  generic→specific promotion** (`dedup_helpers.py:170-189`): `Concept`(catch-all) is overwritten
  by any specific core type; a specific type is never downgraded; **conflicting specific types
  (Person vs Organization) do NOT auto-resolve by majority — they route to review (§2.6),**
  because a specific/specific type conflict on a merged entity is exactly the high-blast-radius
  signal D21 §"blast-radius rule" cares about. (Reject LightRAG's blind majority-vote and
  GraphRAG's identity-forking; majority-vote silently picks a side, forking violates D17/D21.)
- **Reversibility (D21).** Type decisions and merge-time promotions are append-only verdicts
  alongside `resolution_decisions`/`merge_events` — a type promotion is re-adjudicable on
  un-merge, same machinery, no new store.

### 2.6 Human review — only for high blast-radius type conflicts

Mirroring D17/D24: route to the review CLI only the type decisions where
`expected_impact = blast_radius × (1 − confidence)` is high — i.e. a specific/specific type
conflict on a high-degree entity, or a low-confidence type on an entity that many predicates
hang off. The vast majority never reach a human. This reuses the D24 cluster-review queue
(no new tool), with the type-verdict appended reversibly.

### 2.7 Where the typing cascade and resolution cascade *touch* vs *diverge*

| Aspect | Resolution cascade (D17) | Typing cascade (TY3, proposed) |
|---|---|---|
| Question | which entity? (mention→`entity_id`) | what kind? (mention→type∈core) |
| Shared rung | **T0 external authority** | **same T0 lookup yields the type for free** |
| Escalation axis | string/embedding similarity | semantic-signal strength |
| Tier mechanisms | lemma, pg_trgm, Daitch-Mokotoff, embedding, LLM | authority, suffix-gazetteer, GLiNER, LLM |
| Conservative toward | recall (under-merge OK, over-merge poisons) | **precision** (catch-all OK, wrong-type kills predicates) |
| Terminal fallback | mint new `entity_id` | `Concept` (D18 core parent) — never drop |
| Confidence source | per-type golden-set bands (D22) | per-type GLiNER score + golden-set bands (D22) |
| Reconciliation on merge | redirect/`merged_into` (D21) | monotonic generic→specific; conflict→review |

**Ordering interaction (important):** Typing can run *before, after, or interleaved with*
resolution. Recommended: **type the mention early (cheap rungs), because typing improves
resolution.** D17's thresholds are *per-type* (`thresholds_by_type` in `resolver_versions`) and
some authorities are type-scoped (ORCID only validates Persons). A mention typed Person can be
blocked/scored against Person thresholds; an Organization suffix steers it to GLEIF not ORCID.
So a cheap pre-type (authority+suffix+GLiNER) feeds resolution, and resolution's eventual
merge feeds back the entity-level type reconciliation — a two-way handshake, not a pipeline.

---

## 3. Confidence & gaps

**Confidence: HIGH** that a typing cascade is the right shape and that it must be *distinct
from* (not a clone of) D17, that it must be precision-conservative with a `Concept` terminal
fallback, and that GLiNER is the correct confidence-bearing broad rung. These follow directly
from: the verified type-bearing-ness of the authorities (GLEIF/Wikidata cited; DOI/ORCID
structural), the surveyed-system evidence (cited file:line), and the D18 domain/range
mechanics already in the design.

**Confidence: MEDIUM** on the *exact rung ordering and the inline-vs-separate typing choice.**
Graphiti types inline in the extraction LLM and it works; running GLiNER as a *separate* cheap
rung before the LLM is an efficiency/confidence argument (a real score for D22 tuning), not a
correctness one. If extraction already calls an LLM per chunk, the marginal value of a separate
GLiNER pass depends on cost numbers I did not measure.

**Gaps / not verified (no invented numbers):**
- **No accuracy numbers** for GLiNER on UGM's 8 core types, nor for any rung's precision/recall
  — these are golden-set spikes (D22), not literature constants. I deliberately assert none.
- **Wikidata P31 → UGM-core mapping table accuracy is unverified.** P31 can point at thousands
  of classes; the head→core map (Q5→Person, Q43229-subtree→Organization, …) is near-certain at
  the head but has a long ambiguous tail (fictional/legendary/group-of-humans). Mapping
  precision is an open spike.
- **DOI/Crossref `type` granularity** (does every targeted DOI cleanly map to
  Document⊂CreativeWork, or do dataset/software DOIs need Product?) — design-level confirmed,
  per-corpus unverified.
- **The cost trade-off** (separate GLiNER pass vs inline-LLM typing) is unmeasured.
- **GLiNER licensing/serving** for commercial deployments not checked here (parallels the
  CorPipe licensing open item in registries_design §5).

---

## 4. Recommendation for UGM

**Adopt a typing cascade — `Tt0`–`Tt4`, cheap-first, precision-conservative, escalate on
low-confidence, terminal fallback = `Concept`.** It is a *sibling* of D17, sharing only T0, and
it plugs directly into D15/D18 domain/range, D21 reconciliation, and D22 tuning.

| Rung | Mechanism | Earns its place because | Confidence | Escalates when |
|---|---|---|---|---|
| **Tt0** | External-authority type (shares D17-T0): GLEIF LEI→Org, ORCID→Person, DOI→Document, Wikidata P31→core via a mapping table | Type falls out of the *same* lookup at zero marginal cost; structurally near-certain | near-certain (record the authority as type-evidence) | authority misses (D20: most do) → fall through |
| **Tt1** | Deterministic surface/gazetteer: ISO 20275 ELF suffixes→Org, honorific/PER-gazetteer→Person, DOI-shape/extension→Document | Auditable, near-zero cost, high precision; never rejects | high on matched patterns | no pattern matches → fall through |
| **Tt2** | GLiNER zero-shot typed-NER, labels = the 8 core types, per-type threshold | Only rung with a real golden-set-tunable confidence; CPU-cheap; broad coverage | per-span `score`, D22-tuned **per type** | score in/below the escalate band |
| **Tt3** | Extraction LLM, **closed enum** over the core (Graphiti `entity_type_id`, never Cognee free-string) | Best on long-tail / context-dependent types; reuses the existing E2 call | model-reported, treated as last automated rung | specific/specific conflict on merge, or high blast-radius |
| **Tt4** | Human review (reuse D24 CLI) | Only for high `blast_radius × (1−confidence)` | adjudicated, reversible | — |
| **fallback** | `Concept` (D18 core parent) | Never drop, never guess; lets `related_to` (any→any) carry the entity so D18 never sees an untyped subject/object | — | terminal |

**Concrete ties:**

- **D18.** The cascade exists *to feed* `edge_type_map`: every mention reaching relation
  normalization has a core type, so domain/range can gate. The terminal `Concept` fallback
  guarantees a *defined* type for the gate (a missing type would make the gate undefined);
  `related_to` is the legal predicate for `Concept`-typed entities, so a low-confidence entity
  degrades gracefully instead of dropping facts. **Type-tight, fall-back-loose** is the
  precision-conservative inverse of D17's block-loose/decide-tight — chosen because *wrong* type
  is the catastrophic failure here (silent predicate drop), not *missing* type.
- **D15.** Extension-pack types (Task/Decision/Goal⊂Event/Concept) are added to the cascade's
  label/enum sets as registry rows — no machinery change. Extend-never-fork: a custom type that
  can't be confidently assigned falls back to its declared **core parent**, never to a fork.
- **D17.** Share T0 only; do **not** import T1–T4 *mechanisms* (similarity operators) into
  typing. Type early so the type can scope resolution (per-type thresholds, type-scoped
  authorities); reconcile the entity type at merge. Stamp every type decision with
  `resolver_version` like D17.
- **D21.** Type-on-merge = Graphiti's **monotonic generic→specific promotion** (`Concept`
  overwritten by any specific type; specific never downgraded; **specific/specific conflict →
  review**, never blind majority-vote, never GraphRAG-style identity fork). Type verdicts are
  append-only and re-adjudicable on un-merge — same Postgres reversibility store, no new
  machinery.
- **D22.** Each rung's accept/escalate band is **per-type, golden-set-measured, versioned** —
  the GLiNER threshold and the LLM-trust band ship only with a per-type P/R curve, exactly as
  D17's thresholds do. The golden set gains a *typing* slice alongside its resolution-pair slice
  (the open spike is labeling it without circularity — the cascade may *propose*, humans
  *adjudicate*).
- **Phasing.** Phase 1: Tt1 (suffix) + Tt3 (closed-enum LLM typing) + `Concept` fallback +
  golden typing slice — minimal, no new model dependency, unblocks D18 immediately. Phase 2:
  Tt0 (lands with D20's tier-0 authority connectors — they deliver type-evidence for free) +
  Tt2 (GLiNER, with its own model-store/versioning like the coref worker in §5). Tt4 reuses the
  D24 review CLI from Phase 1.

**Argument against the alternative (single-rung inline typing, the Graphiti/LightRAG default):**
it works but throws away (a) the *free* near-certain authority type already being fetched by
D17-T0, (b) a *tunable confidence number* (only GLiNER provides one — LLM inline typing gives
none, so D22 per-type threshold tuning has nothing to tune), and (c) the precision-conservative
escalation that keeps a wrong specific type from silently killing D18 predicates. The cascade is
strictly more aligned with the design's existing commitments (D17 cheap-first, D18 gate, D21
reversibility, D22 golden-set) than a single LLM rung, at the cost of one extra cheap model
(GLiNER) whose value should be confirmed against the cost numbers in the §3 gap.

---

## Sources
- [GLEIF — ISO 20275 Entity Legal Forms Code List](https://www.gleif.org/en/about-lei/code-lists/iso-20275-entity-legal-forms-code-list)
- [Wikidata — Property talk:P31 (instance of)](https://www.wikidata.org/wiki/Property_talk:P31)
- [Wikidata — Help:Properties](https://www.wikidata.org/wiki/Help:Properties)
- Repo findings (file:line citations within): `entity_typing_research/repo_findings/graphiti_cognee.md`, `entity_typing_research/repo_findings/lightrag_graphrag_gliner.md`
- Design context: `plan/designs/registries_design.md` (§1–§4, §6, §8, §10), `decisions.md` (D2,D4,D5,D15,D16,D17,D18,D20,D21,D22), `plan/analysis/concepts.md`
