# LoCoMo benchmark adapter design

> **Status:** approved binding design for WP-8.2; the setup is implemented and may be tested with
> synthetic fixtures, but no real LoCoMo/API/model run is authorized by this document.

## 1. Scope and acceptance boundary

This design implements one adapter for the pinned LoCoMo ten-conversation dataset. It is
repository tooling that consumes the public `MemoryClient` SDK. It does not change query
semantics, own deployment lifecycle, or introduce a general benchmark framework.

Implementation acceptance before owner review is:

- the exact dataset schema and SHA are validated;
- smoke, development, and publication item manifests are committed and self-checking;
- sessions render deterministically to lineage-aware Markdown uploads;
- remote stages are visibly separated and execution-guarded;
- retrieval, reader, judge, deterministic F1, coarse session recall, failure accounting,
  checkpointing, and aggregation are implemented;
- pure and synthetic tests are green;
- no real LoCoMo file is ingested;
- no deployment query is made;
- no reader or judge model is called; and
- the released Compose limitation is documented as a pre-run prerequisite.

The WP-8.2 plan row remains `in progress` until an owner-authorized smoke run completes end to
end against a complete isolated deployment.

## 2. Location and dependencies

Keep the harness outside the shipped `rememberstack` wheel:

```text
benchmarks/
  __init__.py
  locomo/
    __init__.py
    __main__.py
    cli.py
    dataset.py
    model.py
    protocol.py
    runner.py
    manifests/
      smoke.json
      development.json
      publication.json
```

Tests remain under `src/tests/benchmarks/`. Pyright includes `benchmarks/` so the research
harness receives the same standard type checking as library code. Implementation updates
`[tool.pyright].include`, the repository lint/type commands, and CI invocations from `src/` to
`src/ benchmarks/`; otherwise placing the harness outside the wheel would silently exempt it
from the enforced checks. Pytest keeps its tests under `src/tests/` and adds the repository root
to `pythonpath` so those tests can import the unshipped top-level package.

The harness may import public SDK/model values and the existing provider port/adapter from
`rememberstack`; library code never imports `benchmarks`. This preserves the wheel's
client-first surface and avoids putting a research CLI under the stable `remember` command.

Add only the scorer dependencies needed to reproduce official F1:

```toml
[project.optional-dependencies]
benchmark = ["nltk>=3.9", "regex>=2024.11.6"]
```

No orchestration framework, dataframe library, tokenizer download, or vendor benchmark package
is added. `nltk.PorterStemmer` requires no corpus download. The development dependency group
also carries these two packages so the committed benchmark tests run in the ordinary locked CI
environment; the optional extra is the end-user install surface.

Run locally as:

```text
uv run --extra benchmark python -m benchmarks.locomo <command>
```

## 3. Fixed protocol

```text
protocol name       RS-LoCoMo-v1
dataset commit      3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376
dataset SHA-256     79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4
categories          1, 2, 3, 4
retrieval target    current testimony claims
top-k               30
reader model        openai/gpt-4o-mini
reader temperature  0
judge model         openai/gpt-4o-mini
judge temperature   0
judge repetitions   1
primary metric      judge accuracy (J@30)
secondary metric    official LoCoMo F1
diagnostic          coarse evidence-session recall and complete-session success
```

Changing any fixed value creates a different protocol name/version. CLI flags do not override
these values in v1. This removes a large configuration matrix and prevents accidental
apples-to-oranges output.

The only run selections are the committed tier and one sample ID for isolated execution.

## 4. Typed boundaries

All external JSON and all durable harness artifacts are Pydantic models with `extra="forbid"`.
The minimum types are:

### Dataset

- `LoCoMoTurn`: speaker, dialog ID, text, and optional image-derived fields.
- `LoCoMoQuestion`: stable derived ID, question, stringified gold answer, evidence tuple, and
  category `Literal[1, 2, 3, 4, 5]`.
- `LoCoMoSession`: numeric session ordinal, dialog prefix, literal timestamp, and ordered turns.
- `LoCoMoSample`: official sample ID, two speakers, ordered sessions, and ordered questions.
- `LoCoMoDataset`: the ten ordered samples plus validated aggregate counts.

The six top-level sample fields are `sample_id`, `conversation`, `qa`, `observation`,
`session_summary`, and `event_summary`. Speakers and dynamic session fields are nested inside
`conversation`: `speaker_a`, `speaker_b`, list-valued `session_<n>`, and
`session_<n>_date_time`.

The pinned file contains orphan timestamp keys for removed/non-selected sessions (for example,
timestamp ordinals beyond the 19 list-valued sessions in `conv-26`). The parser discovers
sessions from list-valued `session_<n>` fields only, requires a matching timestamp for each
discovered session, and ignores orphan timestamp keys. It rejects:

- missing session timestamps;
- duplicate sample or dialog IDs;
- a session whose turn dialog prefix disagrees with its ordinal;
- retained questions with null answers;
- unexpected categories;
- aggregate counts that differ from the pinned release; and
- any file whose bytes do not match the pinned SHA.

Gold answers are JSON strings or integers. After rejecting `None` for retained categories, the
parser canonicalizes them with `str(answer)`. Many excluded category-5 rows omit `answer` and
carry `adversarial_answer` instead; the boundary accepts that official field but never selects or
scores it.

Unused official `observation`, `session_summary`, and `event_summary` fields are accepted at the
sample boundary but never ingested. They are generated benchmark annotations and would leak
post-hoc summaries into the tested memory backend.

### Manifests and run state

- `QuestionManifest`: tier, dataset revision/hash, exact ordered IDs, count, and IDs hash.
- `RunConfiguration`: protocol constants, tier, sample, manifest hash, repository revision,
  prompt hashes, adapter version, and isolation acknowledgement.
- `PreparedDocument`: session identity, rendered content hash, filename, source metadata.
- `IngestRecord`: document identity plus the public SDK's returned lineage/version IDs.
- `RetrievedClaim`: rank and the public evidence-grain fields.
- `AnswerRecord`: question, gold answer, claims, generated answer or typed failure, timing, and
  provider usage.
- `JudgeRecord`: label or typed failure plus provider usage.
- `RunSummary`: denominators, J@30, F1, per-category results, session-recall coverage, failures,
  calls, tokens, costs, and protocol fingerprint.

Decimal monetary values serialize as strings. Times are UTC. IDs are never inferred from display
text.

## 5. Manifest construction

Stable question IDs are positional against the pinned bytes:

```text
<sample_id>/qa/<zero-padded-zero-based-index>
```

The checked-in manifests are canonical data, not generated at execution time.

- Smoke selects the first two retained questions in each category from `conv-26`, preserving
  original order in the final list.
- Development allocates exactly 20 questions per conversation. Within each conversation it
  gives every available retained category at least one position, allocates remaining positions
  by largest remainder against that conversation's retained category distribution, and takes
  the earliest items in each category. Ties resolve by category number. The final manifest is in
  dataset order.
- Publication contains every category-1–4 ID in dataset order.

A maintenance-only manifest generator may reproduce these files, but normal commands only load
and validate them. The generator refuses any dataset hash other than the fixed v1 hash.

## 6. Deterministic session rendering

For each sample, sessions sort by numeric ordinal and render as UTF-8 Markdown with LF line
endings:

```markdown
# LoCoMo conv-26 — session D1

Participants: Caroline and Melanie

Dataset timestamp: 1:56 pm on 8 May, 2023 (timezone unspecified)

[D1:1 | 1:56 pm on 8 May, 2023] Caroline: Hey Mel! ...

[D1:2 | 1:56 pm on 8 May, 2023] Melanie: ...

Dataset-provided derived image caption for D1:2: ...
Dataset-provided derived image search query for D1:2: ...
```

Rules:

- preserve official text verbatim after the fixed prefix;
- repeat the literal timestamp on every turn so independently extracted claims retain temporal
  context;
- do not fetch or ingest `img_url`;
- label caption/query fields as derived;
- ignore the `re-download` implementation flag;
- end with one newline; and
- hash the exact bytes before upload.

Uploads use `text/markdown`, snapshot versioning, fixed dataset revision, and stable session
source refs. Re-preparing the same bytes is a no-op; changed rendering changes the protocol
fingerprint.

## 7. Command/state machine

Commands are intentionally staged:

### `prepare`

```text
python -m benchmarks.locomo prepare
  --dataset /absolute/path/locomo10.json
  --tier smoke|development|publication
  --output /absolute/path/to/new-run-directory
```

Local only. It validates the data and manifest, records `git rev-parse HEAD`, writes immutable
configuration, and renders the selected samples' session documents. It refuses a non-empty output
directory.

### `ingest`

```text
python -m benchmarks.locomo ingest
  --run /absolute/path/to/run
  --sample conv-26
  --max-documents 19
  --execute
  --confirm-isolated-deployment conv-26
```

Remote and state-changing. It requires exact confirmation that the configured API points at a
clean deployment dedicated to the named sample. `--max-documents` must cover the already prepared
count before the first API call. It uploads each session through `MemoryClient.ingest()` and
atomically checkpoints each response.

Re-running is allowed only when stored content hashes and public no-op/version results remain
consistent. The command never creates, resets, or deletes a deployment.

### Readiness pause

There is no benchmark polling loop. The deployment owns asynchronous pipeline processing. The
operator verifies that all documents reached claim indexing using deployment operations, then
starts answering. The absence of a public per-version completion endpoint is stated in the
pre-run checklist.

### `answer`

```text
python -m benchmarks.locomo answer
  --run /absolute/path/to/run
  --sample conv-26
  --max-questions 8
  --max-reader-calls 8
  --max-evaluator-cost-usd 1.00
  --execute
  --confirm-index-ready conv-26
```

Remote. It validates that every prepared session has a successful ingest record. Before the first
call, the maximum question and reader-call limits must cover the remaining work. For every item it:

1. retrieves 30 claims through the public SDK;
2. maps returned document IDs to ingested session IDs for the coarse diagnostic;
3. records returned count and `dropped_by_hydration`;
4. checkpoints only transport/API/response-validation failure without calling the reader, or
   calls the reader once, including when the successful envelope contains zero claims or a
   `known_empty` negative;
5. records response/failure, latency, usage, and cumulative evaluator cost atomically.

Existing records with the same fingerprint are skipped. A failure record is terminal for that
run and remains in the denominator; an explicit new run is required to change protocol or retry
policy.

`--max-questions` is a run-absolute authorization watermark and must cover the complete prepared
tier: 8 for smoke, 200 for development, or 1,540 for publication. `--max-reader-calls` also counts
reader calls already checkpointed for earlier sample commands; it is not a fresh allowance for
the named sample.

### `judge`

```text
python -m benchmarks.locomo judge
  --run /absolute/path/to/run
  --sample conv-26
  --max-judge-calls 8
  --max-evaluator-cost-usd 2.00
  --execute
```

Remote. It judges successful generated answers once. Retrieval/reader failures receive a local
wrong result without a model call. Judge call failures are recorded as wrong. The same cumulative
evaluator cost ledger is checked after every provider response.

`--max-judge-calls` is likewise run-absolute and includes calls checkpointed for earlier samples.

`--max-evaluator-cost-usd` is a **run-absolute** ceiling over a single persisted reader-plus-judge
ledger, never a new allowance for the current command. Before a provider call, the command refuses
when recorded spend is already at the ceiling. After a successful response it adds the exact
reported `usage.cost_usd` and checkpoints, so one completed call may overshoot. A resumed or later
stage must pass a ceiling greater than or equal to spend already recorded. For example, a smoke
run may authorize at most `$1` through `answer` and then raise the total run ceiling to `$2`
through `judge`; it has not authorized `$1` independently to each stage.

The ledger accounts only usage returned with successfully parsed calls. A provider-billed call
that fails before usable accounting is returned depends on the provider/account hard limit, not
this reconstructed ledger. Atomic checkpoints prevent partial state, but the provider port has no
idempotency key: process death after a response and before its checkpoint can repeat that call on
resume. Resume skips every successfully checkpointed record.

### `summarize`

```text
python -m benchmarks.locomo summarize --run /absolute/path/to/run
```

Local only. It includes every manifest item. Missing sample files, answer records, or judge records
become explicit failures and zeros, never a reduced denominator. A smoke/development/publication
summary states its tier prominently.

## 8. Prompts and provider contract

Prompts live as the following exact named templates in `protocol.py`, with this design, source
lineage, and SHA-256 hashes in the run configuration. They are concise original adaptations of
the unified-memory (`ANSWER_PROMPT_ZEP`) and judge prompts in the
[memobase LoCoMo reproduction](https://github.com/memodb-io/memobase/tree/358c16bbc6d687937d79bc2f984a11c3be8da901/docs/experiments/locomo-benchmark),
which in turn identifies the Mem0 evaluation lineage. They are not the dual-user-bank prompt and
not a verbatim reproduction.

The exact reader template is:

```text
Answer the question using only the ranked conversation memories below.
Use memory timestamps when present. Resolve relative time references to the
corresponding date, month, or year. If memories conflict, prefer the most recent
one. Do not confuse people mentioned in a memory with the conversation speakers.
If the memories do not contain the answer, answer "Unknown".
Return only a concise answer of at most six words.

Ranked memories:
{memories}

Question: {question}
```

`memories` is the rank-ordered join of the public evidence results:

```text
[1] <claim_text>
[2] <claim_text>
...
```

For zero returned claims it is exactly `(none)`. `source_span`, session identity, document title,
gold answer, and gold evidence are retained in the raw result where applicable but are not
interpolated into the reader prompt. In particular, the harness does not restore a timestamp that
the memory pipeline failed to preserve.

The exact judge template is:

```text
Classify the generated answer to the question as CORRECT or WRONG against the
gold answer. Be generous about concise paraphrases that identify the same topic.
For time questions, accept equivalent formats or relative expressions only when
they denote the same date or time period. Extra wording does not make an otherwise
correct answer wrong. A missing, unknown, contradictory, or different answer is
WRONG.

Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}
```

The judge does not produce or store a rationale. Its strict output model is:

```text
label: Literal["CORRECT", "WRONG"]
```

The reader's strict output model is equally binding:

```text
ReaderOutput:
  answer: non-empty str
```

It has no rationale or other field. `AnswerRecord.generated_answer` is exactly
`ReaderOutput.answer`. A missing, empty, or invalid `answer` is an `invalid_response` reader
failure and stays in the denominator.

This is a disclosed `RS-LoCoMo-v1` adaptation of the generous Mem0-lineage judge, not a claim
that the prompt bytes or repetition protocol match the Mem0 paper.

The strict structured reader response is also deliberate. The historical dual-speaker lineage
prompt requested free-text step-by-step reasoning and judged that entire completion; this
protocol returns only a terse structured answer from one unified memory list. Both the different
context budget (30 unified claims rather than up to 30 memories per speaker) and output shape are
part of the protocol fingerprint and prevent direct comparison to a historical `k=30` number.

`ModelRequest` gains an optional bounded `temperature`; the OpenRouter adapter forwards it only
when present. Existing callers remain unchanged, while the benchmark binds temperature zero
instead of relying on a provider default.

Gold answers and evidence are prohibited from the reader prompt. Retrieved memories are
prohibited from the judge prompt. Tests assert both separations.

The protocol fingerprint includes SHA-256 hashes of both prompt templates and both strict JSON
schemas. Prompt rendering performs one `str.format` pass with all named fields supplied after the
memory lines are assembled. Python does not re-scan substituted values, so braces in a question
or claim remain literal. Memory lines join with one `\n` and no trailing blank line.

## 9. Scoring details

### J@30

```text
J@30 = 100 * count(CORRECT) / count(manifest questions)
```

Missing/failed answer or judge records are `WRONG`. Report overall and per category with integer
numerators and denominators.

### Official deterministic F1

Reproduce the official scorer:

- lowercase;
- remove commas and ASCII punctuation;
- remove tokens `a`, `an`, `the`, and `and`;
- normalize whitespace;
- Porter-stem whitespace tokens;
- category 3 uses the gold substring before the first semicolon;
- categories 2–4 use token F1; and
- category 1 splits both generated and gold answers on commas, scores each gold part against its
  best generated part, and averages.

A failed/missing generated answer scores zero. Report the arithmetic mean overall and per
category. Do not add BLEU-1 merely because another paper reported it; it adds no decision value
to this first harness.

### Coarse session evidence diagnostic

Find `D<number>:<number>` substrings in gold evidence fields, while separately marking any field
whose entire value is not one exact dialog ID as malformed. Reduce the valid matches and the
retrieved claim documents to session IDs. The pinned file has six malformed evidence fields.

```text
session_recall = |gold_sessions ∩ retrieved_sessions| / |gold_sessions|
complete_session_success = gold_sessions ⊆ retrieved_sessions
```

Report:

- scorable questions;
- questions with malformed/unparseable evidence;
- mean session recall;
- complete-session success; and
- the warning “session-grain diagnostic; not turn Recall@k.”

## 10. Persistence and failure behavior

Run files are canonical JSON with sorted keys. Every state update writes a temporary sibling,
flushes and fsyncs it, then replaces the destination. A crash leaves either the previous complete
file or the next complete file.

The run configuration is immutable after `prepare`. Remote commands recalculate:

- dataset file hash;
- selected manifest hash;
- rendered document hashes;
- prompt hashes;
- protocol fingerprint; and
- current repository revision.

The repository may be dirty during development, but a real run refuses a dirty worktree and a
revision different from the prepared revision.

Expected per-item remote failures are recorded by stable class (`retrieval`, `reader`,
`judge`, `accounting`, or `invalid_response`) and a bounded message. Programming errors and
interrupts stop the process rather than being converted into benchmark losses.

Secrets, authorization headers, full provider bodies, and environment values are never written.

## 11. Tests that are allowed before owner review

All tests use tiny synthetic fixtures, `httpx.MockTransport`, and the existing fake model
provider. They do not open the real pinned dataset path or network.

Required tests:

1. dataset shape, aggregate, duplicate, timestamp, and hash rejection;
2. stable IDs and manifest selection on synthetic data;
3. deterministic Markdown rendering and explicit derived-image labels;
4. no summary/observation annotation leakage;
5. prompt separation: no gold in reader and no retrieved context in judge;
6. successful zero-claim and `known_empty` retrieval each call the reader once with memories
   exactly `(none)`, consume reader-call/cost allowance, and are not retrieval failures, while
   transport/API/validation failures do not call the reader;
7. the reader uses the exact strict `ReaderOutput` schema; missing/empty answers become typed
   reader failures in the denominator;
8. official F1 examples, including category-1 comma splitting and category-3 semicolon handling;
9. malformed evidence coverage and coarse session recall;
10. explicit execution and isolation/readiness guards;
11. document/question/call/shared-run-cost limit refusal before the next remote call;
12. checkpoint/resume without duplicating checkpointed successful calls or resetting shared
    evaluator spend;
13. failures and missing records remain in the denominator;
14. protocol/prompt/schema/hash mismatch refusal;
15. SDK-only ingest/retrieval calls through mock transports; and
16. bounded `ModelRequest.temperature` forwarding without changing existing callers.

Allowed verification commands are targeted pytest, Ruff, Pyright, and import-linter. The command
help and a synthetic `prepare` may run. Real `ingest`, `answer`, and `judge` commands may not.

## 12. Pre-run checklist

The owner walkthrough must resolve these in order:

1. Confirm CC BY-NC use.
2. Inspect the checked-in protocol, prompts, and manifests.
3. Choose a complete deployment path; the released Compose skeleton is insufficient.
4. Provision one clean deployment for the first smoke conversation.
5. Set deployment ingestion/retrieval budget caps and provider account hard limits.
6. Set `REMEMBERSTACK_*` SDK and OpenRouter credentials through typed settings.
7. Run `prepare` and inspect its call/document plan.
8. Run `ingest` for `conv-26`.
9. Verify all session documents reached claim indexing outside the harness.
10. Run `answer`, inspect returned claims and failures, then run `judge`.
11. Inspect the smoke summary before authorizing development.
12. Repeat the same gate before any publication run.

## 13. Deferred work

- Complete self-host worker composition and a public per-version pipeline-status surface.
- Exact turn-level evidence recall through a generic source-locator contract.
- Matched BM25, dense-RAG, Mem0, and Graphiti adapters (WP-8.3).
- Shared latency/cost artifact machinery across benchmarks (WP-8.4).
- Capability benchmark and publication report (WP-8.5/8.6).
- More LoCoMo models, top-k sweeps, judge repetitions, or prompt variants.

These are not latent hooks in the v1 code. They are separate work packages that may reuse the
small run-manifest/result shapes only after a second real benchmark demonstrates the need.
