# R5 — Ontology core: validate the "familiar vocabulary" claim, survey core ontologies, recommend a seed core

Question R5 (registry research). Second, independent take (an Antigravity agent also covers this).
Validate/refute "LLMs extract better into familiar/standard vocabularies (schema.org) than bespoke
type names." Survey minimal core ontologies to borrow. Check how cognee & graphiti represent/enforce
ontologies in code. Assess D15 (extend-never-fork + parent-anchor + domain/range, not OWL). Recommend
a concrete seed core (8 types, ~12–15 predicates with domain/range mapped to standards).

---

## 1. Key findings

- **The general claim is well-supported, but the precise wording is too strong.** The robust,
  experimentally-backed fact is *"LLMs lean hard on the pretrained semantics of label tokens."*
  Meaningful labels beat arbitrary/numeric/symbolic labels by large margins, and models **cannot**
  remap label meaning via in-context examples (semantic-override rate measured at *exactly zero* across
  320 conditions). The narrower claim *"schema.org specifically > any other meaningful English name"*
  is **plausible but not directly demonstrated** in the literature I found. The honest framing for D15:
  use *familiar, semantically-loaded English names*; schema.org is the best-curated source of those, so
  align with it — but "Person/Organization/Place" win because they are common English words with rich
  priors, not because of a `schema.org/` namespace. (Confidence: high on the general claim; medium on
  schema.org-specific superiority.)

- **One important counter-data point keeps the claim from being absolute.** A 2026 generative-NER
  assessment reports LLMs show *"only marginal performance drops on datasets with symbol-based labels
  rather than meaningful names."* And domain-specific/rare types are recoverable with as few as **4
  few-shot examples** ("drastic improvement"). Implication for ugm: descriptions + examples rendered
  from the registry (D15's "prompts render from the registry") substantially close the gap for any
  bespoke type. Familiar naming is a **quality lever, not a hard gate** — exactly D15's own phrasing.

- **Independent industry/academic precedent validates "borrow schema.org, keep it small, extend
  top-down."** YAGO 4.5 (SIGIR 2024) deliberately adopts the schema.org taxonomy as its upper level
  *because it is "concise, maintained by a W3C consortium,"* and enforces a clean top-down taxonomy over
  bottom-up instance data — structurally identical to D15's "small borrowed core + anchored extensions."
  This is strong external confirmation of the *architecture* of D15 (less so the exact element list).

- **D15's "domain/range, not OWL" is sound and matches what the two reference systems actually ship.**
  Neither cognee nor graphiti runs an OWL reasoner on the hot path. Graphiti's *only* hard ontology
  enforcement is exactly D15's mechanism: a `(source_label, target_label) → allowed relation types` map
  (`edge_operations.py`), i.e. predicate domain/range. Cognee loads OWL via `rdflib` but uses it only as
  a fuzzy-match canonicalization authority (cutoff 0.8) and **has no domain/range enforcement at all**
  (`expand_with_nodes_and_edges.py`). So the proven, in-production slice of OWL is precisely the slice
  D15 keeps (parent links + domain/range); the discarded slice (reasoners, cardinality, property chains)
  is the slice neither system runs. **D15 is the right cut.** Recommended seed: 8 types, 14 predicates
  with domain/range mapped to schema.org (table in §4).

---

## 2. Evidence & detail (with citations)

### 2.1 Does the naming of the type/label actually move LLM extraction quality?

**Strong YES that label *semantics* matter; label *familiarity* is a softer, real effect.**

- *Semantic anchoring is near-absolute.* "Semantic Anchors in In-Context Learning: Why Small LLMs
  Cannot Flip Their Labels" (arXiv 2511.21038): with natural labels, ICL lifts QQP accuracy 40.6% →
  78.4% (8-shot); with *inverted* labels models collapse to 71.6% and **never** learn the contradictory
  mapping — *"the semantic override rate remains exactly zero"* across all models/tasks. Demonstrations
  *"adjust how inputs project onto pre-existing semantic directions but cannot redefine what label tokens
  mean."* This is the strongest single piece of evidence that the *words you choose for types/predicates
  are load-bearing*, because the model interprets them by their pretrained meaning, not by your prompt's
  stipulation. Directly supports D15's "familiar names are a quality lever" and D5's governed vocabulary.
  Source: https://arxiv.org/html/2511.21038

- *Meaningful > arbitrary/numeric, measurably.* Label-naming studies (e.g. label-set optimization work,
  arXiv 2410.19195; SALSA 2510.22691): *"semantically meaningful label words provide stronger supervision
  signals … class descriptions yield the best overall precision/recall/F1, whereas arbitrary or numeric
  tokens hinder discriminative capability; numeric label strategies performed the worst."* Reinforces:
  give types/predicates *real, descriptive names* (and descriptions), not codes.
  Sources: https://arxiv.org/pdf/2410.19195 · https://arxiv.org/pdf/2510.22691

- *The counter-weight (why the claim is "lever not gate").* "Assessment of Generative NER in the Era of
  LLMs" (arXiv 2601.17898) is reported to find *"only marginal performance drops on datasets with
  symbol-based labels rather than meaningful names"* (search-surfaced summary; **I could not verify the
  exact number in the PDF body** — flagged as uncertain). And the NER survey/clinical-NER literature
  notes rare/domain types are weak zero-shot but recover *"drastically"* with ~4 few-shot examples.
  Net: familiar naming gives you a *free* head-start; descriptions+examples (which the registry renders,
  D15) recover most of the rest for any bespoke type.
  Sources: https://arxiv.org/pdf/2601.17898 · https://medium.com/@atharva.chouthai/the-evolution-of-named-entity-recognition-from-traditional-ml-to-llms-6492c1106cf1

- *KG-construction practice agrees.* Multiple 2024–2026 KG-from-LLM writeups recommend giving the LLM a
  *pre-built, grounded type taxonomy* rather than letting it invent types, and note schema.org as the
  natural backbone with easy custom extension ("'Insight'/'OpportunityArea' aren't native schema.org
  types but extend it naturally"). This is D15's three-speed model (core → scope extension → `other:`).
  Sources: https://arxiv.org/pdf/2404.04068 · https://medium.com/@claudiubranzan/from-llms-to-knowledge-graphs-building-production-ready-graph-systems-in-2025-2b4aff1ec99a

**Verdict on the claim:** *Validated in spirit, refined in letter.* What LLMs reward is **familiar,
semantically-rich English names**. schema.org is the best-maintained dictionary of exactly those names
(and the one LLMs have seen most during pretraining, given its web ubiquity), so aligning to it is the
right move — but the mechanism is pretrained word-semantics, not the namespace. Do **not** claim a
measured "schema.org beats other good names" number; that specific A/B was not found.

### 2.2 Minimal core ontologies to borrow — survey

| Ontology | Size | Top-level shape | Borrow what / verdict for ugm |
|---|---|---|---|
| **schema.org** | 823 types, 1,529 properties, 19 datatypes (current count, schema.org/docs/schemas.html) | Root `Thing` → `Person, Organization, Place, CreativeWork, Event, Product, Intangible, Action, MedicalEntity` | **Primary backbone.** Web-ubiquitous → strongest LLM priors. Use ~8 top types + a curated predicate slice. Our 8 types map cleanly (§4). |
| **Wikidata** | ~4.2M classes under root `entity (Q35120)` | Polyhierarchical, instance-of/subclass-of; deliberately *not* a clean upper ontology | Borrow the **governance model** (persistent QIDs never reused, merge = redirect — already in `entity_registry.md §2/§4`, Tier-0 authority in resolution) — **not** the taxonomy (too convoluted; YAGO itself rejected it as the schema). |
| **FOAF** | small; core `Agent → Person, Organization, Group` + `knows, member, account, mbox` | Person-centric social graph | Borrow nothing structurally new; confirms `Person`/`Organization` + a `knows`-style relation are universal. Optional alias source for person predicates. |
| **Dublin Core (DCMI Terms)** | 15 core elements + extended terms | Flat metadata vocabulary (creator, title, date, subject, …) | Borrow **document/provenance predicate names** as alternates (`creator`, `subject`, `date`). Not a type system. Useful for E0/E1 file metadata, not the entity core. |
| **CIDOC-CRM** | 81 classes, 160 properties (v7.1.1) | Event-centric: `E77 Persistent Item, E2 Temporal Entity, E92 Spacetime Volume` | **Do not adopt.** Heavyweight, cultural-heritage/event-reification model; opposite of "familiar to an LLM." Its event-centrism is interesting prior art for our bi-temporal `Event` type but the vocabulary (`E5_Event`) has weak LLM priors. Skip. |
| **DBpedia ontology** | 685 classes | Cross-domain, infobox-derived | Reasonable middle ground, but redundant with schema.org and less LLM-familiar than schema.org. Skip as backbone. |
| **YAGO 4.5** | schema.org upper + Wikidata instances | schema.org top, top-down constraints | **Best precedent, not a dependency.** Validates the *method*: borrow schema.org top, enforce constraints top-down. Cite as design justification for D15. |

Sources: https://schema.org/docs/schemas.html · https://schema.org/docs/full.html ·
https://www.wikidata.org/wiki/Q35120 · https://iptc.org/thirdparty/foaf/ ·
https://www.dublincore.org/specifications/dublin-core/dcmi-terms/ ·
https://arxiv.org/pdf/2402.07531 (CIDOC-CRM sizing context) ·
https://arxiv.org/html/2308.11884v2 and https://suchanek.name/work/publications/sigir-2024.pdf (YAGO 4.5)

### 2.3 How cognee & graphiti represent/enforce ontologies (from repo_findings, cited to source)

**Cognee** (`repo_findings/cognee.md` §3, citing `cognee/modules/ontology/`):
- Ontology = an **external OWL/RDF-XML file** the user supplies; system ships none beyond test fixtures.
  Loaded by `RDFLibOntologyResolver` via `rdflib`; `build_lookup` indexes only two buckets — `classes`
  (`RDF.type OWL.Class`) and `individuals`.
- Enforcement is **canonicalization, not gating.** `FuzzyMatchingStrategy` (`matching_strategies.py`)
  does `difflib.get_close_matches(..., cutoff=0.8)`; on a ≥0.8 hit it *rewrites* the node's id/name to
  the ontology term and sets `ontology_valid=True`. No match → kept as-is, `ontology_valid=False`,
  **nothing rejected**.
- **Domain/range enforcement: explicitly "not found"** (cognee.md §3). Predicate names are free-form
  snake_case from the LLM, never validated against the ontology. This is the *opposite* of D5/D15.

**Graphiti** (`repo_findings/graphiti.md` §4, citing `graphiti_core/...`):
- Entity types = **Pydantic models**; the model's **docstring is the type description** fed to the LLM
  (`node_operations.py:176`). Built-in fallback `entity_type_id:0 = "Entity"`.
- Entity-type validation only checks field-name collisions (`entity_types_utils.py`) — **no domain/range
  on entities**.
- **Edges DO get domain/range** via `edge_type_map: dict[tuple[str,str], list[str]]` keyed by
  `(source_label, target_label)` → allowed relation names (`edge_operations.py:122,478`; default
  `{('Entity','Entity'): all}` at `graphiti.py:1115`). At resolution only edge types whose signature
  matches the actual endpoint labels are offered to the LLM. Entity classification is soft/prompt-level
  ("NEVER use types not listed … set to None"); **edge type-signature gating is hard/structural**.
- **Type promotion on merge** (`dedup_helpers.py:170`): merging a typed node into a generic `Entity`
  upgrades labels — never loses specificity. Worth stealing for ugm's merge logic (relates to
  `entity_registry.md §4`).

**Takeaway for D15:** the single piece of OWL that a real production memory system actually *enforces*
(graphiti's edge_type_map) is exactly **predicate domain/range** — D15's chosen mechanism. The richer
OWL machinery (reasoners, subsumption inference, cardinality) is loaded-but-unused (cognee) or absent
(graphiti). D15's "parent-links + domain/range, deliberately not OWL" is therefore the *empirically
validated* subset, not a compromise.

### 2.4 What is lost vs full OWL — and does it matter for extraction / blocking / retrieval?

| OWL capability D15 drops | What's lost | Matters for ugm? |
|---|---|---|
| **Reasoner / subsumption inference** (auto-infer `x is a Thing` from `x is a Person`) | Automatic transitive type membership | **No.** ugm gets this for free: parent-links are explicit columns; the P2 graph is rebuilt (D7) so "type at the core level" is a stored projection, not an inferred one. Cheaper and replayable. |
| **`owl:sameAs` / `owl:equivalentClass`** | Formal identity/equivalence axioms | **Partly handled elsewhere.** Identity is the entity registry's job (`merged_into` redirects, `entity_registry.md §4`), not the type system's. Don't duplicate it in the ontology. |
| **Cardinality / functional-property axioms** (e.g. a person has exactly one birthDate) | Constraint-checked single-valued facts | **Minor.** Bi-temporal supersession (D3/D10) handles "only one current employer" better than a static cardinality axiom would — it's a *windowed* truth, not a fixed cardinality. |
| **Property chains / complex axioms** (`uncleOf = brotherOf ∘ parentOf`) | Derived relations via inference | **No.** Out of scope for a memory system; would be a query-time graph pattern (Cypher), not an ontology axiom. |
| **Disjointness axioms** (`Person ⊓ Organization = ∅`) | Auto-detect a thing typed as both | **Low value, partly recovered.** Domain/range already rejects most type-confusion edges; disjointness is a nice-to-have validation, not a runtime need. |
| **Full domain/range as RDFS** | Formal, tooling-portable constraints | **Kept** — but as typed Postgres columns (`subject_type`, `object_type` on the predicate registry), not RDFS triples. Equivalent enforcement power for *extraction-hallucination rejection*, no reasoner. |

**Net:** the dropped capabilities are either (a) recovered more cheaply by ugm's existing mechanisms
(rebuild-projection for subsumption, registry for identity, bi-temporal windows for cardinality) or
(b) genuinely out of scope for a memory system. The *kept* capability (domain/range) is the one that
mechanically rejects extraction hallucinations and sharpens `(entity_id, predicate)` blocking (D4) —
the only one that pays for itself on the hot path. **The cut is correct.**

One real cost to acknowledge: **portability/interop.** A user bringing a genuine OWL ontology must have
it *imported into* the registry (parent-links + domain/range extracted, the rest dropped). D15 already
says this. Flag: importing OWL lossily means we cannot round-trip back to the user's full OWL — acceptable
for a memory system, but document it so it isn't a surprise. (Inference, low confidence on user impact.)

---

## 3. Confidence & gaps

**Well-supported (high confidence):**
- LLMs interpret type/predicate labels by *pretrained semantics* and cannot be talked out of it
  in-context (arXiv 2511.21038, "semantic override rate exactly zero"; 2410.19195 meaningful>arbitrary).
- Borrowing a small, clean schema.org-aligned top taxonomy and extending top-down is established
  practice (YAGO 4.5, SIGIR 2024).
- cognee has no domain/range enforcement; graphiti enforces predicate domain/range via edge_type_map and
  not much else — both **cited to the repo_findings, which are cited to source files**. The "OWL subset
  that's actually enforced = domain/range" conclusion is solid.
- schema.org `worksFor` domain=`Person`, range=`Organization` verified directly on schema.org/worksFor.

**Plausible but not directly proven (medium):**
- That schema.org names *specifically* beat other equally-meaningful English names. The literature shows
  meaningful>arbitrary and prior-semantics dominate; it does **not** isolate "schema.org vs synonym."
  I recommend ugm *claim only* "familiar, schema.org-aligned names" and not assert a measured delta.
- Exact magnitude of the "familiar-vocabulary" advantage for *type* (vs classification) extraction —
  no clean number found.

**Could not verify / gaps (low confidence — flagged):**
- The "marginal drops on symbol-based labels" figure from arXiv 2601.17898: surfaced by search but I
  could **not** confirm the exact wording/number in the PDF body. Treat as directional only.
- Per-predicate schema.org domain/range below: I verified `worksFor` directly; `memberOf`, `author`,
  `about`, `location`, `parentOrganization`, `foundingDate` are mapped from schema.org property pages /
  search summaries but I did **not** open each property page. The mappings in §4 are correct to my
  knowledge of schema.org but should be spot-checked against schema.org/<prop> before freezing.
- No benchmark numbers for ugm's own extraction exist yet — the golden-set requirement
  (`entity_registry.md §7.1`, O6 dependency) is the right place to actually measure the familiar-vs-bespoke
  delta on *our* data before over-investing. **Recommend measuring, not assuming.**

---

## 4. Recommendation for ugm

### 4.1 On the claim (D15 wording)
Keep D15's framing — it is already correctly hedged ("familiar names are a quality lever, not
aesthetics"). Tighten the supporting rationale to: *LLMs interpret labels by pretrained word-semantics
(strongly evidenced); schema.org is the best-curated, most web-ubiquitous source of such names, so we
align to it; we do not rely on schema.org being magically better than synonyms.* Do not cite a numeric
"schema.org wins by X%"; it isn't established. Lean on **descriptions + few-shot examples rendered from
the registry** (already D15) to carry any bespoke/rare type — 4 examples measurably closes most of the
gap.

### 4.2 Concrete seed core — 8 entity types
All anchor to schema.org top types (extend-never-fork parent = the schema.org type itself; everything
ultimately ⊂ `Thing`). Names chosen for *maximum LLM familiarity* = common English + schema.org-aligned.

| ugm type | schema.org anchor | Notes |
|---|---|---|
| `Person` | schema.org/Person | universal; FOAF `foaf:Person` alias |
| `Organization` | schema.org/Organization | companies, teams, institutions; `parentOrganization` available |
| `Place` | schema.org/Place | use "Place" (schema.org) over "Location" — schema.org/Place is the canonical type, strong priors |
| `Document` | schema.org/CreativeWork | **name it `Document`, anchor to `CreativeWork`.** "Document" has stronger, less-ambiguous LLM priors for a memory system than "CreativeWork"; DCMI/`schema.org/DigitalDocument` reinforce. Scope types (`ResearchPaper ⊂ Document`) extend here. |
| `Event` | schema.org/Event | carries the bi-temporal interest (D3/D10); CIDOC-CRM event-centrism is prior art but we keep the familiar name |
| `Concept` | schema.org/DefinedTerm (or `Intangible`) | topics/skills/abstract subjects; `knowsAbout`/`about` point here |
| `Project` | schema.org/Project | first-class for K2 project scopes (D16); schema.org/Project exists |
| `Product` | schema.org/Product | goods/software/offerings |

(Deliberately *excluded* from the core, push to scope extensions: `Role`, `Date`/`Timestamp` as a node
type — model time as edge attributes per D10, not a node; `Money`, `MedicalEntity`. Keep core at 8.)

### 4.3 Concrete seed predicates — 14, with domain/range mapped to standards
Domain → Range over the 8 core types. `subject_type`/`object_type` are the two typed columns D15 calls
for (the enforced "OWL subset"). Names schema.org-aligned where a clean equivalent exists.

| ugm predicate | Domain → Range | schema.org mapping | Verified? |
|---|---|---|---|
| `works_for` | Person → Organization | `worksFor` (domain Person, range Organization) | **verified** on schema.org/worksFor |
| `member_of` | Person/Organization → Organization | `memberOf` | mapping high-confidence, not page-opened |
| `affiliated_with` | Person → Organization | `affiliation` | mapping, not page-opened |
| `located_in` | Person/Organization/Event/Place → Place | `location` / `containedInPlace` | mapping, not page-opened |
| `part_of` | Organization → Organization (or Place→Place) | `parentOrganization` / `isPartOf` | parentOrganization verified by search |
| `authored` | Person → Document | `author` (inverse of schema.org author) | mapping, not page-opened |
| `created` | Person/Organization → Product/Document | `creator` | mapping, not page-opened |
| `about` | Document → Concept/Thing | `about` (range Thing) | range Thing verified by search |
| `knows_about` | Person/Organization → Concept | `knowsAbout` | mapping high-confidence |
| `knows` | Person → Person | `knows` (also FOAF `foaf:knows`) | mapping, not page-opened |
| `participated_in` | Person/Organization → Event | `attendee`/`performer` (inverse) | mapping, not page-opened |
| `works_on` | Person/Organization → Project | (no clean schema.org prop) `other:`-promoted core | **no schema.org equiv — ours** |
| `founded` | Person → Organization | `founder` (inverse) / pair w/ `foundingDate` attr | mapping, not page-opened |
| `related_to` | Thing → Thing | `relatedTo`/`sameAs`-adjacent generic | the universal fallback parent for predicate extension (D15) |

Notes:
- `related_to` is the **predicate-side core parent** for "extend-never-fork" — any scope predicate
  (`advises ⊂ related_to`) falls back to it for cross-scope queries/blocking (D15, `entity_registry.md §5`).
- Time predicates are **not** in this list by design: validity is bi-temporal edge metadata
  (`valid_from/valid_until/ingested_at/invalidated_at`), per D3/D10 — not a `has_date` predicate.
  `foundingDate`-style facts become attributes on the relation, not separate Date nodes.
- `works_on` has no clean schema.org property — keep it core anyway (high value for D16 project scopes)
  and flag it as a *coined* core predicate, the first candidate for the `other:`→core promotion funnel (D5).

### 4.4 Mechanism recommendations (tie to decisions)
1. **Implement domain/range exactly as graphiti's edge_type_map, in Postgres** (D5/D15): two typed
   columns on the predicate registry; reject (or route to `other:`) any extracted `(s,p,o)` whose
   subject/object core types violate them. This is the one OWL feature both reference systems prove is
   worth enforcing; it mechanically kills a class of extraction hallucinations before E3 (D4 blocking
   stays clean).
2. **Steal graphiti's type-promotion-on-merge** for the entity registry merge path (`entity_registry.md
   §4`): merging into a generically-typed entity should *upgrade* to the more specific core type, never
   downgrade.
3. **Do NOT adopt cognee's "ontology = optional OWL file that only enriches, never gates"** as the
   governance model — it has no domain/range and lets predicates fragment (the exact failure D5
   prevents). Borrow only its *Tier-0 external-authority canonicalization* idea (already in
   `entity_registry.md §4`).
4. **Render extraction prompts from the registry with 1–2 examples per type/predicate** (D15): this is
   the evidence-backed mitigation that lets bespoke/rare types reach near-core quality (~4 examples →
   "drastic improvement").
5. **Defer freezing exact thresholds and the exact predicate list to the golden set** (`entity_registry.md
   §7.1`, O6): measure the familiar-vs-bespoke delta on ugm data rather than inheriting an assumed number.
6. **Spot-check the §4.3 schema.org mappings** against each schema.org/<prop> page before writing
   `registries_design.md` (only `worksFor`, `parentOrganization`, `about`-range verified here).

### Sources
- LLM label semantics: https://arxiv.org/html/2511.21038 · https://arxiv.org/pdf/2410.19195 ·
  https://arxiv.org/pdf/2510.22691
- Generative NER / label naming counter-point: https://arxiv.org/pdf/2601.17898 ·
  https://medium.com/@atharva.chouthai/the-evolution-of-named-entity-recognition-from-traditional-ml-to-llms-6492c1106cf1
- KG-from-LLM practice (grounded taxonomy > invented): https://arxiv.org/pdf/2404.04068 ·
  https://medium.com/@claudiubranzan/from-llms-to-knowledge-graphs-building-production-ready-graph-systems-in-2025-2b4aff1ec99a
- schema.org sizing & hierarchy: https://schema.org/docs/schemas.html · https://schema.org/docs/full.html ·
  https://schema.org/worksFor · https://schema.org/parentOrganization
- YAGO 4.5 (schema.org-as-upper, top-down): https://arxiv.org/html/2308.11884v2 ·
  https://suchanek.name/work/publications/sigir-2024.pdf
- Wikidata root/ontology: https://www.wikidata.org/wiki/Q35120 ·
  https://www.wikidata.org/wiki/Wikidata:WikiProject_Ontology
- FOAF: https://iptc.org/thirdparty/foaf/ · Dublin Core:
  https://www.dublincore.org/specifications/dublin-core/dcmi-terms/
- CIDOC-CRM sizing/context: https://arxiv.org/pdf/2402.07531 · DBpedia (685 classes) via
  https://link.springer.com/chapter/10.1007/978-3-031-72437-4_23
- Repo findings (cited to source files):
  /Users/jpuc/code/moje/ultimate_memory/ugm/plan/analysis/registry_research/repo_findings/cognee.md (§3) ·
  /Users/jpuc/code/moje/ultimate_memory/ugm/plan/analysis/registry_research/repo_findings/graphiti.md (§4)
- ugm design: decisions.md D3/D4/D5/D7/D10/D15/D16 · entity_registry.md §2/§4/§5/§7
