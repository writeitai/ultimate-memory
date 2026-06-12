# Key findings

1. `ugm` currently has no pre-E2/E3 value gate: E0→E1→E2/E3 runs Claimify, coref, entity resolution, relation normalization, and supersession on every document/chunk ([`overall_design.md:92-101`](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:92)). O3 correctly identifies this as the biggest missing cost lever: most million-document corpora contain boilerplate, duplicates, and low-value filler ([`objections.md:65-82`](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/analysis/objections.md:65)).
2. The cloned systems mostly do **post-extraction cleanup**, not cheap pre-extraction gating. GraphRAG and Cognee extract graph data from every chunk that reaches the graph step. LightRAG dedupes full documents/chunks and caps “high-value” outputs, but still calls the extraction LLM per new chunk. Mem0 has prompt-level filtering and dedupe/novelty behavior, but the cheap decision usually happens after retrieval/embedding or inside an LLM call.
3. The Mem0 “~98% junk” claim is real but not peer-reviewed: it is a GitHub issue audit of 10,134 production entries reporting 224 survivors, or 97.8% junk, with batch rates mostly 95–98% and explicit categories like boot-file restating, cron noise, architecture dumps, and hallucinated profiles ([GitHub issue #4573](https://github.com/mem0ai/mem0/issues/4573), lines 202-210, 220-249).
4. The best cheap gate is not one technique. Use a cascade: deterministic dedup + structural role detection + cheap density/source features + embedding novelty + demand signal, with a calibrated small classifier only after heuristics. Small-LLM judging should be rare and reserved for borderline/high-impact material.
5. Recommendation: insert a gate at both **E0/E1** and **E1/E2**. Always keep E0/E1 chunks and embeddings for retrieval; decide whether each document/section/chunk gets `FULL`, `DEFERRED`, or `CHUNKS_ONLY` before E2/E3. This matches D4’s cheap-first cascade ([`decisions.md:66-80`](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:66)), D7 rebuild discipline ([`decisions.md:116-133`](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:116)), and D12’s staged per-document trigger model ([`decisions.md:213-224`](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:213)).

# Evidence from cloned systems

## Mem0

Mem0’s fact extraction prompt is a **semantic filter inside an LLM call**, not a cheap pre-call gate. The older `FACT_RETRIEVAL_PROMPT` tells the model to return empty facts for “Hi” and generic statements, and says to return an empty list if no relevant facts are found ([`mem0/configs/prompts.py:29-35`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/configs/prompts.py:29), [`prompts.py:54-58`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/configs/prompts.py:54)). The newer additive prompt is broader: it says not to extract greetings/filler/generic acknowledgments, but also says “when in doubt, extract” and treats casual revelations as valuable ([`prompts.py:576-582`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/configs/prompts.py:576)).

Mem0 has a novelty/update controller prompt with `ADD`, `UPDATE`, `DELETE`, and `NONE`; `NONE` is for already-present or irrelevant facts ([`prompts.py:176-186`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/configs/prompts.py:176)). But in the current v3 path, `Memory.add` uses an ADD-only extraction prompt and links to existing memories rather than making an update/delete/noop decision in that step ([`main.py:749-771`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/memory/main.py:749)). It first embeds the parsed messages, searches the vector store for existing memories, and passes top-10 into the extraction prompt ([`main.py:732-748`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/memory/main.py:732)). That spends embedding/vector-search cost before extraction, then still spends one LLM extraction call.

Where it saves: exact hash dedup after extraction skips duplicate memory writes ([`main.py:810-829`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/memory/main.py:810)); custom instructions can steer extraction ([`prompts.py:543-548`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/configs/prompts.py:543), [`prompts.py:1044-1045`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/mem0/mem0/configs/prompts.py:1044)). Where it spends: extraction LLM still runs before the dedup hash and entity-linking work.

## GraphRAG

GraphRAG extracts from every `text_unit`. `create_base_text_units` streams every document, chunks it, writes each chunk, and only skips `None` chunk text ([`create_base_text_units.py:99-111`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphrag/packages/graphrag/graphrag/index/workflows/create_base_text_units.py:99)). The graph workflow reads all text units, creates the extraction model, and calls `extract_graph` across them ([`extract_graph.py:38-67`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphrag/packages/graphrag/graphrag/index/workflows/extract_graph.py:38), [`extract_graph.py:113-125`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphrag/packages/graphrag/graphrag/index/workflows/extract_graph.py:113)).

The prompt says the text is “potentially relevant” and asks to identify all entities/relationships of configured types ([`prompts/index/extract_graph.py:6-27`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphrag/packages/graphrag/graphrag/prompts/index/extract_graph.py:6)). The extractor runs one LLM completion per row, then optional gleaning calls to find missed entities/relationships ([`graph_extractor.py:85-122`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphrag/packages/graphrag/graphrag/index/operations/extract_graph/graph_extractor.py:85)). Claim extraction, when enabled, similarly iterates through texts and runs an LLM with optional gleaning ([`claim_extractor.py:81-98`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphrag/packages/graphrag/graphrag/index/operations/extract_covariates/claim_extractor.py:81), [`claim_extractor.py:119-163`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphrag/packages/graphrag/graphrag/index/operations/extract_covariates/claim_extractor.py:119)). There is no value gate. Savings come from caching and configurable `max_gleanings`, not from avoiding initial extraction.

## LightRAG

LightRAG has better ingestion hygiene but still no salience gate. It dedupes full docs by key and chunks by content hash before extraction: duplicate docs return early, and already-stored chunks are removed from `inserting_chunks` ([`lightrag.py:1403-1438`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/lightrag/lightrag/lightrag.py:1403)). New chunks are simultaneously embedded, stored, and sent to `_process_extract_entities` ([`lightrag.py:1440-1446`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/lightrag/lightrag/lightrag.py:1440)).

The extraction function processes every ordered chunk through an extraction LLM call ([`operate.py:3320-3353`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/lightrag/lightrag/operate.py:3320), [`operate.py:3485-3495`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/lightrag/lightrag/operate.py:3485)). Optional gleaning may add a second extraction call, though it is skipped if token budget would be exceeded ([`operate.py:3519-3563`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/lightrag/lightrag/operate.py:3519)). The prompt contains useful salience language: output fewer rows if fewer high-value items are present; prioritize relationships most significant to the core meaning ([`prompt.py:91-101`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/lightrag/lightrag/prompt.py:91), [`prompt.py:198-203`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/lightrag/lightrag/prompt.py:198)). But that is inside the expensive call.

Where it saves: doc/chunk dedup, LLM response cache, max extracted records, optional gleaning guard, source-id caps, and description dedupe/merge ([`operate.py:2141-2149`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/lightrag/lightrag/operate.py:2141)). Where it spends: all non-duplicate chunks still hit extraction.

## Cognee

Cognee’s default `cognify` pipeline is explicit: classify documents, chunk them, LLM-extract graph and summarize, then persist ([`cognify.py:316-340`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/cognee/cognee/api/v1/cognify/cognify.py:316)). Classification is file-type routing, not value scoring; it maps extensions to document classes and assigns a default `importance_weight` of `0.5` if none exists ([`classify_documents.py:19-57`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/cognee/cognee/tasks/documents/classify_documents.py:19), [`classify_documents.py:132-142`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/cognee/cognee/tasks/documents/classify_documents.py:132)). Chunk extraction yields every chunk read from each document ([`extract_chunks_from_documents.py:50-59`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/cognee/cognee/tasks/documents/extract_chunks_from_documents.py:50)).

Graph extraction calls `extract_content_graph` for every non-DLT chunk via `asyncio.gather` ([`extract_graph_from_data.py:149-173`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/cognee/cognee/tasks/graph/extract_graph_from_data.py:149)). DLT row chunks are the exception: they skip LLM extraction because deterministic FK edges handle them ([`extract_graph_from_data.py:149-159`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/cognee/cognee/tasks/graph/extract_graph_from_data.py:149)). Cognee also has incremental pipeline skip for already-completed data items ([`run_tasks_data_item.py:85-103`](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/cognee/cognee/modules/pipelines/operations/run_tasks_data_item.py:85)). Again: useful dedup/incremental behavior, no salience gate.

# Cheap value-scoring signals

Best predictive signals:

- **Exact/near duplication**: content hash, normalized hash, SimHash, MinHash. This is the highest-confidence save. Exact duplicates should be `CHUNKS_ONLY` or skipped for E2/E3; near-duplicates should route to `DEFERRED` unless they contain new named entities, dates, numbers, or section role differences.
- **Structural role**: PageIndex section labels, heading text, DOM/PDF layout, repeated headers/footers, nav/sidebar, references, legal boilerplate, license text, changelog boilerplate. Strongly predictive because low-value text often has stable structural fingerprints. References sections should usually not get FULL extraction except citation graph extraction.
- **Source trust/type**: curated docs, user-authored notes, decisions, specs, contracts, papers’ abstract/results sections, incident reports, and meeting decisions score higher than scraped nav pages, generated logs, generic docs, or transient chat.
- **Information density**: named entities per token, dates/numbers/units per token, verb/assertion density, modal/hedge ratio, unique content words, table/code/formula markers. Predictive at chunk scale, but can overvalue reference lists and index pages.
- **Novelty against existing claims/chunks**: embedding distance to nearest extracted claims/relations and nearest chunks; pair this with lexical near-dup to avoid embedding false positives. Good for large corpora, but thresholds must be domain-specific.
- **Query demand**: retrieval hits, user opens, compiled-scope interest, entity watchlists, failed-answer traces. This is the best signal for lazy promotion from `DEFERRED` to `FULL`.

Noisy signals:

- **Length alone**: long can mean high-value paper body or giant boilerplate. Very short chunks are often poor extraction candidates, but titles, decisions, and table rows can be valuable.
- **Perplexity/readability**: useful for detecting generated sludge, OCR failure, or logs, but weak as a value proxy.
- **Raw entity count**: high entity density can be references, nav menus, or contact lists. Use entity density only with structural role and novelty.

# Mechanism options

- **Pure heuristics**: regex/layout/hash/source rules. Cost is effectively CPU-only, usually <0.1% of extraction cost. Accuracy is high for boilerplate/dedup, poor for subtle value. Use as hard reject/accept rules.
- **Near-dup pre-pass**: SHA-256 normalized hash, SimHash for line/page boilerplate, MinHash LSH for sections/chunks. Cost is tiny compared with LLM extraction; memory/index overhead is manageable. This should run before E1 embedding where possible, and before E2 always.
- **Embedding novelty threshold**: one embedding per chunk already exists in E1. Compared with E2/E3 extraction, embedding is usually one to two orders of magnitude cheaper than LLM extraction; nearest-neighbor lookup is cheaper still. Good `DEFERRED` signal, not a sole reject criterion.
- **Small trained classifier**: features above plus labels from audit. Fast, batchable, cheap. Best long-term option once a few thousand audited chunks exist. It can learn source/section interactions that rules miss.
- **Small-LLM judge**: use only for borderline chunks or high-trust docs where recall loss is expensive. Even a small judge can cost 10–30% of extraction if it reads the same chunk, so it must be sparse. It is not the default gate.

# External evidence

The Mem0 audit source is a GitHub issue, not a formal paper. Still, it is concrete: 10,134 entries pulled from a 32-day production run; 224 survived; 38 were clean enough to keep unchanged; reported junk rate was 97.8% ([GitHub issue #4573](https://github.com/mem0ai/mem0/issues/4573), lines 202-210, 237-255). The same issue says message-level filtering caught some noise but could not address extraction-layer problems like boot-file restating, architecture dumps, hallucinated profiles, and feedback-loop amplification ([issue lines 260-289](https://github.com/mem0ai/mem0/issues/4573)).

There is broader support that indiscriminate memory hurts: Harvard Business School’s AI Institute summarizes a study where “add-all” memory underperformed no memory addition across EHR, autonomous driving, and network-security agents, while strict filtering before storage gave an average 10% boost ([HBS AI Institute](https://aiinstitute.hbs.edu/smarter-memories-stronger-agents-how-selective-recall-boosts-llm-performance/), lines 52-53).

For graph RAG, DEG-RAG reports that LLM-generated KGs often contain redundant entities and unreliable relationships that degrade retrieval/generation and increase cost ([OpenReview](https://openreview.net/forum?id=y1EQ5EH5zF), lines 22-26). The arXiv version says denoising by entity resolution and triple reflection improves four graph-RAG variants across four QA datasets while reducing roughly half of entities/relations, and up to 70% entity reduction can preserve or improve quality in some settings ([arXiv](https://arxiv.org/html/2510.14271v1), lines 183-206). Chunk filtering evidence points the same direction: entity-based chunk filtering reduced vector index size by about 25–36% while maintaining retrieval quality near baseline ([arXiv](https://arxiv.org/html/2604.24334v1), lines 61-64).

# Recommendations for the ugm design

Place the gate in two stages:

1. **E0/E1 document-section gate**: after markdown/PageIndex, before chunk extraction finalization. Compute source trust, structural role, boilerplate fingerprints, doc/section hash, section type, and rough density. Mark sections as candidate `FULL`, `DEFERRED`, or `CHUNKS_ONLY`.
2. **E1/E2 chunk gate**: after chunks and embeddings exist, before Claimify/coref/entity-resolution. Add embedding novelty, near-duplicate status, chunk density, entity/date/number counts, and query-demand/compiled-scope demand.

Tier semantics:

- **FULL**: run E2/E3 now. High-trust source, body/results/decision/spec content, high novelty, dense assertions, important watched entities, or active demand.
- **DEFERRED**: keep chunks/embeddings and queue for lazy extraction. Trigger when retrieved N times, linked to a watched entity/scope, selected by K compiler, or part of an answer failure.
- **CHUNKS_ONLY**: never run E2/E3 by default. Boilerplate, nav, references, duplicate chunks, logs, generic acknowledgments, repeated legal/license text. Still searchable in P1 for provenance.

Initial scoring formula should be transparent:

`score = source_prior + structural_role + density + novelty + demand - duplicate_penalty - boilerplate_penalty - staleness/transience_penalty`

Start with hard rules plus logistic regression or LightGBM over features. Do not start with a small-LLM judge as the primary mechanism. Use small-LLM review only for chunks near the FULL/DEFERRED boundary in high-trust documents.

Measure:

- Filter rate by source/section type.
- E2/E3 spend saved: tokens, calls, dollars, wall time.
- Recall loss on a golden set: missed claims/relations from gated-out chunks.
- Junk rate in extracted claims/relations.
- Duplicate relation evidence avoided.
- Lazy-promotion yield: percent of `DEFERRED` chunks later promoted and useful.
- Downstream retrieval/K quality: relation recall@k, answer success, graph size, orphan/duplicate entity rates.

Target operating point: first deployment should aim to skip 50–80% of E2/E3 calls with <2–5% loss of gold high-value claims. The 10x lever is plausible only when combined with near-dup/boilerplate elimination and lazy extraction, not with prompt-only filtering.
