# Round 2 review of `plan/implementation_evals`

**Verdict:** not yet safe as a binary design-conformance acceptance gate. The suite is structurally healthy (69 valid YAML files, unique filename-matching IDs, one uniform precedence paragraph, and accurate area counts), and all four Round 1 factual corrections are now present. However, the design-first flip is incomplete: six `Read` instructions name a nonexistent requirements path, five never identify a binding source, and four designate non-design material as binding. More importantly, several checks can reject a conforming implementation or accept a non-conforming one: the K concurrency description contradicts the binding K design; the D64-tagged check never requires the 16-predicate seed; D23 coverage is incomplete; several conditions follow decision-log wording or reviewer suggestions beyond what the designs bind; and some conditions require the wrong enum or architecture shape.

## MUST-FIX

1. **Repair the ten defective `Read` instructions identified under Surgery scars.** Six contain the nonexistent path `requirements_v3.md`; five of those also lack the promised “binding source” wording. Four instructions call `CLAUDE.md` or `plan/analysis/*` material binding even though the suite's own precedence rule says `plan/designs/*` controls.
2. **Fix `boundary_correctness_in_library_d60`.** “Not calling out to a proprietary cloud service to do the work” is broad enough to prohibit the configured model/OCR provider calls that D61 and `packaging_distribution_design.md` §§4–5 explicitly allow through ports. The invariant is that correctness machinery cannot be cloud-product-only or commercially gated, not that it cannot call a configured provider.
3. **Fix the two requirements checks that over-bind code policy.** `code_config_via_pydantic_settings` forbids every `os.environ`/`os.getenv` occurrence even though `requirements_v3.md` §Code explicitly permits a reasoned per-line exception. `code_tooling_and_migrations` requires CI-on-every-PR and a “relax-with-receipts” policy that §Code does not bind.
4. **Fix `e0_subworker_chain_crossrefs_d36` condition 2.** “Only that sub-worker and its downstream dependents — never the whole chain” is self-contradictory for an `ingest` version bump, whose downstream dependents are the rest of the chain. `e0_files_design.md` §1 binds per-sub-worker idempotency and dependency-scoped reruns, not an absolute no-whole-chain result.
5. **Fix `e2_asserted_validity_immutable`.** Condition 1 omits the binding `effective_period` member of `claim_valid_kind` (`postgres_schema_design.md` §§1 and 8). Condition 4 requires a “monotonicity guard” found in decision prose but not in any binding design section; under the suite's stated precedence it cannot be a scored condition unless the design is amended first.
6. **Fix `e2_grounding_layered_dual_field` condition 2.** It says the independent audit is “never per-claim,” while `e2_e3_claims_relations_design.md` §3.3 explicitly permits per-claim judging for the borderline band. Require sampling as the default and allow the designed borderline escalation.
7. **Fix the E3 checks.** `e3_observations_untyped_adjudicated` demands an enum shaped as `evidence / supersede / contradict-coexist / new`, but the binding shared `adjudication_outcome` enum is `add | noop | supersede | contradict | same_as_merge_proposal | retracted_source_removal` (`postgres_schema_design.md` §§1, 9.A). `e3_relations_evidence_collapse` says every repeat of “the same fact” must attach to an existing row, omitting the compatible-validity qualification: §9 deliberately permits a new row for a recurring `(subject, predicate, object)` fact in a non-overlapping validity window.
8. **Fix `er_review_queue_cli` for the current reviewer contract.** Its description and condition 1 say the middle band routes to humans. `k_layers_design.md` §7 permits a human **or designated reviewer agent** and says the latter is normal in agent-operated deployments. The check should require the Postgres queue plus CLI/agent-consumer boundary and the same reversible verdict contract, not a human-only runtime.
9. **Fix the K checks.** `k_planner_writer_driver` says “no concurrent sessions,” contradicting `k_layers_design.md` §6, which explicitly runs writers in parallel across disjoint pages; the forbidden case is concurrent sessions editing shared files. `k_one_mechanism_n_scopes` condition 2 says the shared model page is a compile input of “every page,” but §7 binds it as an input of every **writer**; authored pages have no compile input and fact-sheet-only pages skip the writer.
10. **Fix the ops checks.** `ops_execution_classes_bound` falsely says schema pipeline enums carry an execution-class value for every worker; the binding schema has stage/component enums, not an execution-class enum or complete worker inventory. `ops_idempotency_dlq` hard-codes “max 2” despite `postgres_schema_design.md` §2 calling two a tunable starting value. `ops_producer_checker_families` permits a recorded same-family exception, while the controlling `orchestration_design.md` §8 says checker seats “never share a family” with their producer; the check currently follows the looser decision-log prose instead of the design.
11. **Fix `p_projections_hold_no_authority` condition 1.** The designs bind dumb deterministic projection writers and one validity home (`overall_design.md` §2; `p2_graph_design.md` §1), but D62's package-level import contracts do not bind the invented finer rule that every projection builder may import only read repositories/projection writers or that CI must encode those particular submodule arrows. Score the architectural outcome, or first bind that exact import graph in `packaging_distribution_design.md` §4.
12. **Make D23 coverage match the binding schema and restore the omitted Round 1 load-test condition.** `registry_scale_partitioning_d23` names only three large tables, missing the other partitioned DDL in schema §§7–9.A, and it omits the representative ungated-volume load-test hook explicitly called for by `registries_design.md` §§9 and 11 and by the Round 1 review.
13. **Make D64 scoreable.** `e3_predicate_registry_governed` cites/tags D64 but never requires exactly the current 16-predicate seed or names `uses` and `reports_to`. A 14-predicate pre-D64 implementation can score 1. Bind the exact seed from `registries_design.md` §4 (or at minimum assert 16 plus those two promoted rows and their signatures).
14. **Close the remaining binding coverage gaps:** K watches/subscriptions/dispatch and trigger acyclicity (`k_layers_design.md` §5), K eval acceptance machinery (§7), the S58 cold-consumer skill test (`retrieval_design.md` §§8 and 11), hard-forget erasure of cited K git history/backups (`k_layers_design.md` §10), and the orchestration lane/queue/backfill and cross-cloud batching rules (`orchestration_design.md` §§2–5).

## 1. Surgery scars

### 1.1 Description proofreading

No description contains an obvious regex splice, duplicated path fragment, truncated clause, or garbled `, then` surgery artifact. The descriptions parse as complete sentences.

One description is grammatically intact but factually damaged in effect:

- `k_planner_writer_driver.yaml`:

  > `Plane K is compiled by planner/writer/driver — mechanical zero-LLM routing, dependency-ordered scheduling, one automated committer, no concurrent sessions.`

  The last phrase drops the binding qualifier “editing shared files.” `k_layers_design.md` §6 says writers run in parallel across disjoint pages; `requirements_v3.md` §Fixed choices says “no concurrent sessions editing shared files.”

### 1.2 Broken or unflipped `Read` paths

The following six instructions cite `requirements_v3.md` at repository root. That file does not exist; the actual path is `plan/requirements/requirements_v3.md`.

- `boundary_provider_ports_d61.yaml`:

  > `Read requirements_v3.md §Fixed choices & the reference deployment — the binding source — and decisions.md D61 for rationale and refinement history, then inspect the adapter layer and self-host stack under src/ and the deploy profiles.`

- `code_config_via_pydantic_settings.yaml`:

  > `Read requirements_v3.md §Code, then inspect the settings module(s) and grep the source for environment access under src/.`

- `code_tooling_and_migrations.yaml`:

  > `Read requirements_v3.md §Code, then inspect the tooling configuration, CI workflows, and migrations under the repo.`

- `ops_metering_budgets_enforced.yaml`:

  > `Read requirements_v3.md §Operational properties (cost discipline) and decisions.md D52, then inspect the cost ledgers and budget checks under src/.`

- `ops_versioned_replay_from_storage.yaml`:

  > `Read requirements_v3.md §Operational properties (versioned processing) and decisions.md D7/D33, then inspect version stamping and rebuild paths under src/.`

- `ret_claims_never_answer_now.yaml`:

  > `Read requirements_v3.md §Retrieval (the temporal-split paragraph), decisions.md D41/D49, then inspect recipe definitions and naming under src/.`

The latter five also do not say which source is binding and do not use the advertised design/requirements-first + decision-rationale form. The two code checks have no decision citation, which is fine, but should still say that the correctly pathed requirements section is the binding source. The other three should identify the requirements/design source as binding and the decision entries as rationale/history.

### 1.3 Wrong material designated as “the binding source”

These are not grammar corruption, but they are source-precedence corruption and conflict with the common paragraph in the same file:

- `boundary_no_human_control_plane_d60.yaml`:

  > `Read CLAUDE.md Rule 3 — the binding source — and decisions.md D60 for rationale and refinement history, then survey the repository's shipped surfaces.`

  `CLAUDE.md` is repository guidance, not a binding design. Use `packaging_distribution_design.md` §§1–2 and 5 plus the relevant requirements boundary.

- `e3_relations_evidence_collapse.yaml`:

  > `Read plan/analysis/concepts.md — the binding source — and decisions.md D2 for rationale and refinement history, then inspect the relations and relation_evidence schema and the E3 normalization under src/.`

  `plan/analysis/concepts.md` is analysis. The binding sources are `postgres_schema_design.md` §9 and `e2_e3_claims_relations_design.md` §5.

- `ops_execution_classes_bound.yaml`:

  > `Read plan/analysis/workers.md + plan/designs/orchestration_design.md — the binding source — and decisions.md D52 for rationale and refinement history, then inspect the worker implementations under src/.`

  `workers.md` is the inventory referenced by the design, but it is not co-equal binding ground truth. Lead with `orchestration_design.md` §8 as binding; read the inventory second as implementation mapping.

- `p3_corpus_fs_projection.yaml`:

  > `Read plan/designs/e0_files_design.md §6 plus plan/analysis/p3_agent_navigation.md — the binding source — and decisions.md D40 (and D55's stability contract) for rationale and refinement history, then inspect the P3 builder under src/.`

  The binding source is `e0_files_design.md` §6. The navigation analysis may be supporting context, not part of the phrase “the binding source.”

### 1.4 Uniform precedence paragraph

All 69 checks contain the source-precedence paragraph, and all 69 copies are byte-identical after YAML parsing. That mechanic is sound. Its protection is weakened, however, when the preceding `Read` sentence itself calls a non-design file binding; the judge receives two incompatible source instructions in one prompt.

## 2. Factual accuracy against the designs

### 2.1 Round 1 must-fixes: correctly present

All four Round 1 factual repairs are materially present:

1. **Deletion retention:** `ops_deletion_cascade_grains` condition 2 now says normal deletion retains chunks, claims, evidence links, relations, and entities as audit history, matching `postgres_schema_design.md` §13.1 and `evidence_lifecycle_design.md` §8. Minor wording still needs correction: “version or lineage ... tombstones the lineage/version rows” can imply that deleting one version tombstones the lineage; §13.1 says a version delete tombstones only that version and the lineage continues.
2. **E2 volume exception:** `ops_execution_classes_bound` condition 4 explicitly identifies E2 extraction as the deliberate volume-proportional fixed two-call exception, matching `orchestration_design.md` §3 and `e2_e3_claims_relations_design.md` §§1, 3, and 4.
3. **Selection ledger scope:** `e2_selection_ledger_replay` condition 1 requires drops, `kept_flagged`, and decontextualization edits while excluding plain keeps, matching `postgres_schema_design.md` §8 exactly.
4. **D43 no-cap:** `e3_supersession_fact_level_bitemporal`, `e3_observations_untyped_adjudicated`, `e0_living_mode_retraction`, and the deletion/count checks all preserve the measurement/fixed-period no-cap rule, matching `observations_design.md` §3 and schema §9.A.

### 2.2 Conditions that misstate or overstate the binding design

#### `boundary_correctness_in_library_d60.yaml`

The instruction defines functional as:

> `not calling out to a proprietary cloud service to do the work`

That is not the D60 boundary. `packaging_distribution_design.md` §§4–5 and `requirements_v3.md` §Fixed choices explicitly support model/embedding provider adapters; E0 also permits routed OCR providers. D60 forbids making correctness conditional on the separate commercial **memory cloud**, not provider inference behind a declared port. Narrow the condition to “not implemented only by, or gated on, an out-of-repo commercial control plane,” while allowing configured provider calls.

#### `code_config_via_pydantic_settings.yaml`

Condition 1 requires:

> `no os.environ / os.getenv anywhere in src/`

`requirements_v3.md` §Code says direct access is banned **but explicitly allows a per-line ignore with a reason**. The check must accept that documented exception mechanism or the requirement must be tightened first. The rest of the check (typed settings, `SecretStr`/`SecretBytes`, point-of-use unwrap) matches §Code.

#### `code_tooling_and_migrations.yaml`

Condition 1 adds two requirements absent from its binding source:

> `enforced in CI on every PR`

and

> `per pyproject's relax-with-receipts rule, any disabled check carries a written reason`

`requirements_v3.md` §Code binds Pyright, pytest, Alembic, typing, and Ruff's TID251 enforcement indirectly; it does not bind an every-PR CI trigger or the named waiver policy. These may be good repository policies, but a harness judge cannot score them as design conformance from the cited source.

#### `e0_subworker_chain_crossrefs_d36.yaml`

Condition 2 ends:

> `never the whole chain`

An ingest-component bump can legitimately invalidate every downstream E0 component. `e0_files_design.md` §1 binds “that sub-worker and downstream dependents,” which is the useful invariant. Replace the absolute tail with “never unaffected upstream or sibling work merely because one downstream component changed.”

#### `e2_asserted_validity_immutable.yaml`

- Condition 1's parenthetical lists `proposition-validity vs event-time vs measurement-period` but omits `effective_period`, which is in the binding enum in `postgres_schema_design.md` §§1 and 8.
- Condition 4 requires `a monotonicity guard (a late retrospective cannot move an adjudicated window)`. That wording exists in D41, but no binding design section specifies the guard. The design says claim validity is immutable evidence and fact validity remains on relations; the scoreable condition should stop there unless the guard is promoted into a design.

#### `e2_grounding_layered_dual_field.yaml`

Condition 2 says the independent audit is:

> `never per-claim`

`e2_e3_claims_relations_design.md` §3.3 says the normal audit is sampled/offline, **and** “only a borderline band ever escalates to a per-claim judge.” A correct borderline escalation would currently fail.

#### `e3_observations_untyped_adjudicated.yaml`

Condition 3 requires:

> `a typed enum (evidence / supersede / contradict-coexist / new)`

The binding DDL uses the shared `adjudication_outcome` enum: `add`, `noop`, `supersede`, `contradict`, `same_as_merge_proposal`, and `retracted_source_removal` (`postgres_schema_design.md` §§1 and 9.A). The prose concepts map roughly (`noop` is evidence collapse; `add` is new), but a binary judge may require the literal four-value shape and reject the correct schema. Refer to the binding enum and separately test the observation worker's allowed semantic paths.

#### `e3_relations_evidence_collapse.yaml`

Condition 2 says:

> `the same fact asserted again links evidence to the EXISTING relation rather than inserting a duplicate relation row`

This needs “with compatible/overlapping validity.” `postgres_schema_design.md` §9 defines relation identity as `(subject, predicate, object) + validity interval` and deliberately permits recurring facts in non-overlapping windows. The current condition can reject the correct new-row behavior for “Alice worked at Acme, left, then later rejoined.” Conditions 1 and 3 otherwise correctly enforce the M:N evidence layer and evidence-once key.

#### `er_review_queue_cli.yaml`

The description says “Human review,” and condition 1 routes the middle band “to humans.” `registries_design.md` §8 uses human language, but the later, binding `k_layers_design.md` §7 generalizes the accountable reviewer to a human **or designated reviewer agent**. The current check is not design-complete and its single-source Read instruction hides the refinement.

#### `k_planner_writer_driver.yaml`

The description's `no concurrent sessions` contradicts `k_layers_design.md` §6:

> `Writers run in parallel across disjoint pages`

What is prohibited is concurrent sessions editing shared files or committing independently. The driver remains the sole automated committer and dependency order still applies.

Condition 1 also says “one writer per page per cycle” without limiting that to stale compiled prose pages. Authored pages are not writer targets, unchanged pages do not compile, and fact-sheet-only pages skip writers (`k_layers_design.md` §§4–6).

#### `k_one_mechanism_n_scopes.yaml`

Condition 2 requires the shared model page as a compile input of `every page in the scope`. `k_layers_design.md` §7 says it is a declared input of every **writer**. Authored pages have no compile input/`inputs_hash`, and fact-sheet-only pages skip the writer. Require it for every applicable compiled writer invocation.

#### `ops_deletion_cascade_grains.yaml`

The Round 1 retention correction is good, but this phrase is imprecise:

> `Normal deletion (version or lineage grain) purges raw/artifact bytes and tombstones the lineage/version rows`

Per `postgres_schema_design.md` §13.1, version deletion tombstones only that version; lineage deletion tombstones the lineage and every version. Spell out the two branches so a judge does not demand lineage tombstoning for version deletion.

#### `ops_execution_classes_bound.yaml`

Condition 1 appends:

> `(the schema's pipeline enums carry a value for every worker)`

No binding schema enum records execution class, and `pipeline_component`/`pipeline_stage` do not enumerate every worker in the inventory (for example deletion and hard-forget are not component values). `orchestration_design.md` §8 binds the classification, not this storage representation. Require a complete inspectable inventory/config mapping, or add an execution-class field to the schema design first.

#### `ops_idempotency_dlq.yaml`

Condition 3 says:

> `Retries are bounded (per the design: max 2)`

There is a design-corpus discrepancy: `overall_design.md` §4 and `requirements_v3.md` §Fixed choices say max 2, while the more specific binding schema §2 says `max_attempts = 2` is a **tunable per-stage starting point, not a committed constant**. The check should not make a correct configured non-2 value fail. Require bounded, persisted per-stage retry policy with shipped default 2, and report the source discrepancy under the standard precedence rule.

#### `ops_producer_checker_families.yaml`

Condition 2 permits same-family checking:

> `unless an explicit recorded exception is present`

That follows D53's decision prose, but the controlling `orchestration_design.md` §8 says checking seats “never share a family” with the producer. Under this suite's explicit precedence, a recorded exception cannot score 1. Remove the exception or reconcile the design first.

#### `p_projections_hold_no_authority.yaml`

Condition 1 invents a precise submodule/import contract:

> `Projection builders (P1/P2/P3 writers) import only read-side repositories and projection writers`

The designs bind the outcome: projections never decide or mutate truth, P2's writer is dumb/deterministic, and package-level dependency arrows are CI-enforced. `packaging_distribution_design.md` §4 does not bind read/write repository subpackages or forbid projection workers from importing all core modules via the stated import-linter graph. This can fail a conforming architecture for using a different internal module split.

#### `registry_scale_partitioning_d23.yaml`

Condition 1 narrows “the large append-only tables” to:

> `(mentions, resolution_decisions, relation_evidence — per the current schema design)`

That parenthetical is false for the current schema. Binding partitioned DDL also exists for `claims`, `claim_extraction_decisions`, `chunks`, `chunk_claims`, `testimony_currency_events`, and `observation_evidence` (`postgres_schema_design.md` §§7–9.A and 12). The check also omits `registries_design.md` §9/§11's required load-test at ungated D25 volume. This is both factual incompleteness and a Round 1 application miss.

#### `e3_predicate_registry_governed.yaml`

Condition 3 says only:

> `The seed core ships as registry CONTENT (schema.org-aligned types + predicates with parent anchoring...)`

Nothing requires 16 predicates or the two D64 promotions. A pre-D64 14-predicate seed passes every listed condition. `registries_design.md` §4 binds the authoritative 16 and the exact signatures `uses: Person|Organization → Product` and `reports_to: Person → Person`.

### 2.3 Checks with no material factual defect found

Subject to the citation and coverage issues below, the remaining conditions track the designs closely. In particular, the E0 storage/conversion/structure checks, E1 block/chunk mechanics, no-pre-gate rule, Selection ledger and recall envelope, testimony counting, D43 no-cap behavior, ER cascade/reversibility, projection view contract, retrieval hydration/envelope/grain/negative mechanics, provider ports, delivery shells, and source-of-truth split are substantively aligned.

## 3. Citation correctness

### 3.1 Wrong or insufficient binding citations

| Check | Current binding citation | Problem | Correct binding target |
|---|---|---|---|
| `boundary_correctness_in_library_d60` | requirements §Vision | Too vague to bind the nine named mechanisms or the provider boundary. | `packaging_distribution_design.md` introduction/§§1–5 plus the named subsystem designs; this check is still an omnibus. |
| `boundary_no_human_control_plane_d60` | `CLAUDE.md` Rule 3 | Not a design document. | `packaging_distribution_design.md` §§1–2, 5 and `retrieval_design.md` §§7, 9. |
| `e2_asserted_validity_immutable` | E2/E3 design §7 | §7 is a summary and does not bind the full enum/schema; it also cannot prove the monotonicity condition. | `postgres_schema_design.md` §§1, 8 plus E2/E3 §§3.3, 7. |
| `e3_predicate_registry_governed` | whole `registries_design.md` | D64 is score-critical and the exact seed is in one place. | `registries_design.md` §4 (especially “Seed core” and D64 graduations), plus §7 for promotion. |
| `e3_relations_evidence_collapse` | `plan/analysis/concepts.md` | Analysis is incorrectly called binding. | `postgres_schema_design.md` §9 and `e2_e3_claims_relations_design.md` §5. |
| `e3_supersession_fact_level_bitemporal` | schema §9 | §9 binds relations, not observation no-cap/retraction semantics. | schema §§9 **and 9.A**, plus `observations_design.md` §3. |
| `ops_execution_classes_bound` | analysis workers + orchestration, jointly binding | The analysis inventory is not binding and cannot override the design. | `orchestration_design.md` §8 first; inventory second only for mapping. |
| `p1_lance_estate_rebuildable` | `overall_design.md` §§4–5 | Those sections do not bind all four Lance targets, especially observation labels. | E1 §5; E2/E3 §5; observations §§1, 5; P2 §6; overall §§4–5 for orchestration/rebuild. |
| `p2_rebuild_first_snapshots` | `p2_graph_design.md` | Condition 4 separately scores P3 snapshot behavior not bound by that doc. | Add `e0_files_design.md` §6 for condition 4. |
| `p3_corpus_fs_projection` | E0 §6 + P3 analysis jointly binding | Analysis is not binding. | `e0_files_design.md` §6; lifecycle §2 for lineage stability. |
| `registry_scale_partitioning_d23` | whole schema design | Too broad and misses the load-test source. | `postgres_schema_design.md` §§0, 4, 7–9.A, 12 and `registries_design.md` §§9, 11. |
| `ret_claims_never_answer_now` | malformed requirements path | Correct requirement, wrong path, and it omits the design that implements the bar. | `plan/requirements/requirements_v3.md` §Retrieval plus `retrieval_design.md` §§4 and 6. |
| `scope_views_share_graph_d16` | `registries_design.md` §1 | §1 binds deployment/entity-space separation, but not the scope-view mechanism. | `registries_design.md` §4 (“Scopes share one graph...”) plus `retrieval_design.md` §9. |

The malformed requirements paths in §1.2 are citation failures even where their conditions are otherwise correct.

### 3.2 Broad but usable citations

Several files cite an entire design even though a precise section exists (`er_merges_reversible` → registries §6; `er_resolution_cascade_t0_t4` → §§3 and 5; `er_review_queue_cli` → §8; `eval_golden_sets_d22` → §10; the K checks → their named §§3–8). These are not wrong-document failures, but tightening them would reduce judge drift and make the source precedence operational rather than ceremonial.

## 4. Coverage against D1–D64 and binding requirements

### 4.1 Decision coverage status

- D1–D12 are covered, with the D7/D12 citation/tag caveats below.
- D13–D14 are engine/naming choices and are either excluded by the suite's stated policy or covered incidentally by the fixed-engine/provider checks.
- D15–D25 are represented; D22 and D23 are only partially complete for the reasons below.
- D26–D30 are correctly excluded as withdrawn.
- D31–D63 all have at least one direct check or a scoreable condition, though several conditions need the factual corrections above.
- **D64 is not actually covered.** It is tagged and cited but not asserted.

### 4.2 Remaining uncovered or under-covered binding behavior

1. **D64 seed content:** require the authoritative 16-predicate core and the `uses`/`reports_to` promotions/signatures (`registries_design.md` §4).
2. **D23 full physical design and load test:** cover all currently partitioned tables and the ungated-volume load-test hook. The current check covers the original three named tables and blocking indexes, not the current DDL estate.
3. **K trigger surface (D45/D46):** no check covers page watches, subscription-owned routing rules, debounced delta-carrying dispatch, idempotent subscribers, the four authored-page notification channels, declaration lint, or the one-way E → compiled → authored acyclicity invariant (`k_layers_design.md` §5).
4. **K evaluation (D22 pattern applied by D45):** no check requires planted writer-completeness canaries, sampled citation-faithfulness audits, and evidence-change→recompile staleness latency (`k_layers_design.md` §7). `eval_golden_sets_d22` covers ER, retrieval, Selection, grounding, and contradiction only.
5. **K two-band/runtime boundary:** no check requires deterministic fact-sheet rendering, fact-sheet-only pages, stock-harness writer sandbox/no-internet/read-only memory, archived writer transcripts, or driver-only output acceptance (`k_layers_design.md` §§5 and 7). Some pieces are touched by citations and execution classes, but the binding shape is not accepted end-to-end.
6. **Hard-forget in K:** `ops_deletion_cascade_grains` covers normal K refresh and generic source-payload scrubbing, but not the required git-history rewrite/squash and backup treatment for compiled pages that ever cited forgotten evidence, nor authored-page redaction duty (`k_layers_design.md` §10).
7. **Orchestration topology:** no check requires one queue per deployment/stage/lane, steady-state vs backfill separation, version-filter backfill seeding, lane-specific budgets, E3 `(document, entity)` batching, front-loaded reads/batched writes, or pgBouncer in the representative load test (`orchestration_design.md` §§2–5). The current ops checks cover idempotency/DLQ, budgets, classes, and family separation, not this binding runtime design.
8. **D51 skill acceptance:** `ret_filesystem_first_mounts_skill` checks that the skill exists and names its curriculum, but not the binding S58 cold-harness acceptance test required by `retrieval_design.md` §§8 and 11.
9. **D22 continuous ER health:** `eval_golden_sets_d22` covers golden pairs and versioned metrics but not the continuous cluster-size, singleton, unresolved-mention, merge-acceptance, and alias-growth health metrics in `registries_design.md` §10.

These are implementation-observable and should not be dismissed as pure rationale or naming decisions.

## 5. Mechanics and README accuracy

### 5.1 File/YAML mechanics

- Exactly **69** `.yaml` files exist.
- All 69 parse as YAML.
- All have `schema_version: 1` and `type: harness_judge`.
- All 69 IDs are unique.
- Every ID exactly matches its filename stem.
- All 69 contain the same explicit source-precedence paragraph.
- The README area counts are exact: E0 10, E1 2, E2 9, E3 5, registries/ER/eval 5, K 4, projections 8, retrieval 10, ops 8, code/boundary 8.

### 5.2 Tag consistency

Tags are syntactically well-formed, but they are not fully consistent with the README promise that D-tags support decision-filtered runs.

Six D-tags have no literal citation anywhere in their file:

- `e1_chunks_whole_blocks_no_overlap`: `D57`
- `e2_selection_recall_envelope`: `D22`
- `ops_execution_classes_bound`: `D33`
- `p1_lance_estate_rebuildable`: `D7`
- `registry_scale_partitioning_d23`: `D17`
- `ret_envelope_grain_discipline`: `D41`

Conversely, these conditions explicitly invoke material decisions that are absent from their tags:

- `boundary_extension_points_no_bypass_d60`: D24, D61
- `e0_converter_router_versioned`: D7
- `e0_postgres_holds_no_bodies`: D57
- `e2_context_bundle_two_calls`: D58, D63
- `e2_grounding_layered_dual_field`: D57
- `e2_no_pre_extraction_gate`: D12, D56
- `embedding_model_port_config_d63`: D56
- `er_review_queue_cli`: D21
- `k_planner_writer_driver`: D54
- `ops_execution_classes_bound`: D31
- `ops_idempotency_dlq`: D45
- `ret_claims_never_answer_now`: D43
- `ret_envelope_negative_taxonomy`: D43

Not every cross-reference needs a tag, but these are asserted in scored conditions, so filtering by those decisions currently misses checks that can fail on them. Either make tags exhaustive for scoreable D-invariants or narrow the README claim to “primary decision tags.”

### 5.3 README claims

Accurate:

- 69-check inventory and every per-area count.
- One YAML per check, conjunctive scoring, absence-is-failure, and the common precedence paragraph.
- The four Round 1 factual fixes are present.
- The nine named Round 1 additions exist.

Inaccurate or overstated:

1. **“Every check therefore reads design-first ... as ‘the binding source’.”** False for the five unflipped requirements-first sentences and contradicted by the four non-design binding designations.
2. **“The current set incorporates [the Round 1] review.”** Not in full: the D23 check omitted the Round 1 review's representative load-test hook, and its table scope did not follow the current schema.
3. **“Inventory ... Binding sources covered.”** The counts are right, but the source lists are not exhaustive despite the heading. Examples: the E3 row omits D64; E2 omits tagged D7/D22/D43/D53; projections omit tagged D62; retrieval omits tagged D43/D60/D61; ops omits tagged D25/D45/D50; code/boundary omits tagged D24. Either make the column exhaustive or label it “primary binding decisions.”
4. **“Exhaustive ... D1–D64.”** Premature while D64 has no scoreable condition and the binding coverage gaps in §4.2 remain.

## Bottom line

The suite's file mechanics and the Round 1 four factual repairs are good. The remaining risk is semantic: source precedence is advertised more strongly than it is implemented, and several checks still encode decision prose, reviewer-suggested enforcement mechanisms, or shorthand that the current design explicitly refines. Repair the MUST-FIX items before using these checks as a binary acceptance gate; otherwise a conforming implementation can fail on provider calls, K writer parallelism, borderline grounding audits, reviewer agents, retry configuration, correct schema enums, or harmless internal module layout, while a pre-D64 ontology and incomplete D23 estate can pass.
