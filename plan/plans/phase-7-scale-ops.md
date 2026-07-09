# Phase 7 — Scale + Ops

**Goal:** the system at its stated scale (millions of documents), operable: backfill, load,
budgets, failure drills, end-to-end forget.

**Entry gates:** #1 corpus mix + #2 budget ceiling (owner inputs); **#24 hard-delete design**
(must be designed before its WP); #9/#10 ops choices.
**Exit criteria:** a representative corpus-slice backfill completes within the modeled cost
envelope; D23 load tests recorded; budget enforcement demonstrably halts an over-budget lane;
DLQ + rebuild drills pass; S55 CI gate activates (forget verified end to end).

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-7.1 | Backfill lanes + seeding + reprocessing orchestration (version bumps) | orchestration §3–4 | Phase 6 | lane machinery | steady-state unaffected during backfill test | planned |
| WP-7.2 | D23 load tests at ungated volume: partitions, GIN sizes, hub entities/lineages, recount cost | schema §12; D23; lifecycle §11.5 | WP-7.1 | load report | numbers recorded; index choices locked | planned |
| WP-7.3 | Cross-cloud write-path measurement + batching (F9) and hydration batching under load | orchestration §5; retrieval §13.7 | WP-7.1 | batching config | backfill throughput target met | planned |
| WP-7.4 | Budget enforcement + spend dashboards (per layer/deployment) | orchestration (budgets); schema §2 cost_ledger | WP-7.1, gate #2 | enforcement | over-budget lane halts, alerts | planned |
| WP-7.5 | Observability + drills: tracing, DLQ inspection/replay, P2/P3 rebuild drills, currency-ledger audit | orchestration (DLQ); D7 | WP-7.1, gate #10 | runbooks + drills in CI-cron | drills pass unattended | planned |
| WP-7.6 | **Hard-delete end-to-end** (design first — closes #24; then implement across P1/P2/P3/backups/K history) | new design (gate #24); lifecycle §8; k_layers §10; S55 | gate #24 | forget pipeline | **S55 CI gate ON and green** | blocked(#24) |
| WP-7.7 | **Release engineering**: semver across PyPI + GHCR images + pinned compose; migrations-before-workers upgrade drill; quickstart cold-start time as a release gate | packaging §1, §5–6; D62 | WP-7.1 | release pipeline | tagged release produces all artifacts; upgrade drill green; quickstart under target | blocked(rename-gate) |
| WP-7.8 | **Export/import round-trip**: `ugm export`/`import` (Postgres dump + buckets + K repo + manifest; projections rebuild on import) | packaging §6; D7, D62 | WP-7.1 | export/import CLI | round-trip drill → S-battery subset green (packaging spike 4) | planned |
