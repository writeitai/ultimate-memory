# Repo Findings: Letta (MemGPT) + HippoRAG

Source-of-truth archaeology of two cloned repos. Every claim cites a file path; code/prompts
quoted verbatim; "not found" used where the design concept has no code analog. Paths are
relative to `ugm/_additional_context/`.

TL;DR orientation:
- **HippoRAG** is the relevant one for the registry/ER/graph work. It is a graph-RAG retriever:
  OpenIE (NER → triples) builds a KG; "entity resolution" is *implicit* — synonymy edges added
  by embedding-KNN at a 0.8 cosine threshold, **never a merge**; retrieval is Personalized
  PageRank seeded by LLM-filtered facts. No supersession, no bi-temporality, no ontology, no
  un-merge.
- **Letta** has **no entity/relation/KG/ER/coref machinery at all** (grep for
  `entity_resolution|triple|knowledge graph|synonym|coref` over `letta/services`,
  `letta/agents`, `letta/functions` returns nothing). Its memory model is OS-style tiered text:
  in-context **blocks** (self-edited via string-replace tools) + **archival** passages (vector
  search) + **recall** (message history search). Relevant to ugm only as a contrast model and
  for its self-editing-tool and summarization-eviction patterns.

---

## PART A — HippoRAG (`hipporag/`)

This is "HippoRAG 2" (`README.md:1`, arXiv 2502.14802, "From RAG to Memory"). OSU-NLP-Group.

### A1. Extraction — OpenIE, two-pass, JSON-via-prompt (not function-calling, not grammar)

Two sequential LLM calls per chunk (`src/hipporag/information_extraction/openie_openai.py:130`
`openie()` → `ner()` then `triple_extraction()`):

1. **NER pass** (`prompts/templates/ner.py`): one-shot, system prompt
   `"Your task is to extract named entities from the given paragraph. Respond with a JSON list
   of entities."` Output schema is `{"named_entities": [...]}`.
2. **Triple pass conditioned on the NER list** (`prompts/templates/triple_extraction.py`):
   system prompt `"Your task is to construct an RDF (Resource Description Framework) graph from
   the given passages and named entity lists. Respond with a JSON list of triples..."` with two
   constraints quoted verbatim:
   - `"Each triple should contain at least one, but preferably two, of the named entities in
     the list for each passage."`
   - `"Clearly resolve pronouns to their specific names to maintain clarity."` ← this is the
     **only coreference handling** in the repo: it's a single inline prompt instruction during
     triple extraction, not a coref model. (`fastcoref`/`maverick-coref` are separate sibling
     repos, not used by HippoRAG.)

Constraint mechanism is **prompt + JSON, not schema/function-calling/grammar**. JSON is parsed
out with a regex and `eval()` (`openie_openai.py:31-36`, `:82-88`):
`pattern = r'\{[^{}]*"named_entities"\s*:\s*\[[^\]]*\][^{}]*\}'`. The OpenAI client does set
`response_format = {"type": "json_object"}` (`utils/config_utils.py:54-57`) — JSON mode, not a
typed schema. `temperature = 0` (`config_utils.py:50`), `max_new_tokens = 2048`.

**Single-pass, no gleaning / no multi-round re-extraction.** One NER call + one triple call per
chunk; `batch_openie` (`openie_openai.py:135`) just threads chunks. (Contrast: GraphRAG-style
gleaning loops are absent.)

**Triple validity** is purely structural (`utils/llm_utils.py:222` `filter_invalid_triples`):
keep iff exactly 3 elements and dedupe; docstring explicitly says *"Do not apply any text
preprocessing techniques or rules within this function."* No type checking, no domain/range.

Default extraction model: `llm_name = "gpt-4o-mini"` (`config_utils.py:18-21`).

### A2. "Entity resolution" — there is none in the merge sense; synonymy edges instead

Entities are **nodes keyed by a hash of their lowercased, punctuation-stripped surface string**.
`text_processing` (`utils/misc_utils.py:54-59`):
```python
return re.sub('[^A-Za-z0-9 ]', ' ', text.lower()).strip()
```
Node id = `compute_mdhash_id(content=triple[0], prefix="entity-")` = `"entity-" + md5(string)`
(`HippoRAG.py:763`, `misc_utils.py:115-126`). So **dedup is exactly string-identity after
lowercasing + punctuation removal** — "Alice Novak" and "A. Novak" are *different nodes*; "Apple
Inc." and "apple inc" collapse. This is the entire deterministic ER layer. No fuzzy, no
phonetic, no external-authority (tier-0), no LLM adjudication, no aliases table, no
`merged_into` redirect. Maps to ugm's **Tier 1 only** (exact, post-normalization).

Same-vs-different across surface variants is handled **softly, via edges, never merges**
(`HippoRAG.py:821` `add_synonymy_edges`):
- KNN over entity embeddings, `k = synonymy_edge_topk = 2047` (`config_utils.py:148`).
- Keep a neighbor as a synonym iff cosine `score >= synonymy_edge_sim_threshold = 0.8`
  (`config_utils.py:160-163`; loop break at `HippoRAG.py:869`).
- Guard: only entities with `len(re.sub('[^A-Za-z0-9]','',entity)) > 2` get synonym edges
  (`HippoRAG.py:864`) — skips 1-2 char junk.
- Cap: `num_nns > 100` breaks (`HippoRAG.py:869`) — max 100 synonym edges per node.
- The edge **weight is the raw similarity score** (`HippoRAG.py:879`), and the source comment is
  telling: `self.node_to_node_stats[sim_edge] = score  # Need to seriously discuss on this`.

Incremental note (`HippoRAG.py:847`): synonymy edges are built between newly inserted phrase
nodes and *all* phrase nodes "to reduce cost for incremental graph updates."

**Consequence for ugm:** this is the *anti-pattern* the entity_registry analysis warns about —
identity-by-surface-string with similarity edges papering over the cracks. There is no blocking
key, no `(entity_id, predicate)` supersession, so two-people-same-name fuse if their strings
match and never separate if their strings differ. No reversibility because there's no merge to
reverse. Useful only as the cheap candidate-generation tier (their 0.8 KNN ≈ ugm Tier-4
embedding candidate stage), explicitly *not* as a resolution decision.

### A3. Ontology / type system — none

No entity types, no predicate vocabulary, no domain/range. Predicates are **free-text strings**
straight from the LLM ("located in", "plays songs in", "forayed into" — see the one-shot output
in `triple_extraction.py:27-42`). Predicates are lowercased and embedded but never governed,
canonicalized, or constrained. This is precisely the D5 failure mode (vocabulary fragmentation)
left un-mitigated. `graph_type` config enum (`config_utils.py:211-220`) selects *graph topology*
(`dpr_only`, `entity`, `passage_entity`, `facts_and_sim_passage_node_unidirectional`), not a
type system.

### A4. Temporal / bi-temporal — none

No `valid_from`/`valid_until`, no supersession, no invalidation, no contradiction grouping.
`delete()` (`HippoRAG.py:280`) is the only lifecycle op besides insert: it removes a doc and
*reference-counts* — a triple/entity is deleted only if **no surviving chunk** still produces it
(`HippoRAG.py:316-345`: `non_deleted_docs = doc_ids.difference(chunk_ids_to_delete)`; delete iff
`len(non_deleted_docs) == 0`). That reference-count-before-delete idea is the one lifecycle
pattern worth noting, but there is no notion of a fact being *superseded* vs *retracted*.

### A5. Graph structure — three node types, undirected, igraph + Personalized PageRank

Graph is `igraph`, **undirected** by default (`is_directed_graph = False`,
`config_utils.py:164`; `initialize_graph` `HippoRAG.py:193`). Three kinds of nodes / edges:
- **Phrase (entity) nodes** and **fact edges**: for each triple, an undirected edge between
  subject and object node, weight = co-occurrence count (`add_fact_edges` `HippoRAG.py:766-769`:
  `node_to_node_stats[(a,b)] += 1`).
- **Passage (chunk) nodes** connected to the phrase nodes they contain, weight `1.0`
  (`add_passage_edges` `HippoRAG.py:815`).
- **Synonymy edges** (A2), weight = similarity.

Graph persisted as a pickle (`graph.pickle`, `HippoRAG.py:182`); rebuilt incrementally, not from
a relational authority. (Contrast ugm D6/D7: HippoRAG's graph *is* the store, not a disposable
projection.)

### A6. Retrieval — fact-filter (LLM "recognition memory") → PPR → DPR fallback

`retrieve()` (`HippoRAG.py:363`) pipeline, **graph distance via PPR**, with exactly one
query-time LLM call (the fact filter):

1. **Fact scoring** (`get_fact_scores` `HippoRAG.py:1290`): cosine of query embedding vs all fact
   embeddings, then `min_max_normalize`. Query encoded with instruction
   `"Given a question, retrieve relevant triplet facts that matches this question."`
   (`prompts/linking.py:5`).
2. **Recognition-memory rerank** (`rerank.py` `DSPyFilter`): take top `linking_top_k = 5`
   (`config_utils.py:172`) candidate facts, send to LLM with a DSPy-compiled few-shot prompt,
   LLM returns a filtered subset typed as `Fact(fact: list[list[str]])` (pydantic,
   `rerank.py:11`). Parsing tolerates JSON or `ast.literal_eval`, and re-maps generated facts
   back to candidates with `difflib.get_close_matches(..., cutoff=0.0)` (`rerank.py:123`).
   `max_completion_tokens = 512` (`rerank.py:93`). This is the only query-path LLM call.
3. **Seed weighting → Personalized PageRank** (`graph_search_with_fact_entities`
   `HippoRAG.py:1407`): entities in the surviving facts become PPR reset-seeds; each phrase
   weight is the fact score **divided by the number of chunks the entity appears in**
   (`HippoRAG.py:1463-1464` — an IDF-like damping so hub entities don't dominate). Passage nodes
   get a small direct DPR weight `passage_node_weight = 0.05` (`config_utils.py:79`).
4. **PPR** (`run_ppr` `HippoRAG.py:1572`): `igraph.personalized_pagerank(..., damping=0.5,
   directed=False, weights='weight', reset=reset_prob, implementation='prpack')`. Damping
   `damping = 0.5` (`config_utils.py:180`). Document nodes ranked by resulting PageRank score.
5. **Fallback**: if no facts survive rerank, fall back to pure dense passage retrieval
   (`HippoRAG.py:417-419`, `dense_passage_retrieval` `HippoRAG.py:1330`).

Default embedding model `nvidia/NV-Embed-v2` (`config_utils.py:124`), `retrieval_top_k = 200`,
`qa_top_k = 5`. Distinct query instructions per channel (`linking.py`): `query_to_fact`,
`query_to_passage`, `ner_to_node`, etc.

**Steal for ugm:** this is the concrete realization of D9's "graph-distance reranking" — PPR
seeded from query-relevant facts is exactly center-node reranking, and the per-entity IDF
damping (`/len(chunks)`) is a clean, cheap hub-suppression trick to consider for the
evidence_count rerank. The 0.05 passage-node weight + DPR fallback is a good safety net pattern
(structured signal dominates, dense retrieval rescues).

### A7. Concrete numbers (HippoRAG)

| Parameter | Value | File |
|---|---|---|
| synonymy edge sim threshold | **0.8 cosine** | `config_utils.py:160` |
| synonymy KNN k | 2047 | `config_utils.py:148` |
| max synonym edges/node | 100 | `HippoRAG.py:869` |
| min entity length for synonymy | >2 alnum chars | `HippoRAG.py:864` |
| PPR damping | 0.5 | `config_utils.py:180` |
| passage node weight in PPR | 0.05 | `config_utils.py:79` |
| linking_top_k (facts reranked) | 5 | `config_utils.py:172` |
| retrieval_top_k | 200 | `config_utils.py:176` |
| extraction temperature | 0 | `config_utils.py:50` |
| default LLM / embedder | gpt-4o-mini / NV-Embed-v2 | `config_utils.py:18,124` |
| chunk overlap tokens | 128 | `config_utils.py:97` |

No accuracy/F1 numbers are hard-coded in the source tree; the README cites the paper
(arXiv 2502.14802) but gives no in-repo benchmark figures beyond the eval harness
(`evaluation/retrieval_eval.py`, recall@k with `k_list=[1,2,5,10,20,30,50,100,150,200]`,
`HippoRAG.py:443`).

---

## PART B — Letta / MemGPT (`letta/`)

### B1. Memory model — OS-style tiers, all text, no KG (the MemGPT thesis verbatim)

The tiered model is spelled out in the system prompt (`letta/prompts/system_prompts/
memgpt_chat.py`), quoted:
- **Core memory** (in-context, always visible): persona + human sub-blocks. *"Your core memory
  unit is held inside the initial system instructions file, and is always available
  in-context."* Edited via `core_memory_append` / `core_memory_replace`.
- **Recall memory** (message history DB): *"you can search over your entire message history from
  a database... using the 'conversation_search' function."*
- **Archival memory** (*"infinite size"*, out of context): *"you must explicitly run a
  retrieval/search operation"* — `archival_memory_insert` / `archival_memory_search`.

There is **no entity, relation, triple, or graph layer anywhere** in Letta (verified by grep).
All "memory" is markdown/plaintext. This is the architectural opposite of ugm's evidence plane.

### B2. Self-editing tools — string-replace on text blocks (the pattern worth studying)

`letta/functions/function_sets/base.py` defines the agent-callable memory tools. Two generations:
- **Classic MemGPT**: `core_memory_append(label, content)` (`base.py:246`) does
  `new = current + "\n" + content`; `core_memory_replace(label, old_content, new_content)`
  (`base.py:263`) raises `ValueError` if `old_content not in current_value` then
  `current.replace(old, new)`.
- **v2 "filesystem-style" tools** modeled on Anthropic's computer-use text-editor (comment
  `base.py:310` cites the anthropic-quickstarts edit.py):
  - `memory_replace(label, old_string, new_string)` — **must match exactly and uniquely**;
    raises if `occurences == 0` or `> 1` (`base.py:362-373`). Same discipline as the ugm Edit
    tool. Explicitly rejects line-number prefixes / the line-number warning banner
    (`base.py:345-356`).
  - `memory_insert(label, new_string, insert_line)` (`base.py:391`).
  - `memory_rethink(label, new_memory)` — full block rewrite for "large sweeping changes"
    (`base.py:488`); `rethink_memory` is the older variant (`base.py:283`).
  - `memory_apply_patch(label, patch)` — a **codex/unified-diff multi-block patch** format with
    `*** Add Block:` / `*** Update Block:` / `*** Delete Block:` / `*** Move to:` headers
    (`base.py:453-485`).
  - `memory_finish_edits()` — sentinel to end a multi-step edit session (`base.py:520`).
- Sub-command dispatcher `memory(command, ...)` with `create|str_replace|insert|delete|rename`
  (`base.py:10-68`).

The **sleeptime memory agent** prompt (`prompts/system_prompts/sleeptime_v2.py`) is the most
ugm-relevant text: a background agent that *"organizes and maintains the memories"* with read-only
vs read-write blocks, and two lines worth stealing verbatim as compile-layer guidance:
- *"make sure to be precise when referencing dates and times (... do not write 'today' or
  'recently', instead write specific dates and times, because ... the memory is persisted
  indefinitely)."*
- *"do not contain redundant and outdate[d] information"* + *"be selective in your memory
  editing, but also aim to have high recall."*

### B3. Entity resolution / dedup — none; archival "dedup" is only tag-list dedup

No ER. The only `dedup`/`duplicate` hits in `services/passage_manager.py` are **tag-list
deduplication** for dual-store (vector+SQL) consistency (`passage_manager.py:143,228,297,675`),
*not* content/semantic dedup. `insert_passage` (`passage_manager.py:543`) stores text + embedding
with no same-vs-different check — archival memory can hold near-duplicate passages freely. (This
is the Mem0-class "junk accumulation" risk objections.md O3 flags.)

### B4. Coreference — none. Temporal — wall-clock only

No coref engine. No bi-temporal validity model; archival passages carry `created_at` and
date-range filters (`base.py:194-243` `archival_memory_search` `start_datetime`/`end_datetime`),
i.e. a single ingestion clock, not the two-clock (world-time vs system-time) model of
concepts.md §5. No supersession/invalidation: contradictory facts are resolved by the
**agent rewriting the block** (`memory_replace`/`memory_rethink`), an LLM-judgment overwrite that
destroys the prior value — the opposite of ugm's append-only-evidence + revisable-relation split.

### B5. Memory lifecycle — context-window eviction + recursive summarization

The real lifecycle machinery is the **summarizer** (`letta/services/summarizer/summarizer.py`),
two modes (`SummarizationMode`):
- **STATIC_MESSAGE_BUFFER** (`summarizer.py:244`): keep a fixed buffer; when
  `len > message_buffer_limit` (default 10, `summarizer.py:49`), evict everything between the
  system message and a trim index down to `message_buffer_min` (default 3), preserving user-
  message boundaries; fire-and-forget a background summarizer agent over the evicted span.
- **PARTIAL_EVICT_MESSAGE_BUFFER** (`summarizer.py:136`): the original MemGPT loop — evict
  `partial_evict_summarizer_percentage = 0.30` of messages and replace `message[1]` with a
  recursive summary (`summarizer.py:163`).

Trigger threshold: summarize when usage `> context_window * SUMMARIZATION_TRIGGER_MULTIPLIER`,
`= 0.9` (`constants.py:83`, `services/summarizer/thresholds.py`
`get_compaction_trigger_threshold`). GPT-5 family forced to proactive 90% (`thresholds.py`).

Block size limits (`constants.py:433-435`): `CORE_MEMORY_PERSONA_CHAR_LIMIT = 20000`,
`CORE_MEMORY_HUMAN_CHAR_LIMIT = 20000`, `CORE_MEMORY_BLOCK_CHAR_LIMIT = 100000`. Enforced via the
block's `limit` field (`schemas/block.py:20`) re-validated on every value `__setattr__`
(`schemas/block.py:59-65`). Read-only blocks reject edits with `READ_ONLY_BLOCK_EDIT_ERROR`
(`constants.py:424`).

### B6. Retrieval (Letta)

- `archival_memory_search` (`base.py:194`): semantic similarity + optional tag filter
  (`tag_match_mode: any|all`) + datetime range, `top_k` default 10. Pure vector search, no graph.
- `conversation_search` (`base.py:87`): *"hybrid search (text + semantic similarity)"* over
  message history (`message_manager.list_messages_for_agent`), role + date filters,
  `RETRIEVAL_QUERY_DEFAULT_PAGE_SIZE` default limit.

No RRF, no graph-distance rerank, no cross-encoder — far simpler than ugm D9. The interesting bit
is the **agent-driven** retrieval (the LLM decides when/what to search via tool calls), vs ugm's
zero-LLM-on-query-path recipe approach.

---

## PART C — Steal vs Avoid (for ugm)

**Steal (HippoRAG):**
- **PPR-from-query-facts as the graph-distance reranker** (`graph_search_with_fact_entities` +
  `run_ppr`): concrete, fast (igraph `prpack`), exactly D9's center-node rerank. The per-entity
  **IDF damping** `weight /= len(chunks_entity_appears_in)` is a cheap hub-suppression trick.
- **DPR fallback + small passage-node weight (0.05)**: structured signal leads, dense retrieval
  rescues — a good safety net for the search recipes.
- **NER-conditioned triple extraction** (constrain triples to contain ≥1 NER entity): a cheap
  precision lever that reduces relation hallucination before governance even runs (complements
  D15 domain/range).
- **Reference-count-before-delete** (`delete()`): only drop a triple/entity when no surviving
  chunk produces it — a clean retraction rule.
- The 0.8 cosine KNN as a **candidate-generation tier** (ugm Tier 4), explicitly downstream of a
  real resolver — never as the decision itself.

**Steal (Letta):**
- **Exact-unique string-replace memory tools** (`memory_replace` 0/1/>1-occurrence guard) and the
  **codex-style multi-block `memory_apply_patch`** — directly applicable to the K-plane compiled
  markdown editors; the uniqueness guard is the same one ugm's own Edit tool enforces.
- **Sleeptime-agent prompt discipline**: "no 'today'/'recently', write absolute dates" and
  "remove redundant/outdated info, be selective but high-recall" — drop-in guidance for K1/K2
  compile prompts (objections.md O4 staleness).
- **90%-of-context-window proactive compaction trigger** and recursive-summary eviction as a
  buffer-management reference.

**Avoid:**
- **HippoRAG's identity-by-surface-string ER.** `md5(lowercase(punct-stripped(name)))` as the
  entity key is exactly the under-merge/over-merge trap entity_registry.md §1 describes: same-name
  different-people silently fuse; alias variants silently fragment; and because synonymy is *edges
  not merges*, there is no `(entity_id, predicate)` blocking key, no supersession, and nothing to
  un-merge. The author's own `# Need to seriously discuss on this` on the synonymy-edge weight is
  a tell.
- **HippoRAG's free-text predicates** — the D5 fragmentation failure, unmitigated.
- **The graph as the source of truth** (pickle, incrementally mutated): contradicts D6/D7. ugm's
  graph must stay a rebuildable projection; HippoRAG shows what happens without that discipline
  (entity merges/retypings would be in-place graph surgery).
- **Letta's overwrite-on-contradiction** (`memory_rethink` blows away prior block value): loses
  the evidence/verdict split (D2/D3); never adopt for the E-plane.
- **Letta's no-dedup archival insert**: the Mem0-class junk-accumulation risk (O3) — ugm needs the
  value/salience gate HippoRAG and Letta both lack.
