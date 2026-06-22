# Entity Typing: Graphiti & Cognee (repo findings)

Subject: HOW does each system assign a TYPE (Person/Org/Concept/...) to an entity?
All paths relative to `/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/`.

---

## GRAPHITI

### (a) Where/when the type is assigned

Type is assigned **during extraction, in the same LLM call** that produces the entity
(not a separate post-hoc classifier in the normal path). The extraction prompt emits a
typed entity directly:

- `graphiti/graphiti_core/prompts/extract_nodes.py:28-38` — the LLM response schema
  `ExtractedEntity` has `name: str` and `entity_type_id: int` ("ID of the classified entity
  type. Must be one of the provided entity_type_id integers."). Typing is forced into the
  extraction schema — the model picks an integer ID, not a free string.
- The extraction prompts (`extract_message` :150-153, `extract_json` :236, `extract_text`
  :304) all carry an `<ENTITY TYPES>` block (`context['entity_types']`) and an explicit
  "Entity Classification" step: "Use the descriptions in ENTITY TYPES to classify each
  extracted entity. Assign the appropriate `entity_type_id` for each one."
- The ID→label mapping is built in `node_operations.py:152-181`
  (`_build_entity_types_context`): index `0` is always reserved for the built-in `'Entity'`
  type; user-supplied custom types get IDs `i+1`, their description taken from the Pydantic
  model's `__doc__` (`:176`).
- The ID is resolved back to a label name and attached as Neo4j **labels** in
  `node_operations.py:283-333` (`_create_entity_nodes`): `type_id =
  extracted_entity.entity_type_id`; `entity_type_name = entity_types_context[type_id]...`
  then `labels: list[str] = list({'Entity', str(entity_type_name)})` (`:302-313`). So every
  node carries `Entity` plus at most one specific type label.
- A standalone classifier prompt **does exist** — `extract_nodes.py:347-380`
  (`classify_nodes`: "Each entity must have exactly one type… If none of the provided entity
  types accurately classify an extracted entity, the type should be set to None.") — and is
  declared in the `Prompt`/`Versions` protocols, but in the inline-typing path the type is
  already set at extraction time. (Type lives on `node.labels`; `nodes.py:97`,
  `EntityNode` at `nodes.py:499-503`.)

### (b) Type inventory: fixed list? open? default fallback?

- **Configurable closed set, not open/zero-shot.** Types are caller-supplied Pydantic models
  (`entity_types: dict[str, type[BaseModel]] | None`); the LLM may ONLY choose among the
  provided integer IDs. System prompts hard-enforce this: classify_nodes system prompt =
  "NEVER assign types not listed in ENTITY TYPES" (`extract_nodes.py:348-351`).
- **Default/fallback = the built-in `'Entity'` type** (ID 0), always present even when the
  caller passes no custom types (`node_operations.py:156-169`). Its description explicitly
  frames it as the catch-all: "A specific, identifiable entity that does not fit any of the
  other listed types."
- Out-of-range / invalid IDs also fall back to `'Entity'`: `node_operations.py:303-306`
  (`if 0 <= type_id < len(...): ... else: entity_type_name = 'Entity'`).

### (c) Entities that fit no type

They become bare `Entity` (label `['Entity']` only). No drop, no error.
- classify_nodes prompt instructs "type should be set to None" → maps to bare `Entity`
  (`extract_nodes.py:375`).
- There is also an opt-in **drop** mechanism, but keyed on type NAME, not on
  "untyped-ness": `excluded_entity_types` — `node_operations.py:308-311`, if the resolved
  type name is in the excluded list the node is skipped entirely.

### (d) Mention-level vs entity-level + type-reconciliation-on-merge

- Typing is **mention-level at extraction** (each extracted occurrence gets a type),
  collapsed to entity-level by dedup.
- **Same-message exact-dup collapse** prefers the MORE specific type:
  `node_operations.py:336-384` (`_collapse_exact_duplicate_extracted_nodes`) keeps the node
  with more non-`Entity` labels (`:363-368`).
- **Merge against existing graph node — "type promotion":**
  `graphiti_core/utils/maintenance/dedup_helpers.py:170-189` (`_promote_resolved_node`):
  if the canonical/resolved node is still generic (only `Entity`) and the newly extracted
  duplicate carries a specific label, the canonical node is **upgraded** to the specific
  type (`resolved_node.labels = promoted_labels`). A specific type is never downgraded back
  to `Entity`. This is the explicit type-on-merge reconciliation rule: generic→specific,
  monotonic.
- Edge endpoints also union labels on resolution: `graphiti.py:1689-1692`
  (`resolved_source.labels = list(set(resolved_source.labels) | set(source_node.labels))`).

### (e) Confidence / validation on the type

- **No numeric confidence score** on the type. Validation is structural only:
  - Schema-side: the LLM must return a valid integer ID (Pydantic) and the system prompt
    forbids out-of-list types.
  - Out-of-range IDs silently coerced to `Entity` (`node_operations.py:303-306`).
  - Type-model field-name validation: `utils/ontology_utils/entity_types_utils.py:23-37`
    (`validate_entity_types`) raises `EntityTypeValidationError` if a custom entity-type
    model declares a field that collides with a built-in `EntityNode` field — protects
    attribute extraction, not the type assignment per se.
  - Label safety: `nodes.py:102-105` + `helpers.py:174-181` validate that labels are safe
    Cypher identifiers.
- Domain/range relevance: at merge/dedupe the type description is fed to the LLM as context
  (`node_operations.py:184-189` `_get_entity_type_description`, used at `:493`) but this
  informs dedup, not a type-confidence.

---

## COGNEE

### (a) Where/when the type is assigned

Type is assigned by the **extraction LLM as a free-form string field**, then an ontology
match step only **canonicalizes/validates the name** — it does NOT decide or constrain the
type.

- The LLM emits a `KnowledgeGraph` whose `Node` has `type: str`
  (`cognee/cognee/shared/data_models.py:49-60`) — a plain required string, NO enum, NO
  constraint. (`extract_content_graph.py:13-37` runs the structured-output call against this
  model.)
- The graph extraction prompt (`cognee/cognee/infrastructure/llm/prompts/
  generate_graph_prompt.txt`) only *suggests* coarse types in prose: "when you identify an
  entity representing a person, always label it as **Person**… Avoid… 'Mathematician'…
  Don't use too generic terms like 'Entity'… a date → type **Date**." It is **open / zero-shot**
  — the model invents the type string; there is no provided list it must choose from.
- Each `node.type` string is turned into an `EntityType` node and linked to the `Entity`
  via `is_a`: `cognee/cognee/modules/graph/utils/expand_with_nodes_and_edges.py:218-258`
  (`_process_graph_nodes` calls `_create_type_node(node.type, ...)` then `_create_entity_node(
  ..., type_node, ...)` which sets `is_a=type_node` at `:198-207`).
- Data models: `cognee/cognee/modules/engine/models/Entity.py:7-12` (`is_a:
  Optional[EntityType] = None`) and `EntityType.py:6-10` (just `name`/`description`). Type is
  an entity-level node, not just a label string.

### (b) Type inventory: fixed? open? default fallback?

- **Open / zero-shot.** No fixed inventory; whatever string the LLM produces becomes an
  `EntityType`. The ontology (if loaded) is a *reference vocabulary for canonicalization*,
  not a closed type list. With no ontology file configured, a default empty resolver is used
  (`cognee/cognee/modules/ontology/get_default_ontology_resolver.py:6-7`,
  `RDFLibOntologyResolver(ontology_file=None, matching_strategy=FuzzyMatchingStrategy())`);
  with `graph=None`, lookups are empty (`RDFLibOntologyResolver.py:118-129`,
  `build_lookup`), so `get_subgraph` returns no match and the LLM string is kept verbatim.
- **No default fallback type.** `is_a` is `Optional` (`Entity.py:9`); there is no
  catch-all "Entity" type — an unmatched type simply stays as the raw LLM string.

### (c) The ~0.8 fuzzy cutoff, unmatched handling, default typing

- The fuzzy match lives in `cognee/cognee/modules/ontology/matching_strategies.py:23-53`
  (`FuzzyMatchingStrategy`): `__init__(self, cutoff: float = 0.8)` (`:26`), and
  `find_match` does exact-match-first then `difflib.get_close_matches(name, candidates,
  n=1, cutoff=self.cutoff)` (`:48-53`). 0.8 is the default difflib SequenceMatcher ratio
  threshold. This is a **string-similarity** match against ontology class/individual names —
  it canonicalizes the *name*, it does not classify into a type taxonomy.
- Names are normalized before matching: lowercase, spaces→underscores
  (`RDFLibOntologyResolver.py:110-116` `_uri_to_key`, `:159-167` `find_closest_match`).
- **Unmatched type (below 0.8 / no ontology):** the type is STILL created as an
  `EntityType` node — it is just flagged `ontology_valid=False`.
  `expand_with_nodes_and_edges.py:101-154` (`_create_type_node`):
  `ontology_nodes, ontology_edges, closest_class = ontology_resolver.get_subgraph(
  node_name=node_name, node_type="classes")` (`:123`); `ontology_validated =
  bool(closest_class)` (`:127`). If matched, the node id/name are **rewritten to the
  canonical ontology class name** (`:129-137`). Either way an `EntityType(... type=node_name,
  ontology_valid=ontology_validated ...)` is built (`:139-146`). So a sub-0.8 type is kept
  with its raw LLM string and `ontology_valid=False`.
- The same flow applies to the **entity** name itself (`_create_entity_node`, `:157-215`,
  `node_type="individuals"`): ontology match canonicalizes the entity name and sets
  `ontology_valid`, independent of typing.
- `get_subgraph` returns `([], [], None)` when no close match (`RDFLibOntologyResolver.py:
  186-190`), which is what drives `ontology_validated=False`.

### (d) Mention-level vs entity-level + reconciliation-on-merge

- The LLM types each extracted node (mention-level). Within a chunk-batch, dedup is by
  generated node id (name-derived): `expand_with_nodes_and_edges.py:113-120` and
  `:172-179` short-circuit if the `*_type` / `*_entity` key already exists in
  `added_nodes_map`/`key_mapping`. Ontology canonicalization (`name_mapping`/`key_mapping`,
  `:135-137`, `:194-196`) collapses surface variants onto the same canonical node so a later
  identical type/entity reuses the existing one.
- **No type-conflict reconciliation logic.** First-writer-wins per canonical key; there is
  no "specific beats generic" promotion (contrast Graphiti). If two mentions assign different
  type strings that normalize to different ids, they become two separate `EntityType` nodes /
  two `is_a` edges; nothing merges or arbitrates them.

### (e) Confidence / validation on the type

- **No numeric confidence on the type.** The only validation signal is the boolean
  `ontology_valid` flag on the `EntityType`/`Entity`/edge nodes
  (`expand_with_nodes_and_edges.py:144`, `:203`, `:94`, `:306`). It records "did this match
  an ontology term ≥0.8", not a probability. Edges from LLM extraction are always
  `ontology_valid=False` (`:306`); only ontology-derived edges get `True` (`:94`).
- **No domain/range enforcement.** Cognee loads OWL `is_a`/`subClassOf`/`ObjectProperty`
  structure for *subgraph expansion* (`RDFLibOntologyResolver.py:203-242`) but never checks
  predicate subject/object types against it. (Confirms decisions.md D18 context: "Cognee
  loads OWL but enforces no domain/range.")

---

## STEAL vs AVOID for UGM (re: D18 8-type core + domain/range; the typing gap)

**STEAL (Graphiti):**
- **Type-in-the-extraction-schema against a closed integer-ID list** (`ExtractedEntity.
  entity_type_id`, `extract_nodes.py:30-33`). This is the single cleanest way to get a
  *known, bounded* type the moment a mention is extracted — exactly what D18 domain/range
  enforcement requires (a predicate gate needs `subject_type`/`object_type` to already be one
  of the 8 core types). Map UGM's 8-type core (Person, Organization, Place, Document, Event,
  Concept, Project, Product) to IDs 1–8, ID 0 = catch-all `Concept`/`Entity`.
- **A reserved catch-all type with a "fits no other type" description** (ID 0 `'Entity'`,
  `node_operations.py:156-169`) + **out-of-range coercion to it** (`:303-306`). Gives a
  total function mention→type with no drops — fills the gap that D17 (identity) leaves open
  (typing is currently unspecified). UGM's natural catch-all is `Concept` (D18 core parent
  via `related_to`).
- **Monotonic generic→specific type promotion on merge** (`dedup_helpers.py:170-189`).
  A principled, cheap reconciliation rule for entity-level typing once mentions merge: never
  downgrade, upgrade when a more specific mention arrives. Directly answers UGM's
  "type-reconciliation-on-merge" question, which D17's resolution cascade does not address.
- **`excluded_entity_types`** drop hook (`node_operations.py:308-311`) — useful for D21
  reversibility / golden-set tuning to suppress noisy types per deployment.

**AVOID (Cognee):**
- **Free-string, zero-shot `type` with no enum** (`data_models.py:54`). This is precisely
  what breaks D18: domain/range can't be enforced when types are an unbounded string space
  (`works_for: Person→Organization` is meaningless if "type" can be "Mathematician",
  "ceo", "the_company"). UGM must constrain to the core set at extraction, not post-hoc.
- **Treating string-similarity name-matching as typing** (the 0.8 difflib cutoff,
  `matching_strategies.py:52`). It canonicalizes a *surface name*, not a *type*. Borrowing it
  for typing would conflate identity-resolution (D17's job) with type assignment (the gap) —
  keep these separate per the UGM design split.
- **`ontology_valid` boolean as the only type signal + no reconciliation** (first-writer-
  wins, no specific-beats-generic). Conflicting type strings silently fork into parallel
  `EntityType` nodes — the opposite of D18's controlled 8-type core and D15 extend-never-fork.
- **OWL loaded but domain/range unenforced** — confirms D18's stance: take Graphiti's
  `edge_type_map[(src,tgt)→[rel]]` gate, not Cognee's decorative ontology.

**Gap-closing note:** Neither system specifies a *post-hoc re-typing* pass for entities whose
type only becomes clear later; both type at extraction. For UGM, Graphiti's
extract-time-typing + merge-time promotion is the closest validated pattern to bolt onto the
D17 cascade, with `Concept` as the reserved fallback so a mention is never left untyped before
predicate domain/range (D18) runs.
