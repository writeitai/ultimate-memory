# Evidence Lifecycle — Stress-Test Round (User Objections) and Accepted Amendments

A design-review round on D54–D56 (PR #31): the user stress-tested the freshly-written
`evidence_lifecycle_design.md` with three objections. Verdict per objection: one exposed a
genuine under-specification (accepted, amended), one exposed a wrong blanket rule (accepted,
amended), one is handled by the existing architecture (explained, with one real interaction
caught). This file records the full reasoning so the amendments don't ride on chat memory.

**Status: all amendments BOUND** *(with two follow-up rounds recorded in D55/PR #31: the
`review|retract` dial's default flipped to `retract` on user review, and the `review` softener
was then **removed entirely** — living removal retracts; the O-B text below is the historical
record of the amendment as first accepted)*. O-A (A1–A3) → `e1_chunks_design.md` §2/§4/§7 + D57–D58 +
the D56 key correction; O-B (`removal_semantics`) → `evidence_lifecycle_design.md` §2 + D55;
O-C's timing rule → `evidence_lifecycle_design.md` §5. This file remains the record of the
reasoning.

---

## Objection A — "Reuse can't be based on chunks; chunk positions shift"

**The objection.** One slight change at the beginning of a document moves all subsequent
chunks; if reuse is keyed on chunks, everything invalidates and the D56 efficiency claim
("cost ∝ the edit") silently dies. Depends on the chunking approach — which can itself change
over time.

**What survives the objection.** Reuse is keyed on `chunk_content_hash` — the chunk's *text*,
not offsets. Positional shift alone breaks nothing: if segmentation yields the same text
pieces, hashes match wherever they moved. Section-aware chunking further contains repacking
to the edited section.

**What the objection correctly kills.** Two real failure modes were under-designed:

1. **The intra-section cascade.** Within one section, semchunk packs by token budget from the
   section start — an early insertion shifts every subsequent chunk boundary *in that
   section*. For long sections, and especially for **sectionless documents** (the synthetic
   single-root case), "section-aware" provides no containment: one early edit re-chunks the
   whole document. This is the classic content-defined-chunking (CDC) problem, and the design
   had demoted it to a spike when it is load-bearing.
2. **LLM-derived inputs poison the reuse key — the ~0%-reuse hazard.** As written,
   `extraction_input_hash` includes the PageIndex section path/summary and the E1 context
   prefix. Both are **LLM-generated and non-deterministic**, and both would be *regenerated
   per version* — so for byte-identical text the key would differ anyway, and the measured
   reuse rate could quietly be near zero. The structurer re-running per version can even
   redraw section boundaries over unchanged text, breaking containment too.

**Accepted amendments (A1–A3):**

- **A1 — anchor reuse on conversion-block hash sequences, aligned by diff.** The conversion
  module already emits `blocks[]` (paragraph-grain units with offsets, D38). Hash blocks;
  align old-version and new-version block sequences with an LCS/diff (exactly `git diff` at
  paragraph grain — a solved problem); a chunk is reusable iff its constituent block-hash
  sequence is unchanged, regardless of where it moved. Paragraph identity is far more
  edit-stable than either offsets or chunk-level packing.
- **A2 — boundary-stabilized packing inside long sections.** Restart chunk packing at
  **content-defined anchor blocks** (blocks whose hash satisfies a criterion — the
  rsync/FastCDC resynchronization idea applied at paragraph grain, *for boundary placement
  only*, never for retrieval-unit semantics). An early edit then perturbs boundaries only
  until the next anchor instead of cascading to the section end. This must be a **property of
  the chunking design**, not an optimization note.
- **A3 — LLM-derived context is carried forward, never regenerated, for unchanged regions.**
  Reused chunks keep their stored E1 prefix; unchanged regions keep the prior version's
  structure/summaries. This is not a new principle — it is **D7's replay-not-recall
  discipline applied to versioning** (the same rule that replays extraction and adjudication
  from ledgers instead of re-calling models). Consequently the **reuse key contains only
  stable components**: block hashes of the chunk, block hashes of its neighbors, header
  facts, and the extractor version — no LLM output participates in the key.

**Consequence for sequencing:** the reuse mechanics are a *chunking-strategy* property. The
evidence-lifecycle design keeps the contract ("reuse keyed on stable content identity; cost ∝
the edit"); `e1_chunks_design.md` (next) owns the mechanism (blocks, anchors, alignment,
prefix carry-forward). The reuse-hit-rate spike moves with it.

---

## Objection B — "Absence-is-never-retraction is wrong for some documents"

**The objection.** For a to-be/spec document (a migration target design), a section
disappearing *most likely means we no longer want that*. The blanket fail-safe (flag for
review, never retract) turns a clear, common signal into review-queue noise.

**Accepted — the blanket rule conflated two document classes.** The conservative rule was
calibrated for *evidence* documents, where disappearance is genuinely ambiguous
(restructuring, summarizing, splitting). But for a **normative/authoritative** document — a
spec, a target architecture, a config page, a policy — the document *is* the standing
statement (that is exactly what `living` mode already asserts), and deletion is the source's
ordinary way of saying "withdrawn."

**Accepted amendment — a per-lineage `removal_semantics` dial (`review` | `retract`),
meaningful for `living` lineages:**

- `review` (default, unchanged): removal → currency ends → counts drop →
  `support_withdrawn` flag; fact stands.
- `retract`: removal acts mechanically but safely —
  - fact has **current support from other lineages** → decrement only (it was never this
    lineage's alone to retract);
  - this lineage was the **sole current support** → **cap the derived facts' validity
    windows** at the version's `source_modified_at`, recorded as an adjudication with reason
    `removed_from_source`. A real, auditable "the standing statement withdrew this" — not a
    silent flip, and naturally reversible (re-added content opens a new window through
    ordinary E3).

No LLM call is involved; the rule is mechanical, the record is an adjudication row, and the
"never *silently* resolve" requirement is honored — the resolution is loud, attributed, and
replayable.

**Why this composes well:** it is exactly what the K-plane promotion loop needed
(`k_layers_design.md` §9): a ratified to-be document ingested as `living + retract` makes the
compiled to-be track deletions correctly and automatically — decisions removed from the spec
end their validity windows, K pages recompile, watch-flagged authored pages alert.

---

## Objection C — "A subsection split into a new document duplicates information"

**The objection.** If a subsection of doc A becomes new doc B, the same content now exists in
two lineages — duplicate information in the system.

**Explained — the claims/relations split absorbs this by design.** Walkthrough: B's sentences
extract into new *claims*, but claims are testimony, not facts. E3 normalization collapses
them onto the **same relations/observations** (D2: fact identity is the fact, not the text).
The fact's support swaps: A's contribution withdraws (removal in A's new version), B's
arrives; `evidence_count` (distinct current lineages) stays 1. No duplicate facts, no
duplicate beliefs, and the duplicate *claims* are semantically correct — "doc A asserted X
(until v7)" and "doc B asserts X" are genuinely two pieces of testimony. Default claim
search returns current testimony (B's).

**The real residual (pre-existing, not created here):** *copy* vs *move*. If the section is
copied (stays in A too), count = 2 overstates independent corroboration — that is the known,
deliberately-deferred **D42 syndication/independence problem** (mirrors, quotations,
boilerplate reuse), tracked for the independence-math consumer of `origin`.

**The sharp catch — B×C interaction (move vs removal under `retract`):** a section *moved*
to a new document momentarily looks like a *removal* from the old one. Under
`removal_semantics = retract` + sole support, the naive order (process A's new version before
B is ingested) would wrongfully cap the windows, then B re-opens them — a visible,
self-healing, but wrong flicker. **Rule adopted:** retraction checks run at reconciliation
**after the connector's sync cycle completes** (the same debounce discipline), so an
intra-cycle move resolves as a support-swap, never retract-then-reassert. Cross-cycle moves
(A edited today, B created tomorrow) still leave a short visible gap — named as a spike, not
papered over.

---

## Net effect on D54–D56

The core survives the stress test intact — currency, lineage-grain counting, and the
claims/relations split (objection C is that split *working*). Three amendments strengthen the
edges:

1. Reuse anchoring: block-hash diff alignment + anchor-stabilized boundaries + LLM-context
   carry-forward; reuse keys contain no LLM output. *(Binds in `e1_chunks_design.md`; the
   lifecycle design §6 keeps the contract and defers the mechanism.)*
2. `removal_semantics: review | retract` per living lineage; sole-support mechanical retract
   with a recorded `removed_from_source` adjudication. *(Binds in
   `evidence_lifecycle_design.md` §2/§4 + D55.)*
3. Move-vs-removal: retraction evaluates only after sync-cycle completion; cross-cycle move
   gap is a named spike.

**New/updated spikes:** reuse hit-rate measured *under the A1–A3 mechanics* (block-grain, not
naive chunk-grain); structurer stability across versions (does re-running PageIndex on
lightly-edited documents redraw unchanged sections?); cross-cycle move-gap frequency;
`removal_semantics` defaults per connector/document class.

## References

The objections: user review of PR #31 (July 2026). Amended designs:
`plan/designs/evidence_lifecycle_design.md` (D54–D56), `plan/designs/e1_chunks_design.md`
(planned — next). Related: D7 (replay-not-recall), D38 (conversion blocks), D42
(independence residual), `k_layers_design.md` §9 (promotion loop).
