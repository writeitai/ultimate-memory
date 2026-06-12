# R7 — Cheapest path to a labeled ER evaluation/training set + active learning

**Question.** Cheapest path to a labeled entity-resolution (ER) eval/training set and active learning:
LLM-generated candidate pairs + human verification; active-learning sampling
(uncertainty / query-by-committee); how big a golden set per entity type before threshold tuning is
statistically meaningful; semi-synthetic data. Tie to objection **O6** (no eval loop). Recommend a
concrete bootstrapping plan: build the golden set, size it, feed it into threshold tuning and
regression testing, and decide whether quality metrics ship with v1.

**Scope note / load-bearing distinction.** ugm needs **two distinct labeled assets**, and the
research conflates them at its peril:
- a **GOLDEN EVAL SET** — used to *measure* precision/recall and tune the tier thresholds & band
  boundaries (entity_registry §7.1–7.2; O6). Must be an *unbiased* sample so the numbers generalize.
- a **TRAINING SET** — only needed *if* ugm trains a learned matcher (Splink m/u, a dedupe/Zingg LR,
  or a fine-tuned SLM). Active learning (uncertainty / query-by-committee) optimizes *this*, and an
  AL-sampled set is **deliberately biased toward the boundary** so it is **invalid for measuring**
  generalization performance. Keep them separate. This is the single most important design point in
  this answer.

---

## 1. Key findings

- **Active learning cuts labeling ~3–4× for the *training* set, not for the eval set.** A published
  record-linkage study (EHR, dual-threshold) reached parity-or-better with a random **10,000-pair**
  trainer using **~2,500–3,100 actively-sampled pairs** (probabilistic: better than 10k after 2,500
  pairs/7 iterations; deterministic: ~3,089 pairs/22 iterations) [PMC3900213]. All three repos we
  cloned implement the same uncertainty/disagreement sampler: dedupe's query-by-committee
  `DisagreementLearner.pop()`, Zingg's "lowest-scoring positives + highest-scoring negatives"
  (~20 boundary pairs/round). Their own UX targets are tiny: dedupe's CLI implies **~10 pos + 10 neg**
  for a *usable* model; Zingg bootstraps from **≤5 positives**.
- **The cheapest *labels* are LLM-proposed, human-verified — but the cheapest *trustworthy* large
  golden set is still expert-reviewed.** The strongest 2024–25 result (OpenSanctions, **755,540**
  labeled pairs) was **human-analyst labeled**, with LLMs *benchmarked against* the humans (GPT-4o
  98.95% F1, a distilled 14B open model 98.23% F1, rule baseline 91.33%) — explicitly **not** used to
  generate the ground truth [OpenSanctions arXiv:2603.11051]. The viable cheap pattern is the CHI'24
  **human–LLM collaborative** loop: LLM proposes a label + explanation, a verifier scores confidence,
  humans re-annotate only the *low-confidence* subset [CHI'24 3641960]. This maps cleanly onto ugm's
  existing Tier-5 adjudicator (small model → frontier) producing *proposed* verdicts that a human
  spot-checks.
- **Statistically meaningful golden-set size is governed by binomial CIs, and it is small.** To pin a
  per-type precision/recall to a **±0.05** (5-point) 95% CI you need **~370–385 labeled instances of
  the relevant class** (worst case p≈0.5; Wald n≈ z²p(1−p)/E² = 1.96²·0.25/0.05² ≈ 384). For a looser
  **±0.10** CI, **~100** suffices [PMC12210805; tandfonline 2024.2350445; MeasuringU]. The normal
  approximation is only trustworthy when **n·p·(1−p) ≥ ~10** [sample-size lit]. **Critical caveat:**
  recall needs ~370 *true-positive pairs* and precision needs ~370 *predicted-positive pairs* — these
  are different denominators, and at a 0.0001 match prior (Splink default) true matches are rare, so
  you must **over-sample positives via blocking** to hit them, then re-weight (see §4). This squares
  the entity_registry §7.1 guidance ("a few hundred mention-pairs per entity type incl. hard
  negatives").
- **Semi-synthetic data is good for *plumbing and recall stress-tests*, useless as the *headline
  metric*.** GeCo-style corruptors (keyboard/OCR/phonetic/edit perturbations) and FEBRL (5,000-record
  benchmarks, known dup counts) cheaply manufacture hard positives — exactly the "same-name
  father/son", transliteration, and typo cases entity_registry §7.1 demands — and need **zero human
  labels** because the corruption process *is* the label [GeCo; FEBRL]. But synthetic error
  distributions don't match real OCR/transliteration drift, so synthetic numbers must never be the
  reported precision/recall; use them to *seed positives* and *regression-test* the resolver, not to
  certify it.
- **Verdict for O6 / v1:** ship a **small real golden eval set + per-tier precision/recall + a
  regression harness** in v1 (this is O6's "smallest when started before scale"). Defer any *learned*
  matcher and its active-learning training loop to a later phase — the deterministic/FS tiers (D4)
  need only thresholds, and thresholds need an *eval* set, not a *training* set.

---

## 2. Evidence & detail (with citations)

### 2.1 Active learning: how much it saves, and what the repos actually do

**Published quantification (the one hard number on AL for record linkage):** Optimized Dual-Threshold
ER for EHR databases [PMC3900213] tested random training sets of **2,000→10,000 pairs** vs an
AL loop starting at 2,000 and iterating:
- Probabilistic matcher: AL **beat** the 10,000-random baseline after **~2,500 pairs (7 iterations)**.
- Deterministic matcher: matched 10k-random with **~3,089 pairs (22 iterations)**.
- FIE matcher: plateaued at **~2,742 pairs (13 iterations)**.
- Their thresholding is a **dual threshold** (definite-match / manual-review / definite-non-match) —
  i.e. **three bands**, optimized by particle-swarm to force PPV=NPV=1 on the labeled set. This is
  *exactly* ugm's three-confidence-band model (entity_registry §7.2; auto-accept / review /
  auto-reject), independently arrived at in the EHR literature. Strong external corroboration of D-level
  design.

**Repo-confirmed AL mechanisms (from repo_findings — source-verified):**
- **dedupe** (`splink_dedupe.md`): `DisagreementLearner` runs two learners and `pop()` selects the
  next pair by (1) classifier-thinks-match-but-no-blocking-rule-covers, else (2) covered pairs near a
  random confidence target, else (3) **max classifier disagreement (`numpy.std`)** — textbook
  query-by-committee. Seed = **4 synthetic exact-match positives + 1 random negative**; CLI implies
  **~10 pos + 10 neg** for a usable model. Three-way labels `match/distinct/unsure`.
- **Zingg** (`zingg.md`): `TrainingDataFinder` — once ≥5 pos & ≥5 neg exist, trains an interim model
  and queues **~20 boundary pairs/round** (10 lowest-scoring predicted-positives + 10 highest-scoring
  predicted-negatives = uncertainty sampling). Bootstraps positives by self-join when ≤5 exist. CLI
  shows live class-balance and a 3-way verdict (0 no / 1 yes / 2 not-sure). Editable labels
  (`updateLabel`).
- **Splink** (`splink_dedupe.md`): unsupervised EM for m/u — *no labels required to train*, but
  repo_findings explicitly warns its quality is "un-auditable until you have a labeled set anyway".
  So even the no-label path needs the eval set.

**Caveat the repos themselves flag (repo_findings "Avoid" sections):** an AL-sampled set is biased to
the decision boundary, and dedupe/Zingg both produce **flat clusters via transitive closure** with no
edge-cutting (Splink CC, Zingg GraphFrames `connectedComponents`) — i.e. these are *training/scoring*
tools, not the system of record. ugm's contribution (merge_events, redirects, cluster-level review;
entity_registry §4, §7.3) sits above them.

### 2.2 Cheapest labels: LLM-propose / human-verify (and why pure-LLM labels are unsafe as ground truth)

- **OpenSanctions Pairs** [arXiv:2603.11051]: **755,540** human-labeled pairs (293 sources, 31
  countries, >1M entities), blocking via inverted index on shared name fragments/identifiers/phones,
  **76.9% positive / 23.1% negative** (blocking biases toward likely matches — note this for §4). LLMs
  were **evaluated**, not used to label: rule baseline **91.33% F1**, DeepSeek-R1-Distill-Qwen-14B
  **98.23%**, GPT-4o **98.95%**, Llama-3.1-8B **95.94%**. Authors stress labels "reflect expert
  judgments under incomplete evidence rather than definitive ground truth." **Inference (flagged):**
  if frontier LLMs hit ~99% F1 on expert pairs, an LLM is an excellent *first-pass labeler*, but using
  its own output to *measure itself* is circular — hence human verification on the sampled eval set.
- **Human–LLM collaborative annotation** [CHI'24 10.1145/3613904.3641960]: LLM labels + explanations →
  a verifier scores them → humans re-annotate only the **low-verification-score subset**. This is the
  cheapest credible recipe: humans touch only the uncertain tail. Directly reusable as ugm's golden-set
  build loop, and it *reuses the Tier-5 adjudicator ugm is building anyway* (entity_registry §4).
- LLM-guided weak supervision (LEMONADE/BoostER/BATCHER family) [sciencedirect S0950705125022725;
  search synthesis] reduces token cost via batching + selective verification + Bayesian refinement —
  relevant *later* if ugm trains an SLM matcher; over-engineering for v1.

### 2.3 How big a golden set before threshold tuning is statistically meaningful

This is a **binomial-proportion CI** problem, not an ER-specific one. Precision and recall are each a
proportion estimated on a finite labeled sample; CI width is what makes a tuning number "meaningful."

- Sample size for a target 95% CI half-width E (Wald): **n ≈ z²·p(1−p)/E²**, worst case p=0.5:
  - **E = 0.10 → n ≈ 96–100**
  - **E = 0.05 → n ≈ 384**
  [MeasuringU Wald calculator; tandfonline 2024.2350445; PMC12210805 "Extended sample size
  calculations for evaluation of prediction models using a threshold."]
- Normal approximation valid when **n·p(1−p) ≥ ~10** [sample-size search synthesis]; near p≈1
  (a good matcher) use **Wilson/Agresti-Coull**, not Wald, or the interval is wrong [Statistics How To;
  classification-confidence-intervals PyPI]. **Flag:** for a high-precision resolver (p≈0.97), Wald
  understates the needed n and mis-centers the interval — Wilson is mandatory.
- **The denominator trap (load-bearing):** recall's denominator is *true-positive pairs*; precision's
  is *predicted-positive pairs*. ER classes are extremely imbalanced (Splink default prior 0.0001 =
  1-in-10,000 random pairs match; repo_findings). A naive random sample of pairs is almost all
  negatives and yields ~0 positives — useless for recall. You must **draw positives through blocking**
  (over-sample candidate pairs) and **stratify**, then report per-stratum. entity_registry §7.1's
  "a few hundred mention-pairs per entity type incl. hard negatives" lands exactly in the **~100
  (±0.10) to ~385 (±0.05) per measured class per type** band — well-supported.

**Practical synthesis (inference from the above, flagged as a recommendation not a literature
constant):** **~200 labeled pairs per entity type** (≈100 hard positives incl. synthetic
father/son/translit + ~100 hard negatives) gives ±0.07–0.10 CIs per type — enough to *set* band
boundaries; grow to ~400/class for the types that go to production-critical auto-merge.

### 2.4 Semi-synthetic data

- **GeCo** [dl.acm 10.1145/2505515.2508207]: generates personal data and corrupts it with
  keyboard/OCR/phonetic/edit-distance functions and lookup tables — manufactures realistic typo/variant
  pairs whose match label is known by construction (zero human labeling).
- **FEBRL** [search synthesis]: FEBRL2 = 5,000 records (4,000 orig + 1,000 dup), FEBRL3 = 5,000
  (2,000 orig + 3,000 dup) — standard small benchmarks with known dup counts; a common protocol corrupts
  ~50% of records via GeCo.
- **Use / don't-use:** use synthetic positives to (a) seed the AL bootstrap (mirrors dedupe's "4
  synthetic exact-match positives" and Zingg's self-join positives), (b) build *recall stress-tests* and
  *regression canaries* (entity_registry §7.6 "canary entities"), (c) cover rare-but-known hard cases
  (transliteration, married names, suffix Jr/Sr). **Do not** report synthetic precision/recall as the
  headline; synthetic error distributions are not the production distribution.

---

## 3. Confidence & gaps

**Well-supported (high confidence):**
- Binomial CI sizing math (~100 @ ±0.10, ~384 @ ±0.05, npq≥10, use Wilson near p≈1) — standard
  statistics, multiple sources.
- Active-learning ~3–4× labeling reduction for *training* sets, and the concrete ~2,500–3,100-pair
  numbers — directly from a peer-reviewed record-linkage paper [PMC3900213].
- The AL mechanisms in dedupe/Zingg/Splink — **source-verified** in repo_findings (file/line cites).
- OpenSanctions: pure-LLM labels not used as ground truth; LLM-vs-human F1 figures — from the paper.
- The eval-set-vs-training-set distinction and the AL-bias-invalidates-measurement point — textbook
  active-learning theory; high confidence.

**Moderately supported (medium):**
- The "~200 pairs/type, grow to ~400 for production-critical types" recommendation — a *synthesis* of
  the CI math + entity_registry §7.1, not a single cited constant. The exact split (how many positives
  vs negatives, how many "hard") is a judgment call.
- Human–LLM-collaborative loop as ugm's cheapest credible build path — well-precedented [CHI'24] but
  ugm-specific cost numbers are unknown.

**Gaps / could not verify:**
- **No public number for golden-set size *as a function of number of entity types*** — total budget
  scales ~linearly with type count, but cross-type sharing (core-parent fallback, D15) could cut it;
  unverified. Inference only.
- **No source gives a per-tier threshold for ugm's specific Tier 0–5 cascade** — those must be
  *measured* against the golden set (entity_registry §8.2 open question; explicitly an O6 dependency).
  I did not invent any threshold numbers.
- **LLM-as-labeler accuracy on ugm's own domain** (mixed-type, multilingual, our ontology) is unknown;
  OpenSanctions ~99% F1 is on *sanctions* data and may not transfer. Flagged.
- Could not find a benchmark on **cluster-level** (vs pair-level) golden-set sizing — most literature
  is pairwise, while entity_registry §7.3 wants cluster-level review. Real gap; ugm is ahead of the
  literature here and will need to define its own cluster-eval metric (e.g. B³, CEAF) — *names
  mentioned as standard ER cluster metrics but not verified against a source in this pass.*

---

## 4. Recommendation for ugm (concrete, tied to D1–D16 / O5 / O6)

**Bootstrapping plan — ship in v1 (answers O6 "start before scale"):**

1. **Build the golden EVAL set, LLM-propose / human-verify, blocking-stratified.**
   - Candidate generation: reuse the **D4 cheap-first cascade itself** (Tier 1–3: exact → FTS-blocked
     fuzzy → phonetic) to emit candidate pairs — this over-samples positives so recall has a non-empty
     denominator (the §2.3 denominator trap). Mirrors OpenSanctions inverted-index blocking and Splink
     `block_on`.
   - Labeling loop: **Tier-5 adjudicator proposes** (small model → frontier; entity_registry §4) a
     verdict + short rationale; a human verifies only the **low-confidence / disagreement** subset
     [CHI'24 pattern]. Use a **3-way verdict (match / no / not-sure)** + editable labels — steal
     verbatim from dedupe/Zingg; "not-sure" keeps ambiguous pairs out of the metric.
   - Per **entity type** (the 8 core types, D15): **~200 labeled pairs** (~100 hard positives incl.
     synthetic father/son/translit/married-name; ~100 hard negatives), **grown to ~400/class** for any
     type that reaches production auto-merge. This yields ±0.07–0.10 CIs per type per the binomial math.
   - **Hard negatives are the asymmetry insurance** (entity_registry §1: over-merge is catastrophic):
     load the set with same-name-different-person and acquisition-≠-merge cases (Instagram/Meta,
     entity_registry §3).

2. **Semi-synthetic augmentation (zero-label).** Run a GeCo-style corruptor over real canonical names
   to manufacture typo/OCR/phonetic/transliteration positives → seed the set's hard-positive quota and
   the **canary regression suite** (entity_registry §7.6). Never report synthetic numbers as the
   headline metric.

3. **Feed thresholds & bands (closes entity_registry §8.2, O5).** Tune **each D4 tier threshold** and
   the **three band boundaries** (auto-accept / review / auto-reject, §7.2) against measured per-type
   precision/recall with **Wilson** CIs. Adopt the EHR paper's **dual-threshold** framing
   [PMC3900213] — it independently validates ugm's three-band design. **Band boundaries are versioned
   config** (D5/§7.2) and stamped with `resolver_version` (entity_registry §4).

4. **Regression harness + canaries (closes O6).** On every prompt/model/resolver change
   (`resolver_version`, tracked like D12 prompt/embedding versions), re-run the golden set + canary
   entities and diff precision/recall/F1 per type. Because resolution is **re-adjudicable**
   (entity_registry §4) and the graph is a **rebuild-first projection** (D6/D7), a threshold change is
   a cheap re-resolution campaign + rebuild — not a migration. This is the eval *steering wheel* O6
   asks for.

5. **Quality metrics that SHIP with v1 (O5/O6 "day one"):** per-type resolution precision/recall/F1
   with CIs; merge-proposal acceptance rate; `other:` predicate volume (D5); plus the cheap continuous
   health metrics (entity_registry §7.5) — cluster-size distribution (giant-cluster alarm), singleton
   rate per type (under-merge), unresolved-mention rate. These are SQL over the registry, near-free.

**Defer past v1 (explicitly):**
- A **learned matcher** (Splink m/u EM, dedupe/Zingg LR, or fine-tuned SLM) and its **active-learning
  training set**. v1's D4 tiers are deterministic/FS-style and need only *thresholds* (an eval set),
  not a *trained classifier* (a training set). When/if a learned tier is added, *then* stand up the
  uncertainty/QBC loop (dedupe `pop()` / Zingg ~20-boundary-pairs) — and keep that AL-sampled training
  set **separate from the eval set** so measurement stays unbiased.

**One-line summary:** v1 ships a **small (~200/type), blocking-stratified, LLM-proposed/human-verified
eval set + Wilson-CI per-tier metrics + a canary regression harness** — cheap, statistically
defensible, and exactly the steering wheel O6 demands; active-learning training is a later, separable
phase that must never reuse the eval set as its trainer.

---

## Sources

- [Optimized Dual Threshold Entity Resolution for EHR — Training Set Size and Active Learning (PMC3900213)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3900213/)
- [OpenSanctions Pairs: Large-Scale Entity Matching with LLMs (arXiv:2603.11051)](https://arxiv.org/html/2603.11051v1)
- [Human-LLM Collaborative Annotation through Effective Verification of LLM Labels (CHI 2024, 10.1145/3613904.3641960)](https://dl.acm.org/doi/10.1145/3613904.3641960)
- [Weakly-supervised entity matching via LLM-guided data augmentation (ScienceDirect S0950705125022725)](https://www.sciencedirect.com/science/article/abs/pii/S0950705125022725)
- [Extended sample size calculations for evaluation of prediction models using a threshold (PMC12210805)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12210805/)
- [Binomial Confidence Intervals for Rare Events (The American Statistician, 2024.2350445)](https://www.tandfonline.com/doi/full/10.1080/00031305.2024.2350445)
- [MeasuringU — Wald Confidence Interval Calculator for a Completion Rate](https://measuringu.com/calculators/wald/)
- [Estimating the Performance of Entity Resolution Algorithms (arXiv:2210.01230)](https://arxiv.org/pdf/2210.01230)
- [Deep Indexed Active Learning for Matching Heterogeneous Entity Representations (VLDB, arXiv:2104.03986)](https://arxiv.org/pdf/2104.03986)
- [GeCo: an online personal data generator and corruptor (ACM 10.1145/2505515.2508207)](https://dl.acm.org/doi/10.1145/2505515.2508207)
- [(Almost) All of Entity Resolution (arXiv:2008.04443)](https://arxiv.org/pdf/2008.04443)
- [Entity Resolution Benchmarking: Datasets + Metrics Beyond F1](https://www.minimalistinnovation.com/post/benchmarking-datasets-metrics-entity-resolution)
- Repo findings (source-verified): `registry_research/repo_findings/splink_dedupe.md`, `zingg.md`, `graphiti.md`
- Design docs: `entity_registry.md` (§7.1–7.6, §8), `decisions.md` (D4, D5, D6, D7, D15, D16), `objections.md` (O5, O6)
