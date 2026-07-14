# YAML schema reference

Complete field reference for eval-banana check definitions. Each check file defines a single check — there is no suite wrapper.

## Table of contents

- Common fields (all check types)
- `deterministic` fields
- `harness_judge` fields
- Validation rules
- Error messages and what they mean

## Common fields

| Field | Type | Required | Constraints | Notes |
|---|---|---|---|---|
| `schema_version` | int | **Yes** | Must equal `1` | No default. Omitting → validation error. |
| `id` | string | **Yes** | Pattern `^[a-zA-Z0-9_-]+$`, non-empty after stripping | Must be unique across ALL discovered check files |
| `type` | string | **Yes** | One of `deterministic`, `harness_judge` | Discriminator for the Pydantic union |
| `description` | string | **Yes** | Non-empty after stripping | Human-readable, shown in reports |
| `tags` | list[string] | No | — | Free-form metadata. Not yet used for filtering but allowed. |

`extra="forbid"` is enabled — any unknown field fails validation.

## `deterministic` check

Type-specific fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `script` | string | **One of** | Inline Python source code (use `script: \|` block scalar) |
| `script_path` | string | **One of** | Path to external Python file, **relative to the YAML file's directory** |

**Exactly one** of `script` or `script_path` must be set. Setting both is a validation error. Setting neither is a validation error.

### Subprocess contract

- Command: `python <script> <context_path>`
- `cwd`: `project_root`
- Environment: full parent env (no additional injection)

### `context.json` shape

Passed as `sys.argv[1]`. Always this exact shape:

```json
{
  "check_id": "string",
  "description": "string",
  "project_root": "/abs/path",
  "source_path": "/abs/path/to/check.yaml",
  "output_dir": "/abs/path/to/per-check-output-dir"
}
```

### Result mapping

| Outcome | Status | Score |
|---|---|---|
| Exit 0 | `passed` | 1 |
| Exit non-zero (includes `AssertionError`, uncaught exceptions, `sys.exit(1)`) | `failed` | 0 |
| `FileNotFoundError` on script itself, `OSError` | `error` | 0 |

`stdout` and `stderr` are captured on the `CheckResult` and written to `<output_dir>/checks/<check_id>.stdout.txt` / `.stderr.txt` (only if non-empty).

## `harness_judge` check

Type-specific fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `instructions` | string | **Yes** | Non-empty. The evaluation prompt sent to the harness agent. |
| `model` | string | No | Override `harness.model` for this check only |

### Prompt shape

The runner builds a prompt with:
1. A fixed instruction asking for `{"score": 0|1, "reason": "..."}` JSON output
2. The `description` as context
3. The `instructions` as the evaluation criterion

The harness agent can read project files on its own — tell it which files to check in the `instructions` field.

### Required LLM response format

```json
{"score": 0, "reason": "one sentence explanation"}
```

- `score` MUST be exactly `0` or `1`. Any other value → `error` result.
- `reason` is optional but recommended. If present, must be a string.
- Response must be valid JSON. Prose or malformed JSON → `error` result.

### Result mapping

| Outcome | Status | Score |
|---|---|---|
| Valid JSON, `score == 1` | `passed` | 1 |
| Valid JSON, `score == 0` | `failed` | 0 |
| Malformed JSON or score outside {0,1} | `error` | 0 |
| Harness subprocess spawn/timeout error | `error` | 0 |

## Validation rules summary

The loader raises a `ValueError` naming the file path for any of these:

- YAML parse error
- Top-level YAML is not a dict
- Any required field missing
- `id` doesn't match `^[a-zA-Z0-9_-]+$`
- `description` empty or whitespace-only
- Unknown top-level field (blocked by `extra="forbid"`)
- `type` not one of the allowed values
- `script` AND `script_path` both set, or neither set (deterministic)
- `instructions` empty (harness_judge)

The runner raises `SystemExit` for:
- Duplicate check IDs across files (shows both file paths)
- No checks found after discovery + filtering
- `--check-id` matches multiple files (also shows paths)

## Common validation errors

| Error text | Cause | Fix |
|---|---|---|
| `Field required [type=missing]` on `schema_version` | Forgot the field | Add `schema_version: 1` |
| `Extra inputs are not permitted` | Unknown field | Remove or check spelling |
| `script and script_path are mutually exclusive` | Both set | Remove one |
| `deterministic check must have script or script_path` | Neither set | Add one |
| `instructions must be non-empty` | Empty or missing on harness_judge | Add instructions |
| `id does not match pattern` | Invalid chars (dots, spaces, etc.) | Use only `[a-zA-Z0-9_-]` |
| `Duplicate check id 'X' found in: ...` | Same id in 2+ files | Rename one |
