# Example check patterns

Gallery of real-world eval-banana check patterns. Copy and adapt.

## Table of contents

- Deterministic: file existence and content
- Deterministic: JSON schema validation
- Deterministic: no forbidden tokens in source
- Deterministic: counting records
- Harness judge: README quality
- Harness judge: tone / professionalism
- Harness judge: factual consistency
- Harness judge: multi-file comparison

## Deterministic: file existence and content

```yaml
schema_version: 1
id: changelog_exists_and_nonempty
type: deterministic
description: CHANGELOG.md exists and is at least 200 chars.
script: |
  import sys
  from pathlib import Path

  ctx_path = Path(sys.argv[1])
  import json
  ctx = json.loads(ctx_path.read_text())
  changelog = Path(ctx["project_root"]) / "CHANGELOG.md"
  if not changelog.exists():
      print(f"missing: CHANGELOG.md", file=sys.stderr)
      sys.exit(1)
  content = changelog.read_text(encoding="utf-8")
  if len(content) < 200:
      print(f"only {len(content)} chars", file=sys.stderr)
      sys.exit(1)
```

## Deterministic: JSON schema validation

```yaml
schema_version: 1
id: output_matches_schema
type: deterministic
description: output.json has required top-level keys and correct types.
script: |
  import json, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  data = json.loads((Path(ctx["project_root"]) / "output.json").read_text())

  required = {"id": str, "created_at": str, "items": list}
  for key, expected_type in required.items():
      if key not in data:
          print(f"missing key: {key}", file=sys.stderr)
          sys.exit(1)
      if not isinstance(data[key], expected_type):
          print(f"{key} should be {expected_type.__name__}", file=sys.stderr)
          sys.exit(1)
  if not data["items"]:
      print("items is empty", file=sys.stderr)
      sys.exit(1)
```

## Deterministic: no forbidden tokens in source

```yaml
schema_version: 1
id: no_print_statements_in_src
type: deterministic
description: No print() calls in src/ (should use logging).
script: |
  import json, re, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  src_dir = Path(ctx["project_root"]) / "src"
  pattern = re.compile(r"\bprint\(")
  offenders = []
  for py_file in src_dir.rglob("*.py"):
      text = py_file.read_text(encoding="utf-8")
      for line_no, line in enumerate(text.splitlines(), 1):
          if line.strip().startswith("#"):
              continue
          if pattern.search(line):
              offenders.append(f"{py_file}:{line_no}")
  if offenders:
      print("\n".join(offenders[:10]), file=sys.stderr)
      sys.exit(1)
```

## Deterministic: counting records

```yaml
schema_version: 1
id: users_csv_has_enough_rows
type: deterministic
description: users.csv has at least 100 rows (excluding header).
script: |
  import csv, json, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  path = Path(ctx["project_root"]) / "data" / "users.csv"
  with path.open() as f:
      reader = csv.reader(f)
      next(reader, None)  # Skip header
      row_count = sum(1 for _ in reader)
  if row_count < 100:
      print(f"only {row_count} rows", file=sys.stderr)
      sys.exit(1)
```

## Harness judge: README quality

```yaml
schema_version: 1
id: readme_has_quickstart
type: harness_judge
description: README contains a quickstart that a new user can follow in under 5 minutes.
instructions: |
  Read README.md. Look for a "Quick start" or "Getting started" section.
  Score 1 ONLY if it contains: (1) an install command, (2) a minimum
  config step if required, and (3) at least one example command to run.
  Score 0 if any of these are missing or unclear.
```

## Harness judge: tone / professionalism

```yaml
schema_version: 1
id: error_messages_are_helpful
type: harness_judge
description: Error messages in errors.log are helpful and professional.
instructions: |
  Read errors.log. Score 1 if the error messages: (a) explain what
  went wrong in plain language, (b) suggest what to do next, and (c) do
  NOT expose stack traces or internal paths to end users. Score 0 if
  any message is cryptic, blames the user, or leaks internals.
```

## Harness judge: factual consistency

```yaml
schema_version: 1
id: summary_matches_source
type: harness_judge
description: The generated summary accurately reflects the source data.
instructions: |
  Read summary.md and source_data.json. Compare the claims in the summary
  against the facts in the source data. Score 1 if every numeric claim,
  name, and date in the summary can be verified from the source data.
  Score 0 if ANY claim is fabricated, hallucinated, or contradicts the source.
```

## Harness judge: multi-file comparison

```yaml
schema_version: 1
id: docs_consistent_with_code
type: harness_judge
description: API docs describe the actual endpoints implemented in routes.py.
instructions: |
  Read docs/api.md and src/routes.py. For each endpoint documented in the
  API docs, check if it exists in routes.py. Score 1 if every documented
  endpoint is implemented AND every public endpoint in routes.py is
  documented. Score 0 if there is any drift between the two files.
```
