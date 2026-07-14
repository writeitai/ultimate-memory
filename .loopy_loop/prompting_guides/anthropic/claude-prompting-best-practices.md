> **Condensed snapshot** of https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
> Retrieved 2026-07-14 · © Anthropic. Reformatted for readability (docs-site
> components flattened to plain markdown) and trimmed to what applies to this
> repo's CLI-based agent loop: API/SDK parameter examples, prefill migration,
> vision, document creation, LaTeX, frontend design, and generation-migration
> sections are dropped — the source page is the full original. It goes stale
> silently — re-fetch the source (append `.md` to the URL) and update via PR.

# Prompting best practices

Prompt engineering techniques for Claude's latest models, covering clarity,
examples, XML structuring, thinking, and agentic systems.

This is the reference for prompt engineering with Claude's latest models,
including Claude Fable 5, Claude Mythos 5, Claude Opus 4.8, Claude Sonnet 5,
and Claude Haiku 4.5. Model-specific guidance lives on dedicated pages — two
are vendored beside this file:

* [prompting-claude-fable-5.md](prompting-claude-fable-5.md) — Claude Fable 5 / Mythos 5
* [prompting-claude-opus-4-8.md](prompting-claude-opus-4-8.md) — Claude Opus 4.8 (this repo's `claude` agent pin)

Everything below applies to all current Claude models.

## General principles

### Be clear and direct

Claude responds well to clear, explicit instructions. Being specific about your
desired output can help enhance results. If you want "above and beyond"
behavior, explicitly request it rather than relying on the model to infer this
from vague prompts.

Think of Claude as a brilliant but new employee who lacks context on your norms
and workflows. The more precisely you explain what you want, the better the
result.

**Golden rule:** Show your prompt to a colleague with minimal context on the
task and ask them to follow it. If they'd be confused, Claude will be too.

* Be specific about the desired output format and constraints.
* Provide instructions as sequential steps using numbered lists or bullet
  points when the order or completeness of steps matters.

Example — less effective: `Create an analytics dashboard`. More effective:
`Create an analytics dashboard. Include as many relevant features and
interactions as possible. Go beyond the basics to create a fully-featured
implementation.`

### Add context to improve performance

Providing context or motivation behind your instructions, such as explaining to
Claude why such behavior is important, can help Claude better understand your
goals and deliver more targeted responses.

Example — less effective: `NEVER use ellipses`. More effective: `Your response
will be read aloud by a text-to-speech engine, so never use ellipses since the
text-to-speech engine will not know how to pronounce them.`

Claude is smart enough to generalize from the explanation.

### Use examples effectively

Examples are one of the most reliable ways to steer Claude's output format,
tone, and structure. A few well-crafted examples (known as few-shot or
multishot prompting) improve accuracy and consistency.

When adding examples, make them:

* **Relevant:** Mirror your actual use case closely.
* **Diverse:** Cover edge cases and vary enough that Claude doesn't pick up
  unintended patterns.
* **Structured:** Wrap examples in `<example>` tags (multiple examples in
  `<examples>` tags) so Claude can distinguish them from instructions.

Include 3–5 examples for best results. You can also ask Claude to evaluate your
examples for relevance and diversity, or to generate additional ones based on
your initial set.

### Structure prompts with XML tags

XML tags help Claude parse complex prompts unambiguously, especially when your
prompt mixes instructions, context, examples, and variable inputs. Wrapping
each type of content in its own tag (e.g. `<instructions>`, `<context>`,
`<input>`) reduces misinterpretation.

Best practices:

* Use consistent, descriptive tag names across your prompts.
* Nest tags when content has a natural hierarchy (documents inside
  `<documents>`, each inside `<document index="n">`).

### Give Claude a role

Setting a role in the system prompt focuses Claude's behavior and tone for your
use case. Even a single sentence makes a difference:

```text
You are a helpful coding assistant specializing in Python.
```

### Long context prompting

When working with large documents or data-rich inputs (20k+ tokens), structure
your prompt carefully to get the best results:

* **Put longform data at the top:** Place your long documents and inputs near
  the top of your prompt, above your query, instructions, and examples. This
  improves performance across all models. Queries at the end can improve
  response quality by up to 30% in tests, especially with complex,
  multi-document inputs.

* **Structure document content and metadata with XML tags:** When using
  multiple documents, wrap each document in `<document>` tags with
  `<document_content>` and `<source>` (and other metadata) subtags for clarity:

  ```xml
  <documents>
    <document index="1">
      <source>annual_report_2023.pdf</source>
      <document_content>
        {{ANNUAL_REPORT}}
      </document_content>
    </document>
    <document index="2">
      <source>competitor_analysis_q2.xlsx</source>
      <document_content>
        {{COMPETITOR_ANALYSIS}}
      </document_content>
    </document>
  </documents>

  Analyze the annual report and competitor analysis. Identify strategic
  advantages and recommend Q3 focus areas.
  ```

* **Ground responses in quotes:** For long document tasks, ask Claude to quote
  relevant parts of the documents first before carrying out its task. This
  helps Claude cut through the noise of the rest of the document's contents,
  e.g.: `Find quotes from the patient records and appointment history that are
  relevant to diagnosing the patient's reported symptoms. Place these in
  <quotes> tags. Then, based on these quotes, list all information that would
  help the doctor diagnose the patient's symptoms. Place your diagnostic
  information in <info> tags.`

## Output and formatting

### Communication style and verbosity

Claude's latest models have a more concise and natural communication style
compared to previous models:

* **More direct and grounded:** Provides fact-based progress reports rather
  than self-celebratory updates
* **More conversational:** Slightly more fluent and colloquial, less
  machine-like
* **Less verbose:** May skip detailed summaries for efficiency unless prompted
  otherwise

This means Claude may skip verbal summaries after tool calls, jumping directly
to the next action. If you prefer more visibility into its reasoning:

```text
After completing a task that involves tool use, provide a quick summary of the
work you've done.
```

### Control the format of responses

There are a few particularly effective ways to steer output formatting:

1. **Tell Claude what to do instead of what not to do**

   * Instead of: "Do not use markdown in your response"
   * Try: "Your response should be composed of smoothly flowing prose
     paragraphs."

2. **Use XML format indicators**

   * Try: "Write the prose sections of your response in
     \<smoothly\_flowing\_prose\_paragraphs> tags."

3. **Match your prompt style to the desired output**

   The formatting style used in your prompt may influence Claude's response
   style. If you are still experiencing steerability issues with output
   formatting, try matching your prompt style to your desired output style as
   closely as possible. For example, removing markdown from your prompt can
   reduce the volume of markdown in the output.

4. **Use detailed prompts for specific formatting preferences**

   For more control over markdown and formatting usage, provide explicit
   guidance:

   ````text
   <avoid_excessive_markdown_and_bullet_points>
   When writing reports, documents, technical explanations, analyses, or any
   long-form content, write in clear, flowing prose using complete paragraphs
   and sentences. Use standard paragraph breaks for organization and reserve
   markdown primarily for `inline code`, code blocks (```...```), and simple
   headings (## and ###). Avoid using **bold** and *italics*.

   DO NOT use ordered lists (1. ...) or unordered lists (*) unless: a) you're
   presenting truly discrete items where a list format is the best option, or
   b) the user explicitly requests a list or ranking

   Instead of listing items with bullets or numbers, incorporate them naturally
   into sentences. This guidance applies especially to technical writing. Using
   prose instead of excessive formatting will improve user satisfaction. NEVER
   output a series of overly short bullet points.

   Your goal is readable, flowing text that guides the reader naturally through
   ideas rather than fragmenting information into isolated points.
   </avoid_excessive_markdown_and_bullet_points>
   ````

## Tool use

### Tool usage

Claude's latest models are trained for precise instruction following and
benefit from explicit direction to use specific tools. If you say "can you
suggest some changes," Claude will sometimes provide suggestions rather than
implementing them, even if making changes might be what you intended.

For Claude to take action, be more explicit — less effective (Claude will only
suggest): `Can you suggest some changes to improve this function?`; more
effective (Claude will make the changes): `Change this function to improve its
performance.`

To make Claude more proactive about taking action by default, you can add this
to your system prompt:

```text
<default_to_action>
By default, implement changes rather than only suggesting them. If the user's
intent is unclear, infer the most useful likely action and proceed, using tools
to discover any missing details instead of guessing. Try to infer the user's
intent about whether a tool call (e.g., file edit or read) is intended or not,
and act accordingly.
</default_to_action>
```

On the other hand, if you want the model to be more hesitant by default, less
prone to jumping straight into implementations, and only take action if
requested:

```text
<do_not_act_before_instructions>
Do not jump into implementation or change files unless clearly instructed to
make changes. When the user's intent is ambiguous, default to providing
information, doing research, and providing recommendations rather than taking
action. Only proceed with edits, modifications, or implementations when the
user explicitly requests them.
</do_not_act_before_instructions>
```

Recent Opus models are more responsive to the system prompt than previous
models. If your prompts were designed to reduce undertriggering on tools or
skills, these models may now overtrigger. The fix is to dial back any
aggressive language. Where you might have said "CRITICAL: You MUST use this
tool when...", you can use more normal prompting like "Use this tool when...".

### Optimize parallel tool calling

Claude's latest models run independent tool calls in parallel: multiple
speculative searches during research, several files read at once, bash commands
executed in parallel. This behavior is steerable. While the model has a high
success rate in parallel tool calling without prompting, you can boost this to
~100% or adjust the aggression level:

```text
<use_parallel_tool_calls>
If you intend to call multiple tools and there are no dependencies between the
tool calls, make all of the independent tool calls in parallel. Prioritize
calling tools simultaneously whenever the actions can be done in parallel
rather than sequentially. For example, when reading 3 files, run 3 tool calls
in parallel to read all 3 files into context at the same time. Maximize use of
parallel tool calls where possible to increase speed and efficiency. However,
if some tool calls depend on previous calls to inform dependent values like the
parameters, do NOT call these tools in parallel and instead call them
sequentially. Never use placeholders or guess missing parameters in tool calls.
</use_parallel_tool_calls>
```

To reduce parallel execution instead: `Execute operations sequentially with
brief pauses between each step to ensure stability.`

## Thinking and reasoning

### Overthinking and excessive thoroughness

Recent models do more upfront exploration than previous ones, especially at
higher effort settings. This initial work often helps to optimize the final
results, but the model may gather extensive context or pursue multiple threads
of research without being prompted. If your prompts previously encouraged the
model to be more thorough, tune that guidance:

* **Replace blanket defaults with more targeted instructions.** Instead of
  "Default to using \[tool]," add guidance like "Use \[tool] when it would
  enhance your understanding of the problem."
* **Remove over-prompting.** Tools that undertriggered in previous models are
  likely to trigger appropriately now. Instructions like "If in doubt, use
  \[tool]" will cause overtriggering.
* **Use effort as a fallback.** If Claude continues to be overly aggressive,
  use a lower effort setting.

If the model thinks extensively in a way that inflates tokens and slows
responses, add explicit instructions to constrain its reasoning, or lower the
effort setting:

```text
When you're deciding how to approach a problem, choose an approach and commit
to it. Avoid revisiting decisions unless you encounter new information that
directly contradicts your reasoning. If you're weighing two approaches, pick
one and see it through. You can always course-correct later if the chosen
approach fails.
```

### Leverage thinking capabilities

Claude's latest models decide dynamically when and how much to think, based on
effort and query complexity. On easier queries that don't require thinking, the
model responds directly. Thinking is especially helpful for tasks involving
reflection after tool use or complex multi-step reasoning. You can guide it:

```text
After receiving tool results, carefully reflect on their quality and determine
optimal next steps before proceeding. Use your thinking to plan and iterate
based on this new information, and then take the best next action.
```

If you find the model thinking more often than you'd like, which can happen
with large or complex system prompts, add guidance to steer it:

```text
Extended thinking adds latency and should only be used when it will
meaningfully improve answer quality - typically for problems that require
multi-step reasoning. When in doubt, respond directly.
```

Further principles:

* **Prefer general instructions over prescriptive steps.** A prompt like
  "think thoroughly" often produces better reasoning than a hand-written
  step-by-step plan. Claude's reasoning frequently exceeds what a human would
  prescribe.
* **Multishot examples work with thinking.** Use `<thinking>` tags inside your
  few-shot examples to show Claude the reasoning pattern. It will generalize
  that style to its own thinking.
* **Manual chain-of-thought as a fallback.** When thinking is off, you can
  still encourage step-by-step reasoning by asking Claude to think through the
  problem. Use structured tags like `<thinking>` and `<answer>` to cleanly
  separate reasoning from the final output.
* **Ask Claude to self-check.** Append something like "Before you finish,
  verify your answer against \[test criteria]." This catches errors reliably,
  especially for coding and math.

## Agentic systems

### Long-horizon reasoning and state tracking

Claude's latest models handle long-horizon reasoning tasks with strong state
tracking. Claude maintains orientation across extended sessions by focusing on
incremental progress, making steady advances on a few things at a time rather
than attempting everything at once. This capability especially emerges over
multiple context windows or task iterations, where Claude can work on a complex
task, save the state, and continue with a fresh context window.

If you are using Claude in an agent harness that compacts context or allows
saving context to external files, consider adding this information to your
prompt so Claude can behave accordingly. Otherwise, Claude may sometimes
naturally try to wrap up work as it approaches the context limit:

```text
Your context window will be automatically compacted as it approaches its limit,
allowing you to continue working indefinitely from where you left off.
Therefore, do not stop tasks early due to token budget concerns. As you
approach your token budget limit, save your current progress and state to
memory before the context window refreshes. Always be as persistent and
autonomous as possible and complete tasks fully, even if the end of your budget
is approaching. Never artificially stop any task early regardless of the
context remaining.
```

#### Multi-context window workflows

For tasks spanning multiple context windows:

1. **Use a different prompt for the very first context window:** Use the first
   context window to set up a framework (write tests, create setup scripts),
   then use future context windows to iterate on a todo-list.

2. **Have the model write tests in a structured format:** Ask Claude to create
   tests before starting work and keep track of them in a structured format
   (e.g., `tests.json`). This leads to better long-term ability to iterate.
   Remind Claude of the importance of tests: "It is unacceptable to remove or
   edit tests because this could lead to missing or buggy functionality."

3. **Set up quality of life tools:** Encourage Claude to create setup scripts
   (e.g., `init.sh`) to gracefully start servers, run test suites, and
   linters. This prevents repeated work when continuing from a fresh context
   window.

4. **Starting fresh vs compacting:** When a context window is cleared,
   consider starting with a brand new context window rather than using
   compaction. Claude's latest models are extremely effective at discovering
   state from the local filesystem. Be prescriptive about how it should start:

   * "Call pwd; you can only read and write files in this directory."
   * "Review progress.txt, tests.json, and the git logs."
   * "Manually run through a fundamental integration test before moving on to
     implementing new features."

5. **Provide verification tools:** As the length of autonomous tasks grows,
   Claude needs to verify correctness without continuous human feedback.

6. **Encourage complete usage of context:**

   ```text
   This is a very long task, so it may be beneficial to plan out your work
   clearly. It's encouraged to spend your entire output context working on the
   task - just make sure you don't run out of context with significant
   uncommitted work. Continue working systematically until you have completed
   this task.
   ```

#### State management best practices

* **Use structured formats for state data:** When tracking structured
  information (like test results or task status), use JSON or other structured
  formats to help Claude understand schema requirements
* **Use unstructured text for progress notes:** Freeform progress notes work
  well for tracking general progress and context
* **Use git for state tracking:** Git provides a log of what's been done and
  checkpoints that can be restored. Claude's latest models perform especially
  well in using git to track state across multiple sessions.
* **Emphasize incremental progress:** Explicitly ask Claude to keep track of
  its progress and focus on incremental work

Example structured state file (`tests.json`) plus freeform progress notes
(`progress.txt`):

```json
{
  "tests": [
    { "id": 1, "name": "authentication_flow", "status": "passing" },
    { "id": 2, "name": "user_management", "status": "failing" },
    { "id": 3, "name": "api_endpoints", "status": "not_started" }
  ],
  "total": 200, "passing": 150, "failing": 25, "not_started": 25
}
```

```text
Session 3 progress:
- Fixed authentication token validation
- Updated user model to handle edge cases
- Next: investigate user_management test failures (test #2)
- Note: Do not remove tests as this could lead to missing functionality
```

### Balancing autonomy and safety

Without guidance, recent Opus models may take actions that are difficult to
reverse or affect shared systems, such as deleting files, force-pushing, or
posting to external services. If you want Claude to confirm before taking
potentially risky actions:

```text
Consider the reversibility and potential impact of your actions. You are
encouraged to take local, reversible actions like editing files or running
tests, but for actions that are hard to reverse, affect shared systems, or
could be destructive, ask the user before proceeding.

Examples of actions that warrant confirmation:
- Destructive operations: deleting files or branches, dropping database
tables, rm -rf
- Hard to reverse operations: git push --force, git reset --hard, amending
published commits
- Operations visible to others: pushing code, commenting on PRs/issues,
sending messages, modifying shared infrastructure

When encountering obstacles, do not use destructive actions as a shortcut. For
example, don't bypass safety checks (e.g. --no-verify) or discard unfamiliar
files that may be in-progress work.
```

### Research and information gathering

Claude's latest models can find and synthesize information from multiple
sources effectively. For optimal research results:

1. **Provide clear success criteria:** Define what constitutes a successful
   answer to your research question

2. **Encourage source verification:** Ask Claude to verify information across
   multiple sources

3. **For complex research tasks, use a structured approach:**

```text
Search for this information in a structured way. As you gather data, develop
several competing hypotheses. Track your confidence levels in your progress
notes to improve calibration. Regularly self-critique your approach and plan.
Update a hypothesis tree or research notes file to persist information and
provide transparency. Break down this complex research task systematically.
```

### Subagent orchestration

Claude's latest models orchestrate subagents natively, recognizing when tasks
would benefit from delegating work to specialized subagents:

1. **Ensure well-defined subagent tools:** Have subagent tools available and
   described in tool definitions
2. **Let Claude orchestrate naturally:** Claude will delegate appropriately
   without explicit instruction
3. **Watch for overuse:** Recent Opus models have a strong predilection for
   subagents and may spawn them in situations where a simpler, direct approach
   would suffice (e.g. spawning subagents for code exploration when a direct
   grep call is faster and sufficient).

If you're seeing excessive subagent use:

```text
Use subagents when tasks can run in parallel, require isolated context, or
involve independent workstreams that don't need to share state. For simple
tasks, sequential operations, single-file edits, or tasks where you need to
maintain context across steps, work directly rather than delegating.
```

### Chain complex prompts

With native thinking and subagent orchestration, Claude handles most multi-step
reasoning internally. Explicit prompt chaining (breaking a task into sequential
calls) is still useful when you need to inspect intermediate outputs or enforce
a specific pipeline structure. The most common chaining pattern is
**self-correction:** generate a draft → have Claude review it against criteria
→ have Claude refine based on the review.

### Reduce file creation in agentic coding

Claude's latest models may create new files for testing and iteration purposes,
particularly when working with code — a 'temporary scratchpad' before saving
the final output. Using temporary files can improve outcomes, particularly for
agentic coding use cases. If you'd prefer to minimize net new file creation:

```text
If you create any temporary new files, scripts, or helper files for iteration,
clean up these files by removing them at the end of the task.
```

### Overeagerness

Recent Opus models have a tendency to overengineer by creating extra files,
adding unnecessary abstractions, or building in flexibility that wasn't
requested. If you're seeing this undesired behavior:

```text
Avoid over-engineering. Only make changes that are directly requested or
clearly necessary. Keep solutions simple and focused:

- Scope: Don't add features, refactor code, or make "improvements" beyond what
was asked. A bug fix doesn't need surrounding code cleaned up. A simple feature
doesn't need extra configurability.

- Documentation: Don't add docstrings, comments, or type annotations to code
you didn't change. Only add comments where the logic isn't self-evident.

- Defensive coding: Don't add error handling, fallbacks, or validation for
scenarios that can't happen. Trust internal code and framework guarantees. Only
validate at system boundaries (user input, external APIs).

- Abstractions: Don't create helpers, utilities, or abstractions for one-time
operations. Don't design for hypothetical future requirements. The right
amount of complexity is the minimum needed for the current task.
```

### Avoid focusing on passing tests and hard-coding

Claude can sometimes focus too heavily on making tests pass at the expense of
more general solutions, or may use workarounds like helper scripts for complex
refactoring instead of using standard tools directly. To prevent this behavior
and get solutions that generalize:

```text
Please write a high-quality, general-purpose solution using the standard tools
available. Do not create helper scripts or workarounds to accomplish the task
more efficiently. Implement a solution that works correctly for all valid
inputs, not just the test cases. Do not hard-code values or create solutions
that only work for specific test inputs. Instead, implement the actual logic
that solves the problem generally.

Focus on understanding the problem requirements and implementing the correct
algorithm. Tests are there to verify correctness, not to define the solution.
Provide a principled implementation that follows best practices and software
design principles.

If the task is unreasonable or infeasible, or if any of the tests are
incorrect, please inform me rather than working around them. The solution
should be robust, maintainable, and extendable.
```

### Minimizing hallucinations in agentic coding

Claude's latest models are less prone to hallucinations and give more accurate,
grounded, intelligent answers based on the code. To encourage this behavior
even more:

```text
<investigate_before_answering>
Never speculate about code you have not opened. If the user references a
specific file, you MUST read the file before answering. Make sure to
investigate and read relevant files BEFORE answering questions about the
codebase. Never make any claims about code before investigating unless you are
certain of the correct answer - give grounded and hallucination-free answers.
</investigate_before_answering>
```

---

*Dropped relative to the source (see the URL in the header for the full
original): API/SDK request examples in nine languages, the extended-thinking →
adaptive-thinking API migration, prefilled-response migration, model
self-knowledge strings, LaTeX output, document creation, vision capabilities,
frontend design aesthetics, and the generation-migration checklist — none
apply to how this repo's loop drives Claude through the `claude` CLI.*
