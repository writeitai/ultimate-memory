# Value-gate research: mem0 + cognee — does extraction get GATED before LLM cost?

Question: does either system filter/gate what gets extracted *before* spending LLM cost
(value / salience / novelty / dedup / relevance), or do they extract everything?
All citations to actual source under `/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/`.
"Not found" means inspected and absent in this clone.

Bottom line up front:
- **mem0: NO pre-LLM gate. The LLM call is the gate.** Every `add()` (with `infer=True`) makes
  one unconditional LLM extraction call; all filtering (chit-chat drop, dedup, novelty) is
  *delegated into that one prompt* or done *after* the call. Spend-first, filter-inside/after.
- **cognee: NO salience/relevance gate before extraction; extracts every chunk.** The only
  pre-LLM cost savers are (a) file-level content-hash dedup that skips *re-ingesting unchanged
  documents*, and (b) a deterministic skip for DLT/tabular row-chunks. No novelty/value check
  on chunk content, no near-duplicate check across chunks before the LLM runs.

---

## MEM0

### Active ingest path & where the (only) gate is
`mem0/mem0/memory/main.py`, `_add_to_vector_store(self, messages, metadata, filters, infer, ...)`
(line 688). Two branches:

1. **`infer=False` (raw mode), line 689–723:** stores each message verbatim as a memory, *no
   LLM at all*. This is a user-controlled bypass, not a content gate — it doesn't filter, it
   stores everything raw. The only filtering is structural: skip malformed dicts (697) and
   `role == "system"` messages (700–701).

2. **`infer=True` (default) — "V3 PHASED BATCH PIPELINE", line 725+:** the LLM call is
   **unconditional**. There is no value/salience/novelty/length check before it. Sequence:
   - Phase 1 retrieve top-10 existing memories (`top_k=10`, line 738) — for dedup context, not a gate.
   - Phase 2 **single LLM extraction call** (`self.llm.generate_response(..., response_format={"type":"json_object"})`, lines 765–771). One call per `add()`, always fires.
   - Only *after* the call: if the LLM returns nothing, messages are saved and it returns `[]` (791–794).

So mem0 **spends the LLM cost on every turn**; "gating" is what the prompt is *told to drop*,
plus deterministic post-processing.

### The chit-chat / "DROP" filter lives INSIDE the extraction prompt (not before it)
Active prompt `ADDITIVE_EXTRACTION_PROMPT`, `mem0/mem0/configs/prompts.py` (line 468+). It
instructs the LLM to drop low-value content — but the LLM has already been invoked to do so:
- `Do NOT extract:` vague characterizations, generic acknowledgments ("Sure!", "Great
  question!"), assistant meta-commentary (prompts.py 490–493).
- `Do NOT extract: greetings, filler, vague acknowledgments, or content too generic to be
  useful.` (576).
- But anti-over-filtering bias: `**When in doubt, extract.** A slightly redundant memory is far
  less costly than a missing one. The deduplication system downstream will handle true
  duplicates...` (578), and `### Casual Topics Are Still Extractable` — "Only skip messages that
  are PURELY phatic ('Hi!', 'Sounds good!', 'Thanks!') with zero informational content." (580–582).
- `Accuracy and completeness are critical. ... a missed extraction means lost context` (476).

Net design intent: **recall-biased, drop only pure phatic chit-chat, defer dedup downstream.**
This is a *quality* filter, not a *cost* filter — the model is already paid for by the time it
applies these rules.

### Novelty/dedup is delegated to the prompt + done deterministically AFTER the LLM
- **Prompt-level novelty (inside the same paid call):** "Recently Extracted Memories ... This is
  your primary deduplication reference — do not re-extract" (prompts.py 501–503); "If new
  information ... is semantically equivalent to an Existing Memory with no meaningful new
  context, skip it." (511). The LLM is asked to suppress near-duplicates, but only as part of the
  call that already ran.
- **Post-LLM exact dedup (code, deterministic):** Phase 4/5 MD5-hash of each extracted text vs
  existing hashes and within-batch `seen_hashes`; skip on match (main.py ~810–828). **Byte-exact
  only** — a one-word paraphrase defeats it. No fuzzy/semantic dedup in code.

### The ADD/UPDATE/DELETE/NOOP novelty controller is DORMANT (the 0.95 gate is elsewhere)
- `DEFAULT_UPDATE_MEMORY_PROMPT` (prompts.py 176; defines ADD/UPDATE/DELETE/**NONE**, "NONE:
  Make no change (if the fact is already present or irrelevant)", line 185) and its driver
  `get_update_memory_messages` (prompts.py 406) **have zero call sites in `memory/main.py`**
  (grep confirms). The active pipeline emits only `event: "ADD"` (main.py 718, 875, 987). So the
  classic novelty/reconciliation controller is **not wired** in this clone; UPDATE/DELETE happen
  only via explicit user-invoked `Memory.update()` / `Memory.delete()` API methods.
- The **`>= 0.95` gate is NOT a memory-write/novelty gate.** Every `0.95` occurrence in main.py
  (lines 452, 944, 1933, 2396) is in **entity-store resolution** — deciding whether a
  spaCy-extracted entity span equals an existing entity (append `memory_id` if cosine ≥ 0.95,
  else new entity record). It governs entity *identity merge*, not whether a memory is novel
  enough to extract or store. It runs *after* extraction and embeds, so it spends embedding cost,
  not LLM cost, and it never blocks a memory from being written.

### Where mem0 SPENDS vs SAVES LLM cost
- **Spends:** exactly one LLM extraction call per `add()` in infer mode (main.py 765), regardless
  of message value. Plus query-time search has no extra LLM (deterministic hybrid scoring).
- **Saves:** `infer=False` skips the LLM entirely (raw store); empty/whitespace LLM output is
  short-circuited (791); JSON repair avoids a re-call (`remove_code_blocks`/`extract_json`,
  778–786) rather than retrying the model. Context to the call is bounded — last 10 messages
  (729), top-10 existing memories (738), `PAST_MESSAGE_TRUNCATION_LIMIT = 300` chars
  (prompts.py 965) — which caps token cost per call but does not gate *whether* to call.
- **Cost/quality numbers in repo:** none in the inspected Python source. Eval framework exists
  (`evaluation/`, LOCOMO per CLAUDE.md) but no cost/latency/accuracy figures are present in code.

---

## COGNEE

### cognify path & the (absence of a) salience gate before extraction
`cognee/cognee/tasks/graph/extract_graph_from_data.py`, `extract_graph_from_data(...)` (line 129).
After structural validation only (non-empty list, each chunk has `.text`, valid graph model;
142–147), it runs the LLM on **every** chunk:
```python
chunk_graphs = await asyncio.gather(*[
    extract_content_graph(chunk.text, graph_model, custom_prompt=custom_prompt, **kwargs)
    for chunk in non_dlt_chunks
])                                                  # lines 166–173
```
There is **no salience / relevance / importance / novelty filter on chunk content** before this
fan-out. `importance_weight` exists on chunks/datapoints (default `0.5`,
`modules/chunking/models/DocumentChunk.py:36`; `modules/chunking/TextChunker.py:33,53,76`) but it
is **carried metadata, never used to skip extraction** — it's an unconditioned constant, and the
merge-time use is an explicit `# TODO` (per prior cognee.md §1). So cognee **extracts every
chunk**; the LLM cost scales with chunk count, ungated by content value.

### The only pre-LLM cost savers cognee has (both are dedup/structural, not value/salience)
1. **File-level content-hash dedup (skip re-ingest of unchanged documents).**
   `cognee/cognee/tasks/ingestion/ingest_data.py`: each `Data` record stores a `content_hash`
   (194); on re-add, `content_changed = str(data_point.content_hash) != str(new_content_hash)`
   (150–151). If unchanged and already in the dataset, it goes to `existing_data_points` rather
   than `dataset_new_data_points` (173–178), and `pipeline_status` is only reset when content
   changed (170–171). Comment at line 116: "data_id is the hash of original file contents + owner
   id to avoid duplicate data." This avoids re-cognifying an identical file — a coarse, exact
   **document-level** novelty check, not a content-value gate and not sub-document.
2. **Deterministic skip for DLT/tabular row-chunks (no LLM at all).**
   `extract_graph_from_data.py` 149–159: chunks whose document is a `DltRowDocument` are split
   out (`dlt_chunks`) and **excluded from LLM extraction** — "Skip LLM extraction for DLT row
   chunks — their graph is built deterministically by extract_dlt_fk_edges from schema metadata."
   If *all* chunks are DLT, it returns early with zero LLM calls (158–159). This is the one place
   cognee swaps LLM extraction for deterministic structure — driven by source *type*, not value.

### Other dedup is exact-key and runs AROUND/AFTER extraction, not as a pre-LLM gate
- `uuid5(NAMESPACE_OID, normalized_name)` node identity, `has_edges([...])` existing-edge
  existence check, and final id-based node/edge dedup (per prior cognee.md §1) make ingestion
  *idempotent* on `(s,p,o)` — but the **LLM has already run** on the chunk by then. No
  near-duplicate-chunk check suppresses the call.
- Cascade extraction (`extract_graph_from_data_v2.py`, `n_rounds=2`) *adds* LLM rounds for recall;
  it is a quality/cost-up knob, the opposite of a gate.

### Where cognee SPENDS vs SAVES LLM cost
- **Spends:** one structured-output LLM extraction per non-DLT chunk (`extract_content_graph`,
  main path), unconditionally; optional `consolidate_entity_descriptions` memify pass is one LLM
  call *per entity* over the whole graph (per prior cognee.md §5) — global, not gated; temporal
  event extraction is per-chunk; search-time GRAPH_COMPLETION/CoT add query-time LLM calls.
- **Saves:** unchanged-file content-hash skip (no re-cognify); DLT-row deterministic skip (no LLM);
  client-side rate limiting (`LLM_RATE_LIMIT_REQUESTS=60`/`60s`, CLAUDE.md) throttles but doesn't
  gate by value. Default model `openai/gpt-4o-mini` is the main per-token cost lever.
- **Cost/quality numbers in repo:** `evals/benchmark_summary_cognee.json` reports **accuracy
  only** (e.g. Graph Completion CoT: Human-like Correctness 0.925, DeepEval Correctness 0.846, F1
  0.841; plain Graph Completion ~0.805 correctness). **No cost, token, or latency figures** in the
  inspected files. Research paper arxiv 2505.24478 referenced but not in repo.

---

## Relevance to ugm design (objections.md O3; decisions D1/D4/D7/D12; overall_design planes E/K/P)
- Both systems are **"extract-then-filter," not "filter-then-extract."** Neither implements a
  cheap pre-LLM value/salience/novelty gate of the kind O3 worries about — they pay the LLM on
  every turn (mem0) / every chunk (cognee) and rely on prompt instructions + downstream exact
  dedup to control volume. This is the anti-pattern a D4 cheap-first cascade and a D12 trigger
  model are meant to avoid: mem0/cognee have no trigger that *withholds* the expensive call.
- The closest things to a real pre-LLM gate are **exact-equality** mechanisms: mem0's MD5 memory
  dedup (post-LLM) and cognee's file content-hash (pre-LLM, document-level) + DLT type-skip. None
  is a *semantic* novelty or value gate; all are trivially defeated by paraphrase or sub-document
  novelty. Useful as ugm's cheapest cascade tier (exact-hash short-circuit) but **insufficient as
  the gate** — confirming the design's need for a salience/novelty tier the upstream LLM call is
  conditioned on, which neither repo provides.
- mem0's recall-bias maxim ("When in doubt, extract ... dedup downstream", prompts.py 578) is a
  deliberate stance *against* aggressive gating — worth noting as the opposite pole to a
  cost-conscious value gate. The dormant ADD/UPDATE/DELETE/NONE controller (prompts.py 176–185)
  shows even mem0's own novelty controller is currently *unused* in the active path.
