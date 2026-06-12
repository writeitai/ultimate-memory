# R6 — High-precision, scalable claim/relation extraction into a governed schema

Second, independent take (a Codex agent covers the same question). Scope: free-form vs typed/JSON-schema vs grammar-constrained decoding; single- vs multi-pass gleaning; closed-IE vs OpenIE precision/recall; the cost of ugm's closed-with-`other:`-escape hybrid; which constrained-decoding tools (Outlines/grammars, GLiNER, tool-calling) materially help; static vs dynamic rendering of a growing predicate set; decontextualization-vs-minimality. Recommends the E2→E3 extraction design and what to measure.

Evidence is tagged **[VERIFIED-repo]** (read in our cloned source / repo_findings), **[VERIFIED-web]** (cited source), **[INFERENCE]** (my reasoning), **[UNCERTAIN]** (could not confirm).

---

## 1. Key findings

- **Every production memory/KG system we cloned uses typed structured output (Pydantic/JSON), NOT free-form prose and NOT grammar-constrained decoding** — and the two that *do* use delimited free-form tuples (GraphRAG, LightRAG text mode) silently drop malformed rows on a tolerant regex parse. **[VERIFIED-repo]** Graphiti and Cognee pass a `response_model=` Pydantic class on every call; mem0 uses OpenAI JSON-mode; LightRAG offers a JSON mode but enforces it only with prose + a repair pass. None ships a grammar (GBNF/Outlines FSM).
- **Closed-IE beats OpenIE on precision; the modern consensus is "OpenIE-recall + LLM/closed-validation for precision."** **[VERIFIED-web]** LLM-based and validation-augmented pipelines report "higher precision while maintaining higher recall" vs classic OpenIE, which is flexible/high-recall but noisy. Constraining generation to a closed vocabulary "fundamentally limits" fabrication. This directly validates ugm's **D5 governed predicates + domain/range (D15)** as the precision lever.
- **The "constrained decoding hurts reasoning" fear is real in symptom but mostly a *prompt* artifact, not a *decoder* artifact.** **[VERIFIED-web]** The one controlled benchmark (Tam et al., arXiv 2501.10868) actually found constrained decoding *improved* accuracy on all three reasoning tasks tested (GSM8K 80.1%→83.8%, etc.) **when the schema lets the model reason first then format** (a `reasoning` field before the answer field). Degradation appears when you force reason-and-format in the same token stream. Smaller models are the exception — structured constraints can hurt them.
- **For ugm specifically: prefer provider JSON-schema structured output (constrained decoding under the hood) + a forgiving parser, NOT a hand-written grammar; reserve GLiNER/GLiREL as a cheap pre-filter not the extractor; render the predicate set dynamically (type-signature-gated subset), not the whole growing registry; do one gleaning pass; and split the pipeline E2 (decontextualized claims, Claimify-style) → E3 (minimal typed triples).** **[INFERENCE from all of the below]**

---

## 2. Evidence & detail

### 2.1 What the cloned systems actually do (free-form vs typed vs grammar)

| System | Output mode | Schema enforcement | Gleaning | Source |
|---|---|---|---|---|
| **Graphiti** | Pydantic `response_model=` on every call (`ExtractedEntity`, `Edge`) | provider structured output; **heavy defensive validation** in code (clamp idx, drop bad IDs) | **single-pass, no gleaning/reflexion** (`_extract_nodes_single`, `node_operations.py:244`; no `MAX_REFLEXION` in path) | repo_findings/graphiti.md §3 |
| **Cognee** | Instructor/BAML, Pydantic `KnowledgeGraph` | `json_schema_mode` for gpt-4o; edges dropped if endpoints not in node set | **both**: default single-pass; `extract_graph_from_data_v2.py` cascade `n_rounds=2` feeds previous nodes back | repo_findings/cognee.md §4 |
| **mem0** | OpenAI `response_format={"type":"json_object"}` (JSON-mode, *not* function-calling, *not* grammar) | prose schema + regex JSON repair (`remove_code_blocks`→`extract_json`→`json.loads(strict=False)`) | **single-pass**, post-hoc repair | repo_findings/mem0.md §3 |
| **GraphRAG** | **free-form `<\|>`-delimited tuples**, regex/split parse, malformed rows silently dropped | none (`relationship_strength` is an invented 1-10 float, default 1.0 on parse fail) | **multi-pass gleaning loop** (`max_gleanings=1` default; CONTINUE/LOOP prompts; replays full history) | repo_findings/lightrag_graphrag.md §3 |
| **LightRAG** | delimited-tuple default **OR** JSON mode (`entity_extraction_use_json`); prose "JSON Contract" + repair | none/soft | **one** glean pass processed (`DEFAULT_MAX_GLEANING=1`) + token guard (skip if over `max_extract_input_tokens`) | repo_findings/lightrag_graphrag.md §3 |

Takeaways that are load-bearing for ugm:
- **Nobody uses a hand-written grammar (GBNF/Outlines FSM).** The state of practice is "provider JSON-schema/Pydantic + a forgiving parser." **[VERIFIED-repo]**
- **Defensive validation in code is universal and non-optional.** Graphiti's comment is explicit: "ingestion workflow remains deterministic even when the model misbehaves" — they clamp index ranges, drop extra/missing/duplicate IDs, treat malformed as no-op (`node_operations.py:560-624`). **[VERIFIED-repo]** This is the real reliability mechanism, more than the decoding method.
- **Type/domain-range gating is enforced structurally only for edges, and only in Graphiti.** Graphiti's `edge_type_map: dict[(source_label, target_label) → [allowed relation types]]` offers the LLM only the predicates whose signature matches the actual endpoint types during resolution (`edge_operations.py:460-486`). **[VERIFIED-repo]** This is *exactly* ugm's D15 domain/range constraint, already implemented as a dynamic predicate-subset selector — see §2.5.

### 2.2 Closed-IE vs OpenIE — precision/recall literature

- OpenIE (CoreNLP/spaCy-style) is **schema-free, high-recall, expressive, but noisy** — needs "aggressive filtering to remove noisy triplets." Closed-IE (cIE) extracts only against a predetermined relation/entity set. **[VERIFIED-web]** ([Open IE guide 2025](https://www.shadecoder.com/topics/open-information-extraction-a-comprehensive-guide-for-2025))
- The winning modern pattern is hybrid: **OpenIE for recall + LLM validation for precision** yields "higher precision while maintaining higher recall compared to state-of-the-art." **[VERIFIED-web]** ([ScienceDirect: OpenIE cleaning + LLM validation](https://www.sciencedirect.com/science/article/pii/S1877050924024761))
- cIE hallucination root cause: "the unconstrained generation space of LLMs; by establishing a closed vocabulary of text-grounded elements before extraction, the model's ability to fabricate information is fundamentally limited." **[VERIFIED-web]** ([Anchor-Constrained KG Extraction, MDPI 15/3/178](https://www.mdpi.com/2073-431X/15/3/178))
- **Schema size matters and degrades precision/recall**: an empirical study varying allowed relation types **100→800** found "performance of relation and triple extraction drops significantly with an increased number of allowed relations." A dynamic candidate-relation selector (BERT classifier → top-N predicates into the prompt) peaked at small N (N=3: P 86.5 / R 76.5 / F1 81.2). **[VERIFIED-web]** ([Automatic Prompt Optimization for KG Construction, arXiv 2506.19773](https://arxiv.org/pdf/2506.19773); [Schema-aware Reference as Prompt, arXiv 2210.10709](https://arxiv.org/pdf/2210.10709)) — **this is the single strongest argument for ugm rendering a *selected subset* of predicates, not the whole growing registry, into each extraction prompt.**

### 2.3 Constrained decoding: does it help or hurt? (Outlines/grammars/tool-calling)

- **Symptom vs diagnosis:** grammar-constrained decoding "alters the model's distribution at every token by masking invalid tokens and renormalizing" — so when the model's top tokens are all masked, quality can drop. **[VERIFIED-web]** ([Tam et al., arXiv 2501.10868](https://arxiv.org/html/2501.10868v1)). BUT the same paper's controlled experiment found **constrained decoding *improved* accuracy on all three reasoning tasks** when the schema includes a reasoning field: Llama-3.1-8B Last-Letter 50.7→54.0, Shuffle-Objects 52.6→55.9, GSM8K 80.1→83.8 (best framework = Guidance, via token-healing). The fix is "stop forcing the model to reason and format in the same breath." **[VERIFIED-web]**
- **Function-calling vs JSON-mode vs SAP** (Berkeley Function Calling Leaderboard, n=1000/model, BAML): function-calling and AST-parsing are both beaten by **schema-aligned parsing (SAP)** — generously parse + error-correct against the schema rather than strictly constrain tokens. GPT-4o: FC 87.4 / AST 82.1 / **SAP 93.0**; Claude-3.5-Sonnet: FC 78.1 / AST 93.8 / **SAP 94.4**; Claude-3-Haiku: FC 57.3 / AST 82.6 / **SAP 91.7**. **[VERIFIED-web]** ([BAML schema-aligned parsing](https://boundaryml.com/blog/schema-aligned-parsing)). Core argument (Postel's Law): "be conservative in what you do, be liberal in what you accept" — constrained generation can *prevent* valid schema-matching outputs. This matches what every cloned repo does in practice (forgiving parse + repair).
- **Production signal:** structured-output agents 95-99% action success vs 70-85% for unstructured-text parsing; **but** "structured constraints can harm smaller models." **[VERIFIED-web]** ([buildmvpfast 2026 guide](https://www.buildmvpfast.com/blog/structured-output-llm-json-mode-function-calling-production-guide-2026); [LlamaIndex JSON vs FC](https://developers.llamaindex.ai/python/framework/integrations/llm/openai_json_vs_function_calling/))
- **GLiNER / GLiREL** (encoder-based, not generative): GLiNER zero-shot **outperforms ChatGPT and fine-tuned UniNER** on NER benchmarks with fast CPU inference; 50% negative-sampling ratio best balances P/R. **[VERIFIED-web]** ([GLiNER, arXiv 2311.08526](https://arxiv.org/abs/2311.08526)). **GLiREL operates on *pre-identified entity pairs*** (it's fed gold spans+types and only predicts the relation) — i.e. it is a relation *classifier*, not an end-to-end extractor. **[VERIFIED-web]** ([GLiNER-Relex, arXiv 2605.10108](https://arxiv.org/html/2605.10108v1)). A 2026 GraphRAG-RS effort swapped LLM extraction for GLiNER-Relex specifically for speed. **[VERIFIED-web]** ([GraphRAG-RS 2026](https://autognosi.medium.com/graphrag-rs-2026-kv-caching-structural-extraction-gliner-relex-to-improve-speed-d340c0e5d127))

### 2.4 Single- vs multi-pass gleaning

- Gleaning materially raises **recall**: GraphRAG's loop replays history with a "MANY entities were missed" CONTINUE prompt then a Y/N LOOP prompt; defaults to `max_gleanings=1`. **[VERIFIED-repo]** (lightrag_graphrag.md §3). Chunk size interacts strongly — a 600-token chunk extracted ~2× the entity references of a 2400-token chunk. **[VERIFIED-web]** ([GraphRAG-V / practice notes](https://towardsdatascience.com/graphrag-in-practice-how-to-build-cost-efficient-high-recall-retrieval-systems/))
- **Diminishing returns + cost:** both GraphRAG and LightRAG ship `max_gleanings/MAX_GLEANING = 1` as the default; LightRAG additionally **skips gleaning past a token budget**. **[VERIFIED-repo]** Graphiti does **zero** gleaning and accepts the recall hit for cost/determinism. **[VERIFIED-repo]** Cognee's `n_rounds=2` cascade dedups fed-back nodes by `.lower()`. **[VERIFIED-repo]**
- **[INFERENCE]** For ugm, recall lost at extraction is partly *recovered downstream*: D2 evidence aggregation means a fact missed in one document is very likely caught in another (`evidence_count`), so the marginal value of a second gleaning pass is lower than in single-document KG builders. One glean pass (or temperature-0 single-pass + smaller chunks) is the right default.

### 2.5 Rendering a growing predicate set (static vs dynamic)

- Static "dump the whole vocabulary" degrades as the registry grows (§2.2 — precision/recall drop 100→800 relation types). **[VERIFIED-web]**
- Dynamic subset selection is the proven mitigation: classifier/retrieval picks top-N candidate predicates per input; P/R/F1 peaked at small N. **[VERIFIED-web]** ([arXiv 2506.19773](https://arxiv.org/pdf/2506.19773))
- **Graphiti already does a structural version of this**: it filters the offered relation types to those whose `(source_label, target_label)` signature matches the actual endpoints (`edge_operations.py:460-486`). **[VERIFIED-repo]** This is the cheapest dynamic selector and it is **free under ugm's D15 domain/range columns** — once entities are typed, only predicates whose domain/range admit those types are eligible. **[INFERENCE]**
- LightRAG renders entity types **from a registry/YAML profile** (`resolve_entity_extraction_prompt_profile`, `prompt.py:678`) — a working implementation of D15's "prompts render from the registry." **[VERIFIED-repo]** Adopt the pattern; add the domain/range filter on top.

### 2.6 Decontextualization vs minimality (E2 vs E3 split)

- **Claimify** (Microsoft) is the reference design for E2: 4 stages — Sentence Splitting → Selection (drop opinions/speculation) → Disambiguation (resolve or discard ambiguous) → Decomposition into **atomic, decontextualized, self-contained** claims. **[VERIFIED-web]** ([Claimify / factual-claim extraction, arXiv 2502.10855](https://arxiv.org/pdf/2502.10855))
- **Decontextualization** = the claim is correctly interpretable with no source context: resolve pronouns→proper nouns, relative→absolute ("It was released in 2010" → "The first iPad was released in 2010"). Document-level work recasts it as extractive-summarization-then-rewrite. **[VERIFIED-web]** ([Document-level Claim Extraction & Decontextualisation, ACL 2024.acl-long.645](https://aclanthology.org/2024.acl-long.645/))
- **The two pull in opposite directions and that is precisely why ugm splits them (D2):** decontextualization *adds* context to make a claim self-standing (good for E2 — the immutable testimony in NL, retrievable on its own); minimality *strips* to one binary `(s,p,o)` (good for E3 — the typed fact). Forcing both at once destroys information (concepts.md §1: c1 "joined Acme as VP in March 2024" carries role+date+event that one triple can't hold). **[VERIFIED-repo, concepts.md]** Every cloned repo conflates these into one extraction step and loses the date/role nuance into a free-text edge `description`; ugm's two-layer split is the correction. **[INFERENCE]**

---

## 3. Confidence & gaps

**Well-supported (high):**
- All cloned-system facts (typed Pydantic/JSON, no grammars, defensive validation, gleaning defaults=1, Graphiti edge-type-signature gating). **[VERIFIED-repo]** — these are read from source via repo_findings.
- Closed-IE > OpenIE on precision, and the OpenIE-recall + LLM/closed-validation hybrid being the modern winner. **[VERIFIED-web]**, multiple independent sources.
- Schema-size degradation and dynamic subset selection being the mitigation. **[VERIFIED-web]**, with concrete numbers.
- Claimify 4-stage design and the decontextualization-vs-minimality tension. **[VERIFIED-web + concepts.md]**

**Medium confidence:**
- "Constrained decoding helps, not hurts, when the schema lets the model reason first." Rests substantially on **one** benchmark paper (arXiv 2501.10868) plus the BAML SAP study; the BAML numbers come from a vendor blog (BoundaryML sells SAP) — **flag as vendor-sourced**, though the Berkeley-leaderboard methodology is checkable. The "smaller models are hurt" caveat is consistently reported but I did not find a single rigorous controlled study isolating it.
- GLiNER outperforming ChatGPT/UniNER on NER — true on the cited benchmarks, but benchmark NER ≠ ugm's domain-specific governed-schema extraction; transfer is **[UNCERTAIN]**.

**Gaps / could not verify:**
- **No system in the survey publishes precision/recall numbers** for its own ER or extraction — every repo_findings file says "benchmark figures: not found" in source. So all P/R numbers here are from the academic literature, on *their* datasets, not on memory-system workloads. **Do not treat any number as a prediction for ugm.** **[UNCERTAIN]**
- I could not find a study directly measuring the **cost** (token/latency/quality) of a closed-with-`other:`-escape *hybrid* specifically. The `other:` escape is ugm's own design (D5); its cost is an open empirical question — see §4 "what to measure."
- The exact crossover where dynamic predicate-subset selection beats static (in ugm's registry-size regime) is unknown; the literature's "100→800" range brackets it but isn't ugm's vocabulary.

---

## 4. Recommendation for ugm

### 4.1 The E2→E3 extraction design (concrete)

**E2 — Claims (decontextualized, NL, immutable).** Implement a **Claimify-style 4-stage pipeline** (split → select → disambiguate → decompose), run **after coreference resolution** (D4 requires coref before claim extraction). Output is atomic, **decontextualized** NL claims (pronouns→names, relative→absolute dates), kept in natural language so role/date/event survive (concepts.md §1). Use **provider JSON-schema structured output** (Pydantic/`response_format` with a `claims: list[Claim]` schema), **not** a grammar. Each claim carries `attributed_to`, source date, span/provenance. Steal mem0's **integer-ID remapping** (show the model small int IDs, map back to UUIDs in code) and its preservation rules (exact numbers, proper nouns, "416 pages" not "~400"). **[VERIFIED-repo: mem0.md §3, §8]**

**E3 — Relations (minimal typed triples into the governed schema).** A separate normalization step maps eligible claims → `(subject_entity, predicate, object_entity)` (D2). This is the **closed-IE** step and where governance pays off:
- **Closed predicate vocabulary (D5) + domain/range (D15) is the precision mechanism.** Literature: closing the vocabulary "fundamentally limits fabrication"; domain/range "mechanically reject a class of hallucinations" (entity_registry.md §5; MDPI anchor-constrained). **[VERIFIED-web + repo]**
- **Render predicates dynamically, not statically.** Once the subject/object entities are typed by the registry, offer the LLM **only predicates whose domain/range admit those types** — Graphiti's `(source_label,target_label)→[allowed predicates]` map is the exact mechanism (`edge_operations.py:460-486`), and it is free under D15. Render entity types + the selected predicate subset **from the registry** (LightRAG's `resolve_entity_extraction_prompt_profile` pattern). This avoids the precision drop measured at 800 relation types. **[VERIFIED-repo + web]**
- **`other:<freetext>` escape stays** (D5) — but treat it as the *recall valve and ontology-gap sensor*, not a normal output. Measure its rate (below).
- **Decoding method: provider JSON-schema structured output + a forgiving parser, NOT a hand-written grammar.** The evidence is clear that (a) constrained decoding doesn't hurt and can help *if the schema lets the model reason first* (add a short `evidence_quote`/`reasoning` field before the triple), and (b) schema-aligned forgiving parsing beats strict constrained generation on the function-calling leaderboard, and (c) it's what every production repo actually does. Keep Graphiti-style **defensive validation in code** (drop triples whose endpoints aren't in the entity set, whose predicate isn't in the registry, or whose types violate domain/range) — this is the real reliability layer. **[VERIFIED-repo + web]**

**Gleaning: one pass, or none.** Default to **single-pass, temperature 0, with smaller chunks (~600 tokens)** for recall, and add **at most one glean pass** with a token guard (LightRAG pattern). D2 evidence aggregation recovers most cross-document misses, so don't pay for deep gleaning. **[VERIFIED-repo + INFERENCE]**

**GLiNER/GLiREL: optional cheap pre-filter, not the extractor.** Consider GLiNER as a **deterministic, CPU-cheap candidate-span/blocking pre-pass** before the LLM (and GLiREL as a relation *validator* over candidate entity pairs), reducing LLM load — but it needs typed gold-ish spans to shine and doesn't replace the governed-schema LLM step. Treat as a Phase-2 cost optimization, not a launch dependency. **[VERIFIED-web + INFERENCE]**

### 4.2 What to measure (golden-set-first, per entity_registry.md §7)

Build the labeled golden set **before tuning** (a few hundred sentences/claims per entity type, with hard cases). Then track:

1. **E2 claim quality:** decontextualization correctness (can each claim be interpreted with no source context?), selection precision (opinions/speculation excluded), decomposition atomicity. Borrow Claimify's own eval axes. **[VERIFIED-web]**
2. **E3 extraction P/R/F1 against the golden set**, computed **per predicate** (aggregate F1 hides a few broken predicates).
3. **Schema-violation rates (should approach 0 by construction):** % triples dropped for unknown predicate, % for domain/range violation, % for endpoint-not-in-entity-set. Rising rates = prompt/registry drift.
4. **`other:` escape rate** — overall and the top-K most-frequent `other:` values (the D5 promotion funnel). A spike = ontology gap; a specific recurrent value = a predicate to promote.
5. **Gleaning marginal recall:** Δrecall from pass 2 vs its token cost — kill the pass if Δ is small (it will be, per the defaults all repos chose).
6. **Decoding-method A/B:** structured-output(JSON-schema) vs forgiving-parse on identical inputs — measure invalid-output rate **and** semantic F1 (the SAP/Tam finding says don't assume strict constraint = better quality, especially on smaller models). **[VERIFIED-web]**
7. **Parse-loss rate:** fraction of model outputs that fail schema and are dropped vs repaired — Graphiti/GraphRAG drop silently; ugm should **log** drops (a dropped triple may be a missed supersession, which D4 makes existential).

### 4.3 Ties to decisions

- **D5 (governed predicates)** and **D15 (core+extensions, domain/range, prompts-from-registry)** are *the* precision mechanism — the closed-IE literature and Graphiti's edge-type gating both confirm. Render predicates **dynamically** (domain/range-filtered subset), which D15's typed columns give for free.
- **D2 (claims≠relations, many-to-many)** is what makes the decontextualization-vs-minimality split implementable and what lowers the value of deep gleaning (evidence aggregation recovers misses).
- **D4 (coref before extraction; cheap-first cascade)** sets the ordering: coref → E2 Claimify → E3 closed-IE.
- **D6/D7 (graph is a rebuildable projection)** means retyping/registry cleanups from `other:` promotion apply retroactively for free — so **start strict** (D5) and loosen via measured `other:` promotion.

---

## 5. Sources

Repo (read locally): `repo_findings/{graphiti,cognee,mem0,lightrag_graphrag}.md`; `entity_registry.md`; `concepts.md`; `decisions.md` (D2,D4,D5,D6,D7,D15). Graphiti edge-type gating `edge_operations.py:460-486`; defensive validation `node_operations.py:560-624`.

Web:
- [Generating Structured Outputs from LMs: Benchmark & Studies (Tam et al.), arXiv 2501.10868](https://arxiv.org/html/2501.10868v1)
- [BAML: Prompting vs JSON Mode vs Function Calling vs Constrained Generation vs SAP](https://boundaryml.com/blog/schema-aligned-parsing)
- [Enhancing KG Construction through OpenIE Cleaning and LLM Validation (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S1877050924024761)
- [Open Information Extraction guide 2025](https://www.shadecoder.com/topics/open-information-extraction-a-comprehensive-guide-for-2025)
- [Grounded KG Extraction via LLMs: Anchor-Constrained Framework (MDPI 15/3/178)](https://www.mdpi.com/2073-431X/15/3/178)
- [Automatic Prompt Optimization for KG Construction, arXiv 2506.19773](https://arxiv.org/pdf/2506.19773)
- [Schema-aware Reference as Prompt, arXiv 2210.10709](https://arxiv.org/pdf/2210.10709)
- [GLiNER, arXiv 2311.08526](https://arxiv.org/abs/2311.08526)
- [GLiNER-Relex, arXiv 2605.10108](https://arxiv.org/html/2605.10108v1)
- [GraphRAG-RS 2026 (GLiNER-Relex swap)](https://autognosi.medium.com/graphrag-rs-2026-kv-caching-structural-extraction-gliner-relex-to-improve-speed-d340c0e5d127)
- [Claimify / factual-claim extraction & evaluation, arXiv 2502.10855](https://arxiv.org/pdf/2502.10855)
- [Document-level Claim Extraction & Decontextualisation, ACL 2024.acl-long.645](https://aclanthology.org/2024.acl-long.645/)
- [GraphRAG in Practice: high-recall retrieval (TDS)](https://towardsdatascience.com/graphrag-in-practice-how-to-build-cost-efficient-high-recall-retrieval-systems/)
- [JSON Mode vs Function Calling vs Structured Output: 2026 Guide](https://www.buildmvpfast.com/blog/structured-output-llm-json-mode-function-calling-production-guide-2026)
- [LlamaIndex: OpenAI JSON Mode vs Function Calling for Data Extraction](https://developers.llamaindex.ai/python/framework/integrations/llm/openai_json_vs_function_calling/)
