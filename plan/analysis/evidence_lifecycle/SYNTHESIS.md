# Evidence Lifecycle — SYNTHESIS (internal × Codex)

Two independent analyses of the same two problems — **(A)** re-extraction evidence inflation
(review F3) and **(B)** document versioning for watched sources (Google Drive, hourly) — were
produced in parallel: `internal_analysis.md` (Claude) and `external_agents/codex.md` (Codex,
gpt-5.5). This synthesis records where they converge (most of the architecture), where they
genuinely diverge (one mechanism), and the recommended resolution.

## 1. Convergent — treat as settled direction

Both analyses independently arrived at, in some cases with identical phrasing:

| Point | Substance |
|---|---|
| **Root diagnosis** | Both problems are one event: *the evidence basis of a document changed*. The system wrongly treats a claim row / a content hash as the unit of testimony. |
| **The counting rule's meaning** | `evidence_count` must mean **current testimony from distinct sources** — never claim rows, extraction generations, source versions, or poll cycles. An hourly-edited doc re-asserting a fact stays at one. |
| **Document lineage + immutable versions** | Logical document identity = connector-native `(source_kind, source_ref)` (Drive file ID, not title/path); append-only version rows per `content_hash`; the existing raw path `<doc_id>/<content_hash>/` already implies exactly this. |
| **The semantic split** | Re-extraction = **re-transcription of the same testimony** (bookkeeping, nothing to adjudicate). A new version's changed content = **new testimony** (ordinary E2→E3 flow, supersession where it conflicts). |
| **Absence ≠ retraction** | Content removed from a new version *withdraws support* at most (currency closes, counts drop, review/flag); it never asserts negation. A source retracts only by asserting a retraction — itself a claim. |
| **Claim immutability untouched (D3)** | "Currency"/"currentness" is processing bookkeeping — no supersession, no `invalidated_at`, timestamped transitions, replayable (D7/D33). |
| **Efficiency ladder** | Connector-metadata no-op → content-hash no-op → conversion-artifact reuse → **chunk-grain content-addressed extraction/embedding reuse** → delta-only K routing. Cost of a version ∝ the edit, not the document. |
| **Retrieval regimes** | Default = current testimony; historical/version-pinned/as-of testimony are explicit opt-ins; the envelope labels the regime (extends D49). |
| **Deletion splits three ways** | Delete a version ≠ delete a lineage ≠ hard-forget; the existing cascade gains version grain. |
| **K triggers on deltas only** | `evidence_changed` fires on currency/state changes, never on "a new claim row exists for the same testimony" — else every extractor bump is a repo-wide stale storm. |

Codex additionally contributed three improvements the synthesis **adopts outright**:

- **`extraction_input_hash`** as the E2 reuse key — hash of the chunk text *plus everything in
  the context bundle that can change extraction* (header, section path, neighbors, prefix,
  entity hints) + extractor version. Sharper than chunk-content-hash alone: an unchanged chunk
  whose *neighbors* changed correctly re-extracts.
- **`content_objects`** — bytes deduplicated across lineages (the same file in two Drive
  folders = two lineages, one content object, one conversion).
- **P1 policy**: default claim search returns one representative (current) claim per
  assertion; audit search sees all generations.

## 2. The one genuine divergence — reified evidence bases vs. lineage-grain counting

**Codex's design (A4):** introduce a first-class **`evidence_bases`** entity — "this source,
this source-local assertion" — with an `evidence_basis_occurrences` table (which versions
carried it), re-key `relation_evidence`/`observation_evidence` on `(fact_id,
evidence_basis_id)`, and count distinct current bases. Requires a **reconciler** that decides
when two claims (across extractor generations or document versions) "represent the same
source-local assertion," via fingerprints over spans + normalized text + structure.

**Internal design:** no new identity layer. Evidence joins stay claim-grained; a mode-aware
**currency ledger** marks claims current/non-current mechanically (by basis *coordinates* —
version membership and extractor version — never by content matching); the headline count is
`COUNT(DISTINCT lineage)` over current-testimony claims.

The trade, stated fairly:

| | Codex (bases + matcher) | Internal (lineage count + currency) |
|---|---|---|
| Cross-generation matching | **required** — the load-bearing new component | **not needed** — old generation flips non-current wholesale; no c1↔c2 matching ever happens |
| Failure surface | Codex's own top-4 failure modes are all matcher failures (false merge, false split, span-sensitivity, text-sensitivity) — and a false *split* silently re-opens the very inflation the design exists to kill | currency bugs are possible but mechanical (coordinate comparisons), testable without a golden set |
| Intra-document repetition | counts per assertion (3 paragraphs = 3 bases) — preserves within-source structure | counts per lineage (3 paragraphs = 1) — treats corroboration as a *source* property |
| Stable evidence key for K/P1 | first-class (`evidence_basis_id`) | derived (fact IDs for K staleness; `(lineage, chunk-hash)` coordinates where claim-grain stability is needed) |
| Per-version assertion times | explicit (`occurrences.asserted_at`) | implicit but present: per-version chunk rows referencing reused claims *are* occurrence records at chunk grain |
| Schema blast radius | high — evidence joins re-keyed, new tables, K citation migration | low — one ledger + column, count redefinition, no join re-keying |

**Resolution — adopt the internal shape, absorb Codex's requirements as derived views, and
reject the matcher.** Reasoning:

1. **The matcher is the riskiest component in either proposal, and it is avoidable.** Codex
   needs it only because it re-keys the evidence joins on bases. Lineage-grain counting gets
   the same invariances (re-extraction, version churn, intra-doc repetition) from coordinates
   alone — properties the pipeline already records exactly, with no semantic judgment call.
   When the design's own author lists false-merge/false-split as failure modes #1 and #2,
   and a false split resurrects the original bug silently, the component should have to
   *prove necessity*. It doesn't: every consumer Codex serves with bases can be served
   without them —
   - **K staleness stability**: compute compiled-page `inputs_hash` from **fact IDs +
     validity/currency fingerprints + counts** (not raw claim IDs) — Codex's own §4.9 rule,
     implementable without bases. Claim-grain citations (the attributed-statement residue)
     key on `(lineage, chunk_content_hash)` — stable across re-extraction by construction.
   - **Evidence-once at the right grain**: the count is computed `DISTINCT lineage`, so
     duplicate claim-grain rows are harmless provenance, not a correctness threat; no join
     re-keying needed.
   - **Per-version assertion times** (`claims_as_of` on living docs): answered by the
     chunk-membership relation (claim ↔ versions whose chunk set contains its chunk-hash),
     which the chunk-reuse mechanism maintains anyway.
2. **On intra-document repetition, side with the lineage.** "Three paragraphs assert X" is
   within-source emphasis, not corroboration; D42's whole thrust is that the meaningful
   denominator is *independent sources*. Codex's one counter-case (genuinely independent
   sections inside one file — an appendix by a different author) is real but rare and is
   better handled *when it matters* by splitting the lineage at the connector (attachments
   and embedded docs are separate `source_ref`s anyway) than by paying a per-assertion
   identity layer everywhere.
3. **One Codex gap the internal design must keep:** Codex implicitly treats every watched
   lineage as "living" (currency follows the latest version). That is wrong for *versioned
   archival* sources — quarterly reports fetched from one URL, contract amendments — where
   every version remains independent dated testimony. The internal `versioning_mode =
   snapshot | living` per lineage (connector default + override, `snapshot` as the fail-safe
   default) stays in the recommendation.

If implementation later shows claim-coordinate keys insufficient for K/P1 stability (the
attributed-claims residue proves hot, or `(lineage, chunk-hash)` churns more than measured),
Codex's evidence-basis layer is the documented escalation path — **with the matcher confined
to exact keys only** (its conservative mode), never semantic matching.

## 3. Recommended decision package (candidate D54–D56)

1. **D54 — testimony currency + the counting rule.** Claims gain mode-aware, append-only,
   mechanical currency (re-extraction: superseded generation → non-current; `living` version
   supersession → removed-content claims non-current; `snapshot`: all versions stay current).
   `evidence_count`/`contradict_count` (relations *and* observations) ≡ distinct document
   lineages with current-testimony support, per stance. Zero-current-support facts are
   flagged `support_withdrawn` for review (auto-invalidate only by explicit per-deployment
   policy); they are never K3-eligible while unsupported (extends D47 gating). K compiled-page
   `inputs_hash` keys on fact state, never raw claim IDs; K claim citations key on
   `(lineage, chunk_content_hash)`. Retrieval defaults to current testimony; the envelope
   discloses the regime (extends D49).
2. **D55 — document lineages and versions.** `(source_kind, source_ref)` lineage identity;
   append-only `document_versions` referencing deduplicated `content_objects`;
   `versioning_mode ∈ {snapshot, living}` per lineage (connector default, `snapshot`
   fail-safe); changed content is new testimony through ordinary E2/E3; removal withdraws
   support at most; three deletion grains (version / lineage / hard-forget); P3 paths and K
   citations anchor on lineage (F6 alignment); `asserted_at` from `source_modified_at`.
3. **D56 — content-addressed reuse.** E2 keyed on `extraction_input_hash` (chunk text + full
   bundle fingerprint + extractor version); embeddings on (chunk hash, embedding version);
   conversion artifacts on (content object, converter version); connector ingest debouncing
   (stability window); reconciliation runs once per completed basis change, emitting
   delta-only K triggers.

## 4. Spikes (union of both analyses, deduplicated)

1. Chunk/extraction-input reuse hit-rate on a real watched corpus (both) — decides whether
   boundary-stabilized chunking is needed.
2. Conversion cost floor per source type (Codex) — Google-Docs export vs PDF vs office.
3. Zero-current-support policy measurement (both) — false-withdrawal rate; needs the E2/E3
   eval harness (questions #14).
4. Connector identity rules per source kind (Codex) — source_ref stability, rename/move/copy/
   fork semantics, deletion detection; per-connector table.
5. Recount + reconciliation cost at hub lineages (internal) — a lineage evidencing thousands
   of facts.
6. `versioning_mode` defaults per connector (internal) — and whether Drive is living or
   snapshot by default.
7. Occurrence/version retention + hard-forget interaction (both) — version rows vs S55.
8. P1 representative-claim policy (Codex) — diversity vs lost phrasings, measured.

## 5. Bottom line

Unanimous: document lineages with immutable versions; current-testimony counting; absence ≠
retraction; chunk-grain reuse for watch-cadence efficiency; claim immutability and every
existing decision (D2/D3/D7/D12/D25/D33/D37/D41–D43/D45–D51) preserved or cleanly refined.
Divergent on one mechanism — a reified evidence-basis layer with a cross-generation matcher
(Codex) vs lineage-grain counting with coordinate-based currency (internal) — resolved in
favor of the **matcher-free** design, with Codex's `extraction_input_hash`, `content_objects`,
P1 representative policy, and K fact-state staleness rule absorbed, and the basis layer
recorded as the documented escalation path (exact-key mode only) if coordinate keys prove
insufficient.
