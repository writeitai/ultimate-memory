# Phase 0 — Foundations + Harness

**Goal:** everything later phases stand on: a migratable spine, the pipeline substrate, and —
before anything tunable exists — the evaluation harness. Nothing user-visible ships here.

**Entry gate (closed 2026-07-17):** stack conventions. The choices and exact repository
evidence are recorded in [roadmap §3](roadmap.md#3-technology-stack-binding-for-all-phases):
[PR #39](https://github.com/writeitai/ultimate-memory/pull/39) merged the package scaffold,
tooling, layout/naming, and GitHub Actions CI; [PR #41](https://github.com/writeitai/ultimate-memory/pull/41)
merged the typed configuration/secrets convention and direct-environment-access lint guard.
This closes only the entry gate and WP-0.1; Phase 0 remains incomplete until every exit
criterion below is evidenced.
**Exit criteria:** migrations apply/rollback cleanly on a fresh Postgres; a no-op worker runs
end-to-end through Cloud Tasks with `processing_state` + `cost_ledger` rows; the eval harness
runs an empty suite in CI; the blockizer golden corpus scaffold exists with ≥1 seeded doc.

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-0.1 | Repo scaffolding per stack conventions (typing, lint, CI, layout) | roadmap §3; requirements §Code | gate: stack conventions | the repository skeleton | pyright + pytest green in CI | done |
| WP-0.2 | Alembic migrations for the full schema | postgres_schema_design (all §; §0 conventions) | WP-0.1 | migration chain | fresh-DB apply + downgrade; §16 decision→table map spot-check | planned |
| WP-0.3 | Tenancy + pipeline substrate: `deployments`, `pipeline_component_versions`, `processing_state`, `cost_ledger`, DLQ semantics; the **handler registration model** (stage handlers, chain rule) | schema §2; orchestration §1–2; D12, D52; packaging §3 | WP-0.2 | worker base library (idempotency, retries, versions, cost metering) | a demo no-op worker: enqueue → run → state row → retry → dead-letter | planned |
| WP-0.4 | **The D61 port interfaces** (`ports/` Protocols: object store, task queue, mounts, git remote, model provider, telemetry, auth) + import-linter contracts in CI | packaging §3–4; D61, D62 | WP-0.1 | `ports/` + CI architecture checks | illegal import fails CI (proven by a deliberate violation) | planned |
| WP-0.4a | **Self-host adapters**: pg-queue delivery shell (`LISTEN/NOTIFY` + `SKIP LOCKED`, transactional enqueue, token-bucket rate limits), MinIO/local-FS object store, local mount publisher, `adapters/testing` tier | packaging §3, §5; D62 | WP-0.4, WP-0.3 | `adapters/selfhost` + `adapters/testing` | demo chain runs on compose with zero GCP deps; transactional-enqueue crash test | planned |
| WP-0.4b | **Reference adapters**: Cloud Tasks push shell + dispatch server, GCS store, gcsfuse publisher; **the janitor sweep** (shared, port-agnostic) | packaging §3; orchestration §2–3; D61 | WP-0.4 | `adapters/gcp` + janitor job | same demo chain on the GCP profile; janitor re-announces a killed delivery on BOTH profiles | planned |
| WP-0.4c | **Compose self-host profile** (postgres + minio + api + worker; `profiles/selfhost`) — the quickstart skeleton | packaging §5 | WP-0.4a | docker-compose + profile module | `docker compose up` → demo ingest → state rows; CI-run | planned |
| WP-0.5 | **Eval harness skeleton** (questions #14 — this WP owns it): golden-set storage (`golden_pairs`, `golden_claim_labels`, `canary_cases`, `eval_runs`), suite runner, CI wiring | schema §5; D22; registries §10 | WP-0.2 | harness package + `eval` CI job | empty suites run; a seeded canary fails deliberately and blocks CI | planned |
| WP-0.6 | Golden-set labeling tooling (LLM-propose / human-adjudicate loop, circularity guard) | D22; registries §11.1 | WP-0.5 | labeling CLI | 20 seed pairs labeled end-to-end | planned |
| WP-0.7 | Blockizer golden corpus scaffold (expected block-hash regression per `blockizer_version`) | e1 §2 (D57) | WP-0.5 | corpus + CI check | seeded doc's hashes locked; a deliberate parser change trips CI | planned |
