# Objections to the Current Design

A step-back critique of the layered architecture as captured in
`../requirements/requirements_v3.md` and `../designs/overall_design.md` (June 2026).
Status: **open** — none of these are folded into requirements/designs/decisions yet.
When one is accepted, it should land as a decision (D14+) and flow into the docs;
when rejected, the rationale should be recorded here.

## What survives scrutiny (no objection)

Postgres spine + projection discipline (D1, D6), claims/relations/evidence split (D2, D3),
bi-temporality, rebuild-first L6 (D7), debounced aggregates (D12), cheap-first cascades (D4).
The objections below are about what's *around* these, not these.

---

## O1. The "ladder" framing is wrong — it's a DAG, and the numbering misleads

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

## O3. No value gate before claim extraction — the biggest missing cost lever

**Objection.** The design runs Claimify + coreference + entity resolution + relation
normalization on *everything*. At 1M documents most content is boilerplate, duplication, or
low-value filler (cf. the Mem0 audit finding: ~98% of unfiltered extracted entries were junk).
L2 is simultaneously the cost center and the quality bottleneck — and it processes a paper's
references section with the same enthusiasm as its core findings. Junk in L2 poisons
relations, the graph, and every compiled layer downstream.

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

## O5. Entity resolution and predicate governance deserve subsystem status

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
O3/O5's gates and thresholds.

---

## Priority

If only three: **O3** (pure cost/quality leverage), **O6** (everything else is blind tuning
without it), **O2** (less machinery to build before learning whether compiled layers work at
all). O1 is a cheap doc reframe worth doing alongside; O4 and O5 fold naturally into the
upcoming L2 / git-layer / entity-registry design docs.
