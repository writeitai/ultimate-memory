# Open Questions from the Author

The author's own running list of open questions — raw, first-person, and deliberately kept
separate from the curated register in `questions.md`. This is the *inbox*: questions as they
occur to the author, before they are triaged, researched, or split into decisions. As each one is
worked, it should graduate — into a decision (`decisions.md`), a design doc (`plan/designs/`), or
a tracked entry in the consolidated register (`questions.md`) — and be pruned from here or marked
resolved.

Nothing here is answered. Each item records the question as posed, plus a short **context** note:
what it touches, where it connects in the existing docs, and why it is still open.

> Terminology anchors used below: **PageIndex** is the per-document *structurer* — it turns a
> document into a hierarchical section tree (E0, decisions D36–D40, specifically D39).
> **E0→E1→E2→E3** is the Evidence plane: files → chunks → claims → relations (D14).

---

## Q1. How exactly should the PageIndex (structurer) logic be implemented?

**Context.** E0 extracts per-document structure (a section tree with spans). The constraint names
PageIndex (requirements §Imposed constraints; D39). Investigation of the MIT-licensed PageIndex
library concluded its Markdown path is ~190 lines of *deterministic* (LLM-free) work — regex header
scan, line-slice spans, level-stack nesting — and that for our Markdown-first E0 we should
**reimplement a ~150-line core** rather than vendor the package (see `questions.md` #7). What is
still unspecified is the *exact* implementation: the heading regex and how it hardens against our
real E0 Markdown dialect (ATX vs. Setext headers, ```` ``` ```` vs. `~~~` code fences); how we
derive **character offsets** (PageIndex emits only line numbers — we need char/page spans for chunk
boundaries); the node schema we commit to; whether we keep tiny-section "thinning"; and operating on
an in-memory string rather than reading from disk. Connects to: `e0_files_design.md`, D39,
`questions.md` #7.

## Q2. What are good benchmarks — and ideally not overly expensive ones to run?

**Context.** Evaluation is only partially designed: D22 covers entity-resolution and retrieval eval,
but the E2/E3 side (extraction Selection precision, false-drop canaries, grounding safety, relation
normalization, supersession/contradiction quality) has **no harness yet** (`questions.md` #14). The
open question is twofold: (a) *which* benchmarks/golden sets — public datasets vs. hand-built golden
docs — for each layer (structure quality, chunking, claim extraction, entity resolution, retrieval);
and (b) how to keep eval **cheap to run repeatedly** — sampling, canary sets, cheaper grader models,
deterministic checks — so it can gate every prompt/model/embedding version bump without a large
recurring cost. Connects to: `questions.md` #14, D22, `registries_design.md` (eval section).

## Q3. What should be the connection between PageIndex and chunking, if at all?

**Context.** E1 chunking is named as semchunk + a context prefix, with "section-aware boundaries from
E0" (`questions.md` #18; `e1_chunks_design.md` is planned, not written). The open question is whether
the structurer and the chunker are coupled at all, and how: does chunking *consume* the section tree
(so chunk boundaries snap to section spans, and a chunk never straddles two top-level sections), or
does it run independently over the raw Markdown with semchunk alone? If coupled, how do the
structurer's char-spans feed semchunk, and who wins when a single section is far larger or smaller
than the target chunk size? Connects to: `questions.md` #18, Q1 above, `e0_files_design.md`.

## Q4. For claim extraction, what exact context do we give it — the entire document, or surrounding chunks? If chunks, how many?

**Context.** E2 uses the Claimify principle: a context bundle plus two LLM calls, with no
pre-extraction value gate (junk control is in-call at Selection — D25, D31–D35). The design names a
"context bundle" but does not pin its **scope**. This is a concrete, tunable open parameter: is the
de-contextualization/extraction context the *whole document*, the *current section*, or the *current
chunk plus N neighboring chunks* — and if neighbors, how many (and chosen by count, token budget, or
section boundary)? It trades extraction quality (coreference resolution, "the CEO" → which entity)
against cost and context-window limits, and interacts with cross-document coreference
(`questions.md` #22). Connects to: D31–D35, `e2_e3_claims_relations_design.md`, `questions.md` #22.

## Q5. How do we design the querying (retrieval) system?

**Context.** The consumer surface. D9 gives the *shape* (RRF fusion, rerankers, named recipes, a
zero-LLM core search path); requirements name the four entry points (API, CLI, MCP server, and the
read-only mounted corpus filesystem). But `retrieval_design.md` is unwritten (`questions.md` #16):
the API contract, how the four surfaces compose with the mounted filesystem into recipes, the
cross-plane entry→expand→hydrate orchestration over P1 (search) / Postgres (spine) / P2 (graph) /
P3 (corpus FS), and how a consumer reasons about **mixed freshness** (Postgres live, P2 hours-stale,
K debounced — `questions.md` #23) are all open. Connects to: `questions.md` #16 and #23, D9.

## Q6. Should the design also include worker and queue design — the full set of workers and queues, and exactly how they work?

**Context.** The execution substrate is a fixed constraint (GCP Cloud Run jobs triggered via Cloud
Tasks, ≤2 retries, rate-limited — requirements §Imposed constraints), but there is **no written
design** for the worker/queue topology. Open: what is the complete set of workers (e.g. E0 convert,
E0 structure, E1 chunk + embed, E2 extract, E3 normalize + resolve, K1/K2/K3 compilers, P1/P2/P3
rebuilds) and queues; how they chain and what each one's idempotency key, retry/dead-letter
behavior, ordering, and inter-stage dependencies are; how fan-out (per-document vs. per-chunk) is
shaped; and how this ties into backfill/reprocessing when a converter/structurer/extractor or
embedding version is bumped (`questions.md` #11). A decision is also needed on *whether* this
topology belongs in the binding design set at all, or stays an implementation concern. Connects to:
`questions.md` #11, requirements §Imposed constraints, `overall_design.md`.

---

## How these map to the consolidated register (`questions.md`)

Several of these overlap existing entries; this inbox is where the author raises them, the register
is where they are tracked once triaged. Rough mapping:

- **Q1** ↔ #7 (PageIndex hosted vs. self-hosted) — narrows it to *implementation* of a self-hosted reimplementation.
- **Q2** ↔ #14 (E2/E3 eval harness) — adds the "cheap to run" and "which benchmarks" angle.
- **Q3** ↔ #18 (E1 chunking) — the structurer↔chunker coupling question specifically.
- **Q4** — not yet in the register; a concrete extraction-context parameter under D31–D35. Candidate to add.
- **Q5** ↔ #16 (retrieval) and #23 (mixed-freshness).
- **Q6** ↔ #11 (backfill/reprocessing orchestration) — broadens it to the whole worker/queue topology, currently undesigned.
