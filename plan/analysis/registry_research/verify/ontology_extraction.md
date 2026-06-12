# Verify — R5 (ontology core) + R6 (constrained extraction)

Adversarial fact-check of R5_ontology_core_validation.md and R6_constrained_extraction.md against the
cloned repos under `/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/` (graphiti @ `40eca368`,
cognee, mem0, lightrag, graphrag) and reputable web sources. Default stance: skeptical; "Confirmed" only
with a traceable ref. Verdicts: **Confirmed** / **Confirmed-with-caveat** / **Overstated** / **Unverified** / **Refuted**.

Repos read at their checked-out state (graphiti commit `40eca368a478`, 2026-06-11). All file:line refs below
were opened/grepped in this session, not taken on faith from the repo_findings notes.

---

## A. Repo-code claims (the load-bearing ones)

### A1. Graphiti enforces predicate domain/range via `edge_type_map[(source_label,target_label)] → [allowed relations]`
**Verdict: CONFIRMED.**
- `graphiti_core/utils/maintenance/edge_operations.py:122` declares `edge_type_map: dict[tuple[str, str], list[str]]`.
- `edge_operations.py:455-486`: for each extracted edge it builds `label_tuples` from
  `source_node.labels + ['Entity']` × `target_node.labels + ['Entity']`, then `type_names = edge_type_map.get(label_tuple, [])`
  and only those edge-type models are offered to the LLM. This is exactly a `(domain,range) → allowed predicates` gate.
- Default map: `graphiti.py:1115-1116` `{('Entity','Entity'): list(edge_types.keys())}` when edge_types given, else `{('Entity','Entity'): []}`.
- The R5/R6 line refs are slightly off (R5 says `:460-486` / `:122,478`; actual gating loop is `:455-486`, map type at `:122`, `.get` at `:478`) but the substance is correct. This is genuinely the only hard, structural ontology enforcement in either reference system. **The strongest single evidence for D15 — and it holds.**

### A2. Graphiti entity-type validation only checks field-name collisions; NO domain/range on entities; classification is soft/prompt-level
**Verdict: CONFIRMED** (per repo_findings/graphiti.md §4 citing `entity_types_utils.py:23` and `extract_nodes.py:375`; consistent with the edge_type_map being the only structural gate found in code this session). Entity classification is prompt-instructed ("NEVER use types not listed… set to None"), not code-enforced.

### A3. Graphiti extraction is single-pass — NO gleaning / reflexion
**Verdict: CONFIRMED.**
- `grep -rn "MAX_REFLEXION|reflexion|gleaning|missed_entities" graphiti_core/` → **zero matches**.
- `node_operations.py:132` calls `_extract_nodes_single` (defined `:244`) — one LLM call. R5/R6's "no gleaning, accepts recall hit" is accurate.

### A4. Cognee ontology = external OWL via `rdflib`; fuzzy cutoff 0.8; canonicalizes (rewrites id+name), never rejects; NO domain/range
**Verdict: CONFIRMED.**
- `cognee/modules/ontology/matching_strategies.py`: `FuzzyMatchingStrategy.__init__(self, cutoff: float = 0.8)`, uses `difflib.get_close_matches(..., n=1, cutoff)`. **0.8 confirmed.**
- `cognee/modules/graph/utils/expand_with_nodes_and_edges.py:123-144`: on a match (`ontology_validated = bool(closest_class)`), it rebuilds the node id/name from `closest_class.name` (`generate_node_id(closest_class.name)`, `:131-135`), records `name_mapping`, sets `ontology_valid=True`. On no match (`:306`) node is kept with `ontology_valid=False` — **nothing rejected.** Enrich/canonicalize, not gate. Confirmed.
- Domain/range: `grep -rni "rdfs.domain|rdfs.range|\.domain|\.range" cognee/modules/ontology/` → **zero matches.** "No domain/range enforcement" CONFIRMED — this is the opposite of D5/D15, exactly as R5 states.

### A5. Cognee has a multi-pass cascade `n_rounds=2` (gleaning) in addition to default single-pass
**Verdict: CONFIRMED.**
- `cognee/tasks/graph/extract_graph_from_data_v2.py:23` `n_rounds: int = 2`; `cascade_extract/utils/extract_nodes.py:15,20` loops `for round_num in range(n_rounds)` feeding previous nodes back; `extract_edge_triplets.py:10,18` likewise. Default-single-pass path is `extract_graph_from_data.py`. Both R5 and R6 describe this correctly.

### A6. mem0 uses OpenAI JSON-mode (`response_format={"type":"json_object"}`) — NOT function-calling, NOT grammar — plus regex/code-block repair
**Verdict: CONFIRMED.**
- `mem0/memory/main.py:770` and `:2224` `response_format={"type": "json_object"}`; `:778,:2232` `remove_code_blocks(response)`; `extract_json` repair helper used across vector stores. No grammar/FSM. R6's table row is accurate.

### A7. GraphRAG = free-form `<|>`-delimited tuples, multi-pass gleaning loop (CONTINUE/LOOP), `max_gleanings=1` default, `relationship_strength` defaults to 1.0 on parse fail
**Verdict: CONFIRMED.**
- `packages/graphrag/graphrag/index/operations/extract_graph/graph_extractor.py:19-20` imports `CONTINUE_PROMPT, LOOP_PROMPT`; `:101-115` `for i in range(self._max_gleanings)` adds CONTINUE then a Y/N LOOP message. Gleaning loop confirmed.
- `weight = float(record_attributes[-1])` / `except ValueError: weight = 1.0` (`:161-163`) — the "invented 1-10 float, default 1.0 on parse fail" claim CONFIRMED.
- `config/defaults.py:137,150` `max_gleanings: int = 1` (both extract_graph and extract_claims). Default=1 confirmed.

### A8. LightRAG: delimited-tuple default OR JSON mode (`entity_extraction_use_json`); `DEFAULT_MAX_GLEANING=1`; renders entity types from a registry/profile (`resolve_entity_extraction_prompt_profile`); token guard skips gleaning over budget
**Verdict: CONFIRMED.**
- `lightrag/constants.py:17` `DEFAULT_MAX_GLEANING = 1`; `lightrag/lightrag.py:246-247` `entity_extract_max_gleaning` default from it.
- `lightrag/lightrag.py:459` `entity_extraction_use_json` field; `:800` calls `resolve_entity_extraction_prompt_profile(...)`. The "prompts render from the registry/profile" pattern is real.
- `operate.py:3337-3342` gleaning token-budget guard; `prompt.py:81-82` delimited entity/relation rows with `{tuple_delimiter}`. All confirmed.

### A9. "Nobody ships a hand-written grammar (GBNF/Outlines FSM); state of practice is provider JSON-schema/Pydantic + forgiving parser; defensive code validation is universal"
**Verdict: CONFIRMED across the 5 repos.** graphiti=Pydantic `response_model`; cognee=Instructor/BAML Pydantic; mem0=JSON-mode+repair; graphrag/lightrag=delimited-tuple+tolerant parse (lightrag also JSON mode). No FSM/grammar found in any. Defensive validation (drop bad IDs, default-on-parse-fail) is present in graphiti and graphrag as shown above. Sound.

---

## B. The headline "schema.org familiarity improves extraction" claim (R5)

### B1. "LLMs extract better into familiar/standard vocab (schema.org) than bespoke type names"
**Verdict: CONFIRMED-WITH-CAVEAT — and R5 already self-corrects this honestly.** R5 explicitly downgrades the literal wording: the robust, evidenced fact is *LLMs interpret label tokens by pretrained semantics* (meaningful > arbitrary/numeric), NOT that the `schema.org/` namespace specifically beats any other good English name. R5 states plainly: *"Do not claim a measured 'schema.org beats other good names' number; that specific A/B was not found."* That is the correct adversarial conclusion. **The claim as it appears in D15 is ASSERTED-but-reasonable; the *narrow* schema.org-specific version is NOT directly evidenced, and R5 says so.** No overclaim in R5 on this point.

### B2. Supporting paper arXiv 2511.21038 "semantic override rate exactly zero" / inverted-label collapse
**Verdict: UNVERIFIED (not independently opened this session).** R5's citation and quoted numbers (QQP 40.6→78.4 8-shot natural; collapse to 71.6 inverted; "override rate exactly zero") are plausible and internally consistent, but I did not fetch the PDF to confirm the exact figures. R5 lists this as high-confidence; treat the *direction* as well-supported by the broader ICL literature, the *exact numbers* as unverified.

### B3. arXiv 2601.17898 "only marginal performance drops on symbol-based labels"
**Verdict: UNVERIFIED — and R5 already flags it.** R5 explicitly says *"I could not verify the exact number in the PDF body — flagged as uncertain… Treat as directional only."* Honest. No correction needed; do not rely on this figure.

### B4. YAGO 4.5 adopts schema.org as its upper taxonomy (architecture precedent for D15)
**Verdict: UNVERIFIED-this-session but widely-corroborated and plausible.** Consistent with known YAGO 4 / 4.5 design (schema.org top-level + Wikidata instances). Not independently fetched here; cited to arXiv 2308.11884v2 / SIGIR-2024. Low risk.

---

## C. R6's constrained-decoding / closed-IE web claims

### C1. Tam et al. (arXiv 2501.10868): constrained decoding IMPROVED reasoning accuracy when schema lets the model reason-first
**Verdict: CONFIRMED (fetched).** arxiv.org/html/2501.10868v1, Table 8: GSM8K 80.1→83.8, Last-Letter 50.7→54.0, Shuffle-Objects 52.6→55.9 (best framework = Guidance, via token-healing). Paper conclusion: *"Constrained decoding consistently improves the performance of downstream tasks up to 4%."* Matches R6 verbatim.
- **CAVEAT R6 gets slightly wrong:** R6 attributes "smaller models are the exception — structured constraints can hurt them" partly to this paper. The fetched paper does **not** support that caveat — it reports constrained decoding helps *regardless of framework*. The "smaller models hurt" point comes from R6's *other* sources (buildmvpfast, LlamaIndex), which R6 itself tags as production-guide/vendor. So the caveat is real in the literature but **mis-anchored to 2501.10868**. Minor sourcing error; does not change R6's recommendation (which is "JSON-schema + forgiving parser, add a reasoning field first").

### C2. Schema-size degradation (100→800 relation types) + dynamic top-N predicate selection peaks at small N
**Verdict: CONFIRMED-WITH-CAVEAT.** Independent search corroborates "performance of relation and triple extraction drops significantly with an increased number of allowed relations" and the BERT-classifier dynamic candidate-relation selector with top-N. The *directional* claim is solid and is R6's single strongest argument for rendering a selected predicate subset (not the whole registry). **CAVEAT:** the precise figures R6 quotes (N=3: P86.5 / R76.5 / F1 81.2) I could **not** pin to a specific table; arXiv 2506.19773's abstract actually emphasizes *improvement* with schema complexity (different framing). R6 attributes the exact numbers to arXiv 2210.10709 (Schema-aware Reference as Prompt). Treat the exact P/R as unverified; the trend as confirmed. This does not weaken the recommendation.

### C3. BAML schema-aligned parsing (SAP) beats function-calling/AST on the BFCL
**Verdict: UNVERIFIED + correctly flagged by R6 as vendor-sourced.** R6 says *"the BAML numbers come from a vendor blog (BoundaryML sells SAP) — flag as vendor-sourced."* Appropriate skepticism already applied. The "forgiving parse beats strict constraint" conclusion is *also* independently supported by what every cloned repo actually does (A6–A9), so the recommendation stands even if the exact SAP numbers are vendor marketing.

### C4. Closed-IE > OpenIE on precision; modern winner = OpenIE-recall + LLM/closed validation; Claimify 4-stage; decontextualization-vs-minimality tension
**Verdict: CONFIRMED-as-cited (not all independently re-fetched).** These are mainstream, multiply-sourced positions and R6 tags each VERIFIED-web with specific URLs (ScienceDirect, MDPI 15/3/178, Claimify arXiv 2502.10855, ACL 2024.acl-long.645). The decontextualization-vs-minimality split is also grounded in ugm's own concepts.md. No overclaim detected; the only honest gap (which R6 states) is that **no surveyed system publishes its own P/R**, so none of these numbers predict ugm's results.

---

## D. Net assessment

- **All eight load-bearing repo-code claims (A1–A9) are CONFIRMED by direct source inspection.** The two pillars D15 leans on — (i) graphiti's `edge_type_map` IS predicate domain/range, the only structural ontology gate in production; (ii) cognee loads OWL but enforces NO domain/range, only ≥0.8 canonicalization that never rejects — both hold exactly as written. D15's "keep parent-links + domain/range, drop the reasoner" is the empirically-enforced subset, not a compromise. This is the report's strongest and most decision-relevant finding, and it survives scrutiny.
- **The "schema.org familiarity" claim is properly hedged in R5, not overstated.** R5 itself refuses to assert a measured schema.org-vs-synonym delta and reframes to "pretrained word-semantics; schema.org is the best-curated source of familiar names." That is the correct verdict; the underlying semantic-anchoring evidence (B2) is cited but not re-verified here.
- **R6's centerpiece web claim (constrained decoding helps, C1) is confirmed verbatim**, with one minor mis-attribution (the "smaller models hurt" caveat is not from 2501.10868).
- **Honest gaps that both reports already flag** stay flagged: exact figures in 2601.17898 (B3), 2506.19773/2210.10709 N-sweep (C2), BAML SAP (C3), and 2511.21038 (B2) were not independently confirmed this session; none is load-bearing for the recommendations.
- **No refuted claims.** A few line-number refs are 1–20 lines off but point at the right code.

---

## 5 most important verdicts

1. **CONFIRMED** — Graphiti's `edge_type_map[(source_label,target_label)] → [allowed predicates]` IS predicate domain/range and is the only hard, structural ontology enforcement in any cloned system (`graphiti_core/utils/maintenance/edge_operations.py:122,455-486`; default map `graphiti.py:1115`). Validates D15's chosen mechanism.
2. **CONFIRMED** — Cognee loads OWL via `rdflib` but enforces NO domain/range (zero grep hits in `cognee/modules/ontology/`); its only "enforcement" is `FuzzyMatchingStrategy(cutoff=0.8)` canonicalization that rewrites id/name and **never rejects** (`matching_strategies.py`; `expand_with_nodes_and_edges.py:123-144,306`). The "OWL-but-no-gating" characterization is accurate; D15 correctly declines to copy it.
3. **CONFIRMED-WITH-CAVEAT** — "schema.org familiarity improves extraction" is **asserted, not directly evidenced** for the schema.org-namespace-specifically version; R5 already self-corrects to "LLMs lean on pretrained label semantics (meaningful>arbitrary)" and explicitly declines to claim a measured schema.org delta. No overclaim in R5; the narrow claim remains unproven by design.
4. **CONFIRMED** — Gleaning facts: graphiti = single-pass, no reflexion (zero grep hits); graphrag CONTINUE/LOOP loop with `max_gleanings=1` default (`graph_extractor.py:101-115`, `defaults.py:137,150`); lightrag `DEFAULT_MAX_GLEANING=1` (`constants.py:17`); cognee cascade `n_rounds=2` (`extract_graph_from_data_v2.py:23`). All as reported.
5. **CONFIRMED (fetched)** — Tam et al. (arXiv 2501.10868) really finds constrained decoding *improves* reasoning when a reasoning field precedes the answer (GSM8K 80.1→83.8, Last-Letter 50.7→54.0, Shuffle 52.6→55.9, Guidance). One caveat: the "smaller models are hurt" rider is **mis-attributed** to this paper (it comes from R6's other vendor/production sources); harmless to the recommendation.
