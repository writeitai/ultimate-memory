# Ultimate Memory

A memory system designed to scale to millions of input documents, organized as three planes
(D14): **E — Evidence** (files → chunks → claims → relations; Postgres is truth),
**K — Knowledge** (LLM-compiled scopes and beliefs; git is truth), and **P — Projections**
(search indexes and graph; derived, rebuildable).

## TL;DR — the EKP planes

| Plane | What it holds | Source of truth | Rebuildable? |
|---|---|---|---|
| **E — Evidence** | Raw inputs broken down: files → chunks → claims → relations | Postgres | No (it's the ground truth) |
| **K — Knowledge** | LLM-compiled scopes and beliefs distilled from evidence | git | No (authored/curated) |
| **P — Projections** | Search indexes and graph derived from E and K | derived | Yes (regenerate any time) |

In short: **E** is what we ingested, **K** is what we concluded, **P** is what we query — and P can always be rebuilt from E + K.

## The `plan/` directory

All project planning lives in `plan/`, organized in three levels of abstraction:

- **`plan/requirements/`** — the highest level of abstraction: *what we want from the system*.
  Mostly bullet points. No technology choices, no architecture — just needs, constraints, and
  goals.
- **`plan/designs/`** — drill-downs into the architecture: *how a part of the system works*.
  Data models, store layouts, pipelines, trade-offs and decision rationale. Each design serves
  one area and traces back to the requirements it satisfies.
- **`plan/plans/`** — *bringing it all together*: concrete, ordered plans for building the
  system. Plans reference the designs (never duplicate them) and sequence the work — phases,
  dependencies, deliverables.
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
| [plan/designs/overall_design.md](plan/designs/overall_design.md) | Overall system design |
| [plan/designs/registries_design.md](plan/designs/registries_design.md) | Entity resolution, ontology, governance, review, eval (D15–D24) |
| [plan/designs/e2_e3_claims_relations_design.md](plan/designs/e2_e3_claims_relations_design.md) | Claim extraction + relation normalization; why there is no value gate (D31–D35, D25) |
| [plan/designs/p2_graph_design.md](plan/designs/p2_graph_design.md) | P2 graph layer design (formerly L6) |
| [plan/analysis/objections.md](plan/analysis/objections.md) | Step-back critique O1–O6 with acceptance status |
| [plan/analysis/entity_registry.md](plan/analysis/entity_registry.md) | Entity resolution, ontology (core+extensions), scope views |
| [plan/analysis/registry_research/](plan/analysis/registry_research/) | R1–R10 multi-agent research + SYNTHESIS (→ D17–D24) |
| [plan/analysis/value_gate_research/](plan/analysis/value_gate_research/) | O3 value-gate research + SYNTHESIS (gate mechanism rejected — see D25 / objections O3) |
| [plan/analysis/claimify_research/](plan/analysis/claimify_research/) | Claimify E2 research: de-contextualization + claim-level value selection + SYNTHESIS (→ D31–D35) |
| [plan/analysis/concepts.md](plan/analysis/concepts.md) | Explainer: claims vs. relations, evidence, bi-temporality |
| [plan/analysis/ladybug_capabilities.md](plan/analysis/ladybug_capabilities.md) | Verified LadybugDB capability findings |
| [decisions.md](decisions.md) | Architecture decision log (D1–D35) with rationale |
| [questions.md](questions.md) | Open questions to resolve before building |
