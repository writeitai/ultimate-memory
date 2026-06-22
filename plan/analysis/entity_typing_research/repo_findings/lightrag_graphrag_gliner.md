# Entity Typing: LightRAG, GraphRAG, GLiNER, GLiREL, mem0

Code archaeology of how each system assigns a TYPE (Person/Org/Concept/...) to an
entity. All claims cite `file:line` under `_additional_context/`. Subject = TYPING,
not identity resolution.

The GAP this informs: UGM has identity resolution fully specified (D17) but entity
TYPING unspecified, while D18 predicate domain/range enforcement *requires* types.
Each section closes with steal-vs-avoid for UGM.

---

## 1. LightRAG — LLM extraction-prompt typing, free-text, majority-vote merge

**(a) Where/when assigned.** Type is assigned *inside the single extraction LLM call*,
in the same tuple as name+description. The system prompt instructs:
`entity_type`: "Categorize the entity using the type guidance provided in the
`---Entity Types---` section below. If none of the provided entity types apply,
classify it as `Other`." — `lightrag/lightrag/prompt.py:62`. The type guidance block
is injected at `prompt.py:117` via `{entity_types_guidance}`. There is NO post-hoc
classifier and NO ontology match step.

**(b) Type inventory.** A **soft default list of 11 types** lives in the prompt, not
in code constants: Person, Creature, Organization, Location, Event, Concept, Method,
Content, Data, Artifact, NaturalObject — `prompt.py:20-32`
(`PROMPTS["default_entity_types_guidance"]`). This is *guidance text*, fully
overridable per-deployment via `addon_params["entity_types_guidance"]`
(`prompt.py:705-716`) or a profile YAML file (`prompt.py:657-664`). Note: NO classic
`DEFAULT_ENTITY_TYPES` python list governs validation — the list is prose in the prompt.

**(c) Entities that fit no type.** Prompt says fall back to `Other` (`prompt.py:62`).
BUT the parser does **not enforce the list at all**: in
`_handle_single_entity_extraction` (`operate.py:502`) the raw type string is only
sanitized — rejected only if empty or containing `' ( ) < > | / \` (`operate.py:533`),
comma-split to first token (`operate.py:542-554`), then lowercased and spaces stripped
(`operate.py:557`). Any other free-text string the LLM emits is accepted verbatim as the
type. So "fits no type" in practice means "whatever label the LLM invented" — the type
space is effectively **open**, not closed to the 11.

**(d) Mention-level vs entity-level + merge reconciliation.** Mentions are typed
per-chunk. On merging the same `entity_name` across chunks, the canonical type is chosen
by **majority vote**: `max(set(entity_types), key=entity_types.count)`
(`operate.py:1671-1674`), defaulting to `"UNKNOWN"` if no types present
(`operate.py:1674`, also `operate.py:1617`, `1890`, `1921`). Name is the merge key;
type is reconciled, not part of identity.

**(e) Confidence/validation.** None on the type. No score, no list-membership check
(see c). Only structural sanitization.

**(f) Gleaning loop.** Config `entity_extract_max_gleaning` (`operate.py:3337`) but this
version runs gleaning **at most once** regardless: `run_gleaning = max_gleaning > 0`,
then a single `if run_gleaning:` block (`operate.py:3519-3598`), guarded by a token-budget
precheck that disables it if the replayed history exceeds limits (`operate.py:3541-3547`).
Gleaning merges new/longer-described entities (`operate.py:3584-3598`) — it re-types missed
entities but does not re-vote existing ones. The continue-prompt asks only for
missed/malformed items (`prompt.py:143-159`).

---

## 2. GraphRAG — LLM extraction-prompt typing, type IS part of identity, no reconciliation

**(a) Where/when.** Same model: type assigned in the single extraction call, in the
entity tuple `("entity"<|>name<|>type<|>description)` — prompt
`graphrag/packages/graphrag/graphrag/prompts/index/extract_graph.py:11-15`. The
`entity_type` instruction: "One of the following types: [{entity_types}]"
(`extract_graph.py:13`). No post-hoc classifier; no ontology match.

**(b) Inventory.** Classic hard-coded default list:
`DEFAULT_ENTITY_TYPES = ["organization", "person", "geo", "event"]` —
`graphrag/packages/graphrag/graphrag/config/defaults.py:42`, wired into config at
`config/models/extract_graph_config.py:37-39`. Only **4 types** by default,
configurable. Also a *prompt-tune auto-discovery* path: `generate_entity_types()` asks an
LLM to invent a type list from sample docs (`prompt_tune/generator/entity_types.py:29-56`,
example output `['military unit','organization','person','location','event','date',
'equipment']`) — i.e. types can be corpus-derived rather than fixed.

**(c) Fits no type.** No `Other` fallback in the prompt (unlike LightRAG). Parser
accepts whatever the LLM emits: `entity_type = clean_str(record_attributes[2].upper())`
(`index/operations/extract_graph/graph_extractor.py:147`) — uppercased, no
list-membership validation. The CONTINUE_PROMPT does nudge: "ONLY emit entities that
match any of the previously extracted types" (`prompts/index/extract_graph.py:128`).
So: open type space in code, soft-constrained by prompt.

**(d) Mention vs entity + merge.** CRITICAL DIFFERENCE FROM LIGHTRAG: type is part of
the identity key. `_merge_entities` does
`groupby(["title", "type"])` (`index/operations/extract_graph/extract_graph.py:104-115`).
So "Apple" typed `ORGANIZATION` in one chunk and `PRODUCT` in another becomes **two
separate entities** — there is NO type reconciliation; type disagreement forks identity.

**(e) Confidence/validation.** None on type. Relationship weight is parsed
(`graph_extractor.py:160-163`) but entity type carries no score.

**(f) Gleaning loop.** Real loop with two exit criteria (vs LightRAG's single pass):
`for i in range(self._max_gleanings)` (`graph_extractor.py:101-122`), appending
CONTINUE_PROMPT, then a LOOP_PROMPT yes/no continuation check — exits on max OR when the
model answers `!= "Y"` (`graph_extractor.py:115-120`).

---

## 3. GLiNER — zero-shot typed NER, caller-supplied labels, per-span confidence (the cheap typing tier)

**(a) Where/when.** A trained encoder model assigns the type at inference time —
`model.predict_entities(text, labels, threshold=0.5)`
(`GLiNER/README.md:79`; sig `gliner/model.py:2128`, batch `inference` at
`gliner/model.py:2249-2262`). NOT an LLM prompt, NOT post-hoc on LLM output — it is the
extractor and the typer in one cheap forward pass. This is the model that fits UGM's
"cheap typing tier" slot.

**(b) Inventory.** Fully **open / zero-shot** — the label set is passed in at call time as
a plain list, e.g. `labels = ["Person","Award","Date","Competitions","Teams"]`
(`README.md:76`). README note: "Most GLiNER models should work best when entity types are
in lower case or title case" (`README.md:74`). No fixed list, no default — UGM supplies its
own 8-type core (D18) as the label set directly. Multi-label per span optional
(`multi_label` param, `model.py:2270`).

**(c) Fits no type.** Spans whose best label scores below `threshold` (default 0.5,
`model.py:2128`,`2255`) are simply **not returned** — there is no "Other" bucket; the span
silently drops. So an explicit fallback/UNKNOWN must be added by the caller.

**(d) Mention vs entity.** Purely **mention-level** (character span -> label). GLiNER has
no concept of entity merge or cross-mention reconciliation — that is downstream's job.

**(e) Confidence/validation.** YES — every prediction carries a `score` confidence and a
char span: output dict = `{start, end, text, label, score}`, optional
`class_probs` top-5 per span (`model.py:2279-2285`). This is the only system here with a
real per-assignment type confidence usable for a golden-set-tuned threshold (D17/D22 style).

**(f) Model size/speed.** "small NER models with zero-shot capabilities ... optimized to
run on CPUs and consumer hardware, and has performance competitive with LLMs several times
its size, like ChatGPT and UniNER" (`README.md:32`). Sizes: small/medium/large
(`gliner_small-v2.1`, `gliner_medium-v2.1`, `README.md:65,118`). Production serving via Ray
Serve with dynamic batching, bf16, FlashDeBERTa (`README.md:~95-130`). Genuinely cheap
relative to an LLM call — viable per-mention typing tier.

---

## 4. GLiREL — zero-shot RE that CONSUMES types, with allowed_head/tail = domain/range

**(a)/(b)/(c) Does NOT type entities.** GLiREL is "Zero-Shot Relation Extraction"
(`GLiREL/README.md:1`). It **requires entity types as INPUT**: the `ner` argument is
`[[start, end, TYPE, text], ...]`, and the README is explicit:
"'type' is not used -- it can be any string!" (`README.md:47`). So GLiREL assigns NO
entity type; it predicts the *relation* label between pre-typed spans
(`predict_relations(tokens, labels, threshold, ner, top_k)`, `README.md:49`).

**(d)/(e) Per-relation confidence.** Output carries `label` + `score` per directed pair
(`README.md:65-66`). Mention-pair level.

**(f) DIRECTLY RELEVANT TO D18 domain/range.** GLiREL natively supports typed
head/tail constraints on each predicate — exactly UGM's `subject_type`/`object_type`:
```
'co-founder': {"allowed_head": ["PERSON"], "allowed_tail": ["ORG"]},
'founded on date': {"allowed_head": ["ORG"], "allowed_tail": ["DATE"]},
'headquartered in': {"allowed_head": ["ORG"], "allowed_tail": ["LOC","GPE","FAC"]},
'no relation': {},  # head/tail unconstrained
```
(`README.md:73-88`). This is the same mechanism D18 cites from Graphiti's
`edge_type_map[(src,tgt)→[rel]]` — but here it's enforced *at RE inference time*. It
presupposes types already assigned (by GLiNER or an LLM upstream).

---

## 5. mem0 — does NOT type entities semantically (in this checkout)

**(a) No semantic typing.** This checkout has **no graph-store module at all**:
`mem0/mem0/graphs/` does not exist (only `client, configs, embeddings, llms, memory,
proxy, reranker, utils, vector_stores`). The CLAUDE.md advertises Neo4j/Memgraph/Kuzu/AGE
graph stores (which upstream type via LLM `source_type`/`destination_type` prompts), but
**none of that code is present here** — no `UPDATE_GRAPH_PROMPT`, `source_node`,
`destination_type`, or `EXTRACT_RELATIONS` strings anywhere in the tree.

**(b) What "type" exists is grammatical, not ontological.** The only entity layer present
is `mem0/utils/entity_extraction.py`, a spaCy POS extractor used to populate a vector
"entity_store" (`memory/main.py:36,544-554,894-905`). Its "types" are
**syntactic categories**: PROPER, QUOTED, COMPOUND, NOUN, VERB
(`entity_extraction.py:4-8,123,134,346-351`), NOT Person/Org/Concept. Type priority
(`type_pri = {"PROPER":0,"COMPOUND":1,"QUOTED":2,"NOUN":3,"VERB":4}`,
`entity_extraction.py:347`) picks the best grammatical category per surface string.

**(c) Stored as opaque payload.** `_upsert_entity` writes `"entity_type": entity_type`
into the vector payload (`memory/main.py:439-478`, field at `:470`) purely so entities can
be looked up / linked to memory_ids — it is never used for predicate domain/range or
ontology reasoning. Entity identity here is embedding-cosine ≥ 0.95
(`memory/main.py:452`), independent of type.

**Verdict:** in this build, mem0 does **no ontology typing** of the
Person/Org/Concept kind. It is not a model to copy for typing.

---

## STEAL vs AVOID for UGM

**STEAL:**
- **GLiNER as the cheap typing tier (T-typing).** Pass UGM's D18 8-type core
  (`Person, Organization, Place, Document, Event, Concept, Project, Product`) as the
  zero-shot label list; get back per-span `score` you can threshold against a golden set
  (D22), mirroring D17's golden-set-tuned cascade for identity. It's CPU-cheap and gives a
  real confidence number — the only system here that does (`model.py:2279-2285`).
- **GLiREL's `allowed_head`/`allowed_tail`** as the *runtime* embodiment of D18
  domain/range — same shape as Graphiti's `edge_type_map`, and it lets domain/range act as
  an extraction *constraint*, not just a post-hoc validation. (`README.md:73-88`).
- **LightRAG's majority-vote type reconciliation on merge** (`operate.py:1671-1674`) as the
  entity-level rule when mentions disagree — it keeps type a reconcilable attribute of the
  entity, which is what D17 (identity by name/embedding, type separate) wants.
- **GraphRAG's LOOP_PROMPT two-exit gleaning** (`graph_extractor.py:101-122`) if UGM does
  LLM extraction — cleaner than LightRAG's single-pass gleaning.
- **A soft `Other`/UNKNOWN fallback** (LightRAG `prompt.py:62`, parser default
  `"UNKNOWN"`) so domain/range enforcement (D18) always has a defined type to check, even
  for out-of-ontology mentions — GLiNER silently drops sub-threshold spans, so UGM must add
  this bucket explicitly.

**AVOID:**
- **GraphRAG's `groupby(["title","type"])`** (`extract_graph.py:108`) — making type part of
  the identity key *forks* the same entity on type disagreement. This directly contradicts
  D17 (identity = resolution, type = attribute) and D21 reversibility. UGM must keep type
  OFF the identity key.
- **Trusting the LLM type string with no list validation** (LightRAG `operate.py:533-557`,
  GraphRAG `graph_extractor.py:147`) — both accept arbitrary free-text labels, so the
  "fixed list" is a fiction and the type space silently drifts open. UGM needs an explicit
  membership check / map-to-core step (or use GLiNER's closed label set) before D18
  domain/range can be enforced.
- **mem0's grammatical "types"** (`entity_extraction.py:346-351`) — POS categories are not
  ontology types; do not mistake mem0's `entity_type` field for semantic typing.
- **Relying on a single extraction pass to also do typing** when domain/range matters:
  LightRAG/GraphRAG bind type at extraction with no confidence and no validation. UGM's
  D18 enforcement wants a typed-and-scored mention, which argues for a dedicated typing tier
  (GLiNER) separable from extraction.
