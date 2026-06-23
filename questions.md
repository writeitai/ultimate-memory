# Open Questions & Underspecified Areas

The living register of **what is not settled yet** — open decisions, unwritten/underspecified
designs, known risks, and concrete inconsistencies to fix. It is the one place to look for "what's
still open"; it cross-links the two specialized trackers:

- **`decisions.md`** — what *is* decided (D1–D40).
- **`plan/analysis/objections.md`** — the step-back critique (O1–O6) with accept/reject status.
- The **design-doc index** in `plan/designs/overall_design.md` — which design docs are written
  (`current`) vs. `planned`.

Keep this current: when something here is decided, move it to a decision and prune it below.

---

## 1. Open decisions (undecided — answers shape the design)

**Scale & cost**
1. **Document mix & arrival rate** — one-time backfill of millions vs. thousands/day steady state?
   Drives worker sizing, rate limits, and the R9/D23 scale numbers (currently modeled, not measured).
2. **Monthly LLM/embedding budget ceiling** — the cheap-first cascades (D4, D17) and extraction
   spend should be tuned against a real number.
3. **Embedding model + dimension** — the single hardest thing to change later (re-embedding
   everything). A contextual model (e.g. voyage-context) would replace the E1 context-prefix
   approach. Blocks P1 index/parameter choices and the embedding-migration plan (D8's "embeddings in
   Lance" is already decided — the *model* is not).
4. **LLM per stage** — concrete picks for extraction (E2 Claimify), supersession/resolution
   adjudication (the cheap→frontier residue), and the K-plane compilers.

**Knowledge plane (K) — the least-decided area**
5. **K3 belief shape** — plain markdown statements with claim links, or a numeric stance score with
   update rules? And the unanswered prior: **whose beliefs are these** (the user's? the system's
   epistemic state?) — this question is *why* K3 is the least-specified layer.
6. **K1/K2 freshness window** — the debounce cadence (minutes? hours? daily?) for the
   aggregate-layer triggers; tied to the orchestration gap (§3).

**Operations**
7. **PageIndex: hosted API or self-hosted?** Affects cost, privacy, and the E0 rebuild story (D39).
8. **Security / access model (cross-cutting).** Bigger than retrieval auth: per-deployment IAM and
   GCS bucket access, **mounted-filesystem authorization** for agents (E0 read-only mounts), filtered
   P2/P3 snapshots for access-sensitive scopes (D16), raw-bucket audit access, and retrieval API auth
   (keys/OAuth vs. trusted-infra agents). Blocks the retrieval design (§3).
9. **Postgres HA appetite** — single Hetzner box + PITR, or a replica? Acceptable spine downtime?
10. **Observability stack** — OpenTelemetry + Grafana vs. GCP-native; decide before the first worker.
11. **Backfill / reprocessing orchestration.** E0 artifacts and extraction are version-stamped
    (`converter_version`, `structurer_version`, extractor version) and embeddings can migrate
    (overall §6) — but there is no explicit plan for *how* a version bump reprocesses: version-filter
    queries, queue shape + throttling, partial-rebuild ordering, and rollback.

## 2. Open objections (unresolved critique — see `objections.md`)

12. **O2 — collapse K1/K3?** Are K1 (general), K2 (scopes), K3 (beliefs) one mechanism (compile
    claims → git markdown) wearing three names? Could collapse to one compiled layer with N scopes +
    K3 as a curated view. Untouched.
13. **O4 — semantic regenerability of the K plane.** The git layer is an *unreproducible* source of
    truth. Should every compiled file carry an input-manifest (claim/relation IDs) so it's
    semantically rebuildable and the deletion-cascade can reach it? Open — load-bearing for deletion
    (§4) and the staleness story.
14. **O6 residual — the extraction/supersession eval harness.** O6 is only *partially* folded in:
    D22 covers the registry (ER) + retrieval eval, but the **E2/E3 side** has no eval harness yet —
    Selection precision / false-drop canaries, grounding safety, relation-normalization quality, and
    supersession/contradiction metrics (the E2/E3 design lists these as spikes). Needs an owner.

## 3. Underspecified / unwritten designs (`planned` in the design index)

15. **K plane (`k_layers_design.md`, `k3_beliefs_design.md`) — highest risk, least designed.** The
    mechanism (Codex/OpenCode agents editing a shared git repo, merge-conflict retry, rolling-window
    delay for hot files) is the most operationally fraught part of the system. Resolve O2/O4 first.
16. **Retrieval (`retrieval_design.md`) — the consumer surface.** D9 gives the shape (RRF, rerankers,
    recipes, zero-LLM path); the *API contract* asserts `as_of` (overall §6) and P2 supports it
    (p2_graph §4) — but unwritten: how API/CLI/MCP compose with the **mounted-FS** (whose mechanics
    *do* exist in E0 §5) into retrieval recipes, the cross-plane entry→expand→hydrate orchestration
    across P1/PG/P2/P3, and **mixed-freshness** reasoning (§4).
17. **Spine schema (`postgres_schema_design.md`).** ~15 tables are sketched across separate decisions
    with no consolidated schema, FK map, indexes (only D23, registry-only), constraints, partitioning
    (only the 3 big tables), or migration convention. Mostly consolidation, not new invention.
18. **E1 chunking (`e1_chunks_design.md`).** Thin but low-risk (semchunk + context prefix + embed;
    section-aware boundaries from E0).
19. **P1 search indexes.** Referenced everywhere, never a dedicated design (what's embedded, index
    params, FTS config, inline-write vs. rebuild path).
20. **Cost / metering.** A stated requirement with no design (per-layer/per-deployment spend tracking
    + budget enforcement). Ties to #2.

## 4. Known risks (in decided approaches)

21. **K = non-deterministic agents writing a shared git repo at scale** — the serial-bottleneck risk
    from the original objections; never designed away (see §3.15).
22. **Cross-document coreference** — "the CEO" referring to an entity introduced in *another* document
    falls between intra-doc coref and named-mention ER. An unowned recall hole.
23. **Mixed-freshness retrieval** — Postgres is live, P2 graph is hours stale, K is debounced; a
    consumer needs to reason about this. Unspecified (folds into #16).
24. **End-to-end hard delete / GDPR.** E0 §2 covers raw+artifact+Postgres-row deletion + a K
    tombstone, but a *complete* "forget this source" must also reach the immutable **P2/P3 snapshots**,
    the **P1/Lance** indexes, **PITR/backups**, stale corpus-fs stubs, and the K markdown that
    references it. No coherent end-to-end mechanism yet (depends on O4 / #13). Requirement is "every
    derived layer" (requirements §Deletion cascade).

## 5. Concrete inconsistencies to fix

25. **P3 ↔ K: docs disagree on whether K is a structural input.** D40 / `overall_design.md` §5 /
    `requirements_v3.md` say P3 is built "from … entities/relations + the K-plane structure"; but
    `e0_files_design.md` §6 says P3 is **Postgres-anchored** and only **cross-links** to K (K is *not*
    a structural input). Pick one. (If K is an input, P3 inherits O4's non-reproducibility and
    deletion-manifest burden; the cross-link-only model is cleaner — then D40/overall/requirements
    need updating to match.)
26. **D23 vs D25: gated vs. full extraction volume.** D25 re-stamped the three 10⁸ tables to **full
    extraction** sizing when the value gate was dropped (and `registries_design.md` agrees), but **D23
    still says** "row counts are contingent on the value gate — size against *gated* volume." Update
    D23.
27. **P2 graph design ontology is stale vs D18.** `p2_graph_design.md` lists node types
    (`paper_concept`, `other`) and predicates (`works_at`, `cites`, `collaborates_with`, `advises`)
    that predate the D18 seed core (8 types + 14 predicates) and the registry vocabulary. Update the
    P2 examples/schema to the D18/registry names.
28. **E3 worked example contradicts D18.** `e2_e3_claims_relations_design.md` §5 shows
    `"Project Atlas launched in 2024" → (Project Atlas, launched_in_year, 2024)` — but D18 says
    objects are entities, attributes stay in claims, and time is bi-temporal *edge metadata*, never a
    predicate/Date-node. Fix the example.
29. **E3 claim→predicate mapping is thin.** §5 delegates internals to the registries but doesn't
    specify how the governed predicate is *chosen* from claim text or where domain/range is enforced
    in the flow.

## Resolved since the last version of this file (moved to decisions)

- **Ontology seed** (was "what seeds the ontology") → **D18** (8 core types + 14 predicates with
  domain/range; extension packs; `other:` promotion).
- **Multi-tenant / ID scoping** (was "single user or multi-tenant") → **D16** + the deployment model
  (`registries_design.md` §1): separate deployments = separate Postgres instances + entity spaces.
- **Raw/artifact deletion** (was "hard-delete requirements") → **E0 §2** (deletes raw + artifacts +
  Postgres rows + K tombstone). *Not* fully resolved — the end-to-end cascade across P1/P2/P3
  snapshots, backups, and K markdown is still open (#24 / O4).
