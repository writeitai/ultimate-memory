# Implementation evals — design-conformance acceptance checks

An exhaustive set of [eval-banana](https://github.com/writeitai/eval-banana) `harness_judge`
checks that verify the **final implementation honors the binding design** — the decision log
(D1–D61), the requirements, and the design docs. Each check points an LLM judge at the binding
sources and at the code, states the invariant as concrete conditions, and demands a binary
verdict.

**What these are:** acceptance checks for design conformance — "does the code do what the
design binds it to do?" **What these are not:** quality metrics. Extraction precision,
resolution P/R curves, retrieval recall@k live in the D22 golden-set eval harness (a separate,
data-driven asset); these checks verify the *machinery and its invariants exist and hold*.

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

## Inventory (53 checks)

| Area (prefix) | Checks | Binding sources covered |
|---|---|---|
| `e0_*` — documents/files | 8 | D36–D39, D42, D51 (raw mount), D54–D57 |
| `e1_*` — blocks/chunks | 2 | D57, D58, D25 |
| `e2_*` — claims/extraction | 9 | D2, D3, D19, D25, D31–D35, D41, D54, D59 |
| `e3_*` — relations/observations | 5 | D2–D5, D15, D18, D43 |
| `er_*` — entity resolution/review | 3 | D17, D20, D21, D24 |
| `k_*` — knowledge plane | 4 | D45–D47, D54 |
| `p_*`, `p1_*`, `p2_*`, `p3_*` — projections | 7 | D6–D11, D40, D44, D55 |
| `ret_*` — retrieval | 6 | D9, D41, D48–D51 |
| `ops_*` — orchestration/cross-cutting | 6 | D7, D12, D33, D52, D53, D55, requirements |
| `code_*`, `boundary_*` — conventions/scope | 3 | D60, D61, requirements §Code |

Not every decision needs its own check: withdrawn decisions (D26–D30), naming/plane decisions
(D13, D14), and pure-analysis decisions are covered implicitly or are not implementation-
observable. Where one check verifies several decisions, the tags say so.

## Inconsistencies found while authoring

Authoring these against the full corpus surfaced inconsistencies, registered in
`questions.md` §5 (the repo's fix register): the requirements' temporal-split paragraph
predates D43 (observations also carry adjudicated validity), and the requirements' E3 bullet
omits observations entirely. See `questions.md` items 30–31.

## Review

`codex_review.md` in this directory records an independent Codex review of the set (accuracy
against the designs, coverage gaps, judge-ability).
