# RS-LoCoMo-v1 setup

This directory implements the reviewed `RS-LoCoMo-v1 J@30` protocol. It does not contain the
LoCoMo data and does not auto-download it. The data is CC BY-NC 4.0; confirm the intended use
before obtaining it from the
[official repository](https://github.com/snap-research/locomo/tree/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data).

Install the repository and the two deterministic-scorer dependencies:

```bash
uv sync --extra benchmark
```

The safe first command is local:

```bash
uv run --extra benchmark python -m benchmarks.locomo prepare \
  --dataset /absolute/path/locomo10.json \
  --tier smoke \
  --output .benchmark-runs/locomo-smoke
```

`prepare` checks the exact pinned SHA, validates the committed eight-question smoke manifest,
renders session Markdown, and writes a call/document plan. It does not contact RememberStack or
an evaluator.

Do not proceed to `ingest`, `answer`, or `judge` until the owner walkthrough in
[`locomo_benchmark_design.md`](../../plan/designs/locomo_benchmark_design.md#12-pre-run-checklist).
Those stages require `--execute` plus exact isolation/readiness acknowledgements and explicit
document, question, call, and shared evaluator-cost ceilings.

Question and call ceilings are run-absolute, not allowances for one sample invocation.
`--max-questions` must therefore cover the complete prepared tier (8 for smoke, 200 for
development, or 1,540 for publication), while reader and judge call ceilings include calls
already checkpointed for earlier samples. The evaluator-cost ceiling likewise covers the shared
reader-plus-judge ledger for the entire run.

The local ledger records provider usage attached to successfully parsed, checkpointed calls.
Provider-billed calls that fail before usable accounting is returned are not reconstructable, and
a process death after a response but before its atomic checkpoint may repeat that one call.
Provider/account hard limits are therefore the hard monetary boundary; the harness ceilings are
additional fail-closed operational guards.

The released Compose profile is not yet a valid target: it wires only `convert` and `structure`,
not the complete claim-indexing path. Use of a complete isolated deployment is a pre-run
prerequisite, not something this harness silently constructs.
