# Codex Review of `plan/implementation_evals`

Verdict: the suite is directionally strong and covers most of the final-system invariants, but it is not yet safe as an acceptance gate. Several checks over-claim binding decisions, especially around deletion, extraction ledgers, execution classes, and relation/observation temporal semantics. Those must be fixed before these are handed to binary LLM judges, because a correct implementation could fail for obeying the actual design.

## Must Fix

1. **Fix `ops_deletion_cascade_grains`: it contradicts the deletion design.** The check says lineage deletion "cascades chunks -> claims -> evidence links"; the binding schema says normal delete keeps chunks, claims, and evidence links as audit history. `postgres_schema_design.md` section 13.1: "`claims` are NOT deleted on a normal delete"; `relation_evidence` / `observation_evidence` rows are "retained as historical links." `evidence_lifecycle_design.md` section 8 likewise says claims are "retained as history" and only hard-forget scrubs content.
2. **Fix `ops_execution_classes_bound`: condition 4 is false for E2 extraction.** D52 describes execution classes, but D31/D25 bind E2 extraction as a two-call programmatic LLM over every chunked document. That spend is volume-proportional by design. Do not require every programmatic-LLM worker to sit inside an ambiguity-only cheap-first cascade.
3. **Fix `e2_selection_ledger_replay`: it overstates what the ledger records.** D33 says "Every Selection drop ... and every decontextualization edit" is ledgered. The schema explicitly says plain keeps are not recorded; `claim_extraction_decisions` records `selection_drop`, `selection_keep_flagged`, and `decontext_edit`.
4. **Fix `e3_supersession_fact_level_bitemporal`: it overstates valid-time capping for observations.** D43's no-cap rule says measurement/fixed-period observations are never capped on valid-time; conflicting same-period figures coexist, and source-removal belief withdrawal uses `invalidated_at`.
5. **Add checks for D22 and D23.** The suite does not adequately cover the golden-set/eval plan or the registry scale/indexing rules, both of which are binding and implementation-observable.
6. **Split the biggest omnibus checks before using binary scoring.** Several checks combine schema, worker behavior, runtime config, tests, and global absence claims. A single root defect would double-fail multiple checks, and a judge will struggle to prove all paths statically.

## Factual Accuracy

### Incorrect or Over-Claimed Checks

**`ops_deletion_cascade_grains.yaml`**

Condition 2 is wrong. It asserts lineage deletion removes "spine rows" and cascades `chunks -> claims -> evidence links`. The binding design says normal deletion purges raw/artifact objects and removes the document's current contribution, but retains audit rows:

- `postgres_schema_design.md` section 13.1: deleting a lineage soft-tombstones `documents` and `document_versions`; `chunks` rows are retained; "`claims` are NOT deleted on a normal delete"; `relation_evidence` / `observation_evidence` are retained as historical links.
- `evidence_lifecycle_design.md` section 8: "Claims are retained as history ... their currency ends."

Suggested replacement:

```text
Normal deletion at version or lineage grain purges raw/artifact bytes and tombstones the lineage/version rows, ends testimony currency for affected claims, recomputes counts, and closes solely-supported facts per shape. Chunks, claims, evidence links, relations, and entities are retained as audit history unless the operation is hard-forget; hard-forget separately scrubs source-bearing payloads so forgotten content is indistinguishable from never-existed.
```

**`ops_execution_classes_bound.yaml`**

Condition 4 says all programmatic-LLM workers sit inside cheap-first cascades and spend scales with ambiguity, never volume. That is not true for the E2 extractor. D31 binds a two-call extraction over the context bundle; D25 says every document that survives chunking is fully extracted. `workers.md` calls `extract_claims` "the volume cost center."

Suggested replacement:

```text
Programmatic-LLM workers are fixed-shape, schema-constrained, transcripted, and budgeted. Resolution/adjudication workers use cheap-first cascades so LLM spend scales with ambiguity; E2 extraction is the deliberate volume-proportional exception and must remain a fixed two-call extractor, not an agent harness.
```

**`e2_selection_ledger_replay.yaml`**

Condition 1 says the ledger records "every Selection outcome." D33 only binds drops and decontextualization edits. `postgres_schema_design.md` section 8 narrows this further: the ledger records drops, low-confidence keeps, and decontextualization edits; "Plain keeps are NOT recorded (they ARE the claims row)."

Suggested replacement:

```text
An append-only, version-stamped ledger records every Selection drop, every low-confidence kept_flagged outcome, and every decontextualization edit. Plain keeps are represented by the inserted claim row and need not have separate ledger rows.
```

**`e3_supersession_fact_level_bitemporal.yaml`**

Condition 1 says supersession caps `valid_until` on "relations and observations." For observations this is only true for changing effective states. D43 states the no-cap rule: a measurement/fixed-period figure is never capped on valid-time; same-period conflicts coexist in a `contradiction_group`. D55/D54 source-removal handling invalidates measurement observations rather than capping their valid-time.

Suggested replacement:

```text
Relations and effective-state observations carry bi-temporal windows and supersession caps valid_until without touching claims. Measurement/fixed-period observations obey D43's no-cap rule: same-period conflicts coexist, and source-removal belief withdrawal uses invalidated_at rather than ending the measured period.
```

**`k_citations_binding.yaml`**

Mostly correct, but condition 1 says `knowledge_artifact_evidence` links artifacts to "evidence IDs." The actual schema allows exactly one of `claim_id`, `relation_id`, or `doc_id`. This is probably intended, but the wording should not imply a single generic evidence table or claim-only evidence. Reword to "claim, relation, or document IDs."

**`e0_origin_stamped_at_ingest.yaml`**

Condition 3 says the origin "survives on the lineage/version rows." D42 binds an immutable E0 origin stamp; the schema stores `origin` on `documents` (the lineage), not necessarily on every `document_versions` row. Reword to avoid requiring duplication:

```text
The origin is stored on the durable document lineage/input metadata and remains reachable from all versions and downstream provenance.
```

**`ops_idempotency_dlq.yaml`**

Condition 1 says every worker is keyed on a content-derived hash plus processing version. That fits per-document and chunk workers, but aggregate workers use recorded input/snapshot hashes or processing-state target/version keys. D12's spirit is idempotent, versioned rerunnability; D45 makes K `inputs_hash` the aggregate equivalent. Reword to allow content-derived keys where applicable and manifest/snapshot/input hashes for aggregate jobs.

### Mostly Accurate Checks

The following checks accurately reflect the cited decisions, with no factual issue I would block on:

- E0/E1: `e0_blockizer_owns_identity`, `e0_content_addressed_reuse`, `e0_converter_router_versioned`, `e0_lineages_versions_modes`, `e0_postgres_holds_no_bodies`, `e0_raw_immutable_id_addressed`, `e0_structure_contract_unconditional`, `e1_chunks_whole_blocks_no_overlap`, `e1_multigranularity_retrieval`.
- E2/E3, apart from the noted ledger and temporal wording: `e2_asserted_validity_immutable`, `e2_claims_immutable_append_only`, `e2_context_bundle_two_calls`, `e2_grounding_layered_dual_field`, `e2_no_pre_extraction_gate`, `e2_selection_recall_envelope`, `e2_stance_kept_as_observation`, `e2_testimony_currency_counting`, `e3_blocking_cheap_first_cascade`, `e3_observations_untyped_adjudicated`, `e3_predicate_registry_governed`, `e3_relations_evidence_collapse`.
- Registries/K/P/retrieval/boundary, with judgeability caveats below: `er_*`, `k_*`, `p*`, `ret_*`, `boundary_*`, `code_config_via_pydantic_settings`.

## Coverage Gaps

The suite is broad, but several binding decisions have no direct check and deserve one.

**D1 / D46: split source of truth**

Suggested id: `source_of_truth_split_d1_d46`

Assert:

- Postgres is authoritative for E0-E3 and deterministic/projection control state.
- The K git repo is a source of truth for human-authored pages and curation sidecars, with its own backup/export path.
- Compiled K pages are semantically regenerable from spine evidence plus recorded compile inputs.
- Postgres stores K provenance/control rows, not K bodies as the authority.

**D16 / D50: one graph, many lenses**

Suggested id: `scope_views_share_graph_d16`

Assert:

- K2 scopes never create separate entity spaces or separate canonical graphs.
- Scope-specific graph views are registry/configured filters over the shared graph/export.
- Materialized filtered snapshots, if present, are performance/scope-view projections only, not authorities and not content-authorization boundaries.
- Different trust boundaries require separate deployments, not in-library per-scope filtering.

**D22: golden sets and evaluation plan**

Suggested id: `eval_golden_sets_d22`

Assert:

- ER has a human-adjudicated golden eval set separate from any training set, with hard positives/negatives, per-type strata, Wilson CIs, per-tier metrics, and canary reruns per `resolver_version`.
- Measurement labels are human-adjudicated; the cascade/LLM may propose pairs but cannot label its own eval truth.
- Retrieval evals track recall@k per recipe version and rerank tuning.
- Selection and contradiction/grounding evals are recorded in the eval-run/canary machinery.

**D23: registry scale and indexing**

Suggested id: `registry_scale_partitioning_d23`

Assert:

- The large append-only registry/evidence tables are partitioned per the current schema design and avoid write-amplifying indexes on hot tables.
- `entities` / `aliases` are not partitioned as hot blocking targets.
- Alias blocking has trigram and Daitch-Mokotoff indexes; T3 embeddings live in Lance; HNSW is never in OLTP Postgres.
- Relations have the required btree composites for `(subject_entity_id, predicate[, object])`.
- Representative load-test hooks exist before partition/index choices are locked.

**D36: E0 sub-worker chain and crossrefs**

Suggested id: `e0_subworker_chain_crossrefs_d36`

Assert:

- E0 remains one product layer implemented as separately idempotent, separately observable sub-workers: ingest, convert, structure, crossref.
- Each sub-worker has its own version/idempotency boundary so a config/version bump reruns only the affected sub-worker and downstream dependents.
- Crossref extraction records citations/document links as E0 metadata; PageIndex post-processing is not promoted to a top-level E layer.

**Requirements Code beyond settings**

Suggested id: `code_tooling_and_migrations`

Assert:

- Pyright, pytest, Ruff, and Alembic are configured and wired into CI/test commands.
- Schema changes are represented as Alembic migrations rather than ad hoc DDL.
- The code uses typed Python structures/enums/Literals where the requirements call for typed contracts.

## Judgeability

Several checks ask a static LLM judge to prove global runtime behavior. They should either be split or require concrete evidence artifacts such as central interfaces, tests, lints, or migration constraints.

**`boundary_library_scope_d60`**

Condition 3 is too broad: "No correctness-determining mechanism ... is stubbed out, feature-flagged off, or delegated" asks the judge to audit the entire system in one condition. Split into:

- `boundary_no_human_control_plane_d60`: no web UI, no tenancy/SSO/billing.
- `boundary_correctness_in_library_d60`: named correctness modules exist in-repo and are not cloud-only.
- `boundary_extension_points_cannot_bypass_invariants_d60`: ingestion/review/control-plane extension points still call the invariant-preserving pipeline.

**`e0_lineages_versions_modes`**

This check combines lineage identity, content-object reuse, debounce, snapshot/living semantics, living retraction, deletion, and sync-cycle barriers. Split into:

- `e0_lineage_version_schema_d55`
- `e0_living_mode_retraction_d55_d54`
- `ops_deletion_grains_d55`

**`e0_content_addressed_reuse`**

"Cost proportional to the edit" and "efficiency ladder exists" are hard to infer from code alone. Require targeted tests: unchanged content no-op, one-block edit reuses unchanged chunk claims, neighbor changes force re-extraction, and no LLM-derived field appears in `extraction_input_hash`.

**`e2_context_bundle_two_calls`**

"No dangling pronouns/references in accepted claims" is a quality guarantee, not statically provable. Reword condition 3 to judge implementation mechanics:

```text
The extraction schema/prompt requires decontextualized claims with resolved referents; deterministic validation rejects unresolved pronouns/references where detectable; no dedicated coref model or pre-pass exists.
```

**`e3_observations_untyped_adjudicated`**

Condition 4 asks the judge to decide whether fail-safe coexist is "in code" across all incomplete comparisons. Make it concrete: require an adjudication outcome enum, margin/threshold config, persisted `observation_adjudications` reason rows, and tests for ambiguous comparisons falling to coexist/new.

**`ret_envelope_contract`**

This is five acceptance suites in one: grain discipline, contradiction completeness, freshness stamps, truncation/identity echo, and negative taxonomy. Split into separate checks. A single incomplete envelope type would currently fail a very large check and obscure the defect.

**`ret_hydration_reverifies`**

"Every API/CLI/MCP result" is only judgeable if all surfaces route through one query service/hydrator. Add a condition requiring a shared hydrator boundary plus contract tests for API, CLI, and MCP paths.

**`p_projections_hold_no_authority`**

Global absence of projection-side decisions is hard to prove by reading all writes. Make it more judgeable with architectural constraints: projection builders may import read repositories and projection writers only; they may not import adjudicators, LLM clients, or mutation repositories for validity state.

**`ops_producer_checker_families`**

Runtime model-family separation is config-dependent. Require a validator that fails startup/CI if checker and producer model families match without an explicit recorded exception.

## Overlaps and Conflicts

**Direct conflict**

- `ops_deletion_cascade_grains` conflicts with `e2_claims_immutable_append_only` and `e2_testimony_currency_counting`. The former says deletion cascades through claims/evidence links; the latter checks correctly preserve claims as immutable evidence with currency ended.
- `ops_execution_classes_bound` condition 4 conflicts with `e2_context_bundle_two_calls` and D25/D31 because E2 extraction is volume-proportional, not ambiguity-only.

**Double-fail overlap**

- `boundary_library_scope_d60`, `ret_trust_boundary_no_content_auth`, and `er_review_queue_cli` all check "no web UI / no orgs/users/RBAC/SSO." Keep the boundary check high-level and let the retrieval/review checks focus on their local surfaces.
- `ret_claims_never_answer_now` overlaps with `ret_envelope_contract` condition 1. This is acceptable if kept as separate API naming/linter coverage, but do not let both fail from the same missing enum check unless that double weight is intended.
- `e2_no_pre_extraction_gate` overlaps with `e1_multigranularity_retrieval` condition 3. One should own "no pre-extraction skip"; the other should own "role scalar exists and default recipes filter retrieval-side."
- `p_projections_hold_no_authority` overlaps with `p1_lance_estate_rebuildable`, `p2_rebuild_first_snapshots`, `p2_projection_contract_views`, and `p3_corpus_fs_projection`. That is useful as a plane-level guard, but expect double failures from one missing rebuild path.
- `e2_selection_ledger_replay` overlaps with `ops_versioned_replay_from_storage`; keep the former E2-specific and make the latter a cross-stage version/replay spot check.

## Mechanics

- File count is correct: 53 YAML files, 53 checks. IDs match filenames and there are no duplicate ids.
- README inventory counts are correct by prefix.
- `p1_lance_estate_rebuildable.yaml` cites `overall_design.md section 4-5`; the actual path is `plan/designs/overall_design.md`.
- The README says the suite covers the decision log "(D1-D61)", but `decisions.md` now includes D62 and D63. If this suite is intentionally scoped to D1-D61, say so explicitly in the README. If not, add D62/D63 checks or update the inventory.
- Tags are mostly useful, but several conditions cite decisions missing from tags:
  - `er_resolution_cascade_t0_t4` condition 4 cites D20 but tags omit `D20`.
  - `e2_grounding_layered_dual_field` condition 2 cites D53 but tags omit `D53`.
  - `e3_blocking_cheap_first_cascade` condition 4 cites D43 but tags omit `D43`.
  - `e2_asserted_validity_immutable` condition 2 cites D32 but tags omit `D32`.
  - `p2_rebuild_first_snapshots` condition 4 cites D40 but tags omit `D40`.
  - `k_one_mechanism_n_scopes` condition 3 cites D54 but tags omit `D54`.
- Some section references are loose rather than broken: `e0_content_addressed_reuse` says `evidence_lifecycle_design.md section reuse`, but the heading is "Content-addressed reuse"; prefer exact section numbers/titles.

## Bottom Line

After the must-fix items, this will be a credible design-conformance suite. The most important corrections are to make deletion match the actual normal-delete vs hard-forget split, stop requiring every programmatic LLM worker to be an ambiguity-only cascade, and add D22/D23 coverage. Then split the largest checks enough that a binary judge can produce reliable, actionable failures.
