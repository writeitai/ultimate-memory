# R10 — Human-in-the-loop review tooling for merge proposals & resolution QA

**Question.** Review tooling for entity-resolution merge proposals and resolution QA. Survey existing
tools (Zingg labeler, Splink comparison/cluster dashboards, OpenRefine reconciliation/clustering,
Prodigy, Argilla) vs. building a minimal CLI/web review queue. Determine which review granularity
(pair vs. cluster) scales. Recommend build-vs-adopt for ugm's review queue, the minimal viable
reviewer workflow, and how reviewer decisions feed back into the **append-only resolution records**
(entity_registry §4: `mentions` / `resolution_decisions` / `merge_events`).

**Scope note / the load-bearing distinction.** ugm has **two structurally different review jobs**, and
every surveyed tool collapses them:
- **Training/golden-set labeling** (R7's job): "do these two records match?" → produce labels to tune
  thresholds / train a matcher. Pair-level, uncertainty-sampled. Zingg/dedupe/Prodigy/Argilla all do
  *this*.
- **Production merge-proposal QA** (R10's job): "should this entity actually be merged / is this cluster
  clean?" → produce an **adjudication that mutates the registry** via append-only records, must be
  **reversible**, must record **why**, and must respect the **blast-radius rule** (entity_registry §1,
  §7.4). *No surveyed OSS tool does this part* — it is the gap ugm must build. Keep the two queues
  conceptually separate even if they share a UI shell.

---

## 1. Key findings

- **No surveyed OSS tool gives ugm the production merge-QA queue it needs end-to-end.** They divide into
  (a) **pair labelers** (Zingg, dedupe, Prodigy) — great for R7 golden-set/active-learning, wrong
  granularity for cluster QA and with **no append-only verdict store / no reversibility / no merge
  provenance** (confirmed source-level in `repo_findings/zingg.md` §4, `splink_dedupe.md`); (b)
  **read-only diagnostic dashboards** (Splink `comparison_viewer_dashboard`, `cluster_studio_dashboard`,
  `waterfall_chart`) — explicitly built to *spot-check and find* false pos/neg, **not** to record
  decisions or write anything back ([Splink charts docs](https://moj-analytical-services.github.io/splink/charts/cluster_studio_dashboard.html));
  (c) **interactive merge UIs** (OpenRefine clustering, OpenRefine reconciliation) — these *do* let a
  human approve/merge clusters, but they merge **cell values in a spreadsheet**, not persistent
  entity IDs with redirects, and have no API to surface a queue from an external resolver
  ([OpenRefine reconciling](https://openrefine.org/docs/manual/reconciling),
  [clustering in depth](https://openrefine.org/docs/technical-reference/clustering-in-depth)).
- **Cluster-level review is the granularity that scales; pairwise review does not.** The search space and
  reviewer effort for pairwise tasks grow **quadratically** with cluster size, which is "a fundamental
  challenge" that makes pairwise active learning "hard to scale"
  ([OpenSanctions arXiv:2603.11051](https://arxiv.org/pdf/2603.11051); synthesis in
  [practitioner's guide arXiv:1509.04238](https://arxiv.org/pdf/1509.04238)). Cluster-based human tasks
  give **lower latency** when there are many matching records, though pairwise interfaces are *simpler*
  for the worker ([CrowdER arXiv:1208.1927](https://arxiv.org/pdf/1208.1927)). The
  **entity-centric evaluation** approach — sample fully-resolved clusters, where all in-cluster pairs are
  matches and all boundary-crossing pairs are non-matches — is the scalable QA primitive
  ([arXiv:2404.05622](https://arxiv.org/pdf/2404.05622)). This independently confirms
  entity_registry §7.3 ("review clusters, not pairs; never trust transitive closure").
- **The single most reusable UI patterns are Zingg's, and they are cheap to reimplement.** Source-verified
  in `repo_findings/zingg.md` §4: vertical field-by-field two-record display, **3-way verdict
  (match / no / not-sure) + quit**, **live class-balance stats per pair**, **editable labels**
  (`updateLabel`), and **uncertainty-sampled queueing** (~20 boundary pairs/round). dedupe's CLI is the
  same shape (`(y)es/(n)o/(u)nsure/(f)inished/(p)revious`, ~10 pos + 10 neg target). These are ~200 lines
  of UI, not a reason to adopt Spark or a heavyweight platform.
- **Build-vs-adopt verdict: BUILD a minimal cluster-centric review queue; ADOPT nothing as the system of
  record; optionally BORROW Splink-style waterfall/cluster *visualizations* as read-only evidence panels.**
  The decisive reason is architectural, not effort: ugm's review must write the **append-only
  `resolution_decisions` / `merge_events`** records (entity_registry §4), be **reversible** (un-merge from
  the pre-merge membership snapshot), enforce the **blast-radius rule** (D-level §7.4), and stamp
  `resolver_version` — none of the surveyed tools have this data model, and bolting it onto Zingg's Spark
  labeler or Argilla's generic feedback schema is more work than a thin queue over Postgres (D1) +
  Splink-style evidence rendering. This also keeps the **no-second-authority** discipline (D6): the
  registry in Postgres stays the only place verdicts live.

---

## 2. Evidence & detail (with citations)

### 2.1 The pair labelers — Zingg, dedupe, Prodigy (good for R7, wrong job for R10)

- **Zingg** (`repo_findings/zingg.md` §4, source-verified): the OSS human loop is the **active-learning
  labeler** (`Labeller.processRecordsCli` + `LabelDataViewHelper.displayRecords`). It shows two records
  **vertically** field-by-field, prints "Zingg predicts the above records %s with a similarity score of
  %.2f", and accepts regex `[0129]` → **No=0 / Yes=1 / Not-sure=2 / Quit=9**, storing the verdict on
  `z_isMatch`. It prints **running class balance** every pair ("Labelled pairs so far: %d/%d MATCH …").
  `updateLabel` makes labels **editable by cluster id**. Crucially this loop produces **training labels,
  not production adjudications** — and Zingg's OSS clustering is **GraphFrames `connectedComponents`**
  (blind transitive closure; `zingg.md` §3), with **no un-merge, no merge provenance** in OSS
  (merge/unmerge/cluster-reassignment + human-approved-record persistence are gated **Zingg Enterprise**;
  `runIncremental.md`, `approval.md` "Coming Soon!"). Zingg Enterprise *does* describe an approve-clusters
  workflow where a threshold auto-accepts sure matches and routes the rest to humans, and preserves cluster
  IDs on merge/split ([Zingg scoring docs](https://docs.zingg.ai/zingg/scoring)) — but it is proprietary,
  Spark-based, and still not ugm's append-only/redirect model.
- **dedupe** (`repo_findings/splink_dedupe.md`): `console_label` prompt is
  `(y)es / (n)o / (u)nsure / (f)inished / (p)revious`, target ~10 pos + 10 neg; query-by-committee
  sampler `DisagreementLearner.pop()`. Again: labels → LR classifier → flat clusters; **no verdict
  registry, no reversibility** (`splink_dedupe.md` "Avoid" §2).
- **Prodigy** (commercial, Explosion): scriptable annotation tool; there is a community recipe linking
  records across datasets **via the dedupe library**, and a `review` recipe to reconcile multiple
  annotators ([Prodigy review docs](https://prodi.gy/docs/review),
  [prodigy-recipes](https://github.com/explosion/prodigy-recipes),
  [Kabir Khan, record linkage recipe](https://medium.com/@kabirkhan1137/beyond-basic-recipes-with-prodi-gy-c8fe228e5647)).
  It is a **labeling** tool (license-fee, single-seat-oriented), not a production merge-queue with an
  append-only adjudication store. Good prior art for *recipe-driven* UI; wrong system of record.

### 2.2 The diagnostic dashboards — Splink (read-only, no write-back)

Splink ships three relevant visualizations, all **read-only diagnostics** intended to *find* errors, not
record decisions:
- **`waterfall_chart`** — decomposes a single pairwise prediction into per-field **match-weight (log2 bits)
  contributions**, so a reviewer sees *why* a pair scored as it did; "useful for spot checking pairs … if
  a pair looks like it is incorrectly being assigned a match/non-match, it is a sign the model is not
  working optimally" ([waterfall chart docs](https://moj-analytical-services.github.io/splink/charts/waterfall_chart.html)).
  This is the **explainability primitive** ugm wants in its evidence panel (and maps directly onto
  Fellegi-Sunter bit-decomposition, `splink_dedupe.md` "Steal" §1).
- **`comparison_viewer_dashboard`** — interactive dashboard with example predictions "from across the
  spectrum of match scores" ([comparison viewer docs](https://moj-analytical-services.github.io/splink/charts/comparison_viewer_dashboard.html)).
- **`cluster_studio_dashboard`** (the standalone repo was folded into Splink core) — "interactive dashboard
  that visualises the results of clustering … provides examples of clusters of different sizes. The shape
  and size of clusters can be indicative of problems with record linkage, so it provides a tool to help you
  find potential false positive and negative links"
  ([cluster studio docs](https://moj-analytical-services.github.io/splink/charts/cluster_studio_dashboard.html),
  [charts gallery](https://moj-analytical-services.github.io/splink/charts/index.html)). Requires
  `retain_matching_columns` + `retain_intermediate_calculation_columns = True`. **It does not record
  accept/reject verdicts and does not write decisions back** — the docs and the source describe it purely as
  a visualization (I confirmed there is no decision-capture/export-of-labels affordance in the documented
  API; *flagged as a strong inference from the docs, not a line-level source read of the JS*). Cluster size
  distribution as the over-merge alarm matches entity_registry §7.5 verbatim.

**Takeaway:** Splink's charts are the right *evidence rendering* (waterfall = why-merged; cluster studio =
cluster shape), but they are a panel inside a review tool, never the queue itself.

### 2.3 The merge UIs — OpenRefine (real merge, wrong unit of identity)

- **OpenRefine clustering** (key-collision and nearest-neighbour/kNN with a tunable radius) groups similar
  cell values; the human **reviews each cluster, unchecks values that shouldn't be included, sets the
  merged value, and clicks Merge** — an actual human-in-the-loop cluster-merge UI, with
  "Merge Selected & Re-Cluster" to iterate over keying functions
  ([OpenRefine clustering in depth](https://openrefine.org/docs/technical-reference/clustering-in-depth),
  [UIUC LibGuide](https://guides.library.illinois.edu/openrefine/clustering)). This is the **closest
  existing UX to cluster-level merge review** and is worth imitating: cluster card → list members →
  checkbox-exclude outliers → confirm.
- **OpenRefine reconciliation** matches column values against an external **reconciliation service** (a web
  API returning ranked candidate entities); "reconciliation is semi-automated … human judgment is required
  to review and approve the results", with hover-preview of candidate entities and an interactive cluster
  review interface ([reconciling](https://openrefine.org/docs/manual/reconciling),
  [reconciliation API](https://openrefine.org/docs/technical-reference/reconciliation-api),
  [survey arXiv:1906.08092](https://arxiv.org/pdf/1906.08092)). The **reconciliation-service API contract**
  (given a name + properties, return ranked candidate entity IDs with scores) is a clean, standardized
  shape ugm could expose for "match this mention to an existing entity" review.
- **But**: OpenRefine merges **spreadsheet cells in a project file**, not persistent entity IDs; there is
  no notion of redirects, no append-only decision log, no un-merge of a prior committed merge, and no way to
  *push* a queue of proposals from ugm's resolver into it. It is a desktop data-cleaning tool, not a
  service-backed review queue. **Adopt the interaction patterns, not the tool.**

### 2.4 The generic annotation platforms — Argilla (and why "just use a platform" is tempting but a poor fit)

- **Argilla 2.x** (open-source, Apache-2.0; **acquired by Hugging Face, Feb 2025, ~$10M**, actively
  maintained, self-hostable on HF Spaces or Docker —
  [Argilla joins HF](https://argilla.io/blog/argilla-joins-hugggingface/),
  [aibusiness](https://aibusiness.com/data/hugging-face-acquires-ai-software-startup-to-boost-datasets),
  [Argilla 2.0 release](https://argilla.io/blog/argilla-2-release/)). It offers a flexible **record + fields
  + questions + responses** model with **Suggestions** (machine-proposed answers shown to the annotator to
  accelerate review), record **queues (Pending / Draft / Submitted)**, custom fields, and multi-annotator
  with response status ([data model](https://docs.v1.argilla.io/en/latest/conceptual_guides/data_model.html),
  [annotate](https://docs.argilla.io/latest/how_to_guides/annotate/)). You **could** model a merge proposal
  as a record (the two/N entity profiles as fields, a Suggestion = the resolver's proposed verdict + score,
  a single-label question = accept/reject/not-sure) and pull responses via the SDK to write your own
  `resolution_decisions`.
- **Why it's a medium fit, not a clean adopt:** Argilla's data model is **annotation-record-centric**, not
  **entity-registry-centric**. It has no concept of clusters of arbitrary size with blast-radius guards, no
  merge/redirect/un-merge semantics, and its "labels" are not adjudications that mutate a system of record —
  you still have to build the entire write-back-to-Postgres + reversibility + provenance layer yourself.
  You'd adopt Argilla to avoid writing a UI, but you keep ~all the load-bearing logic. For a **small reviewer
  team (1–3 people) on the middle confidence band only** (entity_registry §7.2: "only the middle costs
  money"), the UI you avoid is small and the integration tax (running/securing a server, mapping its schema
  to yours, keeping its queue in sync with the resolver) is not obviously cheaper than a thin app over the
  data you already own. **Defensible either way; see §4 for the staged call.**

### 2.5 Granularity: why cluster review scales and pairwise doesn't

- **Quadratic blow-up**: for a cluster of *k* records there are *k(k−1)/2* pairs; pairwise review/labeling
  effort and the active-learning search space grow **quadratically** — explicitly called out as why pairwise
  AL is "hard to scale" ([OpenSanctions arXiv:2603.11051]). A reviewer asked to confirm a 12-member cluster
  pairwise faces 66 questions; as one cluster card with 12 rows + "uncheck the outlier", it's one task.
- **Cluster-based human tasks reduce latency** when many records match, at the cost of a slightly more
  complex per-task UI ([CrowdER arXiv:1208.1927]); cluster-based HIT generation is NP-hard to *optimize* but
  the *review unit* itself is simply "one cluster = one task".
- **Entity-centric QA sampling**: review **resolved clusters**, not pairs — within a sampled cluster all
  pairs are matches; any pair crossing the cluster boundary is a non-match — this yields precision/recall
  without quadratic labeling ([arXiv:2404.05622], [practitioner's guide arXiv:1509.04238]).
- **The hybrid that actually works for a human**: present a **cluster card**, but let the reviewer act with
  **edge-level operations** (split off member X; reject bridge edge A–B; confirm whole cluster). This is
  exactly OpenRefine's "uncheck the value that doesn't belong" + dedupe's edge-cutting hierarchical
  clustering (`splink_dedupe.md` "Steal" §4). It respects entity_registry §7.3 ("clustering that cuts weak
  edges") while keeping the reviewer's unit-of-work O(1) per cluster.

### 2.6 Cost-control framing (what to send to humans at all)

- **r-HUMO** (risk-aware human-machine cooperation for ER with quality guarantees,
  [arXiv:1803.05714](https://arxiv.org/pdf/1803.05714)) and **SystemER** (human-in-the-loop *explainable* ER,
  [VLDB vol12 p1794](https://www.vldb.org/pvldb/vol12/p1794-qian.pdf)) formalize the same three-band idea
  ugm already has (entity_registry §7.2): machine auto-decides the confident head and tail; humans see only
  the **risky middle**, prioritized by **expected quality impact**. This is the literature backing for
  routing by **blast radius × uncertainty**, not by uncertainty alone — a hub-merge proposal at medium
  confidence must outrank a long-tail merge at the same confidence (entity_registry §7.4).

---

## 3. Confidence & gaps

**Well-supported (high confidence):**
- Cluster-level review scales and pairwise does not (quadratic effort) — multiple peer-reviewed sources
  (OpenSanctions, CrowdER, arXiv:2404.05622, arXiv:1509.04238) + entity_registry §7.3.
- Zingg/dedupe UI mechanics (3-way verdict, vertical display, class-balance stats, editable labels,
  uncertainty queue) — **source-verified** in `repo_findings/` with file/line cites.
- Splink charts are **read-only diagnostics** (waterfall = per-field bit decomposition; cluster studio =
  cluster-shape inspection) and do **not** record verdicts — from official docs.
- OpenRefine clustering/reconciliation is a real human cluster-merge UI but operates on **spreadsheet
  cells**, not persistent entity IDs with redirects — from official docs.
- Argilla is OSS, HF-owned since Feb 2025, actively maintained, self-hostable, with a record/field/question/
  Suggestion model and review queues — from Argilla/HF sources.
- None of the OSS tools implement append-only adjudication + reversible merges + merge provenance — this is
  the consistent "Avoid" finding across `repo_findings/zingg.md` and `splink_dedupe.md`.

**Moderately supported (medium):**
- That `cluster_studio_dashboard` has **no** decision-capture/write-back path: strongly implied by the docs
  (described purely as visualization) but I did **not** line-read its JS source this pass. Flagged.
- Build < adopt-Argilla on total effort for ugm's small-reviewer-team, middle-band-only case: a judgment
  call weighing UI-saved vs. integration-tax, not a measured comparison.
- r-HUMO/SystemER as the framing for blast-radius-weighted routing: the papers support three-band
  human-machine cooperation; the specific "weight by degree/evidence" knob is ugm's §7.4, mapped on by me.

**Gaps / could not verify:**
- **No off-the-shelf OSS tool was found that does the full job** (cluster queue + append-only verdicts +
  reversibility + provenance + blast-radius gating). If one exists I did not find it; treated as "must
  build". (Senzing does this commercially per entity_registry §2, but it's closed and its review UI wasn't
  inspectable here.)
- **No benchmark on reviewer throughput** (clusters/hour, accuracy vs. cluster size) for any specific tool —
  could not source numbers; the quadratic-vs-linear argument is structural, not measured here.
- **Exact `cluster_studio_dashboard` internals** (does it emit a labels file?) — unverified at source level.
- Whether ugm's reviewer volume ever justifies a real platform (Argilla/Label Studio) is **data-dependent**
  (depends on middle-band size after tuning, R7) and unknown pre-launch.

---

## 4. Recommendation for ugm (concrete, tied to D1–D16 / O5)

**Verdict: BUILD a thin, cluster-centric review queue over Postgres. ADOPT no tool as the system of record.
BORROW Splink-style waterfall/cluster visuals as read-only evidence panels and OpenRefine's
cluster-card-with-exclude interaction. Re-use the Zingg/dedupe verdict ergonomics verbatim.** This is forced
by D6 (single authority — verdicts live only in Postgres) and entity_registry §4 (append-only
mentions/decisions/merge_events + reversibility), which no surveyed tool's data model provides.

### 4.1 What feeds the queue (route by blast radius × uncertainty)
- Only the **middle confidence band** reaches a human (entity_registry §7.2; auto-accept head, auto-reject
  tail). Source merge proposals from the **D4 tier cascade** output that lands in the band, **plus** any
  proposal whose **blast radius is high** (degree/evidence above the §7.4 threshold) regardless of
  confidence — high-degree hub merges are **never** auto-accepted (entity_registry §1, §7.4; r-HUMO/SystemER
  back this). Prioritize the queue by `expected_impact = blast_radius × (1 − confidence)`.
- Granularity = **cluster, not pair** (§2.5; entity_registry §7.3). A queue item is a *proposed cluster* (or
  a proposed merge of two existing clusters), rendered as a card.

### 4.2 Minimal viable reviewer workflow (v1, CLI-first, web later)
Steal the Zingg/dedupe ergonomics; render the cluster the OpenRefine way; explain with the Splink waterfall:
1. **Cluster card** — list member mentions/entities field-by-field (Zingg vertical display), each with its
   surface form, source doc, and type. Show **cluster health**: size, min/max pairwise score (Zingg
   `Z_MINSCORE`/`Z_MAXSCORE` analogue), and a flag if it exceeds the giant-cluster alarm (§7.5).
2. **Evidence panel** — for the weakest in-cluster edge(s), a **Splink-style waterfall** of per-field
   match-weight contributions (Fellegi-Sunter bits; `splink_dedupe.md` "Steal" §1) and the **tier + method**
   that proposed the merge (Tier 0–5, entity_registry §4) and `resolver_version`.
3. **Verdict actions** (OpenRefine-style edge ops + Zingg 3-way):
   - **Confirm cluster** (accept all member edges),
   - **Split off member X** / **reject bridge edge A–B** (uncheck the outlier — cuts the weak edge, never
     blind transitive closure),
   - **Not-sure** (defer; keeps it out of training, Zingg/dedupe pattern),
   - **Reject merge** (keep entities separate).
4. **Live stats** (Zingg pattern): running counts of confirmed/split/rejected/not-sure this session +
   queue depth; cheap drift signal (merge-proposal acceptance rate, entity_registry §7.5).
5. **CLI first** (entity_registry §8.3 asks exactly this). A web queue is a **later** upgrade — and **only
   then** consider mounting it on **Argilla/Label Studio** if reviewer volume justifies a real platform
   (decision deferred to post-tuning data, R7). The UI is small; the data model is the hard part, and that's
   ours regardless.

### 4.3 How decisions feed back into the append-only resolution records (the core requirement)
Every reviewer action is an **append**, never an edit (entity_registry §4; same epistemology as D2/D3):
- **Confirm / reject member → `resolution_decisions` row**: `mention_id → entity_id`,
  `method = human_review`, `confidence`, `resolver_version`, `decided_at`, `reviewer_id`,
  `superseded_by = null`. A later re-review writes a **new row** that sets the old row's `superseded_by`
  (entity_registry §4 "mentions never edited; resolution re-decidable"; versioning mechanics mirror D12).
- **Confirm a merge → `merge_events` row**: `survivor`, `absorbed`, `evidence` (the proposal + reviewer
  verdict + waterfall snapshot), and the **pre-merge membership snapshot** — *this snapshot is what makes
  un-merge possible* (entity_registry §4). The absorbed entity keeps its ID with `merged_into` → **redirect,
  not rewrite** (Wikidata model, entity_registry §3; downstream IDs still resolve).
- **Split / reject-edge → reversal as another append**: write the inverse `merge_event` / a superseding
  `resolution_decision`; because resolution is replayable from lineage, un-merge is "replay to before this
  event" (entity_registry §7.7 reversibility-as-invariant), never a destructive migration.
- **`resolver_version` stamping** ties every human verdict to the cascade version that proposed it, so a
  threshold change (R7) triggers a cheap **re-resolution campaign** rather than a migration — and the
  **P2 graph rebuild (D7)** makes the resulting merges/splits **retroactively clean for free** (the
  incremental-graph nightmare is a no-op here; entity_registry §4 "P2 rebuild synergy").
- **Single authority (D6)**: all of the above lives **only in Postgres** (D1). Lance/LadybugDB receive
  canonical IDs on the next rebuild; the review tool never writes to a projection. This is exactly why a
  generic annotation platform can't *be* the store — it would become a second authority (the Mem0 desync
  class D6 forbids).

### 4.4 Explicitly defer / don't build
- **Don't adopt Zingg/dedupe/Splink as the resolver or store** — they are batch, irreversible, and
  provenance-free (`repo_findings` "Avoid" sections). Borrow their *UI patterns and the waterfall
  explainer*, not their engines.
- **Don't stand up a web platform in v1.** CLI queue + Postgres appends is the smallest thing that closes
  entity_registry §8.3; revisit Argilla/Label Studio only when the middle-band volume (post-R7 tuning)
  proves a single-seat CLI is the bottleneck.
- **Don't review pairs.** Pairwise queues don't scale (§2.5); cluster cards with edge-level exclude do.

**One-line summary:** ugm should **build a thin CLI cluster-review queue** that renders clusters
OpenRefine-style, explains merges with a Splink-style waterfall, captures Zingg-style 3-way verdicts, and —
the part nobody else does — **appends every verdict to `resolution_decisions` / `merge_events` in Postgres
as reversible, provenance-stamped, redirect-preserving records** (entity_registry §4; D1/D6/D7), routing
only the **blast-radius-weighted middle band** to humans (§7.2/§7.4).

---

## Sources

- Repo findings (source-verified): `registry_research/repo_findings/zingg.md` (§3 connected-components, §4
  CLI labeler), `registry_research/repo_findings/splink_dedupe.md` (waterfall/Fellegi-Sunter, dedupe
  console_label, edge-cutting clustering)
- Design docs: `plan/analysis/entity_registry.md` (§1 asymmetry, §4 mentions/decisions/merge_events, §7.2
  bands, §7.3 cluster-not-pairs, §7.4 blast radius, §7.5 health, §7.7 reversibility, §8.3 review-tooling
  open Q), `decisions.md` (D1, D4, D5, D6, D7, D12, D15, D16)
- [Splink cluster studio dashboard](https://moj-analytical-services.github.io/splink/charts/cluster_studio_dashboard.html) ·
  [comparison viewer dashboard](https://moj-analytical-services.github.io/splink/charts/comparison_viewer_dashboard.html) ·
  [waterfall chart](https://moj-analytical-services.github.io/splink/charts/waterfall_chart.html) ·
  [charts gallery](https://moj-analytical-services.github.io/splink/charts/index.html)
- [Zingg interpreting output scores](https://docs.zingg.ai/zingg/scoring) ·
  [Zingg repo](https://github.com/zinggAI/zingg)
- [OpenRefine reconciling](https://openrefine.org/docs/manual/reconciling) ·
  [reconciliation API](https://openrefine.org/docs/technical-reference/reconciliation-api) ·
  [clustering in depth](https://openrefine.org/docs/technical-reference/clustering-in-depth) ·
  [survey of reconciliation services arXiv:1906.08092](https://arxiv.org/pdf/1906.08092)
- [Prodigy review docs](https://prodi.gy/docs/review) ·
  [prodigy-recipes](https://github.com/explosion/prodigy-recipes) ·
  [record-linkage recipe (Kabir Khan)](https://medium.com/@kabirkhan1137/beyond-basic-recipes-with-prodi-gy-c8fe228e5647)
- [Argilla joins Hugging Face](https://argilla.io/blog/argilla-joins-hugggingface/) ·
  [HF acquires Argilla (aibusiness)](https://aibusiness.com/data/hugging-face-acquires-ai-software-startup-to-boost-datasets) ·
  [Argilla 2.0 release](https://argilla.io/blog/argilla-2-release/) ·
  [Argilla data model](https://docs.v1.argilla.io/en/latest/conceptual_guides/data_model.html) ·
  [Argilla annotate](https://docs.argilla.io/latest/how_to_guides/annotate/)
- [CrowdER: Crowdsourcing Entity Resolution (arXiv:1208.1927)](https://arxiv.org/pdf/1208.1927) ·
  [Entity-centric evaluation (arXiv:2404.05622)](https://arxiv.org/pdf/2404.05622) ·
  [Practitioner's guide to evaluating ER (arXiv:1509.04238)](https://arxiv.org/pdf/1509.04238) ·
  [OpenSanctions Pairs (arXiv:2603.11051)](https://arxiv.org/pdf/2603.11051) ·
  [r-HUMO (arXiv:1803.05714)](https://arxiv.org/pdf/1803.05714) ·
  [SystemER (VLDB vol12 p1794)](https://www.vldb.org/pvldb/vol12/p1794-qian.pdf)
