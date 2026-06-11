# mem0ai/mem0 — Code Archaeology

Clone root: `/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/`
Python SDK root: `mem0/mem0/`

**Scope caveat up front.** The repo's `CLAUDE.md` advertises a `mem0/graphs/` package
("Graph Stores: Neo4j, Memgraph, Kuzu, Apache AGE") and graph relation prompts. **In this
clone the graph memory package does not exist.** Verified:

```
find .../mem0/mem0 -name "*.py" -path "*graph*"   → (no results)
ls mem0/mem0/                                       → client configs embeddings llms
                                                      memory proxy reranker utils vector_stores
```

There is no `graphs/` directory, no `EXTRACT_RELATIONS_PROMPT`, no `UPDATE_GRAPH_*` prompt,
no Neo4j/Cypher graph store code. The only graph-adjacent artifacts are: a single vector
store backend `vector_stores/neptune_analytics.py`, and Cypher-string-sanitizing helpers in
`memory/utils.py` (`sanitize_relationship_for_cypher`, `remove_spaces_from_entities`,
`format_entities`) that are imported but have no graph caller in this tree. **Anything about
mem0's graph entity/relation extraction, domain/range typing, or graph supersession is "not
found" in this clone.** Findings below cover the vector-memory pipeline, which is what is
actually present and is substantial.

A second important framing fact: **the active ingestion pipeline is ADD-only ("additive").**
The classic ADD/UPDATE/DELETE/NOOP LLM controller (`DEFAULT_UPDATE_MEMORY_PROMPT`,
`get_update_memory_messages`) still exists in `configs/prompts.py` but **is not called
anywhere in `memory/main.py`** (grep confirms zero call sites). The pipeline that runs is the
"V3 PHASED BATCH PIPELINE" which only emits `event: "ADD"`. UPDATE/DELETE happen only as
explicit user-invoked API methods (`Memory.update()`, `Memory.delete()`), not as an
LLM-driven reconciliation step.

---

## 1. Entity resolution / dedup — how same-vs-different is decided

mem0 has **three distinct dedup mechanisms**, all deterministic except fact extraction itself:

### (a) Memory-text dedup — exact hash, deterministic
`memory/main.py` Phase 4/5 (~lines 810–829). New extracted memory texts are MD5-hashed and
compared against existing memories' stored `hash` and against hashes already seen in the
current batch:

```python
mem_hash = hashlib.md5(text.encode()).hexdigest()
if mem_hash in existing_hashes or mem_hash in seen_hashes:
    logger.debug(f"Skipping duplicate memory (hash match): {text[:50]}")
    continue
```

This is **byte-exact only** — no fuzzy / semantic dedup at the memory level in the active
path. Semantic near-duplicate suppression is delegated to the LLM extractor via prompt
instructions (the `ADDITIVE_EXTRACTION_PROMPT` "Recently Extracted Memories" /
"Existing Memories" dedup sections), not to code.

### (b) Entity resolution in the entity store — embedding threshold 0.95
`memory/main.py` `_upsert_entity` (line 439) and batch Phase 7 (line 944). An "entity" is a
spaCy-extracted span (see §3). To decide if a new entity equals a stored one:

```python
existing = self.entity_store.search(query=entity_text, vectors=entity_embedding,
                                    top_k=1, filters=search_filters)
if existing and existing[0].score >= 0.95:   # <-- the merge threshold
    # append memory_id to existing entity's linked_memory_ids
else:
    # create a new entity record (new UUID)
```

Same `>= 0.95` cosine threshold in the batched path (line 944). So entity identity =
**embedding similarity ≥ 0.95 of the surface text**, scoped by `user_id/agent_id/run_id`.
There is **no canonical-name authority set, no alias table, no LLM adjudication, no blocking
key beyond the session-scope filter.** Entities are stored in a *separate vector collection*
`f"{collection_name}_entities"` (line 420), payload shape:
`{"data": entity_text, "entity_type": <PROPER|QUOTED|COMPOUND|NOUN>, "linked_memory_ids": [...], user_id/agent_id/run_id}`.

Normalization key for within-batch entity dedup is `entity_text.strip().lower()`
(lines 901, 549).

### (c) Pre-embedding text normalization (graph-only helper, no caller here)
`memory/utils.py` `remove_spaces_from_entities` (line 270): lowercases, replaces spaces with
`_`, runs `sanitize_relationship_for_cypher`. Intended for graph triples; **no live caller in
this clone.**

**Thresholds summary (all from code):**
- Entity merge: `score >= 0.95` (main.py 452, 944)
- Entity-boost retrieval floor at search time: `similarity < 0.5 → skip` (main.py 1533)
- Memory dedup: exact MD5 match
- Default search `threshold = 0.1`, `top_k = 20` (main.py 1158, 1156, 1374)

---

## 2. Coreference handling

**No dedicated coreference resolver.** It is pushed entirely into the extraction prompt.
`ADDITIVE_EXTRACTION_PROMPT` (`configs/prompts.py` ~line 521, 629) instructs the LLM:

- "## Last k Messages … Use to resolve references and pronouns in New Messages."
- "### Self-Contained — Every memory must be understandable on its own. Replace all pronouns
  with specific names or 'User.'"

So coref is an LLM behavior contract, not deterministic code. The pipeline supplies the last
10 messages as context (`self.db.get_last_messages(session_scope, limit=10)`, main.py 729) and
a session summary slot to help the model ground pronouns. No `fastcoref`/spaCy-coref usage in
this package.

---

## 3. Extraction — how claims/entities are prompted and constrained

### Two-layer extraction: LLM facts (memories) + deterministic spaCy entities

**Layer 1 — fact/memory extraction (LLM, JSON, single pass).**
Active prompt: `ADDITIVE_EXTRACTION_PROMPT` in `configs/prompts.py` (lines 468–944). Called
in `_add_to_vector_store` with `response_format={"type": "json_object"}` (main.py 770) —
i.e. **OpenAI JSON-mode, not function-calling, not a strict grammar.** Schema is described in
prose + examples, not enforced by a JSON Schema validator. Output contract (prompt lines
918–943):

```json
{ "memory": [
    {"id":"0","text":"...","attributed_to":"user","linked_memory_ids":["uuid"]},
    {"id":"1","text":"...","attributed_to":"assistant"} ] }
```

Field rules quoted from the prompt:
- `id`: "Sequential integers as strings starting at '0'."
- `text`: "contextually rich, self-contained factual statement (15-80 words)" (lines 631–632:
  "up to 100 for detail-rich content").
- `attributed_to`: "user" / "assistant".
- `linked_memory_ids`: UUIDs of related *existing* memories (the memory-linking mechanism,
  §6).

It is **single-pass** — one LLM call per `add()` (main.py 765, "LLM extraction (single
call)"). No multi-pass gleaning/reflection loop. Robustness is via post-hoc JSON repair:
`remove_code_blocks` then `extract_json` (first `{`…last `}`) then `json.loads(strict=False)`
(main.py 778–786; helpers in `memory/utils.py` 109–142).

The prompt is notable for being **ADD-only and anti-supersession by design** — it never
emits UPDATE/DELETE; it links instead (see §5, §6). Strong, quotable engineering content:
- "Your sole operation is ADD" (line 472).
- Anti-hallucination integer remapping: existing memories are shown to the LLM with integer
  ids `str(idx)`, mapped back to real UUIDs in code (main.py 742–747, `uuid_mapping`).
- "**No Fabrication** … If you can't point to where it came from, don't include it." (679)
- "**No Implicit Attribute Inference** — Don't infer gender, age, ethnicity… from names." (680)
- "**No Meta-Extraction**" — extract content of shared docs, not "user shared a case" (684–688).
- Temporal grounding rules: resolve relatives against **Observation Date**, never Current
  Date (525–540, 634): "'User went to Paris last week' is useless 6 months later."
- Numeric/proper-noun preservation rules (637–666): "'416 pages' stays '416 pages', not
  'about 400 pages'"; "'Ferrari 488 GTB', NOT 'sports car'".

Legacy/alternative prompts still in the file but selectable only via `infer`/legacy helpers:
`FACT_RETRIEVAL_PROMPT`, `USER_MEMORY_EXTRACTION_PROMPT`, `AGENT_MEMORY_EXTRACTION_PROMPT`
(all emit `{"facts": [...]}` — flat strings).

**Layer 2 — entity extraction (deterministic spaCy, no LLM).**
`utils/entity_extraction.py`. Pure rule-based over `en_core_web_sm`
(`utils/spacy_models.py` line 60: `spacy.load("en_core_web_sm")`). Produces
`List[(entity_type, entity_text)]` with four types: **PROPER, QUOTED, COMPOUND, NOUN**
(docstring lines 4–8). Mechanism:
- PROPER: capitalized multi-word PROPN/NOUN/ADJ sequences with a mid-sentence capital
  (lines 187–223).
- QUOTED: regex on `"..."` and `'...'` (lines 226–231).
- COMPOUND: spaCy `noun_chunks`, split on possessives/quotes, head must be NOUN/PROPN,
  filtered against large stop-lists (`_GENERIC_HEADS`, `_NON_SPECIFIC_ADJ`,
  `_CIRCUMSTANTIAL_MODS`, `_GENERIC_ENDINGS`, lines 26–80), lemmatized (lines 233–307).
- NOUN: fallback single nouns (lines 286–291).
- Final cleanup (lines 326–357): lowercase dedup, type-priority keep
  (`PROPER > COMPOUND > QUOTED > NOUN`, line 347), and **substring suppression** —
  "Remove entities that are substrings of longer entities" (lines 355–357).

This is a *retrieval-boosting* index, **not** a claim/relation graph. There is no
(subject, predicate, object) extraction in the active code.

---

## 4. Ontology / type system

**Essentially none.** The only "types" are the four enum labels PROPER/QUOTED/COMPOUND/NOUN,
which are syntactic categories from spaCy heuristics, not a domain ontology. There is:
- no predicate vocabulary, no domain/range constraints, no type validation, no subclassing.
- no user-supplied ontology hook (contrast Cognee's OWL matching cited in your
  `entity_registry.md` §2).

`entity_type` is stored on the entity payload but is never used for validation or constraint
— only carried along. "Ontology / type system: not found" beyond syntactic tags.

---

## 5. Temporal / bi-temporal model — supersession / invalidation

**No bi-temporal model. No validity windows. No supersession/invalidation in storage.**

What exists:
- Per-memory `created_at` / `updated_at` ISO-8601 UTC timestamps (main.py 838–840). On the
  ADD-only path `updated_at == created_at` always.
- An **append-only history log** via `self.db.add_history(...)` / `batch_add_history` with an
  `event` column (`"ADD"`, `"UPDATE"`, `"DELETE"`) and `is_deleted` flag (main.py 870–889,
  1761, 1792). `Memory.history(memory_id)` exposes it. This is an audit trail, **not** a
  valid-time/transaction-time bitemporal store — there are no `valid_from`/`valid_to`
  intervals and no "as-of" query.
- **Temporal reasoning lives only in the prompt**: relative→absolute date grounding against
  "Observation Date" (`ADDITIVE_EXTRACTION_PROMPT` 525–540). The model writes the resolved
  date *into the memory text* ("the week of May 15, 2023"); the system does not model time
  structurally.

Supersession: because the pipeline is ADD-only, contradictory facts **coexist** as separate
memories and are linked (`linked_memory_ids` with "Contradiction" as a link reason, prompt
line 699), rather than one invalidating the other. The DELETE-on-contradiction logic of
`DEFAULT_UPDATE_MEMORY_PROMPT` (prompts.py 264) is dormant/unused.

---

## 6. Clustering / merge / un-merge — and "memory linking"

- **No clustering, no transitive closure, no community detection** in this clone.
- **Entity merge** is the only merge: on `score >= 0.95` the new entity's `memory_id` is
  appended to the existing entity's `linked_memory_ids` (main.py 452–464). This is *not* a
  record-merge of two entities into a survivor — it's "this entity now points at one more
  memory." There is **no un-merge / split primitive**; reversibility is absent.
- **Memory linking** (not merging): the LLM populates `linked_memory_ids` to build a soft
  graph of related memories (prompt 692–701, Example 10 lines 843–858). These links are
  stored but **the active code does not persist or traverse them** — `_add_to_vector_store`
  reads `text`/`attributed_to` from the LLM output but never reads `linked_memory_ids`
  (verify main.py 820–844). So memory-linking is currently *prompted but not wired into
  storage* in this clone.
- **Entity-store cleanup on delete** is the closest thing to un-link: `_remove_memory_from_entity_store`
  (main.py 482–535) strips a `memory_id` from every entity's `linked_memory_ids`, deleting the
  entity record when its list empties. Reversible only in the trivial sense.

---

## 7. Retrieval scoring — concrete numbers

`utils/scoring.py` + `memory/main.py` search path. Hybrid additive scoring (semantic + BM25 +
entity boost):

- `ENTITY_BOOST_WEIGHT = 0.5` (scoring.py 57).
- `score_and_rank` (scoring.py 60): `combined = (semantic + bm25 + entity_boost)/max_possible`,
  where `max_possible` ∈ {1.0, 1.5, 2.0, 2.5} depending on which signals are active
  (scoring.py 97–101). **Threshold gates the *semantic* score before combining**
  (`if semantic_score < threshold: continue`, line 111) — BM25/entity cannot rescue a
  below-threshold item.
- BM25 normalization is a **query-length-adaptive logistic sigmoid** (`get_bm25_params`,
  scoring.py 16–40): midpoint/steepness step from `(5.0, 0.7)` for ≤3 terms up to
  `(12.0, 0.5)` for >15 terms. `normalize_bm25` = `1/(1+e^{-steepness(raw-midpoint)})`.
- Entity boost at query time (main.py `_compute_entity_boosts`, 1473): extract query entities
  (cap **8**, line 1487), embed, search entity store `top_k=500` (line 1515), keep matches
  with `similarity >= 0.5` (line 1533). Boost per matched entity:
  `boost = similarity * 0.5 * memory_count_weight` where
  `memory_count_weight = 1.0 / (1.0 + 0.001*((num_linked-1)**2))` (lines 1542–1543) — i.e.
  entities linked to *many* memories (hubs) are **down-weighted**, a deliberate anti-false-hub
  measure. Per memory, the **max** boost across entities is kept (line 1548).
- BM25 lemmatization (`utils/lemmatization.py`) uses `en_core_web_sm` with `ner,parser`
  disabled (spacy_models.py 85), keeps lemmas + original `-ing` forms.

Model choices in code: spaCy `en_core_web_sm` (auto-downloaded, spacy_models.py 30–35).
Embedding/LLM are pluggable (provider factory); no hard-coded model. `existing_results`
retrieval for the extractor uses `top_k=10` (main.py 738). Context window: last 10 messages
(main.py 729). Truncation of context messages: `PAST_MESSAGE_TRUNCATION_LIMIT = 300` chars
(prompts.py 965). **No accuracy/LOCOMO benchmark numbers are present in this clone's Python
source** (eval framework lives under `evaluation/`, not read here).

---

## 8. Steal vs. avoid (for ugm)

### Worth stealing
- **Anti-hallucination ID remapping** (main.py 742–747): show the LLM small integer ids,
  keep the UUID↔int map in code, translate back. Cheap defense against the model inventing
  IDs — directly relevant to your D2 relation/claim id handling and any LLM-in-the-loop
  resolution.
- **Hub down-weighting in graph-distance/entity boost** (main.py 1542): the
  `1/(1+0.001*(n-1)^2)` penalty for highly-linked entities operationalizes your
  `entity_registry.md` warning that "over-merged entities create false hubs that poison
  graph-distance reranking (D9)." A concrete, tunable formula to adapt.
- **Substring/type-priority entity canonicalization** (entity_extraction.py 347, 355–357):
  cheap deterministic suppression of "Alice" when "Alice Novak" is present, and a fixed type
  precedence. Useful as a *blocking/normalization* pre-pass before your expensive ER.
- **Threshold gates the strong signal before fusion** (scoring.py 111): keeps a weak-but-boosted
  item from leaking in. Good discipline for your reranker.
- **ADD-only + link-on-contradiction prompt design** as one *option* for the
  evidence/claims plane: never destructively reconcile in the extractor; keep both, link them
  (prompt 692–701). This matches your D2 "claims are immutable, append-only testimony" — mem0
  independently arrived at append-only-with-links and lets a later stage adjudicate.
- The **prompt's preservation rules** (numbers, proper nouns, transitions, exact meaning;
  prompt 634–675) are a ready-made checklist for your claim-extraction (Claimify) prompt.

### Avoid / cautionary (aligns with your conservative-ER stance)
- **Pure 0.95-embedding entity ER with no authority anchor, no alias model, no adjudication,
  no provenance-of-merge, no un-merge** (main.py 452, 944). This is exactly the
  "threshold-similarity only" shallowness your `entity_registry.md` §2 flags for Cognee, and
  it violates your three Senzing principles (incremental ✓, **explainable ✗**,
  **reversible ✗**). It also blocks only on session scope, so cross-document/global ER —
  the load-bearing case in your architecture — is essentially absent. Do not adopt as the
  primary mechanism.
- **Temporal-grounding-in-text only**: resolving dates into the memory string but modeling no
  valid-time interval means you cannot do "as-of" queries or structural supersession — the
  opposite of your bi-temporal requirement. Treat mem0 as an anti-pattern here.
- **Prompted-but-unwired `linked_memory_ids`**: the LLM produces links the storage layer
  ignores (main.py 820–844). Lesson: if links are load-bearing (your relation graph), they
  must be persisted/traversed in code, not left as prose contract.
- **Single-pass JSON-mode with regex repair** scales but has no schema validation or gleaning;
  fine for casual chat memory, risky for a claims pipeline that must not silently drop a fact.
- **MD5-exact memory dedup**: trivially defeated by one-word paraphrase; mem0 leans on the LLM
  to dedup semantically. For your evidence aggregation (dedupe by (s,p,o), D2), exact-hash is
  insufficient.
