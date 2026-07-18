"""The zero-LLM query engine (retrieval §2-§3): resolve, lookup, search, hydrate.

The one correctness rule is D48: projections (P1 Lance) may NOMINATE
candidates, but every returned record has passed by-ID hydration against the
live Postgres spine — a superseded fact can never be served as current, and
nominations hydration rejects are counted in `dropped_by_hydration` so ranked
results are honest about their denominator. No primitive calls an LLM; reads
never trigger anything.
"""

from datetime import datetime
from datetime import UTC
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.model import EmbeddingRequest
from ultimate_memory.model import EntityCandidate
from ultimate_memory.model import Envelope
from ultimate_memory.model import EvidenceResult
from ultimate_memory.model import FactResult
from ultimate_memory.model import Freshness
from ultimate_memory.model import Grain
from ultimate_memory.model import Negative
from ultimate_memory.model import NegativeKind
from ultimate_memory.model import SourceRecord
from ultimate_memory.model import Validity
from ultimate_memory.ports.model_provider import ModelProviderPort
from ultimate_memory.ports.p1_index import P1SearchPort
from ultimate_memory.spine.entity_registry import normalized_lemma


class QueryEngine:
    """The typed read path over one deployment's spine and P1 indexes."""

    def __init__(
        self,
        *,
        engine: Engine,
        search_index: P1SearchPort,
        model_provider: ModelProviderPort,
        embedding_model: str,
    ) -> None:
        """Bind the engine to the spine, the P1 indexes, and the embedder.

        Embedding a query string is not an LLM call (retrieval §3): the
        provider's embed endpoint is the semantic channel's entry.
        """
        self._engine = engine
        self._search_index = search_index
        self._model_provider = model_provider
        self._embedding_model = embedding_model

    def resolve(
        self, *, deployment_id: UUID, name: str, entity_type: str | None = None
    ) -> Envelope:
        """Resolve a name to ranked current entities (T0 in the skeleton).

        Nothing resolving is the `unknown_entity` negative (S39) — the agent
        widens resolution or searches; it never gets a silent guess (S51).
        """
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _RESOLVE_T0,
                    {
                        "deployment_id": deployment_id,
                        "lemma": normalized_lemma(surface=name),
                        "entity_type": entity_type,
                    },
                )
                .mappings()
                .all()
            )
        candidates = tuple(
            EntityCandidate(
                entity_id=row["entity_id"],
                canonical_name=row["canonical_name"],
                type=row["type"],
                tier="T0",
            )
            for row in rows
        )
        return Envelope(
            grain=Grain.FACT,
            entities=candidates,
            freshness=_freshness(),
            negative=None
            if candidates
            else Negative(
                kind=NegativeKind.UNKNOWN_ENTITY,
                explanation=f"nothing resolves for {name!r}",
                workaround="check spelling, try search over claims or chunks",
            ),
        )

    def lookup_relations(
        self,
        *,
        deployment_id: UUID,
        subject_entity_id: UUID | None = None,
        predicate: str | None = None,
        object_entity_id: UUID | None = None,
    ) -> Envelope:
        """Live relations matching the (s, p, o) pattern — fact grain (S1/S3).

        An existing entity with no matching live facts is `known_empty`: the
        absence is trustworthy within the stated freshness (S39).
        """
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _LOOKUP_RELATIONS,
                    {
                        "deployment_id": deployment_id,
                        "subject_entity_id": subject_entity_id,
                        "predicate": predicate,
                        "object_entity_id": object_entity_id,
                    },
                )
                .mappings()
                .all()
            )
        facts = tuple(_fact_result(row=row, kind="relation") for row in rows)
        return Envelope(
            grain=Grain.FACT,
            facts=facts,
            freshness=_freshness(),
            negative=None
            if facts
            else Negative(
                kind=NegativeKind.KNOWN_EMPTY,
                explanation="no live relations match the pattern",
                workaround=None,
            ),
        )

    def lookup_observations(
        self,
        *,
        deployment_id: UUID,
        entity_id: UUID,
        property_query: str | None = None,
        k: int = 10,
    ) -> Envelope:
        """Live observations on one entity — semantic over statements (S2, D43).

        With a property query, the facts channel NOMINATES by label similarity
        and the spine confirms live rows (D48); without one, the entity block
        is read directly.
        """
        dropped = 0
        if property_query is None:
            with self._engine.connect() as connection:
                rows = (
                    connection.execute(
                        _LOOKUP_OBSERVATIONS,
                        {"deployment_id": deployment_id, "entity_id": entity_id},
                    )
                    .mappings()
                    .all()
                )
        else:
            nominated = self._search_index.search_facts(
                deployment_id=str(deployment_id),
                vector=self._embed(query=property_query),
                k=k,
                kind="observation",
            )
            rows, dropped = self._confirm_observations(
                deployment_id=deployment_id,
                entity_id=entity_id,
                observation_ids=tuple(UUID(item) for item in nominated),
            )
        facts = tuple(_fact_result(row=row, kind="observation") for row in rows)
        return Envelope(
            grain=Grain.FACT,
            facts=facts,
            freshness=_freshness(),
            dropped_by_hydration=dropped,
            negative=None
            if facts
            else Negative(
                kind=NegativeKind.KNOWN_EMPTY,
                explanation="no live observations match on this entity",
                workaround=None,
            ),
        )

    def search_claims(
        self, *, deployment_id: UUID, query: str, k: int = 10
    ) -> Envelope:
        """Semantic claim search — EVIDENCE grain, never a current-fact answer.

        The claims channel nominates (current-testimony-only by default);
        hydration re-reads each claim from the spine and drops what no longer
        confirms, counting the drops (D48 nominate-then-drop honesty).
        """
        nominated = self._search_index.search_claims(
            deployment_id=str(deployment_id),
            vector=self._embed(query=query),
            k=k,
            current_only=True,
        )
        evidence, dropped = self._confirm_claims(
            deployment_id=deployment_id,
            claim_ids=tuple(UUID(item) for item in nominated),
        )
        return Envelope(
            grain=Grain.EVIDENCE,
            evidence=evidence,
            freshness=_freshness(),
            dropped_by_hydration=dropped,
            negative=None
            if evidence
            else Negative(
                kind=NegativeKind.KNOWN_EMPTY,
                explanation="no current-testimony claims match the query",
                workaround="search chunks, or widen with current_only=false",
            ),
        )

    def hydrate_relation(self, *, deployment_id: UUID, relation_id: UUID) -> Envelope:
        """The S5 chain: relation → evidence claims → source documents.

        Composite grain: the fact, its evidence-grain claims (verbatim spans
        and offsets), and the ID-addressed document handles.
        """
        with self._engine.connect() as connection:
            relation = (
                connection.execute(
                    _HYDRATE_RELATION,
                    {"deployment_id": deployment_id, "relation_id": relation_id},
                )
                .mappings()
                .one_or_none()
            )
            if relation is None:
                return Envelope(
                    grain=Grain.COMPOSITE,
                    freshness=_freshness(),
                    negative=Negative(
                        kind=NegativeKind.UNKNOWN_ENTITY,
                        explanation=f"relation {relation_id} does not exist",
                        workaround=None,
                    ),
                )
            claims = (
                connection.execute(
                    _HYDRATE_EVIDENCE_CLAIMS, {"relation_id": relation_id}
                )
                .mappings()
                .all()
            )
            sources = (
                connection.execute(_HYDRATE_SOURCES, {"relation_id": relation_id})
                .mappings()
                .all()
            )
        return Envelope(
            grain=Grain.COMPOSITE,
            facts=(_fact_result(row=relation, kind="relation"),),
            evidence=tuple(EvidenceResult.model_validate(dict(row)) for row in claims),
            sources=tuple(SourceRecord.model_validate(dict(row)) for row in sources),
            freshness=_freshness(),
        )

    def _confirm_claims(
        self, *, deployment_id: UUID, claim_ids: tuple[UUID, ...]
    ) -> tuple[tuple[EvidenceResult, ...], int]:
        """The D48 confirmation hop for claim nominations, order-preserving."""
        if not claim_ids:
            return (), 0
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _CONFIRM_CLAIMS,
                    {"deployment_id": deployment_id, "claim_ids": list(claim_ids)},
                )
                .mappings()
                .all()
            )
        confirmed = {row["claim_id"]: row for row in rows}
        results = tuple(
            EvidenceResult.model_validate(dict(confirmed[claim_id]))
            for claim_id in claim_ids
            if claim_id in confirmed
        )
        return results, len(claim_ids) - len(results)

    def _confirm_observations(
        self, *, deployment_id: UUID, entity_id: UUID, observation_ids: tuple[UUID, ...]
    ) -> tuple[tuple[dict[str, object], ...], int]:
        """The D48 confirmation hop for observation nominations."""
        if not observation_ids:
            return (), 0
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _CONFIRM_OBSERVATIONS,
                    {
                        "deployment_id": deployment_id,
                        "entity_id": entity_id,
                        "observation_ids": list(observation_ids),
                    },
                )
                .mappings()
                .all()
            )
        confirmed = {row["fact_id"]: dict(row) for row in rows}
        results = tuple(
            confirmed[observation_id]
            for observation_id in observation_ids
            if observation_id in confirmed
        )
        return results, len(observation_ids) - len(results)

    def _embed(self, *, query: str) -> tuple[float, ...]:
        """One query-string embedding through the configured port (D63)."""
        response = self._model_provider.embed(
            request=EmbeddingRequest(model=self._embedding_model, texts=(query,))
        )
        return response.vectors[0]


def _freshness() -> Freshness:
    """The skeleton's freshness stamps: PG is live; P1 is written inline."""
    return Freshness(pg_live_ts=datetime.now(tz=UTC))


def _fact_result(*, row, kind: str) -> FactResult:  # noqa: ANN001
    """Build one fact-grain record from a hydrated spine row."""
    return FactResult(
        fact_id=row["fact_id"],
        kind=kind,
        label=row["label"],
        evidence_count=row["evidence_count"],
        validity=Validity(
            valid_from=row["valid_from"],
            valid_until=row["valid_until"],
            ingested_at=row["ingested_at"],
            invalidated_at=row["invalidated_at"],
        ),
    )


_RESOLVE_T0 = text(
    """
    SELECT DISTINCT entities.entity_id, entities.canonical_name, entities.type
    FROM aliases
    JOIN entities ON entities.deployment_id = aliases.deployment_id
                 AND entities.entity_id = aliases.entity_id
    WHERE aliases.deployment_id = :deployment_id
      AND aliases.normalized_lemma = :lemma
      AND entities.status = 'active'
      AND (CAST(:entity_type AS text) IS NULL OR entities.type = :entity_type)
    """
)

_LOOKUP_RELATIONS = text(
    """
    SELECT relation_id AS fact_id,
           coalesce(fact_label, predicate) AS label,
           evidence_count, valid_from, valid_until, ingested_at, invalidated_at
    FROM relations
    WHERE deployment_id = :deployment_id
      AND invalidated_at IS NULL
      AND (CAST(:subject_entity_id AS uuid) IS NULL
           OR subject_entity_id = :subject_entity_id)
      AND (CAST(:predicate AS text) IS NULL OR predicate = :predicate)
      AND (CAST(:object_entity_id AS uuid) IS NULL
           OR object_entity_id = :object_entity_id)
    ORDER BY evidence_count DESC, ingested_at
    """
)

_LOOKUP_OBSERVATIONS = text(
    """
    SELECT observation_id AS fact_id, statement AS label,
           evidence_count, valid_from, valid_until, ingested_at, invalidated_at
    FROM observations
    WHERE deployment_id = :deployment_id
      AND subject_entity_id = :entity_id
      AND invalidated_at IS NULL
    ORDER BY evidence_count DESC, ingested_at
    """
)

_CONFIRM_OBSERVATIONS = text(
    """
    SELECT observation_id AS fact_id, statement AS label,
           evidence_count, valid_from, valid_until, ingested_at, invalidated_at
    FROM observations
    WHERE deployment_id = :deployment_id
      AND subject_entity_id = :entity_id
      AND observation_id = ANY(:observation_ids)
      AND invalidated_at IS NULL
    """
)

_CONFIRM_CLAIMS = text(
    """
    SELECT claim_id, doc_id, chunk_id, claim_text, source_span,
           char_start, char_end, is_attributed, is_current_testimony
    FROM claims
    WHERE deployment_id = :deployment_id
      AND claim_id = ANY(:claim_ids)
      AND is_current_testimony
    """
)

_HYDRATE_RELATION = text(
    """
    SELECT relation_id AS fact_id,
           coalesce(fact_label, predicate) AS label,
           evidence_count, valid_from, valid_until, ingested_at, invalidated_at
    FROM relations
    WHERE deployment_id = :deployment_id AND relation_id = :relation_id
    """
)

_HYDRATE_EVIDENCE_CLAIMS = text(
    """
    SELECT c.claim_id, c.doc_id, c.chunk_id, c.claim_text, c.source_span,
           c.char_start, c.char_end, c.is_attributed, c.is_current_testimony
    FROM relation_evidence e
    JOIN claims c ON c.claim_id = e.claim_id
    WHERE e.relation_id = :relation_id AND e.stance = 'supports'
    ORDER BY c.ingested_at, c.claim_id
    """
)

_HYDRATE_SOURCES = text(
    """
    SELECT DISTINCT d.doc_id, d.title, d.source_kind, r.markdown_uri
    FROM relation_evidence e
    JOIN documents d ON d.doc_id = e.doc_id
    LEFT JOIN document_versions v ON v.version_id = d.current_version_id
    LEFT JOIN document_representations r
           ON r.representation_id = v.current_representation_id
    WHERE e.relation_id = :relation_id
    """
)
