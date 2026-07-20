# Phase 6 — Plane K

**Goal:** the knowledge framework: compiled + authored pages, the compile machine, triggers,
subscriptions, the belief tier.

**Entry gates:** #4 K writer/planner model picks (Codex/OpenCode producers, D53 checkers);
**#5 "whose beliefs"** blocks only WP-6.7.
**Exit criteria:** K scenario classes (S31–S35) pass; writer-completeness canaries green;
citation faithfulness sampled; a full compile cycle (route → plan → compile → validate →
commit) runs debounced end-to-end; dispatch invokes a demo subscriber with a delta payload.

| WP | Goal | Reads | Depends | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|---|
| WP-6.1 | Control plane live: rules, rule keys, plan decisions, compilations (+ routing SQL) | k_layers §3, §5; schema §11; D45 | Phase 5 | driver: routing + staleness | inputs_hash property tests; stale-set exactness | done (PR #112; all seven rules + exact D45/D54 manifests + two-phase compilation catalog) |
| WP-6.2 | Driver commit loop: DAG order, single committer, validation, two-phase git | k_layers §3, §6 | WP-6.1 | driver | no-contention invariant; failure leaves consistent page | done (deployment lease + exact summary propagation + one-publish crash recovery) |
| WP-6.3 | Fact-sheet band (deterministic render) + fact-sheet-only pages | k_layers §5 (two-band) | WP-6.1 | renderer | band = exact query results | done (exact rule-candidate hydration + lifecycle/contradiction render + zero-LLM compiler) |
| WP-6.4 | Writers (prose band): bundle hydration, citations contract, page summaries, suggestions | k_layers §5–7; D46 | WP-6.3 | writer worker | citation validation; completeness canaries | done (exact capped bundles + sandboxed prose writer + archived transcripts + driver-only acceptance) |
| WP-6.5 | Planner + reflection (blast-radius bands, orphan triggers) + quarantine/adoption flows | k_layers §4–5, §7 | WP-6.2 | planner worker | plan-decision transcripts; D24-band routing | planned |
| WP-6.6 | Authored pages: frontmatter sync, watches, review flags, declaration lint; subscriptions + dispatch | k_layers §4–5; schema §11 (watches/dispatches) | WP-6.2 | authored + trigger surface | flag on cited-evidence change; demo dispatch with delta | planned |
| WP-6.7 | Belief tier configuration (K3) | k_layers §8; D47 | WP-6.4, gate #5 | belief scope | evidence-gated recompile test; dual-role citations | blocked(#5) |
