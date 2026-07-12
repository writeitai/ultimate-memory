# Implementation evals — design-conformance acceptance checks

An exhaustive set of [eval-banana](https://github.com/writeitai/eval-banana) `harness_judge`
checks that verify the **final implementation honors the binding design** — the decision log
(**D1–D64**), the requirements, and the design docs. Each check points an LLM judge at the
binding sources and at the code, states the invariant as concrete conditions, and demands a
binary verdict.

**What these are:** acceptance checks for design conformance — "does the code do what the
design binds it to do?" **What these are not:** quality metrics. Extraction precision,
resolution P/R curves, retrieval recall@k live in the D22 golden-set eval harness (a separate,
data-driven asset — itself covered here by `eval_golden_sets_d22`); these checks verify the
*machinery and its invariants exist and hold*.

## Running

eval-banana auto-discovers the `eval_checks/` directory here. From the repo root:

```bash
uvx eval-banana run --harness-agent claude   # or codex / gemini / opencode …
```

Two conventions when running:

- **Judge family (D53).** The checks judge code largely produced by one model family; run the
  judge harness on a **different family** than the primary implementation producer, per the
  producer/checker separation decision.
- **Absence is failure.** These are acceptance checks for the *complete* system: a check whose
  subsystem is not yet implemented scores 0 by design. Until the roadmap phases land, a partial
  score is expected — the set is the finish line, not a progress bar. Filter by `tags` to run
  the subset matching a delivered phase.

## Conventions in the checks

- Every check is `type: harness_judge`, one YAML file per check, self-contained (the judge sees
  only `description` + `instructions` — never this README), and cites its binding sources
  (decision numbers + design docs) so the judge reads the ground truth first.
- Conditions are conjunctive: score 1 only if **every** listed condition demonstrably holds,
  with file paths cited in the reason.
- `tags` carry the area and the decision numbers, for filtered runs
  (e.g. everything tagged `D43`, or all of `e2`).
- Where an invariant is a *deliberate exception* (e.g. E2 extraction is volume-proportional by
  D25 while adjudication is ambiguity-scaled by D4), the check says so explicitly, so a judge
  cannot fail a correct implementation for obeying the design.
- **Decisions for coverage, designs for truth.** The decision log is an append-only record
  whose entries are refined and withdrawn by later ones — it serves as the *coverage index*
  (which binding decisions have checks; the D-numbers in tags and conditions are the repo's
  *names* for invariants, used by the design docs themselves), while the design docs are the
  binding statement of the *current* system. Every check therefore **reads design-first**
  (its Read instruction leads with the design doc or requirements section as "the binding
  source"; the decision entries are cited for rationale and refinement history) **and carries
  an explicit source-precedence rule** in its instructions: if cited sources appear to
  disagree, the design docs (including `postgres_schema_design.md`) are controlling, decision
  entries are read with their refinement/withdrawal annotations, and the judge reports the
  discrepancy instead of failing an implementation that follows the current design. (This is
  the repo's own claims-vs-facts epistemology applied to its documentation: the log is
  testimony; the designs are the adjudicated current belief.)

## Inventory (69 checks)

| Area | Checks | Binding sources covered |
|---|---|---|
| E0 documents/files (`e0_*`) | 10 | D36–D39, D42, D51, D54–D57 |
| E1 blocks/chunks (`e1_*`) | 2 | D57, D58 |
| E2 claims/extraction (`e2_*`) | 9 | D2, D3, D19, D25, D31–D35, D41, D54, D59, D63 |
| E3 relations/observations (`e3_*`) | 5 | D2–D5, D15, D18, D43, D55 |
| Registries/ER + eval (`er_*`, `registry_*`, `eval_*`) | 5 | D17, D20–D24 |
| K plane (`k_*`) | 4 | D45–D47, D54 |
| Projections (`p_*`, `p1_*`, `p2_*`, `p3_*`, `embedding_*`) | 8 | D6–D11, D40, D44, D55, D61, D63 |
| Retrieval (`ret_*`) | 10 | D9, D41, D48–D51 |
| Ops/cross-cutting (`ops_*`, `source_of_truth_*`, `scope_views_*`) | 8 | D1, D7, D12, D16, D33, D46, D52–D56, D62 |
| Code & boundary (`code_*`, `boundary_*`, `delivery_*`) | 8 | D60–D62, requirements §Code |

Not every decision needs its own check: withdrawn decisions (D26–D30), naming/plane decisions
(D13, D14), and pure-analysis decisions are covered implicitly or are not implementation-
observable. Where one check verifies several decisions, the tags say so.

## Review

`codex_review.md` records an independent Codex (gpt-5.5) review of the initial 53-check set.
**The current set incorporates that review**: its four factual must-fixes (deletion retention
semantics, the E2 volume-proportional exception, ledger scope, the observations no-cap rule),
the judgeability rewrites and splits (the boundary and envelope omnibus checks, lineage/living
split), the mechanics fixes (tags, cite paths), and nine added checks closing its coverage gaps
(D1/D46, D16, D22, D23, D36, code tooling, D62 ×2, D63).

## Inconsistencies found while authoring

Authoring these against the full corpus surfaced inconsistencies, registered in
`questions.md` §5 (the repo's fix register): the requirements' temporal-split paragraph
predates D43/D49 (observations also carry adjudicated validity), and the requirements' E3
bullet omits observations entirely. See `questions.md` items 30–31.
