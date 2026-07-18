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
from ultimate_memory.spine.resolver import CascadeResolver
from ultimate_memory.workers.base import HandlerOutcome
from ultimate_memory.workers.p1 import FACT_LABEL_VERSION
from ultimate_memory.workers.p1 import P1_EMBED_CLAIMS_VERSION

_logger = logging.getLogger(__name__)

E3_NORMALIZER_VERSION: Final = "e3-normalize-2026.07"
"""The normalize sub-worker's component version (D12 idempotency member)."""

_NORMALIZE_PROMPT: Final = """You are the normalizer of a memory system. Turn
the CLAIM into zero or more of:
- relations: (subject, predicate, object) between TWO named entities, using
  ONLY the governed predicates listed below (map synonyms onto them; if none
  fits, emit nothing — never invent a predicate);
- observations: a value/property/statement about ONE entity, as a standalone
  statement ("Acme's headcount is 600"). An ATTRIBUTED stance claim ("X said /
  believes / opposes Y") becomes a stance observation anchored on X — never a
  fact about Y.
Entity names must be canonical nominative forms; entity types must come from
the registry types below. Time is never a relation object.

GOVERNED PREDICATES: {predicates}
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
        self._model_provider = model_provider
        self._settings = settings
        self._chunker_version = chunker_version

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Normalize one document version's claims into relations/observations."""
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
        signatures = self._facts.predicate_signatures(deployment_id=deployment_id)
        type_parents = self._facts.entity_type_parents(deployment_id=deployment_id)
        for claim in claims:
            if self._registry.claim_already_normalized(claim_id=claim.claim_id):
                continue  # replay: stored mentions/facts are the output (D7)
            self._normalize_claim(
                deployment_id=deployment_id,
                claim=claim,
                predicates=predicates,
                signatures=signatures,
                type_parents=type_parents,
            )
        return HandlerOutcome(
            follow_up=(
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
        deployment_id: UUID,
        claim: ClaimForNormalization,
        predicates: dict[str, str | None],
        signatures: dict[str, tuple[tuple[str, str], ...]],
        type_parents: dict[str, str | None],
    ) -> None:
        """One claim through the normalizer call and the deterministic gates."""
        response = self._model_provider.generate(
            request=ModelRequest(
                model=self._settings.normalize_model,
                prompt=_NORMALIZE_PROMPT.format(
                    predicates=", ".join(sorted(predicates)),
                    types=", ".join(sorted(type_parents)),
                    is_attributed=claim.is_attributed,
                    claim_text=claim.claim_text,
                ),
            ),
            response_type=NormalizationResponse,
        )
        for relation in response.relations:
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
            self._facts.upsert_relation(
                deployment_id=deployment_id,
                subject_entity_id=subject.entity_id,
                predicate=relation.predicate,
                object_entity_id=object_.entity_id,
                claim_id=claim.claim_id,
                doc_id=claim.doc_id,
                normalizer_version=E3_NORMALIZER_VERSION,
            )
        for observation in response.observations:
            subject = self._resolver.resolve(
                deployment_id=deployment_id, reference=observation.subject, claim=claim
            )
            self._facts.upsert_observation(
                deployment_id=deployment_id,
                subject_entity_id=subject.entity_id,
                statement=observation.statement,
                claim_id=claim.claim_id,
                doc_id=claim.doc_id,
                normalizer_version=E3_NORMALIZER_VERSION,
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
