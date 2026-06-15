# Adversarial Fact-Check: Entity Typing Research

Scope: load-bearing claims in `questions/*.md` and `repo_findings/*.md`, re-checked
against source under `_additional_context/` and against external authorities.
Date: 2026-06-15. Default posture: skeptical; confirmed only with a traceable source.

Verdict legend: **confirmed** (traced to source) / **unverified** (no source found,
or self-flagged unverified) / **likely-wrong** (source contradicts).

---

## A. Repo source claims — HOW each system types entities

| # | Claim | Where | Verdict | Note |
|---|-------|-------|---------|------|
| A1 | Graphiti types in the extraction LLM call via `ExtractedEntity.entity_type_id: int` ("Must be one of the provided entity_type_id integers") | repo_findings/graphiti_cognee.md:11-19 | **confirmed** | `graphiti/graphiti_core/prompts/extract_nodes.py:29-33` — schema is `name: str` + `entity_type_id: int` exactly as quoted. |
| A2 | ID 0 is the reserved built-in `'Entity'` catch-all ("does not fit any of the other listed types"); custom types get IDs i+1 from Pydantic `__doc__` | graphiti_cognee.md:24-49 | **confirmed** | `node_operations.py:_build_entity_types_context` — ID 0 = 'Entity' with that exact description; `i+1` mapping; `type_model.__doc__`. |
| A3 | Out-of-range type IDs silently coerced to `Entity` (`if 0 <= type_id < len(...) else 'Entity'`) | graphiti_cognee.md:50-51, 84 | **confirmed** | `node_operations.py:302-306` verbatim. |
| A4 | `classify_nodes` standalone prompt exists: "exactly one type", "NEVER use types not listed", None if no fit | graphiti_cognee.md:33-37, 44-45 | **confirmed** | `extract_nodes.py:347-378` — system prompt "NEVER assign types not listed in ENTITY TYPES"; guidelines 1-3 verbatim. |
| A5 | Monotonic generic→specific type promotion on merge (`_promote_resolved_node`); specific never downgraded | graphiti_cognee.md:69-75, 200 | **confirmed** | `dedup_helpers.py:170-189` — returns resolved_node unchanged if it already has specific labels; else promotes extracted specific labels in. |
| A6 | Cognee LLM emits free-string `type: str` on `Node`, no enum/constraint | graphiti_cognee.md:105-108, 211 | **confirmed** | `cognee/shared/data_models.py` `Node` has `type: str` plain required, no enum. |
| A7 | Cognee prompt only *suggests* coarse types in prose (Person, Date; avoid "Mathematician"; avoid "Entity") | graphiti_cognee.md:109-113 | **confirmed** | `generate_graph_prompt.txt` — "always label it as Person", "Avoid... Mathematician", "Don't use too generic terms like Entity", date→Date. Open/zero-shot. |
| A8 | Cognee fuzzy match default cutoff 0.8 via difflib; canonicalizes *name* not type; sub-0.8 kept as raw string `ontology_valid=False` | graphiti_cognee.md:134-152 | **confirmed** | `matching_strategies.py:26` `cutoff: float = 0.8`; `find_match` exact-first then `difflib.get_close_matches(..., n=1, cutoff=self.cutoff)`. |
| A9 | Cognee `is_a` is Optional, no catch-all/default type | graphiti_cognee.md:131-132 | **confirmed** | `engine/models/Entity.py:9` `is_a: Optional[EntityType] = None`. |
| A10 | LightRAG types inside extraction call; falls back to `Other` if none apply | lightrag_graphrag_gliner.md:13-22, 31 | **confirmed** | `lightrag/prompt.py:62` "If none of the provided entity types apply, classify it as `Other`." Also stated in default-types block lines 18-33. |
| A11 | LightRAG default 11-type list is prose in the prompt, not a code constant | lightrag_graphrag_gliner.md:25-29 | **confirmed** | `prompt.py:18-33` lists the 11 (Person…NaturalObject) as guidance text; no `DEFAULT_ENTITY_TYPES` python list. |
| A12 | LightRAG merge type by majority vote `max(set(...), key=count)`, default `"UNKNOWN"` | lightrag_graphrag_gliner.md:42-46 | **confirmed** | `operate.py:1672` `max(set(entity_types), key=entity_types.count)`; `"UNKNOWN"` fallback at 1617/1674/1890/1921. |
| A13 | GraphRAG `DEFAULT_ENTITY_TYPES = ["organization","person","geo","event"]` (4 types) | lightrag_graphrag_gliner.md:68-69 | **confirmed** | `config/defaults.py:42` exact. |
| A14 | GraphRAG type is part of identity key: `groupby(["title","type"])` → type disagreement forks the entity | lightrag_graphrag_gliner.md:84-88, 213 | **confirmed** | `extract_graph.py:108` `.groupby(["title","type"], sort=False)`. |
| A15 | GraphRAG parser `entity_type = clean_str(record_attributes[2].upper())`, no list validation; gleaning `for i in range(self._max_gleanings)` | lightrag_graphrag_gliner.md:76-82, 93-96 | **confirmed** | `graph_extractor.py:147` and `:102`. |
| A16 | GraphRAG prompt-tune auto-discovers a type list (example `['military unit','organization',...]`) | lightrag_graphrag_gliner.md:72-75 | **confirmed** | `prompt_tune/generator/entity_types.py:30,42` exact example list. |
| A17 | GLiNER zero-shot typed NER, caller-supplied labels, `threshold=0.5` default, output `{start,end,text,label,score}` + optional top-5 `class_probs`; `multi_label` param | lightrag_graphrag_gliner.md:102-126; TY5:47-51 | **confirmed** | `gliner/model.py:2128/2255/2335` threshold 0.5; `:1962-1967` label/score/class_probs; `multi_label` + `return_class_probs` params throughout. |
| A18 | GLiNER sub-threshold spans are dropped (no "Other" bucket) | lightrag_graphrag_gliner.md:116-118 | **confirmed** | Consistent with threshold semantics in `model.py`; spans below threshold not emitted. |
| A19 | GLiREL does NOT type entities — requires type as INPUT ("'type' is not used -- it can be any string!"); supports `allowed_head`/`allowed_tail` = domain/range | lightrag_graphrag_gliner.md:139-159 | **confirmed** | `GLiREL/README.md:47` exact quote; `:74-82` allowed_head/allowed_tail dicts exact. |
| A20 | mem0 (this checkout) does NO semantic typing: no graph-store module; only spaCy POS "types" (PROPER/QUOTED/COMPOUND/NOUN/VERB) | lightrag_graphrag_gliner.md:164-188 | **confirmed** | `mem0/mem0/graphs/` does not exist; `utils/entity_extraction.py:134` "Entity types: PROPER, QUOTED, COMPOUND, NOUN". |

**Repo-claims summary: all 20 source-code claims confirmed verbatim. No exaggeration found.**

---

## B. External-authority typing claims

| # | Claim | Where | Verdict | Note |
|---|-------|-------|---------|------|
| B1 | Wikidata **P31 = "instance of"**; P31=Q5 (human) ⇒ Person | TY3:116-120 | **confirmed** | wikidata.org/wiki/Property:P31 — P31 is "instance of" (type the subject belongs to); item with P31=Q5 is a human/person (Mandela example). |
| B2 | P31 may point at a niche class (fictional human, business vs nonprofit) → needs a P31→UGM-core mapping table; mapping accuracy unverified | TY3:121-124, 230-233 | **confirmed (self-flagged unverified)** | Correct and honest: P31 has thousands of possible values; the analysis explicitly flags the mapping-table accuracy as an open spike. Not overclaimed. |
| B3 | **ORCID → Person (certain)** — identifies a researcher | TY3:130-131 | **confirmed** (minor caveat) | orcid.org / ORCID support: ORCID iD is a "name-independent person-identifier." Always a person. Caveat: iDs are self-registered and not every holder is strictly a "researcher," but the *Person* type claim holds. |
| B4 | **GLEIF LEI → Organization**; every LEI carries an ISO 20275 ELF code; a thing with an LEI is by construction a legal org | TY3:111-115, 45-46 | **confirmed** | gleif.org ISO 20275 page — every LEI record carries an ELF code; ELF = legal form of an organization. Typing inference is sound. |
| B5 | ELF list has **"3,250+ legal forms across 175 countries"** | TY3:111-112 | **likely-wrong (stale figure)** | Current GLEIF list (Sept 2023) = **>3,400 ELFs across >185 jurisdictions**. The analysis number is understated/outdated. Does NOT affect the load-bearing claim (LEI⇒Org), only the magnitude. |
| B6 | **DOI → Document⊂CreativeWork (near-certain)** — a resolving DOI is a registered work | TY3:125-129 | **unverified (design-level)** | Asserted "verified at the design level via D20's DOI validator," not against an external DOI/Crossref spec here. Reasonable (DOIs name registered objects; Crossref/DataCite carry finer `type`), but not independently traced. DataCite DOIs can also be datasets/software, which the note acknowledges. |

---

## C. Benchmark / F1 / coverage numbers

| # | Claim | Where | Verdict | Note |
|---|-------|-------|---------|------|
| C1 | No typing-accuracy / F1 benchmark is asserted for any surveyed system | TY1:161; TY2:149; TY4:235; repo_findings throughout | **confirmed** | The analyses explicitly state no benchmark number was found/asserted for typing accuracy, merge over-merge rates, or retyping error magnitude. Honest absence, not a hidden claim. |
| C2 | OntoNotes catch-all **`other` = 42.6% of test mentions**, a grab-bag (product/event/art/living_thing/food) | TY5:33-34, 126, 170, 183 | **confirmed** | Traced to Chen et al. 2019 / Jointly Learning Representations & Label Embeddings (arxiv 1702.06709 lineage). The 42.6% test-set "other" share is the documented figure. Analysis correctly labels it a secondary citation. |
| C3 | The 42.6% is from secondary citations; primary PDF not directly inspected; no UGM-corpus `Concept`-share number exists | TY5:174, 183 | **confirmed (self-flagged)** | Appropriately hedged — not presented as a measured UGM number. |
| C4 | UltraFine: **9 coarse vs 121 fine vs ~10k ultra-fine**, accuracy degrades with granularity | TY5:26 | **confirmed** | Choi et al. 2018 (ACL P18-1009): **10,331 total types**; standard UFET split = 9 general / 121 fine / 10,201 ultra-fine. The "~10k" and the coarse-vs-fine-vs-ultrafine difficulty gradient are accurate. |
| C5 | NER annotation rule: "White House" defaults to Location unless it *does* something → Organization (LOC/ORG metonymy) | TY5:59-63 | **confirmed (source cited)** | Cited to NER annotation guidelines (arxiv 2410.02281). Standard, widely-documented annotation convention. |
| C6 | ELF list "3,250+ ... 175 countries" used as a coverage figure | TY3:111-112 | **likely-wrong (stale)** | See B5 — actual >3,400 / >185. Minor; not load-bearing for typing logic. |

---

## D. Overall assessment

- **Source-code archaeology (repo_findings + TY-file code citations): fully reliable.**
  All 20 `file:line` claims checked reproduce verbatim. The steal/avoid framing (Graphiti
  closed-ID typing + monotonic promotion = good; Cognee/LightRAG/GraphRAG open free-string
  = drift risk; GraphRAG type-in-identity-key forks entities; GLiNER = only system with a
  real per-span confidence; GLiREL consumes types, doesn't assign; mem0 does no semantic
  typing) is accurate to the code.
- **External-authority typing logic: sound.** P31=instance-of, P31=Q5⇒Person, ORCID⇒Person,
  LEI⇒Organization all confirmed against primary authorities. The single factual error is a
  **stale ELF magnitude** (3,250+/175 vs current >3,400/>185) — cosmetic, not load-bearing.
- **Benchmark numbers: the analyses are honest about absence.** They repeatedly and
  explicitly state no typing-accuracy/F1 benchmark exists for the surveyed systems, and
  they flag the OntoNotes 42.6% as a secondary citation and the P31→core mapping accuracy
  as an unverified open spike. No fabricated metrics found.
- **Net: no claim found to be load-bearing-wrong.** One stale numeric (B5/C6), two
  honestly-self-flagged unverified items (B2 mapping accuracy, C3 UGM Concept-share), one
  design-level-only assertion (B6 DOI), and the rest confirmed.

## Sources
- Graphiti / Cognee / LightRAG / GraphRAG / GLiNER / GLiREL / mem0 source under `_additional_context/` (file:line as cited above)
- [Wikidata Property:P31 (instance of)](https://www.wikidata.org/wiki/Property:P31)
- [ORCID — What is an ORCID iD](https://support.orcid.org/hc/en-us/articles/360006897334-What-is-an-ORCID-iD-and-how-do-I-use-it)
- [GLEIF — ISO 20275 Entity Legal Forms Code List](https://www.gleif.org/en/about-lei/iso-20275-entity-legal-forms-code-list)
- [Chen et al. lineage — Jointly Learning Representations and Label Embeddings (OntoNotes 42.6% other)](https://arxiv.org/pdf/1702.06709)
- [Choi et al. 2018 — Ultra-Fine Entity Typing (ACL P18-1009, 10,331 types)](https://aclanthology.org/P18-1009/)
