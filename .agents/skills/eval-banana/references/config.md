# Configuration reference

Complete reference for eval-banana configuration: TOML layout, precedence rules, environment variables, and harness_judge setup.

## Table of contents

- File locations
- Config sections
- Precedence rules
- Environment variables
- Harness setup
- Common config mistakes

## File location

Config lives at `.eval-banana/config.toml` in the project directory. It is found by walking upward from the current directory, so `eval-banana` works from any subdirectory.

```bash
eval-banana init          # Create project config
eval-banana init --force  # Overwrite existing
```

## Config sections

### `[core]` section

| Key | Default | Description |
|---|---|---|
| `output_dir` | `.eval-banana/results` | Where run artifacts are written (relative to project root) |
| `pass_threshold` | `1.0` | Minimum `points/total` ratio for the run to pass (0.0-1.0) |
| `llm_max_input_chars` | `0` (disabled) | Max characters sent to `harness_judge` per target file; 0 = no limit |

### `[harness]` section

| Key | Default | Description |
|---|---|---|
| `agent` | unset | Built-in agent name such as `codex`, `claude`, or `gemini` |
| `model` | unset | Override the template default model |
| `reasoning_effort` | unset | Override the template reasoning effort |

### `[discovery]` section

| Key | Default | Description |
|---|---|---|
| `exclude_dirs` | `[".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"]` | Directories to skip when walking for `eval_checks/` |

Setting `exclude_dirs` replaces the built-in default list entirely, it does not append.

## Precedence rules

Config values are resolved in this order (highest priority first):

1. **CLI arguments** (`--output-dir`, `--harness-model`, etc.)
2. **`EVAL_BANANA_*` environment variables**
3. **Project config** (`.eval-banana/config.toml`)
4. **Built-in defaults**

## Environment variables

| Variable | Maps to |
|---|---|
| `EVAL_BANANA_OUTPUT_DIR` | `core.output_dir` |
| `EVAL_BANANA_PASS_THRESHOLD` | `core.pass_threshold` |
| `EVAL_BANANA_LLM_MAX_INPUT_CHARS` | `core.llm_max_input_chars` |
| `EVAL_BANANA_HARNESS_AGENT` | `harness.agent` |
| `EVAL_BANANA_HARNESS_MODEL` | `harness.model` |
| `EVAL_BANANA_HARNESS_REASONING_EFFORT` | `harness.reasoning_effort` |

## Harness setup

Configure a harness agent when your project uses `harness_judge` checks.

```toml
[harness]
agent = "codex"
# codex GPT-5.6 tiers: gpt-5.6-sol (flagship, default), gpt-5.6-terra, gpt-5.6-luna
model = "gpt-5.6-sol"
reasoning_effort = "high"
```

If a project still contains a legacy `[llm]` section, eval-banana exits with a migration error instructing you to delete it and use `[harness]` / `[agents.*]`.

## Generated config template

Created by `eval-banana init` at `.eval-banana/config.toml`:

```toml
# Project-level eval-banana configuration.

[core]
output_dir = ".eval-banana/results"
pass_threshold = 1.0
llm_max_input_chars = 0

[harness]
agent = "codex"

[discovery]
exclude_dirs = [".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"]
```

## Common config mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| `pass_threshold: 80` (integer) | All runs fail | Use `pass_threshold = 0.8` (float, 0.0-1.0) |
| Relative `output_dir` resolved from wrong cwd | Results appear in unexpected locations | eval-banana always resolves from `project_root`, not `pwd` |
| Leaving a stale `[llm]` section in config | eval-banana exits before loading config | Delete `[llm]` and configure `[harness]` / `[agents.*]` instead |
| Replacing `exclude_dirs` with an incomplete list | `.git`, `.venv` get scanned | Lists replace, not merge — include all default entries |
