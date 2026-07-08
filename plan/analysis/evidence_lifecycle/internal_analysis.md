# Evidence Lifecycle — Re-extraction Inflation and Document Versioning (Internal Analysis)

Two problems that look separate and turn out to be one: **(A)** re-running a better extractor
inflates `evidence_count`, the system's headline confidence signal (review finding F3); **(B)**
the system has no model for a *document that changes* — a Google Drive file watched hourly,
edited daily — even though watched sources are a primary ingestion mode for every target
deployment. This analysis works both problems to their root, shows they share one mechanism
(the **evidence basis** of a document changes, and derived state must reconcile), identifies
where their semantics genuinely differ, and recommends a design. A parallel independent
analysis (Codex) lives in `external_agents/codex.md`; a SYNTHESIS follows if the two diverge.

> **Reading this cold.** A **claim** is an immutable record of what a source asserted (E2). A
> **relation**/**observation** is an adjudicated fact the system believes (E3), linked to its
> supporting claims via evidence rows; `evidence_count` caches how many claims support a fact
> and feeds belief gating (K3), retrieval reranking (D9), and adjudication confidence. A
> document's **content_hash** (sha256 of raw bytes) is its identity and idempotency key (D12/
> D37); the **extractor version** stamps which prompt/model generation produced each claim
> (D33). "Re-extraction" = running a new extractor generation over an already-ingested
> document; today it mints new claim IDs for the same sentences.

---

## 1. Problem A anatomy — what re-extraction actually corrupts

Walk the mechanics. Document D, extractor v1, yields claim c1 ("Alice is VP at Acme") → E3
links it: `relation_evidence(r_alice_acme, c1)`, `evidence_count = 1`. Extractor v2 ships
(better Selection, better decontextualization — the whole point of versioning); D re-extracts;
the same sentence yields c2 — a **new claim_id** (claims are immutable and append-only; there
is no update path, correctly). E3's novelty gate sees the same fact → outcome **evidence** →
`relation_evidence(r_alice_acme, c2)` inserts. Now `evidence_count = 2` for one sentence in
one document. Every signal downstream of the count is now wrong:

| Corrupted signal | How |
|---|---|
| `relations.evidence_count` / `contradict_count` | doubles per extractor generation |
| `observations.evidence_count` | same mechanism via `observation_evidence` |
| K3 belief gating (D47: `evidence_count ≥ N`) | thresholds met by generation-churn, not corroboration |
| Retrieval reranking (D9 evidence-count boost) | stale-generation duplication outranks genuine corroboration |
| Adjudicator confidence (D4/D43 cascades consult evidence weight) | biased toward long-lived (= most re-extracted) facts |
| P1 claim search | near-identical claims returned once per generation (`claims_verbatim` degrades) |
| K page rule candidates (D45: claims-via-mentions) | candidate sets and `uncited_count` inflate per generation |
| D42's future independence math | "independent external evidence" needs a denominator that isn't generation count |

Two aggravators make this worse than a slow leak. First, **the reprocessing lanes make
re-extraction routine** (orchestration design, PR #29): version-bump reprocessing is a designed,
recurring operation, not a rare event. Second, **the inflation is not uniform**: only documents
that get re-extracted inflate, so counts stop being comparable *across* facts — the signal
doesn't just grow, it loses meaning as a ranking key.

Note also the *intra-generation* cousin: one document asserting the same fact in three
paragraphs yields three claims → `evidence_count = 3` today. That is arguably intended
("corpus redundancy collapses into evidence counts") — but it conflates *within-source
emphasis* with *cross-source corroboration*, and D42 already recognizes that the real signal
is independent sources. Any fix should decide this deliberately rather than inherit it.

## 2. Problem B anatomy — the missing model for a changing document

The scenario: a connector watches Google Drive; every hour it lists changes; an edited file
must be ingested "as the latest version." Today's design answers only the degenerate cases:

- **Identical bytes** → `content_hash` no-op (idempotency, D12/D25). Solved.
- **Changed bytes** → a *new* `content_hash`, and the schema's `UNIQUE(deployment,
  content_hash)` admits it as… what? There is no concept connecting it to the previous upload.
  Either it becomes an unrelated new document (wrong: every derived layer now double-counts the
  unchanged 95% of its content — the versioning problem *is* the inflation problem at document
  grain), or nothing is defined at all.

Interestingly, the E0 storage layout already *anticipates* versions without saying so: the raw
path is `gs://…-raw/<doc_id>/<content_hash>/original.<ext>` — one `doc_id`, multiple hashes
under it. The design gestured at lineage and never bound it.

Four sub-problems have to be answered:

**B1 — identity across versions.** What makes two uploads "the same document"? Bytes cannot
(they differ — that's the premise). The only workable identity is **connector-native**: the
Drive file ID, the IMAP message ID's thread, the file path in a synced folder, the URL. Call it
`(source, source_ref)`. This is the *document-side* analogue of what D20 called
"internal/domain authoritative IDs" and deferred for *entities* — for documents it cannot be
deferred, because without it every edit is a full new document. Renames/moves are metadata
changes (the `source_ref` — e.g. a Drive file ID — is stable across them); a genuinely new
`source_ref` is a new lineage, even if the content is similar.

**B2 — the version model.** A **document lineage** (stable `doc_id`, the `source_ref`, a
pointer to the current version) plus append-only **versions** (content_hash, version number,
source-modified time, ingested_at, superseded_at). One row per lineage in `documents` with a
`document_versions` history beats one-document-row-per-version: `doc_id` stays the stable
anchor that chunks, claims, P3 paths (F6: paths must not churn), K citations, and crossrefs
point at, while versions carry the byte-level history. This matches the existing raw-path
layout exactly.

**B3 — semantics of the change.** This is the heart, and it splits three ways:

- **Unchanged content** (the common case for an hourly watcher — most of an edited document is
  identical): must cost nothing and change nothing. Not re-extracted, not re-counted, not
  re-embedded. (§4 shows the mechanism.)
- **Changed/added content**: this is **new testimony** — the source now asserts something it
  didn't before. It must flow through E2/E3 *normally*: new claims (with `asserted_at` = the
  version's source-modified time), normalization, and — where the new assertion conflicts with
  an old one — ordinary **supersession** (D3/D4/D43). A Drive roster page edited from
  "headcount 500" to "headcount 600" is *exactly* the Doc B → Doc C case in the observations
  design, arriving through one lineage instead of two documents. Nothing new is needed here;
  that is the machinery working as designed.
- **Removed content**: the hard case. Version 2 no longer contains the paragraph that
  supported a fact. **Absence is not retraction** — documents get restructured, summarized,
  split — so auto-invalidating relations whose supporting text disappeared would be the
  supersession-skip disaster in reverse. But *ignoring* removal is also wrong for a class of
  sources: a wiki roster page that dropped a name is asserting something by the removal. The
  honest resolution is that **this is a property of the source, not of the system**: a
  connector declares each lineage's `versioning_mode` —
  - `snapshot` (default, fail-safe): every version is independent testimony *of its time*;
    old-version claims remain current testimony forever (like two dated filings); removal
    means nothing by itself.
  - `living`: the current version is the source's *standing statement* (rosters, config pages,
    team wikis). Claims present only in superseded versions lose **testimony currency** (§3)
    — they stop counting toward current belief and stop surfacing as current evidence, while
    remaining immutable history. Even then, removal only *withdraws support*; it never
    *asserts negation* — facts whose current support drops to zero get flagged/reviewed (or
    invalidated as "support withdrawn" where policy says so), never silently flipped false.

**B4 — efficiency.** An hourly watcher over an actively-edited corpus must not pay
per-version costs proportional to document size. The watch loop itself is cheap (Drive's
changes API + hash comparison → unchanged files are no-ops before any pipeline work). The
expensive part is what happens on a real change — addressed by chunk-grain reuse (§4). One
more knob: **ingest debouncing** — a document being actively edited (5 saves in an hour)
should coalesce to one ingested version per stability window (only ingest when the file has
been quiet for N minutes), which the connector implements with the same debounce discipline
plane K uses (D12).

## 3. The unification — and where the two problems genuinely differ

Both problems are the same event at the bookkeeping level: **the evidence basis of a document
changed, and derived state must reconcile.** Define a lineage's **extraction basis** as the
pair `(content_hash of current version, extractor_version)`. Problem A changes the second
coordinate; problem B changes the first. In both cases, the claims produced from the *old*
basis stand in some altered relation to the claims from the new basis — and today the system
has no vocabulary for that relation at all, which is exactly why both problems corrupt the
same counters.

But the *semantics* of the two coordinate-changes differ, and conflating them would be a
design error:

| | Re-extraction (extractor bump) | New version (content change) |
|---|---|---|
| what the new claims are | a **re-transcription** of the *same* testimony — the source said nothing new | **new testimony** — the source's statement changed |
| old claims become | **redundant copies** (mechanically non-current; no adjudication involved) | still-valid *historical* testimony (`asserted_at` of their version) |
| conflicts handled by | nothing to adjudicate — same testimony | ordinary E3 supersession/contradiction |
| the fix's nature | bookkeeping (currency + counting) | semantics (lineage + testimony time + mode) |

So: **one reconciliation mechanism, two rule-sets riding it.** That's the design.

### Testimony currency

Introduce one derived, mechanical notion: a claim is **current testimony** iff it belongs to
its lineage's current extraction basis *under the lineage's versioning mode*:

- re-extraction: claims from superseded `extractor_version`s of the same (version, chunk) are
  **not current** (they are re-transcribed by the new generation);
- versioning, `snapshot` mode: claims from *all* versions remain current testimony (each
  version is independent dated testimony);
- versioning, `living` mode: claims present only in superseded versions are **not current**.

Crucially, currency is **not supersession and not invalidation**: it carries no adjudication,
no validity semantics, no `invalidated_at`. It is processing bookkeeping — the same epistemic
category as "this Lance row belongs to a superseded embedding version." Claims stay immutable
in every D3 sense (text, spans, asserted validity, assertion time — untouched forever); what
changes is a *derived* answer to "is this row the system's current transcription of its
source?" Transaction-time honesty is preserved: belief-as-of-T reconstructions still see the
old generation's contribution, because currency transitions are timestamped events, not
overwrites.

### The counting rule

Redefine the cached counts once, robustly against *both* problems and the intra-document
cousin:

> `evidence_count` = **the number of distinct document lineages** whose *current-testimony*
> claims support the fact. (Likewise `contradict_count`; likewise observations.)

This makes the count mean what every consumer already assumes it means — *how many sources
corroborate this* — and makes it invariant under: re-extraction (new generation, same lineage
→ no change), version churn (an hourly-edited doc re-asserting the same fact per version →
still one lineage), and within-document repetition (three paragraphs → one lineage). The
evidence *rows* stay claim-grained (provenance is untouched — every generation's and version's
link survives for audit); only the *aggregate* changes definition. D42's future independence
math then composes cleanly: filter the same distinct-lineage count by `origin = external`.

### The reconciliation flow (shared by both problems)

When a lineage's basis changes — a new version's extraction completes, or a version-bump
re-extraction completes (never before completion: no window where old evidence is gone and new
hasn't landed):

1. **Diff evidence links** for that lineage: facts evidenced under the old basis vs the new.
2. **Currency transitions**: mark old-basis claims non-current per the mode rules above
   (a timestamped, append-only transition — replayable, D7).
3. **Recount** affected relations/observations (indexed per-fact recompute; the set of touched
   facts is exactly the lineage's evidence links — bounded and known).
4. **Zero-current-support policy**: a fact whose current support drops to zero (the new
   extraction didn't re-derive it; the living-mode version removed it) is **flagged for
   review** with the diff attached — `support_withdrawn` — and only auto-invalidated where
   deployment policy explicitly says so. Fail-safe direction: a stale-but-flagged fact beats a
   silently-vanished one; and D35's canary discipline already guards the extraction-regression
   case upstream.
5. **Emit `evidence_changed`** to the K trigger queue (D45) — pages citing affected facts go
   stale; authored pages watching them get flagged. Currency transitions are evidence changes;
   the existing trigger surface carries them without modification.

## 4. Efficiency: content-addressed chunk reuse

The lever that makes hourly watching affordable: **extraction work is keyed by chunk content,
not by document version.** The pipeline already computes section-aware chunks (E1) and already
keys idempotency on content hashes (D12); extend that one level down:

- Each chunk row carries a `chunk_content_hash` (hash of its normalized text).
- E2's idempotency key becomes `(lineage, chunk_content_hash, extractor_version)` — if a chunk
  with identical content was already extracted for this lineage under this extractor, **its
  claims are reused** (re-attached to the new version's chunk row), not re-derived. Same for
  the E1 embedding (keyed by content hash + embedding version — a re-chunked identical text
  costs nothing).
- Result: a 50-page document with a two-paragraph edit re-extracts ~2 chunks; the other ~148
  chunks' claims, embeddings, and evidence links carry forward untouched — **cost proportional
  to the edit, not the document**. No currency transitions fire for untouched chunks; no
  counts move; K pages citing unaffected facts don't even go stale.

One boundary honestly noted: chunk-boundary shifts. An edit that changes section structure can
shift chunk boundaries so that textually-unchanged content lands in differently-hashed chunks
(the classic content-defined-chunking problem). Section-aware chunking (E1 splits on PageIndex
sections) limits blast radius to the edited section, but a measurement spike should quantify
reuse rates on real edit patterns; if plain hashing under-reuses, boundary-stabilized chunking
(anchor boundaries to section IDs rather than offsets) is the next lever — an optimization
detail, not an architecture change.

## 5. Schema deltas (sketch — binding form belongs to the design doc)

- `documents` → lineage semantics: add `source`, `source_ref` (connector-native identity;
  `UNIQUE(deployment, source, source_ref)`), `current_version_id`, `versioning_mode`
  (`snapshot | living`), `version_count`. `UNIQUE(deployment, content_hash)` moves to
  `document_versions`.
- New `document_versions` (append-only): `version_id`, `doc_id`, `content_hash`, `version_no`,
  `source_modified_at` (feeds new claims' `asserted_at`), `ingested_at`, `superseded_at`,
  artifact URIs per version. Raw/artifact paths already accommodate this
  (`<doc_id>/<content_hash>/…`).
- `chunks`: add `chunk_content_hash` (+ the reuse key); chunk rows are per-version, claims
  attach per `(lineage, chunk_content_hash, extractor_version)`.
- Currency: a claim-currency ledger (append-only transitions: claim_id, from-basis, to-state,
  reason ∈ {reextracted, version_superseded}, at) + a maintained boolean/partial index for the
  hot filter (`is_current_testimony`) — the ledger is truth, the flag is cache (the D33
  pattern: transcript + derived state).
- Counts: `evidence_count` semantics change to distinct-current-lineage (recomputed by the
  reconciliation worker; the cached column and its consumers keep their names).
- Retrieval (D48–D51): claim-grain primitives/filters default to **current testimony**, with
  `include_superseded_testimony` opt-in for audit; the envelope's evidence-grain answers state
  which. `claims_as_of` continues to work over *all* testimony (it is historical by
  definition) — versions give it a real corpus to answer over ("what did the roster page
  assert in March?").
- P3/K: leaf stubs and citations point at lineage `doc_id` (stable paths — F6 alignment);
  version pinning available via `content_hash` where audit needs it.

## 6. Interactions with existing decisions

| Decision | Effect |
|---|---|
| D2 (evidence collapse) | *refined*: the count's denominator becomes distinct current lineages; the M:N link layer unchanged |
| D3 (claims immutable; supersession relation-only) | *untouched*: currency is bookkeeping, not validity; no claim is ever superseded/invalidated |
| D12/D25 (content-hash idempotency) | *extended downward*: same discipline at chunk grain; version ingest is the same key one level up |
| D33/D7 (ledgers; replay) | *followed*: currency transitions are an append-only ledger; reconciliation is replayable |
| D37 (content_hash identity) | *refined*: content_hash identifies a **version**; lineage identity is `(source, source_ref)`; raw paths already fit |
| D41 (asserted validity) | *enriched*: `asserted_at` per version gives living documents real testimony timelines |
| D42 (origin) | *composes*: independence math = distinct external lineages |
| D43 (observations) | *works as designed*: version-to-version value changes are ordinary supersession; counts follow the new rule |
| D45–D47 (K triggers) | *reused*: currency transitions emit `evidence_changed`; no new trigger kind |
| D48–D51 (retrieval) | *small additions*: current-testimony defaults + envelope disclosure |
| Deletion §13 / S55 | *composes*: delete a version (its claims' currency ends; lineage continues) vs delete a lineage (the existing cascade) |

Nothing breaks. The two real *changes* are the count's definition (D2 refinement) and document
identity (D37 refinement); everything else is additive machinery that both problems share.

## 7. Open questions and spikes

1. **Chunk-reuse rate on real edit patterns** — measure on a Drive-like corpus slice; decides
   whether boundary-stabilized chunking is needed (§4).
2. **Zero-current-support policy default** — flag-only vs auto-invalidate-with-reason per
   mode/deployment; needs the E2/E3 eval harness (questions #14) to measure false-withdrawal.
3. **`versioning_mode` assignment** — per-connector default (Drive: living? snapshot?) with
   per-lineage override; who decides, and what's the safe default (snapshot).
4. **Ingest debounce window** for actively-edited files (stability threshold before a version
   is ingested; Drive revision semantics).
5. **Recount cost** at reconciliation (bounded by lineage's evidence links — measure the hub
   case: a lineage evidencing thousands of facts).
6. **Cross-version crossrefs and PageIndex diffs** — do structure diffs between versions carry
   useful signal (e.g. section-level change detection to skip conversion of unchanged pages)?
7. **Backfill interaction** — version-bump reprocessing (PR #29 lanes) + currency transitions:
   confirm the reconciliation step slots into the lane design's completion semantics.

## 8. Recommendation (candidate decisions)

1. **D-A (counting/currency):** `evidence_count` ≡ distinct document lineages with
   current-testimony support; testimony currency as an append-only, mode-aware, mechanical
   ledger; reconciliation-on-basis-change with fail-safe zero-support flagging. (Fixes F3;
   pre-registers the D42 independence denominator.)
2. **D-B (versioning):** document lineages identified by connector-native `(source,
   source_ref)`; append-only `document_versions`; `snapshot | living` mode per lineage;
   changed content is new testimony through ordinary E2/E3; removal is support-withdrawal at
   most, never negation.
3. **D-C (efficiency):** chunk-content-addressed extraction/embedding reuse — cost of a new
   version proportional to the edit; ingest debouncing at the connector.

These three are separable decisions but should land together: A without B leaves version churn
uncounted; B without A leaves re-extraction inflating; C is what makes B affordable at
watch-cadence.
