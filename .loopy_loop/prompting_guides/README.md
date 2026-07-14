# Provider prompting guides — vendored snapshots

Official model-prompting guidance from the providers whose models this repo's
loopy-loop workflows spawn, vendored verbatim so agents can read them offline
at stable repo-root-relative paths.

| File | Covers | Use when composing prompts for |
|---|---|---|
| [openai/gpt-5.6-prompting-guidance.md](openai/gpt-5.6-prompting-guidance.md) | GPT-5.6 family (sol/terra/luna) | the harness coordinator itself, `codex` agents, child-session goals (their coordinator is GPT-5.6) |
| [anthropic/claude-prompting-best-practices.md](anthropic/claude-prompting-best-practices.md) | All current Claude models (Opus 4.8, Sonnet, …) | `claude` agents, eval-banana `harness_judge` check instructions (the judge is Claude) |
| [anthropic/prompting-claude-fable-5.md](anthropic/prompting-claude-fable-5.md) | Claude Fable 5 / Mythos 5 specifics | any future Fable/Mythos usage (not currently in the agent roster) |

There is no vendored guide for Antigravity/Gemini (`agy`): no equivalent
official prompting document exists for the agy CLI at snapshot time.

## Usage discipline

- **Consult at prompt-composition moments, not every iteration.** These are
  reference material for when a workflow WRITES prompts (spawned-agent
  prompts, child goals, judge instructions) or when output quality looks off —
  reading ~1,500 lines per iteration would burn context for nothing.
- **These are snapshots and go stale silently.** Each file's header carries
  its source URL and retrieval date; the providers' pages are the truth.
  Re-fetch (append `.md` to the URL) and update via a normal PR when a new
  model generation lands in `loopy_loop_config.yaml`.
- **Vendor docs, not repo rules.** If a guide contradicts this repo's binding
  rules (CLAUDE.md, the system-prompt extension), the repo rules win.
