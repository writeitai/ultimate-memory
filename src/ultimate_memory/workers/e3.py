"""The E3 normalizer (D2-D5, D17-D18, D43): claims → relations and observations.

Per claim, one normalizer call proposes (subject, predicate, object) relations
and entity-anchored observations. Deterministic gates then govern what lands:
the predicate must be in the registry vocabulary and its type signature must
match at some ancestor level (D18 — application-enforced at write time; a
dropped candidate is re-derivable from its immutable claim). Entities resolve
through T0; the fact catalog collapses redundancy (D2) and keeps the D54
lineage-distinct evidence counts.
"""

import logging
from typing import Final
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from ultimate_memory.model import ClaimedWork
from ultimate_memory.model import ClaimForNormalization
from ultimate_memory.model import EnqueueWork
from ultimate_memory.model import ModelRequest
from ultimate_memory.model import NonRetryableHandlerError
from ultimate_memory.model import NormalizationResponse
from ultimate_memory.model import PipelineStage
from ultimate_memory.ports.model_provider import ModelProviderPort
from ultimate_memory.spine.chunk_catalog import ChunkCatalog
from ultimate_memory.spine.claim_catalog import ClaimCatalog
from ultimate_memory.spine.entity_registry import EntityRegistry
from ultimate_memory.spine.fact_catalog import FactCatalog
from ultimate_memory.spine.fact_catalog import OTHER_PREDICATE_GRAMMAR
from ultimate_memory.spine.observation_adjudication import ObservationAdjudicator
from ultimate_memory.spine.resolver import CascadeResolver
from ultimate_memory.spine.supersession import ADJUDICATOR_VERSION
from ultimate_memory.spine.supersession import SupersessionAdjudicator
from ultimate_memory.workers.base import HandlerOutcome
from ultimate_memory.workers.p1 import FACT_LABEL_VERSION
from ultimate_memory.workers.p1 import P1_EMBED_CLAIMS_VERSION

_logger = logging.getLogger(__name__)

_OTHER_PREDICATE: Final = OTHER_PREDICATE_GRAMMAR
"""The escape-value routing check (the spine re-validates authoritatively)."""

E3_NORMALIZER_VERSION: Final = "e3-normalize-2026.07"
"""The normalize sub-worker's component version (D12 idempotency member)."""

_NORMALIZE_PROMPT: Final = """You are the normalizer of a memory system. Turn
the CLAIM into zero or more of:
- relations: (subject, predicate, object) between TWO named entities, using
  ONLY the governed predicates listed below (map synonyms onto them). If a
  clearly relational fact fits NO governed predicate, you may emit
  `other:<short_snake_case>` (e.g. other:sponsors) — never invent a bare
  predicate name;
- observations: a value/property/statement about ONE entity, as a standalone
  statement ("Acme's headcount is 600"). An ATTRIBUTED stance claim ("X said /
  believes / opposes Y") becomes a stance observation anchored on X — never a
  fact about Y.
Entity names must be canonical nominative forms; entity types must come from
the registry types below. Time is never a relation object.

GOVERNED PREDICATES:
{predicates}
REGISTRY TYPES: {types}

CLAIM (attributed={is_attributed}): {claim_text}"""


class E3Settings(BaseSettings):
    """The E3 model binding: interchangeable per-deployment port config (D70)."""

    model_config = SettingsConfigDict(env_prefix="UGM_E3_")

    normalize_model: str = Field(default="openai/gpt-5.6-luna")


class NormalizeRelationsHandler:
    """The normalize stage: every accepted claim of one representation."""

    def __init__(
        self,
        *,
        claim_catalog: ClaimCatalog,
        chunk_catalog: ChunkCatalog,
        registry: EntityRegistry,
        resolver: CascadeResolver,
        facts: FactCatalog,
        observation_adjudicator: ObservationAdjudicator,
        model_provider: ModelProviderPort,
        settings: E3Settings,
        chunker_version: str,
    ) -> None:
        """Bind the handler to its catalogs, registry, provider, and generation."""
        self._claim_catalog = claim_catalog
        self._chunk_catalog = chunk_catalog
        self._registry = registry
        self._resolver = resolver
        self._facts = facts
        self._observation_adjudicator = observation_adjudicator
        self._model_provider = model_provider
        self._settings = settings
        self._chunker_version = chunker_version

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Normalize one document version's claims into relations/observations.

        Newly-created relations chain the supersession adjudicator (D3/D4)
        alongside the P1 writers."""
        source = self._chunk_catalog.chunk_source(
            representation_id=_payload_uuid(work=work, field="representation_id")
        )
        chunks = self._chunk_catalog.chunks_for_embedding(
            representation_id=source.representation_id,
            chunker_version=self._chunker_version,
        )
        claims = self._claim_catalog.claims_for_chunks(
            chunk_ids=tuple(chunk.chunk_id for chunk in chunks)
        )
        if not claims:
            return HandlerOutcome()
        deployment_id = work.deployment_id
        predicates = self._facts.active_predicates(deployment_id=deployment_id)
        prompt_lines = self._facts.predicate_prompt_lines(deployment_id=deployment_id)
        signatures = self._facts.predicate_signatures(deployment_id=deployment_id)
        type_parents = self._facts.entity_type_parents(deployment_id=deployment_id)
        created_relations: list[str] = []
        for claim in claims:
            if self._registry.claim_already_normalized(claim_id=claim.claim_id):
                continue  # replay: stored mentions/facts are the output (D7)
            self._normalize_claim(
                created_relations=created_relations,
                deployment_id=deployment_id,
                claim=claim,
                predicates=predicates,
                prompt_lines=prompt_lines,
                signatures=signatures,
                type_parents=type_parents,
            )
        return HandlerOutcome(
            follow_up=(
                EnqueueWork(
                    deployment_id=work.deployment_id,
                    target_kind=work.target_kind,
                    target_id=work.target_id,
                    stage=PipelineStage.ADJUDICATE_SUPERSESSION,
                    component_version=ADJUDICATOR_VERSION,
                    content_hash=work.content_hash,
                    lane=work.lane,
                    payload={**(work.payload or {}), "relation_ids": created_relations},
                ),
                EnqueueWork(
                    deployment_id=work.deployment_id,
                    target_kind=work.target_kind,
                    target_id=work.target_id,
                    stage=PipelineStage.EMBED_CLAIM,
                    component_version=P1_EMBED_CLAIMS_VERSION,
                    content_hash=work.content_hash,
                    lane=work.lane,
                    payload=dict(work.payload or {}),
                ),
                EnqueueWork(
                    deployment_id=work.deployment_id,
                    target_kind=work.target_kind,
                    target_id=work.target_id,
                    stage=PipelineStage.LABEL_RELATION,
                    component_version=FACT_LABEL_VERSION,
                    content_hash=work.content_hash,
                    lane=work.lane,
                    payload={**(work.payload or {}), "doc_id": str(source.doc_id)},
                ),
            )
        )

    def _normalize_claim(
        self,
        *,
        created_relations: list[str],
        deployment_id: UUID,
        claim: ClaimForNormalization,
        predicates: dict[str, str | None],
        prompt_lines: str,
        signatures: dict[str, tuple[tuple[str, str], ...]],
        type_parents: dict[str, str | None],
    ) -> None:
        """One claim through the normalizer call and the deterministic gates."""
        response = self._model_provider.generate(
            request=ModelRequest(
                model=self._settings.normalize_model,
                prompt=_NORMALIZE_PROMPT.format(
                    predicates=prompt_lines,
                    types=", ".join(sorted(type_parents)),
                    is_attributed=claim.is_attributed,
                    claim_text=claim.claim_text,
                ),
            ),
            response_type=NormalizationResponse,
        )
        for relation in response.relations:
            if _OTHER_PREDICATE.fullmatch(relation.predicate):
                # the D5 escape funnel: register tier=other, unconstrained
                # by signatures, ranked by usage for periodic promotion
                self._facts.ensure_other_predicate(
                    deployment_id=deployment_id, predicate=relation.predicate
                )
                predicates = {**predicates, relation.predicate: "related_to"}
            if relation.predicate not in predicates:
                _logger.warning(
                    "unknown predicate %r dropped for claim %s (re-derivable)",
                    relation.predicate,
                    claim.claim_id,
                )
                continue
            if not _signature_allows(
                predicate=relation.predicate,
                subject_type=relation.subject.type,
                object_type=relation.object.type,
                signatures=signatures,
                type_parents=type_parents,
            ):
                _logger.warning(
                    "signature-rejected %r (%s -> %s) for claim %s (re-derivable)",
                    relation.predicate,
                    relation.subject.type,
                    relation.object.type,
                    claim.claim_id,
                )
                continue
            subject = self._resolver.resolve(
                deployment_id=deployment_id, reference=relation.subject, claim=claim
            )
            object_ = self._resolver.resolve(
                deployment_id=deployment_id, reference=relation.object, claim=claim
            )
            if not _signature_allows(
                predicate=relation.predicate,
                subject_type=subject.entity_type,
                object_type=object_.entity_type,
                signatures=signatures,
                type_parents=type_parents,
            ):
                # the gate binds on the RESOLVED entities' stored types too —
                # T0 may map an emitted name onto a differently-typed entity
                # (Codex review); the candidate stays re-derivable.
                _logger.warning(
                    "signature-rejected %r on resolved types (%s -> %s), claim %s",
                    relation.predicate,
                    subject.entity_type,
                    object_.entity_type,
                    claim.claim_id,
                )
                continue
            upserted = self._facts.upsert_relation(
                deployment_id=deployment_id,
                subject_entity_id=subject.entity_id,
                predicate=relation.predicate,
                object_entity_id=object_.entity_id,
                claim_id=claim.claim_id,
                doc_id=claim.doc_id,
                normalizer_version=E3_NORMALIZER_VERSION,
            )
            if upserted.created:
                created_relations.append(str(upserted.relation_id))
        for observation in response.observations:
            subject = self._resolver.resolve(
                deployment_id=deployment_id, reference=observation.subject, claim=claim
            )
            # the one write path for observations is the D43 adjudicator:
            # block on the entity, gate cheaply, ladder the residue,
            # fail safe to coexist (observations §3)
            self._observation_adjudicator.add_observation(
                deployment_id=deployment_id,
                subject_entity_id=subject.entity_id,
                statement=observation.statement,
                claim_id=claim.claim_id,
                doc_id=claim.doc_id,
            )


def _signature_allows(
    *,
    predicate: str,
    subject_type: str,
    object_type: str,
    signatures: dict[str, tuple[tuple[str, str], ...]],
    type_parents: dict[str, str | None],
) -> bool:
    """The D18 domain/range gate: some signature matches at any ancestor level.

    Unknown emitted types fail closed; a predicate with no declared signatures
    is unconstrained (the registry's permissive parents, e.g. related_to).
    """
    if subject_type not in type_parents or object_type not in type_parents:
        return False
    declared = signatures.get(predicate)
    if not declared:
        return True
    subject_chain = _ancestor_chain(entity_type=subject_type, parents=type_parents)
    object_chain = _ancestor_chain(entity_type=object_type, parents=type_parents)
    return any(
        allowed_subject in subject_chain and allowed_object in object_chain
        for allowed_subject, allowed_object in declared
    )


def _ancestor_chain(
    *, entity_type: str, parents: dict[str, str | None]
) -> frozenset[str]:
    """The type plus every ancestor (extend-never-fork walk, cycle-safe)."""
    chain: set[str] = set()
    current: str | None = entity_type
    while current is not None and current not in chain:
        chain.add(current)
        current = parents.get(current)
    return frozenset(chain)


def _payload_uuid(*, work: ClaimedWork, field: str) -> UUID:
    """Read a required UUID from the claimed payload; absence is non-retryable."""
    value = (work.payload or {}).get(field)
    if not isinstance(value, str):
        raise NonRetryableHandlerError(
            f"stage {work.stage} work {work.processing_id} carries no {field!r} payload"
        )
    return UUID(value)


class AdjudicateSupersessionHandler:
    """The adjudication stage: each newly-created relation through the cascade."""

    def __init__(self, *, adjudicator: SupersessionAdjudicator) -> None:
        """Bind the handler to the composed adjudicator."""
        self._adjudicator = adjudicator

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Adjudicate every relation the normalize stage created (idempotent)."""
        payload = work.payload or {}
        relation_ids = payload.get("relation_ids") or []
        if not isinstance(relation_ids, list):
            raise NonRetryableHandlerError(
                f"work {work.processing_id} carries a malformed relation_ids payload"
            )
        for raw in relation_ids:
            self._adjudicator.adjudicate_new_relation(
                deployment_id=work.deployment_id, relation_id=UUID(str(raw))
            )
        return HandlerOutcome()
