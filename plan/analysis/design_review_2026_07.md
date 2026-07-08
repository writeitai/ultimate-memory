# Design Review — July 2026 (second step-back critique)

A whole-system review of the design as it stands after D1–D44, produced by an external review
agent (Claude) reading the full corpus cold: `README.md`, `plan/requirements/requirements_v3.md`,
`decisions.md` (D1–D44), `plan/analysis/objections.md` (O1–O6), `questions.md`, and all six
`current` design docs including the load-bearing sections of `postgres_schema_design.md`.

This is the same *kind* of document as `objections.md` (a step-back critique, findings with
accept/reject status to be filled in by the maintainer), written a round later — after the
registry, value-gate, Claimify, E0, observations, and LadybugDB-translation work landed. Findings
are numbered **F1–F9** (a fresh prefix; O = objections, D = decisions, R/C/V/TY = research
series). Nothing here is binding; if a finding is accepted it should land as a decision in
`decisions.md` and flow into the design docs, per the repo's normal process.

**Status: F1 accepted → D45–D47 (`k_layers_design.md`; O2 + O4 accepted with it). F2 accepted →
D59 (attributed stance kept; stance observations). F3 accepted → D54–D56
(`evidence_lifecycle_design.md`). F4 accepted → D48–D51 (`retrieval_design.md`, scenario-first
per this finding). F6 accepted → the two-tier path contract + `_index.md` contract
(`e0_files_design.md` §6; lineage anchoring from D55). F9 addressed by the orchestration design
(PR #29). F5, F7, F8 open.**

---

## What survives scrutiny (explicitly endorsed — do not re-litigate without new evidence)

The review's overall verdict is that the E-plane and P-plane architecture is sound and the
following should be kept as-is:

- **The mutually reinforcing core**: claims/relations/evidence split (D2, D3), single validity
  home in Postgres (D6), rebuild-first projections exercised every cycle (D7). These three cover
  for each other: engine risk (LadybugDB is a young fork) is contained *because* the graph is
  disposable; entity merges are cheap *because* rebuilds re-point edges; drift is impossible
  *because* rebuildability is exercised rather than assumed.
- **D25** (no pre-extraction value gate) — including the epistemic quality of the reversal
  itself: the research demoted the imagined 10× saving to an honest 1.5–2× and relocated
  junk-control to where it is cheap and safe (in-call Selection + D2 redundancy collapse).
- **D41's mechanical argument** for why an immutable, many-valued, non-fact-addressable
  claim-validity interval cannot become a second validity authority.
- **D44's `v_graph_*` view boundary** — casts, merge-redirect, and retention filtering in one
  auditable place, leaving the graph writer dumb.
- **The registries design** (D15–D24): reversible merges with pre-merge snapshots,
  blast-radius-gated review, order-independent incremental clustering, and the principled
  exclusion of causal predicates from the graph.
- **Zero LLM calls on the core query path** (D9) — right for agent consumers, who bring their own
  reasoning.

The findings below concentrate on the planes the docs themselves admit are weakest (K,
retrieval), plus two semantic gaps in plane E that no existing register lists.

---

## F1. Restructure the K plane as a manifest-driven build system, not agent sessions on a shared repo ✅ ACCEPTED → D45–D47

**Highest-leverage change in this review.** *(Accepted July 2026 — binding design:
`plan/designs/k_layers_design.md`. The accepted form sharpens this finding: mechanical routing
rules + an LLM planner for structure; a compiled-vs-authored page split (D46) that this section
did not yet have; O2 and O4 accepted with it. The text below is the original finding, kept as
the record of the argument.)*

**Current design.** K1/K2/K3 are compiled markdown in a git repo, produced by Codex/OpenCode
agent sessions that pull latest main, edit shared files, retry merge conflicts within the same
session, and route "hot" files (e.g. the root `index.md`, touched by many compiles) through a
rolling-window-delay worker. The repo is *its own source of truth* (D1) on the grounds that LLM
output is non-deterministic and therefore not rebuildable from Postgres. Staleness is detected by
a periodic "semantic linter" (an LLM pass that looks for contradictions and stale assumptions).

**The objection.** This is the one place in the system where an operationally exotic mechanism
(concurrent LLM agents doing git merge-conflict resolution) was chosen over a boring one — and it
is load-bearing for the product's headline promise ("what do we actually know, and what changed
our mind?"). All of the contention machinery (in-session conflict retry, hot-file delays) exists
only because multiple writers contend for shared files; and they contend only because compilation
is not yet a *function of declared inputs*.

**The fix is already half-built.** The schema's `knowledge_artifact_evidence` table
(`postgres_schema_design.md` §11) records, per compiled K file, exactly which claim / relation /
document IDs it is built from — i.e. it *is* the "input manifest" objection O4 asked for, in
Postgres rather than in file frontmatter. The proposal is to make that manifest **binding**:

- Each K artifact is compiled as a **pure function of its manifest**: input claim/relation IDs
  in → one markdown file out. One writer per file per compile cycle; artifacts compile in
  dependency order, exactly like a build system (make/Bazel: a target, its declared inputs, a
  rule). Merge conflicts, in-session retry, and hot-file rolling windows all disappear — there is
  no contention when every file has one writer whose inputs are declared.
- **"Rebuild" for plane K becomes semantic reproducibility**: re-running the compile over the
  same manifest yields a file that is not byte-identical (LLM non-determinism) but says the same
  thing traceable to the same evidence. D1's "the repo is unreproducible" conflates the two:
  non-determinism only blocks *byte* reproducibility.
- **Split human-authored content from compiled content.** The only genuinely non-rebuildable
  state in plane K is what humans wrote. Record human curation as explicit, separate inputs
  (override/curation files or annotations that the compiler consumes), not as edits merged into
  compiled files. The precious, backup-critical surface then shrinks from "the whole K repo" to
  "the human-authored files" — the rest regenerates from Postgres + manifests.
- **Consequences that come for free**: staleness detection becomes a mechanical manifest diff
  (compare manifest IDs against current validity in Postgres) instead of LLM guesswork; the
  deletion cascade into K (`questions.md` #24) becomes "recompile every artifact whose manifest
  contains the deleted IDs" instead of tombstone-and-hope; incremental refresh ("only summaries
  whose referenced claims changed", D12) becomes exact.

**Accept O2 at the same time.** K1 (general), K2 (scopes), K3 (beliefs) are one mechanism —
compile evidence into markdown — wearing three names. Under the build-system framing the collapse
is natural: one compiled-knowledge layer with N scopes ("general" is the default scope), and K3
starts as a **curated view seeded from high-evidence, low-contradiction relations** — a SQL query
the evidence model already supports — rather than a third pipeline.

**Cost:** the K design docs are unwritten anyway (`k_layers_design.md`, `k3_beliefs_design.md`
are `planned`), so this changes what gets designed, not what gets reworked. **Risk of
ignoring:** operating a serialized, contention-prone agent-merge system at scale; an
unauditable staleness story; a deletion cascade that cannot reach K mechanically.

---

## F2. Selection drops opinion — attributed stance should be a keep class ✅ ACCEPTED → D59

**Current design.** E2 Selection (D31/D34) drops opinions outright: in the worked example, *"The
team considers it a runaway success"* is dropped as opinion, landing only in the drop ledger.
Whether qualitative/sentiment content should be retained at all is an open question
(`questions.md`; the observations design lists it as out of scope).

**The objection.** Look at the deployment list (`registries_design.md` §1): a personal assistant,
the brain of an AI agency, a law-related knowledge engine. In those deployments, *"what does X
think about Y?"* and *"whose position changed, and when?"* are bread-and-butter memory queries —
arguably more central than headcounts. A memory system for those users that structurally discards
opinions is missing a core content class.

**The design already contains the resolution.** The grounding rule in D32 states that "*X said*
Y" entails "X said Y", **not** "Y". The same epistemics applies one level up: **an opinion held by
a named holder is a verifiable fact about the holder.** "The team considers Atlas a success" is
checkable against the source exactly the way "Atlas launched in 2024" is. Only *free-floating,
unattributed* sentiment is genuinely unverifiable. There is in fact an internal tension in the
current docs: Selection says "drop opinion", while Decomposition says "preserve attribution" —
these pull in opposite directions for any attributed opinion.

**Proposed change.** Narrow Selection's drop target to **unattributed** opinion. Attributed
stance ("X believes/considers/prefers Y") is kept as a claim, and normalizes naturally into an
**observation on the holder** (D43): stances shift over time, which is exactly what bi-temporal
observations with the fail-safe-to-coexist adjudicator are built for ("as of March, Jiri
preferred approach A" → later superseded by "prefers B"). This is also this review's
recommendation for the open qualitative-belief fork: resolve it *upstream at E2* as
"attributed stance is a keep class" — rather than either building full
surfaced-distribution machinery or declaring the whole class a non-goal.

**Cost:** a Selection prompt/rubric change + a never-drop/keep-class addition (D35 already has
the machinery); golden-set coverage for stance claims. **Risk of ignoring:** the assistant and
agency deployments cannot answer "what does X think of Y" — a silent product gap that no eval
focused on facts will catch.

---

## F3. Re-extraction inflates `evidence_count` — no register lists this ✅ ACCEPTED → D54–D56

**A semantics gap, not an orchestration gap.** (`questions.md` #11 covers how a version bump
*reprocesses*; this is about what reprocessing *means* for evidence.)

**Mechanics of the problem.** Claims are immutable, append-only, never superseded (D2/D3), and
stamped with `extractor_version`. Evidence-once is enforced per `(relation_id, claim_id)`
(`relation_evidence` PK; same shape for `observation_evidence`). Now bump the extractor version —
the versioning discipline (D12/D33) exists precisely so this can happen — and re-extract a
document: the run mints **new `claim_id`s** for the same source sentences. Each new claim links a
**new evidence row** to the same relation. `evidence_count` roughly **doubles per extractor
generation** across the re-extracted corpus.

**Why it matters.** `evidence_count` is the system's headline confidence/salience signal: the
K3 candidate filter (D2), a retrieval reranker (D9), and the trust basis for relations
generally. D42 already worries about exactly this signal being corrupted by self-ingestion
echoes ("an agent's own assertions inflate `evidence_count` as if independently corroborated");
extractor upgrades corrupt it the same way, and — unlike the agent-loop scenario — upgrades are
*guaranteed* to happen.

**Two candidate fixes** (decide one before the schema freezes; both are cheap now and painful
after data exists):

1. **Version-scoped liveness for claims-as-evidence.** A claim *counts as current evidence* iff
   its `extractor_version` equals the document's current extractor version. Old-generation claims
   remain exactly what they are today — immutable records of what was asserted (D3 untouched) —
   they just stop contributing to `evidence_count`/`contradict_count`. This is a filter at
   aggregation time, not claim supersession.
2. **Evidence aggregation keyed by document, not claim.** `evidence_count` counts distinct
   `(relation_id, doc_id)` pairs — a document contributes once to a fact's evidence no matter how
   many claim generations (or how many same-fact claims within one generation) it produced. The
   evidence *rows* stay claim-grained for provenance; only the *count* changes definition.

Whichever is chosen must be applied consistently to `relations.evidence_count`,
`relations.contradict_count`, `observations.evidence_count`/`contradict_count`, and D42's future
"independent external evidence" math.

**Risk of ignoring:** every re-extraction pass silently doubles the confidence signal that K3,
reranking, and belief derivation stand on — a corpus-wide, hard-to-reverse corruption of the one
number the design calls "free".

---

## F4. Sequence: write the retrieval design (scenario-driven) and resolve K3's "whose beliefs" before further E-plane refinement

**The observation.** Plane E is now deep — bi-temporal supersession, asserted validity,
observations, a ~1,900-line schema — while the two *consumer* surfaces are unwritten
(`retrieval_design.md`, `k_layers_design.md`/`k3_beliefs_design.md` are all `planned`). Retrieval
is the product; storage is means. The risk is not that E is wrong; it is that E's sophistication
has never been validated against a concrete consumer query.

**Proposed process change.** Write `retrieval_design.md` next, and drive it from a **scenario
set**: ~20 concrete end-to-end questions the four target deployments must be able to answer, e.g.

- "What was the standing decision on X as of March, and what changed it?" (Work pack + as-of)
- "Give me both FY2023 revenue figures with sources." (observation contradiction surfacing)
- "Everything Alice said about the migration, in chronological order." (claims + attribution)
- "What did we believe about Acme's structure before the merger closed?" (transaction-time as-of)

Each scenario must resolve to a composition of existing primitives (P1 entry → P2 expand → PG
hydrate; recipes; the claim/relation/observation temporal split). Where a scenario cannot be
composed, that is a design finding *now* rather than an implementation surprise later. The same
exercise forces the mixed-freshness story (`questions.md` #23) into concrete shape.

**And stop deferring the K3 question.** "Whose beliefs are these — the user's, or the system's
epistemic state?" (`questions.md` #5) is not a detail; there is a real unreconciled tension
between the requirement "contradictions are surfaced, never silently resolved" and K3's job of
*committing to beliefs*. The reconciliation policy — under what conditions the system moves from
"two sides stand" to "we hold X" — **is** the K3 design; everything else about K3 is formatting.

---

## F5. Observations: emit an ungoverned `property_hint` to survive hub entities

**Current design.** Observation supersession blocks on the resolved entity (exact, exhaustive)
and, for entities with many observations, narrows by semantic similarity over the `statement`
(D43). Same-property and same-period matching are purely semantic LLM judgments; there is
deliberately no typed attribute vocabulary and no structured property/period column.

**The objection.** In the actual target deployments a handful of entities are **mega-hubs**: the
user themself in the personal-assistant deployment, the company in the agency deployment. For
those, everything flows through one entity — the entity block degenerates to "all observations",
and every narrowing and same-property/same-period call is a semantic judgment. The design's own
cost story ("most entities have few observations") is true corpus-wide but false exactly where
most writes happen.

**Proposed change — the D5 move, one layer over.** Have the E2/E3 extractor emit a free-text
**`property_hint`** slug alongside each observation ("headcount", "fy-revenue", "status") — the
same pattern as the predicate registry's `other:<freetext>` escape: **ungoverned** (no registry,
no vocabulary, no maintenance), **monitored** (frequent hints are a signal, and a promotion
funnel if structure is ever wanted), and used **only to order/narrow candidates — never as a
membership gate** (the entity block stays the exhaustive candidate source, so the D43 no-recall-
hole property is untouched; a wrong hint costs at most a longer adjudication, never a wrong
supersede). This stays true to D43's untyped premise — it is a hint, not a schema — while giving
hub-entity adjudication a cheap-first key, which is the system's own philosophy (D4) applied
where the current design leaves only the expensive tier.

**Cost:** one extra output field in a call already being made; one column; no constraint.
**Risk of ignoring:** adjudication cost and same-property false-match rate concentrate on
precisely the entities the deployments care most about.

---

## F6. P3 path stability is a contract, not a spike ✅ ACCEPTED → `e0_files_design.md` §6 (two-tier path contract; analysis: `p3_agent_navigation.md`)

**Current design.** The corpus filesystem (P3, D40) rebuilds as a full snapshot; the tree
"reorganizes as the corpus grows" and placement hints are "inputs, never commitments". How the
tree stays stable enough for agents to rely on paths is listed as an open spike
(`e0_files_design.md` §8, spike 4).

**The objection.** Agents, K pages, and P3's own cross-links will *store paths* — in compiled
markdown, in agent memories, in `_index.md` files. A tree whose paths can reshuffle on any
rebuild silently breaks all of them; "reorganizable for free" is free only for the projection,
not for its consumers. Stability is therefore a **published contract** of the projection, on par
with "read-only" — not a tuning question.

**Proposed change.** Commit now to a two-tier path contract: **stable, ID-addressed paths for
entity and document leaves** (e.g. `entities/<type>/<entity_id>/`, documents reachable at a
stable per-doc path) that never move across rebuilds, plus **freely reorganizable topic/curation
views** that are explicitly documented as unstable and always link *to* the stable paths.
Consumers that need durability hold stable paths; browsing uses the views.

---

## F7. Cross-document coreference: specify where the E2 bundle's entity hints come from

**Current design.** Cross-document coreference — "the CEO" referring to an entity introduced in
a *different* document — is an acknowledged, unowned recall hole (D19 consequences;
`questions.md` #22). Separately, the E2 context bundle (D31) includes a "**known entity hints**"
element — "canonical names already on the chunk, as hints" — whose *source* is nowhere specified.

**The observation.** These two solve each other halfway. The cheap, partial mitigation for
cross-document coref is to make the hints slot do real work: feed it **registry entities scoped
to the document's context** — same source/thread/collection (an email thread's known
participants, a project folder's known project + org entities, entities from documents this one
cross-references via E0 crossref). For an email that says "the CEO agreed", the thread's known
Organization + its `works_for` neighborhood is usually all that is needed to resolve the mention
— one indexed lookup at bundle-assembly time, no new model, no new stage.

This does not *close* the hole (a truly cold cross-document reference still fails); it converts
an unowned risk into a specified, measurable mechanism whose recall can be evaluated on the
golden set.

---

## F8. Decide the embedding model before designing E1 — volume-proportional LLM spend is now the dominant cost lever

**The observation.** After D25 (extract everything), the system's LLM spend has two very
different shapes: **adjudication** spend scales with ambiguity (D4/D17 — well controlled), but
**extraction-side** spend is strictly volume-proportional: the E1 context-prefix call plus E2's
two calls ≈ **three LLM calls per chunk over the entire corpus**. At millions of documents this —
not adjudication — is where the money goes, which makes the per-stage model choices
(`questions.md` #4) and the embedding model (`questions.md` #3) the biggest unmade *cost*
decisions in the system, not tuning details.

**The sequencing point.** `questions.md` #3 already notes that a contextual embedding model
(e.g. voyage-context — models that embed a chunk *with document context* natively) would
**replace the E1 context-prefix approach entirely**. That means an entire per-chunk LLM pass
exists or does not exist depending on an undecided choice. Writing `e1_chunks_design.md` before
picking the embedding model risks designing (and costing) a stage that the model choice deletes.
Decide the embedding model first; the E1 design follows from it.

---

## F9. Load-test the cross-cloud *write* path early

**The observation.** Postgres lives on Hetzner; workers run on GCP (imposed constraints). The
design correctly keeps the *read/query* hot path's cross-cloud dependency to ID hydration
(`overall_design.md` §7). But the E-plane **write** pipeline is chatty by construction: every
sub-worker of every stage (E0 ingest/convert/structure/crossref, E1, E2, E3, registry
resolution, adjudication) reads and writes the Hetzner spine from GCP, per document, with
cross-cloud latency on every round-trip — multiplied by millions of documents during backfill.

**Proposed change.** Treat cross-cloud write-path throughput as a first-class load-test (alongside
the D23 partition/index test): measure per-stage round-trips × latency at backfill concurrency,
with pgBouncer in the loop. Keep a colocation contingency in the ops plan (e.g. batch/buffered
writes per worker, or moving latency-sensitive workers adjacent to the spine) in case the
measured backfill duration or egress cost is unacceptable. This is an operations-plan item, not
an architecture change — the stores' roles (D1/D6) are untouched.

---

## Priority

If only three: **F1** (K plane as a build system — decides the two unwritten K designs before
they harden), **F3** (evidence inflation — cheap before data exists, corpus-wide corruption
after), **F2** (attributed stance — a product gap for the named deployments and the natural
resolution of the open qualitative-belief question). F4 is a sequencing discipline to adopt
immediately; F5–F9 are targeted and can land with their respective design docs.
