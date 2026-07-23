# Phase 0 — Foundations + Harness

**Goal:** everything later phases stand on: a migratable spine, the pipeline substrate, and —
before anything tunable exists — the evaluation harness. Nothing user-visible ships here.

**Entry gate (closed 2026-07-17):** stack conventions. The choices and exact repository
evidence are recorded in [roadmap §3](roadmap.md#3-technology-stack-binding-for-all-phases):
[PR #39](https://github.com/writeitai/rememberstack/pull/39) merged the package scaffold,
tooling, layout/naming, and GitHub Actions CI; [PR #41](https://github.com/writeitai/rememberstack/pull/41)
merged the typed configuration/secrets convention and direct-environment-access lint guard.
This closes only the entry gate and WP-0.1; Phase 0 remains incomplete until every exit
criterion below is evidenced.
**Exit criteria (amended 2026-07-18):** migrations apply/rollback cleanly on a fresh Postgres;
a no-op worker runs end-to-end through the **task-queue delivery port** with
`processing_state` + `cost_ledger` rows — the self-host shell (WP-0.4a) is the Phase-0 proof;
GCP parity is WP-0.4b; the eval harness runs an empty suite in CI; the blockizer golden corpus
scaffold exists with ≥1 seeded doc.

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-0.1 | Repo scaffolding per stack conventions (typing, lint, CI, layout) | roadmap §3; requirements §Code | gate: stack conventions | the repository skeleton | pyright + pytest green in CI | done |
| WP-0.2 | Alembic migrations for the full structural schema (schema shape only; no deployment/core data) | postgres_schema_design (all §; §0 conventions and §2 post-head boundary) | WP-0.1 | structural migration chain | fresh-DB apply + downgrade; §16 decision→table map spot-check; head contains no deployment/core rows | done |
| WP-0.3 | Tenancy + pipeline substrate: typed transactional `bootstrap_deployment(DeploymentBootstrapInput) -> DeploymentBootstrapResult`, `pipeline_component_versions`, `processing_state`, `cost_ledger`, DLQ semantics; the **handler registration model** (stage handlers, chain rule) | schema §§2–3; registries §4 exact core manifest; orchestration §1–2; D12, D52, D69; packaging §§3–5 | WP-0.2 | library-owned deployment bootstrap + worker base library (idempotency, retries, versions, cost metering) | after schema head, bootstrap maps typed profile inputs to one deployment + exactly 8 roots/16 predicates/116 signatures in one transaction; identical retry is a verified no-op; conflicting retry rolls back with a typed conflict; demo no-op worker: enqueue → run → state row → retry → dead-letter | done |
| WP-0.4 | **The D61 port interfaces** (`ports/` Protocols: object store, task queue, mounts, git remote, model provider, telemetry, auth) + import-linter contracts in CI | packaging §3–4; D61, D62 | WP-0.1 | `ports/` + CI architecture checks | illegal import fails CI (proven by a deliberate violation) | done |
| WP-0.4a | **Self-host adapters**: pg-queue delivery shell (`LISTEN/NOTIFY` + `SKIP LOCKED`, transactional enqueue, token-bucket rate limits), local-FS object store, local mount publisher, `adapters/testing` tier (MinIO wiring lands with WP-0.4c) | packaging §3, §5; D62 | WP-0.4, WP-0.3 | `adapters/selfhost` + `adapters/testing` | demo chain runs against real Postgres with zero GCP deps; transactional-enqueue crash test | done |
| WP-0.4b | **Reference adapters**: Cloud Tasks push shell + dispatch server, GCS store, gcsfuse publisher; **the janitor sweep** (shared, port-agnostic) | packaging §3; orchestration §2–3; D61 | WP-0.4 | `adapters/gcp` + janitor job | same demo chain on the GCP profile; janitor re-announces a killed delivery on BOTH profiles | planned |
| WP-0.4c | **Compose self-host profile** (postgres + minio + api + worker; `profiles/selfhost`) — the quickstart skeleton | packaging §5 | WP-0.4a | docker-compose + profile module | `docker compose up` → demo ingest → state rows; CI-run | done |
| WP-0.5 | **Eval harness skeleton** (questions #14 — this WP owns it): golden-set storage (`golden_pairs`, `golden_claim_labels`, `canary_cases`, `eval_runs`), suite runner, CI wiring | schema §5; D22; registries §10 | WP-0.2 | harness package + `eval` CI job | empty suites run; a seeded canary fails deliberately and blocks CI | done |
| WP-0.6 | Golden-set labeling tooling (LLM-propose / human-adjudicate loop, circularity guard) | D22; registries §11.1 | WP-0.5 | labeling CLI | 20 seed pairs labeled end-to-end | planned |
| WP-0.7 | Blockizer golden corpus scaffold (expected block-hash regression per `blockizer_version`) | e1 §2 (D57) | WP-0.5 | corpus + CI check | seeded doc's hashes locked; a deliberate parser change trips CI | done |


**Sequencing amendment (2026-07-18):** WP-0.4b and WP-0.4c are not Phase-0 exit-blocking. The
exit's no-op worker proof runs on the self-host delivery shell (WP-0.4a); GCP parity + the
janitor (WP-0.4b) and the compose quickstart (WP-0.4c) land as early Phase-1-parallel work.
The original "through Cloud Tasks" exit wording is amended above accordingly.

**WP-0.2 complete (2026-07-18; `P0-L05-WP02-ALEMBIC-FULL-SCHEMA` revision 2):**
[PR #71](https://github.com/writeitai/rememberstack/pull/71) implementation head
[`ec5cb279944d`](https://github.com/writeitai/rememberstack/commit/ec5cb279944db138e093439136bc3237bfd545fd)
adds the six-revision structural-only Alembic chain, the executable catalog contract, and the
pinned PostgreSQL/pg_partman CI service. On PostgreSQL 16.14 with pg_partman 5.2.4, the focused
lifecycle proved clean base → fresh head, exact catalog shape (six extensions, 54 enums, 57 UGM
tables, 83 explicit indexes, seven monthly RANGE parents, two HASH parents with 64 children each,
seven final views, 57 table comments, 438 parent-column comments, and constraint totals
`c=26/f=106/p=57/u=28/x=1`), zero deployment/core registry rows, downgrade cleanup, clean
re-upgrade, and a no-op at head. Its meaningful negative proof removed
`relation_evidence_p63`, observed the contract failure, and restored the final green catalog.
[CI run 29629128266](https://github.com/writeitai/rememberstack/actions/runs/29629128266)
kept the required Python 3.12, Python 3.13, and coverage jobs green. Per D66, this internal
schema-shape leaf has no usable public workflow or user-visible behavior, so no public
documentation surface is changed; public documentation remains deferred to the first usable
slice. Phase 0 remains incomplete and no WP-0.3+ bootstrap/runtime behavior is included.

**WP-0.3 deployment-bootstrap slice in progress (2026-07-18; `P0-L07-WP03-DEPLOYMENT-BOOTSTRAP`):**
[PR #72](https://github.com/writeitai/rememberstack/pull/72) implementation commit
[`4e67a17`](https://github.com/writeitai/rememberstack/commit/4e67a17f6cf2376bf1bbe84249153c66f40e010d)
adds the explicit-Engine, one-transaction D69 library bootstrap, exact immutable `core-v1`
8/16/116 manifest, typed deployment/core conflicts, and PostgreSQL retry/no-mutation/rollback
proofs. Python 3.12, Python 3.13, and coverage were green on implementation-head
[CI run 29631003226](https://github.com/writeitai/rememberstack/actions/runs/29631003226).
This bounded slice exposes no CLI, profile, configuration, deployment workflow, or other public
surface, so D66 requires no website edit. Worker-state/handler behavior remains unimplemented;
WP-0.3 therefore stays `in-progress` and Phase 0 remains incomplete.

**WP-0.3 component-version registry slice in progress (2026-07-18; `P0-L08-WP03-COMPONENT-VERSION-REGISTRY`):**
[PR #73](https://github.com/writeitai/rememberstack/pull/73) implementation commit
[`5b9e168`](https://github.com/writeitai/rememberstack/commit/5b9e168121873200347d707a5e020c099c6f014a)
adds the exact typed 22-component catalog boundary and explicit-Engine transactional
register/resolve operation, with real-PostgreSQL no-op, conflict, key-independence, FK, and rollback
proofs. Python 3.12, Python 3.13, and coverage passed in
[CI run 29635472800](https://github.com/writeitai/rememberstack/actions/runs/29635472800).
This library-only slice exposes no CLI/API/MCP/configuration/mount/connector/deployment surface,
so D66 requires no website edit. Processing-state, cost, handler, and worker behavior remains
unimplemented; WP-0.3 stays `in-progress` and Phase 0 remains incomplete.


**WP-0.3 complete (2026-07-18):** [PR #76](https://github.com/writeitai/rememberstack/pull/76)
adds the work ledger (`spine/work_ledger.py`), the handler-registration model + worker runner
(`workers/base.py`), and typed processing records. Real-PostgreSQL proofs cover the full
acceptance: idempotent enqueue with the D67 steady-promotes-backfill rule, lane pairing enforced
at enqueue and claim, SKIP LOCKED claiming that increments attempts exactly once at handler
start, chain follow-ups committed atomically with success, retryable failure → backoff and
attempt-limit / non-retryable → dead letter with the full traceback in `last_error`
(attempts = 3 = D12's initial + two retries), pending-only budget parking (a running attempt is
never parked), and idempotent cost attribution copied from the locked running row. Earlier
slices: bootstrap (PR #72), component versions (PR #73). Delivery shells, rate limits, and the
janitor remain WP-0.4a/0.4b scope.


**WP-0.4a complete (2026-07-18):** the self-host adapters land in `adapters/selfhost` —
`SelfHostTaskQueue` (announce-only, via the spine's `wake` notification primitive; SQL stays in
spine), `SelfHostWorkerLoop` (LISTEN on `queue_wake`, drain via SKIP LOCKED claims, slow
fallback poll, token-bucket rate limit around the claim), `LocalFSObjectStore` (immutable
write-once keys, traversal-proof), `LocalMountPublisher` (the four D51 views as local
directories), and the `adapters/testing` tier (`RecordingTaskQueue`). Real-PostgreSQL proofs:
the **transactional-enqueue crash test** (a rolled-back insert delivers no wake; a committed
enqueue delivers exactly its row's wake — the schema trigger's by-construction guarantee),
announce re-delivery, and the demo chain draining through the loop with zero GCP dependencies.
MinIO wiring lands with WP-0.4c per the sequencing amendment.

**WP-0.4c complete (2026-07-22):** the fresh-deployment Compose skeleton wires the
real `profiles/selfhost` composition to pinned PostgreSQL 16 + pg_partman and MinIO images,
one migration/bootstrap service, the HTTP API, and separate `convert`/`structure` workers.
The MinIO adapter preserves write-once object semantics, path boundaries, routing metadata,
and hard-forget purge verification. A real Compose acceptance started from empty named volumes,
served health + recipes, ingested Markdown through MinIO, and observed `convert=succeeded`,
`structure=succeeded`, and `chunk=pending` in the authoritative work ledger with zero cost rows
(no provider call). CI repeats that proof in a job parallel to the Python matrix. This remains a
fresh, pre-release infrastructure skeleton: later-stage workers, authentication, restore
recovery, published GHCR images, and the public rename stay in their owning release work.


**WP-0.5 + WP-0.7 complete (2026-07-18):** the eval-harness skeleton lands in `eval/harness.py`
(suites over `canary_cases`, runs recorded in `eval_runs`, per-suite evaluator registration;
a suite with cases but no evaluator **fails** them — absence of measurement is never
compliance) with real-PostgreSQL proofs: all five empty suites run green; a seeded deliberately
failing canary yields `passed=false` in report and history (the CI-blocking signal); unevaluated
cases fail rather than silently pass. The blockizer core lands in `core/blockizer.py` (D57:
pinned GFM profile via markdown-it-py, fixed normalization order, `BLOCKIZER_VERSION`) with the
golden corpus at `src/tests/blockizer_corpus/` — one seeded mixed document (headings,
hard-wrapped paragraph, atomic table, list items, code fence, quote, Czech NFC), its hash
sequence locked in CI; behavior proofs: reflow never changes identity, an edit changes exactly
the edited block, offsets slice document.md exactly.

**Phase 0 exit (2026-07-18): all four exit criteria are met** — migrations apply/rollback
cleanly (WP-0.2); the no-op worker runs end-to-end through the task-queue delivery port with
`processing_state` + `cost_ledger` rows (WP-0.3 + WP-0.4a, per the sequencing amendment); the
eval harness runs empty suites in CI (WP-0.5); the blockizer golden corpus exists with a seeded
doc (WP-0.7). Carried forward, not exit-blocking: WP-0.4b (GCP parity,
Phase-1-parallel) and WP-0.6 (golden-set labeling tooling, needed by Phase 2's measured
thresholds).

**WP-0.4 complete (2026-07-17; `P0-L01-D62-ARCH-GATE` and
`P0-L03-D61-PORT-PROTOCOLS`):** the first slice added the ten behavior-empty D62 package
homes, the locked [import-linter configuration](../../.importlinter), and the required
[CI architecture gate](../../.github/workflows/ci.yml) in
[PR #63](https://github.com/writeitai/rememberstack/pull/63). A deliberate `core → adapters`
edge broke both applicable contracts on Python 3.12 and 3.13 in
[CI run 29610259852](https://github.com/writeitai/rememberstack/actions/runs/29610259852);
the repaired head kept all five contracts and every existing check green in
[CI run 29610342445](https://github.com/writeitai/rememberstack/actions/runs/29610342445).
The completion slice in [PR #66](https://github.com/writeitai/rememberstack/pull/66)
exports exactly seven D61 Protocols, adds their independent shared values and contract tests,
and keeps all five import contracts plus every required Python 3.12/3.13 and coverage context
green in [CI run 29616604149](https://github.com/writeitai/rememberstack/actions/runs/29616604149).
Adapter implementations remain separately scoped to WP-0.4a and WP-0.4b.
