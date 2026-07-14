# Claude prompting — distilled notes

Original-language distillation of Anthropic's official guidance, written for
this repo's loop (`claude` agents pinned to Opus 4.8; the eval-banana judge is
also Claude). Ideas are Anthropic's; the wording is ours. For the full,
current text read the sources (append `.md` for raw markdown):

- **General (all current models):** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- **Opus 4.8 (our pin):** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-4-8
- **Fable 5 / Mythos 5 (future use):** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5

Distilled 2026-07-14 — if the claude pin in `loopy_loop_config.yaml` changes
generation, re-distill from the sources.

## The one-sentence version

Be explicit about what you want and why, give the structure and evidence to
work with, define the boundaries — and don't script the *how*: current Claude
models reason better than a hand-written procedure.

## Writing the prompt

- **Explicit beats implied.** Claude follows precise instructions well and
  won't reliably infer unstated wishes. If you want above-and-beyond behavior
  ("fully featured", "go beyond the basics"), say so. Golden rule: if a
  colleague with no context would be confused by your prompt, so will Claude.
- **Give the why, not just the rule.** A motivated instruction ("never use
  ellipses — a text-to-speech engine reads your output") generalizes; a bare
  prohibition doesn't. Claude extrapolates correctly from reasons.
- **Examples steer harder than instructions.** 3–5 relevant, diverse examples
  wrapped in `<example>`/`<examples>` tags are the most reliable way to pin
  format and tone.
- **Use XML tags to separate prompt parts** (`<instructions>`, `<context>`,
  `<input>`) — unambiguous parsing, fewer instructions bleeding into data.
  A one-sentence role at the top focuses behavior.
- **Long inputs go on top, question at the bottom** (measurably better on
  20k+-token prompts), and for long-document tasks ask Claude to first quote
  the passages it will rely on — grounding through quotes cuts noise.

## Steering behavior

- **Name the action you want.** "Suggest improvements" gets suggestions;
  "change this function" gets changes. Decide whether the default should be
  act-first or advise-first and say it once, clearly.
- **Dial back the shouting.** Prompts written for older models ("CRITICAL:
  you MUST use this tool") now cause overtriggering. Plain "use this tool
  when…" is enough — current models are highly system-prompt sensitive.
- **Tell it to commit to an approach** when you see it re-litigating
  decisions mid-task: pick one, see it through, course-correct only on new
  contradicting information.
- **Ask for a self-check at the end** ("verify against the acceptance
  criteria before finishing") — cheap and reliably catches errors in code and
  math.
- **Independent tool calls run in parallel by default**; encourage it when
  latency matters, or ask for sequential execution when it doesn't.

## Agentic and long-horizon work

The strengths Anthropic emphasizes map directly onto this loop's design:

- **Externalized state over context memory.** Structured files for structured
  facts (test status as JSON), freeform notes for progress, git as the
  checkpoint log. Current models are excellent at rediscovering state from a
  fresh context — be prescriptive about what to read first on resume.
- **First session builds the scaffolding** (tests, setup scripts), later
  sessions iterate against it. Protect the tests explicitly: removing or
  editing tests to get green is unacceptable and worth saying so.
- **State the reversibility boundary.** Encourage local, reversible actions;
  require an explicit gate for destructive, hard-to-reverse, or
  outward-visible ones — and forbid destructive shortcuts around obstacles
  (`--no-verify`, discarding unfamiliar files).
- **Subagents: watch for overuse.** Recent Opus models delegate eagerly, even
  where a direct grep would do. Say when subagents are warranted (parallel,
  isolated-context work) and when to work directly.
- **Counter overengineering explicitly.** Minimal-scope guidance ("only
  changes directly requested; no speculative abstractions, no defensive code
  for impossible scenarios; the right complexity is the minimum for the
  task") measurably improves code output from recent Opus models.
- **Tests verify, they don't define.** Ask for general-purpose solutions and
  an explicit report when a test itself is wrong — otherwise Claude may
  optimize for passing the given cases.
- **No claims without looking.** "Never speculate about code you haven't
  opened; read the file before answering" is worth stating verbatim in
  review/judge prompts — it grounds answers and kills hallucinated findings.

## Opus 4.8 specifics (our `claude` pin)

- **Effort is the main lever.** `xhigh` for agentic/coding work (our pin),
  `high` minimum for anything intelligence-sensitive; below that it scopes
  work literally to what was asked. Raise effort before prompting around
  shallow reasoning.
- **It takes instructions literally** — precision is the upside; the cost is
  that scope must be explicit ("apply to every section, not just the first").
- **It spawns fewer subagents by default** than earlier Opus models; if you
  want fan-out, say when.
- **Review/judge harnesses: separate finding from filtering.** Opus 4.8
  follows severity bars faithfully — a "report only high-severity issues"
  prompt silently drops real findings. Ask for full coverage with confidence
  and severity attached, and filter in a later step. This is directly
  relevant to our eval-banana judge and review roles.
- Long interactive back-and-forth costs more tokens than a well-specified
  single turn: front-load the task, intent, and constraints.

## Fable 5 / Mythos 5 (only if the roster changes)

A different prompting regime: even less prescription (over-specified prompts
cap quality), effort levels up to `xhigh` where it self-validates before
responding, and a hard rule against asking it to echo its own reasoning in
output (triggers a refusal category). Distill the dedicated page before
adopting it in the roster; a one-off link is not enough.
