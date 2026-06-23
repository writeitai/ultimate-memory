# E2 Value Control — Why There Is No Pre-Extraction Value Gate (non-goal)

This document records a **scope boundary**: the system deliberately has **no value/salience gate** and
no E1.5 stage. Designs say *how the system works*; "we deliberately do not build X, and here is what
handles the underlying need instead" is binding design content (it stops a future reader from
re-proposing the gate). Decision: **D25**. Supersedes the earlier `e1_5_value_gate_design.md`; the
research that made a gate look attractive is kept as analysis (`plan/analysis/value_gate_research/`).

## 1. The scope boundary (the non-goal)

Plane E is `E0 → E1 → E2 → E3`. Every document that survives chunking is fully extracted. There is:

- **no E1.5 stage**, no value/salience gate, no per-section FULL/DEFERRED/CHUNKS-ONLY tiering;
- **no deferred/lazy machinery** — no `gate_decisions` / `document_extraction_state` /
  `salience_gate_versions` tables, no transactional outbox, no `SKIP LOCKED` promotion queue, no
  heartbeat reconciler, no promotion triggers;
- **no distilled salience classifier** and **no novelty ANN** on the ingest path.

"Most raw content is low-value" (objection O3's premise) is **true and accepted**. The conclusion that
the *answer* is a pre-extraction gate is **rejected** — see §3. The need O3 names (don't waste expensive
extraction on junk; never silently lose a fact) is met by §2, at a different place in the pipeline.

## 2. What handles junk instead (the positive design)

Junk is filtered where it is cheapest and safest to identify — **inside extraction and downstream of
it**, never by a blind pre-extraction skip.

| Junk type | Handled by | Mechanism | Cost |
|---|---|---|---|
| Opinion / advice / hypothetical / generic / intro / conclusion / lack-of-info | **E2 Selection** (Claimify, in-call) | proposition-level KEEP / REWRITE / DROP on *verifiability*; the ablation-proven highest-leverage stage (element-coverage macro-F1 83.7→54.4 when removed) | **zero marginal LLM calls** — rides the E2 call (D19, D4) |
| Structural non-content (references / bibliography / nav / boilerplate / legal) | **E2 Selection + E0 PageIndex role fed into E2** | the section path/role makes the intro/conclusion DROP classes and the list-item-without-preamble case decidable at proposition grain — the structural signal does *more* work fed into Selection than as a binary skip | free (E0 already computes it) |
| Redundant *facts* (the same fact asserted N times) | **D2 + E3** | N assertions collapse to one relation + N evidence rows; `evidence_count` is a free confidence/salience signal | free (structural) |
| Off-topic-but-verifiable content for a scope | **K2 scope views (D16)** | scope-interest selects relevant facts at query/compile time, never by dropping claims | free (in design) |
| Malformed / ungrounded extraction output | **E2 layered grounding + E3 domain/range (D18)** | window-membership grounding rejects fabrication; typed relation columns reject hallucinated relations | in-call / deterministic |

**Exact-content-hash dedup stays — as idempotency, not a value tier.** A `content_hash` short-circuit
at the worker boundary is the D12 per-doc-chain idempotency key and the D7 rebuildable property (every
surveyed system already uses it this way). It is rebuild-correctness, not selectivity — no tier cascade,
no verdict, no queue.

**Recall envelope.** E2 Selection carries the recall-conservative discipline that the gate's
defer-don't-DROP envelope used to carry, one grain down (the claim-layer D35 proposal): conservative
KEEP bias, never-drop lexical classes (quantities, dates, named-entity + predicate, change-of-state
markers), a `kept_flagged` low-confidence outcome instead of a hard delete, an append-only DROP ledger
for version-filtered re-examination, and per-fact canary CI.

## 3. Why not a gate (the rejected mechanism)

- **The "value" rung was vaporware.** The only rung that actually discriminated *value* (a distilled
  salience classifier) is unbuilt and depends on a golden set that does not exist; the novelty rung is a
  corpus-scale ANN at 10⁸ claims — i.e. the gate's own worst risk was becoming a new fleet-scale stage.
- **The lever was small and the machinery large.** The honest cost lever for skip-alone is ~1.5–2×, not
  10×. The 10× lived entirely in the DEFERRED tier, whose two state tables + transactional outbox +
  `SKIP LOCKED` queue + heartbeat reconciler + four promotion triggers are complexity disproportionate
  to a 1.5–2× lever.
- **It concentrated the highest-severity correctness risk.** A pre-extraction skip of the only
  superseding evidence serves a stale fact as current (the zombie-fact case); deciding "never defer this
  predicate" before extraction is circular (the predicate is only known *after* extraction). Extracting
  every section removes both at the root.
- **A cheaper, safer filter already exists.** Claimify's Selection ablation (83.7→54.4) makes the in-call
  verifiability filter the highest-leverage junk control, and it is free; D2 collapses redundant facts
  downstream. Nobody in the surveyed prior art (GraphRAG, LightRAG, HippoRAG, mem0, cognee, Letta) builds
  a value gate — all extract-everything — which is the to-be state here, plus a *better* in-call filter.

## 4. Accepted non-goals / risks (and the cheap add-back if any ever bites)

Each is an accepted consequence with a mitigation; none justifies re-introducing the smart gate.

1. **We pay E2 on low-value sections** (the ~1.5–2× we forgo). *Accepted:* Selection's in-call precision
   means that spend buys clean claims. **Add-back if it bites:** a trivial deterministic section filter
   `pageindex_node_type NOT IN {references, bibliography, nav, boilerplate, legal}` on E2 entry — a
   metadata branch, no classifier, no ANN, no defer state machine — gated on a measured break-even. A
   trivial structural skip, **not** a smart gate.
2. **Re-ingested boot files / one-byte-churn near-dup spam** defeat exact-content-hash. *Accepted, with
   bounds:* D2 collapses the resulting duplicate *facts* into `evidence_count` (the graph does not
   bloat) and Selection drops the same junk propositions each time (no junk claims persist); the residual
   is the repeated E2 call, for which the §4.1 structural-skip add-back is the lever.
3. **A long references/bibliography section is verbatim-verifiable**, so Selection could keep
   citation-claims. *Accepted, mitigated:* this is exactly why E0's PageIndex role is fed into E2 — the
   structural role makes the references/intro/conclusion DROP classes decidable; if a slice shows leakage,
   the structural-skip add-back drops the `references` node-type at E2 entry.
4. **Selection's DROP is a hard delete; element recall ≈ 87.6%; a uniquely-attested fact has no
   `evidence_count` net.** *Accepted, mitigated by the §2 recall envelope* (D35) — and the drop *removes*
   the gate's worse, section-grain version of this risk.
5. **R9 / D23 lose the favorable gate shrink.** *Accepted:* the 10⁸ tables revert to full-extraction
   sizing (`f_full = 1`); R9's load-test plans against ungated volume — "engineer the indexes, not the
   row counts" already holds there.

## References

Decisions: **D25** (and withdrawn D26–D30), D2 (redundancy → evidence_count), D4 (cheap-first), D7
(rebuildable), D12 (per-doc chain / idempotency), D18 (domain/range), D19 (coref in-call). Analysis:
`plan/analysis/claimify_research/SYNTHESIS.md` (E2 Selection + the recall envelope),
`plan/analysis/value_gate_research/SYNTHESIS.md` (kept as the archive of *why a gate looked attractive*).
Objection: `plan/analysis/objections.md` (O3 — premise accepted, mechanism rejected).
