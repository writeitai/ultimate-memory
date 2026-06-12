# Zingg (zinggAI/zingg) — Repo Findings

Source-of-truth read of the cloned repo at `_additional_context/zingg/`. Zingg is an ML-based
entity-resolution / master-data tool running on Apache Spark (Java core, `common/` =
engine-agnostic, `spark/` = Spark bindings; a `snowflake/` path also exists via the abstraction).
**No LLM anywhere** — grep for `openai|gpt-|langchain|llm|bert|embedding` across `common`/`spark`
`*.java` returns nothing. The whole system is supervised ML (logistic regression over
string-similarity features) plus a human-in-the-loop active-learning labeler. Relevant to ugm:
this is the **probabilistic-record-linkage / batch** archetype mentioned in `entity_registry.md`
§2 ("Good for backfill campaigns; wrong as the primary online mechanism") — confirmed here.

---

## 1. Same-vs-different decision: ML classifier, not deterministic, not LLM

Two learned models (README "Key Zingg Concepts"):

1. **Blocking model** — a learned decision tree of hash functions that indexes near-similar
   records so Zingg compares ~0.05–1% of the N² pairs (README).
2. **Similarity model** — a **logistic-regression classifier** that, within a block, predicts
   match / no-match per record pair.

The classifier is in
`spark/core/src/main/java/zingg/spark/core/model/SparkModel.java`. The exact pipeline:

- Per field-pair, similarity functions produce features (`SparkTransformer` → `z_simN` columns).
- `VectorAssembler` → `PolynomialExpansion` **degree 3** (lines 72–76) → `LogisticRegression`.
- LR config (lines 78–85): `setMaxIter(100)`, `setFitIntercept(true)`, probability + prediction
  cols.
- **Hyperparameter grid + cross-validation** (`applyFitPipeline`, lines 110–123):
  - `regParam` grid = `getGrid(0.0001, 1, 10, true)` → geometric: `{0.0001, 0.001, 0.01, 0.1, 1}`.
  - `threshold` grid = `getGrid(0.40, 0.55, 0.05, false)` → `{0.40, 0.45, 0.50, 0.55}` (the
    LR decision threshold is itself tuned).
  - `CrossValidator … setNumFolds(2)` (comment: "Use 3+ in practice"),
    `BinaryClassificationEvaluator` (default metric = areaUnderROC).
- Output decision is discrete: `predict()` → `z_prediction` ∈ {0.0 no-match, 1.0 match}
  (`common/.../util/ColValues.java`: `IS_MATCH_PREDICTION=1.0`, `IS_NOT_A_MATCH_PREDICTION=0.0`,
  `IS_NOT_SURE_PREDICTION=2.0`, `IS_NOT_KNOWN_PREDICTION=-1.0`). A continuous `z_score` is the
  probability extracted from the LR probability vector (`VectorValueExtractor`).

**Verdict mechanism is purely the trained LR** — there is no rule table, no external authority,
no LLM adjudication. The only "threshold" is the cross-validated LR cutoff (0.40–0.55 search
band). Match filtering is hard: `common/.../filter/PredictionFilter.java` keeps only rows where
`z_prediction == 1.0` (no configurable score band at output time in this OSS code).

### Similarity functions (the features)
`common/.../feature/StringFeature.java` maps a field's declared `matchType` → sim functions:
- `FUZZY` → **AffineGap + JaroWinkler** (`addSimFunctionsForFuzzyString`).
- `TEXT` → Jaccard (`JaccSimFunction`); `NUMERIC` → `NumbersJaccardFunction`;
  `EXACT` → `StringSimilarityFunction`; plus `PINCODE`, `EMAIL`, `NUMERIC_WITH_UNITS`
  (`ProductCodeFunction`), `NULL_OR_BLANK`, `ONLY_ALPHABETS_FUZZY/EXACT`, `DONT_USE`
  (`common/.../client/MatchTypes.java`).
- JaroWinkler is delegated to `com.wcohen.ss.Jaro` (SecondString lib) —
  `common/.../similarity/function/SJaroWinkler.java` is an empty subclass. The functions emit a
  **continuous [0,1] similarity**, not a thresholded boolean — thresholding is left to the LR.

**No fixed per-field thresholds exist in code** (e.g. no "JaroWinkler > 0.9"); all cutoffs are
learned. This is the opposite of ugm's tiered cheap-first cascade (D4) where thresholds are
explicit, versioned config.

---

## 2. Blocking architecture (the "scale" half) — learned tree of hash functions

This is the most transferable idea. Files: `common/.../block/Block.java`, `Canopy.java`,
`Tree.java`, `util/BlockingTreeUtil.java`, `util/Heuristics.java`, `hash/*`.

- Zingg learns a **blocking tree** (canopy-clustering style) rather than hand-written blocking
  keys. `Block.getBlockingTree()` (the "Holy Grail of Standalone", line 224) greedily picks, at
  each node, the **hash function + field** that best splits the data while keeping true-duplicate
  pairs together.
- "Hash functions" are coarsening transforms in `common/.../core/hash/`: `First2CharsBox`,
  `First3CharsBox`, `FirstChars`, `LastChars`, `LastWord`, `Round`, `RangeInt/Dbl/Long`,
  `TrimLastDigits*`, `TruncateDouble`, `IsNullOrEmpty`, `Identity*`, etc. (declared via
  `HashFnFromConf` / `HashFunctionRegistry`). They map a field value to a block key.
- **Greedy selection metric** (`Block.getBestNode`): for each candidate function compute
  `elimCount` = how many *known-duplicate* training pairs would be split apart
  (`Canopy.estimateElimCount`, lines 237–262: applies the hash to both sides of a labeled pair;
  if the two hashes differ the pair is "eliminated"). Pick the function with the **smallest
  elimCount** (fewest true dupes broken) that still yields `childrenSize > 1` (actually
  partitions the data). I.e. **maximize blocking reduction subject to not separating known
  matches** — a precision/recall-aware blocking learner driven by the labeled set.
- **Recursion stop = block size heuristic** (`Heuristics.getMaxBlockSize`, exact code):
  ```java
  MIN_SIZE = 8L;
  maxSize = (long)(0.001 * totalCount);          // target 0.1% of total per block
  if (maxSize > blockSizeFromConfig) maxSize = blockSizeFromConfig;
  if (maxSize <= MIN_SIZE)           maxSize = MIN_SIZE;   // floor at 8
  ```
  So a block keeps subdividing until it holds ≤ max(0.1% of N, 8) records (capped by config).
- At match time the tree is serialized and applied to every record (`Block.applyTree`) to emit a
  `z_hash`; records sharing a hash form a block; pairs are generated only within a block
  (`Matcher.getActualDupes` → `joinWithItself(blocked, HASH_COL)`).

**Why it scales:** comparisons drop from O(N²) to within-block only. README claims "0.05–1% of
the possible problem space"; `hardwareSizing.md` gives real numbers (see §7).

---

## 3. Clustering / merge — connected components over predicted-match edges

File: `spark/core/src/main/java/zingg/spark/core/util/SparkGraphUtil.java` (+ interface
`common/.../util/GraphUtil.java`, builder `match/output/GraphMatchOutputBuilder.java`).

- After the classifier predicts matching **pairs**, Zingg builds a graph: vertices = records,
  edges = predicted matches, then runs **GraphFrames `connectedComponents()`** (line 40). Each
  connected component = one cluster = one resolved entity; the component id becomes
  `z_cluster` (`CLUSTER_COLUMN`).
- **This is exactly the "never trust transitive closure" pitfall** flagged in
  `entity_registry.md` §7.3 and `decisions.md` D-analysis: connected components takes the full
  transitive closure — A≈B, B≈C ⇒ A,B,C all merged into one cluster, **even though A and C were
  never compared or were predicted non-matching**. There is **no edge-weight cutting / no
  correlation-clustering / no Louvain** in the OSS path. The commented-out
  `setAlgorithm("graphx")` (line 39) and a dead scored-graph variant exist but the live code is
  plain connected components.
- Cluster scores: `getMinMaxScores` (GraphMatchOutputBuilder, lines 113–165) attaches min/max
  pairwise score per cluster; pairs the graph discovered transitively but the classifier didn't
  score get a **dummy score 0.0** (line 134) — an implicit signal that those are weak/inferred
  cluster members.
- **No automatic un-merge / split in OSS.** Reversibility is only via re-labeling +
  retraining + full re-run (batch). `runIncremental.md` states automatic merge/unmerge/cluster
  reassignment and preservation of human-approved records — but it is gated **"Zingg Enterprise
  Feature"** (proprietary, not in this repo). `approval.md` ("Approve Clusters") is also
  Enterprise and marked "Coming Soon!".

---

## 4. Human-in-the-loop: active-learning labeler (the most relevant UX)

Files: `common/.../executor/TrainingDataFinder.java`, `Labeller.java`,
`LabelDataViewHelper.java`, `TrainingDataModel.java`, `LabelUpdater.java`, `FindAndLabeller.java`.
Phases (`client/options/ZinggOptions.java`): `findTrainingData`, `label`, `train`, `match`,
`link`, `trainMatch`, `updateLabel`, `findAndLabel`, `recommend`, `generateDocs`.

### Uncertainty sampling (active learning) — `TrainingDataFinder.execute()`
- Bootstraps positives: if user has ≤5 positive pairs, it **self-joins random samples on
  `z_zid`** to synthesize positive pairs (a record matches itself) — `getPositiveSamples`,
  `posPairs.count() <= 5` (line 68).
- Once ≥5 pos **and** ≥5 neg labeled pairs exist (line 109), it trains an interim
  `SparkLabelModel` and predicts over freshly blocked sample pairs, then selects the **most
  uncertain pairs near the decision boundary** (`getUncertain`, lines 167–182):
  - predicted-match pairs sorted **ascending** by score → take **lowest-scoring 10**
    (`pos.limit(10)`);
  - predicted-no-match pairs sorted **descending** by score → take **highest-scoring 10**
    (`neg.limit(10)`).
  - → ~20 boundary pairs per round are queued for the human. This is classic
    **uncertainty-sampling active learning**.
- Cold start (no labels yet): emit ~20 random blocked pairs marked
  `prediction = -1 (UNKNOWN)`, `score = 0` (lines 128–136), `20.0 / blocks.count()` sampling.
- Sample size from config: `args.getLabelDataSampleSize()` (`data.sample(false, fraction)`).

### The CLI review loop — `Labeller.processRecordsCli` + `LabelDataViewHelper.displayRecords`
- Records are shown **vertically** (field-by-field, two records side by side) via
  `VerticalDisplayUtility` — matching README's "labelvertical.gif".
- Prompt shows a header: `"Current labelling round : %d/%d pairs labelled"` and
  `"Zingg predicts the above records %s with a similarity score of %.2f"` (LabelDataViewHelper
  `getMsg2`, lines 74–86 — score floored to 2 decimals).
- Three-way choice + quit (`displayRecords`, lines 96–105), read by `readCliInput` which only
  accepts regex `[0129]`:
  ```
  No, they do not match : 0
  Yes, they match       : 1
  Not sure              : 2
  To exit               : 9
  ```
  Mapped to `ColValues.MATCH_TYPE_NOT_A_MATCH=0 / MATCH=1 / NOT_SURE=2`,
  `QUIT_LABELING=9`. Choices are stored on `z_isMatch`.
- **Running stats shown every pair** (`printMarkedRecordsStat`): "Labelled pairs so far :
  %d/%d MATCH, %d/%d DO NOT MATCH, %d/%d NOT SURE" — gives the labeler a live sense of class
  balance. (Note `totalCount = markedRecords.count()/2` since each pair is two rows.)
- README pitch: "active learning that builds models on **frugally small training samples** to
  high accuracy" — explicitly positioned against Fellegi-Sunter and entity-centric matching.

### Correction workflow — `LabelUpdater` (`updateLabel` phase)
- Lets a human revisit already-marked clusters **by cluster id** and re-label
  (`update()`, lines 60–93). Updating a label decrements the old class counter and increments the
  new (`getUserInput` lines 132–133) → the labeled set is itself editable. This is the only
  "correction" affordance in OSS, and it acts on **training labels**, not on production output
  clusters (production cluster correction = Enterprise approval flow).

**Pattern worth stealing for ugm review tooling (Open Q §8.3 in entity_registry.md):** the
uncertainty-sampling queue (20 boundary cases/round) + 3-way verdict (match/no/not-sure) +
live class-balance stats + editable labels is a clean, minimal review UX. Note Zingg reviews
**pairs**, not clusters — the doc's §7.3 ("review clusters, not pairs") is a deliberate
*divergence* ugm should keep.

---

## 5. Ontology / type system / coreference / temporal — mostly N/A

- **Ontology / predicates / domain-range:** **not found.** Zingg has no relations, no
  predicates, no graph of facts. Its only "type system" is per-field `matchType` (FUZZY, EXACT,
  EMAIL, PINCODE, NUMERIC, …) declared in `config.json` `fieldDefinition[]` (see
  `examples/febrl/config.json`) — these pick similarity functions, not semantic types. There is
  **no entity typing** (Person/Org/…); every row is the same opaque "record".
- **Coreference handling:** **not found.** Zingg resolves whole structured records, not mentions
  in text. There is text preprocessing (`preprocess/stopwords/RemoveStopWords`, `trim`,
  `casenormalize`) but no pronoun/coref resolution.
- **Extraction / claims / prompts / JSON-schema / gleaning:** **not found / N/A.** Input is
  already-structured tabular data (CSV/DB/Parquet via the `Pipe` abstraction). There is no
  extraction step and no LLM prompting of any kind.
- **Temporal / bi-temporal / validity windows / supersession:** **not found** in OSS. There are
  bookkeeping cols `z_updated`, `z_updated_real`, `z_action`, `z_user`, `z_modelId`
  (`client/util/ColName.java`) hinting at incremental lineage, but the bi-temporal /
  supersession / cluster-reassignment logic lives in **Zingg Enterprise** (`runIncremental.md`,
  not in this repo). So Zingg contributes **nothing** to ugm's E3 bi-temporal model (D3) or
  supersession cascade (D4) directly.

---

## 6. Concrete numbers / parameters present in code

| Parameter | Value | Source |
|---|---|---|
| Polynomial feature expansion degree | **3** | `SparkModel.java:75` |
| LR max iterations | **100** | `SparkModel.java:79` |
| LR `regParam` CV grid | **{1e-4, 1e-3, 1e-2, 0.1, 1}** (×10 geometric) | `SparkModel.java:111` |
| LR `threshold` CV grid | **{0.40, 0.45, 0.50, 0.55}** | `SparkModel.java:112` |
| Cross-validation folds | **2** ("use 3+ in practice") | `SparkModel.java:121` |
| Target block size | **0.1% of total** (`0.001 * totalCount`), floor **8**, capped by config | `Heuristics.java:9-19` |
| Comparison space claim | **0.05–1%** of N² | README |
| Active-learning queue per round | **~20** pairs (10 lowest-pos + 10 highest-neg by score) | `TrainingDataFinder.java:174,180` |
| Positive bootstrap threshold | **≤5** pos pairs → synthesize | `TrainingDataFinder.java:68,110` |
| Cold-start random sample | **20 / blocks.count()** | `TrainingDataFinder.java:129` |
| Match output filter | `z_prediction == 1.0` only | `PredictionFilter.java:25` |

### Performance / scale (from `docs/setup/hardwareSizing.md`, verbatim)
- 120k records (febrl120k): **5 min** on 4-core / 10 GB local Spark.
- 5M records (NC Voters): **~4 h** on 4-core / 10 GB local Spark.
- 9M records, 3 fields: **45 min** on AWS m5.24xlarge (96 cores, 384 GB).
- 80M records, 8–10 fields: **<2 h** on 1 driver (128 GB, 32 cores) + 8 workers (224 GB,
  64 cores) — user-reported, unoptimized.
- CI perf tests exist for febrl120K and ncVoters5M (README badges).
- **No accuracy/precision/recall benchmark numbers** are committed in the repo (only timing).

---

## 7. Steal vs avoid (for ugm)

### Steal
1. **Learned blocking tree.** The greedy "pick the hash fn that splits data most while breaking
   the fewest labeled-duplicate pairs" objective (`Block.getBestNode` + `Canopy.estimateElimCount`)
   is a principled, **label-driven** way to derive blocking keys instead of hand-tuning them. ugm's
   FTS/phonetic blocking (D4 tiers 2–3) is currently hand-specified; this is a way to *learn*
   block keys against the golden set (`entity_registry.md` §7.1).
2. **Uncertainty-sampling review queue.** Surface only boundary cases (≈20/round: lowest-confidence
   positives + highest-confidence negatives). Directly answers Open Q §8.3 "Review tooling: where do
   merge proposals surface?" — sample near the decision boundary, not randomly. Maps onto ugm's
   middle confidence band (§7.2: "only the middle costs money").
3. **Three-way verdict incl. an explicit "not sure".** Match / no-match / **not-sure** / quit. The
   not-sure class keeps ambiguous pairs out of training rather than forcing a wrong label — good for
   golden-set hygiene.
4. **Editable labels (`updateLabel`).** Treats the labeled set as correctable state, not immutable
   — aligns with ugm's "resolution is re-adjudicable" (entity_registry §4) but at the *training*
   level.
5. **Live class-balance feedback** during labeling (pos/neg/not-sure running counts) — cheap UX win
   that keeps a human from over-labeling one class.
6. **Engine-agnostic core (`common/` vs `spark/`, `snowflake/`).** ZFrame abstraction lets the same
   ER logic target Spark or Snowflake — a clean separation pattern if ugm ever needs multiple
   execution backends.

### Avoid
1. **Connected components for clustering.** This is the textbook **transitive-closure over-merge**
   trap (`entity_registry.md` §1 "over-merging poisons it catastrophically", §7.3 "never trust
   transitive closure"). One spurious bridge edge fuses two real entities into one giant cluster,
   and OSS Zingg has **no edge-cutting and no un-merge**. ugm must use correlation-clustering /
   weak-edge-cutting and keep merges reversible (D7 rebuild, Wikidata-style redirects).
2. **No external-authority / deterministic Tier-0.** Everything rides one LR classifier; there's no
   cheap exact/authority short-circuit (ORCID/DOI/registry). ugm's Tier-0 (entity_registry §4) is a
   deliberate improvement.
3. **Pairwise review, not cluster review.** Zingg labels pairs; the doc's §7.3 prescribes
   cluster-level review for scale. Keep the queue cluster-centric in ugm.
4. **Reversibility & incremental ER are paywalled.** Merge/unmerge/cluster-reassignment +
   human-approval persistence are Enterprise-only (`runIncremental.md`, `approval.md`). The OSS
   reversibility story is "re-label and re-run the batch" — unacceptable as ugm's online mechanism
   (matches entity_registry §2 verdict: probabilistic batch linkage is "wrong as the primary online
   mechanism").
5. **Non-deterministic, hard-to-audit decisions.** CV-tuned LR threshold (0.40–0.55) means the
   accept boundary shifts per training run; there's no stable, versioned threshold config to audit
   or replay. ugm wants explicit, versioned band boundaries (§7.2).
6. **No provenance of *why* two records merged.** Output is cluster ids + min/max scores; there's no
   per-merge evidence record (contrast Senzing's "every merge records why", entity_registry §2). ugm's
   `merge_events` append-only design (entity_registry §4) is the corrective.
