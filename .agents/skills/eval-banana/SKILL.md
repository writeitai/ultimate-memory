---
name: eval-banana
description: Guide for using eval-banana, a lightweight aspect-based evaluation framework with YAML check definitions. Use when the user is working in a project with `eval_checks/` directories, wants to write or debug YAML eval definitions, needs to score LLM outputs or workflow behavior with pass/fail checks, is running `eval-banana` / `eb` CLI commands, or is setting up eval-banana in a new project. Covers deterministic checks, harness_judge checks, auto-discovery rules, context.json contract, config precedence, and report interpretation.
---

# eval-banana

## Overview

eval-banana is a lightweight evaluation framework. Check definitions live in YAML files under `eval_checks/` directories and are auto-discovered. Each check scores 0 or 1 (pass/fail) with equal weight. Two check types cover most needs. One YAML file per check — there is no suite wrapper.

## The two check types

| Type | Use when | Mechanism |
|---|---|---|
| `deterministic` | Asserting file content, structure, or values objectively | Python script via subprocess; exit 0 = pass, non-zero = fail |
| `harness_judge` | Evaluating qualitative properties (coherence, tone, factuality) | Harness agent returns `{"score": 0\|1, "reason": "..."}` |

**Default to `deterministic`** when the condition can be checked with code — it's the cheapest, most reliable, and requires no credentials.

## Core workflow

1. **Install** (once per machine): `uv tool install git+https://github.com/writeitai/eval-banana.git`
2. **Initialize in project**: `eval-banana init` — creates `.eval-banana/config.toml`
3. **Write checks**: add `*.yaml` files to any `eval_checks/` directory (they are auto-discovered from the project root)
4. **Run**: `eval-banana run`
5. **Read the report**: look under `.eval-banana/results/<run_id>/`

## Common YAML fields

Every check file starts with these fields regardless of type:

```yaml
schema_version: 1            # Always 1. Required. No default.
id: my_check_id              # Unique across the project. Pattern: [a-zA-Z0-9_-]+
type: deterministic          # One of: deterministic, harness_judge
description: Human-readable  # Required. Non-empty.
tags: [fast, critical]       # Optional list of free-form tags.
```

Plus type-specific fields below.

## Writing a `deterministic` check

Runs a Python script via subprocess. Exit code 0 = pass, non-zero = fail. Infrastructure problems (missing script file, OS execution failure) = error.

```yaml
schema_version: 1
id: output_has_result_key
type: deterministic
description: output.json exists and contains a 'result' key.
script: |
  import json, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  project_root = Path(ctx["project_root"])
  output = project_root / "output.json"
  if not output.exists():
      sys.exit(1)
  data = json.loads(output.read_text())
  if "result" not in data:
      sys.exit(1)
```

Use `script: |` for inline Python, or `script_path: my_script.py` for an external script. The path is resolved **relative to the YAML file's directory**. Exactly one of `script` or `script_path` must be set.

### The `context.json` contract (critical!)

The script is invoked as `python <script> <context.json>`. Read `sys.argv[1]` to get the context path. It always has this exact shape:

```json
{
  "check_id": "output_has_result_key",
  "description": "output.json exists and contains a 'result' key.",
  "project_root": "/abs/path/to/project",
  "source_path": "/abs/path/to/project/eval_checks/my_check.yaml",
  "output_dir": "/abs/path/.../.eval-banana/results/<run_id>/checks/output_has_result_key-<sha256-of-exact-id>"
}
```

Key points:
- `project_root` is absolute — use it to locate any file in the project.
- The subprocess runs with `cwd = project_root`, so relative paths in the script also resolve from there.
- `output_dir` is the durable directory for evidence produced by this check.
  Its final component is the same safe stem used for result, prompt, stdout,
  and stderr artifacts: a readable label of at most 40 characters plus the
  full SHA-256 of the exact check ID. Never reconstruct it from `check_id`.

### Deterministic failure mapping

- `sys.exit(0)` or falling off the end → passed
- `sys.exit(1)` or any non-zero exit → failed
- `AssertionError` or any uncaught exception → failed (non-zero exit)
- `FileNotFoundError` on the script itself → error

## Writing a `harness_judge` check

Invokes the configured harness agent with instructions. The agent can read files on its own. It must eventually emit JSON: `{"score": 0|1, "reason": "one sentence"}`.

```yaml
schema_version: 1
id: readme_explains_install
type: harness_judge
description: README gives a new user enough info to install the package.
instructions: |
  Read README.md. Does it give a new user enough information to
  install and run the package locally (environment setup, install
  command, and how to invoke it)? Score 1 if yes, 0 if anything
  critical is missing.
```

Guidelines for good instructions:
- State the exact condition for score 1 and score 0.
- Be binary — avoid "mostly", "partially", etc.
- Reference concrete things to look for.
- Tell the agent which files to read.
- Keep it short. Long instructions confuse the judge.
- Do not ask for scores outside {0, 1} — the parser rejects anything else as `error`.

Optional fields:
- `model: gpt-5.6-sol` — override the default harness model for this one check
  (codex tiers: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`).

## Auto-discovery rules

- eval-banana walks from the project root (the directory containing `.eval-banana/`).
- It finds every directory named exactly `eval_checks/`.
- Inside each, it loads every `*.yaml` and `*.yml` file.
- Check IDs must be unique across all discovered files. Duplicates are a **fatal load error**.
- These directories are skipped by default: `.git`, `.hg`, `.svn`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`.
- Symlinked directories are not followed.

Co-locate checks with the code they verify:

```
project/
├── eval_checks/                     # Top-level checks
│   └── overall_quality.yaml
├── src/api/
│   └── eval_checks/                 # API-specific checks
│       └── response_schema.yaml
└── frontend/
    └── eval_checks/                 # Frontend E2E checks
        └── login_flow.yaml
```

## Running checks

```bash
eval-banana run                        # Run everything
eval-banana run --check-id my_check    # Run one check; relaxed validation of siblings
eval-banana run --check-dir path/      # Only scan this directory
eval-banana run --verbose              # Debug logging
eval-banana run --pass-threshold 0.8   # Override pass ratio
eval-banana list                       # Discover + print checks without running
eval-banana validate                   # Validate YAML without executing anything
eval-banana init [--force]  # Create project config
```

**`--check-id` is the debug escape hatch.** It uses relaxed validation — broken YAML in other files does NOT block a single targeted check. Use it when iterating on one check in a repo with incomplete checks elsewhere.

## Reading results

Each run writes to `.eval-banana/results/<run_id>/`:

```
<run_id>/
├── report.json                # Machine-readable, full EvalReport
├── report.md                  # Human-readable summary
└── checks/
    ├── <safe_check_id_stem>/            # Deterministic-check evidence directory
    ├── <safe_check_id_stem>.json        # Per-check CheckResult
    ├── <safe_check_id_stem>.prompt.txt  # Exact harness-judge input
    ├── <safe_check_id_stem>.stdout.txt  # Captured stdout (only if non-empty)
    └── <safe_check_id_stem>.stderr.txt  # Captured stderr (only if non-empty)
```

`<safe_check_id_stem>` is a bounded readable label plus the full SHA-256 of the
exact check ID. All artifacts for one check share it, while IDs that differ only
by case or normalization remain distinct. The evidence directory is created for
deterministic checks; the prompt file is created for harness-judge checks.

The console output shows:
- Run ID
- `points_earned/total_points` and percentage
- PASS or FAIL verdict
- Per-check list with reason (for failed) or error (for errored)

**Pass criteria**: `run_passed = (points_earned / total_points) >= pass_threshold AND errored_checks == 0`. A single erroring check means the whole run fails, even if every other check passed.

Exit code: 0 on `run_passed`, 1 otherwise. Usable directly in CI.

## When to use which check type

- **`deterministic`** — the condition is objective and testable with code:
  - "file X exists and is non-empty"
  - "the JSON has field Y"
  - "no TODO comments in src/"
  - "the CSV has N rows with these columns"

- **`harness_judge`** — the condition is subjective or needs language understanding:
  - "the error message is helpful to end users"
  - "the generated summary captures the key points"
  - "the tone is professional and friendly"
  - "the docs explain the concept clearly"

**If in doubt, prefer `deterministic`** — cheapest, most reliable, no credentials needed.

## Common gotchas

- **Forgetting `schema_version: 1`** — it has no default and omitting it is a validation error.
- **Using `script:` AND `script_path:`** — exactly one must be set, never both.
- **Putting a shell string in `command:`** — must be a list, e.g. `["pytest", "-q"]`, never `"pytest -q"`.
- **Duplicate IDs across files** — fatal. Grep for the ID before adding a new check.
- **Expecting judge checks to work without a harness** — configure `[harness] agent` or pass `--harness-agent`.
- **Assuming `cwd` is where you invoked `eval-banana`** — deterministic scripts run with `cwd = project_root`.
- **LLM judge returns prose instead of JSON** — the runner requires strict `{"score": 0|1, "reason": "..."}`. Tell the LLM to respond with JSON only.

## References

For deeper detail, read these as needed:

- **`references/yaml-schema.md`** — Every field for every check type, validation rules, and edge cases. Read when writing a check with unusual requirements or debugging a validation error.
- **`references/examples.md`** — Gallery of real-world check patterns (JSON validation, test runners, linters, LLM tone checks, UI flows). Read when looking for a template matching the current use case.
- **`references/config.md`** — Full TOML config reference, precedence rules, harness settings, and environment variable list. Read when configuring eval-banana for a new project.
