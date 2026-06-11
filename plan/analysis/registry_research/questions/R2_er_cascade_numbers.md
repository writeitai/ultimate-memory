# R2 — What do tiered-cascade ER systems actually achieve, with real numbers?

**Question.** Our assumed thresholds (Jaro-Winkler ≥0.92, cosine ≥0.88) are folklore. What do
classical Fellegi-Sunter, embedding, and LLM matchers actually achieve on standard ER benchmarks
(Magellan/DeepMatcher, Abt-Buy, DBLP-ACM/Scholar, WDC)? How much recall is lost to blocking? Are
our thresholds defensible? How should thresholds be set? Recommend tier ordering, where the LLM
call belongs, and how to set thresholds — tied to D1–D16.

> **Scope note.** UGM resolves *mentions → entities* (and supersession blocks on
> `(entity_id, predicate)`, D4). The benchmark literature measures *record-pair matching* (given
> two records, same or not). These are not identical tasks — UGM does clustering on top of pairwise
> decisions, and our "records" are LLM-extracted entity mentions with type + context, not clean
> tabular rows. Benchmark F1 numbers are therefore an **upper-bound proxy** for our pairwise tier
> quality, not a direct prediction. This is flagged throughout.

---

## 1. Key findings

- **Our two specific numbers are not arbitrary folklore — they are Splink's shipped defaults, but
  they are *per-field similarity cut-points inside a probabilistic model*, not standalone accept
  thresholds.** Splink's `NameComparison` ships `jaro_winkler_thresholds = [0.92, 0.88, 0.7]` and
  `EmailComparison` uses JW≥0.88 (verified in `repo_findings/splink_dedupe.md`, lines 75–79, from
  `comparison_library.py`). Crucially, in Splink **none of these is an accept/reject boundary** —
  each level just contributes a Bayes factor (m/u) to an aggregate match weight; the actual
  accept threshold is a *separately tuned* match-probability. So copying JW≥0.92 as a *standalone
  auto-merge* rule is using a number out of context: in its native system it is one piece of
  evidence, not a verdict.

- **No single threshold is defensible across entity types or datasets — the right cut varies by an
  order of magnitude in error rate depending on data cleanliness.** On clean structured
  bibliographic data, string-similarity classical methods reach ~92–98 F1 (Magellan: DBLP-ACM
  98.4, DBLP-Scholar 92.3). On textual/noisy data the *same class of method collapses*: Magellan
  Abt-Buy = **43.6 F1**, dirty Walmart-Amazon = **37.4 F1** (Ditto paper, Table 5/10). A threshold
  tuned on names will be badly wrong on product titles or addresses. This is direct evidence for
  **per-type, learned thresholds tuned against a golden set** (entity_registry.md §7.1) over a
  global constant.

- **The LLM/embedding gap over classical is largest exactly where UGM's hard cases live (textual,
  noisy, semantic-synonym, unseen entities).** GPT-4 zero-shot beats fine-tuned Ditto on
  e-commerce (Abt-Buy 95.78 vs 91.31; Walmart-Amazon 89.67 vs 86.39) and ties on bibliographic
  (DBLP-ACM 98.41 vs 99.00) (Peeters & Bizer 2023, Table 4). On clean structured data, classical
  ≈ DL ≈ LLM (DBLP-ACM is 98–99 for all three) — so on the *easy* cases the cheap tier is enough,
  and the LLM only earns its cost on the *hard residue*. This is the empirical justification for
  the cheap-first cascade (D4) with the LLM as last resort.

- **Blocking loses real recall and that loss is a tunable design parameter, not a bug to ignore.**
  Good blocking schemes on Abt-Buy land around 82–94% pairs-completeness depending on how
  aggressively you cut the candidate space: BlockingPy 0.823 recall at 1,076 candidate pairs vs
  PyJedAI 0.938 recall at 5,380 pairs (BlockingPy paper, arXiv:2504.04266). **Recall lost to
  blocking is a hard ceiling** — a pair never generated as a candidate can never be matched, no
  matter how good the downstream LLM is. UGM's blocking (D4 tiers: FTS/embedding candidate
  generation) must be measured by pairs-completeness against the golden set and tuned to a recall
  target (e.g. ≥95–98%), not assumed.

---

## 2. Evidence & detail with citations

### 2.1 The "folklore" thresholds are real defaults — but used differently than we assume

From `repo_findings/` (code archaeology, all verified against source):

| System | Mechanism | Threshold(s) | Role |
|---|---|---|---|
| **Splink** | Fellegi-Sunter Bayes factors | NameComparison JW `[0.92, 0.88, 0.7]`; Email JW `0.88`; generic JW `[0.9, 0.7]`; Cosine `[0.9, 0.8, 0.7]` | **Per-field evidence levels**, not accept thresholds. Accept = separately tuned match-probability/weight | `splink_dedupe.md` §"Comparison levels", §"Threshold semantics" |
| **Dedupe** | Logistic regression on field distances | Global accept `0.5` default | "Lower → recall, raise → precision"; no auto-optimizer in this version | `splink_dedupe.md` §"Threshold" |
| **Zingg** | Logistic regression, CV-tuned | Decision threshold searched in `{0.40, 0.45, 0.50, 0.55}` | **Learned per training run**, not fixed; no per-field thresholds in code | `zingg.md` §6 |
| **Graphiti** | 3-tier cascade | cosine floor `0.6` (candidacy); fuzzy Jaccard auto-merge `0.9`; name-entropy gate `1.5` | Deterministic auto-merge bar `0.9` is deliberately conservative; rest escalates to LLM | `graphiti.md` §1, §7 |
| **mem0** | Embedding similarity | entity merge `≥0.95` cosine | Single global merge bar, no type awareness, no adjudication | `mem0.md` §1 |
| **Cognee** | Name-hash identity + OWL fuzzy match | ontology fuzzy `cutoff=0.8` (difflib) | Identity is exact UUID5(name); 0.8 is only for ontology anchoring | `cognee.md` §1, §3 |
| **HippoRAG** | Surface-string identity + synonymy edges | synonymy KNN cosine `≥0.8` | 0.8 builds *edges, never merges*; identity is md5(normalized name) | `letta_hipporag.md` §A2 |

**Three observations that reframe our `JW≥0.92 / cosine≥0.88` assumption:**

1. **The cosine numbers in the wild span 0.6 → 0.95** depending on the *role* the number plays:
   0.6 = candidate-gathering floor (Graphiti), 0.8 = synonym-edge / ontology-anchor (HippoRAG,
   Cognee), 0.9 = conservative deterministic auto-merge (Graphiti Jaccard), 0.95 = aggressive
   auto-merge with no adjudication (mem0). **There is no single "right" cosine threshold; the right
   value depends on what the tier does with the result.** Our `cosine≥0.88` sits between
   "candidate" and "auto-merge" — it is defensible *only* if we are explicit about which it is.

2. **Splink's `0.92`/`0.88` are inside a Bayes-factor cascade, not accept boundaries.** Reading
   them as standalone auto-merge thresholds (which our design doc implies) overstates their
   strength. In Splink a JW≥0.92 name agreement is *evidence* combined with email, DOB, address,
   and a prior λ=0.0001 before any accept decision (`splink_dedupe.md` §"Concrete defaults"). The
   lesson: a high name-similarity alone should be evidence feeding aggregation, not a verdict —
   which aligns with UGM's Fellegi-Sunter-for-relations instinct (the "steal" in splink_dedupe.md).

3. **The most-cited modern systems do NOT hardcode thresholds at all** — Zingg cross-validates the
   decision threshold per training run (`{0.40–0.55}`); Dedupe learns a logistic model and lets the
   user pick the operating point. This is the strongest signal that **thresholds should be
   *learned/tuned against labeled data*, not chosen by folklore.**

### 2.2 Classical (Fellegi-Sunter / Magellan random-forest) numbers

From the Ditto paper (Li et al., VLDB 2020, ar5iv 2004.00584, Table 5/10) — Magellan is the
classical-learning baseline (random forest over string-similarity features), the closest analog to
Fellegi-Sunter / Splink-style methods:

| Dataset | Type | **Magellan (classical)** | DeepMatcher (DL) | Ditto (PLM) |
|---|---|---|---|---|
| DBLP-ACM | Structured (clean) | **98.4** | 98.45 | 98.99 |
| DBLP-Scholar | Structured | **92.3** | 94.7 | 95.6 |
| Amazon-Google | Structured | **49.1** | 70.7 | 75.58 |
| Walmart-Amazon | Structured | **71.9** | 73.6 | 86.76 |
| Abt-Buy | **Textual** | **43.6** | 62.8 | 89.33 |
| Company | Textual | **79.8** | 92.7 | 93.85 |
| DBLP-ACM (dirty) | Dirty | **91.9** | 98.1 | 99.03 |
| Walmart-Amazon (dirty) | Dirty | **37.4** | 53.8 | 85.69 |

**Conclusion (paper's own, corroborated):** classical string-similarity methods are competitive
**only on clean, structured, low-vocabulary data** (DBLP-ACM, where all three tie at ~98). They
**collapse on textual / noisy / semantic-synonym data** — Abt-Buy 43.6, dirty Walmart-Amazon 37.4,
Amazon-Google 49.1. The DeepMatcher SIGMOD-2018 paper reports the attention/DL advantage over
non-soft-alignment models is ~4.5 F1 on average but **up to 23.5 F1 on Abt-Buy**
(deepmatcher-sigmod18.pdf, via search).

**Implication for UGM:** our entity mentions are LLM-extracted from prose — they are *textual and
noisy* (the Abt-Buy/Company regime), **not** clean bibliographic rows. So the classical/fuzzy tier
will have *high precision but mediocre recall* on our data, exactly as `graphiti.md` §7 warns
("the deterministic layer is precision-oriented; recall comes from the LLM"). The cheap fuzzy tier
should be tuned for **precision (auto-accept only)** and must *escalate ambiguous/near-miss cases*
rather than auto-reject them.

### 2.3 Embedding / PLM numbers

Ditto (fine-tuned PLM) column above. Ditto reaches SOTA on every dataset and is **far more robust
on dirty/textual data** than classical (Abt-Buy 89.33 vs 43.6; dirty Walmart-Amazon 85.69 vs
37.4). In the WDC products benchmark, the language-model component alone contributes +3.41 F1 on
average across 20 settings (55.3% of Ditto's total +6.16 improvement) (search, Ditto/WDC).

**Caveat — generalization cliff:** fine-tuned PLMs do **not transfer** to unseen entity
distributions. Transferring a fine-tuned model to an unseen test set drops F1 by **36–56% for
Ditto and 22–61% for RoBERTa** (Peeters & Bizer 2023; Steiner-Peeters-Bizer 2024/2025). This
matters for UGM: a PLM matcher fine-tuned on one corpus will degrade badly on a new K2 scope/domain
unless retrained. An off-the-shelf embedding-similarity tier (no fine-tuning) sidesteps this but
gives weaker raw F1.

### 2.4 LLM matcher numbers

Peeters & Bizer, "Entity Matching using Large Language Models" (arXiv:2310.11244v4), Table 4,
**zero-shot** (no task-specific training):

| Dataset | **GPT-4 zero-shot** | Ditto (fine-tuned) | RoBERTa (fine-tuned) |
|---|---|---|---|
| DBLP-ACM | 98.41 | 99.00 | 99.14 |
| DBLP-Scholar | 89.82 | 94.31 | 93.88 |
| Amazon-Google | 76.38 | 80.07 | 79.27 |
| Walmart-Amazon | **89.67** | 86.39 | 87.02 |
| Abt-Buy | **95.78** | 91.31 | 91.21 |
| WDC Products | **89.61** | 84.90 | 77.53 |

**Headline:** GPT-4 with **zero training data matches or beats PLMs fine-tuned on thousands of
pairs**, winning on the three e-commerce/textual datasets (Abt-Buy, Walmart-Amazon, WDC) and tying
on bibliographic. Its big advantage is **generalization to unseen entities** — the exact opposite
of the PLM transfer cliff (§2.3). Cost is the catch: LLM-per-pair is expensive, which is why every
production system (Graphiti, our D4) reserves the LLM for the *unresolved residue only*.

**Cross-check against Graphiti's design (`graphiti.md` §1):** Graphiti independently arrived at
exactly this shape — deterministic exact+fuzzy auto-resolves the easy majority; the LLM is invoked
*only* for `unresolved_indices`, with type/summary context passed in, and the famous failure case
("Java" language vs "Java" island) handled by giving the LLM entity-type signals. This is
convergent evidence for our tier ordering.

### 2.5 Blocking / candidate-generation recall (the hard ceiling)

- **Metrics:** Pairs Completeness (PC) = recall of the blocking step (fraction of true matches that
  survive blocking); Reduction Ratio (RR) = fraction of the O(n²) space eliminated. There is a
  direct PC↔RR tradeoff (survey arXiv:1905.06167; minimalistinnovation.com ER benchmarking).
- **Concrete Abt-Buy numbers (BlockingPy paper, arXiv:2504.04266):**
  - PyJedAI: **0.9377 recall** at 5,380 candidate pairs.
  - BlockingPy (ANN-based): **0.8234 recall** at 1,076 candidate pairs.
  - → Cutting candidates ~5× costs ~11 points of recall. **The recall lost to blocking (here
    6–18%) is an upper bound on whole-pipeline recall** — no matcher recovers a pair that blocking
    dropped.
- **Implication for UGM (D4):** our candidate generation (FTS-blocked fuzzy, embedding-blocked) is
  itself a recall bottleneck that must be measured (pairs-completeness against the golden set) and
  tuned to a target (recommend ≥95–98% PC for the merge path, since UGM's asymmetry —
  entity_registry.md §1 — makes *missed* candidates cause silent supersession failures, D4). Graphiti
  uses cosine ≥0.6 as the candidate floor with top-15 candidates (`graphiti.md` §1) — a low floor
  precisely to protect recall, pushing the precision/recall decision downstream to deterministic+LLM
  tiers. This is the right pattern: **block loose (recall), decide tight (precision).**

### 2.6 On "are our thresholds defensible?"

- **`JW≥0.92` for names:** defensible as a *high-precision auto-accept signal for the name field*,
  because it is literally Splink's top name-comparison level and the regime (person/org names) is
  the clean-ish case where string similarity works. **Not** defensible as a standalone whole-entity
  merge decision (Splink never uses it that way; names collide — father/son, common names — which is
  why entity_registry.md §7.1 demands hard negatives in the golden set). Use it as evidence + always
  combine with type and at least one other signal, or escalate.
- **`cosine≥0.88` generically:** **weakly defensible — it is a guess in the middle of a wide
  empirical band (0.6–0.95).** The wild values cluster at 0.8 (synonym/anchor) and 0.9–0.95
  (auto-merge). 0.88 is plausible as an auto-accept floor *for some embedding model on some entity
  type*, but the literature is unanimous that the correct value is **model-specific and type-specific
  and must be calibrated** — there is no transferable constant. Treat 0.88 as a *placeholder to be
  replaced by a measured value*, not a defended choice.

### 2.7 How thresholds should be set (per-type, learned)

The evidence converges hard here:

1. **Per-type, not global.** Magellan's 98.4 (DBLP-ACM) vs 43.6 (Abt-Buy) on the *same algorithm*
   proves the operating point that works for one entity/data type is catastrophic for another. UGM
   has typed entities (D15: Person, Organization, Document, …); thresholds must be set per type
   (entity_registry.md §7.2: "band boundaries are versioned config," "tuned per entity type").
2. **Learned/tuned against a labeled golden set, with hard negatives.** Zingg cross-validates the
   threshold; Dedupe fits a logistic model and exposes the operating point; entity_registry.md §7.1
   makes the golden set a prerequisite ("a few hundred mention-pairs per entity type incl. hard
   negatives"). **Recommendation: do not ship any numeric threshold without a per-type
   precision/recall curve measured on the golden set.** The golden set is the dependency (O6) that
   gates threshold-setting — until it exists, thresholds are provisional.
3. **Three operating bands, not one cut** (entity_registry.md §7.2): auto-accept (high precision) /
   review-or-LLM (the ambiguous middle — "only the middle costs money") / auto-reject. Two
   thresholds per type, both calibrated, with the LLM/human owning the middle. This matches
   Graphiti's structure (auto-merge ≥0.9 Jaccard, else LLM) and is more honest than a single 0.5/0.88
   cut.
4. **Fellegi-Sunter aggregation for the relation/evidence side (D2), not single-field thresholds.**
   For relation/claim dedup, Splink's Bayes-factor composition (each field contributes log2 bits,
   summed against a prior) is auditable and the right model (splink_dedupe.md "Steal" #1) — it
   replaces "field X ≥ θ" with "total evidence ≥ accept-weight," which is both more accurate and
   explainable (Senzing principle, entity_registry.md §2).

---

## 3. Confidence & gaps

**Well-supported (high confidence):**
- The benchmark F1 numbers in §2.2–2.4 (Magellan/DeepMatcher/Ditto/GPT-4 per dataset) are quoted
  from the primary papers (Ditto VLDB 2020; Peeters & Bizer 2023) and are widely reproduced.
- Classical methods tie on clean structured data and collapse on textual/dirty data — multiply
  sourced (Ditto Table 5/10; DeepMatcher SIGMOD-18; explicit paper conclusions).
- LLM zero-shot ≈ or > fine-tuned PLM on textual datasets, with superior unseen-entity
  generalization; PLM transfer cliff 22–61% F1 — sourced to Peeters/Bizer and Steiner et al.
- Repo threshold facts (Splink `[0.92,0.88,0.7]`, mem0 0.95, Graphiti 0.6/0.9, etc.) are verified
  code archaeology in `repo_findings/`.
- Blocking imposes a hard recall ceiling and trades PC against RR — sourced (BlockingPy,
  arXiv:1905.06167 survey).

**Medium confidence / inference:**
- The mapping "UGM mentions resemble the Abt-Buy/textual regime more than the DBLP-ACM clean
  regime" is reasoned inference, not measured. It is plausible (LLM-extracted names from prose are
  noisy) but UGM's actual data cleanliness is unknown until the golden set exists. **If** UGM
  entities turn out clean+structured, the cheap fuzzy tier will carry more load than I assume.
- The recommended PC target (≥95–98%) is a judgment from the asymmetry argument (over/under-merge),
  not a value any cited benchmark prescribes for our exact task.

**Could not verify / gaps:**
- **No published precision/recall for the *cascade systems themselves* on standard benchmarks.**
  Graphiti, Cognee, mem0, Zingg, Splink, Dedupe **all ship without committed accuracy numbers** —
  every repo_findings file states "no accuracy/benchmark numbers in source" (graphiti.md §7,
  zingg.md §6, cognee.md §8, mem0.md §7, splink_dedupe.md, letta_hipporag.md §A7). So I **cannot**
  give you "Graphiti's cascade achieves X F1 on Abt-Buy" — that number does not exist publicly. The
  benchmark numbers are for *pairwise matchers* (Magellan/Ditto/GPT-4), which the cascades *use as
  components* but do not benchmark end-to-end. **This is the single biggest gap and worth
  flagging to the Codex cross-check.**
- Exact Magellan numbers came via the Ditto paper's re-runs (ar5iv HTML) because the original
  DeepMatcher/Magellan PDFs would not parse cleanly via fetch. The Ditto-paper Magellan column is
  consistent with the literature, but a second independent source for the exact Magellan F1 per
  dataset was not separately confirmed.
- Splink/Dedupe publish no F1 on these academic benchmarks (they target administrative data);
  treating their JW defaults as "validated on Abt-Buy" would be wrong — they are validated on UK
  census/admin linkage, a cleaner regime.

---

## 4. Recommendation for UGM

### 4.1 Tier ordering (where the LLM call belongs)

Adopt the **Graphiti-validated, D4-aligned cascade**, refined by the numbers above. Block loose,
decide tight, LLM last:

```
Tier 0 — External authority match (per type: DOI/ORCID/ISBN/registry).
         Highest precision AND highest recall when it applies. Deterministic. (entity_registry.md §4)
Tier 1 — Exact normalized match (case/whitespace/punct-folded; type-scoped).
         Auto-accept. ~free. (Cognee/HippoRAG/Graphiti all do this; D4 tier 1.)
Tier 2 — Candidate generation = BLOCKING (loose, recall-first):
         FTS-blocked fuzzy + embedding KNN (cosine floor LOW, ~0.6 à la Graphiti, top-K).
         Goal: pairs-completeness ≥95–98% measured on golden set. NOT a decision tier.
Tier 3 — Cheap scoring over candidates: per-field similarity (JW for names, cosine for
         text) COMPOSED via Fellegi-Sunter Bayes factors (Splink model, D2-aligned), plus
         the type signal and entropy gate (Graphiti: skip fuzzy on short/low-entropy names).
         Two calibrated per-type bands → auto-accept (high precision) / escalate.
Tier 4 — LLM adjudication ON THE RESIDUE ONLY (the ambiguous middle band):
         small model first, frontier model for higher blast radius, with type + attributes +
         candidate context in the prompt (Graphiti's pattern). Defensive output validation.
Tier 5 — Human review for high blast-radius merges (hub entities, entity_registry.md §7.4).
```

**Where the LLM belongs:** *only* on the unresolved middle band after Tiers 0–3, never on the easy
majority. Justification from numbers: on clean cases classical ≈ LLM (DBLP-ACM all ~98), so the LLM
adds cost without accuracy there; the LLM only earns its keep on textual/noisy/ambiguous pairs
(Abt-Buy GPT-4 95.78 vs classical 43.6) — which is exactly the residue Tiers 0–3 cannot resolve.
This keeps write-side LLM cost scaling with *ambiguity, not volume* (D4 consequence, verbatim).

### 4.2 How to set thresholds (concrete, actionable)

1. **Block the golden set first (O6 / entity_registry.md §7.1).** A few hundred labeled
   mention-pairs *per entity type*, including hard negatives (same-name father/son, common names).
   This is a hard prerequisite — **ship no numeric threshold before it exists.** (Ties to open
   question entity_registry.md §8.2.)
2. **Replace both folklore numbers with measured per-type bands.** For each type, plot
   precision/recall vs threshold on the golden set and pick: an **auto-accept** cut at the precision
   target (recommend ≥0.99 precision for auto-merge given the over-merge asymmetry, §1) and an
   **auto-reject** cut; everything between escalates to Tier 4. `JW≥0.92` and `cosine≥0.88` become
   *initial guesses to be overwritten by these curves*, type by type, model by model.
3. **Per-type, versioned config (D5/D15 machinery).** Store band boundaries as registry rows keyed
   by entity type + resolver version (entity_registry.md §7.2). Person-name thresholds ≠
   Organization ≠ Document thresholds — the Magellan 98.4-vs-43.6 spread is the proof.
4. **Use Fellegi-Sunter composition for relation/claim dedup (D2), not single-field cuts.** Steal
   Splink's `predict.py`/`comparison_level.py` Bayes-factor math (splink_dedupe.md "Steal" #1) plus
   term-frequency adjustment (rare-value agreement weighted higher). This is auditable (each merge
   decomposes into per-field log2-bit contributions — satisfies the Senzing "explainable" principle,
   entity_registry.md §2) and replayable (deterministic — D4/D7 friendly).
5. **Measure blocking recall as a first-class metric.** Track pairs-completeness per type on the
   golden set; tune candidate generation (FTS/embedding top-K, cosine floor) to a recall target.
   Because UGM's asymmetry makes a missed candidate cause silent supersession failure (D4: false
   negatives in resolution = missed supersessions), bias blocking toward recall (low floor, à la
   Graphiti 0.6) and let downstream tiers handle precision.

### 4.3 Ties to decisions

- **D4 (cheap-first cascade):** the numbers *validate* it — classical handles the easy majority,
  LLM handles the residue where it's 2× better (Abt-Buy). The one refinement: insert an explicit
  **loose blocking tier with a measured recall target** before the cheap scoring tier, and make the
  cheap tier *escalate* rather than auto-reject ambiguous near-misses (because classical recall on
  our likely-textual data is mediocre — Magellan 43.6 on Abt-Buy).
- **D2 (Fellegi-Sunter / evidence aggregation):** confirmed as the right model for the relation
  side; adopt Splink's Bayes-factor composition over single-field thresholds.
- **D5/D15 (governed predicate/type vocabulary):** the type signal is what makes LLM dedup safe
  (Graphiti's "Java language vs island" fix is to pass types) — domain/range + entity types are a
  *quality lever for resolution*, not just for extraction.
- **D6/D7 (rebuild-first projection):** deterministic, replayable scoring (Fellegi-Sunter,
  seeded MinHash) is essential so re-resolution campaigns are batch jobs, not migrations
  (entity_registry.md §4). Avoid Zingg/mem0-style non-deterministic CV-tuned thresholds that shift
  per run and can't be audited (zingg.md §7 "avoid", mem0.md §8 "avoid").
- **entity_registry.md §7 (quality machinery):** golden set → per-type bands → cluster-level review
  with weak-edge cutting (Dedupe's hierarchical clustering, not Splink/Zingg blind connected-
  components transitive closure) → blast-radius guard. The threshold-setting recommendation is a
  direct instantiation of §7.1–7.2.

### 4.4 For the Codex cross-check

The most likely point of disagreement: **there are no published end-to-end accuracy numbers for any
cascade ER system** (Graphiti/Cognee/mem0/Zingg/Splink/Dedupe all ship without committed F1). Any
claim that "system X's cascade achieves Y F1 on benchmark Z" should be treated as unverified — the
real numbers belong to the *pairwise component matchers* (Magellan/Ditto/GPT-4), not the cascades.
Our recommendation rests on (a) those component numbers and (b) convergent *architectural* evidence
(Graphiti's independently-derived identical cascade), not on a benchmarked cascade.

---

## Sources

- Li et al., *Deep Entity Matching with Pre-Trained Language Models (Ditto)*, VLDB 2020 —
  [arXiv:2004.00584](https://arxiv.org/pdf/2004.00584) / [ar5iv HTML](https://ar5iv.labs.arxiv.org/html/2004.00584) (Magellan/DeepMatcher/Ditto F1 tables)
- Peeters & Bizer, *Entity Matching using Large Language Models*, 2023 —
  [arXiv:2310.11244v4](https://arxiv.org/html/2310.11244v4) (GPT-4 zero-shot vs PLM, Table 4; PLM transfer cliff)
- Steiner, Peeters, Bizer, *Fine-tuning LLMs for Entity Matching*, 2024/2025 —
  [arXiv:2409.08185](https://arxiv.org/html/2409.08185v2) (generalization, cost)
- Mudgal et al., *Deep Learning for Entity Matching: A Design Space Exploration (DeepMatcher)*,
  SIGMOD 2018 — [PDF](https://pages.cs.wisc.edu/~anhai/papers1/deepmatcher-sigmod18.pdf) (DL vs Magellan gap)
- Papadakis et al., *A Survey of Blocking and Filtering Techniques for Entity Resolution* —
  [arXiv:1905.06167](https://arxiv.org/pdf/1905.06167) (PC/RR metrics)
- *BlockingPy: approximate nearest neighbours for blocking* —
  [arXiv:2504.04266](https://arxiv.org/pdf/2504.04266) (Abt-Buy blocking recall numbers)
- ER benchmarking metrics overview —
  [minimalistinnovation.com](https://www.minimalistinnovation.com/post/benchmarking-datasets-metrics-entity-resolution)
- UGM repo_findings (verified code archaeology): `splink_dedupe.md`, `zingg.md`, `graphiti.md`,
  `cognee.md`, `mem0.md`, `letta_hipporag.md`; design docs `entity_registry.md`, `decisions.md` (D1–D16).
