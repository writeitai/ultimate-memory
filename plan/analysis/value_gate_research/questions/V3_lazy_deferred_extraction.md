# V3 — Architecture for LAZY / DEFERRED / on-demand extraction

**Question (O3, second half):** Architecture for lazy/deferred/on-demand E2/E3 extraction.
Patterns (eager vs lazy materialization, extract-on-first-retrieval + cache, priority work
queues, backfill-on-demand, extract-on-scope-interest). Who does this (LazyGraphRAG,
RAG-on-demand)? **Consistency:** does deferral break "rebuildable from Postgres" (D7) and the
per-doc trigger chain (D12)? Is the *defer decision* itself versioned/replayable state? How to
keep deferred work tracked / idempotent / not-lost. **Recall risk:** deferred docs contribute
nothing to global aggregation (K1/K2/K3) until pulled — acceptable? mitigations.

Scope note: this answers the *deferred* half of O3. The *gate decision* (full / deferred /
chunks-only, the salience classifier itself) is the sibling question; here a "defer verdict" is
taken as a given input and the focus is the **machinery that holds, tracks, replays, and
eventually executes** deferred work without violating ugm's invariants. "not found" = grepped/
read and absent in the cited checkout; benchmark numbers are quoted verbatim from the cited
source and not invented.

---

## 1. Key findings

1. **Lazy extraction is real, proven, and quantified — but only as a *whole-corpus retrieval
   strategy* (LazyGraphRAG), not as a *per-document defer-and-backfill* mechanism.** Microsoft's
   LazyGraphRAG *defers all LLM-based summarization/claim-extraction to query time*, keeping
   only a cheap NLP noun-phrase co-occurrence graph at index time, and reports **"data indexing
   costs … 0.1% of the costs of full GraphRAG"** and **">700× lower query cost"** than GraphRAG
   global search at comparable quality ([Microsoft Research](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)).
   This is the strongest external evidence that O3's "10× lever" is conservative. **But
   LazyGraphRAG does NOT cache/materialize what it extracts at query time** — the Microsoft blog
   "does not address whether extracted claims are cached," and the design re-extracts per query,
   trading a permanent index cost for a recurring query cost + latency. ugm wants the *opposite
   trade*: defer once, then **extract-on-trigger and persist into the Postgres ledger** so the
   work is paid at most once. So LazyGraphRAG validates the *economics* of deferral but is **not
   a reusable architecture** for ugm's persistent-ledger model.

2. **None of the cloned ingestion systems implement deferral at all — they are uniformly eager.**
   GraphRAG, LightRAG, HippoRAG, mem0, and cognee all extract on ingest; the only "skip"
   primitives any of them have are **exact content-hash idempotency caches** (re-ingest of
   identical bytes costs ~0), never a "defer this document's extraction until something needs it"
   path (`value_gate_research/repo_findings/graphrag_lightrag_hipporag.md` §1–3;
   `mem0_cognee.md`). This means ugm's lazy/deferred tier is **unbuilt prior art** — the reusable
   pieces to lift are the *idempotency hash caches* (HippoRAG chunk-hash OpenIE cache, LightRAG
   `compute_text_content_hash`) as the floor, plus a job-queue/durable-execution pattern for the
   deferred work itself, which lives entirely outside these repos.

3. **Deferral does NOT break D7 (rebuildable-from-Postgres) or D12 (per-doc chain) *if the defer
   decision is materialized as a first-class, versioned row in Postgres* — and it actively
   strengthens both.** The per-doc chain (D12) already ends at E2/E3 and is built on idempotent
   Cloud-Tasks workers keyed by `content hash + processing version`; "defer" is just a **terminal
   state of E1's stage transition** that enqueues an E2 job *conditionally / lazily* instead of
   *immediately*. D7's rebuild guarantee covers "everything deterministically derivable" — the
   defer verdict (a classifier output) is exactly such a derivable artifact and belongs in the
   Postgres spine alongside processing state. The danger is the inverse: if the defer decision
   lives only in a queue (Cloud Tasks, Redis) and not in Postgres, a queue loss silently drops
   documents from extraction forever — *that* breaks D7 (you cannot rebuild what you never
   recorded you owed). **Recommendation hinges on this: the defer decision is durable Postgres
   state, the queue is a derived projection of it.**

4. **The recall risk is real and asymmetric, and the ledger model (D2) makes the right
   mitigation cheap.** A deferred document contributes **zero claims, zero relations, zero
   evidence-count** to K1/K2/K3 aggregation and to P2 graph until pulled — so a globally
   important fact buried in a "low-salience" PDF is invisible to every compiled scope. Pure
   on-first-*retrieval* laziness (LazyGraphRAG style) has a bootstrap hole: **you cannot retrieve
   what was never indexed**, so the document must remain reachable by *some* cheap channel (its
   E1 chunks, which are always embedded) for the lazy trigger to ever fire. Mitigations:
   (a) **always do E1 fully** (chunk + embed + PageIndex) even for deferred docs, so they are
   retrievable and can *self-trigger* extraction on first hit; (b) **extract-on-scope-interest**
   — a K2 scope declaring interest in an entity/predicate enqueues backfill for every deferred
   doc whose chunks mention it; (c) a **bounded backfill drain** (priority queue, oldest-/
   highest-evidence-first) so "deferred" means "later," never "never"; (d) treat the deferred
   set as a **measured quality property** (deferred-but-later-found-material rate) feeding O6's
   eval loop, so the gate's false-defer rate is tuned, not hoped.

---

## 2. Evidence & detail with citations

### 2.1 Who actually does lazy / deferred extraction

**LazyGraphRAG (Microsoft) — the canonical "defer to query time" system.** Verbatim from the
Microsoft Research blog ([link](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/),
fetched 2026-06):
- **Index time (cheap, deterministic):** "Uses NLP noun phrase extraction to extract concepts and
  their co-occurrences," then "uses graph statistics to optimize the concept graph and extract
  hierarchical community structure." No LLM. (This is GraphRAG's *Fast* pipeline lineage —
  spaCy/TextBlob, cf. `graphrag_lightrag_hipporag.md` §1.)
- **Query time (deferred LLM):** "LLM-based query refinement to identify subqueries,
  sentence-level relevance assessment of text chunks, and final **claim extraction** and answer
  generation." So *claim extraction itself is deferred to the moment a query touches the chunk.*
- **Numbers (verbatim):** "LazyGraphRAG data indexing costs are identical to vector RAG and
  **0.1% of the costs of full GraphRAG**"; "**more than 700 times lower query cost**" than
  GraphRAG global search for global queries; "for **4% of the query cost** of GraphRAG global
  search, LazyGraphRAG significantly outperforms all competing methods." Tunable via a single
  **"relevance test budget"** (how many chunks to relevance-test per query).
- **Caching:** the blog "does not address whether extracted claims are cached or re-extracted per
  query." The published design re-extracts per query (claim extraction is in the query path);
  an independent survey notes LazyGraphRAG "incurs high latency during retrieval, as it requires
  multiple LLM invocations … for a single query" ([E²GraphRAG, arXiv 2505.24226](https://arxiv.org/pdf/2505.24226)).

**Why this is validating but not directly reusable for ugm.** LazyGraphRAG trades a one-time
index cost for a *recurring* per-query LLM cost + latency, and (as published) **does not persist**
the extracted claims — every query re-pays. ugm's invariant is the opposite: extraction output is
**durable evidence in Postgres** (claims immutable/append-only, relations bi-temporal, D2/D3),
search is **zero-LLM** (D9), and P2 is a rebuildable projection (D6/D7). ugm therefore wants
**"defer the LLM extraction, but when it finally runs, run it once and write it to the ledger
forever,"** not LazyGraphRAG's "run it every query, throw it away." The *economic case* (O3's 10×)
transfers; the *mechanism* does not.

**RAG-on-demand / deferred matching in the literature is shallow.** The "Practical GraphRAG" line
([arXiv 2507.03226](https://arxiv.org/html/2507.03226v2)) and others describe "deferred entity
matching" (extract question entities, match later) — a *query-side* deferral, not a *corpus-side*
defer-and-backfill of extraction. No surveyed system implements "classify doc → defer → backfill
on interest → persist." This is a genuine gap.

**The cloned ingestion repos: uniformly eager, no defer path.** Confirmed by the prior repo
archaeology:
- GraphRAG: fixed workflow `chunk → extract_graph (LLM) → …`, "no filter/skip/salience step
  between chunking and extraction"; cost lever is *model swap* (Fast=NLP) not *defer*
  (`graphrag_lightrag_hipporag.md` §1).
- LightRAG: two **exact content-hash** dedup layers (`compute_text_content_hash`,
  `pipeline.py:473,501,665`) — idempotent re-ingest only; "no … 'is this chunk worth extracting'
  check anywhere" (ibid §2).
- HippoRAG: **exact chunk-hash OpenIE cache** (`load_existing_openie`, `HippoRAG.py:238`) — same
  rebuild/idempotency guarantee, no defer (ibid §3).
- mem0: one **unconditional** LLM call per `add()` (`main.py:765`); "spend-first" (`mem0_cognee.md`).
- cognee: extracts **every** chunk (`extract_graph_from_data.py:166`); only pre-LLM savers are
  file content-hash dedup + DLT-row deterministic skip — neither is a defer (`mem0_cognee.md`).

**Net:** the *idempotency hash caches* in these repos are the reusable floor (they guarantee
"extracting the same bytes twice is free," which is what makes a *backfilled* deferred doc safe to
run), but the **defer-and-track-and-backfill machinery is unbuilt prior art** ugm must add. This
directly mirrors `graphrag_lightrag_hipporag.md`'s closing note: "none of them stages extraction;
it's eager on ingest, the opposite of O3's lazy/deferred-on-retrieval proposal."

### 2.2 The defer patterns, mapped

| Pattern | What it is | Fit for ugm | Evidence |
|---|---|---|---|
| **Eager materialization** | extract on ingest (status quo, all repos) | the thing O3 wants to escape for low-value docs | all repo_findings |
| **Lazy / extract-on-first-retrieval + cache** | extract when chunks first retrieved, persist result | **core recommendation** — but ugm *caches into Postgres ledger* (unlike LazyGraphRAG which doesn't) | LazyGraphRAG (defer); HippoRAG/LightRAG hash cache (the persist) |
| **Priority work queue** | deferred jobs in a table, drained by `SELECT … FOR UPDATE SKIP LOCKED ORDER BY priority` | **how the backfill drain is implemented**; standard PG pattern | [PG SKIP LOCKED queue](https://www.dbpro.app/blog/postgresql-skip-locked); [graphile-worker pattern](https://www.netdata.cloud/academy/update-skip-locked/) |
| **Backfill-on-demand** | bounded drain of the deferred set (oldest / highest-evidence first) | the safety valve that makes "deferred ≠ never" | "if the job is backfill, order by the oldest unprocessed range" ([digitalapplied ref](https://www.digitalapplied.com/blog/background-job-queue-patterns-2026-engineering-reference)) |
| **Extract-on-scope-interest** | a K2 scope declaring interest in entity/predicate triggers extraction of deferred docs mentioning it | **ugm-specific, high-value** — ties laziness to the consumer (K2), aligns D16 "scopes declare extraction interests" | D16 ("extraction interests"); overall_design §4 note; no external prior art (novel) |

### 2.3 Consistency: D7 (rebuildable) and D12 (per-doc chain)

**D12 — the per-doc chain accommodates defer natively.** D12: "L0→L1→L2 chain per document
(Cloud Tasks) … idempotent workers keyed by content hash + processing version." The defer
decision is simply a **conditional edge** in this chain: E1 completes (chunks always embedded),
then instead of *unconditionally* enqueuing E2, it consults the gate verdict:
- `full` → enqueue E2 now (status quo);
- `deferred` → write a `extraction_deferred` row, **do not** enqueue E2;
- `chunks_only` → terminal, never enqueue E2 (a permanent defer with no backfill expectation).

This is *within* the per-doc chain, not a violation of it. The chain still "ends at E2/E3"
(D12) — it just ends earlier (at E1) for deferred docs, with a recorded reason. The idempotency
key (`content hash + processing version`) is what makes a *later* backfill safe: re-running E2 on
the same bytes is the same idempotent operation, exactly as HippoRAG's chunk-hash cache
guarantees (§2.1).

**D7 — deferral is rebuildable *iff the defer decision is Postgres state*.** D1/D7: Postgres is
authoritative for "everything deterministically derivable"; the rebuild path is "exercised every
cycle." The defer verdict (gate classifier output) **is** deterministically derivable from the
document + gate model/prompt version, so it belongs in Postgres by D1's own logic. Concretely:
- A `document_extraction_state` row carries `state ∈ {pending, full_done, deferred, chunks_only,
  backfill_queued, backfilling, backfill_done}`, `gate_verdict`, `gate_model_version`,
  `gate_prompt_version`, `deferred_at`, `defer_reason`, `processing_version`.
- **Rebuild semantics:** rebuilding P2/P1 from Postgres reads only *materialized* claims/relations
  — deferred docs simply have none yet, which is the *correct* current truth (they were never
  extracted). Nothing is lost: the rebuild faithfully reproduces "the corpus as extracted so
  far." The defer rows are part of the spine, so a Postgres PITR restore restores the *exact set
  of outstanding deferred work* — the queue can be regenerated from them.
- **The failure mode D7 forbids** is putting the defer decision *only* in Cloud Tasks / a transient
  queue. Then a queue purge = silently dropped documents with no Postgres record that extraction
  was owed → the system is *not* rebuildable (you'd rebuild missing those docs and never know).
  This is the durable-execution lesson: "durable execution … can be thought of as the combination
  of a queue system and a state store that remembers the most recently seen execution state"
  ([DBOS/Postgres](https://www.dbos.dev/blog/why-postgres-durable-execution)); and the
  **transactional-outbox** discipline — "the order row and the enqueued workflow commit (or roll
  back) together" ([DBOS outbox](https://docs.dbos.dev/python/examples/outbox)) — is exactly how to
  enqueue a backfill job *atomically with* flipping the Postgres state, so the two never diverge.

**Is the defer decision versioned/replayable state? — Yes, and it must be.** Tag every defer row
with `gate_model_version + gate_prompt_version` (D12 already mandates prompt/model versions on
every artifact; overall_design §8 "Versioning"). Then:
- **Replay:** a better gate later → re-classify deferred docs as a *batch job filtered by version*
  (same mechanism as embedding migration, overall_design §8, and as resolution re-decisions in
  `entity_registry.md` §4). A doc that was wrongly deferred under gate v1 gets re-promoted under
  gate v2 — no migration, just a new verdict row.
- **Audit:** "why is this doc not in the graph?" answers from one row: `deferred, reason=…,
  gate v1.2, at T`. This is the same transcript/verdict epistemics ugm uses for claims (D2) and
  resolution (registry §4) — *the defer decision is a verdict over evidence, append-only and
  re-adjudicable.*

### 2.4 Tracked / idempotent / not-lost

- **Tracked:** `document_extraction_state` table (above) is the single source of outstanding work.
  A deferred doc is never "lost" because its non-extraction is an explicit recorded state, not the
  absence of a queue message.
- **Idempotent:** backfill re-runs E2/E3 keyed by `content hash + processing version` (D12); the
  exact-hash extraction caches from HippoRAG/LightRAG (§2.1) make a duplicate backfill a no-op.
  Claims are append-only with source-assertion identity (D2), so a double-extraction produces
  *the same* claim rows (idempotent on `(source, assertion)`), and relation dedup on `(s,p,o)`
  (D2) absorbs the rest.
- **Not-lost / queue == projection of Postgres:** the work queue (PG table drained via
  `FOR UPDATE SKIP LOCKED ORDER BY priority DESC, deferred_at ASC` —
  [pattern](https://www.dbpro.app/blog/postgresql-skip-locked)) is *derived* from the
  `document_extraction_state` rows in `deferred`/`backfill_queued` state. If the queue is lost,
  it is **regenerable by a SQL query** over Postgres — the canonical "rebuildable" property (D7)
  applied to the work list itself. Cloud Tasks (D12) can carry the *message*, but the *truth* of
  what is owed is the Postgres row; enqueue them together via the outbox discipline (§2.3).
- **Backfill triggers (what moves a row from `deferred` → `backfill_queued`):**
  1. **on-first-retrieval** — a search hit on a deferred doc's E1 chunk enqueues its E2 backfill
     (lazy materialization, LazyGraphRAG-style trigger, but persisted);
  2. **on-scope-interest** — a K2 scope's declared entity/predicate interest (D16) matched against
     deferred docs' chunk embeddings/PageIndex noun-phrases enqueues backfill;
  3. **bounded steady-state drain** — a low-priority worker drains the oldest deferred docs so the
     backlog is bounded and "deferred" decays to "done" over time;
  4. **gate-version re-classification** — a new gate promotes previously-deferred docs.

### 2.5 Recall risk and mitigations

**The risk (verbatim framing of O3):** a deferred doc "contributes nothing to global aggregation
until pulled." Concretely it has **no claims → no relations → no evidence_count → no graph edges →
invisible to K1/K2/K3 and P2**. Because K3 beliefs are seeded from *high-evidence* relations (D2,
overall_design §5), a fact whose only support sits in deferred docs has artificially low (zero)
evidence and may never surface as a belief — a silent recall miss, the same *invisible* failure
class O5 flags for entity-resolution false-negatives.

**Why pure on-retrieval laziness is insufficient alone:** you cannot retrieve what was never
indexed. LazyGraphRAG escapes this only because it *always* builds the cheap concept graph over
*all* docs at index time. ugm's analogue: **E1 must run fully on every document, deferred or not**
— chunk + context-prefix + embed + PageIndex are cheap relative to E2/E3 LLM extraction and keep
the deferred doc *retrievable*, which is the precondition for the lazy trigger to ever fire. So the
defer boundary is drawn **between E1 and E2**, never before E1.

**Mitigations (recommended set):**
1. **Always-full E1.** Deferred ≠ unindexed. Every doc is chunked, embedded, PageIndexed →
   retrievable → self-triggers E2 on first material hit. Closes the bootstrap hole.
2. **Extract-on-scope-interest (D16).** When a K2 scope registers interest in entity/predicate X,
   run a backfill sweep: deferred docs whose chunks mention X get E2 enqueued. This is the
   highest-leverage mitigation — it ties extraction cost to *demonstrated consumer demand*, the
   exact "progressive disclosure of processing" O3 asks for, and it's where ugm beats LazyGraphRAG
   (the scope makes the laziness *targeted*, not query-random).
3. **Bounded backfill drain.** A background priority worker guarantees every deferred doc is
   eventually extracted (e.g., within an SLA window), so the gate is a *scheduler*, not a
   *discard*. Order by `priority, deferred_at` (oldest-first) or by a cheap salience prior
   (PageIndex summary length, citation in-degree, evidence-count of mentioned entities).
4. **Conservative gate + measured false-defer rate (O6 hook).** Mirror the entity-registry
   discipline (`entity_registry.md` §1, §7): under-defer (extract slightly too much) is a gradual
   cost; over-defer (skip a globally material doc) is a silent quality hole — so **tilt the gate
   conservative** and **measure** the "deferred-but-later-found-material" rate (docs whose
   backfill produced high-evidence/high-degree relations) as a production metric feeding O6's eval
   loop. Threshold tuning needs the golden set (O6), same dependency the registry has.
5. **K3/belief guard.** Because K3 is evidence-gated, optionally exclude entities with a high
   fraction of *deferred* mentions from belief promotion until backfilled — prevents a belief from
   being asserted or denied on a knowingly-incomplete evidence base.

**Acceptable?** Yes, *with* mitigations 1–4. The acceptability argument is the same as D7's for
P2: staleness is bounded and exercised, not unbounded and hoped. "Deferred" with a bounded drain +
on-interest + on-retrieval triggers is a *freshness SLA on extraction*, directly analogous to D7's
"freshness SLA = rebuild cadence." Without the always-full-E1 + bounded-drain guarantees, it is
**not** acceptable — it degenerates to silent permanent data loss, the D7 violation in §2.3.

---

## 3. Confidence & gaps

**Confidence: HIGH** on the consistency analysis (D7/D12) and the recommendation shape — it
follows directly from ugm's own decisions read against the repo archaeology, and the
durable-execution / outbox / SKIP-LOCKED patterns are well-established and independently cited.
**HIGH** on "no cloned system implements defer" (grepped/read in prior findings). **HIGH** on the
LazyGraphRAG cost figures and what it defers (quoted verbatim from Microsoft Research).

**MEDIUM/uncertain:**
- **Whether LazyGraphRAG caches query-time extractions.** The Microsoft blog is silent; the
  published design re-extracts per query. I did **not** read the LazyGraphRAG *implementation*
  source (the GitHub discussion #2061 indicates it was community-reimplemented, not in the main
  repo at the time). Flagged as inference, not verified code.
- **Exact false-defer rate / 10× claim.** O3's "plausibly 10×" and LazyGraphRAG's "0.1% indexing
  cost" are *not* the same metric (LazyGraphRAG defers *100%* of extraction; ugm would defer only
  the low-salience fraction). The realized ugm cost saving depends entirely on the gate's defer
  rate × the deferred set's later-backfill rate — **unmeasurable without O6's eval loop and a real
  corpus.** Do not quote a multiplier as a ugm projection.
- **extract-on-scope-interest has no external prior art** I could find — it is novel to ugm
  (derived from D16's "extraction interests"). Its cost/recall behavior is unvalidated; it should
  be prototyped and measured, not assumed.

**Not investigated (out of scope here):** the gate *classifier* design itself (salience model,
section-level vs doc-level, features) — that is the sibling half of O3.

---

## 4. Recommendation for ugm

**Adopt deferred extraction as a per-document state machine in the Postgres spine, with the defer
boundary drawn between E1 and E2, never before E1.** Concretely:

1. **Defer boundary = E1→E2 edge (D12).** Run E0+E1 *fully* on every document (store, markdown,
   PageIndex, chunk, context-prefix, embed → P1). The gate verdict gates only the *E2 enqueue*.
   This keeps deferred docs retrievable (closing the lazy-trigger bootstrap hole) and keeps the
   per-doc chain intact — defer is a recorded terminal state of E1, not a bypass of the chain.

2. **The defer decision is durable, versioned Postgres state (D1/D7/D12).** Add
   `document_extraction_state(document_id, state, gate_verdict, defer_reason,
   gate_model_version, gate_prompt_version, processing_version, deferred_at, …)`. This makes the
   defer decision (a) **rebuildable-safe** — a P-plane rebuild over Postgres reproduces exactly
   "the corpus as extracted so far," and a PITR restore restores the exact outstanding-work set;
   (b) **replayable** — a better gate re-classifies deferred docs as a version-filtered batch job
   (same machinery as embedding migration and resolution re-decisions, registry §4); (c)
   **auditable** — "why isn't this doc in the graph?" is one row. The defer verdict is a
   *verdict-over-evidence* in the same epistemics as claims (D2) and resolution (registry §4):
   append-only, re-adjudicable, never silently mutated.

3. **The work queue is a projection of that state, not an independent store (D7 + outbox).** Hold
   the backlog as `state ∈ {deferred, backfill_queued}` rows; drain with
   `SELECT … FOR UPDATE SKIP LOCKED ORDER BY priority DESC, deferred_at ASC`
   ([PG queue pattern](https://www.dbpro.app/blog/postgresql-skip-locked)). Enqueue Cloud Tasks
   (D12) **atomically with** the state flip via the transactional-outbox discipline
   ([DBOS outbox](https://docs.dbos.dev/python/examples/outbox)) so the message and the truth never
   diverge. A lost queue is regenerated by SQL — "not-lost" reduces to D7. Backfill is idempotent
   on `content hash + processing version` (D12) and on `(source, assertion)` / `(s,p,o)` (D2),
   reinforced by exact-hash extraction caches lifted from HippoRAG/LightRAG (the one reusable
   primitive from the cloned repos).

4. **Four backfill triggers, in priority order (cheap-first, D4-flavored):**
   (i) **on-scope-interest** (D16 "extraction interests") — a K2 scope's declared entity/predicate
   interest sweeps deferred docs mentioning it; *highest leverage*, ties cost to demand, and is
   where ugm improves on LazyGraphRAG's query-random laziness;
   (ii) **on-first-retrieval** — a search hit on a deferred doc's E1 chunk enqueues its E2 (lazy
   materialization, but persisted to the ledger — the trade LazyGraphRAG does *not* make);
   (iii) **bounded steady-state drain** — guarantees "deferred ≠ never," giving extraction a
   freshness SLA analogous to D7's rebuild SLA;
   (iv) **gate-version re-classification** — promotes previously-deferred docs under a better gate.

5. **Recall safeguards (O3 risk, O6 hook):** always-full E1 (mitigation 1); conservative gate —
   tilt toward extract, because over-defer is a *silent* hole and under-defer is a *gradual* cost
   (same asymmetry as ER over/under-merge, `entity_registry.md` §1); **measure** the
   deferred-but-later-material rate as a first-class production metric in O6's eval loop (it is the
   only way to validate the gate threshold — explicitly an O6 dependency); optionally guard K3
   belief promotion against entities whose evidence is mostly still-deferred.

**One-line position:** *Deferral is safe and powerful for ugm precisely because ugm already has a
durable spine — make the defer decision a versioned Postgres verdict and the queue a projection of
it, defer the E2/E3 LLM cost (not E1), and back it with on-scope-interest + on-retrieval +
bounded-drain triggers so "deferred" is a scheduler, not a discard. This realizes O3's lazy-
processing lever without violating D7 (rebuildable) or D12 (per-doc chain) — and improves on
LazyGraphRAG by persisting what it extracts once, instead of re-paying every query.*

### Sources
- [LazyGraphRAG: Setting a new standard for quality and cost — Microsoft Research](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)
- [E²GraphRAG (arXiv 2505.24226) — notes LazyGraphRAG query-time latency](https://arxiv.org/pdf/2505.24226)
- [Towards Practical GraphRAG / deferred entity matching (arXiv 2507.03226)](https://arxiv.org/html/2507.03226v2)
- [microsoft/graphrag Discussion #2061 — LazyGraphRAG community implementation](https://github.com/microsoft/graphrag/discussions/2061)
- [Why Postgres is a Good Choice for Durable Workflow Execution — DBOS](https://www.dbos.dev/blog/why-postgres-durable-execution)
- [Transactional Outbox — DBOS Docs](https://docs.dbos.dev/python/examples/outbox)
- [PostgreSQL FOR UPDATE SKIP LOCKED job queue — DB Pro](https://www.dbpro.app/blog/postgresql-skip-locked)
- [FOR UPDATE SKIP LOCKED for queue workflows — Netdata](https://www.netdata.cloud/academy/update-skip-locked/)
- [Background Job & Queue Patterns 2026 — digitalapplied](https://www.digitalapplied.com/blog/background-job-queue-patterns-2026-engineering-reference)
- Repo archaeology (this analysis set): `value_gate_research/repo_findings/graphrag_lightrag_hipporag.md`, `mem0_cognee.md`; `registry_research/repo_findings/{cognee,graphiti,lightrag_graphrag}.md`
