# V5 — The rare-but-critical-fact problem: gating WITHOUT losing gems

**Question.** O3 proposes a salience/novelty gate before E2 claim extraction (plausibly a 10×
cost lever). The classic failure mode of any such gate is dropping a low-frequency but vital
fact — the "user has a penicillin allergy," the one-off key decision. How do we gate while making
the gate *reversible and low-regret*? Survey the safeguard set (defer-don't-drop, retrieval-
triggered backfill, salience override/pinning, never-drop rules, sampling audits) and the
empirical evidence on recall loss from aggressive filtering, then recommend a concrete safeguard
set for ugm tied to D1/D4/D7/D12 and O3.

Sources: cited inline (URLs + repo `file:line`). Verified fact vs. inference is flagged
throughout. No benchmark numbers are invented; where a number is the paper's own, it is quoted.

---

## 1. Key findings

1. **The gate is structurally a deferral, not a deletion — ugm is unusually well-positioned to
   make it low-regret.** The danger in the literature is that "gate" = *evict/prune/forget*,
   which is lossy by construction (LRU/TTL/salience eviction physically removes the record). In
   ugm the gate sits at **E2 (claim extraction)**, *downstream* of **E0/E1 which are immutable
   and authoritative** (Postgres + GCS hold every original byte and chunk forever — D1, overall_design
   §2). A skipped or deferred document is **never lost; it is un-extracted.** So O3's gate can be
   expressed as DEFER-don't-DROP almost for free: the L0/E0 layer *is* the immutable backstop the
   eviction literature has to bolt on. This is the single most important framing for V5.

2. **The empirical case both ways is real: aggressive filtering of *redundant* content is nearly
   free, but the dropped tail is exactly where rare facts hide.** Zero-RAG prunes **30% of the
   Wikipedia corpus with <2-point average degradation**, and on TriviaQA removing **70% costs
   only 0.62 points** — strong evidence that most corpus volume is redundant and gateable
   ([arXiv 2511.00505](https://arxiv.org/abs/2511.00505)). But their pruning criterion is
   *"how well the LLM already masters this passage"* (Mastery-Score) — i.e. they prune **what the
   model already knows**, which is the opposite of a rare user-specific fact. The aggregate
   "<2-point drop" is silent on the long-tail: a single penicillin-allergy fact is a rounding
   error in corpus-level recall@k yet a catastrophic individual miss. **Aggregate recall metrics
   systematically under-weight rare-but-critical facts** — so the gate must be tuned and audited
   on *per-fact* loss, not corpus averages (this is also why O6's eval loop is a hard dependency).

3. **The frequency-as-importance proxy is the named failure mode, and the named fix is salience
   override + never-drop classes.** Mem0's own eviction write-up states it plainly: *"LRU treats
   access frequency as a proxy for importance, and that proxy breaks for low-frequency, high-stakes
   data,"* with the canonical example *"If the agent has not had occasion to surface a user's
   penicillin allergy in six months, an LRU policy will quietly prune it"*
   ([mem0.ai](https://mem0.ai/blog/memory-eviction-and-forgetting-in-ai-agents)). The prescribed
   discipline — *"Passive aging is for noise. Active forgetting is for facts"* — is exactly the
   safeguard split ugm needs: cheap automatic deferral for boilerplate, but **never automatic drop
   for fact-bearing / high-stakes content; that requires an explicit, evidenced decision.**

4. **All five safeguards are independently attested and composable; together they make the gate
   reversible.** DEFER-don't-DROP (immutable backstop), retrieval-triggered backfill (lazy
   extraction on first retrieval), salience override / pinning (importance beats frequency),
   never-drop rules by source/type (allergies, decisions, user-authored), and sampling audits of
   the deferred stream (canary-style) each appear in the surveyed systems and map cleanly onto
   ugm's existing primitives (D4 cascade, D7 rebuild, D12 triggers, the entity-registry's
   canary/audit pattern). **None requires new infrastructure ugm doesn't already plan** — the
   deferred-work queue is already named in O3, the rebuild path in D7, the audit cadence in O5/O6.

---

## 2. Evidence & detail with citations

### 2.1 Why the gate is a deferral in ugm (architecture, verified from repo)

- **E0/E1 immutability is the backstop.** Postgres is "source of truth for plane E"; GCS is
  "source of truth for file bytes"; both are append-only and never overwritten
  (overall_design.md §2 store table, lines 45–57; D1 decisions.md:12–26). Chunks (E1) carry
  references back to document + PageIndex node (overall_design.md §4 step 2). **A gate at E2
  therefore decides only whether to spend LLM extraction now; the underlying evidence remains
  fully present and re-processable.** *(Verified: repo file:line.)*
- **D7 makes re-extraction routine, not a disaster-recovery script.** "'Rebuildable from
  Postgres' is exercised every cycle instead of rotting as a DR script" (D7, decisions.md:131);
  workers are "idempotent (content hash + processing version)" (D12, decisions.md:216). *(Inference,
  well-grounded): re-running E2 over a previously-deferred document is the same idempotent path as
  a normal first extraction — backfill is a no-new-machinery operation.*
- **D12 already has a deferred/debounced trigger model.** The per-document chain ends at E2/E3;
  K and P planes are window/debounce-triggered (D12, decisions.md:213–223). *(Inference): a
  "deferred extraction" queue is the same Cloud-Tasks + debounce primitive, just with a different
  enqueue condition — O3's "deferred-work queue" is consistent with the existing trigger
  substrate.*

### 2.2 Empirical evidence on recall loss from aggressive filtering

- **Redundant-content pruning is cheap (the case *for* a gate).** Zero-RAG: *"Zero-RAG prunes the
  Wikipedia corpus by 30% and accelerates the retrieval stage by 22%, without compromising RAG's
  performance"*; *"pruning 30% of the database results in only minimal performance degradation —
  averaging less than a two-point drop at moderate pruning levels"*; *"for TriviaQA, removing 70%
  of the corpus results in merely a 0.62-point drop"*
  ([arXiv 2511.00505](https://arxiv.org/abs/2511.00505), HTML v1). **Caveat (flagged):** their
  prune target is passages **the LLM already masters** (Mastery-Score over generated QA pairs) —
  this validates dropping *globally-known boilerplate*, NOT user-specific rare facts. The paper's
  limitations section discusses only "Generalizability Across Domains" and "Dependency on Initial
  Data Quality" and **does not quantify long-tail / rare-query loss** (verified absent in fetched
  text). So this is strong evidence that *most volume is gateable* and **weak/no evidence on the
  rare-fact tail** — precisely the gap V5 must cover with safeguards rather than rely on the
  aggregate number.
- **An interpretive search summary** (not located in the paper's own abstract/limitations) framed
  pruning as shifting "evidence from high-density results to lower-density results … compression
  often removes answer-bearing details even when retrieved context is broadly relevant"
  ([search synthesis](https://arxiv.org/pdf/2511.00505)). **Flag: could not verify this exact
  sentence in the fetched paper text — treat as plausible interpretation, not a quoted finding.**
- **Long-tail retrieval is already weak before any pruning.** A practitioner synthesis reports
  long-tail domains "typically achieve 60–70% recall before tuning, compared to 80% for most
  FAQ/help-center corpora"
  ([Medium/Nexumo](https://medium.com/@Nexumo_/the-8-retrieval-benchmarks-lying-to-your-rag-5811ca3ee057)).
  **Flag: blog-grade source, directional only, not a peer-reviewed figure.** Directionally it
  reinforces that the rare tail has the least recall headroom to spend on a gate.
- **The frequency proxy explicitly fails for high-stakes low-frequency data** (mem0, quoted in
  §1.3). Mem0 also notes the *interference* argument in the other direction — *"An agent that
  remembers everything is an agent that recalls badly … every additional fact in the index is
  another candidate to surface during a top-k search, and most of those candidates are noise"*
  ([mem0.ai](https://mem0.ai/blog/memory-eviction-and-forgetting-in-ai-agents)). **For ugm this
  interference cost is much weaker than for mem0**, because ugm collapses corpus redundancy into
  *one relation with N evidence rows* (D2, decisions.md:42–45) — N documents asserting the same
  fact do not produce N index candidates. So ugm's gate is justified by *LLM extraction cost*
  (O3), far more than by retrieval-time interference. *(Inference, grounded in D2.)*
- **Benchmarks now penalize obsolete recall, validating defer/supersede over hard-drop.** Memora
  introduces *Forgetting-Aware Memory Accuracy (FAMA), a metric that penalizes reliance on
  obsolete or invalidated memory*; MemoryAgentBench finds *"all paradigms exhibit dramatic
  failures on multi-hop conflict resolution, with best accuracy remaining at or below 6% for
  multi-hop cases"*
  ([MemoryAgentBench arXiv 2507.05257](https://arxiv.org/pdf/2507.05257);
  [From Recall to Forgetting / Memora](https://arxiv.org/html/2604.20006v1)). **Flag: I read these
  via search-result summaries, not the full PDFs — directionally reliable, exact context
  unverified.** Takeaway for ugm: the correct treatment of *stale* facts is **supersession at the
  relation level (D3), not dropping the claim** — claims are immutable records of what a source
  asserted (D2/D3, decisions.md:30–62). ugm's data model already encodes the "active forgetting is
  for facts" discipline as window-closing, not deletion.

### 2.3 Retrieval-triggered backfill / lazy extraction (precedent)

- O3 itself proposes the ideal: *"extract claims when a document's chunks first get retrieved, or
  when a compiled scope declares interest in its entities"* (objections.md:78–79). This is **lazy
  extraction keyed on demand.**
- Precedent for deferring heavy work to a demand/offline trigger: AgentCore / consolidation
  designs *"keep high-frequency online memory decisions lightweight … while deferring heavy
  abstraction and consolidation to offline processing"*
  ([AWS AgentCore](https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/));
  consolidation triggers are *"time-based … event-based … or resource-based"*
  ([apxml](https://apxml.com/courses/agentic-llm-memory-architectures/chapter-3-designing-memory-systems/memory-consolidation-summarization)).
  **Flag: industry/blog sources; establish that demand- and event-triggered deferred processing is
  standard practice, not novel risk.**
- **Reversible-deferral substrate is a solved pattern in adjacent systems** (soft-delete /
  tombstone / restore-on-access): Active Directory tombstones keep deleted objects "just long
  enough" and the Recycle Bin "preserves all object attributes … making restoration trivial"
  ([reintech](https://reintech.io/blog/handling-active-directory-tombstoned-objects-reanimation));
  S3 Intelligent-Tiering auto-archives cold data and restores on access
  ([AWS S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intelligent-tiering-managing.html)).
  **Flag: storage-systems analogies, not memory-system results.** The point is only that
  "cheap-tier-until-touched, restore-on-demand" is mature engineering — ugm's E0-immutable +
  on-retrieval-extract is the same shape and inherits its reversibility.

### 2.4 Salience override / pinning, never-drop rules, sampling audits (precedent)

- **Salience over frequency:** *"Salience scoring shifts the eviction question from 'when was this
  used' to 'how much does this matter'"* — but mem0 flags **rater drift** as salience's own risk:
  *"when the model scoring salience changes versions or prompts, previously calibrated thresholds"*
  become unreliable
  ([mem0.ai](https://mem0.ai/blog/memory-eviction-and-forgetting-in-ai-agents)). **Implication
  for ugm:** any salience threshold must be versioned alongside prompt/model (D1 already records
  prompt/model/embedding versions per artifact, decisions.md:25–26) so a threshold can be
  re-evaluated when the scorer changes — and audited (O6).
- **Sampling audits + canaries are already ugm's accepted ER pattern, and transfer directly.**
  entity_registry.md:169 prescribes *"Sampled human audits + canary entities (known-tricky cases
  re-run per resolver"* and :161–169 the general audit discipline; splink/dedupe is logged as the
  right tool for *"backfill campaigns"* (entity_registry.md:32). *(Verified: repo file:line.)*
  **The same machinery audits the deferred/dropped stream:** sample the gate's "deferred" and
  "chunks-only" decisions, plant canary documents containing planted rare facts, and measure how
  many a given threshold would have buried. O6's golden set (objections.md:143–148) is the natural
  home for these canaries.
- **Never-drop-by-source/type** is the data-model-level expression of "active forgetting is for
  facts." ugm has the typing to express it: claims are typed and temporally classified
  (overall_design.md §3); the predicate registry + ontology with domain/range (D5, D15) can mark
  high-stakes predicate/type classes (e.g. medical, legal, explicit user directives) as
  **never-defer**. *(Inference, grounded in D5/D15.)*

---

## 3. Confidence & gaps

**Overall confidence: medium-high.**

- **High confidence (verified repo + directly-quoted external):**
  - The architectural claim that ugm's gate is a deferral over an immutable E0/E1 backstop, making
    backfill a no-new-machinery rebuild (D1, D7, D12 — verified file:line). This is the core of
    the recommendation and it rests on the repo, not on external benchmarks.
  - The frequency-proxy failure mode and the penicillin-allergy framing (mem0, exact quotes).
  - Zero-RAG's headline pruning numbers (30% / <2pt / 70%→0.62pt — quoted from the paper).
  - That ugm's audit/canary pattern already exists and transfers (entity_registry.md, verified).

- **Medium confidence (directionally reliable, source-grade caveats):**
  - That redundant-content pruning generalizes to ugm's E2 gate. Zero-RAG prunes *model-mastered*
    passages, a different criterion than O3's salience gate; the transfer is by analogy.
  - Lazy/deferred-processing and soft-delete/restore precedents are blog/industry-grade and from
    adjacent (storage, online-memory) domains, not from claim-extraction pipelines specifically.

- **Gaps / could-not-verify (explicitly flagged):**
  - **No quantified study of rare-fact recall loss from a *salience/value* gate specifically.** The
    eviction studies (TTL/LRU/salience) discuss the *mechanism* and the *penicillin* failure mode
    qualitatively; I did **not** find a paper that measures "fraction of one-off critical facts lost
    at gate threshold τ." This is the precise number V5 would want and it does not appear to exist
    publicly — **ugm must generate it in-house via O6's golden set / canaries.**
  - The "pruning shifts high-density→low-density evidence / removes answer-bearing details"
    sentence could **not be confirmed** in the Zero-RAG paper text I fetched (appeared only in a
    search synthesis) — flagged as unverified.
  - MemoryAgentBench / Memora FAMA details were read via search summaries, not full PDFs.
  - The long-tail "60–70% recall" figure is a single practitioner blog — directional only.

---

## 4. Recommendation for ugm (concrete; tied to D1/D4/D7/D12 and O3)

Adopt a **five-part reversibility envelope** around O3's E2 salience gate. The gate's *output is
never DROP* — it is one of `{EXTRACT_NOW, DEFER, CHUNKS_ONLY}` — and every state is recoverable.

1. **DEFER-don't-DROP as the gate's contract (leverages D1 + D7).**
   The gate never deletes evidence; E0/E1 are immutable (D1). A document the gate routes to DEFER
   or CHUNKS_ONLY remains fully indexed at E1 (chunks searchable in P1) and fully re-extractable.
   Persist a `extraction_status ∈ {extracted, deferred, chunks_only}` + the gate's
   score + the **gate prompt/model version** (D1 already versions derived artifacts) on the
   document/section row in Postgres. Because re-extraction is the same idempotent worker (D12)
   over the same Postgres/GCS truth (D7), backfill is a routine enqueue, not a recovery operation.
   *This is the highest-leverage, lowest-cost safeguard and the one ugm gets almost for free.*

2. **Retrieval-triggered backfill (implements O3's lazy path on D12 triggers).**
   When a `deferred`/`chunks_only` document's chunk is returned by P1 retrieval (it still
   participates in semantic/BM25 search — that's why CHUNKS_ONLY exists), **enqueue its E2
   extraction.** Demand is the strongest possible salience signal: a rare fact that is *never*
   queried costs nothing un-extracted; the moment it's relevant, it gets promoted. Reuse the
   existing Cloud-Tasks/debounce substrate (D12); debounce so a popular deferred doc enqueues once.
   Also honor O3's second trigger: when a K2 scope "declares interest" in a document's entities,
   backfill it.

3. **Salience override / pinning + never-drop classes (counters the frequency-proxy failure; D5/D15).**
   Make **importance beat the cheap gate.** Two mechanisms:
   - **Never-defer type/predicate classes**, declared as rows in the predicate/ontology registry
     (D5, D15): high-stakes classes (medical/allergy, legal, security, explicit user
     directives/decisions) bypass the gate to EXTRACT_NOW regardless of salience score. This is the
     data-model expression of mem0's *"active forgetting is for facts."*
   - **Source-trust pinning:** user-authored / first-party / curated sources pin to EXTRACT_NOW;
     low-trust bulk/scraped sources are the gate's primary deferral target. (ugm already
     distinguishes source provenance in evidence.)
   Version every salience threshold with prompt/model (D1) to survive mem0's "rater drift."

4. **Cheap-first decision *for the gate itself* (mirrors D4's cascade philosophy).**
   The gate must not become a new cost center. Decide `EXTRACT_NOW/DEFER/CHUNKS_ONLY` with a
   cheap-first cascade exactly as D4 does for supersession: deterministic rules first (never-drop
   classes, source-trust, PageIndex section type — e.g. a "References" section → CHUNKS_ONLY) →
   cheap embedding/heuristic salience → small model only on the ambiguous residue; a frontier LLM
   essentially never. A gate that itself costs an LLM call per document would erase O3's savings.

5. **Sampling audits of the deferred stream (reuses ugm's canary/audit pattern; closes O6).**
   The gate is a tunable with no ground truth until measured (O6). Operationalize:
   - **Canary documents** in O6's golden set, each carrying a planted rare-but-critical fact;
     CI fails if a candidate threshold would route any canary to DEFER without a retrieval that
     backfills it. (Directly reuses entity_registry.md:169 canary discipline.)
   - **Sampled human audit** of a random slice of `deferred`/`chunks_only` decisions at the O5/O6
     cadence — measure the in-house number the literature lacks: *rare-critical-fact deferral rate
     at threshold τ.* Tune τ against that, never against corpus-average recall.
   - **Backfill campaigns** (the splink/dedupe pattern, entity_registry.md:32): when a threshold is
     found too aggressive, batch-re-extract the affected deferred set — cheap because it's the
     same rebuild path (D7).

**Net.** O3's gate is safe to ship aggressively **because** ugm's planes make it reversible:
E0/E1 immutability (D1) is the backstop, D7 rebuilds make backfill routine, D12 triggers carry
both the deferral and the retrieval-triggered promotion, D4's cascade keeps the gate cheap, and
the registry (D5/D15) plus O6's golden set/canaries pin the gems and prove the loss rate. The one
thing the public literature cannot give ugm — *how many one-off critical facts a given threshold
loses* — is exactly what the O6 canary/audit loop is built to measure, so the gate stays low-regret
and tunable rather than a blind bet.

---

### Sources
- [Memory eviction and forgetting in AI agents — mem0.ai](https://mem0.ai/blog/memory-eviction-and-forgetting-in-ai-agents)
- [Zero-RAG: Towards Retrieval-Augmented Generation with Zero Redundant Knowledge — arXiv 2511.00505](https://arxiv.org/abs/2511.00505)
- [Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions (MemoryAgentBench) — arXiv 2507.05257](https://arxiv.org/pdf/2507.05257)
- [From Recall to Forgetting / Memora (FAMA) — arXiv 2604.20006](https://arxiv.org/html/2604.20006v1)
- [AgentCore long-term memory deep dive — AWS](https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/)
- [Memory Consolidation and Summarization Techniques — apxml](https://apxml.com/courses/agentic-llm-memory-architectures/chapter-3-designing-memory-systems/memory-consolidation-summarization)
- [The 8 Retrieval Benchmarks Lying to Your RAG — Medium/Nexumo](https://medium.com/@Nexumo_/the-8-retrieval-benchmarks-lying-to-your-rag-5811ca3ee057)
- [Handling AD Tombstoned Objects and Reanimation — Reintech](https://reintech.io/blog/handling-active-directory-tombstoned-objects-reanimation)
- [Managing S3 Intelligent-Tiering — AWS](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intelligent-tiering-managing.html)
- Repo: `decisions.md` (D1:12–26, D2:30–45, D3:49–62, D4:66–80, D7:116–133, D12:213–223, D15, D16);
  `plan/designs/overall_design.md` §2–§5; `plan/analysis/objections.md` (O3:65–86, O6:132–152);
  `plan/analysis/entity_registry.md` (:32, :161–169); value_gate `repo_findings/*.md`.
