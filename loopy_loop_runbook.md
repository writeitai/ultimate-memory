# loopy-loop runbook — operating the implementation loop

The repo is driven by [loopy-loop](https://github.com/writeitai/loopy-loop)'s
**double loop**: a PM parent session (`pm_planner_dispatcher` — planner +
dispatcher) decomposes the roadmap into work packages; each WP runs as its own
child session (`inner_outer_eval`) that implements, evaluates, and delivers via
PR. Configuration lives in `loopy_loop_config.yaml`, the PM goal in
`loopy_loop_goal.txt`, the workflow prompts under `.loopy_loop/workflow_sets/`.
This runbook is the operator's side of the contract: how to start, watch,
resume, and stop the run.

## Install (pin!)

```bash
uv tool install "loopy-loop==0.5.0"
```

loopy-loop 0.5.0 or newer is required (session-goal rendering, child-session
recovery, `*.json` child-request scanning, failure caps, events/usage ledger),
with team-harness 0.3.1 or newer underneath (the antigravity model pin —
older versions silently ignore it; a fresh `uv tool install` resolves it,
an existing install may need `uv tool upgrade loopy-loop`).
The `eval-banana` CLI installs with it and is made visible to spawned agents
automatically. The worker delegates to agent CLIs — this run needs `codex`, `claude`, and
`agy` (Antigravity) authenticated: codex is the harness coordinator and
primary implementer, claude and antigravity serve the in-team review/research
roles (`team_harness_agents`), and claude additionally judges the eval checks
(`.eval-banana/config.toml`, D53 producer/checker separation).

## Preflight

From the repo root:

```bash
loopy status                                    # expect: no state, or a terminal previous session
eval-banana validate --cwd . --check-dir plan/implementation_evals/eval_checks
gh api repos/{owner}/{repo}/branches/main/protection --jq '.required_status_checks.contexts'
```

The last command shows the required CI contexts; the loop's merge policy relies
on green checks, so verify branch protection still matches expectations (strict
required checks, no required human review) before an unattended run.

## Start

Two processes, separate terminals, both from the repo root:

```bash
# terminal 1
loopy coordinator --host 127.0.0.1 --port 8080

# terminal 2 — exactly ONE worker
loopy worker --coordinator http://127.0.0.1:8080
```

There is exactly one worker per coordinator: a second worker is refused (HTTP
409, exit code 3) while the first is verifiably alive. The provider is `codex`,
so no API key export is needed for the loop itself (the OpenRouter variables in
the config apply only if the provider is switched to `openai_compat`).

## Monitor

```bash
loopy status            # the whole session stack: PM parent + live child, usage totals
loopy status --watch    # re-render every 2s
loopy events --follow   # the deepest active session's event stream
```

Durable artifacts live under `.loopy_loop/sessions/<session_id>/` (gitignored):
the PM session's `project_state/` (work items, finished ledger), `children/`
(each child session's full state), and per-iteration `iterations/` records.
The plan itself (WP statuses, phase evidence) is repo state and changes only
through the children's merged PRs.

## Stop — read this before you need it

```bash
loopy stop
```

`loopy stop` flags the **top-level PM session only**. A running child session
does not see the flag: it keeps iterating until it reaches a terminal state,
and only then does the resumed parent honor the stop. If you must stop a child
immediately, stop the worker process instead (Ctrl-C / kill); the coordinator
will recover the interrupted iteration on the next worker registration (see
Crash recovery). Expect a child to take long: its ceiling is the shared
`max_turns` from the config.

## Resume / crash recovery

- **Coordinator died (or machine rebooted):** restart with
  `loopy coordinator --resume`. It walks the durable parent→child session stack
  to the deepest live session — a running child continues where it was.
  Starting without `--resume` against a still-`running` state fails on purpose.
- **Worker died mid-iteration:** just start a new `loopy worker`. Registration
  performs recovery: a verifiably-alive previous worker is protected (409); a
  dead one's completed-but-unreported result is recovered from disk; otherwise
  its orphaned agent processes are drained (default policy, bounded by
  `recovery_drain_timeout_s`) before the iteration is re-dispatched. `/register`
  may legitimately block for minutes during a drain.
- **Both:** coordinator first (`--resume`), then the worker.

## When the loop stops by itself

Check `loopy status` for the stop reason:

- `goal_met` — the planner concluded the roadmap's completion criteria hold
  (including the final-closeout full eval suite). Verify via the PM session's
  `project_state/finished.md`.
- `unresolvable_error` — last-resort autonomous stop; the exact blocker is in
  the session's `control.json` reason and `current_state.md`.
- `workflow_failure_cap` / `max_turns` — a circuit breaker fired (consecutive
  harness failures of one workflow, or the turn ceiling). For a child this is
  planner-reviewable evidence; for the parent, inspect
  `loopy events` / `state.json` history for the failing workflow.

## Escalation

If the run needs human input mid-flight, write it into the ACTIVE session's
`updates_from_user.md` (the PM parent's for roadmap-level steering; a child's
for WP-level steering — find the live session id via `loopy status`). The
planner/outer workflows read that inbox every iteration and reflect it into
durable state before clearing it.
