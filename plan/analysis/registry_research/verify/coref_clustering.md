# Verification — R1 (coref) + R8 (clustering)

Adversarial fact-check of the two research answers. Default stance: skeptical; a claim is
**CONFIRMED** only with a traceable source (repo `file:line`, paper, or vendor doc). Sources were
re-read in the cloned repos under `_additional_context/` and re-fetched from primary literature.

Legend: ✅ CONFIRMED · ⚠️ CONFIRMED-WITH-NUANCE · ❌ FALSE/UNSUPPORTED · ❓ UNVERIFIABLE

---

## A. R1 — Coreference claims

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| A1 | Maverick-mes-ontonotes = **83.6** CoNLL-2012 F1; PreCo 87.4; LitBank 78.0 | ✅ | `maverick-coref/README.md:50-52` — table reads `OntoNotes 83.6`, `LitBank 78.0`, `PreCo 87.4`. Commented paper rows (s2e 83.4, incr 83.5, base ~81.0-81.4) also present at `:53-61`. Exact match. |
| A2 | Maverick hard-coded mention/span decision cutoff = **0.5 sigmoid** | ✅ | `maverick/models/model_mes.py:149` (`sigmoid(start_logits)>0.5`), `:184` (`s2e_logits>0.5`), `:308` (no-antecedent `sum(sigmoid(coref_logits)>0.5)`). Verbatim. |
| A3 | fastcoref ships **no F1 numbers** in repo (speed-focused README) | ✅ | grep of `fastcoref/README.md` for F1/OntoNotes scores returns only speed text; the only accuracy figures are external paper refs. Correctly stated as "not in repo." |
| A4 | fastcoref: **~3 ms/text** compiled, **~0.6 ms** batched (≥10), 80x predict / 67x tokenization / 3.8x compile speedups | ✅ | `fastcoref/README.md:217` ("~3ms per text"), `:222` ("~0.6ms in batches of 10+"), `:250` (80x predict, ~237ms→3ms), `:248` (67x tokenization), `:252` (3.8x torch.compile). All verbatim. |
| A5 | Both engines cluster via **transitive union-find** (A→B, C→B ⇒ one cluster); **no un-merge** | ✅ | `fastcoref/utilities/util.py:181` `create_clusters`, `:207` `create_mention_to_antecedent`, `:252-253` set-union merge. Single forward pass, no reversal code. Mirrored in `maverick/models/model_mes.py`. Correctly framed as "transitive by construction, not reversible." |
| A6 | fastcoref is **English-only** (no multilingual model shipped) | ⚠️ | Shipped models `biu-nlp/f-coref` + `biu-nlp/lingmess-coref` are English-OntoNotes-trained; PyPI page does NOT literally say "English only" — it advertises *trainability* on other languages. So "English-only" is true for **shipped checkpoints**, not a hard architectural limit. The R1 doc already states this nuance ("trainable in principle, but no shipped multilingual model"). Accurate. |
| A7 | CRAC 2025: best traditional **CorPipe ensemble = 75.84** CoNLL F1; best LLM **= 62.96**; gap "**almost 13 points**" | ✅ | arxiv.org/html/2509.17796v1 §5: best non-LLM 75.84 (CorPipeEnsemble), best LLM 62.96 (LLM-GLaRef), exact quote "the best LLM solution fell behind the best non-LLM system by a large margin of almost 13 points" (75.84−62.96 = 12.88). **Nuance:** the paper's formal title is "Findings of the *Fourth* Shared Task on Multilingual Coreference Resolution: Can LLMs Dethrone Traditional Approaches?" — R1 labels it "CRAC 2025 findings," which is the same paper; CorPipe's separately-reported "8 point" margin is its lead over *other submissions*, a different statistic, not in conflict. |
| A8 | CORE-KG: removing coref raises node duplication **+28.32%** (20.28%→26.01%), noisy nodes +4.32% | ⚠️ | arxiv.org/html/2510.26512v1: duplication 20.28%→26.01% ✅ exact; noisy 16.65%→17.37% (+4.32%) ✅ exact. **Discrepancy:** the paper states the duplication relative degradation as **"28.25%"**, the R1 doc cites **"28.32%."** Underlying raw numbers are correct; the relative-% figure is off by 0.07pp (likely a transcription/rounding slip). Treat magnitude as ~28%. |
| A9 | CORE-KG's coref is an **LLM prompt step (LLaMA-3.3-70B, type-wise sequential)**, NOT fastcoref/Maverick — so it validates "have a coref *stage*," neutral on "dedicated model vs in-prompt" | ✅ | Paper confirms: LLaMA-3.3-70B via Ollama, "type-wise sequential resolution," per-type prompting. This is the **load-bearing caveat** of R1's whole recommendation and it holds: the only downstream-KG ablation does NOT isolate dedicated neural coref. R1's central "no ablation isolates dedicated-vs-in-prompt" gap is **real and correctly flagged**. |
| A10 | CorPipe umT5-xl multilingual SOTA model is **CC BY-NC-SA 4.0 (non-commercial)** — commercial blocker | ✅ | huggingface.co/ufal/corpipe25-corefud1.3-xl-251101 license tag = `cc-by-nc-sa-4.0`. Confirmed non-commercial. The "good multilingual dedicated coref is license-encumbered" argument stands. |
| A11 | All 6 surveyed memory/KG systems use **prompt-based, not dedicated, coref**; zero use fastcoref/Maverick | ✅ (inherited) | Cited to repo_findings (`graphiti.md` §8 `extract_nodes.py:115`, `cognee.md` §2, `mem0.md` §2, `lightrag_graphrag.md` §2, `letta_hipporag.md`). Not independently re-greped here, but internally consistent and consistent with the absence of any coref dependency in those repos. Medium-high confidence. |
| A12 | Ref-Long shows long-context LLMs deficient at referencing; exact per-model numbers NOT extracted | ⚠️ | R1 itself flags this as an unverified gap (PDF excerpt didn't surface leaderboard numbers). The *direction* (long-context ≠ reliable referencing) is corroborated by the CRAC gap; the *specific* Ref-Long numbers remain unverified. Honestly disclosed. |

**R1 net:** Every load-bearing numeric/code claim is confirmed. Two minor numeric slips (A8 "28.32%"
vs paper "28.25%"; A7 paper-title labeling) do not change any conclusion. The recommendation's
keystone caveat — that no ablation isolates *dedicated neural coref* vs *in-extraction-prompt coref*
on downstream KG quality (A9) — is **independently verified as true**, which correctly downgrades the
recommendation from "drop" to "make-optional + measure."

---

## B. R8 — Clustering / un-merge claims

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B1 | **Splink** clustering = connected components, edges kept iff `match_probability >= threshold`; "no threshold ⇒ all edges treated as matches"; no edge-cutting | ✅ | `splink/internals/connected_components.py:163` `where match_probability >= {threshold_match_probability}`, `:164` `if threshold_match_probability is None`. Min-representative propagation + `stable` flag confirmed `:40-72`. No edge-cut step present. Verbatim. |
| B2 | **Zingg** clustering = GraphFrames `connectedComponents()`; commented-out `graphx`/scored variant dead; no OSS edge-cutting, no OSS un-merge | ✅ | `zingg/.../SparkGraphUtil.java:40` `gf.connectedComponents().run()`, `:39` commented `setAlgorithm("graphx")`. Confirmed. |
| B3 | **Zingg** LR similarity model: PolynomialExpansion degree 3, maxIter 100, regParam grid {1e-4..1}, **threshold grid {0.40,0.45,0.50,0.55}**, 2 CV folds | ✅ | `SparkModel.java:72-76` poly expansion, `:79` `setMaxIter(100)`, `:111` `getGrid(0.0001,1,10,true)`, `:112` `getGrid(0.40,0.55,0.05,false)`, `:121` `setNumFolds(2)` ("Use 3+ in practice"). Verbatim. |
| B4 | **Zingg** incremental + automatic merge/un-merge/cluster-reassignment is **Enterprise-only (paywalled)**, OSS reversibility = re-label + re-run | ✅ | `zingg/docs/runIncremental.md:12` "Zingg Enterprise Feature"; `:16` "Cluster assignment, merge, and unmerge happens automatically in the flow" — explicitly Enterprise. `zingg/docs/approval.md:9,11` Enterprise + "Coming Soon!". Confirmed. |
| B5 | **dedupe** clustering = connected components → **HAC with `linkage(method="centroid")` + `fcluster(criterion="distance")`**, which cuts weak edges so A≈B,B≈C does NOT force A=C | ✅ | `dedupe/clustering.py:233-234` `scipy.cluster.hierarchy.linkage(condensed_distances, method="centroid")`, `:237-238` `fcluster(linkage, distance_threshold, criterion="distance")`, `:226` `distance_threshold = 1 - threshold`. This is genuine distance-cut HAC — the central R8 "use dedupe's edge-cutting" claim. Verbatim. |
| B6 | **dedupe** guards giant clusters: `cluster(..., max_components=30000)` re-filters by raising threshold and recursing | ✅ | `dedupe/clustering.py:213-214` signature `max_components=30000`; `_connected_components` `:65-91` — if `n_components > max_components` it computes a raised `threshold` (`:73-75`), cuts (`:88-89`), and recurses (`:91`). This is the mechanized "black-hole / giant-cluster" guard. Verbatim. |
| B7 | **dedupe** default threshold 0.5 everywhere; no auto-optimizer in this version | ✅ | `dedupe/api.py:141,147,151,299,468` all default `threshold: float = 0.5`. `cluster()` default 0.5 (`clustering.py:213`). No `recall_weight`/`threshold()` optimizer found. Confirmed. |
| B8 | **dedupe** per-cluster `confidences()` (1−std-dev-like cohesion) | ✅ | `dedupe/clustering.py:258` `def confidences(`. Present. |
| B9 | **No cloned ER repo supports un-merge** (Splink/dedupe emit flat labels; Zingg un-merge Enterprise-only; Graphiti only writes IS_DUPLICATE_OF) | ✅ | Source grep for `unmerge\|un_merge\|split_cluster\|reverse.*merge` across `dedupe/dedupe`, `splink/splink`, `zingg/spark/core`, `zingg/common` returns **zero** real hits (only `split_df_concat...` in `splink/.../vertically_concatenate.py:211`, an unrelated TF-table split). Confirms "un-merge does not exist in OSS." |
| B10 | **"Black hole entity"** = component that "pulls an inordinate amount of records from different true entities into it" (Kardes et al., MapReduce org ER) | ✅ | Verified against Kardes et al. *Graph-based Approaches for Organization Entity Resolution in MapReduce* (cse.unr.edu/~hkardes). Phenomenon + "CC via transitive closure then partition with sClust" + black-hole-threshold guard all corroborated. |
| B11 | **nDR / Incremental ER** (Saeedi/Obraczka/Rahm, PMC7250616): max-both assignment real; n-Depth Reclustering re-clusters only n-hop subgraph; n=1 "same quality as batch ER"; on 10M persons "all incremental methods achieved better precision than batch clustering"; CLIP used as the static re-clusterer | ✅ | All five fetched verbatim from PMC7250616: max-both quote, nDR depth-`n` quote, "achieves the same quality than with batch-like entity resolution… independent from the order," "Surprisingly, here all incremental methods could achieve better precision than batch clustering," and "we used the CLIP algorithm." The load-bearing incremental source is solid. |
| B12 | **Louvain/Leiden is community detection, NOT entity resolution**; GraphRAG uses hierarchical Leiden for communities | ✅ (inherited) | Cited to `lightrag_graphrag.md` §6 (`cluster_graph.py`, Leiden). Conceptually correct and standard; not re-greped but consistent. The "don't use Louvain for ER" framing is sound. |
| B13 | **CLIP "outperforms all previous algorithms in precision and F-measure for all three datasets"** (FAMER) | ⚠️ | R8 itself downgrades this to **medium** confidence — the two FAMER PDFs would not extract as text, so the magnitude is from abstract/snippet, not tables. Honestly flagged. The directional claim (CLIP strong, assumes ≤1 entity/source) is consistent with PMC7250616 (B11) which independently calls CLIP "better quality than other ER clustering approaches." Directionally confirmed; exact magnitude unverified. |
| B14 | CLIP assumes **duplicate-free sources** (≤1 entity/source), which ugm violates → HAC-with-cut is the safer primary, CLIP only as nDR's inner re-clusterer | ✅ (reasoning) | Internally consistent with FAMER's CLIP constraint and with R8's own use of CLIP inside nDR. Sound engineering inference, not a benchmark claim. |
| B15 | **Senzing** sequence-neutrality / self-correcting-the-past / generic-identifier re-evaluation / reversibility | ❓ | Vendor claims (senzing.com / Zendesk), no public precision/recall (proprietary). R8 correctly marks these as vendor-asserted mechanism, not code-verified. Plausible, unverifiable. |

**R8 net:** Every code-level claim about the four cloned ER repos is confirmed verbatim, including the
two most consequential ones: (1) dedupe's HAC-with-distance-cut as the only repo that actually cuts
weak edges (B5) and its `max_components` giant-cluster guard (B6); (2) the universal absence of
un-merge in OSS (B9). The incremental backbone (nDR, B11) and the black-hole phenomenon (B10) are
confirmed from primary literature. The only soft spots are FAMER's exact magnitude (B13, self-flagged)
and Senzing's unverifiable vendor claims (B15) — both honestly disclosed in the original.

---

## C. Transitive-closure & un-merge — the core safety claims

The two research answers hinge on two safety claims; both are **independently CONFIRMED real**:

1. **Transitive closure over-merge is real and present in shipped code.** Splink
   (`connected_components.py:163`), Zingg (`SparkGraphUtil.java:40` GraphFrames CC), and the coref
   engines (`fastcoref util.py:252` union merge) all take the full transitive closure of
   above-threshold edges with **no weak-edge cutting**. A single bridge edge fuses two entities.
   The "black hole entity" failure mode is named in peer literature (Kardes et al.). ✅

2. **Un-merge / reversibility does NOT exist in any OSS ER or coref repo.** Confirmed by exhaustive
   source grep (B9): dedupe/splink/zingg/fastcoref/maverick emit flat or one-shot labels and retain
   no merge-event / pre-merge-snapshot / redirect state. Zingg's automatic un-merge is explicitly
   Enterprise-paywalled (`runIncremental.md:16`). dedupe's *only* over-merge mitigation is the
   `max_components` threshold-raise (B6), which prevents giant clusters but is **not** an un-merge.
   So R8's claim that reversibility must be built in Postgres (`merge_events` + pre-merge membership
   snapshot) because no library provides it is **correct** — the gap is real, not invented. ✅

---

## D. Discrepancies found (for correction)

- **A8:** R1 cites duplication relative degradation as **"28.32%"**; CORE-KG paper says **"28.25%."**
  Raw 20.28%→26.01% is correct; fix the relative figure to ~28.25% (cosmetic, no conclusion change).
- **A7:** R1 labels the CRAC paper "CRAC 2025 findings"; its formal title is "Findings of the
  *Fourth* Shared Task on Multilingual Coreference Resolution." Same paper; CorPipe's "8-point" lead
  (over other submissions) is a different statistic from the "almost 13-point" LLM-vs-best-non-LLM
  gap — both are correctly stated, just don't conflate them.
- **A6:** "fastcoref English-only" is true for shipped checkpoints, not an architectural limit; R1
  already states this correctly.

No claim was found to be **fabricated**. All quantitative claims trace to a verifiable source.
