# Phase 0 — Foundations + Harness

**Goal:** everything later phases stand on: a migratable spine, the pipeline substrate, and —
before anything tunable exists — the evaluation harness. Nothing user-visible ships here.

**Entry gates:** stack conventions (roadmap §3 slots — owner-provided).
**Exit criteria:** migrations apply/rollback cleanly on a fresh Postgres; a no-op worker runs
end-to-end through Cloud Tasks with `processing_state` + `cost_ledger` rows; the eval harness
runs an empty suite in CI; the blockizer golden corpus scaffold exists with ≥1 seeded doc.

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-0.1 | Repo scaffolding per stack conventions (typing, lint, CI, layout) | roadmap §3; requirements §Code | gate: stack conventions | the repository skeleton | pyright + pytest green in CI | blocked(stack-conventions) |
| WP-0.2 | Alembic migrations for the full schema | postgres_schema_design (all §; §0 conventions) | WP-0.1 | migration chain | fresh-DB apply + downgrade; §16 decision→table map spot-check | planned |
| WP-0.3 | Tenancy + pipeline substrate: `deployments`, `pipeline_component_versions`, `processing_state`, `cost_ledger`, DLQ semantics | schema §2; orchestration §1–2; D12, D52 | WP-0.2 | worker base library (idempotency, retries, versions, cost metering) | a demo no-op worker: enqueue → run → state row → retry → dead-letter | planned |
| WP-0.4 | Queue topology bootstrap (per deployment/stage/lane) | orchestration §2–3 | WP-0.3 | queue provisioning config | queues created; rate limits configurable | planned |
| WP-0.5 | **Eval harness skeleton** (questions #14 — this WP owns it): golden-set storage (`golden_pairs`, `golden_claim_labels`, `canary_cases`, `eval_runs`), suite runner, CI wiring | schema §5; D22; registries §10 | WP-0.2 | harness package + `eval` CI job | empty suites run; a seeded canary fails deliberately and blocks CI | planned |
| WP-0.6 | Golden-set labeling tooling (LLM-propose / human-adjudicate loop, circularity guard) | D22; registries §11.1 | WP-0.5 | labeling CLI | 20 seed pairs labeled end-to-end | planned |
| WP-0.7 | Blockizer golden corpus scaffold (expected block-hash regression per `blockizer_version`) | e1 §2 (D57) | WP-0.5 | corpus + CI check | seeded doc's hashes locked; a deliberate parser change trips CI | planned |
