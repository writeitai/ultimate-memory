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
| WP-7.1 | Backfill lanes + seeding + reprocessing orchestration (version bumps) | orchestration §3–4 | Phase 6 | lane machinery | steady-state unaffected during backfill test | planned |
| WP-7.2 | Reproducible scale battery: D23 partitions/indexes, hub entities/lineages, recount cost, and provider-neutral read/write batching | schema §12; D23; lifecycle §11.5; orchestration §5; retrieval §13.7 | WP-7.1 | fixed synthetic profiles + report | shapes and batching invariants recorded; timings remain measurements, not hosted SLAs | planned |
| WP-7.3 | Cost metering + configurable budget enforcement | orchestration §4; schema §2 `cost_ledger` | WP-7.1 | enforcement + admin inspection | explicit fixture ceiling parks and resumes an over-budget lane; attribution is visible | planned |
| WP-7.4 | Operational correctness surfaces + drills: typed telemetry, pipeline/DLQ inspection and replay, P2/P3 rebuild, currency-ledger audit | orchestration §6–7; D7, D60–D61 | WP-7.1 | telemetry/admin surfaces + deterministic drills | failures remain visible and drills pass without a dashboard or hosted control plane | planned |
| WP-7.5 | **Hard-delete end-to-end**: design first, then purge active P1/P2/P3/K surfaces and prevent restore resurrection through the portable purge record/adapter contract | new design (gate #24); lifecycle §8; k_layers §10; S55 | gate #24 | forget pipeline | **S55 CI gate ON and green** across library-controlled surfaces + restore canary | blocked(#24) |
| WP-7.6 | **Release engineering**: semver across PyPI + GHCR images + pinned compose; migrations-before-workers upgrade drill; quickstart cold-start release gate | packaging §1, §5–6; D62 | WP-7.1, rename/CLA gate | release pipeline | tagged release produces all artifacts; upgrade drill green; quickstart under target | blocked(rename-gate) |
| WP-7.7 | **Export/import round-trip**: `ugm export`/`import` (Postgres dump + buckets + K repo + deletion state; projections rebuild on import) | packaging §6; D7, D62 | WP-7.1, WP-7.5 | export/import CLI | round-trip drill → no forgotten-data resurrection + S-battery subset green | planned |
