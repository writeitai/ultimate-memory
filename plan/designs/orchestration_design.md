# Orchestration — Workers, Queues, Lanes, Budgets, DLQ (Design)

How the workers *run*: the operational plane that connects the per-worker designs. The worker
**inventory** — every worker, its behavior contract, its execution class — is
`../analysis/workers.md`; per-worker *semantics* live in the layer designs. This document binds
what none of them owns: queue topology, the steady-state/backfill lane split, budget-enforcement
semantics, dead-letter operations, and the cross-cloud write discipline. Decisions: **D52–D53**
(execution-class and model-family invariants), building on D12 (idempotent workers, retries,
DLQ), D7 (replay-not-recall), D16 (deployment isolation), D23 (scale), D25 (ungated volume).
Numbers here are starting points to measure, not committed constants (CLAUDE.md).

> **Reading this cold.** Plane E is a per-document chain of workers (E0
> ingest→convert→structure→crossref; E1 chunk/prefix/embed; E2 extract/ground; E3
> resolve/normalize/adjudicate/label), each a Cloud Run job fired by a Cloud Tasks queue when
> the previous stage completes; planes K and P are debounced/scheduled aggregate workers.
> `processing_state` in Postgres is the idempotency + status + dead-letter ledger (one row per
> target/stage/version — schema §2); `cost_ledger` meters every model call. A **lane** is a
> parallel queue set for the same stages with its own rate limits and budgets.

## 1. No workflow engine — the chain is the orchestrator (scope boundary)

There is deliberately **no Airflow / Temporal / Step Functions layer**. The orchestrator is the
composition of three things that already exist:

1. **Cloud Tasks queues** — delivery, retry, rate limiting (imposed constraint);
2. **`processing_state`** — state, idempotency, dead letters (D12);
3. **the chain rule** — a completing worker enqueues the next stage for its target.

A workflow engine would duplicate all three, add a second stateful system to operate, and put
pipeline state somewhere other than the spine — against the grain of "state has one home"
(D6). Cross-stage coordination needs nothing more because stages are **independent idempotent
steps**: there is no distributed transaction to manage, only the next enqueue. This is a scope
boundary, not a deferral: a future need (e.g. deadline-bound human-in-the-loop steps spanning
stages) must be argued against this section, not assumed.

## 2. Queue topology

- **One queue per (deployment, stage, lane).** Per-deployment isolation is a hard rule (D16 —
  separate instances never share infrastructure paths). Per-*stage* queues exist so backlogs
  do not couple: a slow OCR batch (convert) must not starve extraction; E3's Postgres-heavy
  adjudication is rate-limited independently of E2's LLM-throughput limits. Queue count is
  configuration, not architecture — stages × lanes × deployments is tens of queues, well
  inside platform limits.
- **Enqueue granularity mirrors `processing_state` targets**: document-grain through E0;
  chunk-grain from E1 fan-out (chunking is the fan-out point); E3 adjudication consumes
  **batches per (document, entity)** — the observation-design batching rule (one block fetch,
  batched adjudication) applied as the enqueue unit, which also concentrates cross-cloud
  round-trips (§5).
- **Rate limits and concurrency are per-queue config**, sized against the two shared
  bottlenecks: Postgres write capacity through pgBouncer (the cross-cloud spine) and
  per-provider LLM rate limits. Queues meter *volume*; the cascades already meter *ambiguity*
  (D4) — the two knobs are deliberately different mechanisms.
- **K and P workers keep their own trigger models** (debounce window; schedule — D12) and do
  not use lanes; lanes are a plane-E concept. Their jobs still record `processing_state` rows
  (`build_snapshot`, `compile_knowledge`, …) like everything else.

## 3. Two lanes: steady-state and backfill

Backfill (initial corpus load; version-bump reprocessing) and live ingestion run the **same
pipeline, same workers, same idempotency keys** — but **separate lanes**, so a million-document
backfill can never starve a fresh document's freshness SLA ("plane E processes promptly per
document" — requirements). Rules:

- **A backfill is defined by a version filter, nothing else** (D12): "all documents where
  `converter_version < X`", "all chunks where `extractor_version < Y`". A deterministic
  **backfill seeder** job — the one worker this document adds to the inventory — enumerates
  the filter into the backfill lane in bounded batches. Resumability is free: re-seeding is a
  no-op for every already-succeeded `(target, stage, version)` row, so a crashed or paused
  backfill continues by re-running the seeder.
- **Lane budgets are separate** (§4): backfill spend is a knob turned deliberately, never a
  surprise on the steady-state budget. The two dominant backfill costs are metered per lane
  and known in advance: extraction-side LLM calls (volume-proportional — design-review F8) and
  cross-cloud write round-trips (§5).
- **Priority is structural, not scheduled**: the steady lane's rate limits are never reduced
  for a backfill; a backfill gets whatever headroom the shared bottlenecks have left. No
  priority scheduler exists or is needed.

## 4. Budget enforcement — park, never drop

"Budgets enforced, not advisory" (overall §8) gets concrete semantics here:

- **Declaration**: budgets are per `(deployment, stage, lane, window)` — e.g. "extract_claims
  / steady / $N per day" — in deployment config.
- **Enforcement is a deterministic pre-flight check in the worker**: read the deduplicated
  `cost_ledger` window total (cached, refreshed on the order of minutes — enforcement is a
  dam, not a scalpel; minutes of lag are priced in). If the budget is exhausted, the worker
  **parks**: re-enqueue its own task with a `not_before` past the window roll and exit
  *without* consuming a retry (`processing_state.attempts` untouched, status stays
  `pending`).
- **Parking is not failure.** Nothing dead-letters because of budget; no work is lost or
  skipped; the chain resumes exactly where it stopped when the window rolls or the budget is
  raised. Parking between stages is safe **by construction** — stages are independent
  idempotent steps, so there is no half-open cross-stage state to corrupt.
- **Exhaustion alerts carry the tier breakdown** (`cost_ledger.tier` — which cascade rung
  spent the money): the operator must be able to tell "the corpus got bigger" from "a prompt
  regression made the frontier rung fire 10× more often" in the alert itself, not by
  archaeology.

## 5. The cross-cloud write path (design-review F9, made binding)

Postgres lives on Hetzner; workers on GCP — every spine round-trip pays cross-cloud latency,
multiplied by millions of documents during backfill. Rules:

- **Batch writes per worker invocation.** A worker commits its target's rows in as few
  transactions as its semantics allow — never row-at-a-time chatter. The E3
  per-(document, entity) batching exists for adjudication correctness and pays again here.
- **Front-load reads.** A worker fetches its inputs (context bundle, blocking candidates) in a
  bounded number of round-trips at start — never incrementally inside a loop.
- **pgBouncer is in the loop for every load test**: the D23 partition/index test and the F9
  write-path test run at backfill concurrency before any backfill sizing is trusted.
- **Colocation contingency — an ops item, documented here, not an architecture change**: if
  measured backfill duration or egress cost is unacceptable, the latency-sensitive workers
  (E3's chatty adjudication) move adjacent to the spine. Store roles (D1/D6) are untouched
  either way.

## 6. Dead-letter operations

The DLQ **is** `processing_state` rows with `status='dead_letter'` (D12 — no separate
infrastructure). The operational surface over it is thin and deterministic:

- **Inspect** — SQL views by (stage, error class, component version, age); the preserved
  enqueue `payload` makes every dead letter self-describing and manually replayable.
- **Replay** — reset the row to `pending`, re-enqueue its payload. Unconditionally safe: the
  idempotency key is unchanged, so a partially-succeeded earlier attempt no-ops. Bulk replay
  is the same operation scoped by version or error class, routed through the backfill lane
  when large.
- **Poison detection** — the same target dead-lettering across ≥2 component versions is
  flagged for a human: that is a content pathology (a document that breaks the converter), not
  a transient, and no amount of retrying fixes it.
- **DLQ depth per stage is a first-class alert metric.** "Failures never disappear"
  (requirements) is only true if something is watching the place they go.

## 7. Observability — queries over existing state, not new state

Everything below derives from tables that already exist (`processing_state`, `cost_ledger`,
`projection_snapshots`, `knowledge_compilations`); observability adds dashboards, never a
second bookkeeping system:

- per-stage throughput / latency / error rate / DLQ depth (`processing_state`);
- spend by stage × cascade tier × lane against budget (`cost_ledger`);
- the end-to-end trace of one document — its `processing_state` rows, ordered, *are* the
  trace;
- freshness SLAs: plane E p95 ingest→relations latency; plane P `built_from_watermark` lag vs
  cadence; plane K evidence-change→recompile lag vs the configured window (the k_layers eval
  metric).

## 8. Invariants (D52, D53)

- **Execution classes are bound** (D52): every worker is deterministic, programmatic-LLM, or
  agent-harness per the inventory's rule; **no harness on a per-document, per-claim, or query
  path** — harness seats live only on plane K and the review/audit surfaces.
- **Every LLM-calling worker carries an append-only transcript** (D52 — the D33 ledger
  discipline as a standing rule for new workers).
- **Checker seats run on a different model family than their producers** (D53): judges,
  reviewer agents, and the K reflection pass never share a family with what they check.

## References

Inventory: `../analysis/workers.md`. Decisions: D4, D6, D7, D12, D16, D23, D25, **D52–D53**
(`decisions.md`). Review findings: `../analysis/design_review_2026_07.md` (F8, F9).
Requirements: operational properties + imposed constraints (`../requirements/requirements_v3.md`).
Worker semantics live in their layer designs: `e0_files_design.md`,
`e2_e3_claims_relations_design.md`, `observations_design.md`, `registries_design.md`,
`k_layers_design.md`, `p2_graph_design.md`; infra tables: `postgres_schema_design.md` §2.
