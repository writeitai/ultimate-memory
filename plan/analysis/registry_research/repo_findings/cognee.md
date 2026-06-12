# Cognee — code archaeology (topoteretes/cognee)

Repo root: `/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/cognee/`
Focus: ontology matching/validation, entity description consolidation, temporal_awareness.
Everything below is cited to actual source. Where the code does not implement a thing, it says **not found**.

---

## 1. Entity resolution / dedup — how it decides same-vs-different

**The decisive mechanism is fully deterministic: a UUIDv5 hash of the normalized name.** There is
no similarity threshold, no embedding compare, and no LLM call in the actual same-vs-different
decision. Two mentions are "the same entity" iff their normalized names produce the same UUID.

`cognee/infrastructure/engine/utils/generate_node_id.py` (the whole file):
```python
from uuid import NAMESPACE_OID, UUID, uuid5

def generate_node_id(node_id: str) -> UUID:
    return uuid5(NAMESPACE_OID, node_id.lower().replace(" ", "_").replace("'", ""))
```
Name normalization (`cognee/modules/engine/utils/...`):
```python
def generate_node_name(name: str) -> str:
    return name.lower().replace("'", "")
def generate_edge_name(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "")
```
So normalization is only: lowercase, strip spaces (id only), strip apostrophes. "Alice Novak" and
"A. Novak" → different UUIDs → **different entities, silently**. "Apple" the company and "apple"
the fruit → same UUID → **wrongly merged**. No type is mixed into the id hash; node identity is
name-only. (Node keys carry a category suffix only inside one extraction batch — see below.)

**Dedup within a cognify batch** — `cognee/modules/graph/utils/expand_with_nodes_and_edges.py`:
- `_create_node_key(node_id, category) = f"{node_id}_{category}"` (categories: `"entity"`, `"type"`).
- `added_nodes_map` / `added_ontology_nodes_map` are plain dicts keyed by that string; first writer
  wins, later identical keys are skipped (`if entity_node_key in added_nodes_map: return ...`).
- Edge dedup key: `_create_edge_key = f"{source_id}_{target_id}_{relationship_name}"`.

**Dedup against the existing graph** — `cognee/modules/graph/utils/retrieve_existing_edges.py`:
queries the graph engine with `graph_engine.has_edges([...])` to see which `(src, tgt, rel)` triples
already exist, builds `existing_edges_map`, and `expand_with_nodes_and_edges` skips those. This is an
**exact-key existence check** (edges only); nodes coalesce purely because `uuid5(name)` collides.

**Final dedup pass** — `cognee/modules/graph/utils/deduplicate_nodes_and_edges.py`: dedup nodes by
`str(node.id)`, edges by `str(src)+rel+str(tgt)`. Again exact-id, no fuzziness.

> Net: cross-document entity resolution in cognee is **string-identity only**. The fuzzy/threshold
> matching (§3) applies *only* to mapping an extracted name onto a user-supplied OWL ontology, not to
> general mention-to-mention resolution. This matches `entity_registry.md` §2's note: "Cross-document
> ER itself is shallow there — threshold similarity only."

**Importance / merge bookkeeping is a TODO, not implemented.** In `expand_with_nodes_and_edges.py`
`_create_entity_node`:
```python
# TODO add importance_weight calculation if an entity with that id already exits
importance_weight=data_chunk.importance_weight,
```
`DataPoint` (`cognee/infrastructure/engine/models/DataPoint.py`) carries `version: int = 1`,
`created_at`, `updated_at`, `ontology_valid: bool = False`, `importance_weight: float | None = 0.5`,
`belongs_to_set`, and an `update_version()` that does `self.version += 1`. There is **no `merged_into`
redirect, no un-merge, no split** anywhere in the registry.

## 2. Coreference handling

**Prompt-only; no algorithmic coref.** The graph-extraction system prompts instruct the LLM to
canonicalize references inside a single chunk. `cognee/infrastructure/llm/prompts/generate_graph_prompt.txt`,
§3 "Coreference Resolution":
> "If an entity is mentioned multiple times in the text but is referred to by different names or
> pronouns, always use the most complete identifier for that entity throughout the knowledge graph."

`generate_graph_prompt_strict.txt` is stronger: "Resolve all references (including pronouns, aliases,
short names) to their canonical form. Example: 'he', 'Dr. Turing' → 'Alan Turing'" and "Ensure all
mentions referring to the same entity point to the **same node**."

This is **intra-chunk, LLM-best-effort** coref. There is no cross-chunk/cross-document coref pass, no
mention table, no pronoun resolver. A dedicated `fastcoref`/`maverick-coref` style component is
**not found** in cognee.

## 3. Ontology / type system — definition, validation, enforcement

Module: `cognee/modules/ontology/`. The ontology is an external **OWL/RDF XML file** loaded by
`RDFLibOntologyResolver` (`rdf_xml/RDFLibOntologyResolver.py`) via `rdflib`. The user supplies it; the
system ships none beyond test fixtures.

**Lookup build** (`build_lookup`): walks the RDF graph and indexes two buckets only —
`classes` (subjects of `RDF.type OWL.Class`) and `individuals` (subjects whose `RDF.type` is one of
those classes). Keys are URI fragments normalized via `_uri_to_key` (split on `#` or last `/`,
lowercase, spaces→`_`).

**Matching** — `cognee/modules/ontology/matching_strategies.py`, `FuzzyMatchingStrategy`:
```python
def __init__(self, cutoff: float = 0.8):
    self.cutoff = cutoff
def find_match(self, name, candidates):
    if name in candidates: return name          # exact first
    best = difflib.get_close_matches(name, candidates, n=1, cutoff=self.cutoff)
    return best[0] if best else None
```
**The concrete threshold is `cutoff=0.8`** (Python `difflib.SequenceMatcher` ratio), `n=1`. Exact
match short-circuits. CLAUDE.md documents the default as `MATCHING_STRATEGY=fuzzy` "fuzzy matching with
80% similarity". Env config (`ontology_env_config.py`): `ontology_resolver="rdflib"`,
`matching_strategy="fuzzy"`, `ontology_file_path=""`.

**Only one resolver and one strategy are wired.** `get_default_ontology_resolver.py` →
`get_ontology_resolver_from_env` raises `EnvironmentError` unless
`ontology_resolver=="rdflib" and matching_strategy=="fuzzy"`. Multiple OWL files supported via
comma-split paths.

**How validation/enforcement actually works** (`expand_with_nodes_and_edges.py`):
- For each extracted node, `_create_type_node` calls `ontology_resolver.get_subgraph(node_name, node_type="classes")`; `_create_entity_node` calls it with `node_type="individuals"`.
- If a close (≥0.8) match is found, the node is **canonicalized**: its id/name are *replaced* by the
  ontology term's name (`generate_node_id(closest_class.name)`), a `name_mapping`/`key_mapping` entry is
  recorded so later edges retarget the canonical node, and `ontology_valid=True` is set.
- The matched ontology subgraph (parents via `RDFS.subClassOf`, `RDF.type`, and `OWL.ObjectProperty`
  edges) is pulled in as extra `EntityType`/`Entity` nodes and `is_a`/property edges
  (`_process_ontology_nodes`, `_process_ontology_edges`). These carry `ontology_valid=True`.
- If no match: node is kept as-is with `ontology_valid=False`. **Nothing is rejected.** The ontology
  *enriches and canonicalizes*; it does not gate extraction.

**Domain/range enforcement: not found.** `get_subgraph` reads `OWL.ObjectProperty` triples that already
exist between named individuals in the OWL file, but there is no check that an extracted predicate's
subject/object types satisfy `rdfs:domain`/`rdfs:range`. Predicate names from the LLM are free-form
(snake_cased), not validated against the ontology. The ontology extraction prompt
(`extract_ontology.txt`) only says "Relationships can't be empty, and have to be logical AND CONNECTING
NODES" and "The source is the parent of the target."

`get_subgraph` BFS is bounded by `directed=True` default (only outgoing object-property edges); the
traversal walks `is_a`/subclass chains and object properties until the queue drains.

## 4. Extraction — prompting & constraints

**Structured output via Instructor/BAML, Pydantic response models — not free-form, not a grammar.**
CLAUDE.md: `STRUCTURED_OUTPUT_FRAMEWORK="instructor"` (default, via litellm) or `"baml"`;
`LLM_INSTRUCTOR_MODE` defaults per-model (e.g. `json_schema_mode` for gpt-4o). Default model
`openai/gpt-4o-mini`.

**The graph schema** (`cognee/shared/data_models.py`, `KnowledgeGraph`):
```python
class Node(BaseModel):
    id: str; name: str = ""; type: str; description: str
    # __init__: if no name, name := id
class Edge(BaseModel):
    source_node_id: str; target_node_id: str; relationship_name: str
    description: str | None  # "Concrete one-sentence fact ... using endpoint names."
class KnowledgeGraph(BaseModel):
    nodes: list[Node]; edges: list[Edge]
```
(A separate Gemini-only variant adds a `label` field because "Gemini doesn't allow an empty dictionary
to be part of the data model.") After extraction, edges whose `source_node_id`/`target_node_id` aren't in
the node set are dropped (`extract_graph_from_data.py`):
```python
valid_node_ids = {node.id for node in graph.nodes}
graph.edges = [e for e in graph.edges if e.source_node_id in valid_node_ids and e.target_node_id in valid_node_ids]
```

**Prompt constraints** (`generate_graph_prompt.txt` / `_strict.txt`): basic atomic node types
("Person", not "Mathematician" → put as `profession` property); never integer node IDs; snake_case
relationship + property names; dates as `YYYY-MM-DD`; "Do not add outside knowledge" / "Do not
hallucinate"; the strict variant gives a fixed type vocabulary (Person/Organization/Location/Date/
Event/Work/Concept). Prompt ends with "Non-compliance will result in termination" (single-pass default).

**Single vs multi-pass gleaning — both exist:**
- Default `extract_graph_from_data.py` → `extract_content_graph(chunk.text, graph_model)` once per chunk
  (single pass, parallel over chunks).
- **Cascade / multi-round** `extract_graph_from_data_v2.py`, default `n_rounds=2`: three sequential
  LLM stages — `extract_nodes` → `extract_content_nodes_and_relationship_names` → `extract_edge_triplets`.
  `extract_nodes` (`cascade_extract/utils/extract_nodes.py`) loops `for round_num in range(n_rounds)`,
  feeding `previous_nodes` back each round and deduping by `node.lower()` — this is the actual
  "gleaning" loop. Both paths converge on `integrate_chunk_graphs` (→ ontology validation + storage).

**Entity-only extraction** (`extract_entities_system.txt`) demands strict JSON:
> "Your response MUST be a valid JSON object with a single field 'entities' ... Do not include any
> explanatory text, markdown formatting, or code blocks." Each entity has `name`, `is_a {name, description}`
> (TYPE in uppercase), `description` (1-2 sentences).

## 5. Entity description consolidation

`cognee/memify_pipelines/consolidate_entity_descriptions.py` — runs as a `memify` pipeline
(extraction task `get_entities_with_neighborhood` → enrichment tasks
`generate_consolidated_entities`, `add_data_points`).

- `get_all_entity_nodes`: `graph_engine.get_filtered_graph_data([{"type": ["Entity"]}])` — every Entity.
- For each entity, fetch edges + neighbors, build a neighborhood prompt
  (`build_node_neighborhood_prompt`): "This node's description is the following: {name} - {description}.
  It is connected to its neighbors in the following way: \n- {edge_label}: {neighbor_name} - {neighbor_desc}".
- LLM call with system prompt `consolidate_entity_details.txt`, response model `NodeDescription{description:str}`:
  > "You are a top-tier summarization engine. ... Be brief and concise, but keep the important
  > information and the subject. Use synonym words where possible in order to change the wording but
  > keep the meaning. You are to use description provided in the node, as well as data about its
  > neighbors and edges connecting them."
- Rebuilds the `Entity` with the same id/name/type but the **new consolidated description**, then
  `add_data_points` re-stores it (overwrites by id). This is a global, LLM-per-entity rewrite of
  descriptions using 1-hop neighborhood context. It does **not** merge entities or change identity —
  only the free-text `description`.

## 6. Temporal / bi-temporal model

**Two distinct temporal subsystems; neither is true bi-temporal with supersession/invalidation.**

(a) `cognee/tasks/temporal_awareness/` — **delegates to external Graphiti.**
`build_graph_with_temporal_awareness.py` instantiates `graphiti_core.Graphiti(url, "neo4j", password)`
and calls `graphiti.add_episode(name=..., episode_body=text, source=EpisodeType.text,
reference_time=datetime.now(timezone.utc))`. Validity windows / edge invalidation live in Graphiti, not
cognee. `GraphitiNode` (`graphiti_model.py`) is just `content/name/summary`. Requires Neo4j + the
`graphiti` extra.

(b) `cognee/tasks/temporal_graph/` — **cognee-native event extraction** (point/interval times, no
invalidation). `models.py`:
```python
class Timestamp(BaseModel):  # year required (ge=1,le=9999); month/day default 1; h/m/s default 0
class Interval(BaseModel): starts_at: Timestamp; ends_at: Timestamp
class Event(BaseModel): name; description; time_from: Timestamp|None; time_to: Timestamp|None; location
```
The persisted `Event` DataPoint (`cognee/modules/engine/models/Event.py`) has `at: Timestamp|None`,
`during: Interval|None`, `location`, `attributes`. `extract_events_and_entities.py` LLM-extracts an
`EventList` per chunk; `add_entities_to_event.py` attaches entities (via the same `generate_node_id`
dedup) with relationship edges.

**Query-time temporal retrieval** — `cognee/modules/retrieval/temporal_retriever.py`
(`TemporalRetriever extends GraphCompletionRetriever`): LLM extracts a `QueryInterval` from the query
(`extract_query_time.txt`, `QueryInterval{starts_at?, ends_at?}`), then
`graph_engine.collect_time_ids(time_from=, time_to=)` → `collect_events(ids=)`, ranks by vector
similarity over `Event_name`, returns `top_k` (default **5**; `wide_search_top_k=100`;
`triplet_distance_penalty=6.5`). If no time is parsed, falls back to plain triplet search.

> There is **no `valid_from/valid_to/invalidated_at` supersession** in cognee-native code, and **no
> transaction-time vs valid-time split**. Times are descriptive event attributes, not assertion-validity
> windows. (Contrast `decisions.md` D10: ugm does bi-temporal as-of filtering over four temporal columns.)

## 7. Clustering / merge / un-merge

- **Clustering:** no entity-resolution clustering. The only "clustering" is community detection, which
  CLAUDE.md says "runs externally"; not part of the ontology/registry path. No transitive-closure
  union-find over candidate matches — **not found**.
- **Merge:** implicit only — two extractions with the same normalized name land on the same UUID, so
  their edges accumulate on one node. There is no explicit merge operation, no merge-event log, no
  evidence record of *why* two things merged.
- **Un-merge / split / reversibility:** **not found.** No `merged_into`, no redirect chain, no
  pre-merge snapshot. `DataPoint.update_version()` bumps a version int but stores no history and supports
  no rollback. Once two real entities collide on a name hash, untangling them requires re-extraction.

## 8. Concrete numbers / model choices / benchmarks

- Ontology fuzzy-match cutoff: **0.8** (`FuzzyMatchingStrategy.cutoff`, `difflib`).
- Cascade extraction rounds: **`n_rounds=2`** default.
- Default LLM: **`openai/gpt-4o-mini`**; instructor mode `json_schema_mode` for gpt-4o family.
- Default `importance_weight=0.5`; `DataPoint.version` starts at 1.
- Temporal retriever: `top_k=5`, `wide_search_top_k=100`, `triplet_distance_penalty=6.5`.
- `Timestamp` bounds: year 1–9999, month 1–12, day 1–31, hour 0–23, min/sec 0–59; defaults month/day=1, h/m/s=0.
- Default DBs: graph=Ladybug, vector=LanceDB, relational=SQLite (CLAUDE.md).
- Rate-limit defaults: 60 requests / 60 s.
- Accuracy / benchmark figures **in the inspected code: not found** (eval framework exists under
  `cognee/eval_framework/` but no published numbers in these files). Research paper linked in CLAUDE.md:
  arxiv 2505.24478 — content not in repo.

---

## 9. Steal vs avoid (for ugm)

**Steal:**
1. **Ontology anchoring as a canonicalization tier, not a gate.** `expand_with_nodes_and_edges` matches
   an extracted name to a curated authority (OWL classes/individuals) at ≥0.8 and *rewrites id+name to
   the canonical term*, flagging `ontology_valid`. This is exactly the "anchor outward to authority sets"
   idea behind ugm D15 / resolution tier 0 — and crucially it never rejects, only enriches. Worth copying:
   the `name_mapping`/`key_mapping` retarget so downstream edges follow the canonical node.
2. **Deterministic-first identity for the trivial case.** `uuid5(NAMESPACE_OID, normalized_name)` gives a
   free, replayable exact-match tier. ugm can keep this as resolution tier 1 (cheap-first cascade, D4) —
   but must *not* let it be the whole resolver.
3. **Edge existence pre-check** (`retrieve_existing_edges` + `has_edges` batch) to make incremental
   ingestion idempotent on `(s,p,o)` — aligns with ugm's relation dedupe by `(s,p,o)` (D2).
4. **Cascade gleaning** (`n_rounds`, feed previous nodes back) as a quality knob for recall.
5. **Neighborhood-aware description consolidation** (`consolidate_entity_descriptions`): a memify pass
   that rewrites an entity's description from its 1-hop graph context. Good pattern for ugm profile
   summaries — but make it append-only/versioned, not an in-place overwrite.

**Avoid:**
1. **Name-hash as the *primary* ER mechanism.** This is precisely ugm's catastrophic-over-merge risk
   (`entity_registry.md` §1 asymmetry): "Apple"≡"apple", and split surfaces ("A. Novak" vs "Alice Novak")
   silently fragment. No type guard in the id hash. ugm must mix type/context and use a real
   candidate→adjudicate tier.
2. **No reversibility.** No `merged_into` redirect, no merge log, no un-merge/split, no pre-merge
   snapshot. ugm's transcript/verdict + merge_events design (entity_registry.md §4) directly fixes this;
   do not regress to cognee's implicit-merge-by-collision.
3. **Ontology has no domain/range enforcement** and predicate names are emergent free-form snake_case —
   the opposite of ugm D5 (governed predicate vocabulary). Don't adopt cognee's "ontology = optional OWL
   file that only enriches" as the governance model.
4. **Temporal model is descriptive, not assertional.** Event timestamps ≠ fact-validity windows; there's
   no supersession/invalidation in native cognee (it punts to Graphiti). For ugm's bi-temporal
   supersession (D3/D4/D10), cognee offers no reusable mechanism — look at Graphiti instead.
5. **In-place description overwrite** in the consolidate pipeline loses provenance/history — conflicts
   with ugm's immutable-transcript discipline.
