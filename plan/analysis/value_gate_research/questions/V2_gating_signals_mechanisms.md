# V2 — Cheap value-gating signals & mechanisms before expensive extraction

**Question.** Best CHEAP techniques to score document/section/chunk VALUE *before* expensive
extraction (E2 claims / E3 relations). Which signals (source trust, structural role, density,
novelty, length/perplexity, query-demand), which mechanism (heuristic / small classifier /
small-LLM judge / embedding-novelty threshold / dedup pre-pass), what cost ratio vs. the
extraction it gates, and a concrete recommendation: signal set + mechanism + the three output
tiers (full / deferred / chunks-only). This answers objection **O3** (`objections.md`).

Evidence is drawn from (a) the four cloned ugm repo-finding docs (value-gate + registry), which
establish that **no major memory/RAG system implements a value gate** (only exact-hash dedup),
and (b) the LLM-pretraining data-curation literature, which is the one field that has built and
*measured* cheap value gates at corpus scale (FineWeb, DCLM, Ask-LLM/Density, SemDeDup,
Ultra-FineWeb). The pretraining field is the right analogue: it faces ugm's exact problem —
"most of 1M docs is boilerplate/dup/filler" — and its gates are designed to cost orders of
magnitude less than the downstream consumer (there, training; here, LLM extraction).

A note on transfer: pretraining filters optimize *what a model learns from*; ugm gates *what is
worth spending extraction LLM cost on*. The signals transfer directly (both ask "is this text
information-dense, novel, non-boilerplate, trustworthy?"); the *thresholds* do not (must be
re-tuned on ugm's golden set — O6 dependency). Flagged throughout.

---

## 1. Key findings

1. **No prior memory/RAG system has a value gate — the cheapest tier everyone ships is
   exact-content-hash dedup, which is trivially defeated by paraphrase or one-byte changes.**
   GraphRAG, LightRAG, HippoRAG, mem0, cognee all extract *everything that survives chunking*;
   their only pre-LLM cost lever is idempotent re-ingest by content hash
   (`value_gate_research/repo_findings/graphrag_lightrag_hipporag.md:5-12,143-159`;
   `mem0_cognee.md:8-15,150-162`). GraphRAG even quantifies the prize: **"graph extraction ≈ 75%
   of indexing cost"** (`graphrag_lightrag_hipporag.md:43-48`, citing `docs/index/methods.md:44`),
   so a gate that drops a meaningful fraction of low-value text is a near-linear LLM-cost lever —
   consistent with O3's "plausibly 10×". **The value/salience/novelty tier is unbuilt prior art;
   ugm must build it, and it is a genuine differentiator** (verified by grep-absence across five
   repos).

2. **The pretraining field has settled on a layered cascade whose ordering is itself the cost
   discipline: cheapest-and-most-destructive signals first, expensive judgments last.** FineWeb's
   public pipeline order is: text-extraction/boilerplate-removal (trafilatura) → cheap heuristic
   quality filters (C4 + Gopher repetition rules) → MinHash near-dedup → model-based filtering
   ([FineWeb/NeurIPS 2024](https://papers.neurips.cc/paper_files/paper/2024/file/370df50ccfdf8bde18f8f9c2d9151bda-Paper-Datasets_and_Benchmarks_Track.pdf);
   [HF FineWeb writeup](https://zeroentropy.dev/concepts/fineweb/)). Each rung is ~1–2 orders of
   magnitude cheaper than the next; you never pay the expensive rung on text the cheap rung
   already killed. This *is* ugm's D4 cheap-first cascade, applied to the extraction-gate problem
   instead of the supersession problem.

3. **Concrete cost ratios (the load-bearing numbers):**
   - **Heuristics (regex/length/ratio rules): effectively free** — O(1) per doc, CPU, no model.
     They are the structural-role and length filters (boilerplate, references, repetition).
   - **MinHash/SimHash near-dedup: ~free per doc, CPU-only.** Fingerprint is O(doc length) once;
     pairwise compare is O(1) XOR+popcount via LSH banding, not O(n²)
     ([Manku/Google SimHash](https://research.google.com/pubs/archive/33026.pdf);
     [In Defense of MinHash](https://arxiv.org/pdf/1407.4416)). FineWeb config: 5-gram shingles,
     112-perm signature, 14 bands × 8 hashes ([MixMinMatch](https://arxiv.org/html/2512.18834)).
   - **Embedding-novelty (SemDeDup): one embedding pass + k-means + in-cluster cosine.** Removes
     ~50% of data with minimal loss; on C4, keeping 80% held perplexity flat for 10–15% compute
     savings ([SemDeDup arXiv:2303.09540](https://arxiv.org/abs/2303.09540);
     [NeMo Curator docs](https://docs.nvidia.com/nemo/curator/curate-text/process-data/deduplication/semdedup)).
     The embedding is **already computed in ugm** (E1 embeds every chunk for P1) — so novelty is a
     **marginal-zero-cost** signal here (a cosine lookup against existing claim/relation embeddings).
   - **Small classifier (fastText/BERT-style): the workhorse, 6× cheaper than an LLM filter and
     GPU-free.** Ultra-FineWeb Table 2: filtering 15T tokens costs **~6,000 H100-GPU-hours with an
     LLM classifier vs. ~1,000 CPU-hours (80 CPUs, no GPU) with fastText — a 6× speedup and a
     hardware-class change** ([Ultra-FineWeb arXiv:2505.05427](https://arxiv.org/html/2505.05427v1)).
     fastText throughput is CPU-bound and effectively free relative to any GPU pass; a BERT-style
     edu-classifier does ~450 GB/h on one H100 at 87% precision (per
     [BRICS data-quality survey](https://brics-econ.org/measuring-data-quality-for-llm-training-model-based-and-heuristic-filters)).
   - **Small-LLM judge (Ask-LLM): most accurate, most expensive — one inference pass per item.**
     A frontier judge (Nemotron-4-340B-class) does only ~15–25 docs/min on 8×A100 and "LLM-only
     filtering would cost $20,000 to filter 10 TB" ([BRICS survey](https://brics-econ.org/measuring-data-quality-for-llm-training-model-based-and-heuristic-filters)).
     Ask-LLM justifies this only because the cost is **amortized over many downstream training runs**
     ([How to Train Data-Efficient LLMs, arXiv:2402.09668](https://arxiv.org/abs/2402.09668)).
     **That amortization argument does NOT hold for ugm**: ugm gates a *one-shot per-document*
     extraction, so a per-doc LLM judge that costs a meaningful fraction of the extraction it gates
     violates the "gate ≪ extraction" rule. **Use the LLM judge only to label a seed set and
     distill a small classifier**, not in the steady-state per-doc path. (Inference; high confidence.)

4. **The dominant, repeatedly-validated mechanism is two-stage distillation: an LLM "oracle" labels
   a sampled seed set once, then a cheap classifier (fastText) scales the gate.** "Pipelines like
   LMDS sample a subset and label it with a high-capacity LLM oracle, then fine-tune a lightweight
   classifier to scale up the filter economically" ([LLM-as-judge cost survey, Encord/BRICS]); Ultra-FineWeb
   builds its fastText filter from "600K samples … positive seeds … negatives randomly selected"
   ([Ultra-FineWeb](https://arxiv.org/html/2505.05427v1)). This *is* the answer to "heuristic vs
   classifier vs LLM-judge": **not either/or — heuristics + dedup as free pre-filters, a distilled
   classifier as the steady-state value gate, an LLM judge only off the hot path (seed labeling).**
   It also satisfies O6: the seed set the classifier distills from *is* the golden set.

---

## 2. Evidence & detail with citations

### 2.1 Signal-by-signal: what's cheap, how it's computed, what it buys

| Signal | Cheapest mechanism | Cost | What it catches | Evidence |
|---|---|---|---|---|
| **Source type / trust** | Lookup on `document.source` metadata (already in PG) | free (table read) | down-weight scraped/forum/auto-gen; up-weight curated/peer-reviewed | Standard data-curation practice; FineWeb uses URL/domain priors ([FineWeb](https://zeroentropy.dev/concepts/fineweb/)). ugm already records source metadata at E0. |
| **Structural role (boilerplate / refs vs body)** | Heuristics on PageIndex node type + regex (line-length, stopword ratio, ellipsis density, "References"/"Bibliography"/nav headers) | free, CPU O(1) | the exact O3 case — "references section processed with the same enthusiasm as core findings" (`objections.md:71-72`) | FineWeb C4+Gopher heuristics: "mean line length, stopword ratio, fraction of alphabetic chars, ellipsis density … drops boilerplate and SEO spam"; trafilatura main-content extraction beats raw WET ([FineWeb writeup](https://zeroentropy.dev/concepts/fineweb/); [NeurIPS](https://papers.neurips.cc/paper_files/paper/2024/file/370df50ccfdf8bde18f8f9c2d9151bda-Paper-Datasets_and_Benchmarks_Track.pdf)). **ugm advantage: PageIndex (E0) already labels hierarchy/node-type — structural role is nearly free metadata, not inference.** |
| **Information / entity density** | NER span count ÷ token count; ratio of content words; (optionally cheap noun-phrase count) | very cheap (spaCy/regex; ugm runs coref+NER anyway) | filler/phatic text (mem0's "purely phatic" class, `mem0_cognee.md:48-49`); a high-density section is high-value-per-extraction-dollar | Density of nameable entities is the strongest cheap proxy for "this chunk will yield relations." cognee carries an `importance_weight` field but **never uses it** (`mem0_cognee.md:104-110`) — a cautionary tale: don't compute a salience score and then ignore it. |
| **Novelty vs. known** | Cosine of the chunk/claim embedding against existing claim/relation embeddings (top-k in Lance); threshold | **marginal-zero** — embedding already computed at E1 for P1 | suppresses Nth restatement of a known fact; routes clear-novel to full extraction | SemDeDup: embed → k-means → in-cluster cosine, keep one representative; removes ~50% at minimal loss ([arXiv:2303.09540](https://arxiv.org/abs/2303.09540); [NeMo](https://docs.nvidia.com/nemo/curator/curate-text/process-data/deduplication/semdedup)). Density sampling "downsample[s] redundant, high-density information" ([2402.09668](https://vladbogo.com/blog/2024/02/19/how-to-train.html)). **Caveat:** semantic novelty ≠ value (a novel boilerplate footer is novel-but-worthless) → novelty is a *router*, not a sole gate. |
| **Near-duplicate (exact + fuzzy)** | content-hash (exact) → MinHash/SimHash LSH (near) | free/CPU-only | re-ingest idempotency (everyone has exact); MinHash adds the *paraphrase/near-dup* tier nobody has | Exact-hash is the floor every system ships (LightRAG `compute_text_content_hash`, `graphrag_lightrag_hipporag.md:57-99`; cognee `content_hash`, `mem0_cognee.md:113-120`). MinHash: O(1) banded-LSH compare, "no additional computation beyond standard dedup" ([MixMinMatch](https://arxiv.org/html/2512.18834)); SimHash 64-bit, XOR+popcount, "faster than minhash even on enormous corpuses" ([SimHash explainer](http://ben-whitmore.com/simhash-and-solving-the-hamming-distance-problem-explained/); [Manku](https://research.google.com/pubs/archive/33026.pdf)). |
| **Length / perplexity** | char/token length thresholds (free); perplexity needs a small LM forward pass | length free; perplexity ~small-model cost | too-short = no extractable content; perplexity flags gibberish/spam | FineWeb drops docs with too-high short-line fraction etc. ([writeup](https://zeroentropy.dev/concepts/fineweb/)). **Perplexity has a known flaw: strong in-distribution bias** — "perplexity filters exhibit a strong in-distribution bias … Ask-LLM can escape this bias" ([2402.09668 search synthesis]). **Recommendation: use length (free) but treat perplexity as low-priority** — it's a model pass that mostly catches what cheaper heuristics already catch, and it's biased. (Inference; medium confidence.) |
| **Query / retrieval demand** | counter on chunk retrievals; "compiled scope declares interest in entity X" trigger | free (event-driven) | enables O3's *lazy extraction* — extract on first retrieval, not on ingest | This is the deferred-work lever, not a per-doc score. Query-driven/lazy KG construction is an active but **less-mature** research direction ([Query-Driven GraphRAG, ACL 2025](https://aclanthology.org/2025.findings-acl.1100.pdf); [RAKG arXiv:2504.09823](https://arxiv.org/html/2504.09823v1)) — no production memory system ships it (`graphrag_lightrag_hipporag.md:164`: "none of them stages extraction; it's eager on ingest"). Lower confidence that it's robust at scale; recommend as the **"deferred" tier's promotion trigger**, not the primary gate. |

### 2.2 Mechanism-by-mechanism: cost vs. extraction it gates

The hard requirement is **gate-cost ≪ extraction-cost**. ugm's extraction (E2/E3) per chunk is:
coreference + Claimify (multi-step LLM) + entity resolution + relation normalization + supersession
cascade — *multiple* LLM calls per chunk (`overall_design.md:96-102`). Against that baseline:

| Mechanism | Per-item cost | Ratio vs. extraction | Accuracy | Verdict |
|---|---|---|---|---|
| **Heuristics** (length, ratios, structural role) | regex, O(1), CPU | **~10⁴–10⁶× cheaper** (no model at all) | coarse but high-precision on boilerplate/refs | **Tier-0 pre-filter. Always on.** |
| **Exact + near-dup (hash + MinHash/SimHash)** | hash + LSH lookup, CPU | **~10³–10⁵× cheaper** | exact (content-hash); high-recall fuzzy (MinHash) | **Tier-1 dedup pre-pass. Always on.** Adds the near-dup tier no prior system has. |
| **Embedding-novelty** | 1 cosine lookup (embedding already exists) | **marginal-zero** (embedding sunk at E1) | good as a *router*, not a gate | **Tier-2 router.** Cheapest *semantic* signal available; free because of E1. |
| **Small classifier (fastText, distilled)** | CPU inference, 80 CPUs ≈ 1,000 h / 15T tok | **6× cheaper than an LLM filter, GPU-free** ([Ultra-FineWeb T2](https://arxiv.org/html/2505.05427v1)); ≫ cheaper than ugm multi-call extraction | tunable; 87% precision class achievable (BERT-edu) | **Tier-3 value gate (steady state). The workhorse.** |
| **Small-LLM judge (Ask-LLM)** | 1 LLM pass/item; ~15–25 docs/min on 8×A100; "$20k/10TB" | **same order as a single extraction call** — too close to the thing it gates for per-doc use | best (92–95% human agreement, frontier judge) | **Off the hot path only: seed-label → distill. NOT steady-state per-doc.** |

The decisive asymmetry: a per-doc LLM judge costs roughly one LLM call; ugm extraction costs
*several*. So an LLM judge could in principle save net cost — **but** the pretraining field's own
conclusion is that you should *distill* it (label once, classify cheaply forever) because the
classifier is 6× cheaper and GPU-free while retaining most of the signal
([Ultra-FineWeb](https://arxiv.org/html/2505.05427v1); LMDS two-stage pattern). For ugm, where the
judge can't be amortized over repeated training runs, distillation is the only economically sound
way to use the LLM's judgment. (Inference from the cited cost numbers; high confidence.)

### 2.3 What the cloned repos contribute as reusable primitives

- **Exact-dup floor:** LightRAG `compute_text_content_hash` + filename dedup
  (`graphrag_lightrag_hipporag.md:57-99`); cognee file `content_hash`
  (`mem0_cognee.md:113-120`) — lift directly as Tier-0/1's exact rung (idempotent re-ingest, also
  serves D7 rebuildability via HippoRAG's chunk-hash extraction cache,
  `graphrag_lightrag_hipporag.md:103-118`).
- **Cheap-first cascade shape:** GraphRAG Fast/Standard split (NLP vs LLM extraction,
  `graphrag_lightrag_hipporag.md:33-48`) and LightRAG's merge-side `force_llm_summary_on_merge=8`
  threshold (`:89-93`) confirm the *pattern* (defer/avoid the LLM by a cheap pre-check) — but none
  gate on *value*, only on merge depth or model tier.
- **Classical blocking/similarity math** (for the dedup pre-pass clustering, not entity-level):
  splink/dedupe Jaccard/Jaro-Winkler + Fellegi–Sunter (`registry_research/repo_findings/splink_dedupe.md:81,234`),
  zingg Jaccard (`zingg.md:49`). These are entity-resolution tools; relevant to V2 only insofar as
  MinHash-Jaccard is the same shingled-similarity family.
- **Anti-pattern to avoid:** cognee's `importance_weight` default-`0.5`, computed-but-unused, with a
  merge-time `# TODO` (`mem0_cognee.md:104-110`). Do not ship a salience score that nothing reads.

---

## 3. Confidence & gaps

**High confidence**
- No prior memory/RAG/GraphRAG system implements a value gate; only exact-hash dedup
  (grep-verified across 5 cloned repos; explicit "not found" annotations).
- The layered cheap-first cascade (heuristics → dedup → embedding-novelty → classifier → judge) is
  the field-standard architecture, and each rung is materially cheaper than the next.
- fastText classifier is ~6× cheaper than an LLM classifier and GPU-free
  (Ultra-FineWeb Table 2, direct quote).
- Two-stage distillation (LLM oracle labels seed → cheap classifier scales) is the dominant,
  repeatedly-validated mechanism.
- Embedding-novelty is near-zero marginal cost in ugm specifically, because E1 already embeds
  every chunk.

**Medium confidence**
- Exact transfer of *thresholds* from pretraining to ugm — the signals transfer, the cut-points
  must be re-tuned on a ugm golden set (O6). Pretraining filters optimize "what to learn from";
  ugm optimizes "what to spend extraction on." Directionally identical, not numerically portable.
- Perplexity's low value for ugm (in-distribution bias + redundant with cheaper heuristics) — based
  on the paper's own critique, not a ugm-specific measurement.
- The precise net-cost win of the gate ("10×", O3) — GraphRAG's "extraction ≈ 75% of indexing cost"
  bounds the *prize*, but the realized multiplier depends on ugm's actual junk fraction, which is
  unmeasured here.

**Low confidence / gaps (could not verify)**
- **Lazy/query-demand extraction at scale.** Active research ([Query-Driven GraphRAG],[RAKG]) but no
  production memory system ships it; robustness, cold-start retrieval quality, and the
  "never-retrieved → never-extracted" coverage hole are unproven. Recommend piloting as the
  *deferred-tier promotion trigger*, not the primary gate.
- **No cost/quality numbers exist in any of the cloned repos themselves** — mem0, cognee,
  HippoRAG, LightRAG commit eval scaffolding but no token/cost/latency figures
  (`mem0_cognee.md:88-89,144-147`; `graphrag_lightrag_hipporag.md:135-137,146-147`). All cost
  ratios in this doc come from the *pretraining* literature, not from the memory systems.
- **No ugm golden set exists yet** (O6) — every threshold below is a starting point, not a tuned value.
- I did not independently re-run any benchmark; all numbers are cited from sources, not measured.

---

## 4. Recommendation for ugm

A **five-rung cheap-first gate** sits between E1 (chunks, embedded) and E2 (claims), as a new
plane-E stage. It is the D4 cheap-first cascade applied to the *extraction* decision, the trigger
that D12 currently lacks ("none of them stages extraction; it's eager on ingest",
`graphrag_lightrag_hipporag.md:164`), and the direct implementation of O3's salience gate. It runs
**per section** (PageIndex node) with per-chunk overrides, because structural role is a section
property and ugm already has the PageIndex hierarchy from E0.

### 4.1 The cascade (ordered cheapest-first; stop as soon as a decision is reached)

0. **Heuristic structural/length pre-filter (free, CPU).** Using PageIndex node type + regex:
   route references/bibliography/nav/boilerplate/footer sections and sub-threshold-length chunks
   straight to **chunks-only**. (FineWeb C4+Gopher heuristics; resolves the O3 references case
   directly.)
1. **Dedup pre-pass: exact content-hash → MinHash/SimHash near-dup (free, CPU).** Exact hash =
   idempotent re-ingest (lift LightRAG/cognee/HippoRAG primitives — also the D7 rebuild cache).
   MinHash adds the *paraphrase/near-dup* suppression nobody ships: a near-dup of an
   already-extracted chunk → **chunks-only** (it's still searchable via P1, but earns no
   extraction). Config: 5-gram shingles, ~112-perm, LSH banding.
2. **Embedding-novelty router (marginal-zero — embedding sunk at E1).** Cosine of the chunk
   embedding vs. existing claim/relation embeddings in Lance. **High similarity to known facts +
   high evidence_count already present → deferred** (the fact is well-attested; re-extraction has
   low marginal value — note `evidence_count` is the free salience signal D2 already provides).
   **Clear novelty → carry to the classifier.** Novelty is a *router*, never the sole gate (novel
   boilerplate is still boilerplate).
3. **Distilled small classifier — THE value gate (CPU, ~6× cheaper than an LLM, GPU-free).** A
   fastText/BERT-style classifier scoring "extraction-worthiness" (information density + source
   trust as features). Output band → tier: high → **full**, middle → **deferred**, low →
   **chunks-only**. Trained by the two-stage distillation pattern (§4.3).
4. **Frontier-LLM judge — OFF the hot path.** Used **only** to label the seed/golden set the
   classifier distills from (Ask-LLM-style yes/no extraction-worthiness prompt), and for periodic
   audit of the classifier's middle band. **Never a steady-state per-doc call** — its per-item cost
   is the same order as a single extraction call, which would violate gate ≪ extraction and can't be
   amortized the way pretraining amortizes it over many training runs.

### 4.2 The three output tiers

- **FULL** — run the complete E2→E3 chain (coref → Claimify → ER → relation normalization →
  supersession). For high-density, novel, trusted body text.
- **DEFERRED** — embed + index for P1 search now (cheap), **enqueue extraction on a deferred-work
  queue**; promote to FULL when **(a)** the chunk is first *retrieved* (query-demand signal,
  §2.1), or **(b)** a compiled K2 scope declares interest in its entities, or **(c)** novelty later
  rises (a now-contradicting fact arrives). This is O3's "lazy extraction / progressive disclosure
  of *processing*." The per-document chain (D12) "already supports staged triggering"
  (`objections.md:84`).
- **CHUNKS-ONLY** — embed + index for P1 retrieval, **never extract claims/relations**. The text
  stays findable (P1 semantic/BM25) but earns no extraction cost and **never pollutes E3/relations
  or P2/graph** — directly answering O3's "junk in L2 poisons relations, the graph, and every
  compiled layer downstream" (`objections.md:71-72`). References, boilerplate, near-dups, low-value
  filler land here.

### 4.3 Tie to ugm decisions

- **D1 (source of truth):** the gate decision (tier + signal scores + classifier/prompt version) is
  recorded in **Postgres** per chunk — auditable, re-runnable, versioned like every other E-plane
  artifact. Re-gating after a better classifier = a batch job over stored signals, not a migration.
- **D4 (cheap-first cascade):** the five rungs *are* a D4 cascade — heuristic → dedup → embedding →
  small classifier → (frontier LLM, off-path). Same discipline D4 applies to supersession, applied
  to the extraction decision. Escalate only on the residue the cheap rung couldn't decide.
- **D7 (rebuildable):** the exact-hash rung doubles as the idempotent extraction cache (HippoRAG
  pattern) so a P-plane rebuild / re-ingest costs ~0 extra LLM. Gate decisions are deterministic
  given stored signals + versioned classifier, so the gate is replayable.
- **D12 (triggers):** the gate is the **missing trigger that withholds the expensive call** — it
  converts the E1→E2 edge from unconditional into conditional, and the DEFERRED tier introduces the
  *demand-driven* trigger (extract-on-retrieval) D12 currently lacks. Aggregate planes K/P are
  unaffected (still debounced/scheduled).
- **O3 (the objection):** this is the direct implementation — cheap salience gate → full / deferred /
  chunks-only, plus lazy extraction as the deferred-tier promotion path. Realizes the "plausibly
  10×" lever GraphRAG's 75%-of-cost figure bounds.
- **O6 dependency (must flag):** every threshold and the classifier itself are **untunable without a
  golden set**. The seed set the LLM judge labels to distill the classifier (§4.1 rung 4) **is** that
  golden set — so building the gate and building the eval harness are the same first task. Do not
  ship hard-coded thresholds (cognee's unused `importance_weight` is the cautionary anti-pattern).

### 4.4 One-line build order

Ship rungs 0–2 first (heuristics + dedup + embedding-novelty) — they are free/marginal-zero, need
no training data, and already capture the references/boilerplate/near-dup cases that motivate O3.
Add the distilled classifier (rung 3) once the seed/golden set exists. Treat lazy/query-demand
extraction (DEFERRED promotion) as a fast-follow pilot, not a launch dependency.

---

### Sources

Repo findings (this workspace):
`plan/analysis/value_gate_research/repo_findings/graphrag_lightrag_hipporag.md`,
`.../mem0_cognee.md`,
`plan/analysis/registry_research/repo_findings/splink_dedupe.md`,
`.../zingg.md`,
`.../lightrag_graphrag.md`.

Literature:
[FineWeb (NeurIPS 2024)](https://papers.neurips.cc/paper_files/paper/2024/file/370df50ccfdf8bde18f8f9c2d9151bda-Paper-Datasets_and_Benchmarks_Track.pdf) ·
[FineWeb writeup](https://zeroentropy.dev/concepts/fineweb/) ·
[How to Train Data-Efficient LLMs (Ask-LLM / Density), arXiv:2402.09668](https://arxiv.org/abs/2402.09668) ·
[Ask-LLM/Density summary](https://vladbogo.com/blog/2024/02/19/how-to-train.html) ·
[SemDeDup, arXiv:2303.09540](https://arxiv.org/abs/2303.09540) ·
[NeMo Curator semantic dedup](https://docs.nvidia.com/nemo/curator/curate-text/process-data/deduplication/semdedup) ·
[Ultra-FineWeb, arXiv:2505.05427](https://arxiv.org/html/2505.05427v1) ·
[Measuring Data Quality for LLM Training (BRICS)](https://brics-econ.org/measuring-data-quality-for-llm-training-model-based-and-heuristic-filters) ·
[MixMinMatch (MinHash params), arXiv:2512.18834](https://arxiv.org/html/2512.18834) ·
[SimHash & Hamming distance explainer](http://ben-whitmore.com/simhash-and-solving-the-hamming-distance-problem-explained/) ·
[Detecting Near-Duplicates for Web Crawling (Manku/Google)](https://research.google.com/pubs/archive/33026.pdf) ·
[In Defense of MinHash Over SimHash, arXiv:1407.4416](https://arxiv.org/pdf/1407.4416) ·
[Query-Driven Multimodal GraphRAG (ACL 2025)](https://aclanthology.org/2025.findings-acl.1100.pdf) ·
[RAKG, arXiv:2504.09823](https://arxiv.org/html/2504.09823v1).
