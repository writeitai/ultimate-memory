# Phase 5 — Retrieval Complete

**Goal:** the full consumer surface: every primitive, recipes as registry rows, the whole
envelope contract in CI, all surfaces, the consumption skill.

**Entry gates:** none (spikes inside).
**Exit criteria:** retrieval §11's contract-test list green in CI; the S-battery's retrieval
classes pass (A–M, N′ incl. S46/S47/S60/S61); **S58 cold-agent test passes** with the shipped
skill; latency budget measured against the §10 envelope.

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-5.1 | Remaining primitives: `fuse`, `rerank`, `transcript`, `delta`, `pages_about`, enumerated `aggregate`, `scan` | retrieval §3, §9 | Phase 4 | primitive set | per-primitive tests; batch pool isolation | done (PR #105; primitives at the `QueryEngine` layer + `core/ranking.py`; MCP/CLI/API rendering is WP-5.4) |
| WP-5.2 | Recipe registry (`retrieval_recipes` rows + registration linter + replay-equivalence test) | retrieval §4; schema §11.A; D50 | WP-5.1 | registry + seed recipes | grain-bar CHECK; recipe≡chain diff empty | done (PR #106; `Recipe`/linter/`RecipeRegistry`/`RecipeExecutor` + 9 canonical recipes; MCP/CLI rendering is WP-5.4) |
| WP-5.3 | Envelope, complete: parts/composite, contradiction co-member contract, truncation/continuations, horizons, identity regime, negatives | retrieval §5–6; D49 | WP-5.1 | envelope layer | contract CI list green (S18/S23/S49…) | done (PR #107; S23 co-members + D54 support + S47 parts + S61 regime + believed_at horizons; contract suite `test_envelope_contract.py`) |
| WP-5.4 | Surfaces: MCP (rendered from registry), CLI parity, API auth perimeter hooks | retrieval §7; D50–D51 | WP-5.2 | MCP server + CLI | tool list = registry; parity test | done (PR #108; `RecipeSurface`/`RecipeMcpServer` + API `/recipes`+`/recipe/{name}`+auth + `ugm query` CLI; parity test + reference docs) |
| WP-5.5 | **Consumption skill v1** (per-deployment rendered) + the S58 protocol as a repeatable eval | retrieval §8; D51 | WP-5.3 | skill + S58 harness | S58 green with a cold harness | done (deployment/scopes/K/mount/recipe-rendered `SKILL.md`; provider-backed S58 retrieval canary) |
| WP-5.6 | Retrieval spikes: Lance scale, hub pagination, rerank weights, envelope overhead, hydration batching, resolve context | retrieval §13 | WP-5.3 | spike reports + tuned constants | recorded in eval_runs | planned |
| WP-5.7 | **PyPI packaging of the client surface**: base install = SDK + CLI + MCP; extras `[server]`/`[connectors-*]`/`[k]`; **lineage-aware ingest** in SDK/CLI; connector-management commands | packaging §1–2; D62 | WP-5.4 | the pip package (dist `remember-dev` — decided, questions.md §11a) | fresh-venv install → query + ingest against a compose deployment; push-feeder lineage test (stable source_ref → versions) | planned |
