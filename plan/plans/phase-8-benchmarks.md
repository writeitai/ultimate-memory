# Phase 8 — Competitive Benchmarks

**Goal:** demonstrate the system against the field — external, comparative, reproducible.
Distinct from the internal D22 harness: that answers "are we correct against our own golden
set"; this answers "are we better than the alternatives on shared ground", plus "what can we
do that they cannot".

**Entry gates:** Phases 1–3 + 5 done (ingestion, lifecycle, full retrieval); Phase 6 optional
per benchmark (K helps orientation-style tasks). Each run records its actual cost and explicit
run cap; no deployment-owner budget is an OSS benchmark gate (D60).
**Exit criteria:** a published methodology + results document (reproducible runs, pinned
versions, honest losses included); the capability benchmark demonstrates the differentiators
end to end.

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-8.1 | **Benchmark landscape survey** — the field moves; select at execution time. Candidates to evaluate (verify currency then): LoCoMo, LongMemEval, DMR-class conversational-memory suites; multi-hop QA (HotpotQA/MultiHop-RAG-class) for graph strengths; latency/cost protocols the competitors publish | — (web survey; D22 for fit) | phase gates | selection memo (analysis/) | chosen suites + rationale + baseline list | planned |
| WP-8.2 | Adapter layer: the system as a memory backend behind each benchmark's protocol (ingest/query interfaces, session semantics) | retrieval §3–7; benchmark specs | WP-8.1 | adapters | benchmark harness runs end-to-end on a sample | planned |
| WP-8.3 | Baselines: competitor systems (Mem0/Zep-class per survey) + a naive-RAG floor, same corpora, same models where fair | WP-8.1 memo | WP-8.2 | baseline runs | reproducible baseline numbers | planned |
| WP-8.4 | Metrics + instrumentation: accuracy per suite, latency (P50/P95), token + $ cost per op (cost_ledger), ingestion throughput | schema §2; retrieval §10 | WP-8.2 | metrics pipeline | one dashboard per run | planned |
| WP-8.5 | **Capability benchmark** (ours, from the S-battery): the differentiators competitors lack — bi-temporal as-of (S9/S10/S15), contradiction surfacing (S23), provenance hydration (S5), watched-source lifecycle (edit/retract/delete), forget (S55) | retrieval_scenarios.md | WP-8.2 | capability suite + narrative doc | each capability demonstrated + scripted | planned |
| WP-8.6 | Methodology + results publication (honest: include losses; pin versions; publish configs) | all above | WP-8.3–8.5 | report | reviewed; reproducible by a third party | planned |
