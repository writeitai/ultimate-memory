# TY1 — WHEN/WHERE should entity typing happen in the ugm pipeline?

**Question.** Options: (a) at extraction time (the E2/E3 LLM proposes a type as it
extracts the mention, type as an enum field in the structured-output schema); (b) during
entity resolution; (c) a dedicated typing stage. Recommend the pipeline position with
rationale, and how the type menu (8 core + per-deployment extension/pack subtypes) is
supplied to the extractor. Tie to D17/D18 and the per-document chain (D12).

---

## 1. Key findings

1. **Every surveyed production KG system that types entities does so at extraction time,
   in the same LLM call, against a caller-supplied type menu rendered into the prompt** —
   Graphiti, LightRAG, GraphRAG all bind type inside the extraction structured output;
   none runs a separate "classify entities" stage in the normal path. Cognee types at
   extraction too (free-string). There is no production precedent for option (b)
   (typing during resolution) or a mandatory option (c) (dedicated typing stage). This is
   convergent evidence for **option (a) as the primary mechanism.**

2. **Domain/range enforcement (D18) is a hard ordering constraint: types must exist before
   the predicate gate can run.** Graphiti's own pipeline ordering proves this — nodes are
   extracted-and-typed first, resolved, *then* edges are extracted with the
   `edge_type_map[(src_type,tgt_type)→[rel]]` gate (`graphiti.py:617→621→656`; mirrored at
   `:1122→1131→1148`). The typed-mention is a precondition of the structural gate UGM adopts
   in D18. This rules out typing *after* relation extraction.

3. **The cleanest extract-time mechanism is a CLOSED enum / integer-ID type field in the
   structured-output schema, not a free string.** Graphiti forces an integer
   `entity_type_id` "must be one of the provided entity_type_id integers"
   (`extract_nodes.py:28-38`) with a system prompt that forbids out-of-list types; out-of-range
   IDs coerce to the reserved catch-all `Entity` (ID 0) (`node_operations.py:303-306`).
   Cognee/LightRAG/GraphRAG accept arbitrary free-text type strings, which silently reopens
   the type space and breaks any domain/range gate — the explicit AVOID for UGM. OpenAI-style
   structured-output enum constraints make the closed-set field a native, reliable capability.

4. **The type menu is supplied by RENDERING THE REGISTRY into the extraction prompt
   (= D18's "prompts render from the registry"), not hard-coded.** The active type set for a
   document = the 8 universal core types + the deployment's enabled extension-pack subtypes
   (Work pack `Task⊂Event, Decision⊂Event, Goal⊂Concept`, etc.) + scope extension types. Each
   is a registry row with a name, description, and examples; the extractor receives them as an
   enumerated label menu. This makes "defining a scope = editing rows," and the exact rendered
   menu is captured by prompt-version under the per-document chain (D12).

---

## 2. Evidence & detail with citations

### 2.1 Where production systems put typing (all = extraction time, same call)

- **Graphiti** — type is emitted by the extraction LLM as part of `ExtractedEntity`
  (`name: str`, `entity_type_id: int`, "Must be one of the provided entity_type_id integers")
  — `graphiti/graphiti_core/prompts/extract_nodes.py:28-38`. The prompt carries an
  `<ENTITY TYPES>` block and an explicit "Entity Classification" step (extract_nodes prompt,
  "Use the descriptions in ENTITY TYPES to classify each extracted entity. Assign the
  appropriate `entity_type_id`"). A standalone `classify_nodes` prompt *exists*
  (`extract_nodes.py:347-380`) but the normal inline path types at extraction; it is not a
  required separate stage. (repo_findings `graphiti_cognee.md` §GRAPHITI(a).)
- **LightRAG** — type assigned inside the single extraction call, same tuple as
  name+description; prompt: "Categorize the entity using the type guidance ... If none apply,
  classify it as `Other`" (`lightrag/lightrag/prompt.py:62`), guidance block injected at
  `prompt.py:117`. No post-hoc classifier, no ontology step.
  (repo_findings `lightrag_graphrag_gliner.md` §1(a).)
- **GraphRAG** — type assigned in the single extraction call, in the entity tuple
  `("entity"<|>name<|>type<|>description)`; `entity_type` = "One of the following types:
  [{entity_types}]" (`graphrag/.../prompts/index/extract_graph.py:11-15`).
  (repo_findings §2(a).)
- **Cognee** — extraction LLM emits `Node.type: str` (free string), ontology step only
  *canonicalizes the name* afterward — it does NOT decide the type
  (`cognee/.../shared/data_models.py:49-60`). Still extract-time typing, just unconstrained.
  (repo_findings `graphiti_cognee.md` §COGNEE(a)-(b).)
- **GLiNER** — types at inference in one cheap forward pass with a caller-supplied label
  list and a per-span confidence score (`model.predict_entities(text, labels, threshold)`,
  `GLiNER/gliner/model.py:2128,2249-2262,2279-2285`). It is the *extractor and the typer in
  one pass* — i.e. typing co-located with mention detection, the same architectural position
  as option (a), at a cheaper tier. (repo_findings §3.)

External confirmation: enum-constrained structured outputs turn each type field into a
per-mention classification done in-call, described as "cleaner than post-processing" for KG
construction (OpenAI structured-output entity extraction; ellmer structured-data docs —
see Sources).

**Verdict on (b) entity-resolution-time typing:** no surveyed system does this, and it is
architecturally wrong for UGM — resolution (D17) is mention→entity_id identity, deliberately
kept SEPARATE from typing (repo_findings AVOID notes: GraphRAG's `groupby(["title","type"])`
makes type part of identity and *forks* entities on type disagreement —
`graphrag/.../extract_graph.py:104-115` — directly contradicting D17/D21). Typing during
resolution would also be too late: resolution runs after mentions are extracted, but
domain/range (D18) needs the type already present on the mention.

### 2.2 The hard ordering constraint from D18

Graphiti's pipeline ordering is the verified precedent that types precede the predicate gate:

```
extract_nodes (TYPED)        graphiti.py:617    (and :1122)
  → resolve_extracted_nodes  graphiti.py:621    (and :1131)
    → extract_edges(edge_type_map)  graphiti.py:656  (and :1148)
      → resolve_extracted_edges(edge_type_map)  graphiti.py:669 (and :669/910)
```

`edge_type_map: dict[tuple[str, str], list[str]]` keys the allowed predicates by
*(source_type, target_type)* — so the endpoint types must already be assigned. This is exactly
the gate D18 adopts ("Enforce domain/range exactly as Graphiti's `edge_type_map[(src,tgt)→[rel]]`",
decisions.md:370). GLiREL embodies the same constraint at RE inference time with
`allowed_head`/`allowed_tail`, and is explicit that it *consumes* pre-assigned types
(`GLiREL/README.md:47,73-88`). Conclusion: **typing must complete before E3 relation
extraction / domain-range validation runs.** This forbids any "type later" option.

### 2.3 Closed enum vs free string

- Closed, list-bound: Graphiti integer ID + system prompt "NEVER assign types not listed"
  + out-of-range→`Entity` (`extract_nodes.py:30-33,348-351`; `node_operations.py:303-306`).
- Free string (AVOID): Cognee `type: str` no enum (`data_models.py:54`); LightRAG accepts any
  sanitized string verbatim (`operate.py:533-557`); GraphRAG `clean_str(...upper())` with no
  membership check (`graph_extractor.py:147`). repo_findings flags all three: "the 'fixed
  list' is a fiction and the type space silently drifts open ... UGM needs an explicit
  membership check / map-to-core step ... before D18 domain/range can be enforced."
- Modern structured-output enums (OpenAI/Anthropic tool-use / JSON-schema `enum`) make the
  closed field a first-class, reliably-honored capability — so UGM can use a true enum, not
  Graphiti's integer-ID workaround.

### 2.4 Supplying the menu = rendering the registry (D18, D12)

decisions.md D15/D18 and registries_design.md §4 already mandate "Prompts render from the
registry (types + predicates + descriptions + examples) — defining a scope is editing rows,
not prompt engineering; captured by prompt-version (D12)" (registries_design.md:139-140;
decisions.md:293-295). The per-document chain runs E0→E1→E2 per document (D12,
decisions.md:218), so the type menu rendered for a given document is the set active for that
deployment/scope at that prompt-version, and the prompt-version stamp records exactly which
menu was used (idempotent worker keyed by content hash + processing version). The menu =
8 core types (decisions.md:365) + enabled pack subtypes (Work pack, registries_design.md:156-162)
+ scope extension types, each declaring a core parent (extend-never-fork, D15).

---

## 3. Confidence & gaps

**Confidence: HIGH** that typing belongs at extraction time, in-call, against a registry-rendered
closed menu, before relation/domain-range. This is directly grounded in (i) 5/5 surveyed systems
typing at extraction, (ii) Graphiti's verified node-before-edge ordering enforcing the D18
precondition, and (iii) UGM's own D15/D18 "prompts render from the registry" decision.

**Verified facts:** the file:line citations above (Graphiti ordering and schema, LightRAG/GraphRAG
prompts/parsers, Cognee free-string, GLiNER per-span scoring, GLiREL allowed_head/tail) are read
from the cloned repos by the repo_findings analyses and spot-confirmed here
(`graphiti.py:617/621/656`, `extract_nodes.py:28-38`).

**Inference (not directly tested):**
- That a true JSON-schema `enum` will be honored as reliably as Graphiti's integer-ID trick is
  an inference from structured-output behavior, not measured on UGM's corpus. *Flag: validate
  enum-adherence rate on the golden set before trusting it as the sole gate.*
- Whether E2 (claim extraction) or a co-located mention/typing sub-step owns the type field is a
  UGM-internal design choice not settled by the surveyed systems (they collapse mention+type+edge
  into fewer calls than UGM's claim→relation split, D2).

**Gaps I could NOT verify:**
- No surveyed system runs a *post-hoc re-typing* pass for entities whose type only becomes clear
  later (repo_findings gap-note). UGM's merge-time reconciliation (below) is the closest analog,
  but there is no production evidence for an explicit re-typing stage — it would be net-new.
- No benchmark number is asserted for typing accuracy of any approach here; none was found and
  none is invented.

---

## 4. Recommendation for ugm

**Position: option (a) — type at extraction time, in-call, as a CLOSED-ENUM field — PLUS a
deterministic merge-time reconciliation, with the dedicated GLiNER tier as a cheaper variant of
(a), and an explicit re-type-on-supersession hook deferred.** Concretely:

1. **Primary mechanism (extract-time, in-call enum).** The E2 mention/claim extraction LLM
   emits each mention with a `type` field constrained to a JSON-schema `enum` rendered from the
   registry (the 8 core + enabled pack/scope subtypes + a reserved catch-all). This is
   Graphiti's STEAL pattern, upgraded from integer-ID to a true enum. The type is on the
   *mention*, carried into `mentions.type` and onto the entity (registries_design.md §2 data
   model: `entities.type → type registry`). **Type is NEVER part of the identity key** — keep it
   off resolution (D17), avoiding GraphRAG's identity-forking bug (decisions.md/D21
   reversibility). *(Ties D17: identity and type are orthogonal; D18: provides the typed mention
   the domain/range gate requires.)*

2. **Reserved catch-all so typing is a TOTAL function before D18 runs.** Add a reserved fallback
   type (UGM-natural = `Concept`, the core parent via `related_to`, or an explicit `other`/
   `UNKNOWN` bucket) so no mention reaches relation extraction untyped — mirroring Graphiti's
   ID-0 `Entity` (`node_operations.py:156-169,303-306`) and LightRAG's `Other` (`prompt.py:62`).
   GLiNER silently drops sub-threshold spans, so this bucket must be explicit. This closes the
   gap D17 leaves open (typing currently unspecified) without ever blocking the D18 gate.

3. **Menu supplied by registry rendering (D18, D12).** Render `entity_types` rows
   (name + description + examples, each with a declared core parent) into the extraction prompt
   as the enum; the active menu = 8 core + the deployment's enabled extension packs
   (registries_design.md §4) + scope extension types. The exact rendered menu is captured by
   prompt-version under the per-document E0→E2 chain (D12), idempotent on content_hash +
   processing/resolver version. No prompt engineering to add a type — it is a registry row.

4. **Cheap typing tier (variant of (a), per D17/D22 economics).** Offer GLiNER as an optional
   sub-LLM typing tier: pass the same registry menu as the zero-shot label list, get a per-span
   `score` (`GLiNER/gliner/model.py:2279-2285`) thresholded against the golden set — the only
   surveyed system giving a real per-assignment type confidence, mirroring D17's golden-set-tuned
   cascade and D22's per-type P/R discipline. *(Ties D22: type thresholds, like resolution
   thresholds, ship only with a golden-set curve; ties D17's cheap→frontier escalation shape.)*

5. **Merge-time reconciliation (deterministic, monotonic).** Mention-level types collapse to
   entity-level on resolution. Adopt Graphiti's **monotonic generic→specific promotion** rule
   (`dedup_helpers.py:170-189`): never downgrade a specific type to the catch-all; upgrade when a
   more specific mention arrives. (LightRAG's majority-vote, `operate.py:1671-1674`, is the
   alternative if mentions genuinely conflict among specific types.) This is reversible state
   living only in Postgres (D21: `resolution_decisions`/`merge_events`), re-pointed for free on
   P2 rebuild (D7). *(Ties D21: type reconciliation is an append-only, reversible decision, not a
   destructive rewrite — answers the "type-on-merge" question the D17 cascade leaves open.)*

6. **Defer, do not build now: post-hoc re-typing on supersession.** No production precedent
   exists; treat a later type correction as an ordinary reversible re-adjudication
   (re-extract / promote on new evidence) under D21/D7 rather than a standing stage. Flag as an
   open spike if golden-set monitoring shows material mis-typing that only later context fixes.

**Net:** typing is option (a) at E2 extraction, enum-constrained from the registry, with a
reserved catch-all guaranteeing a typed mention before the D18 domain/range gate; reconciled
monotonically at merge (D21) and tuned on the golden set (D22) — leaving D17 identity untouched.

## Sources

- repo_findings: `entity_typing_research/repo_findings/graphiti_cognee.md`,
  `entity_typing_research/repo_findings/lightrag_graphrag_gliner.md`
- Cloned repos under `_additional_context/`: `graphiti/graphiti_core/graphiti.py:617,621,656,1122,1131,1148`;
  `graphiti/graphiti_core/prompts/extract_nodes.py:28-38,347-380`;
  `graphiti/graphiti_core/utils/maintenance/node_operations.py:156-169,303-306`;
  `graphiti/graphiti_core/utils/maintenance/dedup_helpers.py:170-189`;
  `lightrag/lightrag/prompt.py:62,117`; `lightrag/lightrag/operate.py:533-557,1671-1674`;
  `graphrag/.../prompts/index/extract_graph.py:11-15`;
  `graphrag/.../operations/extract_graph/graph_extractor.py:147`, `extract_graph.py:104-115`;
  `cognee/cognee/shared/data_models.py:49-60`; `GLiNER/gliner/model.py:2128,2249-2262,2279-2285`;
  `GLiREL/README.md:47,73-88`
- Design/decisions: `plan/designs/registries_design.md` §2,§4; `decisions.md` D2,D5,D12,D15,D17,D18,D21,D22
- [Custom Entity and Edge Types | Zep Documentation](https://help.getzep.com/graphiti/core-concepts/custom-entity-and-edge-types)
- [Entity extraction using OpenAI structured outputs mode](http://blog.pamelafox.org/2024/11/entity-extraction-using-openai.html)
- [Structured data • ellmer](https://ellmer.tidyverse.org/articles/structured-data.html)
