# Open Questions & Underspecified Areas

The living register of **what is not settled yet** — open decisions, unwritten/underspecified
designs, known risks, and concrete inconsistencies to fix. It is the one place to look for "what's
still open"; it cross-links the two specialized trackers:

- **`decisions.md`** — what *is* decided (D1–D59).
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

**Knowledge plane (K)**
5. **K3 belief content** — the *mechanism* is now decided (D47: the belief tier — compiled pages
   over high-evidence, uncontradicted facts; evidence-gated updates). Still open: **whose beliefs
   are these** (the user's? the system's epistemic state?), and whether a belief carries a numeric
   stance score — the answer *configures* the D47 tier (its rules and curation policy), it does
   not replace it.
6. **K1/K2 freshness window** — the debounce cadence (minutes? hours? daily?) for the compile
   driver's cycle (D45); tied to the compile-cycle economics spike (`k_layers_design.md` §11).

**Operations**
7. **PageIndex: hosted API or self-hosted?** Affects cost, privacy, and the E0 rebuild story (D39).
8. **Security / access model — trust model decided; only deployment ops remain.** Decided
   (D50/D51): **content-level authorization and per-user scoping are library non-goals** — a
   deployment is one trust domain; isolation = separate deployments; perimeter security is
   deployment infrastructure; the raw mount requires data-access audit logging. Remaining
   (ops, not design): per-deployment IAM layout and key management, API perimeter auth
   mechanics (keys/OAuth vs. trusted-infra), audit-log review cadence.
9. **Postgres HA appetite** — single Hetzner box + PITR, or a replica? Acceptable spine downtime?
10. **Observability stack** — OpenTelemetry + Grafana vs. GCP-native; decide before the first worker.
11. **Backfill / reprocessing orchestration.** E0 artifacts and extraction are version-stamped
    (`converter_version`, `structurer_version`, extractor version) and embeddings can migrate
    (overall §6) — but there is no explicit plan for *how* a version bump reprocesses: version-filter
    queries, queue shape + throttling, partial-rebuild ordering, and rollback.

## 2. Open objections (unresolved critique — see `objections.md`)

12. ~~**O2 — collapse K1/K3?**~~ **RESOLVED (D47).** One compilation mechanism, N scopes; K1 =
    the default scope, K3 = the belief tier (same mechanism, stricter configuration). See
    `plan/designs/k_layers_design.md` §2/§8.
13. ~~**O4 — semantic regenerability of the K plane.**~~ **RESOLVED (D45/D46).** Every page
    carries routing rules + binding citations; compiled pages are semantically regenerable; the
    non-rebuildable surface narrows to human-authored content; the deletion cascade reaches K by
    citation reverse-lookup. See `k_layers_design.md` §4–§5, §10.
14. **O6 residual — the extraction/supersession eval harness.** O6 is only *partially* folded in:
    D22 covers the registry (ER) + retrieval eval, but the **E2/E3 side** has no eval harness yet —
    Selection precision / false-drop canaries, grounding safety, relation-normalization quality, and
    supersession/contradiction metrics (the E2/E3 design lists these as spikes). Needs an owner.

## 3. Underspecified / unwritten designs (`planned` in the design index)

15. ~~**K plane — highest risk, least designed.**~~ **RESOLVED (D45–D47)** —
    `k_layers_design.md` is written (planner/writer/driver compile system; compiled vs authored
    pages; belief tier; `k3_beliefs_design.md` folded in). The fraught mechanism (concurrent
    sessions, merge retry, hot-file delays) is removed, not mitigated. Remaining K items: the
    spikes in `k_layers_design.md` §11 (rule-kind coverage, planner blast-radius bands, writer
    completeness eval, compile-cycle economics, git-history erasure) and #5/#6 above.
16. ~~**Retrieval — the consumer surface.**~~ **RESOLVED (D48–D51)** — `retrieval_design.md` is
    written, driven by the S1–S61 scenario battery (`plan/analysis/retrieval_scenarios.md`):
    zero-LLM primitives + registry recipes, the response envelope (grain / contradictions /
    freshness / typed negatives), propose-dispose hydration, four mounts + filesystem-first
    precedence, the consumption skill. Remaining retrieval items: the spikes in
    `retrieval_design.md` §13 (Lance scale, hub pagination, rerank weights, envelope overhead,
    the S58 cold-agent protocol) and the deployment-security slice of #8.
17. **Spine schema (`postgres_schema_design.md`).** ~15 tables are sketched across separate decisions
    with no consolidated schema, FK map, indexes (only D23, registry-only), constraints, partitioning
    (only the 3 big tables), or migration convention. Mostly consolidation, not new invention.
18. ~~**E1 chunking.**~~ **RESOLVED (D57–D58)** — `e1_chunks_design.md` is written: the
    blockizer + block substrate, sections snapped to the block grid, non-overlapping
    whole-block chunk packing with anchors, multi-granularity retrieval (claims = needle
    index), extraction batching, the A1–A3 reuse mechanics. The **embedding-model choice (#3)
    remains the design's one open branch point** (prefix stage exists vs deleted).
19. **P1 search indexes.** Referenced everywhere, never a dedicated design (what's embedded, index
    params, FTS config, inline-write vs. rebuild path).
20. **Cost / metering.** A stated requirement with no design (per-layer/per-deployment spend tracking
    + budget enforcement). Ties to #2.
20a. **P2 projection (LadybugDB) — spikes to run before building the worker (D44,
    `plan/analysis/ladybug_translation_research/SYNTHESIS.md` §6).** The translation is designed (the
    `v_graph_*` views, §10.A), but verify on the deployed engine: (a) **UUID-as-node-PK** smoke test
    (source-verified; confirm the packaged build; STRING fallback documented); (b) **ATTACH cross-DB scan
    throughput + pushdown** at 10⁷–10⁸ rows — gates ATTACH-direct vs. the committed Parquet baseline,
    esp. the `MENTIONED_IN` aggregation + merge-survivor recursion; (c) **merge-redirect recursion**
    cycle guard + the pre-snapshot validation gate; (d) **inline multi-hop as-of path-filter performance**
    (projected-graph `MATCH` is unavailable — §4); (e) **snapshot retention window N** for retracted
    edges; (f) NULL-`TIMESTAMP` semantics through the Parquet round-trip.

## 4. Known risks (in decided approaches)

21. ~~**K = non-deterministic agents writing a shared git repo at scale**~~ **RESOLVED (D45)** —
    the compile driver is the repo's only automated committer; writers compile disjoint pages in
    dependency order, so write contention is structurally impossible. The residual risk moved to
    **planner quality** and **writer completeness** — both inspectable state with an eval surface
    (`k_layers_design.md` §7/§11), not emergent session behavior.
22. **Cross-document coreference** — "the CEO" referring to an entity introduced in *another* document
    falls between intra-doc coref and named-mention ER. An unowned recall hole.
23. ~~**Mixed-freshness retrieval**~~ **RESOLVED (D48/D49)** — projections only *nominate*;
    every result is re-verified by-ID against live Postgres at hydration (staleness costs
    recall, never correctness), and the envelope stamps freshness per contributing source (PG
    live / P1 lag / P2 snapshot ts / K compiled_at + flags). See `retrieval_design.md` §2/§5.
24. **End-to-end hard delete / GDPR.** E0 §2 covers raw+artifact+Postgres-row deletion, and the
    **K side is now mechanical** (D45/D46: citation reverse-lookup → compiled pages recompile
    without the evidence, authored pages get author-redaction flags; residual: **K-repo
    git-history erasure**, named in `k_layers_design.md` §10). Still open: reaching the immutable
    **P2/P3 snapshots**, the **P1/Lance** indexes, **PITR/backups**, and coordinating the whole
    cascade. Requirement is "every derived layer" (requirements §Deletion cascade).

## 5. Concrete inconsistencies to fix

25. ~~**P3 ↔ K: docs disagree on whether K is a structural input.**~~ **RESOLVED** — the
    cross-link-only model is adopted everywhere: K is never a structural input to P3 (P3 stays
    rebuildable from the E spine + artifacts). D40 carries a refinement note;
    `overall_design.md` §5 and `requirements_v3.md` §Plane P updated to match
    `e0_files_design.md` §6.
26. **D23 vs D25: gated vs. full extraction volume.** D25 re-stamped the three 10⁸ tables to **full
    extraction** sizing when the value gate was dropped (and `registries_design.md` agrees), but **D23
    still says** "row counts are contingent on the value gate — size against *gated* volume." Update
    D23.
27. ~~**P2 graph design ontology is stale vs D18.**~~ **RESOLVED (D44).** `p2_graph_design.md` §2/§3 now
    use the D18 seed core (8 types + 14 predicates), `DOC_CROSSREF(kind)` (generalizing the old `CITES`),
    and the `IS_DOCUMENT` bridge — see the Postgres→LadybugDB translation analysis
    (`plan/analysis/ladybug_translation_research/SYNTHESIS.md`) and the `v_graph_*` projection views
    (`postgres_schema_design.md` §10.A).
28. **E3 worked example contradicts D18.** `e2_e3_claims_relations_design.md` §5 shows
    `"Project Atlas launched in 2024" → (Project Atlas, launched_in_year, 2024)` — but D18 says
    objects are entities, attributes stay in claims, and time is bi-temporal *edge metadata*, never a
    predicate/Date-node. Fix the example.
29. **E3 claim→predicate mapping is thin.** §5 delegates internals to the registries but doesn't
    specify how the governed predicate is *chosen* from claim text or where domain/range is enforced
    in the flow.

## Resolved since the last version of this file (moved to decisions)

- **The attributed-stance / qualitative-belief fork** (review F2; blocked scenario S37) →
  **D59**: attributed stance is a Selection keep class, normalized to holder-anchored
  observations (ordinary D43 machinery — changed minds are supersession); unattributed opinion
  still drops; surfaced distributions recorded as the documented alternative.

- **Re-extraction evidence inflation (review F3) + document versioning for watched sources**
  → **D54–D56** + `plan/designs/evidence_lifecycle_design.md` (testimony currency; evidence_count
  ≡ distinct current-testimony lineages; lineages/versions with snapshot|living semantics;
  content-addressed chunk reuse). Spikes tracked in that design §11.

- **The K plane design** (was #15 "highest risk, least designed", #12 O2, #13 O4, #21 the
  shared-repo bottleneck) → **D45–D47** + `plan/designs/k_layers_design.md`: manifest-driven
  planner/writer/driver compilation; compiled vs authored pages; one mechanism with K3 as the
  belief tier. Open remainders stay tracked above (#5 whose-beliefs, #6 cadence, #24 hard-delete
  residuals) and in the design's §11 spikes.

- **Ontology seed** (was "what seeds the ontology") → **D18** (8 core types + 14 predicates with
  domain/range; extension packs; `other:` promotion).
- **Multi-tenant / ID scoping** (was "single user or multi-tenant") → **D16** + the deployment model
  (`registries_design.md` §1): separate deployments = separate Postgres instances + entity spaces.
- **Raw/artifact deletion** (was "hard-delete requirements") → **E0 §2** (deletes raw + artifacts +
  Postgres rows + K tombstone). *Not* fully resolved — the end-to-end cascade across P1/P2/P3
  snapshots, backups, and K markdown is still open (#24 / O4).
