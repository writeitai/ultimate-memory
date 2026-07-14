# Provider prompting guides — distilled notes

Distillations of the providers' official prompting guidance for the models
this repo's loopy-loop workflows spawn — the important ideas in our own words,
kept small enough to actually read at prompt-composition time. Each file links
to the hosted originals (append `.md` to any of those URLs for raw markdown);
the vendor pages remain the full, current truth.

| File | Covers | Use when composing prompts for |
|---|---|---|
| [openai/gpt-5.6-prompting-guidance.md](openai/gpt-5.6-prompting-guidance.md) | GPT-5.6 family (sol/terra/luna) | the harness coordinator itself, `codex` agents, child-session goals (their coordinator is GPT-5.6) |
| [anthropic/claude-prompting-best-practices.md](anthropic/claude-prompting-best-practices.md) | Current Claude models, with an Opus 4.8 section (**this repo's `claude` pin**) and a Fable 5 pointer | `claude` agents, eval-banana `harness_judge` check instructions (the judge is Claude) |

There is no guide for Antigravity/Gemini (`agy`): no equivalent official
prompting document exists at distillation time.

## Usage discipline

- **Consult at prompt-composition moments, not every iteration.** These are
  reference material for when a workflow WRITES prompts (spawned-agent
  prompts, child goals, judge instructions) or when output quality looks off.
- **These are distillations and date themselves.** Each file states its
  distillation date and sources. When a new model generation lands in
  `loopy_loop_config.yaml`, re-read the hosted pages and re-distill via a
  normal PR — don't just bump the pin.
- **Vendor guidance, not repo rules.** If a guide contradicts this repo's
  binding rules (CLAUDE.md, the system-prompt extension), the repo rules win.
