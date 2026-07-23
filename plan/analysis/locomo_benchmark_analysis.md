# WP-8.2 — LoCoMo benchmark analysis

**Date:** 2026-07-23

**Status:** approved protocol analysis; no benchmark run has been performed

**Scope:** the first external benchmark adapter, deliberately not a general benchmark
framework

## Recommendation

Implement a small repository-native LoCoMo harness around the public `MemoryClient` SDK and
report a precisely named **`RS-LoCoMo-v1 J@30`** score:

- the pinned `locomo10.json` release at LoCoMo commit
  `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`;
- local dataset SHA-256
  `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`;
- categories 1–4 only: multi-hop, temporal, open-domain, and single-hop;
- 1,540 questions for publication, with smaller committed smoke and development manifests;
- one isolated RememberStack deployment per conversation;
- one source document per conversation session;
- claim search at `k=30`;
- one frozen `openai/gpt-4o-mini` reader call per question;
- one frozen `openai/gpt-4o-mini` judge call per generated answer; and
- the official deterministic LoCoMo F1 calculation as a secondary metric over the same
  answers.

The `J@30` name is intentional. A bare “LoCoMo score” would hide retrieval depth and imply a
standardization that does not exist. The run artifact must retain the dataset, prompt, manifest,
model, adapter, and repository revisions so a number can be compared only to a matching
protocol.

Do not run the benchmark as part of this work package. Implement and verify parsing, rendering,
manifests, scoring, cost guards, checkpointing, and command boundaries with synthetic data only.
The real ingest, retrieval, reader, and judge stages remain behind explicit execution flags for
an owner-reviewed run.

## What LoCoMo actually contains

The [official LoCoMo repository](https://github.com/snap-research/locomo) and
[ACL 2024 paper](https://aclanthology.org/2024.acl-long.747/) define a long-conversation
benchmark built from multi-session dialogues. The selected public release contains ten
conversations. Each conversation contains:

- two named speakers;
- ordered sessions with a human-readable timestamp;
- turns carrying `speaker`, `dia_id`, and `text`;
- optional image URL, generated image caption, and image-search query fields; and
- questions carrying a gold answer, evidence dialog IDs, and a numeric category.

A read-only audit of the exact pinned file produced:

| Property | Pinned value |
|---|---:|
| Conversations | 10 |
| Sessions | 272 |
| Dialogue turns | 5,882 |
| Turns with image-related derived fields | 1,226 |
| All questions | 1,986 |
| Category 1 — multi-hop | 282 |
| Category 2 — temporal | 321 |
| Category 3 — open-domain | 96 |
| Category 4 — single-hop | 841 |
| Category 5 — adversarial | 446 |
| Retained categories 1–4 | **1,540** |

The dataset is [CC BY-NC 4.0](https://github.com/snap-research/locomo/blob/main/LICENSE.txt).
It must not be vendored into this Apache-2.0 repository. A user supplies a local copy and the
harness checks its hash before doing anything else. The non-commercial restriction needs an
owner/legal assessment before a commercial benchmark use; code implementation does not waive
that obligation.

### Dataset irregularities that must stay visible

Six evidence entries in the pinned release are not one exact `D<number>:<number>` dialog ID.
Examples include combined strings such as `D8:6; D9:17`, whitespace-separated IDs, and a typo
such as `D:11:26`. A scorer must not silently invent corrected ground truth.

The v1 harness can still report a clearly labelled **coarse session-recall diagnostic**:
extract syntactically valid dialog IDs, reduce them to session IDs, and compare them with the
sessions of retrieved claims. It must report coverage and malformed evidence count beside the
metric. Exact turn Recall@k is not reported because the public claim-search result does not carry
a stable LoCoMo turn locator. Adding benchmark-specific turn IDs to the core retrieval contract
would be scope creep.

## Why published LoCoMo numbers are not one standard

LoCoMo supplies data and deterministic QA scoring, but the conversational-memory “J score” used
by vendors comes from later evaluation harnesses. Important protocol choices vary:

- included categories;
- dataset revision and subset;
- ingestion unit and whether memories are split by speaker;
- retrieval depth;
- answer model and prompt;
- judge model, prompt, temperature, and repetition count;
- whether evidence is shown to the reader or judge;
- whether failures remain in the denominator; and
- whether the score is deterministic F1, LLM-judge accuracy, or an aggregate.

The [Mem0 paper](https://arxiv.org/abs/2504.19413) established the recognizable
categories-1–4 J-score lineage and reported Mem0, Mem0g, and contextual competitor results with
F1, BLEU-1, and an LLM judge. Its appendix uses a concise memory-answering prompt and a generous
correct/wrong judge. An
[open reproduction](https://github.com/memodb-io/memobase/tree/358c16bbc6d687937d79bc2f984a11c3be8da901/docs/experiments/locomo-benchmark)
exposes that prompt lineage and a default retrieval depth of 30.

That historical open harness applies `top_k=30` separately to each speaker store and concatenates
the results, so it may send roughly 60 memories to the reader. `RS-LoCoMo-v1 J@30` retrieves 30
claims total from one unified deployment. The identical number therefore does not mean an
identical context budget. The lineage harness also reports a simple overlap F1 distinct from the
official stemmed, category-aware LoCoMo F1 used here; those F1 numbers must not be compared
directly.

The current [Mem0 memory-benchmarks repository](https://github.com/mem0ai/memory-benchmarks)
uses materially different defaults: newer models, multiple top-k settings, an automatically
downloaded moving dataset, and a much longer, benchmark-specific permissive judge prompt. Its
headline is useful context, but not a matched comparator for the historical paper protocol or
for `RS-LoCoMo-v1`.

Therefore:

1. Use the historical concise prompt lineage, not the current vendor-tuned prompt.
2. Pin every protocol input and publish raw per-question records.
3. Call the result `RS-LoCoMo-v1 J@30`, not “the standard LoCoMo score.”
4. Put mismatched vendor-reported numbers in a contextual table only.
5. Reproduce baselines under this exact harness in WP-8.3 before making matched claims.

The LoCoMo paper's prose list order and the numeric category IDs used by the released JSON and
official `evaluation.py` are easy to conflate. `RS-LoCoMo-v1` always reports the dataset/scorer
IDs: 1 multi-hop, 2 temporal, 3 open-domain, and 4 single-hop.

## Protocol choices

### Retained questions and tiers

Category 5 is excluded, matching the widely reported memory QA setup and WP-8.1. Failures,
timeouts, parse errors, missing answers, and missing judge results remain in the denominator as
zero.

| Tier | Questions | Use |
|---|---:|---|
| Smoke | 8 from `conv-26`, two from every retained category | Contract/debug only; never a headline |
| Development | 200, exactly 20 from each conversation and stratified by available category | Bounded iteration |
| Publication | all 1,540 category 1–4 questions | Deliberate headline run |

LoCoMo has no native QA identifier. The adapter assigns stable positional IDs of the form
`conv-26/qa/0000` against the pinned bytes. All selected IDs are committed in manifests, and
their expected count and hash are checked before execution. Selection never changes after
scores are observed.

### Ingestion mapping

Use **one Markdown document per session**, not one document per conversation and not one
document per turn.

Each turn is rendered as its own paragraph:

```text
[D1:3 | 1:56 pm on 8 May, 2023] Caroline: ...
```

When present, `blip_caption` and `query` follow the turn with explicit labels such as
`Dataset-provided derived image caption`. The image URL is metadata, not fetched. The source is
always transparent about generated visual text; it never presents a caption as a human-authored
message.

The session document choice is the smallest faithful mapping:

- it preserves session timestamps and dialog IDs;
- 272 documents are materially cheaper than 5,882 turn documents;
- turns remain distinct blocks for the normal RememberStack chunker;
- it exercises the public document-ingestion boundary; and
- it avoids a benchmark-only chunking path.

Source lineage is immutable:

```text
source_kind = "locomo"
source_ref = "<dataset-commit>/<sample-id>/<session-id>"
versioning_mode = "snapshot"
source_version_ref = "<dataset-commit>"
```

The dataset gives no timezone, so `source_modified_at` is omitted rather than falsely declaring
UTC. The literal session timestamp remains in every turn.

### Conversation isolation

All ten conversations must not share one deployment. `MemoryClient.search_claims()` scopes to a
deployment and currently has no document/source filter. A combined corpus could retrieve another
conversation's answer and inflate or corrupt the score.

The simplest honest boundary is:

```text
clean isolated deployment for one conversation
  -> ingest that conversation's sessions
  -> answer its selected questions
  -> retain local artifacts
  -> move to the next isolated deployment
```

The harness does not delete Docker volumes, databases, or cloud resources. Destructive lifecycle
ownership remains with the operator. Execution commands require an explicit sample-specific
isolation acknowledgement and record it, but cannot prove an external deployment is clean
through the current public API.

### Retrieval and answer generation

For each question:

1. call public `search_claims(query=question, k=30)`;
2. retain rank order, claim text, source span, and provenance IDs in the raw artifact;
3. render only each returned `claim_text` as `[<rank>] <claim text>` in the frozen reader prompt;
4. call `openai/gpt-4o-mini` once with temperature zero and a strict answer schema; and
5. checkpoint before advancing to the next question.

Ground-truth answers and evidence IDs are never included in retrieval or reader context.
Retrieved claims from both speakers remain in one ranked list because RememberStack is a unified
memory backend; inventing two user stores would misrepresent it.

An empty evidence envelope, including `known_empty`, is a successful retrieval with an empty
memory list. It still receives one reader call and, if the reader returns a valid answer, one
judge call. Only transport, API, or response-validation errors are retrieval failures. The
harness does not reconstruct timestamps or dialog text from gold data: if claim extraction did
not preserve the timestamp in `claim_text`, that loss is part of the measured system behavior.

### Scoring

The primary score is the percentage of retained questions labelled `CORRECT` by one frozen
`openai/gpt-4o-mini` judge call at temperature zero. The judge sees only the question, gold
answer, and generated answer. It never sees gold evidence.

One judge pass is deliberate. The historical Mem0 paper used repeated judging to report
variance; WP-8.1 instead binds one frozen judge and a later fixed audit sample so publication
cost is bounded. The run artifact states `judge_repetitions=1`, so it is not represented as an
exact reproduction of a ten-repeat result.

The secondary F1 metric reproduces the official LoCoMo normalization, category-1 comma-split
multi-answer handling, and Porter stemming over the same answer records. It costs no additional
model calls.

Coarse session evidence recall is diagnostic only. It is not blended into J or F1.

## Calls, costs, and execution safety

For `N` selected questions after ingestion:

| Operation | Calls |
|---|---:|
| RememberStack retrieval | `N` |
| Frozen reader | at most `N` |
| Frozen judge | at most `N` |

That is 400 reader/judge calls for development and 3,080 for publication, before any retry.
RememberStack ingestion also performs model extraction and embedding; its exact call count
depends on normal chunking and extraction output and must be constrained by the deployment's
existing cost ledger rather than guessed by the harness.

The harness enforces:

- no dataset auto-download;
- exact dataset and manifest hashes;
- separate `prepare`, `ingest`, `answer`, `judge`, and `summarize` commands;
- an explicit execution acknowledgement on every API/model stage;
- a declared maximum question count before any remote call;
- declared reader and judge call limits;
- one explicit run-absolute evaluator cost ceiling over reader plus judge calls, with the shared
  persisted spend checkpointed from reported provider usage after every call;
- resume from immutable run configuration and per-question checkpoints; and
- refusal when an existing run's protocol fingerprint differs.

A provider-reported cost ceiling can stop subsequent calls but may overshoot by one call because
the charge is known only after the response. The harness ledger covers usage returned with
successfully parsed calls; a billed call that fails before usable accounting is returned is not
reconstructable. A process death after a response but before its atomic checkpoint can also cause
that call to repeat on resume. Provider/account hard limits and the deployment cost ledger are
therefore the true hard monetary boundary. The pre-run checklist must verify both.
Before each provider call the harness refuses when shared reader-plus-judge spend is already at
the run ceiling. A resumed or later stage must declare a ceiling no lower than spend already
recorded; the flag never resets the ledger or creates a per-command allowance.

`prepare` reports ingestion units (sessions, turns, and bytes), not a fabricated ingestion price.
The ingestion/build cost row required by WP-8.1 comes from the deployment cost ledger after the
run; the harness can preflight and enforce only its directly owned reader/judge calls.

## Current deployment prerequisite

The released Compose profile is intentionally a fresh-deployment skeleton. It wires API
ingestion plus `convert` and `structure`, but not the complete E1 chunk/embed, E2 extraction, and
P1 claim-index worker path required by `search_claims`.

The benchmark harness must not conceal this by:

- importing repositories and handlers directly;
- constructing a benchmark-only in-process system;
- adding a benchmark-specific query endpoint; or
- claiming an end-to-end sample passed against the released Compose profile.

The implemented adapter can target any complete RememberStack deployment through the public SDK.
Before the first run, the presumptive path is to finish and review the ordinary self-host
composition. A complete deployment from the parallel cloud project could also exercise the same
public SDK, but it must not become the only working path. Deployment completion is a pre-run
prerequisite, not hidden scope inside the LoCoMo adapter.

## Rejected expansions

- A general benchmark plugin system, dataset DSL, workflow engine, or dashboard.
- Automatic dataset download or vendoring non-commercial data.
- A new benchmark-only retrieval API or document filter.
- One deployment containing all conversations.
- One deployment created and destroyed automatically by the harness.
- Feeding gold evidence to the reader or judge.
- Adopting a current vendor's long benchmark-tuned judge as a neutral standard.
- Exact turn-recall claims without a stable returned turn locator.
- Adding LongMemEval, baselines, or Phase-8 metrics infrastructure in this first adapter.
- Wiring the full production deployment topology under the guise of benchmark setup.

## Owner review before any real run

The setup review should explicitly confirm:

1. use of the CC BY-NC dataset is appropriate for the intended run;
2. `RS-LoCoMo-v1 J@30` is the desired public protocol label;
3. `gpt-4o-mini` remains the reader and judge for comparison continuity;
4. one judge pass is acceptable;
5. the deployment used for each sample is complete and isolated;
6. deployment-side ingestion/retrieval budgets and provider-side hard limits are active;
7. smoke is run first, then development, then publication only after inspecting artifacts; and
8. no result is published without its full protocol fingerprint and limitations.
