# R8 — Incremental Entity Clustering with Reversible Merges

**Question.** Correct production approach to incremental entity clustering with reversible
merges. Dangers of transitive closure; correlation clustering vs connected-components-with-edge-
cutting vs Louvain vs hierarchical. Incremental cluster maintenance; Senzing-style real-time
principle-based resolution. Un-merge state. Quality safeguards. How does graph-rebuilt-from-
Postgres-every-cycle (D7) change the choice? Recommend algo + incremental procedure +
reversibility records + safeguard metrics for a Postgres-backed store.

**Scope note.** This is the *second independent take* (an Antigravity agent covers the same
question separately). Where I rely on a single source I say so. I do **not** invent benchmark
numbers; the only quantitative claims below are quoted from named sources.

---

## 1. Key findings

- **Connected-components / transitive-closure clustering is the wrong default and every cloned
  ER repo that ships it ships the over-merge bug.** Splink (`connected_components.py`), Zingg
  (`SparkGraphUtil.java` → GraphFrames `connectedComponents()`), Graphiti (`compress_uuid_map`
  Union-Find), and Cognee/GraphRAG community detection all take the full transitive closure of
  above-threshold edges: A≈B and B≈C ⇒ {A,B,C}, even when A,C were never compared or scored as a
  non-match. A single spurious "bridge" edge fuses two real entities. The literature's named
  failure mode is the **"black hole entity"** — a component that "pulls an inordinate amount of
  records from different true entities into it" (FAMER survey / Kardeş et al.). This is exactly
  the hazard `entity_registry.md` §1 ("over-merging poisons it catastrophically") and §7.3
  ("never trust transitive closure") already names.

- **The production answer is a two-stage pipeline: connected-components to *gather* candidate
  blobs, then a precision clustering pass that *cuts weak edges inside each blob*.** The cut step
  is where the field's algorithms differ. The two best-supported choices for our setting are
  **(a) hierarchical agglomerative clustering with a distance cut** (what `dedupe` actually ships
  — `scipy.linkage(method="centroid")` + `fcluster(criterion="distance")`, which *does not* force
  A=C when the centroid distance exceeds threshold) and **(b) CLIP** (FAMER's "strong-link"
  clusterer, which "outperforms all previous algorithms in terms of precision and F-measure for
  all three datasets" per the FAMER paper, and enforces at most one record per source). Both beat
  bare connected components on precision/robustness. Correlation clustering is the theoretical
  ideal (maximize intra-cluster links + inter-cluster non-links) but is **NP-hard**, so only
  approximations are used in practice. **Louvain/Leiden is the wrong tool for entity dedup** — it
  is *community* detection (modularity over topic-dense regions), not identity resolution; using
  it to merge entities re-introduces the transitive-merge problem at community granularity. Our
  D11 already restricts Louvain/Leiden to the separate community pass, not ER.

- **Incremental maintenance is a solved problem and does NOT require full re-cluster.** The
  reference method is Saeedi/Obraczka/Rahm "Incremental Multi-source Entity Resolution" (PMC7250616,
  already cited in `entity_registry.md` §8): add a new mention with **max-both assignment** (attach
  to the most-similar existing cluster only when no better new candidate competes), then run
  **n-Depth Reclustering (nDR)** — re-cluster only the subgraph of clusters within n hops of the
  changed node, leaving the rest of the graph untouched. At n=1 the paper reports nDR "achieved
  the same quality as batch ER" across insertion orders and on the 10M-person dataset incremental
  methods had "better precision than batch clustering." The naive incremental method (max-both
  merge alone) is strongly **order-dependent**; nDR is the repair that removes that dependence.
  This is the algorithmic core of Senzing's "sequence neutrality."

- **D7 (graph rebuilt from Postgres every cycle) fundamentally changes the calculus and makes our
  job EASIER, but it does not remove the need for incremental clustering — it just moves it.** The
  clustering decision is an **entity-registry (Plane E, Postgres) operation, not a graph (P2)
  operation.** The graph rebuild re-points edges to canonical IDs for free (D7 makes merges a
  no-op in P2), but the *cluster assignment itself* lives in Postgres and must be maintained as
  mentions stream in — you cannot afford to re-cluster the whole registry on every new mention,
  and you should not wait for the 6-hourly rebuild to resolve identity (resolution is on the write
  path: D4 supersession blocks on `entity_id`). So: **incremental cluster maintenance in Postgres
  (nDR-style, bounded blast radius) + free transitive re-pointing in the P2 rebuild.** Reversibility
  is cheap because un-merge in P2 is also a no-op (next rebuild reflects the corrected Postgres
  state) — the only place that must store reversibility state is Postgres (`merge_events` with a
  pre-merge membership snapshot, already in `entity_registry.md` §4).

---

## 2. Evidence & detail

### 2.1 Transitive-closure danger — confirmed in code and literature

**In our cloned repos (verified by the repo_findings, which quote source):**
- **Splink** `splink/internals/connected_components.py:120` `solve_connected_components`: edges kept
  iff `match_probability >= threshold`; with no threshold "all edges treated as matches." The
  finding explicitly flags: "Splink offers no edge-cutting in plain connected-components — you
  control merging only via the single global probability threshold" (`splink_dedupe.md` §clustering).
- **Zingg** `SparkGraphUtil.java:40` GraphFrames `connectedComponents()`; finding: "This is exactly
  the 'never trust transitive closure' pitfall… One spurious bridge edge fuses two real entities
  into one giant cluster, and OSS Zingg has no edge-cutting and no un-merge" (`zingg.md` §3, §7).
- **Graphiti** `bulk_utils.py:584-621` Union-Find with lexicographic representative: "3→2 and 2→1
  collapses to 3→1." No un-merge (`graphiti.md` §6). Canonical chosen by *uuid order*, which the
  finding flags as arbitrary.
- **GraphRAG** hierarchical Leiden (`cluster_graph.py`, `max_cluster_size=10`, `seed=0xDEADBEEF`) —
  but that is *community* detection, "clustering ≠ entity resolution" (`lightrag_graphrag.md` §6).
- **Cognee** — "no entity-resolution clustering," only external community detection (`cognee.md` §7).

**In the literature:** the survey material describes the "black hole entity" — "an entity begins to
pull an inordinate amount of records from different true entities into it, erroneously matching on
more records and escalating the problem" — and the standard guard: when a component exceeds a
**black-hole threshold**, "the match threshold is incremented by a delta and the black hole is
further partitioned with another transitive closure job… repeated until the sizes of all connected
components are below the black hole threshold" (search synthesis of Kardeş et al. *Graph-based
Organization Entity Resolution in MapReduce*; ACM survey *An Overview of End-to-End ER for Big Data*
[3418896]). **This is precisely the mechanism `dedupe` already implements in code**: `cluster(...,
max_components=30000)` re-filters by raising the threshold and recursing when a component is too big
(`dedupe/clustering.py:72-91`, per `splink_dedupe.md`). So our §7.5 "emerging giant cluster" alarm is
a known, mechanized industry pattern, not a novel idea.

### 2.2 The clustering-algorithm comparison

| Algorithm | What it does | Verdict for ER identity clustering |
|---|---|---|
| **Connected components / transitive closure** | Union of all above-threshold edges | Baseline; **high recall, fragile precision**; the over-merge/black-hole trap. Fine as a *candidate-gathering blob* stage, never as the final decision. (Splink, Zingg, Graphiti.) |
| **Hierarchical agglomerative (HAC) + distance cut** | Merge most-similar sub-clusters until linkage distance exceeds threshold; cuts weak edges | **Recommended cut stage.** Shipped by `dedupe` (`scipy linkage centroid` + `fcluster distance`). "A≈B, B≈C does not force A=C." Per-record confidence via cluster cohesion (`dedupe confidences()`). Literature: "advocated… for large scale entity resolution." |
| **Correlation clustering** | Maximize intra-cluster links + inter-cluster non-links | Theoretically ideal (uses *negative* edges), but **NP-hard**; only approximations in practice. Good when you have explicit "these are NOT the same" evidence. |
| **CLIP (FAMER)** | Uses "strong links" / link strength; enforces ≤1 entity per source | FAMER paper: "outperforms all previous algorithms in terms of precision and F-measure for all three datasets." Strong if you have a duplicate-free-source assumption; weaker fit for us (a single conversation can mention the same entity many times → not duplicate-free per source). |
| **Star / center / merge-center** | Pick representative nodes, attach neighbours | Cheaper than HAC, lower quality; mostly of historical interest in the FAMER comparison. |
| **Louvain / Leiden (modularity)** | Find topic-dense communities | **NOT entity resolution.** Community detection. Using it to merge entities re-creates transitive over-merge at community scale. Keep it in the D11 community pass only. |

Sources: ACM *End-to-End ER for Big Data* [3418896] and arXiv 1905.06397; FAMER paper (DOAJ /
dbs-leipzig); `dedupe/clustering.py` and `splink/internals/connected_components.py` as quoted in
repo_findings. (Two FAMER PDFs would not extract as text — `eswc_0.pdf`, the 2018 CSIMQ PDF — so
the CLIP precision/F-measure superiority is taken from the publishers' abstracts/search snippets,
not from the figures themselves; flagged as **medium** confidence on the exact magnitude.)

### 2.3 Incremental maintenance — the nDR method (the load-bearing source)

Saeedi, Obraczka, Rahm, *Incremental Multi-source Entity Resolution for Knowledge Graph Completion*
(PMC7250616, ESWC 2020), fetched directly:

- **max-both assignment:** a new entity `e` from set `S` "is only assigned to the cluster `c` with
  the highest similarity to `e` (above a minimal similarity threshold) if there is no other entity
  in `S` from the same source than `e` with a higher similarity." Prevents greedy mis-attachment.
- **Order dependence is real:** base Max-Both Merge tested across 12 source-addition sequences —
  "for the worst order MB achieves substantially lower recall and F-measure… strong dependency on
  the insert order." This is the danger of naive streaming clustering.
- **n-Depth Reclustering (nDR) is the fix:** "Identifies neighbor clusters at depth n from new
  entities; extracts that subgraph portion for re-clustering; applies static clustering (CLIP) to
  that region; reintegrates." At **n=1** only directly-connected neighbour clusters are reconsidered.
- **Results:** nDR (n=1) "achieved the same quality as batch ER" across insertion orders on the
  geographic dataset; on the 10M-record person dataset "all incremental methods achieved better
  precision than batch clustering." nDR "consistently outperformed max-both on recall."

**Takeaway:** the correct incremental procedure is *bounded re-clustering* — touch only the
neighbourhood of the change, run a precision clusterer there, splice back. The "blast radius" is
literally `n` hops. This is the algorithmic backbone of both Senzing's sequence-neutral self-
correction and our §7.4 blast-radius rule.

### 2.4 Senzing — principle-based, real-time, sequence-neutral, reversible

From `senzing.com` and the Senzing Zendesk *Principle-Based ER* article (fetched):

- **Three behavioural principles** on attributes (not learned rules): **Frequency** ("does one,
  few, many, or very many entities share the same value"), **Exclusivity** ("does an entity
  typically have one or multiple instances"), **Stability** ("constant or change over lifetime").
- **Sequence neutrality / self-correcting the past:** "Sequence neutrality allows Senzing to self-
  correct the past in real-time, whether it received record A first then B, or… B then A… overall
  error rates decrease over time as new information reverses earlier assertions, and reloading is
  never required." (senzing.com v4 page.) This is *reversibility as an operating principle*, and the
  mechanism is the same neighbourhood re-evaluation nDR formalizes.
- **Generic/overused identifiers:** "when multiple people are using the same SSN, our software
  detects it, labels that SSN as generic and **reevaluates all prior records with that number**."
  This is the principled version of our term-frequency intuition (Splink TF-adjustment) plus an
  automatic blast-radius re-cluster of everything that touched the now-discredited identifier.
- **Explainability:** the "why / why-not / how" API — "entity resolution decisions must be
  explainable long after they occur… scores and rules alone are insufficient without evidence of
  preserved relationships." Maps to our `merge_events` + `resolution_decisions` provenance (§4).

**Three principles to adopt wholesale** (already in `entity_registry.md` §2): *incremental,
explainable, reversible*. R8 confirms the mechanism behind each.

### 2.5 Un-merge — what state to retain

No cloned repo supports un-merge (Splink/Dedupe emit flat labels; Zingg's un-merge is Enterprise-
only paywalled; Graphiti only writes an `IS_DUPLICATE_OF` edge and "no code reverses a merge").
The Wikidata governance model (`entity_registry.md` §2) and Senzing's reversibility define the
required state. To un-merge you must retain, in **Postgres**:

1. **Per-mention resolution decisions** (`resolution_decisions`, append-only): every mention's
   `→ entity_id`, method/tier, confidence, resolver_version, `decided_at`, `superseded_by`. This is
   the ground truth of who-belonged-where; un-merge = re-deciding the affected mentions.
2. **`merge_events` (append-only) with a pre-merge membership snapshot** — survivor, absorbed,
   evidence, and the exact set of mentions/aliases each side held *before* the merge. Without the
   snapshot you cannot reconstruct the split boundary (§4).
3. **Persistent IDs never reused + redirect chain** (`merged_into`): the absorbed entity keeps its
   ID forever resolving to the survivor (Wikidata redirect model). Un-merge revives the old ID
   rather than minting a new one, so downstream stored IDs stay valid.
4. **Negative/exclusion edges** (optional but valuable for correlation-style cutting): "mention X is
   NOT entity Y" verdicts, so a re-merge doesn't immediately re-fuse what a human just split.

Because P2 is a pure projection (D6/D7), **none of this reversibility state lives in the graph** —
the graph just re-reads canonical IDs on the next rebuild. Un-merge is a Postgres transaction
(rewrite affected `resolution_decisions`, append a reversing `merge_event`) + wait one rebuild cycle.

### 2.6 Quality safeguards (mechanized, from code + literature)

- **Blast-radius / degree cap before auto-merge** (§7.4): never auto-merge an entity above a
  degree/evidence threshold; route hubs to review. Senzing's generic-identifier detection is the
  same idea applied to *attributes*.
- **Black-hole threshold** (FAMER survey / Kardeş; `dedupe max_components=30000`): if a component/
  cluster exceeds size T, raise the match threshold by δ and re-partition until all components < T.
- **Cluster-size distribution monitoring** (§7.5): an emerging giant cluster = over-merge in
  progress. Track max cluster size, top-k sizes, and growth rate per resolver version.
- **Singleton rate per type** (§7.5): rising singletons = under-merge.
- **Per-cluster cohesion/confidence** (`dedupe confidences()`): a 1−(std-dev-like) score so whole-
  cluster quality is summarizable and reviewers see clusters not pairs (§7.3).
- **Merge-proposal acceptance rate, unresolved-mention rate, alias-per-entity growth** (§7.5) as
  drift detectors — falling acceptance = thresholds drifting.
- **Canary entities + sampled human audits** (§7.6): known-tricky cases re-run per resolver version
  as regression tests.

---

## 3. Confidence & gaps

**Well-supported (high):**
- Transitive-closure over-merge danger and the black-hole phenomenon — confirmed in 4 cloned repos'
  source (quoted) *and* multiple survey sources. Convergent.
- `dedupe`'s HAC-with-distance-cut and `max_components` re-filter as the concrete, code-level
  edge-cutting pattern — read from source in repo_findings.
- nDR incremental method and max-both — fetched directly from PMC7250616 with quoted mechanism and
  quoted quality claims ("same quality as batch ER" at n=1; "better precision" on 10M persons).
- Senzing principles (frequency/exclusivity/stability), sequence neutrality, generic-identifier
  re-evaluation, reversibility-as-principle — quoted from Senzing's own pages.
- D7 making merge/un-merge re-pointing free in P2 — follows directly from D6/D7 text.

**Medium confidence:**
- **Exact magnitude of CLIP's superiority** over connected components / correlation clustering. The
  two FAMER PDFs (`eswc_0.pdf`, CSIMQ 2018) would not extract as text; "outperforms all previous
  algorithms in precision and F-measure for all three datasets" is from publisher abstract/search
  snippets, not the tables. Treat as directional, not a precise benchmark.
- **CLIP's fit for ugm specifically.** CLIP assumes *duplicate-free sources* (≤1 entity per source).
  Our sources (conversations, documents) are emphatically NOT duplicate-free — one document mentions
  the same person many times. So CLIP's core constraint is violated; **HAC-with-cut is the safer
  pick for us** and CLIP's value is mainly as the per-neighbourhood re-clusterer inside nDR (where
  the FAMER authors themselves use it).

**Gaps / could not verify:**
- No public precision/recall numbers exist for Senzing (proprietary). Reversibility/sequence-
  neutrality are vendor *claims*; the mechanism is plausible and matches nDR but is unverified at
  code level.
- I did not find a head-to-head benchmark of correlation-clustering-approx vs HAC vs CLIP *on
  conversational-memory data* — none exists publicly that I could locate. Our threshold/band tuning
  must come from our own golden set (O6 dependency, §7.1), not from borrowed numbers.
- The "black-hole threshold + δ re-partition" loop is well-attested for batch MapReduce ER; I have
  not verified anyone running it *incrementally* — but it composes cleanly with nDR's bounded scope.

---

## 4. Recommendation for ugm

**Recommended clustering algorithm (Plane E, Postgres registry):** a **two-stage cut, not bare
connected components.**
1. **Candidate blob = connected components** over above-threshold resolution edges — *only to
   gather*, with a **black-hole guard** (if a component exceeds size T, raise threshold by δ and
   re-partition; `dedupe max_components` pattern). Implementable in SQL (Splink's SQL-native CC) or
   in the external pass that already runs over the Parquet export (D11 infrastructure).
2. **Decision = hierarchical agglomerative clustering with a distance cut inside each blob**
   (`dedupe` model: centroid linkage + `fcluster(criterion="distance")`). This cuts weak bridge
   edges so A≈B, B≈C does not force A=C. Keep CLIP only as an *option* for the per-neighbourhood
   re-cluster (it assumes duplicate-free sources, which we violate — so HAC is primary).
   **Do NOT use Louvain/Leiden for ER** — reserve it for the D11 community pass.

**Incremental procedure (write path, per new mention):**
- Resolve the mention through D4's tiered cascade (Tier 0 external authority → exact → fuzzy/FTS →
  phonetic → embedding → small model → frontier; `entity_registry.md` §4) to get candidate entities.
- Apply **max-both assignment**: attach to the best existing cluster only if no competing in-batch
  mention is a better fit (PMC7250616).
- Run **n-Depth Reclustering at n=1** (n=2 only when a high-degree/hub node is touched): re-cluster
  the subgraph of clusters within 1 hop of the changed node with the HAC cut, splice back. This
  bounds blast radius and removes insert-order dependence (= our version of Senzing sequence
  neutrality). Full re-cluster is **never** on the write path.
- **Generic-identifier guard (Senzing):** if an attribute/alias suddenly links many distinct
  entities (e.g. a shared email, a common name), flag it generic, down-weight it (Splink TF-
  adjustment), and trigger an nDR re-evaluation of clusters that relied on it.
- **D7 division of labor:** all of the above writes *cluster assignments + canonical IDs* to
  **Postgres**. The 6-hourly **P2 rebuild** re-points every graph edge to canonical IDs for free —
  merges/un-merges/retypings are no-ops in P2 (D7). Do not cluster in the graph; do not wait for the
  rebuild to resolve identity.

**Reversibility records (Postgres only):**
- `resolution_decisions` (append-only, per-mention, superseded_by) — the replayable who-belonged-
  where ledger.
- `merge_events` (append-only) **with pre-merge membership snapshot** — the un-merge enabler (§4).
- Persistent `entity_id` never reused + `merged_into` redirect chain (Wikidata model).
- Optional negative/exclusion edges (`mention NOT entity`) so human splits stick and feed a future
  correlation-clustering cut.
- Un-merge = Postgres transaction (rewrite affected decisions + append reversing merge_event) →
  corrected state appears in the next P2 rebuild. **Anything not auto-undoable goes through the
  review queue (§7.7).**

**Safeguard metrics to instrument (continuous health, §7.5):**
- Max cluster size + top-k cluster sizes + growth rate per resolver_version (giant-cluster /
  black-hole alarm; hard cap T with δ-repartition).
- Singleton rate per entity type (under-merge signal).
- Auto-merge blast-radius distribution; **hard rule: no auto-merge above a degree/evidence
  threshold** — route hubs to cluster-level review (§7.3, §7.4).
- Per-cluster cohesion/confidence score (`dedupe confidences()` style) surfaced in review.
- Merge-proposal acceptance rate, unresolved-mention rate, alias-per-entity growth (drift detectors).
- Canary-entity regression suite re-run per resolver version (§7.6).

**Ties to decisions:** directly operationalizes **D4** (tiered resolution feeds clustering; cluster
quality = supersession quality), **D6/D7** (clustering is a Postgres operation, graph is a free
re-pointed projection, merges are no-ops, reversibility lives only in Postgres), **D11** (reuse the
external-pass-over-Parquet infrastructure for the CC/black-hole stage; keep Louvain out of ER),
**D15/D16** (one entity space; domain/range + type signals sharpen the HAC distance and reduce
black-hole risk). It honors `entity_registry.md` §1 (conservative-tilt asymmetry), §7.3 (review
clusters not pairs, never trust transitive closure), §7.4 (blast radius), §7.5 (health metrics),
§7.7 (reversibility as an invariant).

---

## Sources
- ACM, *An Overview of End-to-End Entity Resolution for Big Data* — https://dl.acm.org/doi/fullHtml/10.1145/3418896
- arXiv 1905.06397, *End-to-End Entity Resolution for Big Data: A Survey* — https://arxiv.org/pdf/1905.06397
- Saeedi, Obraczka, Rahm, *Incremental Multi-source Entity Resolution for KG Completion* (ESWC 2020) — https://pmc.ncbi.nlm.nih.gov/articles/PMC7250616/
- FAMER (Saeedi/Peukert/Rahm), *Scalable Matching and Clustering of Entities with FAMER* — https://dbs.uni-leipzig.de/research/publications/scalable-matching-and-clustering-of-entities-with-famer ; *Using Link Features for Entity Clustering in KGs* (CLIP) — https://link.springer.com/chapter/10.1007/978-3-319-93417-4_37
- Kardeş et al., *Graph-based Organization Entity Resolution in MapReduce* (black-hole entity) — https://www.cse.unr.edu/~hkardes/pdfs/organizationEntityResolution.pdf
- Senzing — *Principle-Based ER* https://senzing.zendesk.com/hc/en-us/articles/231726307-Principle-Based-Entity-Resolution ; *What is Principle-Based ER* https://senzing.com/what-is-principle-based-entity-resolution/ ; *v4 release / sequence neutrality* https://senzing.com/senzing-ai-sdk-v4-release/ ; *Explainability* https://senzing.com/explainability/
- arXiv 2112.06331, *Graph-based hierarchical record clustering for unsupervised ER* — https://arxiv.org/pdf/2112.06331
- Repo findings (source-quoted): `registry_research/repo_findings/splink_dedupe.md`, `zingg.md`, `graphiti.md`, `lightrag_graphrag.md`, `cognee.md`
- Design docs: `plan/analysis/entity_registry.md` (§1, §2, §4, §7), `decisions.md` (D4, D6, D7, D11, D15, D16)
