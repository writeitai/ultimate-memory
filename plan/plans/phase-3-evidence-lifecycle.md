# Phase 3 — Evidence Lifecycle

**Goal:** documents that change: lineages/versions, the watch loop, testimony currency,
reconciliation, reuse — the D54–D56 economy, live.

**Entry gates:** #7 PageIndex hosted/self-hosted (full structure route lands here; **resolved** → D71).
**Exit criteria:** the lifecycle scenario set passes end-to-end on a watched test corpus:
edit (reuse ≥ measured target, only changed chunks re-extract), removal (living retract per
shape), deletion (uniform rule; split-into-four survives), extractor bump (currency swap; a
planted non-rederivation raises exactly one `support_withdrawn` flag and triages both ways);
counts invariant throughout.

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-3.1 | Lineage/version/content-object model + migrations already in place → workers honor them; version-aware E0 | lifecycle §2; schema §6; D55 | Phase 1 | versioned ingest | same-bytes/off-cycle no-ops | done (PR #95) |
| WP-3.2 | Drive connector: watch loop, debounce, `connector_sync_cycles`, source-deletion detection | lifecycle §2, §8; e0 §2 | WP-3.1 | connector | cycle rows; delete observed → lineage cascade | done (PR #95; detection + tombstone — the downstream cascade is WP-3.6's delete worker) |
| WP-3.3 | Full PageIndex route + section snap + placement hints | e0 §4; e1 §3; D39, D57 | WP-3.1, gate #7 (→ D71) | structure worker | snap algorithm property tests | done (PR #96) |
| WP-3.4 | Reuse: block diff, `extraction_input_hash` check, `chunk_claims` occurrence writes, context carry-forward | e1 §7; lifecycle §6; D56 | WP-3.1 | reuse path in E1/E2 | **reuse hit-rate spike measured** on real edits | done (PR #97; spike: `plan/analysis/reuse_hit_rate_spike.md` — hit rate 0.79, re-extraction bounded to edit+neighbors) |
| WP-3.5 | Currency + reconciliation: events ledger, recount (D54 SQL), per-shape closure, retract-at-finalization, K delta emission | lifecycle §3–5; D54–D55; schema §8 | WP-3.4 | reconciliation worker | worked-example test (lifecycle §5) green; idempotent retry | planned |
| WP-3.6 | Deletion grains (version/lineage/source-observed) + normal-delete semantics | lifecycle §8; schema §13.1 | WP-3.5 | delete worker | split-into-four test; forgotten≠deleted audit distinction | planned |
| WP-3.7 | Lifecycle eval pack: currency/count invariants, flag-rate metric, canaries | lifecycle §4; D35 | WP-3.5, WP-0.5 | eval suite `lifecycle` | suite green; flag-rate dashboarded | planned |
