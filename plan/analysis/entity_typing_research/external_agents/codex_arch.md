# Recommended architecture (TL;DR)

- **Typing is a registry adjudication, not just an extractor field.** The E2/E3 extractor must emit a contextual mention type, but that is evidence. The registry decides the canonical entity type through an append-only `type_decisions` ledger.
- **Pipeline order:** extract mentions/claims/candidate relations → type mentions → resolve mentions to entities using type as a blocking/negative feature → adjudicate entity type → validate candidate relations against predicate domain/range → write accepted E3 relations.
- **Mention typing is contextual; entity typing is canonical.** Store both. `mentions.proposed_type` answers “what does this span refer to here?”; `entities.type` is a cached current verdict backed by `entity_type_decisions`.
- **Core type is effectively stable but re-adjudicable.** A Person does not become a Place. Most “type drift” is either subtype refinement or evidence of an identity-resolution error. Retyping exists because adjudication can be wrong.
- **Domain/range gates only accepted relations, never raw extraction.** Candidate relations can be stored pending type validation; accepted relations require endpoint entity types satisfying the predicate signature.
- **Use a cheap-first typing cascade:** authority IDs → deterministic lexical/source rules → gazetteers/ontology anchors → GLiNER-style typed NER → extraction LLM → human review for high blast radius.
- **Do not use `Concept` as “unknown.”** Add an explicit `UnresolvedType` / `unknown` decision state outside the ontology. `Concept` means an identifiable abstraction/topic, not a trash bin.
- **Subtype is coarse-to-fine.** Extraction chooses from a scoped menu of enabled types, but every subtype maps to one core parent. Relation validation always works at both leaf and ancestor levels.

# 1. When/Where Typing Happens

**Recommended answer:** typing happens immediately after mention extraction and before identity resolution finalization and relation validation. The extractor proposes the first mention-level type, but the registry adjudicates it through a typing cascade.

Do not make typing purely “during resolution.” Resolution needs type as a feature: `Washington` as Person, Place, Organization, Document, or Project creates different candidate pools. Waiting until after identity resolution makes the resolver compare across incompatible worlds and invites over-merge. Conversely, do not make the E2/E3 LLM’s type final. Extraction has useful context but poor auditability; it will be wrong on polysemy, metonymy, and deployment-specific subtypes.

The pipeline should be:

```text
E0 docs
→ E1 chunks
→ E2 extraction:
   mentions + spans + claim text + candidate relations + extractor_type_vote
→ typing cascade:
   mention_type_decisions
→ entity resolution:
   resolution_decisions mention_id → entity_id, type-aware
→ entity type reconciliation:
   entity_type_decisions, entities.type cache
→ relation normalization/validation:
   candidate_relation → accepted relation or rejected/pending
→ E3 relations
```

This fits the current registry model in [plan/designs/registries_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/registries_design.md), where `mentions` are immutable evidence and `resolution_decisions` are append-only verdicts. Type should follow the same evidence/verdict split.

Graphiti is evidence for the extraction-time part, not for final adjudication. In [extract_nodes.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphiti/graphiti_core/prompts/extract_nodes.py:28), `ExtractedEntity` includes `entity_type_id` and says it “must be one of the provided entity_type_id integers.” The prompt gives `<ENTITY TYPES>` to the model and says “Use the descriptions in ENTITY TYPES” and “Assign the appropriate `entity_type_id`” [extract_nodes.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphiti/graphiti_core/prompts/extract_nodes.py:118). Graphiti also has a separate `classify_nodes` prompt with “Each entity must have exactly one type” and “NEVER use types not listed” [extract_nodes.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphiti/graphiti_core/prompts/extract_nodes.py:347). That is the right interface shape, but Graphiti stores the result directly as labels, not as an auditable registry verdict.

# 2. Mention-Level vs Entity-Level Typing

A mention type is a contextual assertion. An entity type is the current canonical verdict.

Store:

- `mentions.proposed_core_type`
- `mentions.proposed_subtype`
- `mention_type_decisions`
- `entities.type`
- `entities.subtype`
- `entity_type_decisions`

Reconciliation rule:

1. **Authority wins** when an external ID strongly implies type: ORCID → Person, DOI → Document, LEI → Organization, Wikidata/OpenAlex class mapping → mapped core/extension type.
2. **Human verdict wins** over all automated evidence.
3. **High-confidence repeated contextual votes win** only when they are type-consistent and come from independent mentions.
4. **Predicate-signature evidence can support but not alone force type.** If an entity is repeatedly the subject of `works_for`, that is evidence for Person, but it may also indicate a bad relation extraction.
5. **Disagreement is first an identity-resolution warning, not a type-majority problem.**

For `Washington`, if one cluster contains `Washington was born in 1732` as Person and `Washington borders Oregon` as Place, the default action is not “majority type = Place.” It is **split review** or automatic split if confidence is strong. The resolver should treat core-type mismatch as a hard negative feature except for explicitly modeled metonymy. A same-name cross-type merge should require T5/human approval.

Genuine drift should be rare at the core type level. If something seems to drift from `Project` to `Product`, it may be two entities: the project and the launched product. If `Decision` later becomes obsolete, that is relation validity, not type drift. If `ResearchPaper` is later recognized as `Document`, that is subtype refinement, not identity drift.

Metonymy is handled by typing the referent in context. “The White House said” should usually type the mention as Organization/Event-administration-like extension if enabled, not Place. If the system needs to preserve surface semantics, add `mentions.surface_semantic_type` separately; relation validation cares about the referent type.

# 3. Fixed or Re-Adjudicable

Type is **re-adjudicable like identity**, but with stricter semantics.

Add an append-only `entity_type_decisions` table. `entities.type` is only the current materialized verdict, same as `entities.merged_into` is a current redirect state backed by `merge_events`.

Retyping mechanism:

```text
entity_type_decisions
  decision_id
  entity_id
  decided_core_type
  decided_subtype nullable
  method enum(ET0_AUTHORITY, ET1_DETERMINISTIC, ET2_GAZETTEER,
              ET3_GLINER, ET4_LLM, ET5_HUMAN, REBUILD)
  confidence
  evidence jsonb
  type_resolver_version
  decided_at
  superseded_by nullable
```

Retyping must trigger relation revalidation. Since D7 makes P2 rebuild-first and Postgres authoritative, the correct model is:

- Relations have `validation_status`: `accepted`, `rejected_type_mismatch`, `pending_type`, `superseded_by_retype`.
- Relations store `validated_against_type_decision_ids` for subject and object.
- When an entity type decision changes, mark affected relations dirty:
  - accepted relations involving the entity are revalidated;
  - rejected candidate relations involving the entity are eligible for replay;
  - P1/P2 projections rebuild from the new accepted relation set.

Do not mutate claims. Do not delete relation evidence. A type change changes the verdict layer, not the transcript. This is exactly aligned with D2/D3 in [decisions.md](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md): claims are immutable assertions; relations are revisable facts.

# 4. Resolving the Circular Dependency

There is no circular dependency if relation extraction is treated as candidate production.

Correct order:

1. Extract candidate mentions with spans and context.
2. Extract candidate claims and candidate relations referencing mention IDs or local mention names.
3. Type each mention with the cascade.
4. Resolve each mention to an entity using type-aware candidate generation.
5. Decide or update the canonical entity type.
6. Validate candidate relation predicate against current endpoint entity types.
7. Accept, reject, or defer the relation.

The subject and object types are both required before a relation is accepted. If either endpoint is untyped or low-confidence, relation status is `pending_type`, not accepted through `related_to`. This is important: `related_to` is a governed permissive predicate, not a bypass around missing typing.

Graphiti’s source shows the intended structural gate shape. It computes label tuples from source and target node labels and looks up allowed edge types in `edge_type_map` [edge_operations.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphiti/graphiti_core/utils/maintenance/edge_operations.py:458). That means relation type selection depends on node labels. UGM should keep that idea but make node type adjudication explicit and replayable.

# 5. Typing Cascade

Use an entity-typing cascade parallel to D17, but do not reuse D17’s exact tiers because typing and identity have different evidence.

Recommended cascade:

| Tier | Name | Role | Examples | Behavior |
|---|---|---|---|---|
| ET0 | External authority | Near-certain type evidence | DOI→Document, ORCID→Person, LEI→Organization, OpenAlex work→Document, Wikidata P31 mapped to core | Accept high confidence; fall through on miss |
| ET1 | Deterministic source/schema | Cheap exact rules | Gmail message/file→Document, calendar row→Event, GitHub repo→Project/Product by connector schema | Accept when source schema is authoritative |
| ET2 | Lexical/gazetteer/ontology anchor | Cheap but fallible | Inc/Ltd/GmbH suffix→Organization, country/city gazetteer→Place, ontology class exact/fuzzy match | Accept only high precision; otherwise candidate signal |
| ET3 | GLiNER-style typed NER | Cheap contextual classifier | Run over chunk with enabled type labels | Accept high band, escalate middle |
| ET4 | Extraction LLM / classifier LLM | Context-rich adjudicator | Structured enum over scoped type menu | Accept high band, escalate high-impact ambiguity |
| ET5 | Human review | Blast-radius protection | Conflicting types on high-degree entity | Final verdict |

GLiNER earns a place because it accepts a caller-supplied label menu and runs as a smaller NER model. The local README says labels are passed to `predict_entities`, e.g. `labels = ["Person", "Award", "Date", "Competitions", "Teams"]`, then `model.predict_entities(text, labels, threshold=0.5)` [README.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/GLiNER/README.md:74). It also supports serving with dynamic batching [README.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/GLiNER/README.md:104), which is useful at millions-of-docs scale. Use it as a cheap vote, not as final truth.

Cognee’s ontology behavior is useful as ET2 evidence, but not as enforcement. The local analysis confirms a fuzzy `cutoff=0.8`, exact match first, and unmatched nodes are kept with `ontology_valid=False`; nothing is rejected [cognee.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/analysis/registry_research/repo_findings/cognee.md:91). It also explicitly found no domain/range enforcement [cognee.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/analysis/registry_research/repo_findings/cognee.md:121). UGM should not copy that as the structural gate.

# 6. Subtype Assignment

Every entity has exactly one **current core type** and optionally one **current subtype**. Subtypes are registry rows with `parent_type`, so `ResearchPaper ⊂ Document` and `Task ⊂ Event`.

Recommendation:

- The extractor sees a scoped menu of enabled types: 8 core types plus enabled extension types for the deployment/scope.
- It may emit the leaf subtype if context supports it.
- The typing cascade stores both:
  - `core_type = ancestor_core(type)`
  - `subtype = leaf_type or null`
- Relation validation uses subtype inheritance:
  - `ResearchPaper` satisfies `Document`;
  - `Task` satisfies `Event`;
  - subtype-specific predicates can require the leaf.

Do not ask the extractor to choose among every installed type globally. Render a scope-aware menu from `entity_types`, `scope_interests`, and enabled packs. Large menus reduce accuracy and increase false specificity. For generic E2 extraction, prefer core types plus high-value pack types. For a legal deployment, include `Contract`, `Statute`, `Ruling`, `Jurisdiction`; for the Work pack, include `Task`, `Decision`, `Goal`.

If extractor emits only core, a later refinement job can promote core→subtype using richer evidence: document metadata, connector schema, repeated predicates, authority classes, and LLM review. Subtype refinement should not block core relation validation unless a predicate requires the subtype.

# 7. Untypable Mentions and the Concept Risk

Do **not** create an ontology type called `Thing` and do **not** use `Concept` as unknown.

Use a decision state outside the ontology:

```text
type_decision_status:
  accepted
  pending
  rejected_not_entity
  unresolved_type
  conflict_review
```

`Concept` means a stable, identifiable abstraction, topic, theory, goal, method, or domain object. Examples: “entity resolution,” “GDPR compliance,” “zero-shot typed NER.” It does not mean “we could not classify this.” Graphiti’s own default fallback type is `Entity`, described as something that “does not fit any of the other listed types” but still must be “concrete” and “uniquely identifiable,” with “When in doubt, do not extract” [node_operations.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/graphiti/graphiti_core/utils/maintenance/node_operations.py:158). That is safer than dumping into Concept, but UGM should be stricter: unknown type is not graph-admissible until adjudicated.

Operational rules:

- A mention with `unresolved_type` can remain in `mentions` and claims.
- It cannot create an accepted relation except through predicates whose signature explicitly allows untyped endpoints; v1 should allow none.
- Candidate relations involving unresolved endpoints are replayable after retyping.
- Monitor `unresolved_type` and `Concept` volume by source, scope, prompt version, and extractor version.
- Require Concept decisions to include a `concept_kind` or explanation field in `features`: topic, method, theory, goal, value, category, etc.
- If a frequent unresolved class appears, promote it through D5/D15 extension governance instead of widening Concept.

# 8. Data Model

Add typing without breaking the existing registry shape in [registries_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/registries_design.md):

```sql
-- immutable mention evidence additions
mentions (
  mention_id,
  surface_form,
  normalized_lemma,
  context,
  claim_id,
  chunk_id,
  doc_id,
  language,
  char_span,
  proposed_core_type text null references entity_types(type),
  proposed_subtype text null references entity_types(type),
  proposed_type_confidence numeric null,
  proposed_type_method text null,
  type_resolver_version text null
);

mention_type_decisions (
  decision_id bigserial primary key,
  mention_id uuid not null references mentions,
  decided_core_type text null references entity_types(type),
  decided_subtype text null references entity_types(type),
  status text not null,
  method text not null,
  confidence numeric not null,
  features jsonb not null,
  type_resolver_version text not null,
  decided_at timestamptz not null,
  superseded_by bigint null
);

-- current cache on canonical entity
entities (
  entity_id,
  type text null references entity_types(type),
  subtype text null references entity_types(type),
  type_confidence numeric null,
  type_decision_id bigint null references entity_type_decisions,
  canonical_name,
  status,
  merged_into,
  profile_summary,
  profile_embedding_ref
);

entity_type_decisions (
  decision_id bigserial primary key,
  entity_id uuid not null references entities,
  decided_core_type text not null references entity_types(type),
  decided_subtype text null references entity_types(type),
  status text not null,
  method text not null,
  confidence numeric not null,
  evidence jsonb not null,
  type_resolver_version text not null,
  decided_at timestamptz not null,
  superseded_by bigint null,
  caused_by_merge_id uuid null,
  caused_by_resolution_decision_id uuid null
);

candidate_relations (
  candidate_relation_id uuid primary key,
  claim_id uuid not null,
  subject_mention_id uuid not null,
  predicate text not null references predicates(predicate),
  object_mention_id uuid not null,
  extraction_features jsonb not null,
  validation_status text not null,
  rejection_reason text null,
  replay_after_type_decision_id bigint null,
  created_at timestamptz not null
);

relations (
  relation_id,
  subject_entity_id,
  predicate,
  object_entity_id,
  valid_from,
  valid_until,
  ingested_at,
  invalidated_at,
  validation_status text not null,
  subject_type_decision_id bigint not null references entity_type_decisions,
  object_type_decision_id bigint not null references entity_type_decisions,
  type_validation_version text not null
);

type_resolver_versions (
  type_resolver_version text primary key,
  tier_config jsonb not null,
  thresholds_by_type jsonb not null,
  enabled_type_menu jsonb not null,
  authority_type_map_version text not null,
  configured_at timestamptz not null
);
```

Indexes:

- `mention_type_decisions(mention_id, decided_at desc)`
- `entity_type_decisions(entity_id, decided_at desc)`
- `entities(type, normalized/canonical_name)` for type-aware blocking
- `candidate_relations(validation_status, replay_after_type_decision_id)`
- `relations(subject_entity_id, predicate)` remains as D23 requires

# Data model + decision text

## Proposed Design Section: Entity Typing

**Decision.** Entity typing is a two-level, append-only registry subsystem. E2/E3 extraction emits contextual mention-type evidence. A cheap-first typing cascade adjudicates mention type. Entity resolution uses type as a blocking and negative-evidence feature. The canonical entity type is decided by an append-only `entity_type_decisions` ledger and cached on `entities.type`. Relations are accepted only after subject and object entity types satisfy predicate domain/range, including subtype inheritance.

**Pipeline.**

```text
extract mentions + candidate relations
→ adjudicate mention types
→ resolve mentions to entities
→ reconcile canonical entity type
→ validate relation signatures
→ write accepted relations
```

**Rules.**

- Every accepted entity has exactly one current core type.
- An entity may have one current leaf subtype; subtype ancestors satisfy parent signatures.
- Type disagreement inside an entity cluster is treated as possible wrong merge before it is treated as type drift.
- Retyping is allowed and append-only. It marks affected relations for revalidation and makes previously rejected candidate relations replayable.
- `Concept` is not an unknown type. Unknown typing is `unresolved_type`, which cannot pass relation validation.
- Human review is required for high-blast-radius cross-core retyping or cross-core merges.

## Proposed Decision: D25. Entity Typing Cascade and Re-Adjudicable Type Verdicts

**Decision.** UGM adds an entity-typing subsystem parallel to entity resolution. The extractor proposes mention types from the deployment’s scoped ontology menu, but final type is a registry verdict. Type decisions are append-only and versioned (`mention_type_decisions`, `entity_type_decisions`, `type_resolver_versions`). Domain/range validation runs only after endpoint entity types are known. Retyping revalidates affected relations and replays pending/rejected candidate relations during the Postgres rebuild/projection cycle.

**Context.** D18 requires predicate domain/range constraints, but D15-D24 did not specify how entity types are assigned. Graphiti demonstrates the useful extraction interface: structured `entity_type_id`, entity labels, and `edge_type_map` keyed by source/target labels. It does not provide UGM’s needed audit/rebuild semantics. Cognee demonstrates ontology anchoring, but not domain/range enforcement. GLiNER provides a cheap zero-shot typed-NER tier over dynamic labels.

**Consequences.**

- Relation validation is no longer circular.
- Type disagreement becomes a first-class ER quality signal.
- Retyping is retroactively clean in P1/P2 because projections rebuild from Postgres.
- `Concept` remains meaningful and measurable instead of absorbing all uncertainty.
- Golden-set evaluation must add typed-mention and canonical-entity type accuracy by core type and subtype.

# Open risks / what to spike

- **Typing golden set.** Extend D22 with mention-level type labels, entity-level canonical labels, and hard negatives for same-name cross-type cases.
- **Thresholds.** Measure ET2/ET3/ET4 confidence bands per core type. No global GLiNER or LLM threshold should ship.
- **Menu-size effect.** Benchmark extractor and GLiNER accuracy with 8 core types only vs core + Work pack vs deployment-specific large menus.
- **Metonymy policy.** Decide whether to model `White House` as Organization via context, or introduce explicit metonymy links between Place and Organization entities.
- **Replay cost.** Estimate how many candidate relations are retained and replayed after retyping; partition or TTL low-value rejected candidates if needed.
- **Subtype churn.** Define which subtype changes are cheap refinements and which are identity-split signals.
