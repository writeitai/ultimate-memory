# Objections to the Current Design

A step-back critique of the layered architecture as captured in
`../requirements/requirements_v3.md` and `../designs/overall_design.md` (June 2026).
Status:
- **O1 accepted → D14** (E/K/P plane naming).
- **O3 premise accepted, gate-mechanism rejected → D25** (no pre-extraction value gate;
  junk-control reassigned to E2 Selection + D2). Researched in `value_gate_research/` and
  `claimify_research/`; premise verified (with the "98% junk" headline demoted — see below).
- **O5 accepted → D15–D24** (entity-registry/ontology subsystem). Researched in
  `registry_research/`; design doc `plan/designs/registries_design.md`.
- **O6 partially folded in** via D22 (eval loop ships v1; ER half + retrieval half).
- **O2, O4 still open.**

When an objection is accepted, it lands as a decision (D14+) and flows into the docs;
when rejected, the rationale is recorded here.

## What survives scrutiny (no objection)

Postgres spine + projection discipline (D1, D6), claims/relations/evidence split (D2, D3),
bi-temporality, rebuild-first L6 (D7), debounced aggregates (D12), cheap-first cascades (D4).
The objections below are about what's *around* these, not these.

---

## O1. The "ladder" framing is wrong — it's a DAG, and the numbering misleads ✅ ACCEPTED → D14

**Objection.** L6 is not "above" L5: the graph is a projection of L2-level relations and has
nothing to do with beliefs. Relations — the most load-bearing artifact in the system — have no
layer number at all, which is exactly how they got conflated with claims initially (the
`claim_id`-on-edges mistake in the first L6 draft came from this). The v1 idea "each layer
triggers the next" was ladder-thinking too.

**The actual structure** is three planes forming a DAG:

- **Evidence pipeline** (per-document, mostly deterministic): files → chunks → claims →
  relations
- **Synthesis stack** (aggregate, LLM, git): compiled knowledge
- **Projections** (derived, rebuildable): vector indexes, graph

**Proposed change.** Reframe docs around planes-with-a-DAG; keep L-numbers only as familiar
shorthand. Mostly a documentation change, but the naming has already produced one real design
bug and keeps generating wrong intuitions about triggers, freshness, and dependencies.

**Cost of adopting:** low. **Risk of ignoring:** recurring conceptual bugs.

---

## O2. L3/L4/L5 are one mechanism wearing three names

**Objection.** By mechanism: L3 compiles claims into git markdown via agent sessions; L4 does
the same scoped to a domain; L5 (the least-specified layer — "ultra-derived beliefs") would
also be compiled markdown. A layer should earn its existence with a **distinct mechanism**,
not a distinct name. The system has four real mechanisms: *store* (L0), *index* (L1),
*extract* (L2 + relations), *compile* (L3/L4/L5).

Additionally, L5's central question — *whose* beliefs are these (the user's? the system's
epistemic state?) — is unanswered; building a dedicated layer before answering it is
speculative machinery.

**Proposed change.** Collapse to **one compiled-knowledge layer with N scopes** ("general" is
just the default scope). Demote L5 to a **curated view**, seeded mechanically from
high-evidence, zero-contradiction relations (a SQL query that the evidence model already
gives us for free) — promote it back to a layer only when a concrete use case proves it needs
its own machinery.

**Cost of adopting:** low now, high later (machinery built on three named layers hardens).
**Risk of ignoring:** building and operating three pipelines where one suffices.

---

## O3. No value gate before claim extraction — the biggest missing cost lever  ✅ PREMISE ACCEPTED, MECHANISM REJECTED → D25

**Objection.** The design runs Claimify + coreference + entity resolution + relation
normalization on *everything*. At 1M documents most content is boilerplate, duplication, or
low-value filler. E2/E3 is simultaneously the cost center and the quality bottleneck — and it
processes a paper's references section with the same enthusiasm as its core findings. Junk in
E2 poisons relations, the graph, and every compiled layer downstream.

**Citation correction (post-research).** The original draft cited "a Mem0 audit: ~98% of
unfiltered entries were junk." Research (`value_gate_research/`) traced this to a real but
**single-deployment** audit (mem0 GitHub issue #4573: 97.8% of 10,134 entries, 52.7% of it one
agent re-ingesting its own boot file) — *not* a population statistic. The premise nonetheless
holds, multiply-sourced: web survival ~5–10% after dedup/boilerplate-strip; pruning ~40% of
entities can *improve* answer quality (denoising-KG arXiv 2510.14271). Decisive: swapping in a
stronger model only dropped junk to 89.6% — **the extraction prompt, not the model, is the
bottleneck**, so a gate must precede extraction.

**Proposed change.** Tiered processing:

1. a cheap **salience gate** per document/section decides: full extraction / deferred /
   chunks-only;
2. ideally **lazy extraction** — extract claims when a document's chunks first get
   *retrieved*, or when a compiled scope declares interest in its entities.

"Progressive disclosure" should apply to *processing*, not just summarization. Plausibly a
10× cost lever.

**Cost of adopting:** medium (one new gate + a deferred-work queue; the per-doc chain already
supports staged triggering). **Risk of ignoring:** L2 cost scales with corpus size instead of
corpus value; junk degradation of all derived layers.

**Resolution (post-research).** The premise (junk exists; it poisons downstream) is **accepted**; the
proposed *gate* is **rejected**. The only value rung (a distilled salience classifier) is unbuilt and
golden-set-dependent; the novelty rung is a corpus-scale ANN (the gate's own worst risk); the honest
lever is ~1.5–2× (not 10×) and the 10× lived in DEFERRED machinery disproportionate to it; and a
pre-extraction skip concentrates the highest-severity correctness risk (the zombie-fact /
supersession-skip case). Junk-control instead lives at **E2 Selection** (Claimify verifiability,
in-call, ablation-proven 83.7→54.4) + **D2** (redundancy → `evidence_count`), with exact-hash dedup
retained as idempotency only and the E0 PageIndex role fed into E2 (`claimify_research/`). A trivial
deterministic structural section-skip is a documented future add-back, not a smart gate.
→ **D25** (and withdrawn D26–D30); design `plan/designs/e2_e3_claims_relations_design.md`.

---

## O4. Compiled (git) layers should be semantically regenerable

**Objection.** The compiled repo is an unreproducible source of truth — mitigated by backups
(D1), but that's acceptance, not mitigation. The non-determinism objection to "rebuildable
from Postgres" applies to byte-identity, not semantic identity.

**Proposed change.** Require every compiled file to carry a **manifest of its input claim /
relation IDs** (frontmatter). Then:

- "rebuild" = re-run compile over the same inputs — not byte-identical, but semantically
  reproducible;
- the semantic linter gets **mechanical staleness detection** (diff manifests against current
  claim/relation validity in Postgres) instead of LLM guesswork;
- incremental refresh ("only summaries whose referenced claims changed") becomes exact
  rather than heuristic.

Promote from nice-to-have to requirement.

**Cost of adopting:** low (a frontmatter convention + writer discipline).
**Risk of ignoring:** unauditable staleness; the repo drifts from the evidence invisibly.

---

## O5. Entity resolution and predicate governance deserve subsystem status  ✅ ACCEPTED → D15–D24

**Objection.** Both are flagged "make-or-break" in the decisions (D4, D5) and then live as
bullets inside the L2 section. If entity resolution is mediocre: relations are garbage, the
graph is garbage, and `(entity_id, predicate)` blocking misses supersessions *silently* —
quality failure here is invisible until everything downstream is poisoned.

**Proposed change.** Promote to a first-class subsystem with its own design doc
(`entity_registry_design.md`): registry schema, tiered resolution, alias lifecycle,
human-in-the-loop merge review, predicate promotion workflow, and **quality metrics from day
one** (resolution precision/recall on a labeled sample, merge-proposal acceptance rate,
`other:` predicate volume).

**Cost of adopting:** one design doc now; the work was implied anyway.
**Risk of ignoring:** the system's central quality dependency has no owner, no metrics, and
no roadmap.

---

## O6. There is no evaluation loop anywhere

**Objection.** Nothing in the requirements measures whether the memory is *good*: claim
extraction precision, junk rate, entity-resolution accuracy, supersession recall,
contradiction detection, retrieval quality. Every tunable in the design — novelty-gate
thresholds, blocking keys, resolution tiers, rerank weights — is untunable without ground
truth. For an LLM-heavy pipeline an eval harness is not optional infrastructure; it is the
steering wheel.

**Proposed change.** Add to requirements:

- a **golden set** (curated documents with expected claims, entities, relations,
  supersessions) maintained as the pipeline evolves;
- a **regression harness** run on pipeline/prompt/model changes;
- **per-stage quality metrics** sampled in production (junk rate, resolution accuracy,
  supersession precision) with human audit cadence;
- retrieval evals (recall@k on known-answer queries per search recipe).

**Cost of adopting:** real but front-loaded; smallest when started before scale.
**Risk of ignoring:** blind tuning, silent quality regressions, no way to validate any of
O5's resolution thresholds and E2 Selection's drop quality (O3).

---

## Priority

Original call (if only three): **O3**, **O6**, **O2**. **Status update:** O1 (→D14), O5
(→D15–D24), O3 (→D25, gate mechanism rejected) are done; O6 is half-folded via D22 (eval loop). **Remaining open:
O2** (collapse K1–K3 — orthogonal, untouched) and **O4** (semantic regenerability / manifests
for the K-plane git layers). Both naturally belong with the upcoming K-layer design docs.
