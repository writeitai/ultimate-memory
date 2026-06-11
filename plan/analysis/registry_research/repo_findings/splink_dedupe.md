# Splink & Dedupe — Repo Findings (classical ER tradition)

Code archaeology of the two cloned repos under `_additional_context/`. Everything below is
quoted/cited from actual source. Both libraries are **fully deterministic, no LLM anywhere**
(grep for `openai|anthropic|llm|gpt|claude|prompt` across `splink/splink` and `dedupe/dedupe`
returns only an unrelated JS labelling-tool file and a Spark backend file — no model calls).
These are batch, supervised/unsupervised statistical linkers — exactly the "good for backfill,
wrong as primary online mechanism" verdict in `entity_registry.md` §2.

---

## SPLINK (Fellegi–Sunter probabilistic record linkage)

### Same-vs-different decision: the math (no LLM, pure Bayes)

The whole engine is Fellegi–Sunter: each field comparison contributes a **Bayes factor**,
factors multiply against a prior, the product is converted to a match probability via a sigmoid.

`splink/internals/misc.py:21-34` — the exact conversion functions:
```python
def prob_to_bayes_factor(prob: float) -> float:
    return prob / (1 - prob) if prob != 1 else inf
def prob_to_match_weight(prob: float) -> float:
    return log2(prob_to_bayes_factor(prob))
def match_weight_to_bayes_factor(weight: float) -> float:
    return 2**weight
def bayes_factor_to_prob(bf: float) -> float:
    return bf / (1 + bf)
```

`splink/internals/predict.py:196-218` — `_combine_prior_and_bfs`: combined score is
`bf_prior * bf_term1 * bf_term2 * ...`, clamped to `[1e-300, 1e300]`, then
`match_probability = bf/(1+bf)`. `match_weight = log2(bayes_factor)`. A comparison level's
Bayes factor is `m/u` (the m-probability divided by the u-probability) —
`comparison_level.py:349-364` computes `_bayes_factor` and `_log2_bayes_factor = math.log2(bf)`.

**Plain English:** `match_weight` is in bits (log2). Each agreeing field adds bits, each
disagreeing field subtracts bits, starting from the prior. This is precisely the
"evidence aggregation" model `entity_registry.md` §1 wants for relations dedup.

### Concrete default parameters (`splink/internals/settings.py`)

| Parameter | Default | Line |
|---|---|---|
| `probability_two_random_records_match` (the prior λ) | **0.0001** | `settings.py:184` |
| `em_convergence` | **0.0001** | `settings.py:195` |
| `max_iterations` (EM) | **25** | `settings.py:196` |

The prior of 0.0001 = "two random records have a 1-in-10,000 chance of being the same entity";
it sets the base match weight before any field evidence. A warning fires if the user leaves it
at default (`settings.py:602-619`, `_lambda_is_default`).

### m/u estimation: Expectation–Maximization, unsupervised

`splink/internals/expectation_maximisation.py:245-332`. **No training labels required** (README:
"Unsupervised Learning: No training data is required"). The loop:
```python
for i in range(1, max_iterations + 1):       # default 25
    ...                                       # E-step: predict match_probability per pair
    core_model_settings = maximisation_step(...)   # recompute m & u counts
    if max_change_dict["max_abs_change_value"] < em_convergence:   # 0.0001
        break
```
`compute_new_parameters_sql` (`predict.py`/`expectation_maximisation.py:44-60`) recomputes m and
u as `sum(match_probability * count)` and `sum((1-match_probability) * count)` per comparison
vector value — classic soft-EM. Unobserved levels are flagged with the constant
`"level not observed in training dataset"` (`internals/constants.py:1`).

### Comparison levels — the fuzzy-match thresholds, baked-in presets

`splink/internals/comparison_library.py`. Splink ships opinionated out-of-the-box comparisons.
The decision is a **CASE-WHEN cascade** (most-similar level wins), each level carrying its own
m/u → Bayes factor:

- **`NameComparison`** (`:1004-1083`): default `jaro_winkler_thresholds = [0.92, 0.88, 0.7]`.
  Levels: Null → ExactMatch (with term-frequency adjustment) → JW≥0.92 → JW≥0.88 →
  (optional dmetaphone array-intersect) → JW≥0.70 → Else.
- **`EmailComparison`** (`:953-1001`): Null → exact full email (TF-adjusted) → exact username
  (regex `^[^@]+`) → JW≥**0.88** full → JW≥**0.88** username → Else.
- **`ForenameSurnameComparison`** (`:1089`): JW thresholds `[0.92, 0.88]`.
- Generic builders w/ defaults: `JaroWinklerAtThresholds`/`JaroAtThresholds`/`JaccardAtThresholds`
  default `[0.9, 0.7]`; `CosineSimilarityAtThresholds` default `[0.9, 0.8, 0.7]`;
  `LevenshteinAtThresholds`/`DamerauLevenshteinAtThresholds` default `[1, 2]`.
- `DateOfBirthComparison` (`:712`) and `AbsoluteTimeDifferenceAtThresholds` (`:420`) compare via
  absolute time deltas at configurable thresholds.

**Term-frequency adjustment** is wired into exact-match levels (e.g. `name_col` TF column) — a
rare surname agreeing is stronger evidence than a common one. This is the schema.org-style
"sharpen by frequency" idea, mechanized.

### Blocking rules (candidate generation)

`splink/blocking_rule_library.py` + `internals/blocking_rule_library.py:199`. `block_on(...)`
generates **equi-join** conditions; multiple columns → AND-compound rule:
```python
br_1 = block_on("first_name")
br_2 = block_on("substr(surname,1,2)", "surname")
```
Blocking is purely to cut the O(n²) comparison space — only pairs satisfying *some* blocking
rule are ever scored. Supports `salting_partitions` and `arrays_to_explode`.
`internals/find_brs_with_comparison_counts_below_threshold.py` and `optimise_cost_of_brs.py`
auto-suggest blocking rules whose comparison counts stay under a budget (the analogue of
ugm's FTS-blocked candidate generation, D4 tier 2).

### Clustering: connected components, SQL-native, threshold-gated

`splink/internals/connected_components.py:120` `solve_connected_components` (inspired by
arXiv:1802.09478; author's writeup `robinlinacre.com/connected_components/`).

- Edges kept iff `match_probability >= threshold_match_probability` (`:163`,
  `where match_probability >= {threshold}`); if no threshold, **all edges treated as matches**.
- Iterative "min-representative propagation": each node's rep = min over its neighbours' reps,
  with a `stable` flag when a cluster has no outgoing cross-cluster edges; loop until
  `count_of_edges_needing_processing == 0`.
- Public API `clustering.cluster_pairwise_predictions_at_threshold` (`internals/clustering.py:43`):
  "Records with an estimated match probability **at or above** `threshold_match_probability` are
  considered to be a match (i.e. they represent the same entity)."

**Critical pitfall, present in the code by design:** Splink clustering takes the *transitive
closure* of all above-threshold edges (A–B and B–C ⇒ A,B,C one cluster). This is exactly the
"never trust transitive closure" hazard `entity_registry.md` §7.3 warns about. Splink offers no
edge-cutting in plain connected-components — you control merging only via the single global
probability threshold. (There is also `one_to_one_clustering.py` for 1:1 link constraints.)

### Threshold semantics

No single hardcoded "accept" threshold — it's a user-chosen knob expressed either as
`threshold_match_probability` (0–1) or `threshold_match_weight` (bits). `predict.py:108-111`:
`where log2({bayes_factor_expr}) >= {threshold_as_mw}`. The docstrings consistently frame it as
the precision/recall dial.

---

## DEDUPE (active-learning + logistic-regression record linkage)

### Same-vs-different decision: logistic regression on field distances

`dedupe/labeler.py:79-98` (`MatchLearner`) and `dedupe/core.py:73-99`. The classifier is
`sklearn.linear_model.LogisticRegression()` (`labeler.py:83`). Each candidate pair is turned
into a **feature vector of per-field distances** (the featurizer), then
`classifier.predict_proba(features)[:, -1]` gives the match score in `[0,1]`
(`core.py:79`, `labeler.py:98`). Pairs with `score > 0` are persisted to a memmapped array
(`core.py:81-97`). This is a supervised linear model — no LLM, no Fellegi–Sunter.

Field distance functions (`dedupe/variables/string.py`): `ShortString`/`String` use
**affine-gap edit distance** (`affinegap.normalizedAffineGapDistance`) by default, or a CRF
edit distance (`highered.CRFEditDistance`) if `crf=True`; cosine for text. Other variable
types: `exact`, `categorical`, `set`, `latlong`, `price`, `exists`, `interaction`.

### Active-learning labeling (the headline feature)

`dedupe/labeler.py` — `DisagreementLearner` runs **two learners in parallel**: a `MatchLearner`
(the logistic classifier) and a `BlockLearner` (the blocking-rule learner). `pop()`
(`labeler.py:348-398`) is the uncertainty/disagreement sampler that picks the next pair to ask
a human about:
```python
decisions = probs > 0.5
uncovered_disagreement = numpy.any(decisions != decisions[:, [0]], axis=1) * (probs[:,1] == 0)
```
Priority order: (1) pairs the **classifier thinks match but no blocking rule covers** (most
valuable for recall), weighted by classifier confidence; (2) otherwise sample covered pairs
near a random confidence target; (3) otherwise pick by **classifier disagreement** (`numpy.std`
of the two learners' probabilities). This is classic query-by-committee active learning —
ask where the models disagree most.

Seeding (`labeler.py:435-452`): training is bootstrapped with **4 synthetic exact-match
positives + 1 random-pair negative** before any human input (`[1]*4 + [0]`).

The CLI labeling loop `dedupe/convenience.py:122-194` (`console_label`). The literal prompt:
```
Do these records refer to the same thing?
(y)es / (n)o / (u)nsure / (f)inished / (p)revious
```
It shows progress as `"{n_match}/10 positive, {n_distinct}/10 negative"` — the implicit target
is ~10 positive + 10 negative labels to get a usable model. Labels are `"match"/"distinct"/
"unsure"` (`convenience.py:106`).

### Blocking-rule learning (predicate selection — genuinely clever)

`dedupe/training.py:36-93` (`BlockLearner.learn`) + `dedupe/branch_and_bound.py:46`. Dedupe
*learns* its blocking rules instead of hand-coding them:

1. A large library of candidate **predicates** (`variables/string.py:12-30`): e.g.
   `wholeFieldPredicate`, `firstTokenPredicate`, `sameThreeCharStartPredicate`,
   `sameFiveCharStartPredicate`, `doubleMetaphone`, `sortedAcronym`, n-gram fingerprints, plus
   **index predicates** TF-IDF canopy (`_index_thresholds = (0.2, 0.4, 0.6, 0.8)`) and
   Levenshtein canopy at distances `(1, 2, 3, 4)`.
2. Compute each predicate's *cover* (which true-match pairs it blocks together) — `cover()`
   (`training.py:95-129`) via `predicate(record_1).isdisjoint(predicate(record_2))`.
3. `target_cover = int(recall * len(matches))` (`training.py:62`) — default **recall = 1.0**
   during active learning (`labeler.py:117-119`), meaning "find rules that block together
   *all* known dupes".
4. Optionally add **random-forest-derived conjunctions** when training data is large enough:
   `K = max(floor(log10(len(matches))), 1)`; conjunctions only added once `K > 1`
   (`training.py:77-81`) — an explicit anti-overfitting guard.
5. `branch_and_bound.search(candidate_cover, target_cover, 2500)` (`training.py:87`) — greedy
   set-cover with branch-and-bound, capped at **2500** search calls, to find the smallest
   predicate set achieving target coverage.

### Clustering: connected components → hierarchical, with edge-cutting

`dedupe/clustering.py` — notably **more conservative than Splink**:

- `cluster(dupes, threshold=0.5, max_components=30000)` (`:213`). `distance = 1 - score`.
- `connected_components` (`:20-94`) groups via `union_find` (`:97-170`), but if any component
  exceeds `max_components` (30000) it **re-filters by raising the threshold** and recurses
  (`:72-91`) — guards against runaway giant clusters (the `entity_registry.md` §7.5 "emerging
  giant cluster" alarm, mechanized).
- Within each component, **hierarchical agglomerative clustering**:
  `scipy.cluster.hierarchy.linkage(..., method="centroid")` then
  `fcluster(linkage, distance_threshold, criterion="distance")` (`:233-239`). This **cuts weak
  edges** rather than taking blind transitive closure — A≈B, B≈C does *not* force A=C if the
  centroid distance exceeds threshold. This is exactly the cluster-quality discipline
  `entity_registry.md` §7.3 asks for, and it's why dedupe is the better ER-clustering model.
- Per-record **confidence scores** (`confidences()`, `:258-281`): a 1−(std-dev-like) metric so
  whole-cluster quality can be summarized (basis for `entity_registry.md` §7.5 health metrics).

### Threshold (default 0.5 everywhere; no auto-optimizer in this version)

`dedupe/api.py`: `partition`, `cluster`, `join`, `score`, `search` all default
`threshold: float = 0.5` (`api.py:141-151`, `:299`, `:468`, `:870`). Docstrings: "Lowering the
number will increase recall, raising it will increase precision." `clustering.py:222`: same.
Note: this 3.x version has **no `recall_weight`/`threshold()` auto-optimizer method** (older
dedupe versions did; grep finds none here) — the user picks the threshold.

`gazetteMatching` (`clustering.py:299`) and `greedyMatching` (`:284`) provide 1:N and 1:1
matching modes for the record-linkage/gazetteer use cases.

---

## Steal vs Avoid (for ugm)

### Steal
1. **Fellegi–Sunter as the evidence-aggregation math for relation/claim dedup** (D2). Bayes
   factors in log2 bits compose cleanly and are *fully auditable* — every match weight
   decomposes into per-field contributions you can show a reviewer. This is the deterministic,
   replayable scoring D4 tiers 1–3 need, and it directly satisfies the "explainable merge"
   principle (`entity_registry.md` §2, Senzing lesson). `splink/internals/predict.py` +
   `comparison_level.py` are the reference implementation.
2. **Term-frequency adjustment on exact matches** — rare value agreement weighted higher. Maps
   onto ugm's instinct that a rare-surname collision is strong evidence; cheap to add to the
   tiered resolver.
3. **Dedupe's disagreement/uncertainty sampler** (`labeler.py:348-398`) — query-by-committee is
   the right way to build ugm's labeled golden set (`entity_registry.md` §7.1, O6) with minimal
   human labels (~10 pos / 10 neg gets a usable model). Steal the *active learner*, not the
   classifier.
4. **Dedupe's hierarchical-clustering-with-edge-cutting** (`clustering.py:233-239`) over blind
   connected components — directly implements "review clusters not pairs; never trust transitive
   closure" (§7.3) and `max_components` re-filtering implements the giant-cluster alarm (§7.5).
5. **Dedupe's learned predicate blocking + branch-and-bound set cover** as a way to *auto-tune*
   blocking rules against a recall target instead of hand-coding them.
6. **Splink's SQL-native connected components** — if ugm clusters in Postgres/Ladybug, this is a
   proven pattern that runs in-engine at scale (1M records/min on a laptop, per README).

### Avoid
1. **Splink's plain connected-components transitive closure** as the *only* merge mechanism — a
   single global probability threshold + transitive closure is precisely the over-merge
   catastrophe (`entity_registry.md` §1 asymmetry, §7.3). If borrowing Splink's clustering, add
   dedupe-style edge-cutting or a blast-radius guard (§7.4) on top.
2. **Both libraries are batch + irreversible by construction** — neither has merge events,
   redirects, un-merge, or per-mention decision provenance. They produce a flat cluster
   assignment, not the transcript/verdict registry of `entity_registry.md` §4. Use them as the
   *scoring/clustering engine inside* a tier, never as the system of record.
3. **EM unsupervised m/u** (Splink) is seductive ("no labels!") but its quality is
   un-auditable until you have a labeled set anyway, and it's a global batch fit — wrong for
   incremental online resolution (`entity_registry.md` §2: "wrong as the primary online
   mechanism"). Tune thresholds against the golden set (§7.1), don't trust EM blindly.
4. **Hardcoded 0.5 default thresholds** (dedupe) — meaningless without per-type precision/recall
   measurement; ugm's three confidence bands (§7.2) must be tuned per entity type, not a global
   constant.
5. **No coreference, no extraction, no ontology, no temporal model in either repo** — these are
   pure record-linkage libraries operating on already-structured rows. They contribute *nothing*
   to ugm's coref/extraction/ontology/bi-temporal needs (those open questions in §8 must be
   sourced elsewhere — graphiti/cognee/fastcoref).

## Not found (explicitly absent in both repos)
- Coreference resolution: **not found**.
- LLM / function-calling / JSON-schema extraction / prompts: **not found** (deterministic only).
- Ontology / type system / domain-range constraints: **not found** (dedupe has *variable types*
  String/Categorical/etc. for distance functions, but these are feature definitions, not an
  entity/predicate ontology).
- Temporal / bi-temporal validity windows, supersession: **not found** (Splink can compute date
  *differences* as a feature; no validity model).
- Un-merge / merge reversibility / merge-event provenance / persistent-ID redirects: **not found**
  in either — both emit flat cluster labels and forget how they got there.
- Multi-pass gleaning: **not found** (N/A — no extraction).
