"""T0 entity resolution over the alias registry (D17): exact match or mint.

T0 is the cheapest cascade tier: an exact match on the normalized
`llm_canonical` lemma. A miss mints a new canonical entity (the novelty path)
with its alias, and every resolution — hit or mint — writes the immutable
mention and an append-only resolution verdict. Higher tiers (T1-T4 blocking
and adjudication) arrive with the truth-machinery phase.
"""

from typing import Final
import unicodedata
from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.model import ClaimForNormalization
from ultimate_memory.model import EntityRef
from ultimate_memory.model import ResolvedEntity

T0_RESOLVER_VERSION: Final = "e3-resolver-t0-2026.07"
"""The T0-only resolver generation (walking skeleton; cascade tiers follow)."""


def normalized_lemma(*, surface: str) -> str:
    """The registry match key: accent-stripped, lowercased, whitespace-folded."""
    decomposed = unicodedata.normalize("NFKD", surface)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.lower().split())


class EntityRegistry:
    """Alias-registry resolution and mention/verdict writes for one deployment."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the registry to the spine database."""
        self._engine = engine

    def resolve_t0(
        self, *, deployment_id: UUID, reference: EntityRef, claim: ClaimForNormalization
    ) -> ResolvedEntity:
        """Resolve one reference by exact lemma match, minting on a miss.

        One transaction writes the mention, the entity + alias when minted,
        and the append-only T0 verdict (D17: verdicts supersede, never edit).
        """
        lemma = normalized_lemma(surface=reference.name)
        with self._engine.begin() as connection:
            existing = connection.execute(
                _SELECT_BY_LEMMA, {"deployment_id": deployment_id, "lemma": lemma}
            ).scalar_one_or_none()
            created = existing is None
            entity_id = existing if existing is not None else uuid4()
            if created:
                connection.execute(
                    _INSERT_ENTITY,
                    {
                        "entity_id": entity_id,
                        "deployment_id": deployment_id,
                        "type": reference.type,
                        "canonical_name": reference.name,
                        "normalized_name": lemma,
                    },
                )
                connection.execute(
                    _INSERT_ALIAS,
                    {
                        "alias_id": uuid4(),
                        "deployment_id": deployment_id,
                        "entity_id": entity_id,
                        "alias_text": reference.name,
                        "lemma": lemma,
                    },
                )
            mention_id = uuid4()
            connection.execute(
                _INSERT_MENTION,
                {
                    "mention_id": mention_id,
                    "deployment_id": deployment_id,
                    "surface_form": reference.name,
                    "lemma": lemma,
                    "canonical_name_form": reference.name,
                    "emitted_type": reference.type,
                    "claim_id": claim.claim_id,
                    "chunk_id": claim.chunk_id,
                    "doc_id": claim.doc_id,
                },
            )
            connection.execute(
                _INSERT_DECISION,
                {
                    "decision_id": uuid4(),
                    "deployment_id": deployment_id,
                    "mention_id": mention_id,
                    "entity_id": entity_id,
                    "is_new_entity": created,
                    "features": {"lemma": lemma},
                    "resolver_version": T0_RESOLVER_VERSION,
                },
            )
        return ResolvedEntity(entity_id=entity_id, created=created)

    def claim_already_normalized(self, *, claim_id: UUID) -> bool:
        """Whether normalization already ran for the claim (mention-backed replay).

        A claim that yielded no entities leaves no marker; its re-run on a
        crash-retry is bounded by the attempt limit and lands idempotently.
        """
        with self._engine.connect() as connection:
            return (
                connection.execute(_COUNT_MENTIONS, {"claim_id": claim_id}).scalar_one()
                > 0
            )


_SELECT_BY_LEMMA = text(
    """
    SELECT entity_id FROM aliases
    WHERE deployment_id = :deployment_id AND normalized_lemma = :lemma
    ORDER BY first_seen
    LIMIT 1
    """
)

_INSERT_ENTITY = text(
    """
    INSERT INTO entities (
        entity_id, deployment_id, type, canonical_name, normalized_name
    ) VALUES (
        :entity_id, :deployment_id, :type, :canonical_name, :normalized_name
    )
    """
)

_INSERT_ALIAS = text(
    """
    INSERT INTO aliases (
        alias_id, deployment_id, entity_id, alias_text, normalized_lemma, provenance
    ) VALUES (
        :alias_id, :deployment_id, :entity_id, :alias_text, :lemma, 'llm_canonical'
    )
    """
)

_INSERT_MENTION = text(
    """
    INSERT INTO mentions (
        mention_id, deployment_id, surface_form, normalized_lemma,
        canonical_name_form, emitted_type, claim_id, chunk_id, doc_id
    ) VALUES (
        :mention_id, :deployment_id, :surface_form, :lemma,
        :canonical_name_form, :emitted_type, :claim_id, :chunk_id, :doc_id
    )
    """
)

_INSERT_DECISION = text(
    """
    INSERT INTO resolution_decisions (
        decision_id, deployment_id, mention_id, entity_id, method,
        confidence, is_new_entity, features, resolver_version
    ) VALUES (
        :decision_id, :deployment_id, :mention_id, :entity_id, 'T0',
        1.0, :is_new_entity, :features, :resolver_version
    )
    """
).bindparams(bindparam("features", type_=JSON))

_COUNT_MENTIONS = text("SELECT count(*) FROM mentions WHERE claim_id = :claim_id")
