# TY5 — Hard cases: polysemy/metonymy, subtype granularity, the Concept dumping-ground

Scope: the three hardest entity-typing failure modes for ugm, where typing (mention →
{Person, Organization, Place, Document, Event, Concept, Project, Product}) is currently
**unspecified** in the design yet D18 predicate domain/range enforcement *requires* a type
to be assigned. This note recommends concrete handling tied to D15/D17/D18/D21/D22.

---

## 1. Key findings

1. **Metonymy/polysemy is a context-dependent typing problem with a known annotation
   answer, not a model novelty.** The canonical rule is literally "*the White House*
   defaults to **Place**, unless *the White House does something*, in which case it is
   **Organization**" — i.e. the predicate context decides the type. ugm should treat typing
   as **context-scoped per mention** (type lives on the mention/`resolution_decision`, not
   first on the entity), and let domain/range act as a *disambiguator*, not just a gate.
   There is **no clean fallback that recovers the right type** when genuinely ambiguous —
   every surveyed production system either guesses (LLM/GLiNER) or dumps to a catch-all
   (Graphiti `Entity`). The honest fallback is therefore *route-to-review / keep the
   evidence in claims*, not invent a type.

2. **Coarse-to-fine is the correct extraction contract: pull the CORE type reliably; treat
   the leaf subtype (e.g. `ResearchPaper`) as a refinement that may abstain.** The
   literature is consistent that **leaf/fine/ultra-fine types are markedly harder than
   coarse types** (UltraFine: 9 coarse vs 121 fine vs ~10k ultra-fine, accuracy degrading
   sharply with granularity). For ugm, the extractor MUST commit to one of the 8 core types
   (D18 needs it); subtype assignment is a *separate, abstainable* decision the extractor (or
   a cheap second pass) makes only when confident — never forced. This is exactly what D15's
   `ResearchPaper ⊂ Document` parent-link buys you: domain/range is checked at the **parent
   (core) level**, so a missing subtype never blocks predicate validation.

3. **The Concept dumping-ground risk is real and quantified in the literature.** OntoNotes'
   catch-all `other` type is **42.6% of test mentions** and is a grab-bag of unrelated
   subtypes (product, event, art, living_thing, food). NER's `MISC` category is the same
   pathology (adjectives like "Italian" + events like "1000 Lakes Rally" in one bucket). A
   broad catch-all *does* swallow a near-majority of mentions in practice. `Concept` is
   ugm's `other`-shaped slot AND its hardest ER case (fuzzy boundaries → poor blocking, poor
   embeddings). Mitigation is threefold and all three should ship: (a) an **explicit,
   monitored `other:<freetext>` floor BELOW `Concept`** (D5/D15 already specifies this) so
   `Concept` is a *real* type, not the sink; (b) **monitor `Concept` growth and `other:`
   volume as a first-class health metric** (D22 already tracks singleton/cluster-size
   distributions — add Concept-share and other-share); (c) **prefer abstain (→ `other:` or
   review) over dumping into `Concept`** when confidence is low — refusing to type is safer
   than a wrong type because D18 domain/range will then wave through garbage.

4. **GLiNER gives ugm the mechanism for all three at once** (verified in the cloned repo):
   per-span `score` confidence, `multi_label` (assign core + subtype simultaneously), and
   `return_class_probs` (top-k per span) — `GLiNER/gliner/model.py:2163-2196, 1966-1967`.
   This is the only surveyed system with a real per-assignment confidence usable for a
   golden-set-tuned abstain threshold (mirrors D17's per-type tuned bands; D22 obligation).

---

## 2. Evidence & detail (citations)

### 2.1 Polysemy / metonymy / "the White House said"

- **The annotation rule that operationalizes context-dependent typing.** NER annotation
  guidelines: "*White House* defaults to being labeled as a **location** unless *the White
  House* does something, in which case it is labeled as an **organization**." Metonymy
  between LOC and ORG is explicitly flagged as requiring context: "Washington" → US
  government, "China" → Chinese government, a country name → its national team.
  (Survey + guidelines: [Annotation Guidelines for Corpus Novelties: NER](https://arxiv.org/pdf/2410.02281),
  [Code Book for Cross-Document Coreference in News](https://arxiv.org/pdf/2310.12064),
  [Wikipedia: Named entity](https://en.wikipedia.org/wiki/Named_entity).)
  *Inference (mine, flagged):* the disambiguating signal is the **predicate** — "X said" /
  "X announced" implies an Organization subject. ugm's D18 `edge_type_map` is precisely the
  table that encodes this ("the predicate `said`-like relation wants an Organization
  subject"), so domain/range can be run **as a typing prior**, not only as a post-hoc gate.

- **Polysemy is hard and unbounded.** "bank" has 49 BabelNet senses; highly polysemous
  words resist disambiguation; LLMs/transformers are SOTA at WSD but not perfect, and the
  cited surveys do **not** specify a context-window fallback or abstention mechanism — i.e.
  there is no published "clean fallback when genuinely ambiguous."
  ([Unsupervised WSD using Transformer attention, MDPI](https://www.mdpi.com/2504-4990/7/1/10);
  [Exploration-Analysis-Disambiguation framework for WSD with LLMs](https://arxiv.org/html/2603.05400v1).)
  *Verified-fact vs inference:* the *difficulty* is well-attested; the *"no clean fallback"*
  conclusion is my synthesis — the surveys are silent on abstention, which is itself the
  evidence that abstaining is under-served and must be designed in.

- **How the surveyed code handles ambiguity today (from repo_findings):**
  - GraphRAG makes it *worse*: type is part of the identity key (`groupby(["title","type"])`,
    `graphrag/.../extract_graph.py:104-115`) → "Apple" as ORGANIZATION vs PRODUCT **forks
    into two entities**. This is the anti-pattern; ugm must keep type OFF the identity key
    (already the design: type is an entity attribute, D17 resolves on name/embedding).
  - LightRAG reconciles by **majority vote** across mentions
    (`lightrag/.../operate.py:1671-1674`), default `"UNKNOWN"`. Cheap, but a majority vote
    over a polysemous name (Apple-the-company vs Apple-the-fruit) is *wrong* — it assumes one
    true type per surface string, which metonymy violates.
  - Graphiti dumps the unresolved case to bare `Entity` and **promotes generic→specific
    monotonically on merge** (`dedup_helpers.py:170-189`) — never downgrades. Clean, but a
    monotonic promotion is dangerous under metonymy (the first specific type wins and locks).

### 2.2 Subtype granularity (leaf vs core; who refines)

- **Fine/leaf types are harder than coarse types — strongly attested.** UltraFine /
  ultra-fine entity typing: among ~10,331 types, coarse (9 labels, e.g. person) is far
  easier than fine (121, e.g. engineer) which is far easier than ultra-fine (~10,201, e.g.
  *flight* engineer); accuracy "is exacerbated when dealing with ultra-fine types."
  ([Ultra-Fine Entity Typing](https://arxiv.org/pdf/1807.04905);
  [Coarse-to-fine decoding / hierarchical FET surveys](https://arxiv.org/pdf/2208.10081).)
  Fine-grained typing also allows a mention to occupy a **type-path that need not end at a
  leaf** — i.e. stopping at the coarse node is a first-class, valid output, not a failure.
- **Coarse-to-fine decoding is an established design** ("allows users to select between
  coarse- and fine-grained types"), though I did **not** find a paper *prescribing* a
  two-stage extractor→refiner pipeline specifically; the
  [From Ultra-Fine to Fine](https://arxiv.org/html/2312.06188) paper is about transfer
  learning, not pipeline staging (verified by fetch — it makes no coarse-first claim).
  *So:* "coarse type easy, leaf type hard, leaf is optional" is verified; "use a separate
  refiner step" is my engineering recommendation, supported by but not lifted from a paper.
- **D15 already gives the structural hook.** Every extension type declares a core parent
  (`ResearchPaper ⊂ Document`), and "subtypes inherit a parent's signatures"
  (`registries_design.md:130-134`). So domain/range (D18) is enforced at the parent level —
  the extractor only *has* to be right at the 8-type core; the leaf is gravy.
- **GLiNER mechanism (verified in repo):** `multi_label: bool` and `return_class_probs:
  bool` (`GLiNER/gliner/model.py:2163-2196`), per-span `class_probs` surfaced at
  `model.py:1966-1967`. You can pass `["Document","ResearchPaper","Person",...]` in one
  zero-shot call and read off both the core hit and the subtype hit with separate scores —
  the subtype can fail its threshold while the core passes. This is the cleanest "core
  mandatory, subtype abstainable" primitive in the survey.

### 2.3 The Concept dumping-ground

- **Quantified pathology — the headline number.** In OntoNotes, the catch-all `other` type
  is **42.6% of test-set mentions** and bundles unrelated subtypes (product, event, art,
  living_thing, food). A broad fallback does not stay small — it becomes the plurality
  class. ([Zero-Shot Open Entity Typing as Type-Compatible Grounding](https://arxiv.org/pdf/1907.03228),
  cited via [Jointly Learning Representations and Label Embeddings](https://arxiv.org/pdf/1702.06709).)
- **Same pathology under a different name (NER `MISC`):** "encompasses entities that do not
  fall into other specified categories ... diverse items such as adjectives like *Italian*
  and events like *1000 Lakes Rally*" — a catch-all is *internally incoherent*, which is
  exactly why it later resists clustering/embedding/ER.
  ([Annotation Guidelines for NER](https://arxiv.org/pdf/2410.02281).)
- **Why `Concept` specifically is the worst case for ugm's ER (ties to D21):** the
  dumping-ground subtypes have "large semantic gaps and diverse semantic meanings, meaning
  samples corresponding to the same entity type are not close to each other in the embedding
  space, leading to ambiguous prototypes" ([Taxonomy-guided prototype FET](https://www.sciencedirect.com/science/article/abs/pii/S0306457323002947)).
  ugm's T4 embedding tier (D17) and HAC distance-cut (D21) both assume within-type
  embedding cohesion — a heterogeneous `Concept` blob breaks blocking *and* clustering,
  which is the silent over/under-merge failure D21's health metrics are meant to catch.
- **What the surveyed systems do (repo_findings):**
  - Graphiti: reserved catch-all `Entity` (ID 0) with description "*does not fit any of the
    other listed types*", **out-of-range IDs coerced to it** (`node_operations.py:156-169,
    303-306`). A *typed floor* exists — but it is the sink.
  - Cognee: **no catch-all**, `is_a` is Optional; the raw LLM string is kept with
    `ontology_valid=False` (`expand_with_nodes_and_edges.py:139-146`) — i.e. a monitored
    "ungoverned" bucket, structurally identical to ugm's `other:<freetext>` (D5).
  - LightRAG: prompt says fall back to `Other`, but the parser accepts any free string
    (`operate.py:533-557`) — the "fixed list" is a fiction; type space silently drifts open.
    This is the failure mode ugm's explicit membership check must prevent.
- **Production-feasible abstain/monitoring signal:** GLiNER confidence "follows a long-tail
  distribution," and entity types frequent in pretraining are predicted more reliably than
  ambiguous ones (which are exactly the Concept-shaped ones) — so a per-type confidence
  threshold *can* separate "confident Concept" from "I'm dumping here."
  ([GLiNER scoring discussion](https://github.com/urchade/GLiNER/discussions/100);
  [FiNERweb on confidence distributions](https://arxiv.org/pdf/2512.13884).) GLiNER returns
  no type below threshold (silent drop) — so ugm must add the explicit `other:`/review
  bucket itself; it is not free.

---

## 3. Confidence & gaps

**Confidence: HIGH** on the three core claims:
- metonymy/polysemy needs context-scoped typing + there is no clean recover-the-type
  fallback (well-attested in annotation guidelines and WSD surveys);
- coarse types are reliable, leaf/fine types are not, and stopping at coarse is valid
  (directly quantified in UltraFine);
- a broad catch-all becomes a near-plurality dumping ground (OntoNotes `other` = 42.6%,
  MISC pathology) — a hard number, multiply sourced.

**Gaps / what I could NOT verify:**
- The exact 42.6% is from secondary citations of the Chen et al. 2019 paper; the PDF
  fetch failed to decode, so I confirmed the figure via two independent citing papers
  rather than the primary text. Treat as *well-corroborated, not primary-verified*.
- No paper *prescribes* a two-stage extractor→subtype-refiner pipeline; "use a separate
  refiner" is my engineering recommendation built on the verified coarse-easy/fine-hard
  finding, not a cited best practice.
- No surveyed system implements a *principled abstain-over-dump* rule — they either guess,
  silently drop (GLiNER), or dump to a sink (Graphiti). So ugm's "refuse-to-type → other:/
  review" is a build-not-borrow item (consistent with D24 "no OSS tool ships this").
- No measured `Concept`-share number for ugm's own corpora exists yet — the 42.6% is a
  *risk indicator from another dataset*, not a prediction for ugm. **Spike: measure
  Concept-share + other:-share on a ugm corpus slice before trusting any threshold** (same
  spirit as `registries_design.md:332` open spikes — do before committing numbers).

---

## 4. Recommendation for ugm (concrete, tied to decisions)

**(1) Polysemy/metonymy — context-scoped typing + domain/range as a prior + honest fallback.**
- **Type the mention, not the entity, first.** Store the type on the
  `resolution_decision`/mention (the schema already has `mentions` immutable + `entities.type`,
  `registries_design.md:50-66`). Different mentions of "Apple"/"Washington" may carry
  different core types; the entity-level `type` is a *reconciliation* over them, NOT part of
  the identity key (keep type OFF the blocking key — explicitly AVOID GraphRAG's
  `groupby(["title","type"])` fork). This preserves D17 (identity = name/embedding) and D21
  reversibility (a re-typed mention is an append, not a rewrite).
- **Run D18 `edge_type_map` as a disambiguating prior, not only a gate.** When a mention is
  the subject of a `said`/`announced`/`works_for`-class predicate whose domain is
  Organization, prefer Organization over Place for "the White House". This costs nothing
  extra — the table already exists for D18 — and turns the one structural gate we trust into
  a metonymy resolver.
- **Entity-level reconciliation rule:** LightRAG-style majority vote is too blunt for
  metonyms. Recommend: keep per-mention types; set `entities.type` to the **mode of recent,
  high-confidence mentions**, but **flag an entity whose mentions disagree across core types
  as a typing-conflict** → route to the D24 review queue (blast-radius weighted). Do NOT
  adopt Graphiti's monotonic generic→specific lock for cross-core-type conflicts (it locks
  in the first specific guess); monotonic promotion is fine only *within* a parent
  (Concept→subtype), never *across* core types.
- **Genuinely-ambiguous fallback = abstain to `other:` or review, never a coin-flip.**
  Below the golden-set-tuned typing confidence band (D22), do not assign a core type; emit
  `other:<freetext>` and keep the full claim in E2 (the evidence is never lost — concepts.md
  epistemics). This is the only honest answer when context truly underdetermines the type.

**(2) Subtype granularity — coarse mandatory, leaf abstainable, registry refines.**
- **Extractor contract: MUST return one of the 8 core types; MAY return a subtype.** The
  core assignment is non-optional (D18 domain/range needs it); the leaf is a separate,
  thresholded decision. Mechanically: one GLiNER call with `multi_label=True`,
  `return_class_probs=True` over `[8 core types] + [enabled pack subtypes]`
  (`GLiNER/gliner/model.py:2163-2196`); accept the core hit always, accept the subtype only
  above its own (lower-recall, higher-precision) golden-set band.
- **Who refines core→subtype:** the **registry-rendered prompt/labels** (D15: "prompts
  render from the registry") — enabling the Work pack or a legal pack simply adds its
  subtypes to the label set, so refinement is *configuration, not code*. A dedicated
  re-typing pass is **not** needed in v1; subtype can be upgraded later via Graphiti-style
  monotonic promotion **within a parent only** (Document→ResearchPaper is safe; it never
  changes which domain/range signatures apply, by D15 inheritance, `registries_design.md:130`).
- **Domain/range always checks at the core/parent level** so a missing or wrong leaf never
  blocks a valid predicate (D15 inheritance + D18). This makes "abstain on subtype" free.

**(3) The Concept dumping-ground — explicit floor + monitoring + abstain-over-dump.**
- **Keep `other:<freetext>` as a real floor BELOW `Concept`** (already D5/D15:
  "core → scope extensions → `other:<freetext>` escape, ungoverned, monitored"). Rule:
  **`Concept` is a positive assertion** ("this is an idea/topic/field the model is confident
  about"), and **`other:` is the dumping ground** — the model must *choose* `Concept`, never
  fall into it. Out-of-confidence mentions go to `other:`, not `Concept`. This is the single
  most important mitigation: it stops `Concept` from becoming OntoNotes' 42.6% `other`.
- **Add three Concept-specific health metrics to D22's continuous monitoring**
  (`registries_design.md:316-317` already tracks cluster-size/singleton/alias growth):
  (a) **`Concept`-share of all entities** (rising toward a plurality ⇒ over-dumping);
  (b) **`other:`-share + top `other:` value frequencies** (the D5/D7 promotion funnel — a
  frequent `other:` value is the system reporting an ontology gap, promote it to a pack
  subtype); (c) **intra-`Concept` embedding dispersion / mean cluster cohesion** (D21) —
  rising dispersion ⇒ `Concept` is incoherent and is poisoning blocking/clustering. These
  are cheap, ride existing D21/D22 machinery, and make the dumping-ground *observable*.
- **ER guardrail for `Concept` (D17/D21):** because Concept embeddings are heterogeneous,
  set **per-type thresholds for `Concept` to recall-conservative / auto-merge-OFF** — never
  auto-merge two Concepts on embedding alone; route to T5/review. This is exactly D17's
  per-type golden-set-tuned bands + D21's blast-radius rule, applied with the knowledge that
  Concept is the worst-cohesion type. Add ~400 hard pairs/type for Concept in the golden set
  (D22 already prescribes 400/type for auto-merge-critical types — make Concept one of them).
- **Refuse-to-type beats dump-to-Concept.** When the typer is below band, the correct output
  is `other:` (+ optional review for high blast-radius), NOT `Concept`. GLiNER silently drops
  sub-threshold spans (`model.py` threshold default 0.5), so ugm must add this explicit
  bucket — it is build-not-borrow (consistent with D24).

**Net:** typing for ugm should be a **GLiNER cheap tier returning per-span confidence**,
producing a **mandatory core type + optional thresholded subtype**, with **domain/range
(D18) doubling as a metonymy prior**, **`other:` as the monitored floor that protects
`Concept`**, and **abstain→review** (D24) as the only honest path when context genuinely
underdetermines the type — all bands golden-set-tuned and versioned per `resolver_version`
(D17/D22).

---

### Sources
- [Annotation Guidelines for Corpus Novelties: NER](https://arxiv.org/pdf/2410.02281)
- [Code Book for Cross-Document Coreference in News](https://arxiv.org/pdf/2310.12064)
- [Wikipedia: Named entity](https://en.wikipedia.org/wiki/Named_entity)
- [Unsupervised WSD Using Transformer Attention (MDPI)](https://www.mdpi.com/2504-4990/7/1/10)
- [Exploration-Analysis-Disambiguation WSD with LLMs](https://arxiv.org/html/2603.05400v1)
- [Ultra-Fine Entity Typing](https://arxiv.org/pdf/1807.04905)
- [Type-enriched Hierarchical Contrastive FET](https://arxiv.org/pdf/2208.10081)
- [From Ultra-Fine to Fine (transfer learning)](https://arxiv.org/html/2312.06188)
- [Zero-Shot Open Entity Typing as Type-Compatible Grounding](https://arxiv.org/pdf/1907.03228)
- [Jointly Learning Representations and Label Embeddings (cites OntoNotes 42.6%)](https://arxiv.org/pdf/1702.06709)
- [Taxonomy-guided Prototype Few-shot NER](https://www.sciencedirect.com/science/article/abs/pii/S0306457323002947)
- [GLiNER scoring/threshold discussion](https://github.com/urchade/GLiNER/discussions/100)
- [FiNERweb (confidence distributions)](https://arxiv.org/pdf/2512.13884)
- Repo: `_additional_context/GLiNER/gliner/model.py:1966-1967, 2163-2196`;
  Graphiti `node_operations.py:156-169,303-306`, `dedup_helpers.py:170-189`;
  GraphRAG `extract_graph.py:104-115`; LightRAG `operate.py:1671-1674,533-557`;
  Cognee `expand_with_nodes_and_edges.py:139-146`.
