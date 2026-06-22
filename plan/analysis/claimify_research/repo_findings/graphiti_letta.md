# Graphiti & Letta — extraction context window + selection/filtering

Code archaeology of the two repos under `_additional_context/`. Everything below is
VERIFIED against source (file:line) unless explicitly marked INFERENCE or UNVERIFIED.
Note: this local `graphiti` checkout is a heavily-modified fork (timestamps Jun 11),
not the upstream Zep release — the prompts quoted here are the actual code in this tree.

---

## GRAPHITI (`_additional_context/graphiti`)

Graphiti is episode-based. An "episode" = one ingested unit (a chat message, a text blob,
or JSON). `add_episode` runs: extract_nodes → resolve/dedup nodes → extract_edges (facts)
→ resolve/dedup/invalidate edges → extract attributes/summaries. Edges ARE the
"fact triples" (`source_entity_name`, `relation_type`, `target_entity_name`, `fact`).

### (1) CONTEXT WINDOW — what the extraction LLM actually sees

**Both node and edge extraction see the target episode PLUS a window of prior episodes.**
The window is real prior episodes retrieved from the store, not just the local chunk.

- Window size: `RELEVANT_SCHEMA_LIMIT = 10` in the live `add_episode` path
  (`graphiti_core/search/search_utils.py:64`; used at `graphiti_core/graphiti.py:1087-1096`:
  `previous_episodes = await self.retrieve_episodes(reference_time, last_n=RELEVANT_SCHEMA_LIMIT, ...)`).
  The bulk path uses `EPISODE_WINDOW_LEN = 3`
  (`graphiti_core/utils/maintenance/graph_data_operations.py:29`;
  `graphiti_core/utils/bulk_utils.py:115-116`).
- Edge (fact) extraction prompt literally embeds both
  (`graphiti_core/prompts/extract_edges.py:114-129`):
  ```
  <PREVIOUS_MESSAGES>
  {to_prompt_json(context['previous_episodes'])}
  </PREVIOUS_MESSAGES>

  <CURRENT_MESSAGE>
  {context['episode_content']}
  </CURRENT_MESSAGE>

  <ENTITIES>
  {to_prompt_json(context['nodes'])}
  </ENTITIES>

  <REFERENCE_TIME>
  {context['reference_time']}  # ISO 8601 (UTC); used to resolve relative time mentions
  </REFERENCE_TIME>
  ```
  The context dict is built in `edge_operations.py:186-200` (`previous_episodes` = list of
  `{content, timestamp}` for each prior episode; `episode_content` = current episode(s)).
- The prompt scopes prior context to disambiguation only — extraction targets the current
  message (`extract_edges.py:132-139`):
  ```
  Extract all factual relationships between the given ENTITIES based on the CURRENT MESSAGE.
  Only extract facts that:
  - involve two DISTINCT ENTITIES from the ENTITIES list,
  - are clearly stated or unambiguously implied in the CURRENT MESSAGE, ...
  You may use information from the PREVIOUS MESSAGES only to disambiguate references or
  support continuity.
  ```
- Node extraction (`prompts/extract_nodes.py:122-128`) similarly shows
  `<PREVIOUS MESSAGES>` then `<CURRENT MESSAGE>`, and explicitly
  **excludes** entities that appear only in prior context:
  `extract_nodes.py:148` — "**Exclude** entities mentioned only in the PREVIOUS MESSAGES
  (they are for context only)." Context built at `node_operations.py:115-129`.
- A single `add_episode` call can itself pack MULTIPLE episodes into `<CURRENT_MESSAGE>`:
  `concatenate_episodes` (`utils/text_utils.py:62-75`) prefixes each with
  `[Episode N] (timestamp: ...)` so the LLM can attribute facts per-episode
  (`episode_indices` field, `extract_edges.py:48-52`).

VERDICT: Graphiti does NOT de-contextualize from a bare sentence. It always extracts with
surrounding context = the whole current episode + up to 3–10 prior episodes (with their
timestamps) injected as `<PREVIOUS_MESSAGES>`, used for coref/continuity but not as
extraction targets.

### Decontextualization (coref / pronouns / acronyms) — DONE, at extraction time

- Node prompt: "Pronoun references such as he/she/they or this/that/those should be
  disambiguated to the names of the reference entities." (`extract_nodes.py:115-116`).
  Bare relational/kinship terms must be qualified with the possessor — "extract 'Nisha's dad'
  not 'dad'" (`extract_nodes.py:107-110`, `145-147`).
- Edge prompt: "Facts should include entity names rather than pronouns whenever possible."
  (`extract_edges.py:137`); rule 5 forbids generalizing specifics
  ("NEVER generalize 'Gamecube' to 'gaming console'…", `extract_edges.py:157-159`) — i.e.
  the `fact` must be self-contained and keep proper nouns/quantities/descriptors.
- This matches UGM's E2 "Claimify+coref" intent: graphiti resolves references inside the
  extraction call using prior-episode context (cf. D19 "coref-in-call").

### Temporal resolution — DONE, explicit and per-episode

- Edges carry `valid_at` / `invalid_at` ISO-8601 (`extract_edges.py:40-47`).
- `REFERENCE_TIME` resolves relative expressions ("last week"); per-episode timestamps
  override it when multiple episodes are present
  (`extract_edges.py:160`, DATETIME RULES `168-175`, system msg `106-110`).
- "Do **not** hallucinate or infer temporal bounds from unrelated events"
  (`extract_edges.py:161`). Dedicated `extract_timestamps` / `extract_timestamps_batch`
  prompts re-derive bounds ("NEVER hallucinate dates", `extract_edges.py:246, 260, 277`).
- Temporal contradiction handling: `dedupe_edges.resolve_edge` marks
  `contradicted_facts` vs `duplicate_facts` so an updated fact invalidates the prior edge
  (`prompts/dedupe_edges.py:24-32, 43-58`) — "NEVER mark facts as duplicates if they have
  key differences, particularly around numeric values, dates, or key qualifiers."

### (2) SELECTION / FILTERING — yes, aggressive, at BOTH node and edge level

Graphiti does NOT extract everything; it filters what becomes a node or a fact:

- Node-level (the strongest filter). `extract_nodes.extract_message` forbids extracting
  pronouns, abstract concepts/feelings ("joy, balance, growth, resilience, happiness"),
  generic common nouns ("day, life, people, work, stuff, things"), generic media/event/
  institutional nouns, sentence fragments, adjectives, and duplicates
  (`extract_nodes.py:90-112`). Decision rule:
  "Could this have its own Wikipedia article or database entry…?" (`extract_nodes.py:135`).
  "When in doubt, do NOT extract." (`extract_nodes.py:157, 325`).
- Edge-level. Only facts between two DISTINCT entities already in the ENTITIES list, "clearly
  stated or unambiguously implied in the CURRENT MESSAGE" (`extract_edges.py:133-136`).
  Single-entity vague states are dropped:
  "BAD: 'Alice feels happy' (vague single-entity state…)" (`extract_edges.py:150`).
  Semantic-redundancy filter across episodes (`extract_edges.py:154-156`).
- Attribute/summary extraction has a hard "only explicitly stated" gate, no inference:
  `extract_attributes` system msg "You ONLY emit attribute values that are explicitly stated…
  no reasoning, no explanation" (`extract_nodes.py:387-392`, edge variant
  `extract_edges.py:185-190`); "NEVER infer attribute values from the entity's name, from
  related entities, from generic world knowledge…" (`extract_nodes.py:428-430`).
- This is claim/triple-level selection (opinions/feelings/boilerplate dropped). It is NOT a
  separate chunk-level value gate (cf. UGM E1.5 / D25-D30) — filtering is fused INTO the
  extraction prompts, not a pre-pass deciding whether a chunk is worth processing.

### Grounding / faithfulness

- "every concrete noun, number, and descriptor in the source should survive into the `fact`"
  but "Do not verbatim quote the original text" (`extract_edges.py:159`) — paraphrase that
  preserves specifics.
- Entity-name validation rejects edges whose endpoints are not in the extracted ENTITIES
  list (`edge_operations.py:217-223`; prompt rule `extract_edges.py:146`), preventing
  hallucinated subjects/objects.
- Summary prompts: "Use ONLY facts explicitly stated in EPISODES…", "NEVER infer beyond what
  is directly supported", "NEVER manufacture pattern language from a single occurrence"
  (`extract_nodes.py:542-596`).

---

## LETTA (`_additional_context/letta`)

Letta (MemGPT lineage) has NO triple/claim extractor. "Memory" = editable text **memory
blocks** (`human`, `persona`, data-source blocks) maintained by an LLM agent. Extraction =
an LLM agent deciding what prose to write into a block via memory-edit tool calls. There are
two relevant agents: the **sleeptime** memory agent (background) and the **voice sleeptime**
agent. Both operate on a conversation transcript, not on isolated sentences.

### (1) CONTEXT WINDOW — full transcript, not a single sentence

- The sleeptime memory agent is handed a stitched transcript of **prior + recent messages**:
  `transcript_summary = [stringify_message(m) for m in prior_messages + response_messages]`
  then `message_text = "\n".join(transcript_summary)`
  (`letta/groups/sleeptime_multi_agent_v2.py:278-293`; identical pattern in
  `letta/agents/voice_sleeptime_agent.py:205-220`). `prior_messages` are fetched with
  `list_messages(..., before=response_messages[0].id, ...)` (voice_sleeptime_agent.py:209-213).
- The sleeptime system prompt itself states the whole conversation is in scope:
  voice_sleeptime Phase 2 — "integrating information from the **ENTIRE** conversation
  transcript (both `Older` and `Newer` sections)…"
  (`letta/prompts/system_prompts/voice_sleeptime.py:58`).
- The transcript is line-indexed and split into `(Older)` / `(Newer)` regions; the agent
  segments the `(Older)` portion into topic chunks (voice_sleeptime.py:10-12, 21-31).
- Core memory blocks (`human`/`persona`/etc.) are ALSO always in the agent's context window
  ("always available in-context… you will see it at all times",
  `system_prompts/sleeptime_v2.py:7-8`), so memory edits see prior memory + the transcript.

VERDICT: Letta's memory writes are maximally contextual — the LLM sees the full recent
conversation plus existing memory blocks. There is no sentence-level de-contextualization;
if anything, decontextualization is the agent's *job* (resolve relative time, integrate).

### Decontextualization / temporal resolution — INSTRUCTED, agent-discretion

- Explicit absolute-time instruction (appears in multiple prompts):
  "be precise when referencing dates and times (for example, do not write 'today' or
  'recently', instead write specific dates and times, because … the memory is persisted
  indefinitely)" (`sleeptime_v2.py:17`; `sleeptime_doc_ingest.py:23`;
  voice_sleeptime.py:65 "avoid relative terms like 'today' or 'recently'").
- "Infer Sensibly: Add light, well-supported inferences … but do not invent unsupported
  details." (voice_sleeptime.py:64) — note: unlike graphiti, letta explicitly PERMITS light
  inference into memory.
- No structured pronoun/acronym resolver and no `valid_at`/`invalid_at` fields — temporal
  fidelity is whatever prose the LLM writes.

### (2) SELECTION / FILTERING — yes, but soft/LLM-judgment, two forms

1. **store_memories (eviction-driven archival)** — segment evicted dialogue into chunks and
   write a forward-looking blurb per chunk. The selection signal is the `context` field:
   "1-3 sentence paraphrase capturing key facts/details, user preferences, or goals that this
   chunk reveals—written for future retrieval"
   (`letta/functions/function_sets/voice.py:43-46`, `MemoryChunk.context`). Prompt: segment
   `(Older)` "into coherent chunks by topic, instruction, or preference" with "a blurb
   explaining why this chunk matters" (voice_sleeptime.py:11-16). This is selection by
   summarization (which lines matter + why), not drop-vs-keep gating; it does not formally
   discard chit-chat — it just compresses it.
2. **Memory-block editing relevance gate** — the agent is told to be selective:
   "If there are no meaningful updates to make to the memory, you call the finish tool
   directly. Not every observation warrants a memory edit, be selective in your memory
   editing, but also aim to have high recall." (`sleeptime_v2.py:23-25`;
   `sleeptime_doc_ingest.py:29-31`). Refinement principles: "Update: Remove or correct
   outdated or contradictory information." (voice_sleeptime.py:62) — so contradicted/stale
   info is actively pruned during rewrite.

- The memory-edit tools the LLM sees are plain text ops, no claim schema:
  `core_memory_append(label, content)`, `core_memory_replace(label, old, new)`
  (`base.py:246-280`), `memory_replace` / `memory_insert` / `memory_rethink`
  (`base.py:311-520`), `rethink_memory`/`rethink_user_memory` (full block rewrite,
  `base.py:283-302`, `voice.py:10-21`). What becomes "memory" is entirely the LLM's prose
  judgment under these instructions — there is no programmatic opinion/boilerplate filter.

### Grounding / faithfulness

- voice_sleeptime: "do not invent unsupported details" (voice_sleeptime.py:64);
  sleeptime_doc_ingest: "summarize the context and store it in the right memory blocks"
  (sleeptime_doc_ingest.py:36). Faithfulness is prompt-instructed only; no
  validation/verification step exists (UNVERIFIED that any post-hoc grounding check runs —
  none found in these files).

### Contrast vs UGM design

- Letta = block/prose memory with soft LLM relevance gating; closest to UGM's chunk-level
  value gate intuition (E1.5 / D25-D30) but realized as agent discretion ("not every
  observation warrants a memory edit"), not a deterministic gate. No claim/triple layer, no
  temporal edges, no coref resolver — opposite end of the spectrum from graphiti.

---

## Cross-system summary

| | Context window at extraction | Selection/filter | Decontextualize | Temporal resolve |
|---|---|---|---|---|
| Graphiti | current episode + 3–10 prior episodes (w/ timestamps) as `<PREVIOUS_MESSAGES>`; prior context = disambiguation only | YES — drops pronouns/feelings/generic nouns (node) + vague single-entity facts (edge); fused into extract prompt | YES — coref→entity names, qualify bare terms, keep specifics | YES — `valid_at`/`invalid_at`, REFERENCE_TIME, per-episode ts, no-hallucinate, contradiction→invalidate |
| Letta | full recent transcript (prior+recent msgs) + existing memory blocks, line-indexed Older/Newer | SOFT — "be selective… not every observation warrants an edit"; archival = compress-by-topic | Agent's job (integrate); permits light inference | INSTRUCTED only — "absolute dates not 'today'"; no temporal fields |
