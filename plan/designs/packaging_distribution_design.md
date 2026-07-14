# Packaging & Distribution — Artifacts, Task Execution, Code Architecture (Design)

What the open-source library *ships as*, how work physically executes on both deployment
profiles, and how the codebase is structured so the substrate stays swappable without
spaghetti. Binding design for decision **D62**, filling in what D60 (the OSS boundary) and D61
(provider ports) left as the unwritten packaging design (`questions.md` §11a). Companion
analyses: the cloud repo's `analysis/oss_cloud_split/` (the Sentry-shaped split) and the
brainstorm rounds recorded in this repo's PR #37. Numbers and tool choices marked *(slot)*
await the owner-provided stack conventions (roadmap §3).

> **Reading this cold (CLAUDE.md Rule 1).** The system is a per-deployment memory pipeline:
> workers process documents in stages (E0 convert → E1 chunk → E2 extract → E3 adjudicate …),
> each stage recorded in the Postgres table `processing_state` (D12: one row per
> target/stage/version — pending/running/succeeded/failed/dead-letter). **D61 ports** are
> narrow interfaces over the deployment substrate (object store, task queue, mounts, K git
> remote, model providers, telemetry, auth perimeter), each with a **self-host** adapter and a
> **GCP reference** adapter. Jargon used below: **at-least-once delivery** = a task may be
> handed to a worker more than once (never zero times), so handlers must be **idempotent**
> (safe to re-run — D12 already mandates this); **`LISTEN/NOTIFY`** = Postgres's built-in
> publish/subscribe — a session can sleep on `LISTEN channel` and be woken instantly by any
> transaction that runs `NOTIFY channel`; **`SELECT … FOR UPDATE SKIP LOCKED`** = the Postgres
> idiom that lets N workers each atomically claim different pending rows with no coordinator
> and no double-claims; **hexagonal / ports-and-adapters** = the code architecture where pure
> domain logic depends on interfaces ("ports") and vendor integrations live in swappable
> "adapters" at the edge; **extras** = optional pip dependency groups (`pip install
> pkg[server]`).

## 1. The delivery artifacts — three, each with a distinct consumer

| Artifact | Consumer | Contents |
|---|---|---|
| **The GitHub repository** | contributors, evaluators | source + the `plan/` design corpus (itself a differentiator: the architecture rationale ships with the code) |
| **The PyPI package** — dist **`remember-dev`**, CLI **`remember`**, import **`remember`** (brand **`remember.dev`**, decided 2026-07-13 — `questions.md` §11a; the mechanical rename executes at the release gate) | **agent harnesses and their operators** — positioned as *the client* | base install = the **client surface** (§2): typed SDK, CLI, MCP server. Extras: `[server]` (workers, spine, adapters), `[connectors-gdrive]` etc. (per-connector, server-side), `[k]` (the K compile machine's driver dependencies) |
| **Container images + compose profiles** (published on **GHCR** — same org as the repo, no second registry account) | self-hosters, CI, benchmarks | `api` and `worker` images; `docker compose up` brings up the **self-host profile**: Postgres + MinIO + api + worker(s). The ten-minute quickstart is a release-gating, CI-tested artifact — an infrastructure-shaped OSS that cannot be *tried* quickly dies |

One package, not a package family: the same distribution contains client and server code;
extras select dependency weight. The *positioning* is what differs: the README sells
`pip install <pkg>` as "connect your agent to a memory deployment," because the designed
consumers are harnesses (requirements §Retrieval); operators install `[server]`.

## 2. The client surface (what the base package exposes)

- **Query**: the typed SDK + CLI + MCP server over the retrieval API (D48–D51) — primitives,
  recipes, envelopes. The MCP tool list renders from the recipe registry (D50).
- **Ingest — lineage-aware by contract**: `client.ingest(bytes|path, *, source_kind=…,
  source_ref=…, source_modified_at=…, versioning_mode=…)` / `ugm ingest …`. Writes always
  enter through E0 (D60 invariant — no surface writes around the pipeline). The optional
  lineage fields are the load-bearing part: a caller that pushes the same logical document
  repeatedly with a stable `source_ref` creates **versions of one lineage** with full D54–D56
  lifecycle semantics (currency, reuse, retraction) — which is how third parties build
  *push-style feeders* for sources the deployment cannot poll (behind-firewall systems),
  without us shipping their connector. Omitted lineage fields = a one-shot upload lineage.
- **Connector management, never execution**: `ugm connectors add|list|pause|status`.
  Connectors (Drive, mailboxes, URLs) execute **deployment-side** as workers — they own sync
  cycles, debounce, and deletion detection (`connector_sync_cycles`, D55), semantics that
  must not depend on a client process staying alive. The client configures them; credentials
  live deployment-side.
- **Admin**: the D24 review CLI (cluster review, `support_withdrawn` triage) and deployment
  introspection (pipeline state, DLQ, budgets) — reading state the spine already persists.

## 3. Task execution — one model, two delivery shells

**The unifying rule (this section's core, refining D61's queue-port row):**

> **Work is Postgres rows; the queue port only delivers wake-ups.** `processing_state` (D12)
> is the sole authority for what must run, is running, succeeded, failed, or dead-lettered.
> The task queue never *owns* work — it *announces* it. Consequently there is no push-vs-pull
> split in application code: both adapters implement "announce this row."

**Application code is written once, as handlers.** Each stage registers
`handle_<stage>(task) → result`. A completing handler writes its results + its
`processing_state` transition + **enqueues the successor stage** (the chain rule,
orchestration §1) through the port. Handlers are idempotent (D12; both adapters are
at-least-once) and never know which shell invoked them.

**The two shells (~200 lines each, in `adapters/`):**

- **Self-host shell — `LISTEN/NOTIFY` + `SKIP LOCKED` (not naive polling).** Enqueue =
  `INSERT` the task row **in the same transaction** as the caller's state writes (crash
  between "state written" and "successor enqueued" is *impossible by construction* — the
  decisive correctness argument for Postgres here) + `NOTIFY queue_wake`. Worker processes
  sleep on `LISTEN`; a notify wakes them in milliseconds; the woken worker claims with
  `SELECT … FOR UPDATE SKIP LOCKED LIMIT n` (atomic multi-worker claiming, no coordinator).
  A **slow fallback poll (~30 s)** exists only as a safety net: missed notifications,
  `run_after` schedules coming due, crash recovery. Retry counters/backoff are row columns;
  per-queue rate limits are a token bucket consulted in the claim query. Scaling =
  `docker compose up --scale worker=N`.
- **GCP reference shell — Cloud Tasks push.** Enqueue = create a Cloud Task; delivery = an
  HTTP push to a thin Cloud Run handler-dispatch server; retries/backoff/rate limits are
  queue configuration; attempt counts arrive in headers. Cloud Run autoscales on push.

**The janitor closes both shells' gaps with one mechanism.** A scheduled sweep re-announces
any `pending` row older than a threshold whose delivery evidently got lost. On GCP this
repairs the non-transactional enqueue window (state committed, Cloud Task creation crashed);
on self-host it backstops lost notifications. Same code, port-agnostic, because truth was in
the row all along.

**The port contract** (what both shells must satisfy; the orchestration design's queues,
lanes, and budgets sit on top, adapter-agnostic): `enqueue(stage, target, queue/lane,
run_after?)`; at-least-once handler invocation; bounded retries with backoff → DLQ hand-off
(dead-letter state is `processing_state`, both shells); per-queue rate limits; scheduled
delivery (`run_after`). A third, **test-tier** adapter — in-process/synchronous — exists for
unit tests and local hacking; it is test infrastructure, not a maintained deployment adapter
(D61's two-adapter discipline governs what we *maintain*, not what the port permits — a
community Redis/arq adapter is possible against the same contract; considered and not chosen
for maintained self-host: it adds a second stateful service to every deployment and gives up
transactional enqueue, for throughput this LLM-bound pipeline never needs).

## 4. Code architecture — hexagonal, with the arrows enforced in CI

```
ugm/
  model/       # typed domain objects (Pydantic at boundaries; TypedDict/enum/Literal inside) — imports nothing
  core/        # PURE logic, zero I/O: blockizer, packer, snap algorithm, grounding checks,
               # counting rules, currency rules, envelope assembly — unit-testable with no infra
  spine/       # the Postgres access layer — the ONLY place SQL lives (repositories per aggregate)
  ports/       # the seven D61 interfaces as typing.Protocols — no implementations
  adapters/
    selfhost/  # MinIO/S3 object store, the pg-queue shell (§3), local-dir mount publisher,
               # plain git remote, BYO model keys, OTLP telemetry, API-key auth
    gcp/       # GCS, the Cloud Tasks shell, gcsfuse publication, hosted repo, configured
               # providers, managed telemetry
    testing/   # in-process queue, tmpdir object store — the test tier
  llm/         # the programmatic-LLM layer (D52 class 2): prompt registry (rendered from the
               # ontology/recipe registries), schema-constrained calls, transcript writing —
               # every extractor/adjudicator call goes through here, no exceptions
  workers/     # stage handlers: thin orchestration composing core + spine + ports
  surfaces/    # api / mcp / cli — depend on services, never on adapters
  eval/        # the D22 harness, canaries, contract tests
  profiles/    # composition roots: selfhost.py / reference.py wire a deployment from config —
               # explicit constructor injection, no DI framework, no magic
```

**The anti-spaghetti mechanism is not the layout — it is the mechanically enforced dependency
direction** (the user's requirement "no spaghetti" as a failing test, not a convention):

- `core` imports only `model`. `workers` import `core` + `ports` + `spine` — never
  `adapters`. `surfaces` never import `adapters`. Vendor SDKs (`google.cloud.*`, `boto3`,
  `redis`, …) are importable **only** inside `adapters/`. SQL strings/builders exist **only**
  inside `spine/`.
- Enforced with **import-linter** contracts in CI: an illegal import is a build failure, not
  a review comment. Architecture erosion fails loudly (the project's standing value).
- Every worker is a thin shell over pure `core` functions, so the logic tests run without
  Postgres, queues, or GCS; integration tests run on the `testing/` + compose profile.

This is what makes "develop locally / deploy on GCP / build the cloud later" a **profile
selection**, not a refactor — and per D60 rule 2, the cloud product consumes exactly these
ports and published extension points, keeping it portable off GCP too.

## 5. Deployment profiles

- **Self-host profile** (the compose file, shipped + CI-tested): `postgres` (the spine + the
  queue + the DLQ — one stateful service), `minio` (object store), `api`, `worker` (×N),
  optional `k-driver`. Mounts publish to a local directory tree. Dev loop: `docker compose up
  postgres minio` + run api/worker from source; pure-logic work needs no containers at all
  (`adapters/testing`).
- **Reference profile** (GCP — the production shape and what the cloud runs): Cloud Run jobs
  + Cloud Tasks, GCS + gcsfuse, per D61's table. Terraform/config templates live in-repo.
- Profile choice is configuration consumed by `profiles/`; no code path branches on "am I on
  GCP" outside adapters.

## 6. Releases, upgrades, export

- **Versioning**: semantic versioning on the package and images (same version string);
  every release publishes PyPI + GHCR images + the compose file pinned to that tag.
  *(Names decided — dist `remember-dev`, CLI `remember`, brand `remember.dev`; container
  images follow the dist name when the rename gate executes — `questions.md` §11a.)*
- **Upgrades**: Alembic migrations run **before** workers roll (the schema doc is the source
  of truth; migrations implement it). Processing-version stamps (D7/D12) mean code upgrades
  never silently invalidate derived state — reprocessing is explicit, per version filters,
  through the Phase-7 lanes.
- **Export / import — rebuild-first makes this cheap (D7)**: a deployment's portable state is
  exactly its **sources of truth** — the Postgres database (dump), the raw + artifacts
  buckets (object sync), and the K git repo (clone). Projections (P1/P2/P3) are *not*
  exported: they rebuild from the spine on import by the standard cycle. `ugm export` /
  `ugm import` wrap those three + a manifest (versions, deployment id); this doubles as the
  cloud↔self-host migration path in both directions (no lock-in — a D60 credibility
  requirement).

## 7. Decision interactions

| Decision | Effect |
|---|---|
| D60 (OSS boundary) | *implements*: the complete-single-deployment deliverable becomes concrete artifacts; export/import keeps self-hosting a first-class exit |
| D61 (ports) | *refines the queue row*: queue = delivery-only over `processing_state` truth; self-host adapter confirmed as the Postgres shell; test-tier adapter named |
| D12 (idempotency, DLQ) | *load-bearing*: at-least-once + idempotent handlers is the uniform execution contract; DLQ stays Postgres rows on both shells |
| D50/D51 (trust, surfaces) | *unchanged*: API-key perimeter in the library; ingest is a client capability but writes through E0 |
| D54–D56 (lifecycle) | *extended to clients*: the lineage-aware ingest contract lets push-feeders participate in versioning |
| D52/D53 (execution classes, model split) | *housed*: the `llm/` layer is where class-2 calls and family assignments live |
| orchestration design | *unchanged semantics*: queues/lanes/budgets defined against the port contract; both shells satisfy it |

## 8. Spikes / open slots

1. **Stack-convention slots** *(owner-provided; gate WP-0.1)*: package manager, lint/format,
   CI provider, secrets handling. The layout and import-linter contracts above are bound.
2. **pg-queue shell parameters**: fallback-poll interval, claim batch size, token-bucket
   granularity — measure under Phase-7 load tests.
3. **Compose quickstart UX**: measure the cold-start-to-first-query time; it is a release
   gate (target: minutes).
4. **Export/import round-trip drill**: self-host → export → import → projections rebuild →
   S-battery subset green; belongs in Phase 7's drills.
5. **MCP server distribution**: whether the MCP server also ships as a standalone binary/uvx
   target for harnesses that don't want a Python env — decide with the first external users.

## References

Decisions: **D62** (this design), D7, D12, D48–D56, D60–D61 (`decisions.md`). Cloud-side
analyses: `ultimate-memory-cloud/analysis/oss_cloud_split/` (synthesis + licensing/naming).
Plans: `plan/plans/roadmap.md` §3 (stack), phases 0/5/7 (the WPs realizing this design).
Open governance items (name, CLA): `questions.md` §11a.
