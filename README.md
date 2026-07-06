# Ultimate Memory

A memory system for AI agents, designed to ingest **millions** of heterogeneous documents and
distill them into progressively more abstract, navigable knowledge — while keeping everything
auditable by humans. Scale is a requirement, not an aspiration: it is meant to still be useful
at a million documents.

> **⚠️ This repository is in the research and design phase. It contains documents, not code.**
> There is nothing to build or run yet. What lives here is the thinking — requirements,
> architecture, research, decisions, and the open questions — that has to be settled *before*
> implementation. If you're looking for a working library, it isn't here yet.

## TL;DR

Imagine pouring a million documents into a system and being able to ask it not just "where did
I read this?" but "what do we actually know, and what changed our mind?" That's the goal.

The design is organized as **three planes** — a useful mental model for the whole system:

| Plane | Plain-English meaning | What it holds | Can we rebuild it? |
|---|---|---|---|
| **E — Evidence** | *what we ingested* | Raw inputs broken down step by step: files → chunks → atomic claims → relations (facts) | No — it's the ground truth |
| **K — Knowledge** | *what we concluded* | LLM-distilled and human-editable summaries and beliefs, version-controlled like code | No — authored/curated |
| **P — Projections** | *how we reach it* | Search indexes, a knowledge graph, and a browsable filesystem, derived from the evidence spine | Yes — regenerate any time |

The one-line version: **E** is what we ingested, **K** is what we concluded, **P** is how we
reach it — and **P can always be rebuilt from E.**

Each plane breaks into a handful of layers:

**E — Evidence** *(per-document chain; Postgres is truth)*

| | What it is | Backed by | Holds |
|---|---|---|---|
| **E0** | Files / document layer | GCS (raw + artifacts) + Postgres | original bytes, markdown, per-doc section structure (PageIndex) |
| **E1** | Chunks | Postgres + Lance | retrieval-sized units with context prefixes |
| **E2** | Claims | Postgres | atomic, verifiable natural-language assertions (immutable) |
| **E3** | Relations + Observations | Postgres | **relations**: normalized `(subject, predicate, object)` entity↔entity facts (graph-projected); **observations**: untyped, entity-anchored non-graph facts (a value/statement about one entity) — both bi-temporal (D43) |

**K — Knowledge** *(LLM-compiled markdown; git is truth)*

| | What it is | Backed by | Holds |
|---|---|---|---|
| **K1** | General knowledge | git repo | progressive-disclosure summaries over the claims |
| **K2** | Special-purpose scopes | git repo | pluggable domain layers (people profiles, projects, …) |
| **K3** | Core beliefs | git repo | ultra-distilled beliefs, each linked to its evidence |

Plane K is a **framework**, not three fixed layers (D45–D47): one compile machine — an LLM
planner owning *structure*, LLM writers owning *content*, a deterministic driver owning
staleness, routing, and commits — over two page kinds: **compiled** (regenerated from the
evidence when it changes) and **authored** (human/agent commitments that are never rewritten,
only *alerted* when the evidence they cite changes). K1–K3 is the shipped **default
configuration** of that framework; deployments — and users of the library — define their own
scopes and tiers ("knowledge structure is configuration, not machinery").

**P — Projections** *(derived from the E spine; rebuildable, hold no source-of-truth; K pages
cross-link with P3 but are never a structural input — D40 refined)*

| | What it is | Backed by | Serves |
|---|---|---|---|
| **P1** | Search indexes | LanceDB | vector (semantic) + FTS/BM25 search over chunks, claims, relation + observation labels |
| **P2** | Graph | LadybugDB | neighborhood / path / as-of traversal over entities + relations |
| **P3** | Corpus filesystem | GCS directory tree | agents browsing the memory as a mounted filesystem (`ls`/`cat`/`grep`) |

A few ideas give the design its character:

- **Nothing is silently overwritten.** New information *supersedes* old information by closing a
  validity window rather than erasing it; contradictions are surfaced, not quietly resolved.
- **Two notions of time, everywhere.** When a fact was true in the world, and when the system
  learned it — so you can ask "what did we believe as of last March?"
- **Built for agents, auditable by humans.** Every conclusion traces back to the exact claims
  and source documents that support (or contradict) it.
- **Clear sources of truth.** The evidence spine lives in Postgres (original files in
  cloud storage), the distilled knowledge in a git repo, and the search and graph layers are
  derived, rebuildable projections on top.

For the full picture, start with [plan/designs/overall_design.md](plan/designs/overall_design.md).

## The `plan/` directory

All project planning lives in `plan/`, organized into four areas — three levels of abstraction
plus the research behind them:

- **`plan/requirements/`** — the highest level of abstraction: *what we want from the system*.
  Mostly bullet points. No technology choices, no architecture — just needs, constraints, and
  goals.
- **`plan/designs/`** — drill-downs into the architecture: *how a part of the system works*.
  Data models, store layouts, pipelines, trade-offs and decision rationale. Each design serves
  one area and traces back to the requirements it satisfies.
- **`plan/plans/`** — *bringing it all together*: concrete, ordered plans for building the
  system. Plans reference the designs (never duplicate them) and sequence the work — phases,
  dependencies, deliverables. *(Empty for now — sequencing begins once the designs settle.)*
- **`plan/analysis/`** — the working material *behind* the designs: research reports,
  capability surveys (e.g. `ladybug_capabilities.md`), option explorations, worked explainers
  (e.g. `concepts.md`), external-review digests. Analyses are allowed to be messy,
  opinionated, and eventually superseded — they capture *why we believe things*. Designs
  distill analyses into the binding picture and cite them; nothing in `analysis/` is binding
  on its own.

Rule of thumb: requirements say **what**, designs say **how**, plans say **in what order**,
analysis says **why we think so**. A change should land at the highest level it applies to
and flow downward.

## Document index

| Doc | Purpose |
|---|---|
| [plan/requirements/requirements_v3.md](plan/requirements/requirements_v3.md) | Requirements (current) |
| [plan/designs/overall_design.md](plan/designs/overall_design.md) | Overall system design — **best place to start** |
| [plan/designs/registries_design.md](plan/designs/registries_design.md) | Entity resolution, ontology, governance, review, eval (D15–D24) |
| [plan/designs/e2_e3_claims_relations_design.md](plan/designs/e2_e3_claims_relations_design.md) | Claim extraction + relation normalization; why there is no value gate (D31–D35, D25) |
| [plan/designs/e0_files_design.md](plan/designs/e0_files_design.md) | E0 document layer + P3 corpus filesystem (D36–D40) |
| [plan/designs/p2_graph_design.md](plan/designs/p2_graph_design.md) | P2 graph layer design (formerly L6) |
| [plan/designs/k_layers_design.md](plan/designs/k_layers_design.md) | K plane: manifest-driven compiled + authored knowledge (D45–D47) |
| [plan/designs/retrieval_design.md](plan/designs/retrieval_design.md) | The query machine: primitives, recipes, envelope, mounts, consumption skill (D48–D51) |
| [plan/analysis/retrieval_scenarios.md](plan/analysis/retrieval_scenarios.md) | Retrieval stress battery S1–S61 — drives the retrieval design + the D22 golden set |
| [plan/analysis/objections.md](plan/analysis/objections.md) | Step-back critique O1–O6 with acceptance status |
| [plan/analysis/retrieval_review/](plan/analysis/retrieval_review/) | External adversarial review of the retrieval design (Codex) + reconciliation |
| [plan/designs/evidence_lifecycle_design.md](plan/designs/evidence_lifecycle_design.md) | Document versions, testimony currency, the counting rule, content-addressed reuse (D54–D56) |
| [plan/analysis/evidence_lifecycle/](plan/analysis/evidence_lifecycle/) | Parallel analyses (internal + Codex) + SYNTHESIS behind D54–D56 |
| [plan/analysis/design_review_2026_07.md](plan/analysis/design_review_2026_07.md) | Second step-back review F1–F9 (post-D44) — K-plane build system, attributed stance, evidence inflation, … |
| [plan/analysis/entity_registry.md](plan/analysis/entity_registry.md) | Entity resolution, ontology (core+extensions), scope views |
| [plan/analysis/registry_research/](plan/analysis/registry_research/) | R1–R10 multi-agent research + SYNTHESIS (→ D17–D24) |
| [plan/analysis/entity_typing_research/](plan/analysis/entity_typing_research/) | Entity typing cascade options + SYNTHESIS (→ registries design) |
| [plan/analysis/value_gate_research/](plan/analysis/value_gate_research/) | O3 value-gate research + SYNTHESIS (gate mechanism rejected — see D25 / objections O3) |
| [plan/analysis/claimify_research/](plan/analysis/claimify_research/) | Claimify E2 research: de-contextualization + claim-level value selection + SYNTHESIS (→ D31–D35) |
| [plan/analysis/concepts.md](plan/analysis/concepts.md) | Explainer: claims vs. relations, evidence, bi-temporality |
| [plan/analysis/ladybug_capabilities.md](plan/analysis/ladybug_capabilities.md) | Verified LadybugDB capability findings |
| [plan/analysis/ladybug_translation_research/SYNTHESIS.md](plan/analysis/ladybug_translation_research/SYNTHESIS.md) | Postgres→LadybugDB translation (the `v_graph_*` projection contract, D44) |
| [decisions.md](decisions.md) | Architecture decision log (D1–D56) with rationale |
| [questions.md](questions.md) | Open questions to resolve before building |
