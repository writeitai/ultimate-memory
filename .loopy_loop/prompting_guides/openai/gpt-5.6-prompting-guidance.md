# GPT-5.6 prompting — distilled notes

Original-language distillation of OpenAI's official guidance, written for this
repo's loop (the harness coordinator, `codex` agents, and child-session goals
all run GPT-5.6). Ideas are OpenAI's; the wording is ours. For the full,
current text read the source:
**https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6**
(append `.md` for raw markdown). Distilled 2026-07-14 — if a new GPT
generation lands in `loopy_loop_config.yaml`, re-distill from the source.

## The one-sentence version

Tell GPT-5.6 the **outcome**, the **constraints**, the **evidence it has**,
and the **bar for "done"** — then get out of its way. It suffers more from
too much prompt than too little.

## Simplify before anything else

- Fewer instructions outperform more. Repeated instructions, redundant
  examples, and leftover guidance written for older models actively degrade
  output and waste tokens (OpenAI measured double-digit eval gains and
  40–65% token reductions from leaner prompts). Prune before adding.
- Contradictions are the top failure source. Two instructions that conflict
  ("be thorough" + "keep it under 100 words"; a tool description that
  disagrees with the system prompt) produce erratic behavior. When output is
  erratic, hunt for the contradiction before adding new instructions.
- Don't tell it how to think or hand it a step-by-step script — capable
  models execute a script *literally* and cap their own quality on it.

## Outcome-first structure

State, in roughly this order:

1. **Outcome** — what exists when the task is done, not the procedure.
2. **Constraints** — hard boundaries only (what must not change, what
   conventions bind, what's out of scope).
3. **Evidence** — the files, documents, and context it should treat as given,
   and where to find more.
4. **Completion bar** — the observable conditions under which it should stop
   and report done. Without an explicit stopping condition it may stop early
   on long tasks or keep polishing past the point of value.

This is exactly the shape the dispatcher composes child goals in: WP Goal
cell, constraints from the repo rules, Reads as evidence, Acceptance as the
completion bar.

## Autonomy and approval boundaries

Say explicitly what it may do without asking and what requires an ask.
GPT-5.6 respects stated boundaries well, but unstated ones default to its own
judgment. In a fully autonomous loop like ours: name the *only* stop-worthy
conditions (destructive/monetary actions), and say everything else should be
attempted and routed around, never waited on.

## Tools

- Describe each tool by *when to use it*, not just what it does. Overlapping
  tools without routing guidance cause dithering.
- It parallelizes independent tool calls well; you rarely need to prompt for
  that. Do say when calls must be sequential.

## Grounding and claims

Require that claims be tied to evidence from the session ("point to the
file/test/output that shows it") and ask reports to cite concrete artifacts.
This measurably reduces confident invention, especially late in long runs.

## Long-running work

- Have it externalize state (progress files, todo lists, structured test
  status) rather than carrying everything in context — the same discipline
  our project_state contract enforces.
- Fresh sessions recover well from disk state; be prescriptive about what to
  read first on resume.

## Reasoning effort

Match effort to the task; don't run everything at maximum. `xhigh` is for
correctness-critical, hard work (our codex pin, deliberately). Drop to
medium/low for mechanical subtasks — quality holds, tokens drop. If output
seems shallow, raise effort before adding "think harder" prose.

## Verify before finishing

Tell it to check its work against the completion bar before reporting done —
run the tests, re-read the acceptance criteria, confirm each claim. GPT-5.6
does this well when asked and skips it when not.

## Debugging a prompt stack

Change one thing at a time and re-run the same small set of real cases. A
regression after a model/prompt/tool change is undiagnosable if several
things moved at once. Make surgical edits aimed at an identified failure
mode, not broad rewrites.
