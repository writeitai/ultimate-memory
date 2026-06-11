# R1 — Is a separate coreference-resolution step still warranted in 2026?

**Question.** Keep, drop, or make-optional a *dedicated* coreference-resolution stage (Maverick / fastcoref) in the ugm **E2 claim-extraction** pipeline, vs. letting the long-context extraction LLM resolve pronouns/anaphora implicitly?

**Scope note.** "Coref" here = *intra-document* mention clustering / pronoun-and-definite-NP grounding that feeds the `mentions` transcript before claim extraction (`entity_registry.md` §8.7 open Q; D4 "coreference resolution runs before claim extraction"). This is **not** cross-document entity resolution — that is the registry's tiered ER (D4, `entity_registry.md` §4), a separate concern. Conflating the two is the most common framing error here, so this answer keeps them apart throughout.

---

## 1. Key findings

- **None of the surveyed production memory/KG systems run a dedicated coref engine.** Graphiti, cognee, mem0, LightRAG, Letta/HippoRAG all push coreference into the extraction LLM via prompt instructions ("disambiguate pronouns to entity names", "replace all pronouns with specific names", "avoid using pronouns"). Verified directly in the cloned repos (citations in §2). Zero of six use fastcoref/Maverick/spaCy-coref. GraphRAG has *no* coref instruction at all. So the de-facto 2026 industry answer is already "no separate coref step."
- **Dedicated coref is still measurably more accurate than prompt-based LLM coref on the coref task itself** — but the gap is narrowing and the absolute task is not the goal. At **CRAC 2025** (CorefUD 1.3, 22 datasets / 17 languages), the best traditional supervised system (CorPipe ensemble) scored **75.84 CoNLL F1** vs the best LLM system **62.96** — "**the best LLM solution fell behind the best non-LLM system by a large margin of almost 13 points**" ([CRAC 2025 findings](https://arxiv.org/html/2509.17796v1)). Long-context LLMs also fail a dedicated *referencing* benchmark ([Ref-Long](https://arxiv.org/pdf/2507.09506)), i.e. big context windows do **not** by themselves guarantee reliable reference tracking. So "LLMs resolve coref implicitly and perfectly" is **false** as stated.
- **BUT the one ablation that measures the thing we actually care about — does coref help downstream KG quality — used an LLM-prompted coref step, not a dedicated model.** CORE-KG (legal corpus, ~2k-word docs) found removing its coref module raised node duplication by **28.32%** (20.28%→26.01%) and noisy nodes by 4.32% ([CORE-KG](https://arxiv.org/html/2510.26512v1)). Crucial nuance: their coref is **LLaMA-3.3-70B prompted**, a *type-wise sequential* resolution pass — so this validates "**have a coref step**," not "**use a dedicated neural coref model.**" There is **no ablation in the evidence isolating dedicated-neural-coref vs LLM-in-extraction-prompt for downstream KG/claim quality** — this is the central gap (see §3).
- **Multilingual is the decisive practical axis, and it cuts against the dedicated tools as documented in our repo_findings.** `repo_findings/coref.md` only inventoried **English** models (fastcoref = English-only; Maverick models documented = OntoNotes/PreCo/LitBank, all English). The published Maverick *does* support multilingual (mT5: En 83.3 / Ar 68.5 / Zh 74.3 F1) and there is a German fork (`uhh-lt/maverick-coref-de`); the genuine multilingual SOTA is **CorPipe** (umT5-xl, 12–17 languages). **However the CorPipe umT5-xl model is released CC BY-NC-SA 4.0 — non-commercial** ([HF model card](https://huggingface.co/ufal/corpipe25-corefud1.3-xl-251101)), a hard blocker for a commercial product. So a *good multilingual dedicated coref* is either not what our repo_findings evaluated, or is license-encumbered.
- **Cost asymmetry favors the dedicated tool at scale, but the absolute LLM cost is small here.** fastcoref runs **local, ~3 ms/text (≈0.6 ms batched), zero API cost** (`coref.md` §5). LLM-in-extraction adds essentially **$0 marginal** because E2 already calls an LLM over the whole document — coref rides along in that same call. A *separate LLM coref pass* (CORE-KG-style) is the worst of both: extra frontier-model tokens per document at 1M-doc scale.
- **Recommendation: MAKE-OPTIONAL (default OFF for English/long-context extraction; pluggable per-language).** Rely on the E2 extraction LLM's in-context coref as the default (matches every surveyed system and D4's "coref before extraction" can be satisfied *within* the E2 call), and keep a dedicated coref engine as a registry-configurable pre-pass for (a) languages/domains where the extractor underperforms, and (b) when documents exceed the context the extractor can reliably track. Treat any coref output as **evidence/candidate groupings, never committed identity** (`entity_registry.md` §4, §7.3). Reasoning and ties to D-decisions in §4.

---

## 2. Evidence & detail (with citations)

### 2.1 What the surveyed systems actually do (all repo-verified)

| System | Coref mechanism | Source (repo finding) |
|---|---|---|
| **Graphiti** | Prompt-only. Extraction prompt: "disambiguate [pronouns] to the names of the reference entities"; edge prompt: "Facts should include entity names rather than pronouns." No coref module. | `repo_findings/graphiti.md` §8 (`extract_nodes.py:115`, `extract_edges.py:137`) |
| **cognee** | Prompt-only, intra-chunk. `generate_graph_prompt.txt` §3 "Coreference Resolution": "use the most complete identifier… throughout"; strict variant: "'he','Dr. Turing' → 'Alan Turing'". No cross-chunk coref, no resolver. | `repo_findings/cognee.md` §2 |
| **mem0** | Prompt-only. `ADDITIVE_EXTRACTION_PROMPT`: "Use [last k messages] to resolve references and pronouns… Replace all pronouns with specific names or 'User.'" Supplies last 10 messages as context. No fastcoref/spaCy-coref. | `repo_findings/mem0.md` §2 |
| **LightRAG** | Prompt-only: "avoid using pronouns such as `this article`… `he/she`." Cross-chunk coref not handled. | `repo_findings/lightrag_graphrag.md` §2 |
| **GraphRAG** | **No coref instruction at all.** | `repo_findings/lightrag_graphrag.md` §2 |
| **Letta / HippoRAG** | Prompt-only, single inline instruction: "Clearly resolve pronouns to their specific names." No coref model. | `repo_findings/letta_hipporag.md` B4 / L40-42 |

**Inference (high confidence):** the field has *already* converged on "no dedicated coref step; let the extraction LLM do it in-context." This is not an oversight — these are the most-watched memory/KG repos of 2024–2026. The convergence is itself strong evidence that the marginal value of a bolt-on coref engine, *given* a capable extraction LLM seeing the whole chunk/document, is low enough that nobody ships it.

### 2.2 Dedicated coref is still more accurate *at the coref task* (verified numbers)

- **CRAC 2025 Shared Task** (CorefUD 1.3, 22 datasets / 17 languages): best traditional **CorPipe ensemble = 75.84 CoNLL F1 / 72 CEAF-e**; best LLM system **LLM-GLaRef = 62.96 / 58**. Quote: "the best LLM solution fell behind the best non-LLM system by a large margin of almost 13 points." Fine-tuned LLMs (62.96, 59.84) beat few-shot (61.74, 60.09) but all four LLM systems trailed the encoder systems. ([CRAC 2025 findings](https://arxiv.org/html/2509.17796v1)). Title is literally "*Can LLMs Dethrone Traditional Approaches?*" — answer: not yet.
- **Maverick (dedicated)**: 83.6 CoNLL-2012 F1 English OntoNotes; mT5 multilingual variant En 83.3 / Ar 68.5 / Zh 74.3 (`coref.md` §4; [Maverick paper](https://www.researchgate.net/publication/382739385_Maverick)).
- **Ref-Long benchmark**: long-context LLMs show "significant performance deficiency" at tracking references across long documents; the benchmark exists precisely because expanded context windows do **not** imply reliable implicit reference resolution ([Ref-Long](https://arxiv.org/pdf/2507.09506)). General-purpose long-context retrieval is strong (e.g. Claude Opus long-context retrieval ~97% on needle-style tasks per [vendor-blog comparisons](https://www.mindstudio.ai/blog/gpt-54-vs-claude-opus-46-vs-gemini-31-pro-benchmarks)) — but *referencing/coref* is a distinct, harder capability that those retrieval scores do not certify. (Flagged: the Ref-Long top-model numbers weren't extractable from the PDF excerpt — see §3.)

**Caveat on transferring these numbers:** CoNLL F1 measures *full mention-cluster* agreement against OntoNotes/CorefUD annotation guidelines — including singletons, nested mentions, and nominal chains that ugm's E2 does not need. ugm needs the much narrower "ground the pronoun/definite-NP that is the subject/object of a candidate claim." An LLM can be weak at full-document cluster F1 yet adequate at the local "who does 'she' refer to in this sentence" that E2 actually requires. So the 13-point CRAC gap is an **upper bound** on the quality ugm would lose, not a direct estimate.

### 2.3 The downstream-quality evidence (the only ablation that targets KG output)

- **CORE-KG** (20 U.S. legal cases, ~2k words each, LLaMA-3.3-70B): ablating the coreference module → node duplication **+28.32%** (20.28→26.01%), noisy nodes +4.32% ([CORE-KG](https://arxiv.org/html/2510.26512v1)). Their coref is an **LLM prompt step** (type-wise sequential resolution), *not* fastcoref/Maverick. Cost of that step is **not disclosed**.
- **Reading for ugm:** this is real evidence that a coref *stage* materially reduces entity fragmentation/duplication in KG construction — directly relevant to the over-/under-merge asymmetry in `entity_registry.md` §1 (split entities → split evidence → missed supersession on `(entity_id, predicate)`, D4). But because CORE-KG's "coref" is itself an LLM pass, the experiment supports "**do coref**," and is *neutral* on "**dedicated model vs in-extraction prompt**." If the extraction LLM already resolves pronouns in its single E2 call, CORE-KG's benefit may already be captured without a second component.

### 2.4 Cost per document (verified where available)

| Option | Marginal cost / doc | Latency | Multilingual | License | Source |
|---|---|---|---|---|---|
| **In-extraction LLM coref** (default) | **~$0 marginal** (rides the existing E2 call) | none added | follows extractor (good in major langs) | n/a | surveyed systems; D2/E2 already calls LLM |
| **fastcoref (dedicated, local)** | **$0 API**, GPU/CPU compute | **~3 ms/text, ~0.6 ms batched** | **English-only** | Apache/MIT (permissive) | `coref.md` §5 |
| **Maverick (dedicated, local)** | $0 API, GPU compute | no per-doc latency published | En + multilingual variants (mT5; +German fork) | check per-model | `coref.md` §5; [Maverick](https://github.com/uhh-lt/maverick-coref-de) |
| **CorPipe umT5-xl (multilingual SOTA)** | $0 API, large GPU | not benchmarked here | **12–17 languages, SOTA** | **CC BY-NC-SA 4.0 — non-commercial ⚠** | [HF card](https://huggingface.co/ufal/corpipe25-corefud1.3-xl-251101) |
| **Separate LLM coref pass** (CORE-KG style) | **extra frontier tokens/doc** | extra round-trip | follows model | n/a | [CORE-KG](https://arxiv.org/html/2510.26512v1) |

The economically dominant *local* option (fastcoref) is exactly the one that is **English-only** — so it cannot serve ugm's multilingual ambitions (`entity_registry.md` §8.5 "Multilingual aliases and transliteration"). The multilingual SOTA (CorPipe) is **non-commercial-licensed**. Maverick multilingual is the only permissive-ish multilingual dedicated option, but its non-English models are less battle-tested and weaker (Arabic 68.5).

### 2.5 Multilingual availability — summary

- **fastcoref:** English only ([PyPI](https://pypi.org/project/fastcoref/)). Trainable on own data in principle, but no shipped multilingual model.
- **Maverick:** English SOTA; multilingual via mT5 (En/Ar/Zh numbers above); community German fork. Permissive-ish but uneven quality and our repo_findings did **not** inventory the multilingual checkpoints — flagged as a documentation gap in `coref.md`.
- **CorPipe (CRAC winner):** the real multilingual SOTA, 12–17 CorefUD languages — but **CC BY-NC-SA 4.0**, non-commercial. Code on GitHub, model on HuggingFace/LINDAT. ([CorPipe 2025](https://github.com/ufal/crac2025-corpipe)).
- **Frontier extraction LLMs:** strong implicit coref in high-resource languages, degrading for low-resource (CRAC notes low-resource langs like Romanian have poor zero-shot coref) — but they inherit whatever multilingual ability the chosen E2 model has, with **no extra integration** and no license issue.

---

## 3. Confidence & gaps

**Well-supported (high confidence):**
- All six surveyed systems use prompt-based, not dedicated, coref. (Direct repo reads.)
- Dedicated supervised coref still beats prompt-LLM coref *on the coref task* by ~13 CoNLL F1 (CRAC 2025), and long-context ≠ reliable implicit referencing (Ref-Long exists and shows deficits).
- A coref *stage* reduces KG node duplication (~28% in CORE-KG).
- fastcoref is English-only and near-free locally; CorPipe multilingual SOTA is non-commercially licensed.

**Weakly-supported / inferred (medium):**
- That ugm specifically would gain little from a dedicated engine *given* a frontier E2 extractor seeing the whole chunk. This is an inference from (a) universal industry convergence and (b) the CRAC gap being measured on full-cluster F1 (broader than E2's need), not a direct ugm ablation.
- Per-doc economics of a separate LLM coref pass at 1M docs (directional, not costed — CORE-KG didn't disclose).

**Genuine gaps (could not verify — flagged, not invented):**
- **No ablation anywhere isolating "dedicated neural coref vs in-extraction-prompt coref" on downstream KG/claim quality.** CORE-KG compares coref-vs-no-coref, both LLM. This is the experiment ugm would need to run on its *own* golden set (O6 / `entity_registry.md` §7.1) to decide definitively. **This is the single most important missing piece** and the reason the recommendation is "make-optional + measure," not "drop."
- Ref-Long exact per-model accuracy numbers (PDF excerpt didn't surface them); claim "long-context LLMs are deficient at referencing" rests on the paper's framing + the CRAC gap, both solid, but the specific Ref-Long leaderboard is unverified.
- Maverick multilingual checkpoint quality/availability beyond En/Ar/Zh/De is not deeply verified; our `coref.md` only inventoried English models.
- No public 2026 cost-per-document figure for in-context coref specifically (it is bundled into extraction cost by construction).

---

## 4. Recommendation for ugm

**Verdict: MAKE-OPTIONAL.** Concretely:

1. **Default: in-extraction LLM coref (no separate stage), for the common case.** E2 (claim extraction, Claimify-style, `concepts.md`) already issues an LLM call over the whole chunk/document. Instruct that prompt to resolve pronouns/definite-NPs to canonical surface names *in the emitted claims* — exactly what Graphiti/cognee/mem0/Letta do. This satisfies D4's "coreference resolution runs before claim extraction" **within** the E2 call (the claim never leaves E2 with a dangling pronoun), at **~$0 marginal cost**, with no English-only or license constraints. It also keeps the pipeline aligned with O3's cost-discipline concern (don't add a separate model invocation per document when the existing call can absorb the work).

2. **Keep a dedicated coref engine as a registry-configurable, per-scope/per-language pre-pass — built but default OFF.** Turn it ON when measurement (point 4) shows the extractor under-resolving, specifically: (a) **lower-resource languages** where the E2 model's implicit coref is weak (CRAC shows this is real); (b) **long documents** that exceed the span the extractor reliably tracks (Ref-Long motivates this); (c) high-blast-radius scopes (`entity_registry.md` §7.4) where duplication is costly. This is a clean fit for D15/D16: coref-engine choice becomes a **registry row per scope/language**, not a pipeline rewrite — same "edit rows, not code" philosophy as ontology extensions.

3. **Whatever produces coref, treat its output as evidence, never as a committed verdict.** Coref clusters are *candidate within-document mention groupings* that seed the `mentions` transcript (`entity_registry.md` §4) — they are **not** identity decisions and must not be inherited transitively. `coref.md` §9 and `entity_registry.md` §7.3 both warn: coref clustering is transitive-by-construction (union-find) and *not reversible*; A≈B,B≈C silently becomes A=C. So pipe coref groupings into the registry as candidate mention-links, then let the conservative tiered ER (D4, with un-merge via `merge_events`, §4) own the same-vs-different verdict. This preserves the reversibility invariant (`entity_registry.md` §7.7) that none of the dedicated coref tools offer.

4. **Resolve the decision empirically with the golden set (O6 dependency).** Before committing thresholds, run the missing ablation on ugm's labeled mention-pairs / golden documents (`entity_registry.md` §7.1, §8.2): measure E2 claim-subject/object correctness and downstream entity-duplication **with in-extraction coref only** vs **+ dedicated pre-pass**, per language. The CORE-KG 28% duplication delta says the *stage* matters; only ugm's own numbers can say whether the *dedicated* engine beats the in-prompt version enough to justify the integration, GPU, and (for multilingual) licensing cost. Wire the chosen coref `resolver_version` into provenance (`entity_registry.md` §4) so re-resolution campaigns (D7 rebuild + re-adjudication) can replay it.

5. **For multilingual specifically (the open question in §8.5/§8.7):** do **not** adopt fastcoref (English-only) as the engine; do **not** adopt CorPipe's umT5-xl model as-is in the product (CC BY-NC-SA non-commercial). If a dedicated multilingual coref is ever switched on, the realistic permissive options are Maverick's multilingual variants (verify each checkpoint's license and quality first) or training CorPipe's *code* on permissively-licensed data — both larger efforts that should be justified by point-4 measurements first. Until then, rely on the frontier E2 model's native multilingual coref.

**One-line summary:** the industry has already dropped dedicated coref in favor of in-extraction LLM coref, and ugm should follow that default — but *build the optional dedicated pre-pass* (per-language registry row) because (a) dedicated coref is still genuinely more accurate at the task, (b) low-resource languages and long documents are exactly where implicit coref fails, and (c) ugm's quality bar on the `(entity_id, predicate)` blocking key (D4) makes silent under-resolution catastrophic — then let ugm's golden-set ablation decide per-language when to flip it on.

---

## Sources

- [CRAC 2025 findings — "Can LLMs Dethrone Traditional Approaches?"](https://arxiv.org/html/2509.17796v1)
- [CORE-KG — coref ablation on KG construction](https://arxiv.org/html/2510.26512v1)
- [Ref-Long — long-context referencing benchmark](https://arxiv.org/pdf/2507.09506)
- [CorPipe at CRAC 2025](https://arxiv.org/pdf/2509.17858) · [code](https://github.com/ufal/crac2025-corpipe) · [model card (CC BY-NC-SA 4.0)](https://huggingface.co/ufal/corpipe25-corefud1.3-xl-251101)
- [Maverick paper](https://www.researchgate.net/publication/382739385_Maverick) · [German Maverick fork](https://github.com/uhh-lt/maverick-coref-de)
- [fastcoref (PyPI, English-only)](https://pypi.org/project/fastcoref/) · [F-coref paper](https://arxiv.org/pdf/2209.04280)
- [CorefUD multilingual strategies](https://arxiv.org/abs/2408.16893)
- Repo findings (local): `repo_findings/coref.md`, `graphiti.md` §8, `cognee.md` §2, `mem0.md` §2, `lightrag_graphrag.md` §2, `letta_hipporag.md` B4
- Design docs (local): `entity_registry.md` §1/§4/§7/§8, `decisions.md` D4/D5/D15/D16, `concepts.md`, `objections.md` O3/O6
