# loopy-loop runbook — operating the UGM implementation program

UGM runs loopy-loop's recoverable **double loop**. A parent program session
uses `pm_planner_dispatcher`: planner selects and accepts roadmap items,
dispatcher publishes typed child assignments, and planner decides program
completion. Each high-level phase/milestone outcome runs as an
`inner_outer_eval` child whose outer role owns decomposition, acceptance,
handoff, and child completion. Child eval roles publish optional observations;
they do not close the goal. One loopy worker advances the deepest active layer;
team-harness may spawn dynamic attempt-local delegates inside it.

Configuration is `loopy_loop_config.yaml`, the parent goal is
`loopy_loop_goal.txt`, and versioned role contracts/prompts live below
`.loopy_loop/workflow_sets/`.

## Required released tools

Install the exact supported registry releases, not editable checkouts:

```bash
uv tool install --force --reinstall --no-sources --no-config "eval-banana==0.3.6"
uv tool install --force --reinstall --no-sources --no-config "team-harness==0.5.4"
uv tool install --force --reinstall --no-sources --no-config \
  --with "eval-banana==0.3.6" --with "team-harness==0.5.4" \
  "loopy-loop==0.8.0"
```

The third command is mandatory even when the first two tools are current:
`loopy-loop` has its own isolated Python environment and otherwise continues
using the dependency versions embedded in that environment.

The Python tool and the `loopy-loop` Agent Skill are installed separately.
Before launch or resume, refresh the shared skill from the v0.8.0 release and
verify that it byte-matches `skills/loopy-loop/SKILL.md` at that tag. Do not run
with an older skill that lacks protocol-v3 layer state, workflow/scheduler
rosters, advisory evals, or orchestrator-owned completion.

`codex`, `claude`, and `agy` must already be authenticated. Every loopy
workflow coordinator uses `gpt-5.6-sol`. Direct delegates use the configured
four-tier capability roster. Eval roles choose a proportionate enabled bundle
and normally prefer a different model family from the producer when useful.

## Preflight

From the repository root:

```bash
loopy status
eval-banana validate --no-project-config --cwd . \
  --check-dir plan/implementation_evals/eval_checks --harness-agent claude
gh api "repos/$(gh repo view --json nameWithOwner --jq .nameWithOwner)/branches/main/protection" \
  --jq '.required_status_checks.contexts'
```

For a new program, `loopy status` should report no state or a terminal archived
session. A running session requires `--resume`; never start a second fresh
coordinator over it. Confirm strict required CI and no ordinary human-review
gate before unattended execution.

## Fresh start

Use two terminals in the repo root:

```bash
# terminal 1
loopy coordinator --host 127.0.0.1 --port 8080

# terminal 2 — exactly one worker
loopy worker --coordinator http://127.0.0.1:8080
```

A second live worker is refused. The first fresh item is autonomous
phase planning: planner reconciles the roadmap with evidence already on current
`main`, then selects a coherent phase/milestone outcome. It does not dispatch a
one-command reconciliation child or pre-decompose the child into exact leaves.

## Observe the run

```bash
loopy status --watch
loopy events --follow
loopy traces list
loopy traces inspect MANIFEST_OR_ID
```

Compact durable state is under `.loopy_loop/sessions/<root>/`: scoped goals,
assignments, project state, child requests/outcomes, parent acceptance, eval and
git/delivery receipts, control, and recovery state. Detailed prompts, harness
records, spawned-agent assignments/streams, raw eval reports, and verbose git
evidence live separately under `.loopy_loop/traces/`. Raw eval output includes
the exact `checks/<safe-check-id-stem>.prompt.txt` sent to every invoked judge;
the paired result/stdout/stderr files use that same collision-safe stem.
Session state and traces are both gitignored. State is still required for
continuity, while trace retention is independent and traces may contain
private raw data.

## Add steering without rewriting history

```bash
loopy update "concise new instruction"
loopy update --session SESSION_ID "instruction for this exact layer"
```

Without `--session`, an update routes to the deepest active layer. Updates are
append-only in `inputs/user_updates.jsonl`; do not edit or truncate the legacy
`updates_from_user.md` file.

## Stop semantics

```bash
loopy stop
```

The stop request is tree-wide. It prevents another descendant from being
dispatched and is honored at the next safe assignment boundary; current model
or harness work is not killed mid-write. Stop is an operator action, distinct
from workflow-owned `goal_met` or last-resort `unresolvable_error` control.

If the problem is a library/runtime defect and the frozen goal and workflow
contracts remain correct, **do not use `loopy stop`**. Terminate worker and
coordinator processes, fix/release/install the owning library, then resume the
same durable session. If the frozen goal/config/contract itself is wrong, stop
the tree and start a fresh session after fixing the versioned setup; active v2
or v3 identity and snapshots must not be patched in place.

## Crash or maintenance recovery

Restart the coordinator first, then one worker:

```bash
loopy coordinator --resume --host 127.0.0.1 --port 8080
loopy worker --coordinator http://127.0.0.1:8080
```

Resume walks the parent-to-child pointers to the deepest live session. Worker
registration recovers completed-but-unreported output when possible; otherwise
it drains orphaned agent processes before redispatch. Registration may take
minutes during a bounded drain. A verifiably live previous worker remains
protected from duplicate registration.

## Diagnose autonomous stops

- `goal_met`: the layer orchestrator (`outer` or parent `planner`) made a
  reasoned completion decision and published identity-bound protocol-v3
  control plus an up-to-date semantic handoff. Evals are cited evidence when
  useful, not the completion authority. Parent completion additionally expects
  all phases, final curated-inventory review, delivery evidence, and green main
  CI under the repository goal.
- `unresolvable_error`: read `control.json`, `current_state.md`, attempted
  routes, and evidence refs. It is the rare loopy-loop D5 autonomy escape hatch.
- `workflow_failure_cap` or `max_turns`: inspect `loopy events`, the failing
  attempt trace, and session history. A stopped child is evidence for planner
  re-scope/reroute; a parent cap requires runtime or workflow diagnosis.
- Protocol/control rejection: inspect `control_rejected/` and
  `protocol_failures/`; repair the role output rather than bypassing validation.

When a loopy-loop, team-harness, or eval-banana defect causes the program to go
sideways, preserve state and traces, stop the processes, repair and release the
owning package, install the new exact version, and resume. Stop and create a
fresh session only when the frozen program contract itself must change.
