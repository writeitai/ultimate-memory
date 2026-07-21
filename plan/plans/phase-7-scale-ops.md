# Phase 7 — Operational Correctness + Portability

> The filename is retained as a stable historical path; this title and D60 define the current
> scope. "Scale + Ops" is no longer the phase contract.

**Goal:** finish the mechanisms a complete single-deployment OSS library must own: resumable
backfill, reproducible scale checks, enforced configurable budgets, visible failures, portable
deletion, releases, and export/import.

**Scope boundary (D60):** this phase ships library behavior, adapter contracts, self-host
surfaces, and deterministic drills. It does **not** choose or operate a hosted corpus capacity,
monthly spend policy, Postgres HA topology, observability backend, backup schedule, fleet, or
vendor-specific network layout. Those are `ultimate-memory-cloud`/operator concerns. The
reference adapters remain supported without turning their production operations into OSS logic.

**Simplicity rule (`implementation_core_values.md` §3):** add no control plane, dashboard service,
HA manager, backup scheduler, or parallel source of operational truth. Extend the existing
Postgres state, narrow ports, typed settings, and CLI/admin surfaces along one shared path for
self-host and reference adapters.

**Entry gates:** none. Work-package-local gates remain explicit: #24 must be designed before
WP-7.5; rename/clearance + CLA gate WP-7.6 only.
**Exit criteria:** fixed synthetic scale profiles exercise the D23 shapes and portable batching;
a fixture budget parks and later resumes work without loss; telemetry/admin surfaces expose
pipeline and DLQ state; rebuild and forget drills pass; S55 is green across active serving stores
and a restore cannot resurrect a forgotten identity; release and export/import artifacts pass
their round trips.

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-7.1 | Backfill lanes + seeding + reprocessing orchestration (version bumps) | orchestration §3–4 | Phase 6 | lane machinery | steady-state unaffected during backfill test | done |
| WP-7.2 | Reproducible scale battery: D23 partitions/indexes, hub entities/lineages, recount cost, and provider-neutral read/write batching | schema §12; D23; lifecycle §11.5; orchestration §5; retrieval §13.7 | WP-7.1 | fixed synthetic profiles + report | shapes and batching invariants recorded; timings remain measurements, not hosted SLAs | done |
| WP-7.3 | Cost metering + configurable budget enforcement | orchestration §4; schema §2 `cost_ledger` | WP-7.1 | enforcement + admin inspection | explicit fixture ceiling parks and resumes an over-budget lane; attribution is visible | done |
| WP-7.4 | Operational correctness surfaces + drills: typed telemetry, pipeline/DLQ inspection and replay, P2/P3 rebuild, currency-ledger audit | orchestration §6–7; D7, D60–D61 | WP-7.1 | telemetry/admin surfaces + deterministic drills | failures remain visible and drills pass without a dashboard or hosted control plane | planned |
| WP-7.5 | **Hard-delete end-to-end**: design first, then purge active P1/P2/P3/K surfaces and prevent restore resurrection through the portable purge record/adapter contract | new design (gate #24); lifecycle §8; k_layers §10; S55 | gate #24 | forget pipeline | **S55 CI gate ON and green** across library-controlled surfaces + restore canary | blocked(#24) |
| WP-7.6 | **Release engineering**: semver across PyPI + GHCR images + pinned compose; migrations-before-workers upgrade drill; quickstart cold-start release gate | packaging §1, §5–6; D62 | WP-7.1, rename/CLA gate | release pipeline | tagged release produces all artifacts; upgrade drill green; quickstart under target | blocked(rename-gate) |
| WP-7.7 | **Export/import round-trip**: `ugm export`/`import` (Postgres dump + buckets + K repo + deletion state; projections rebuild on import) | packaging §6; D7, D62 | WP-7.1, WP-7.5 | export/import CLI | round-trip drill → no forgotten-data resurrection + S-battery subset green | planned |

## WP-7.1 implementation

`BackfillSeeder` enumerates the authoritative `processing_state` ledger for prior executions of
one plane-E stage that do not yet have the requested component version. Each configured-size
transaction copies the latest immutable target input into the existing D12 enqueue path on the
`backfill` lane. Re-running the same request is the cursor and recovery mechanism; no campaign
table, scheduler, or second pipeline exists.

Initial corpus loads use that same pipeline by selecting `backfill` at the upload boundary or via
the typed `UGM_SYNC_LANE` setting. Steady work keeps its distinct claim route and still promotes
a pending/failed duplicate under the D67 rule. After seeding has completed and all deployment
backfill rows are terminal, `BackfillFinalizer` invokes the portable P1 maintenance port; it
refuses the explicit Lance index build while any backfill row remains unresolved.

## WP-7.2 implementation

The `operational` eval suite records one complete four-part fixed-profile report in the existing
`eval_runs` history. Its capability-sized CI profile verifies the exact seven RANGE plus two
HASH-64 D23 parents, unpartitioned registry blocking targets and their GIN/Daitch-Mokotoff/btree
indexes (including measured index sizes), a 2,000-alias entity hub, and a lineage fanning out to
1,000 relations plus 1,000 observations. The same ungated shape scales through typed
`UGM_OPERATIONAL_SCALE_*` settings; no corpus forecast or hosted target is embedded in the
library.

Lifecycle currency application and relation/observation recount are set-based: each remains one
transaction and a constant two SQL statements independent of batch size, while preserving retry
idempotency, last-transition cache semantics, distinct-current-lineage counts, and caller input
order. E3 front-loads normalized-claim replay markers and groups proposed observations by the
resolved `(document, entity)` batch. The adjudicator takes one entity lock, one claim-timestamp
read, and one exhaustive block read, then applies assertions in order against an in-memory block
that tracks new rows, caps, and contradiction groups before committing once.

The provider-neutral measurement uses the real SQLAlchemy engine with explicit injected latency:
513 interactive claim ids cross the binding 256-id boundary in exactly three confirmation
statements, while currency writes and hub recount retain their constant statement counts. Only
shape, correctness, query-count, and transaction-count invariants gate acceptance; every elapsed
time is recorded as a machine-specific measurement, never an OSS SLA or topology commitment.

## WP-7.3 implementation

Operators declare no implicit monetary policy. An optional typed `UGM_WORK_BUDGETS` list supplies
explicit ceilings keyed by deployment, stage, lane, and aligned fixed window; an omitted route is
unlimited. After locking one due row, the existing claim transaction sums the deduplicated
`cost_ledger` range for that route. Exhaustion moves the row to durable `pending` / `budget` state
until the window boundary without starting a handler, consuming an attempt, changing the last
error, or creating a second scheduling ledger. The worker re-announces that existing row through
the delivery port with the stored resume time.

`WorkLedger.budget_status` and `ugm budget inspect` read the same two authoritative Postgres
tables. They expose configured ceiling, current-window spend, remaining amount, tier attribution,
aligned bounds, and parked-work count; they do not add a dashboard, hosted billing policy, cache,
or control plane. The PostgreSQL acceptance fixture records two attributed calls, proves an
over-budget handler never starts, then crosses the fixture window and proves the exact row resumes
and completes normally.

Successful generation and embedding responses carry mandatory provider-reported usage through the
existing model port. The worker binds that usage to its running processing row, and every
model-using stage records a deterministic logical call key and cascade tier before consuming the
response. OpenRouter responses without cost/token accounting fail visibly instead of degrading to
zero spend; the deterministic test provider emits zero-cost usage so end-to-end worker tests prove
the same production attribution path without network calls.
