# Coreference Resolution — repo findings (maverick-coref, fastcoref)

Source repos read in full:
- `_additional_context/maverick-coref/` — SapienzaNLP, ACL 2024 paper "Maverick: Efficient and Accurate Coreference Resolution Defying Recent Trends".
- `_additional_context/fastcoref/` — shon-otmazgin, AACL 2022 demo "F-COREF" (ships `FCoref` and `LingMessCoref`).

**Scope caveat for ugm:** these are *neural coreference* engines. They resolve mentions **within a single document/text** into clusters. They are **NOT entity resolution / dedup systems** — no cross-document identity, no canonical IDs, no merge/un-merge, no ontology, no bi-temporal model, no LLM, no thresholds-on-similarity dedup. They map onto exactly one open question in `entity_registry.md` §8.7 ("Coreference resolution engine choice (runs before extraction, feeds mentions)") and the design's "mentions are evidence" intake stage. Everything below answers the prompt's checklist with that framing; where a checklist item has no analog in the code, it is marked **not found**.

---

## 1. What these systems actually do (mention-cluster, not pronoun-only)

Both are **full mention-cluster** coreference resolvers, not pronoun-only. They detect *all* mention spans (noun phrases, proper names, pronouns, nominals) and partition them into clusters where each cluster = one entity referenced across the text.

Concrete output shape (maverick `README.md` L88-95):
```python
model.predict(ontonotes_format)
>>> {
  'tokens': [...],
  'clusters_token_offsets': [[(5,5),(7,8),(17,17)], [(0,1),(12,13)]],
  'clusters_text_mentions': [['Rome','The city','its'], ['Barack Obama','the president']]
}
```
`'Rome' / 'The city' / 'its'` is one cluster — a place referenced by a proper noun, a definite NP, and a pronoun. So clusters contain mixed mention types, not just pronouns.

fastcoref `README.md` L44-52 same shape: clusters as char-index span pairs or as strings, plus per-pair `get_logit(span_i, span_j)`.

**Why "pronoun-only" is a tempting misread but wrong:** both models carry a linguistic-category system that *includes* pronoun categories, but it spans the full matrix (see §3). LingMess's name = "**Ling**uistically **Mes**s" / linguistic-message-passing categories.

---

## 2. Model architecture

### Maverick (`maverick/models/`)
Three interchangeable decoder variants over a shared transformer encoder; `mes` is the released/SOTA one:
- **`Maverick_mes`** (`model_mes.py`) — "Mention-Endpoints-Sentence"-style: pipeline is (a) per-token *start* classifier, (b) for each predicted start, enumerate candidate ends **constrained to the same sentence** via an EOS mask, (c) a start-to-end mention classifier, (d) incremental antecedent clustering. Quoted decision thresholds (hard-coded, `model_mes.py`):
  - start token is a mention-start if `torch.sigmoid(start_logits) > 0.5` (L149)
  - span is a mention if `torch.sigmoid(s2e_logits) > 0.5` (L184)
  - antecedent "no-antecedent / singleton" cutoff: `1 - torch.sum(torch.sigmoid(coref_logits) > 0.5, dim=-1)...` (L308)
- **`Maverick_s2e`** (`model_s2e.py`) — start-to-end, no sentence constraint.
- **`Maverick_incr`** (`model_incr.py`) — incremental, adds a small recurrent clustering head (`incremental_model_hidden_size: 768`, `incremental_model_num_layers: 1`, `conf/model/incr/longformer-large.yaml`).

Encoder is configurable via Hydra. Released SOTA model uses **DeBERTa-v3-large** (`microsoft/deberta-v3-large`, `conf/model/mes/deberta-large.yaml` L18-19); other configs use `allenai/longformer-large-4096`, base variants exist. Speaker info injected as special tokens `[SPEAKER_START]`/`[SPEAKER_END]` (`maverick_model.py` L35).

The `mes` antecedent scorer is **bilinear, factored into 4 endpoint interactions** (start-start, end-end, start-end, end-start) **per linguistic category** (`_calc_coref_logits`, `model_mes.py` L257-275), via `einsum('bnkf, nfg, bnlg -> bnkl', ...)` with per-category weight tensors `antecedent_*_all_weights` shaped `(num_cats, hidden, hidden)`.

### fastcoref (`fastcoref/coref_models/`)
- **`FCorefModel`** (`modeling_fcoref.py`) — the fast student. Encoder **`distilroberta-base`** (training default, `soft_training/run.py`; README L170-178 distills from `distilroberta-base`). RoBERTa-family → now uses **SDPA attention** (README changelog v2.2.0).
- **`LingMessModel`** (`modeling_lingmess.py`) — the accurate teacher. Encoder **Longformer** (`config.py` notes "LingMess uses Longformer (sparse attention) which is architecturally incompatible with SDPA, so it continues using eager attention", `modeling.py` L246; `modeling_lingmess.py` L57 forces `attn_implementation="eager"`). HF id `biu-nlp/lingmess-coref`; FCoref id `biu-nlp/f-coref`.

Both fastcoref models share the same head structure as Maverick_mes (same author lineage): mention MLPs → **top-λ mention pruning** → per-category bilinear antecedent scoring. Pruning keeps `k = seq_len * top_lambda` top mentions (`_prune_topk_mentions`, `modeling_lingmess.py` L109-135); `top_lambda`, `max_span_length`, `ffnn_size`, `dropout_prob` come from `config.coref_head` (`modeling.py` L108-110, `modeling_lingmess.py` L46-49). `max_doc_len=4096`, `max_segment_len` segmented w/ a "leftovers" mechanism for long docs (`soft_training/run.py` L101-126).

**Clustering algorithm (both repos, identical logic):** greedy antecedent → cluster via union-find-style merge. `create_mention_to_antecedent` takes `coref_logits.argmax(axis=-1)`; a null column = "no antecedent" (singleton). `create_clusters` walks (mention, antecedent) pairs and unions them into clusters (`fastcoref/utilities/util.py` L181-219; mirror in `maverick/models/model_mes.py` L297-387). This is **transitive by construction** (A→B, C→B all land in B's cluster) — see §6.

---

## 3. The linguistic-category system (the "pronoun" subtlety)

Both repos define an **identical** 6-way mention-pair category taxonomy and an 8-group pronoun table:

`CATEGORIES` (fastcoref `utilities/consts.py` L21-27, maverick `common/constants.py` L59 — byte-identical):
```python
{'pron-pron-comp':0, 'pron-pron-no-comp':1, 'pron-ent':2,
 'match':3, 'contain':4, 'other':5}
```
`PRONOUNS_GROUPS` (8 groups: 1st/2nd/3rd-person singular by gender, neuter, 1st/2nd/3rd plural, demonstratives `that/this`) and `STOPWORDS` are duplicated in both repos.

`get_category_id` (maverick `common/util.py` L13-33; fastcoref `utilities/util.py` L236-256, identical) classifies each mention-antecedent pair:
- both pronouns, same group → `pron-pron-comp`
- both pronouns, different group → `pron-pron-no-comp`
- exactly one pronoun → `pron-ent`
- non-pronoun, identical word-set (minus stopwords) → `match`
- one word-set subset of the other → `contain`
- else → `other`

The model learns a **separate antecedent scorer per category** (`num_cats = len(CATEGORIES)+1`, +1 for an "ALL" head; `model_mes.py` L38). This is the LingMess thesis: pronoun-pronoun, pronoun-entity, and entity-entity links need different decision functions. **So pronouns are one cell of a full mention-vs-mention matrix, confirming mention-cluster, not pronoun-only.**

---

## 4. Accuracy (CoNLL-2012 / OntoNotes F1) — numbers present in the repos

From maverick `README.md` L48-52 (avg CoNLL-2012 F1 unless noted):

| HF model | Train set | Score | Singletons |
|---|---|---|---|
| `sapienzanlp/maverick-mes-ontonotes` | OntoNotes | **83.6** | No |
| `sapienzanlp/maverick-mes-litbank` | LitBank | 78.0 | Yes |
| `sapienzanlp/maverick-mes-preco` | PreCo | 87.4 | Yes |

Commented-out (paper-table) rows in the same README record `s2e-ontonotes` 83.4, `incr-ontonotes` 83.5, base encoders ~81. The eval script "directly output[s] the CoNLL-2012 scores" (README L215).

fastcoref repo: **no F1 numbers committed in the README or code** (the README focuses on speed). Paper figures (F-COREF ~78–79, LingMess ~81 OntoNotes) are **not found in-repo** — only referenced via the AACL citation. State as "not in repo."

Takeaway for ugm: Maverick-mes-ontonotes at **83.6 CoNLL-2012 F1** is the strongest single number physically present; PreCo 87.4 is higher but PreCo guidelines differ (README L62 warns annotation guidelines differ per dataset — choose by use case).

---

## 5. Speed / cost per document — numbers present in the repos

fastcoref is the speed play; numbers are in `README.md` "Performance" (L205-262):
- with `compile_model=True`: first call ~6s one-time `torch.compile`, **subsequent calls ~3ms per text**.
- **batched per-text cost drops to ~0.6ms in batches of 10+**.
- `max_tokens_in_batch` (default **10000**, `modeling.py` L245) trades speed vs VRAM vs accuracy.
- v2.2.0 changelog claims **80x faster predict()** (removed HF `Dataset.from_dict()`+`.map()` overhead, ~237ms→~3ms), **67x faster tokenization** (spacy runs tokenizer only, all pipeline components excluded — `_SPACY_EXCLUDE`, `modeling.py` L28), **SDPA 2-4x attention**, **torch.compile 3.8x forward**.
- Runs on CPU or CUDA; model dtype `torch.bfloat16` (`modeling.py` L145).
- Memory hygiene: `pred.release_logits()` frees the `[max_k, max_k+1]` float32 logit matrix (lazy storage, fixes accumulation of "hundreds of MB" — changelog).

Maverick: no per-doc latency numbers committed; paper's selling point is "efficient" (small coref head, no expensive higher-order inference). **Latency figures not found in maverick repo.** No $ cost anywhere — these are **local GPU/CPU models, zero API/per-token cost** (the key economic contrast with the LLM-per-entity approaches surveyed in `entity_registry.md` §2 Graphiti row).

---

## 6. API usage (concrete, copy-pasteable)

### Maverick
```python
from maverick import Maverick
model = Maverick(hf_name_or_path="sapienzanlp/maverick-mes-ontonotes", device="cuda:0")
out = model.predict(text_or_word_tokens_or_sentences)  # 3 input formats auto-detected
```
Notable params (`maverick_model.py predict()` L96): `singletons=True/False` (emit single-mention clusters — only meaningful for preco/litbank models, README L111-112), `predefined_mentions=[(s,e),...]` (**clustering-only** mode — bring your own mentions, README L124-134), `add_gold_clusters=[[...]]` (seed with known clusters, README L136-143), `speakers=[...]` (OntoNotes speaker info). Char-offset outputs only when input is raw text.

### fastcoref
```python
from fastcoref import FCoref            # fast
# from fastcoref import LingMessCoref   # accurate
model = FCoref(device='cuda:0', compile_model=True)
preds = model.predict(texts=['...','...'], max_tokens_in_batch=10000, output_file='out.jsonl')
preds[0].get_clusters(as_strings=True)      # or False for char spans
preds[0].get_logit(span_i=(33,50), span_j=(52,64))   # pairwise coref logit
```
- `is_split_into_words=True` for pre-tokenized input.
- **spaCy v3 component** (`spacy_component.py`): `nlp.add_pipe("fastcoref", config={'model_architecture':'LingMessCoref',...})`; exposes `doc._.coref_clusters` and, with `resolve_text=True`, `doc._.resolved_text` — a rewritten text where each non-head mention is replaced by its cluster **head** (the resolved-text logic is the one piece of post-processing relevant to ugm; see §9).

---

## 7. Checklist items with NO analog in these repos (explicit "not found")

- **Entity resolution / dedup same-vs-different across documents** — **not found.** Coref is intra-document only; no canonical entity store, no cross-doc matching, no similarity threshold for dedup. (The internal `match`/`contain` categories are *features for the neural scorer*, not a dedup decision rule.)
- **Deterministic vs LLM resolution** — neither; it's a **trained neural net**. No LLM anywhere. The only deterministic rules are the `get_category_id` taxonomy and fixed `0.5` sigmoid cutoffs (§2).
- **Claim/entity/relation extraction, prompts, JSON-schema/function-calling/grammar, gleaning passes** — **not found.** No generative extraction at all.
- **Ontology / type system / predicates / domain-range** — **not found.** No entity typing; clusters are untyped span sets.
- **Temporal / bi-temporal / validity windows / supersession** — **not found.**
- **Merge / un-merge / reversibility / transitive-closure handling** — clustering *is* transitive-by-construction (union-find merge, §2) and **not reversible** (single forward pass, no merge_events log). There is no un-merge. The `add_gold_clusters` param (Maverick) is the closest thing to "seed/constrain" but it only adds, never splits.
- **Benchmark thresholds for ER** — **not found**; only the neural `0.5`/`argmax`/`top_lambda` model internals.

---

## 8. Concrete numbers inventory (everything quotable)

| Quantity | Value | Location |
|---|---|---|
| Maverick-mes OntoNotes CoNLL-2012 F1 | **83.6** | maverick README L50 |
| Maverick-mes PreCo / LitBank F1 | 87.4 / 78.0 | maverick README L51-52 |
| Maverick SOTA encoder | DeBERTa-v3-large | `conf/model/mes/deberta-large.yaml` |
| Maverick LR (Adafactor) | 3e-5, warmup 6000, 80000 steps | `conf/model/mes/deberta-large.yaml` |
| Mention start/span sigmoid cutoff | **0.5** | `model_mes.py` L149, L184, L308 |
| fastcoref per-text latency (compiled) | **~3ms**, ~0.6ms batched | fastcoref README L217-222 |
| `max_tokens_in_batch` default | **10000** | `modeling.py` L245 |
| `max_doc_len` | 4096 | `soft_training/run.py` L102 |
| FCoref encoder | distilroberta-base | README L170, training run |
| LingMess encoder | Longformer | `modeling.py` L246 |
| Inference dtype | bfloat16 | `modeling.py` L145 |
| Category taxonomy | 6 categories + ALL | `consts.py` L21-27 |
| Pronoun groups | 8 | `consts.py` L7-16 |
| HF model ids | `biu-nlp/f-coref`, `biu-nlp/lingmess-coref`, `sapienzanlp/maverick-mes-*` | both READMEs |

---

## 9. Steal vs avoid (for ugm)

**Steal:**
1. **Use one of these as the §8.7 coref engine that feeds `mentions` before extraction.** Maverick-mes-ontonotes (83.6 F1) for quality, FCoref for throughput at million-doc scale (~0.6ms/text batched, local, zero API cost). Both emit exactly what the registry's intake wants: clusters of `(start,end)` spans + surface strings — i.e. pre-grouped same-document mentions, which seeds `mention_id → surface_form → context` rows (`entity_registry.md` §4 transcript table) *before* cross-doc ER tiers run. This shrinks the cross-doc matching load: pronouns/definite-NP variants get collapsed to their cluster head locally and never hit the expensive Tier 3-5 adjudication.
2. **The `resolve_text=True` head-substitution pattern** (`spacy_component.py` `_core_logic_part`, L85-110): rewrite "its", "the city", "the president" to the cluster's noun/proper-noun **head** before claim extraction. This directly improves Claimify atomicity (`concepts.md` §1) — claims come out with resolved entity names instead of dangling pronouns. The head is chosen as the first span containing a NOUN/PROPN (`_get_span_noun_indices` L43-55), with a possessive-pronoun apostrophe-s fixup. Cheap, deterministic, worth adopting.
3. **The per-category scorer idea as a *feature design*** — distinct decision functions for pronoun-pronoun vs entity-entity is a real signal; ugm's fuzzy/embedding tiers could similarly branch on mention-type (proper name vs nominal vs pronoun) rather than one uniform similarity threshold.
4. **bfloat16 + batching + `release_logits()` discipline** — concrete ops patterns for running a neural pass over a million docs without OOM (the v2.2.0 changelog is essentially a cost-at-scale postmortem).

**Avoid / watch out:**
1. **Do not mistake this for entity resolution.** It is *intra-document* only. The catastrophic over-merge asymmetry in `entity_registry.md` §1 is **out of scope** for these tools — they will happily put two same-document mentions of different real people named "Alice" in one cluster if context misleads them, and there is **no reversibility / merge log** to undo it (§7). Treat coref output as *evidence* (a proposed within-doc grouping), never as a committed identity verdict — exactly the `mentions = evidence, entities = verdicts` split (`entity_registry.md` §4). Pipe coref clusters into the registry as candidate mention-groupings, then let the conservative tiered ER (with un-merge, §3) own the same-vs-different decision.
2. **Transitive closure is silently accepted** (union-find merge, §2; `create_clusters`) — the exact thing `entity_registry.md` §7.3 warns against ("A≈B, B≈C does not make A=C; never trust transitive closure"). Coref clusters *are* transitively closed with no weak-edge cutting. So a single bad antecedent link can chain unrelated mentions. Re-confirm cross-mention identity at the ER layer; don't inherit coref's transitivity into the entity graph.
3. **Annotation-guideline mismatch** (maverick README L62): OntoNotes excludes singletons and proper-noun-only clusters differ from PreCo/LitBank. Picking the wrong model silently changes what counts as a mention. Choose deliberately and pin the model version (maps to ugm's `resolver_version` provenance, `entity_registry.md` §4).
4. **No types, no temporal, no LLM** — these add nothing to ontology (D15), bi-temporal (E3), or supersession machinery; don't try to source those concerns here. Their entire contribution is the front-of-pipeline mention-grouping referenced in `entity_registry.md` §8.7.
