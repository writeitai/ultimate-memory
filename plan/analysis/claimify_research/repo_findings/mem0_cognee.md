# mem0 + cognee — extraction context window & selection/filtering (code archaeology)

Scope: the two cross-cutting questions for every system —
**(1) Context window**: when extracting a claim/fact/triple, what text does the extraction LLM actually *see* (only the target chunk/sentence, or also neighbors/document/summary/prior episodes)?
**(2) Selection/filtering**: does it decide *which* content becomes a claim (drop opinions/boilerplate/chit-chat), or extract everything?
Plus: decontextualization (pronouns/acronyms/time) and grounding/faithfulness.

VERIFIED = read in the actual checked-out source. INFERRED / COULD-NOT-VERIFY flagged inline. No benchmark numbers are reported (none were measured here).

---

## IMPORTANT: this is a *modified fork*, not stock mem0

The local checkout at `_additional_context/mem0` does **not** run the classic public-mem0 two-call pipeline (separate `FACT_RETRIEVAL_PROMPT` extraction call, then `DEFAULT_UPDATE_MEMORY_PROMPT` ADD/UPDATE/DELETE/NONE call). Those prompts and helper functions still physically exist in the repo but are **dead code on the add path**:

- `get_fact_retrieval_messages`, `get_fact_retrieval_messages_legacy`, `USER_MEMORY_EXTRACTION_PROMPT`, `AGENT_MEMORY_EXTRACTION_PROMPT`, `get_update_memory_messages`, `DEFAULT_UPDATE_MEMORY_PROMPT` are defined in `mem0/configs/prompts.py` / `mem0/memory/utils.py` but are **never imported/called** from `mem0/memory/main.py`. VERIFIED: `grep get_fact_retrieval_messages|get_update_memory_messages|USER_MEMORY_EXTRACTION_PROMPT` across `mem0/mem0/` returns hits only inside their own definition files.
- The live `add` path is a single-call **"V3 phased batch pipeline"** using `ADDITIVE_EXTRACTION_PROMPT` + `generate_additive_extraction_prompt(...)`. VERIFIED: `mem0/mem0/memory/main.py:725-771` (sync) and `:2177-2222` (async `AsyncMemory`), both reached via `_add_to_vector_store(... infer=True)`.

Both the classic design AND the live fork design are documented below because the design-context brief (decisions.md, overall_design.md) references the canonical mem0 fact-extraction + ADD/UPDATE/DELETE/NOOP controller.

---

## mem0 — LIVE fork path (V3 additive extraction)

### (1) Context window: SINGLE LLM CALL, sees the new turn(s) PLUS retrieved memories PLUS last-10 history
mem0's extractor does **not** see only the target message in isolation. The single `system+user` call assembles several context blocks (`main.py:725-771`):

- **New Messages** — the current turn(s), serialized by `parse_messages()` into `"role: content\n"` lines across user/assistant/system (`utils.py:61-70`). NOTE: `parse_messages` *does* concatenate `system:` lines too, but the system prompt instructs the model what to attribute (it does not hard-strip system text the way the legacy `_add_to_vector_store(infer=False)` branch does).
- **Last k Messages** — up to the **last 10** prior messages of the session, pulled from a local SQLite/store cache: `last_messages = self.db.get_last_messages(session_scope, limit=10)` (`main.py:729`; storage signature `get_last_messages(self, session_scope, limit: int = 10)` at `storage.py:298`). Truncated to 300 chars each (`prompts.py:965 PAST_MESSAGE_TRUNCATION_LIMIT = 300`, `_format_conversation_history` `prompts.py:982-992`). Prompt purpose: *"Recent messages (up to 20) preceding New Messages. Use to resolve references and pronouns in New Messages."* (`prompts.py:519-521`).
- **Existing Memories** — top-10 semantically retrieved existing memories, UUID-remapped to integer ids "0".."9" for anti-hallucination, passed as `[{"id","text"}]` (`main.py:735-747`). Prompt: *"Use these ONLY for deduplication and linking — do NOT extract new memories from Existing Memories."* (`prompts.py:506-516`).
- **Summary** and **Recently Extracted Memories** sections are *documented* in the prompt (`prompts.py:496-503`) and supported by `generate_additive_extraction_prompt` params, **but `main.py` never passes `summary=` or `recently_extracted_memories=`** (only `existing_memories`, `new_messages`, `last_k_messages`, `custom_instructions` — `main.py:757-762`). So in this fork those two blocks render empty (`_format_summary`→"", `_serialize_memories(None)`→"[]"). COULD-NOT-VERIFY that any other caller populates them in this checkout.

So: **target turn is NOT decontextualized in isolation** — the extractor is explicitly given recent conversational history (for coref) and retrieved memories (for dedup/linking). This is much richer context than classic mem0.

### (2) Selection/filtering: YES — drops phatic chit-chat, but deliberately KEEPS casual personal facts
The `ADDITIVE_EXTRACTION_PROMPT` is a value/selection gate, but tuned *toward inclusion*:
- Drops: *"greetings, filler, vague acknowledgments, or content too generic to be useful"* (`prompts.py:576`); *"Generic assistant acknowledgments ('Sure!', 'Great question!')"*, *"Vague assistant characterizations"*, *"Assistant meta-commentary about its own capabilities"* (`prompts.py:490-493`).
- Explicitly REFUSES to treat casual content as droppable chit-chat: *"Conversations about pets, hobbies, childhood memories, funny anecdotes, and personal preferences are NOT 'chitchat' to be skipped... Only skip messages that are PURELY phatic ('Hi!', 'Sounds good!', 'Thanks!') with zero informational content."* (`prompts.py:580-582`).
- Bias: *"When in doubt, extract. A slightly redundant memory is far less costly than a missing one."* (`prompts.py:578`). This is the OPPOSITE of a strict claim-worthiness filter.
- Dedup/novelty is folded into the same call (linking via `linked_memory_ids`, skip if semantically equal to an Existing Memory `prompts.py:511`) PLUS a downstream exact-hash dedup (`md5(text)` vs existing/seen hashes, `main.py:825-829`). There is **no separate LLM novelty/UPDATE/DELETE call** on this path — `ADD`-only ("Your sole operation is ADD", `prompts.py:472`).

### Decontextualization & grounding (live fork)
- **Pronouns**: *"Self-Contained ... Replace all pronouns with specific names or 'User.'"* (`prompts.py:628-629`); coref resolved using the Last-k history block.
- **Time**: strong relative→absolute grounding against an **Observation Date** anchor (NOT current date): *"'User went to Paris last week' is useless 6 months later"* (`prompts.py:524-535, 634-635`). NOTE: in this fork `main.py` passes no `timestamp=`/`current_date=`, so `_resolve_dates` defaults both Observation and Current date to `utcnow().date()` (`prompts.py:1007-1013`) — the temporal-anchor machinery is present but unfed on the default add call. COULD-NOT-VERIFY a caller that supplies observation date.
- **Faithfulness**: *"No Fabrication... If you can't point to where it came from, don't include it"*; *"No Detail Contamination from Context"* — must NOT merge details from Existing/Recent memories into a new extraction unless the new message references them (`prompts.py:677-689`); preserve proper nouns/numbers exactly (`prompts.py:640-666`).

### mem0 — CLASSIC path (dead here, but is the design-context reference)
- **Context window**: extractor sees `parse_messages(messages)` of the current batch only (system stripped) — no retrieval, no summary. Then a *separate* UPDATE call sees `[extracted facts]` + retrieved old memories. Prompts: `FACT_RETRIEVAL_PROMPT` (`prompts.py:15-60`), `get_update_memory_messages` (`prompts.py:406-...`).
- **Selection**: `FACT_RETRIEVAL_PROMPT` is the canonical chit-chat dropper — `Input: "Hi." → {"facts": []}`, `Input: "There are branches in trees." → {"facts": []}` (`prompts.py:29-33`); user/assistant-only, ignore system (`prompts.py:55`).
- **Novelty controller**: `DEFAULT_UPDATE_MEMORY_PROMPT` = the ADD / UPDATE / DELETE / NONE four-op controller (`prompts.py:176-324`), with worked examples (merge "cheese pizza"+"chicken pizza"→UPDATE; "Dislikes cheese pizza"→DELETE the contradicted memory; etc.).

---

## cognee — knowledge-graph triple extraction

### (1) Context window: ONE CHUNK AT A TIME, ZERO surrounding context
This is the strongest finding. The extractor sees **only `chunk.text`** — no neighbor chunks, no parent document, no running summary, no prior episodes.

- Default path: `extract_graph_from_data` fans out one LLM call per chunk via `asyncio.gather([extract_content_graph(chunk.text, graph_model, ...) for chunk in non_dlt_chunks])` (`cognee/tasks/graph/extract_graph_from_data.py:166-173`).
- `extract_content_graph(content, response_model, custom_prompt)` passes `content` straight through to `LLMGateway.acreate_structured_output(content, system_prompt, response_model)` (`cognee/infrastructure/llm/extraction/knowledge_graph/extract_content_graph.py:13-37`). The `{}` context dict means the system prompt is static, not enriched (`:31`).
- The adapter builds the literal call: `messages=[{"role":"system","content":system_prompt},{"role":"user","content": f"""{text_input}"""}]` — i.e. the user message is **exactly the chunk text, nothing prepended/appended** (`cognee/infrastructure/llm/structured_output_framework/litellm_instructor/llm/openai/adapter.py:148-156`; same shape in the gemini/anthropic/ollama/azure adapters).
- Cascade path (`extract_graph_from_data_v2.py`) is also strictly per-chunk: `extract_nodes(chunk.text, n_rounds)`, then `extract_content_nodes_and_relationship_names(chunk.text, nodes, ...)`, then `extract_edge_triplets(chunk.text, nodes, rels, ...)` — multi-round, but every round's text input is still just that one chunk's text (`extract_graph_from_data_v2.py:40-58`).
- Granularity: `DocumentChunk.text` is a single mid-size chunk (`chunk_index`, `chunk_size`, `cut_type` fields — `cognee/modules/chunking/models/DocumentChunk.py:30-33`). So extraction is **chunk-scoped, fully de-contextualized from the rest of the document.**

### (2) Selection/filtering: NO salience/value/chit-chat gate — extract-everything
- The default prompt `generate_graph_prompt.txt` is "extract all entities + relationships" with quality constraints, **no instruction to drop opinions, chit-chat, boilerplate, or to judge importance/worthiness**. It only forbids outside knowledge: *"Do not add outside knowledge."* (`generate_graph_prompt.txt:7`) and aims for *"simplicity and clarity"* (`:11`). VERIFIED: a repo-wide grep for `salien|relevan|importan|chit.?chat|boilerplate|trivial|worth remember` across `cognee/tasks/graph` + `cognee/infrastructure/llm/prompts` finds **no value/salience filter** on the default path.
- The closest thing to selection is in the **cascade** edge-triplet prompt: *"Exclude trivial, redundant, or nonsensical triplets, keeping only meaningful and well-structured connections"* (`cognee/tasks/graph/cascade_extract/prompts/extract_graph_edge_triplets_prompt_system.txt:6`). That is **structural triple-quality pruning, not content-value/chit-chat filtering** — it removes malformed/redundant triples, not opinions or boilerplate.
- The event-graph prompt is the opposite of selective — *"ANY action or verb represents an event"*, *"Granularity and richness ... is of utmost importance"* (`generate_event_graph_prompt.txt:6,15`).
- Filtering that DOES exist is **post-extraction structural**, not pre-extraction value: dangling edges (source/target not in node set) are dropped in Python (`extract_graph_from_data.py:181-188`); ontology validation/dedup in `integrate_chunk_graphs` (`:99-125`). DLT row chunks skip the LLM entirely (deterministic FK edges) (`:149-159`).

### Decontextualization & grounding (cognee)
- **Coref**: resolved **only within the chunk** — *"If an entity is mentioned multiple times in the text but is referred to by different names or pronouns, always use the most complete identifier"* (`generate_graph_prompt.txt:28-32`). Because the call sees no neighbor chunks, an entity introduced in chunk N-1 and pronoun-referenced in chunk N **cannot** be resolved — a structural de-contextualization risk.
- **Time**: dates normalized to `YYYY-MM-DD` when present *in the chunk* (`generate_graph_prompt.txt:21-24`); no document-level "as-of" anchor on the default path. (A separate temporal/event-graph pipeline exists, `tasks/temporal_graph/*`, not the default.)
- **Grounding/faithfulness**: enforced by *"Do not add outside knowledge"* + structured-output schema (`KnowledgeGraph` = nodes{name,type,description}, edges{relationship_name, description} — `cognee/shared/data_models.py:20-44`). No explicit "every claim must trace to a source span" rule like Claimify; faithfulness rests on the no-outside-knowledge instruction plus the empty `{}` context (nothing extra to leak in).

---

## Cross-system contrast (for UGM design)
- **mem0 (live fork)**: rich context at extraction (recent history + retrieved memories), selection gate that drops *only* phatic chit-chat while deliberately keeping casual personal facts, ADD-only single call with dedup/linking folded in. Strong decontextualization mandate (self-contained, pronoun-resolved, time-anchored) — but the observation-date and summary inputs are wired-but-unfed on the default add call in this checkout.
- **mem0 (classic, the design reference)**: two calls — chit-chat-dropping fact extraction, then ADD/UPDATE/DELETE/NONE novelty controller; extractor sees only current batch.
- **cognee**: extract-everything per chunk, no value/salience filter, **zero cross-chunk context** — the purest de-contextualization case; coref is chunk-local only.
