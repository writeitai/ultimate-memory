# Graphiti (getzep/graphiti) — Code Archaeology Findings

Repo: `_additional_context/graphiti` @ commit `40eca368` (2026-06-11). All paths below are relative to that repo root unless noted. Everything here is quoted/derived from actual source; where a feature is absent I write **not found**.

---

## 1. Entity resolution / node dedup — the mechanism

Graphiti uses a **3-tier cascade**: (1) semantic retrieval to gather candidates, (2) deterministic resolution (exact normalized-name + fuzzy MinHash/LSH), (3) LLM fallback for whatever is left unresolved. This is the single most "stealable" piece.

### Tier 0 — candidate gathering (semantic, per extracted node)
`graphiti_core/utils/maintenance/node_operations.py:418` `_semantic_candidate_search`:
- For each extracted node, embed `node.name` and run `node_similarity_search` directly (no reranking).
- Concrete params (`node_operations.py:63-65`):
  ```python
  MAX_NODES = 30
  NODE_DEDUP_CANDIDATE_LIMIT = 15          # top-K candidates per extracted node
  NODE_DEDUP_COSINE_MIN_SCORE = 0.6        # cosine floor for candidacy
  ```
  So candidate set = up to 15 existing nodes with cosine ≥ 0.6.

### Tier 1 — deterministic resolution
`graphiti_core/utils/maintenance/dedup_helpers.py`. Module-level thresholds (`dedup_helpers.py:31-36`):
```python
_NAME_ENTROPY_THRESHOLD = 1.5
_MIN_NAME_LENGTH = 6
_MIN_TOKEN_COUNT = 2
_FUZZY_JACCARD_THRESHOLD = 0.9
_MINHASH_PERMUTATIONS = 32
_MINHASH_BAND_SIZE = 4
```

`_resolve_with_similarity` (`dedup_helpers.py:220`) does, per extracted node:
1. **Exact normalized-name match** (`_normalize_string_exact` = lowercase + collapse whitespace, line 39). Always attempted regardless of length/entropy.
   - exactly 1 existing match → resolve to it (auto-merge, deterministic, no LLM).
   - >1 match (ambiguous) → escalate to LLM.
2. **Entropy gate** (`_has_high_entropy`, line 79): name must satisfy `len >= 6 OR token_count >= 2`, AND Shannon char-entropy `>= 1.5`. Short/low-entropy names (e.g. "Sam", "NYC") skip fuzzy and go straight to LLM. Comment explains why: "Short or repetitive names yield low entropy, which signals we should defer resolution to the LLM instead of trusting fuzzy similarity."
3. **Fuzzy MinHash/LSH** (line 255): 3-gram char shingles (`_shingles`, line 88) → 32-permutation MinHash signature (blake2b hashing, line 97) → LSH bands of size 4 → candidates from shared buckets scored by **Jaccard similarity** on shingle sets. Auto-merge only if `best_score >= _FUZZY_JACCARD_THRESHOLD` (0.9). Otherwise escalate to LLM.

This is genuinely deterministic and reproducible (seeded blake2b, no randomness).

### Tier 2 — LLM resolution
`_resolve_with_llm` (`node_operations.py:467`) is invoked only for `state.unresolved_indices`. Prompt = `dedupe_nodes.nodes`. The LLM is given the unresolved entities and the candidate existing nodes (with `candidate_id`, name, types, and `summary[:120]`) and must return, **for every entity**, a `duplicate_candidate_id` or `-1`.

Response schema (`graphiti_core/prompts/dedupe_nodes.py:25-38`):
```python
class NodeDuplicate(BaseModel):
    id: int                       # echo of the input entity id
    name: str                     # best/most-complete name
    duplicate_candidate_id: int   # candidate_id of match, or -1
class NodeResolutions(BaseModel):
    entity_resolutions: list[NodeDuplicate]
```

Prompt guardrails (`dedupe_nodes.py:83-94`): "Entities should only be considered duplicates if they refer to the *same real-world object or concept*… NEVER mark entities as duplicates if: They are related but distinct… similar names or purposes but refer to separate instances." Plus few-shot examples including the key negative: `"Java" (programming language)` vs `"Java" (Location/island)` → **-1** ("same name but distinct real-world things"), and positive synonym: `"Marco's car"` vs `"Marco's vehicle"` → duplicate.

There is heavy **defensive validation** of the LLM output (`node_operations.py:560-624`): missing IDs warned, extra/out-of-range IDs dropped, duplicate IDs ignored, invalid `duplicate_candidate_id` treated as no-duplicate. Comment: "ingestion workflow remains deterministic even when the model misbehaves."

### Type promotion on merge
`_promote_resolved_node` (`dedup_helpers.py:170`): when a generic canonical node (only `Entity` label) is matched by an extracted node that carries a specific type, the canonical node's labels are upgraded to include the specific label. So merging never loses type specificity.

### Within-message collapse (pre-DB)
`_collapse_exact_duplicate_extracted_nodes` (`node_operations.py:336`): collapses same-message exact normalized-name duplicates, keeping the more specific (more labels, then longer name), merging `episode_indices`.

---

## 2. Edge (fact) dedup, contradiction & invalidation

`graphiti_core/utils/maintenance/edge_operations.py` + `prompts/dedupe_edges.py`.

### Candidate gathering for an extracted edge (`resolve_extracted_edges`, line 325)
- **Exact in-batch dedup** first: key `(source_uuid, target_uuid, _normalize_string_exact(fact))` (line 349).
- `related_edges` (duplicate candidates) = `EntityEdge.get_between_nodes` (same endpoints) + hybrid search `EDGE_HYBRID_SEARCH_RRF` filtered to those edge UUIDs.
- `edge_invalidation_candidates` = broader hybrid search over the fact, minus anything already in `related_edges`.

### Fast path (`resolve_extracted_edge`, line 684)
If a related edge has identical endpoints AND `_normalize_string_exact(fact)` equality → reuse it verbatim, no LLM.

### LLM resolve (`dedupe_edges.resolve_edge`, prompt at `prompts/dedupe_edges.py:43`)
Response schema (`dedupe_edges.py:24-32`):
```python
class EdgeDuplicate(BaseModel):
    duplicate_facts: list[int]      # idx ONLY from EXISTING FACTS range
    contradicted_facts: list[int]   # idx from EITHER list
```
Key design: **EXISTING FACTS and INVALIDATION CANDIDATES are presented as one continuously-indexed list** (`idx` offset = `len(related_edges)`, line 703). A fact can be **both a duplicate and contradicted** ("semantically the same but the new fact updates/supersedes it"). Few-shot:
- "Alice works at Acme as a software engineer" vs "…as a senior engineer" → `contradicted_facts=[1]`, NOT duplicate.
- "Bob ran 5 miles Tuesday" vs "Bob ran 3 miles Wednesday" → neither (different events). Prompt explicitly: "NEVER mark facts as duplicates if they have key differences, particularly around numeric values, dates, or key qualifiers."

Output is validated/clamped to valid idx ranges (lines 735-776).

### Uses `model_size=ModelSize.small` for edge dedup
`edge_operations.py:729` — edge dedup, timestamp extraction, and attribute extraction all run on the **small** model; node extraction uses the default (large) model.

---

## 3. Extraction — prompt shape & constraints

**Structured output via Pydantic `response_model`** (function-calling / JSON-schema style), NOT free-form, NOT grammar. Every LLM call passes a `response_model=` Pydantic class. Three source-type-specific node prompts (`prompts/extract_nodes.py`): `extract_message`, `extract_text`, `extract_json`, dispatched by `EpisodeType` (`node_operations.py:261`).

Node schema (`extract_nodes.py:28-42`):
```python
class ExtractedEntity(BaseModel):
    name: str
    entity_type_id: int            # must be one of the provided ids
    episode_indices: list[int]     # which episodes it came from
```

The extraction prompt is **very heavily constrained with negative rules** — long "NEVER extract" blocks (pronouns, abstract concepts, generic nouns, bare relational/kinship terms, bare media/event/institutional nouns) plus a specificity rule ("Could this have its own Wikipedia article or database entry?") and possessor-qualification ("extract `Nisha's dad` not `dad`"). Six worked few-shot examples. This is a memory/conversational-recall-tuned prompt, not a general KG extractor.

### Single-pass extraction — NO reflexion/gleaning
`_extract_nodes_single` (`node_operations.py:244`) makes **one** LLM call. There is **no multi-pass gleaning / reflexion loop** in this path (a `MAX_REFLEXION` constant was searched for and **not found** in the current extraction path; classification is a separate optional `classify_nodes` prompt but extraction itself is single-pass).

### Edge extraction (`prompts/extract_edges.py:94`)
Schema (`extract_edges.py:25-52`):
```python
class Edge(BaseModel):
    source_entity_name: str   # MUST be a name from the ENTITIES list
    target_entity_name: str
    relation_type: str        # SCREAMING_SNAKE_CASE
    fact: str                 # NL paraphrase
    valid_at: str | None      # ISO 8601
    invalid_at: str | None
    episode_indices: list[int]
```
Constraints in `extract_edges` (`edge_operations.py:117`): source/target names must exist in the provided ENTITIES list (LLM-returned names validated; non-matching edges dropped, line 218); self-edges dropped (line 235); `max_tokens=16384` (line 141). The prompt forbids generalizing specifics ("NEVER generalize 'Gamecube' to 'gaming console'", line 158) — every concrete noun/number/descriptor must survive into `fact`.

---

## 4. Ontology / type system

- **Entity types = Pydantic models**, keyed by name; the model's **docstring is the type description** fed to the LLM (`node_operations.py:176` `'entity_type_description': type_model.__doc__`). There is always a built-in `entity_type_id: 0 = "Entity"` fallback (`node_operations.py:156`).
- **Validation of entity types** (`utils/ontology_utils/entity_types_utils.py:23` `validate_entity_types`): the only rule is that a custom type's field names must NOT collide with reserved `EntityNode` field names — else `EntityTypeValidationError`. There is **no domain/range constraint on entities themselves**.
- **Edge types** = Pydantic models too; docstring = description. Domain/range IS enforced for edges via `edge_type_map: dict[tuple[str, str], list[str]]` — keyed by **(source_label, target_label) signature** → list of allowed relation type names (`edge_operations.py:122`, `:478`). Default map when types provided: `{('Entity','Entity'): list(edge_types.keys())}` (`graphiti.py:1115`). During resolution, only edge types whose signature matches the actual source/target labels are offered to the LLM (`edge_operations.py:460-486`).
- **Excluded entity types** validated against available names (`helpers.py:189` `validate_excluded_entity_types`; `'Entity'` always available). Excluded types are filtered out post-extraction (`node_operations.py:309`).
- Enforcement is **soft/prompt-level for entity classification** ("NEVER use types not listed in ENTITY TYPES… set to None", `extract_nodes.py:375`) but **hard structurally for edge type-signature gating**.

---

## 5. Temporal / bi-temporal model

This is Graphiti's headline feature and it IS real and explicit. `EntityEdge` carries **two time axes** (`edges.py:271-282`):
```python
expired_at: datetime | None       # system/transaction time: when the edge was invalidated in the graph
valid_at:   datetime | None       # event/validity time: when the fact became true
invalid_at: datetime | None       # event/validity time: when the fact stopped being true
reference_time: datetime | None   # episode timestamp that produced the edge
created_at: datetime              # (on base Edge) when the record was written
```
- `valid_at`/`invalid_at` = **valid time** (extracted by LLM, ISO 8601, resolved against `reference_time`). `created_at`/`expired_at` = **transaction/system time**. That is the bi-temporal pairing.
- **Timestamp extraction**: prompt-driven (`extract_edges.edge` returns valid_at/invalid_at directly; separate `extract_timestamps` / `extract_timestamps_batch` on the **small** model as fallback when missing, `edge_operations.py:576`). DATETIME RULES (`extract_edges.py:168`): ongoing/present-tense fact → `valid_at = episode timestamp`; date-only → assume `00:00:00`; year-only → Jan 1; "Do NOT hallucinate or infer dates."

### Invalidation / supersession logic (deterministic, code not LLM)
`resolve_edge_contradictions` (`edge_operations.py:538`) and the tail of `resolve_extracted_edge` (`edge_operations.py:820`):
- If `resolved_edge.invalid_at` set and no `expired_at` → set `expired_at = now`.
- For invalidation candidates sorted by `valid_at`: if a candidate's `valid_at > resolved_edge.valid_at` (more recent info exists), the **new** edge is expired (`resolved_edge.invalid_at = candidate.valid_at`, `expired_at = now`) (line 826-839).
- Conversely an existing edge is invalidated by the new one when `edge.valid_at < resolved_edge.valid_at`: set `edge.invalid_at = resolved_edge.valid_at`, `edge.expired_at = now` (line 564-571).
- Overlap guard (line 553): if their validity windows can't overlap (one ends before the other begins), no invalidation.

**Edges are never hard-deleted on supersession** — they get `invalid_at`/`expired_at` stamped, preserving history. This is the bi-temporal point: you can query "what did we believe was true as of time T."

---

## 6. Clustering / merge / un-merge / transitive closure

- **Transitive closure on merge**: `compress_uuid_map` (`bulk_utils.py:606`) builds a **Union-Find** (`UnionFind`, line 584) over all duplicate pairs and maps every uuid → the **lexicographically smallest** uuid in its set. Path compression. Used in bulk node and edge dedup (`bulk_utils.py:461`, `:567`). So 3→2 and 2→1 collapses to 3→1. This is the canonical "pick a stable representative" approach.
- **Persisted duplicate edges**: confirmed duplicates create `IS_DUPLICATE_OF` relationships in the graph (queried in `filter_existing_duplicate_of_edges`, `edge_operations.py:850`, with backend-specific Cypher for Neptune/Kuzu/Neo4j). `filter_existing_duplicate_of_edges` avoids re-creating an `IS_DUPLICATE_OF` edge that already exists.
- **Un-merge / reversibility**: **not found.** There is no un-merge / split operation. Merge picks a canonical representative and rewrites edge pointers (`resolve_edge_pointers`, `bulk_utils.py:627`). The `IS_DUPLICATE_OF` edge records that a merge happened (some provenance), but no code reverses a merge. Choosing canonical by lexicographic uuid is **arbitrary** (not "most-complete name" at the graph level) — though the LLM dedup prompt is told to return the most complete name for the node record.
- **Community/cluster detection** exists separately (`community_operations.py`, label-propagation style) but that's topic clustering, not entity dedup.

---

## 7. Concrete numbers / model choices (all verified in source)

| Item | Value | Location |
|---|---|---|
| Node dedup cosine floor | `0.6` | `node_operations.py:65` |
| Node dedup candidate top-K | `15` | `node_operations.py:64` |
| Fuzzy Jaccard auto-merge threshold | `0.9` | `dedup_helpers.py:34` |
| Name entropy threshold (fuzzy gate) | `1.5` bits | `dedup_helpers.py:31` |
| Min name length / token count (gate) | `6` / `2` | `dedup_helpers.py:32-33` |
| MinHash permutations / band size | `32` / `4` | `dedup_helpers.py:35-36` |
| Shingle size | 3-gram chars | `dedup_helpers.py:88` |
| Max nodes per summary LLM call | `30` | `node_operations.py:63` |
| Edge extraction max_tokens | `16384` | `edge_operations.py:141` |
| Summary char cap | `1000` | `text_utils.py:26` |
| Episode context window | `3` previous | `graph_data_operations.py:29` |
| Edge dedup/timestamp/attr model size | `ModelSize.small` | `edge_operations.py:729` |
| Max search query length | `128` | `search_utils.py:68` |

**Models** (`CLAUDE.md`, Nov 2025): defaults documented as OpenAI `gpt-4.1`/`gpt-4.1-mini`, `gpt-5-mini`/`gpt-5-nano` (reasoning, require `temperature=0`); Anthropic `claude-sonnet-4-5`, `claude-haiku-4-5`; Gemini 2.5. Note: "works best with services supporting structured output (OpenAI, Gemini). Other providers may cause schema validation issues, especially with smaller models." **No accuracy/benchmark numbers** are present in the source tree (eval scripts exist at `tests/evals/` but no reported figures in code/docs). **Not found:** published precision/recall.

---

## 8. Coreference handling

No dedicated coreference module (no `fastcoref`/spaCy-style resolver). Coref is **prompt-level only**: the extraction prompt instructs the LLM to "disambiguate [pronouns] to the names of the reference entities" (`extract_nodes.py:115`) and the edge prompt says "Facts should include entity names rather than pronouns whenever possible" (`extract_edges.py:137`). Bare relational terms must be possessor-qualified ("Nisha's dad"). So coref = LLM in-context, no separate algorithm.

---

## 9. Steal vs. avoid (for ugm)

### Steal
1. **The 3-tier dedup cascade** (semantic candidates → deterministic exact+fuzzy → LLM fallback). Directly maps to ugm's entity_registry. The cost discipline is the point: cheap deterministic resolution handles the easy majority; the LLM only sees genuinely ambiguous cases.
2. **The entropy gate before fuzzy matching** (`dedup_helpers.py:79`). Elegant, cheap heuristic to *not* trust fuzzy similarity on short/low-entropy names ("Sam", "NYC", "Java") and defer those to the LLM. Concrete thresholds (len≥6 or ≥2 tokens, entropy≥1.5) are a good starting calibration.
3. **MinHash+LSH for fuzzy candidate blocking**, seeded with blake2b (fully deterministic/reproducible — important for ugm's testability). Jaccard 0.9 is a deliberately conservative auto-merge bar.
4. **Union-Find transitive closure with a stable lexicographic representative** for merge sets (`bulk_utils.py:584-621`). Clean, correct, handles 3→2→1 chains.
5. **Continuously-indexed duplicate+contradiction list in one LLM call** for edges, allowing "duplicate AND contradicted" (supersession) — efficient single round-trip.
6. **Bi-temporal stamping instead of deletion**: `valid_at/invalid_at` (event time) + `created_at/expired_at` (system time), supersession sets timestamps, never deletes. Matches ugm's need for temporal/audit queries.
7. **Defensive LLM-output validation everywhere** (clamp idx ranges, drop extra/missing/duplicate IDs, treat malformed as "no-op") so ingestion stays deterministic when the model misbehaves.
8. **Edge type-signature gating** (`(source_label,target_label) → allowed relation types`) — a lightweight, real domain/range enforcement worth adopting for ugm predicates.
9. **Type promotion on merge** so merging a typed node into a generic `Entity` upgrades the canonical's labels — avoids losing specificity.

### Avoid / watch out
1. **No un-merge / reversibility.** Graphiti can only record `IS_DUPLICATE_OF`; it cannot split a wrongly-merged entity. ugm should design merges as reversible from day one (keep source members + provenance, don't destructively rewrite). This is a known ugm requirement; Graphiti is a cautionary example.
2. **Canonical chosen by lexicographic uuid** (`compress_uuid_map`) — arbitrary, not semantically "best". The richer node record may not win. ugm should pick canonical by completeness/recency, not uuid ordering.
3. **Single-pass extraction, no gleaning/reflexion.** Good for cost, but recall on dense text depends entirely on one prompt. If ugm needs higher recall, a gleaning pass is a deliberate add-on, not inherited here.
4. **Dedup correctness leans on the LLM for the hard cases**, with only soft prompt guardrails for "related but distinct." The `"Java"` island-vs-language case shows the failure mode; entity-type signals (passing types into the dedup prompt) are the main mitigation. ugm should pass strong type/attribute signals into any LLM dedup step.
5. **Memory/conversational tuning bleed-through.** The extraction prompts are saturated with conversation-recall-specific rules (speaker-first, "Nisha's dad", pet/kinship qualification). These are not domain-neutral — ugm must rewrite extraction prompts for its own domain rather than copy them.
6. **Fuzzy path is name-string only** (char shingles). It will miss true synonyms that don't share trigrams ("NYC" vs "New York City" — note 0.9 Jaccard would NOT match these; they fall to the LLM). So the deterministic layer is precision-oriented, recall comes from the LLM. Set expectations accordingly.
7. **Two prompt copies to keep in sync** (Python summary prompt mirrored in a Go worker, `extract_nodes.py:540`) — a maintenance hazard if ugm splits ingestion across languages/services.
