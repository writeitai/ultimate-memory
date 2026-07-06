# Evidence Lifecycle — Document Versions, Testimony Currency, and the Counting Rule (Design)

How the system stays truthful when **the evidence basis of a document changes** — either
because a better extractor re-processes it (re-extraction) or because the source itself was
edited (a watched Google Drive file, ingested hourly). Binding design for decisions
**D54–D56**, building on D2 (evidence collapse), D3 (claims immutable; supersession
relation-only), D12/D25 (content-hash idempotency), D33/D7 (ledgers; replay), D37 (E0
storage), D41 (asserted validity), D42 (origin), D43 (observations), D45–D51 (K triggers;
retrieval envelope). Research: `plan/analysis/evidence_lifecycle/` (internal + Codex parallel
analyses + SYNTHESIS — convergent on everything here except one mechanism, §9). Numbers are
starting points to measure, not committed constants (CLAUDE.md).

> **Reading this cold (CLAUDE.md Rule 1).** A **claim** is an immutable record of what a
> source asserted (E2) — never edited, never superseded. A **relation**/**observation** is an
> adjudicated fact the system believes (E3), linked to supporting claims by evidence rows;
> **`evidence_count`** caches how much support a fact has and feeds belief gating (K3),
> retrieval reranking (D9), and adjudication. A document's **`content_hash`** (sha256 of its
> bytes) is the idempotency key (D12); the **extractor version** stamps which prompt/model
> generation produced each claim (D33). Before this design, the system had no vocabulary for
> either "this document was re-extracted by a newer generation" or "this document was edited
> at its source" — both silently inflated `evidence_count` and polluted claim search.

## 1. The problem, in one example each

**Re-extraction (problem A).** Document D, extractor v1 → claim c1 ("Alice is VP at Acme") →
`relation_evidence(r, c1)`, count = 1. Extractor v2 ships (better Selection — the whole point
of versioning); D re-extracts; the same sentence yields c2 — a *new* claim_id, because claims
are immutable and append-only (correctly). E3's novelty gate sees the same fact → outcome
*evidence* → count = 2. One sentence, one document, and the system's headline confidence
signal doubled — and doubles again per generation, *only* for re-extracted documents, so
counts also stop being comparable across facts.

**Versioning (problem B).** A connector watches Google Drive hourly. A file is edited: new
bytes, new `content_hash`. The schema had no concept connecting the new upload to the old one
— it would ingest as an unrelated document, double-counting the unchanged 95 % of its content
(the versioning problem *is* the inflation problem at document grain), and paying full
conversion + extraction per edit.

**The shared root.** Define a document's **extraction basis** = (content hash of its current
version, extractor version). Problem A changes the second coordinate; problem B changes the
first. In both cases, claims from the *old* basis stand in an altered relation to claims from
the new basis — and the system needs (1) vocabulary for that relation, (2) a counting rule
invariant under basis changes, and (3) reconciliation machinery that runs when a basis
changes. But the *semantics* differ, and the design keeps them distinct:

| | Re-extraction (extractor bump) | New version (content change) |
|---|---|---|
| the new claims are | a **re-transcription** of the *same* testimony | **new testimony** — the source's statement changed |
| the old claims become | redundant copies (mechanically non-current) | still-valid *historical* testimony, dated by their version |
| conflicts handled by | nothing — same testimony, nothing to adjudicate | ordinary E3 supersession/contradiction (D3/D4/D43) |

One mechanism, two rule-sets riding it.

## 2. Document lineages, versions, and content objects (D55)

**Three identities, three jobs:**

1. **Content object** — immutable bytes, keyed `content_hash`. The idempotency and blob-reuse
   key (D12/D37, unchanged in spirit): identical bytes are stored, converted, and paid for
   once, even if two lineages carry them (the same PDF in two Drive folders).
2. **Document lineage** — the *logical document over time*, the stable `doc_id`. Identity is
   **connector-native**: `(source_kind, source_ref)` — the Drive file ID, the message ID, the
   watched URL, the upload event. Bytes cannot identify a lineage (they change — that is the
   premise); titles and paths cannot either (renames/moves are metadata changes over a stable
   `source_ref`). A genuinely new `source_ref` is a new lineage even if the content is
   similar. Everything durable anchors on the lineage: P3 paths (the F6 stability contract),
   K citations, crossrefs, GCS path prefixes (`<doc_id>/<content_hash>/…` — the layout that
   always implied this design).
3. **Document version** — one observed immutable snapshot of a lineage, pointing at one
   content object, carrying the per-snapshot state: artifact URIs, conversion/structure
   provenance, `source_modified_at` (which feeds derived claims' `asserted_at` — testimony is
   dated by *when the source said it*, D41), and processing status. Append-only; the lineage
   holds a `current_version_id` pointer.

**Versioning mode — the semantic dial (per lineage, connector default + override):**

- **`snapshot`** *(the fail-safe default)*: every version is independent testimony *of its
  time*. Old-version claims remain current testimony forever — correct for versioned archival
  sources (quarterly reports fetched from one URL, contract amendments), where the old
  version's assertions were never withdrawn, only succeeded.
- **`living`**: the current version is the source's *standing statement* (rosters, wikis,
  config pages). Claims present only in superseded versions lose testimony currency (§3) —
  they stop counting toward current belief while remaining immutable history.

**Absence is never retraction.** In *either* mode, content missing from a new version only
ever *withdraws support* (currency closes, counts drop, review flags raise — §4); it never
asserts negation, caps a validity window, or marks a fact false. Documents get restructured,
summarized, split; a source retracts only by *asserting* a retraction — which is a claim,
adjudicated like any other. (Changed content that asserts something *different* is the easy
case: it is new testimony flowing through ordinary E2→E3, where supersession does exactly
what it was built for — a roster edited from "headcount 500" to "600" is the observations
design's worked example arriving through one lineage instead of two documents.)

**Ingest debouncing.** A file being actively edited (five saves in an hour) coalesces to one
ingested version per stability window (ingest only after N quiet minutes — the D12 debounce
discipline at the connector). A connector poll that finds an unchanged revision/etag is a
no-op before any bytes move; unchanged bytes are a `content_hash` no-op as today.

## 3. Testimony currency (D54)

One new, deliberately narrow notion: a claim is **current testimony** iff it belongs to its
lineage's current extraction basis *under the lineage's mode*:

- **re-extraction**: when generation v2 completes for a (version, chunk), that chunk's v1
  claims flip non-current (`reextracted`) — wholesale, by coordinates; no content matching;
- **`living` version supersession**: claims whose chunks are absent from the new current
  version flip non-current (`version_superseded`);
- **`snapshot`**: version succession flips nothing.

**What currency is not.** Not supersession, not invalidation, not a validity judgment — no
adjudicator is involved, no `invalidated_at` exists, and nothing about the claim itself
changes (text, spans, asserted validity, assertion time: immutable forever, D3 fully intact).
Currency is processing bookkeeping — the same epistemic category as "this Lance row belongs
to a superseded embedding version." Mechanically it is the D33 pattern: an **append-only
transitions ledger** is the truth (timestamped, reason-coded, replayable — D7), and a cached
flag + partial index on `claims` is the hot-path filter. Because transitions are timestamped
events, transaction-time reconstructions ("what did we believe in March?") still see the old
generation's contribution — nothing is overwritten.

## 4. The counting rule (D54)

> `evidence_count` (and `contradict_count`; relations *and* observations) ≡ **the number of
> distinct document lineages** whose **current-testimony** claims support (resp. contradict)
> the fact.

One redefinition, three inflations dead: re-extraction (new generation, same lineage → no
change), version churn (an hourly-edited doc re-asserting a fact per version → one lineage),
and within-document repetition (three paragraphs asserting X → one lineage — corroboration is
a *source* property; within-source emphasis is not corroboration, and D42's independence math
gets its natural denominator: distinct *external* lineages). The evidence *rows* stay
claim-grained and append-only — every generation's and version's link survives as provenance;
only the aggregate's definition changes. Consumers keep their names and get the semantics
they always assumed.

**Zero current support.** A fact whose current-testimony support drops to zero (the new
generation didn't re-derive it; the living-mode edit removed it) is **flagged
`support_withdrawn`** into the review queue (D24 machinery) with the basis diff attached —
auto-invalidation only where an explicit per-deployment policy says so. Fail-safe direction:
a flagged-but-standing fact beats a silently vanished one (the supersession-skip lesson,
D25). While unsupported, the fact is **not K3-eligible** (extends D47's gating) and carries
its state in the retrieval envelope. D35's canary CI guards the upstream cause (an extraction
regression dropping facts corpus-wide) before a new extractor ever rolls.

## 5. Reconciliation — one flow for both problems

Runs when a lineage's basis changes, and only on **completion** (a new version's extraction
finished; a version-bump re-extraction finished — never mid-flight, so there is no window
where old support is gone and new support hasn't landed; slots into the orchestration lanes'
completion semantics):

1. **Diff** the lineage's evidence links: facts evidenced under the old basis vs the new.
2. **Transition currency** per the §3 rules (append ledger rows; update the cache).
3. **Recount** affected facts — bounded and indexed: the touched set is exactly the lineage's
   evidence links.
4. **Apply the zero-support policy** (§4) where counts hit zero.
5. **Emit `evidence_changed`** (the D45 trigger queue) carrying the *fact-level* delta.

**K stability rules** (the stale-storm guard): a compiled page's `inputs_hash` is keyed on
**fact state** — fact IDs + validity/currency fingerprints + counts — never on raw claim IDs,
so a re-extraction that changes no fact state stales nothing. Claim-grain citations (the
attributed-statement residue) key on `(lineage, chunk_content_hash)` — coordinates stable
across re-extraction by construction. "A new claim row exists for the same testimony" is
*not* an evidence change and emits nothing.

## 6. Content-addressed reuse (D56) — cost proportional to the edit

The efficiency ladder for the hourly watcher, cheapest exit first:

1. **Connector metadata no-op** — unchanged revision/etag: no fetch.
2. **Content-object no-op** — bytes hash to a known object: new version row, everything else
   reused (and `UNIQUE` dedup means a copy in another folder reuses conversion too).
3. **Conversion reuse** — same content object + same converter version: artifacts reused.
4. **Chunk-grain extraction reuse** — the load-bearing lever. E2's idempotency key becomes
   the **`extraction_input_hash`**: a fingerprint of the chunk text **plus everything in the
   context bundle that can change extraction** (document header, section path, the E1 prefix,
   neighbor-chunk hashes, entity hints) + the extractor version. A chunk whose hash is
   already extracted for this lineage **reuses its claims** (the new version's chunk row
   points at them); a chunk whose *neighbors* changed correctly re-extracts even though its
   own text didn't. Embeddings reuse on (chunk content hash, embedding version) the same way.
5. **Delta-only downstream** — untouched chunks fire no currency transitions, move no counts,
   stale no K pages.

Walkthrough: a 50-page Drive document gets a two-paragraph edit. The watcher fetches once;
conversion produces the new Markdown; chunk hashing shows ~2 changed chunks; E2 runs on ~2
chunks; reconciliation diffs and finds the handful of affected facts; everything else — ~148
chunks' claims, embeddings, evidence links, K pages — carries forward untouched. **Cost ∝
the edit, not the document.**

Honest boundary: chunk-boundary shift. An edit that changes section structure can re-align
chunk boundaries so unchanged text lands in differently-hashed chunks. Section-aware chunking
(E1 splits on PageIndex sections) bounds the blast radius to the edited section; the reuse
hit-rate on real edit patterns is spike 1, and boundary-stabilized chunking (anchoring
boundaries to section identity rather than offsets) is the documented next lever if hashing
under-reuses.

Per-version chunk rows double as the **occurrence record**: which versions carried a claim is
derivable from chunk membership (claim ↔ versions whose chunk set contains its chunk hash) —
which is how `claims_as_of` answers "what did the roster page assert in March?" without any
additional machinery.

## 7. Retrieval and P1 touches

- Claim-grain primitives and recipes default to **current testimony**;
  `include_superseded_testimony` is the audit opt-in; the envelope's evidence-grain answers
  disclose which regime answered (extends D49's regime disclosure).
- `claims_as_of` is historical by definition and runs over **all** testimony — versions
  finally give it a real corpus (per-version assertion times via chunk membership, §6).
- **P1 claim search** indexes current testimony into the default channel — one current claim
  per assertion (re-extraction *replaces* the searchable claim rather than accumulating
  generations); the audit channel sees everything. A representative-text change re-embeds
  that claim; it never moves a count.
- Belief-grain answers gain a `support: current | withdrawn` marker where relevant (§4).

## 8. Deletion — three grains

- **Delete a version**: its claims' currency ends (`version_superseded`); the lineage
  continues; counts recompute; bytes purge if no other version references the content object.
- **Delete a lineage**: the existing document cascade (§13 of the schema design), at lineage
  grain — the watched-source equivalent of removing the document.
- **Hard-forget**: as today (S55 semantics), across all versions of the selected lineage —
  version rows are soft-tombstoned like document rows; the K redaction flow is unchanged.

## 9. The rejected alternative — reified evidence bases (documented escalation path)

The Codex parallel analysis proposed a first-class `evidence_bases` identity ("this source,
this source-local assertion") with the evidence joins re-keyed onto it — which requires a
**cross-generation assertion matcher** (fingerprints over spans + normalized text) deciding
when two claims "are the same assertion." Rejected here (SYNTHESIS §2): the matcher is the
riskiest component in either proposal — its author's own top failure modes are all matcher
failures, and a false *split* silently resurrects the very inflation this design kills —
while every consumer it serves is servable from coordinates the pipeline already records
(lineage-distinct counting; fact-state K hashing; `(lineage, chunk_content_hash)` citation
keys; chunk-membership occurrences). **Escalation path, if coordinate keys ever prove
insufficient** (measured, not assumed): introduce the basis layer in **exact-key mode only**
— never semantic matching. What was adopted *from* that proposal: `extraction_input_hash`,
`content_objects`, the P1 representative policy, and the K fact-state staleness rule.

## 10. Decision interactions

| Decision | Effect |
|---|---|
| D2 | **refined**: the count's denominator = distinct current lineages; the M:N link layer unchanged |
| D3 | **untouched**: currency is bookkeeping, never validity; no claim is superseded/invalidated |
| D12/D25 | **extended downward**: the same content-hash idempotency at chunk grain (`extraction_input_hash`); version ingest is the same key one level up |
| D33/D7 | **followed**: currency transitions are an append-only ledger; reconciliation replays |
| D37 | **refined**: `content_hash` identifies a **version** (via content objects); lineage identity is `(source_kind, source_ref)`; the GCS layout already fits |
| D41 | **enriched**: `asserted_at` from `source_modified_at` per version — living documents get real testimony timelines |
| D42 | **composes**: independence math = distinct *external* lineages |
| D43 | **works as designed**: version-to-version value changes are ordinary supersession; observation counts follow the new rule |
| D45–D47 | **reused**: reconciliation emits `evidence_changed`; K `inputs_hash` keyed on fact state (stale-storm guard); D47 gating excludes zero-current-support facts |
| D48–D51 | **small additions**: current-testimony defaults, regime disclosure, P1 channels |
| Deletion §13 / S55 | **composes**: version grain added; lineage and forget as before |

## 11. Spikes (measure before locking)

1. **Chunk/extraction-input reuse hit-rate** on a real watched corpus — decides whether
   boundary-stabilized chunking is needed (§6).
2. **Conversion cost floor per source type** — Google-Docs export vs PDF vs office: how much
   work is unavoidable before chunk hashes can compare.
3. **Zero-current-support policy** — false-withdrawal rate on the golden set (needs the E2/E3
   eval harness, `questions.md` #14); flag-only vs auto-invalidate per mode.
4. **Connector identity rules per source kind** — `source_ref` stability, rename/move/copy/
   fork/deletion semantics; a per-connector table (Drive, IMAP, URL, upload).
5. **Reconciliation cost at hub lineages** — a lineage evidencing thousands of facts.
6. **`versioning_mode` defaults per connector** — is Drive living or snapshot by default?
7. **Version retention × hard-forget** — retention policy for old versions and their
   artifacts vs S55 obligations.
8. **P1 representative policy** — search diversity vs lost phrasings, measured.

## References

Research: `plan/analysis/evidence_lifecycle/` (internal_analysis.md, external_agents/codex.md,
SYNTHESIS.md). Decisions: **D54–D56** (this design), D2, D3, D7, D12, D24, D25, D33, D35, D37,
D41, D42, D43, D45–D51. Schema: `postgres_schema_design.md` §6 (lineages/versions/content
objects), §7 (chunk reuse keys), §8 (currency), §9/§9.A (counts). Adjacent: review finding F3
(`design_review_2026_07.md`), the orchestration lanes (PR #29) for reconciliation-on-completion.
