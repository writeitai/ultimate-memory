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
from ultimate_memory.model import TranscriptEntry
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
        valid_at: datetime | None = None,
    ) -> Envelope:
        """Relations matching the (s, p, o) pattern — fact grain (S1/S3/S9).

        Without `valid_at`, current means both clocks: still believed AND the
        valid-time window covers now. With `valid_at`, the window test moves
        to that instant (the S9-class as-of read; belief stays live — the
        believed_at axis arrives with its own parameter). The applied instant
        is echoed in the envelope. An existing entity with no matching facts
        is `known_empty` (S39).
        """
        as_of = valid_at or datetime.now(tz=UTC)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _LOOKUP_RELATIONS,
                    {
                        "deployment_id": deployment_id,
                        "subject_entity_id": subject_entity_id,
                        "predicate": predicate,
                        "object_entity_id": object_entity_id,
                        "as_of": as_of,
                    },
                )
                .mappings()
                .all()
            )
        facts = tuple(_fact_result(row=row, kind="relation") for row in rows)
        return Envelope(
            grain=Grain.FACT,
            as_of_valid_at=valid_at,
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
        valid_at: datetime | None = None,
    ) -> Envelope:
        """Observations on one entity — current, or as-of on the valid-time
        axis (S2/S9, D43): "headcount mid-2024" is the capped slice whose
        window covers that instant.

        With a property query, the facts channel NOMINATES by label similarity
        and the spine confirms live rows (D48); without one, the entity block
        is read directly.
        """
        dropped = 0
        as_of = valid_at or datetime.now(tz=UTC)
        if property_query is None:
            with self._engine.connect() as connection:
                rows = (
                    connection.execute(
                        _LOOKUP_OBSERVATIONS,
                        {
                            "deployment_id": deployment_id,
                            "entity_id": entity_id,
                            "as_of": as_of,
                        },
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
                as_of=as_of,
            )
        facts = tuple(_fact_result(row=row, kind="observation") for row in rows)
        return Envelope(
            grain=Grain.FACT,
            as_of_valid_at=valid_at,
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

        Composite grain: the fact, its supporting evidence-grain claims
        (verbatim spans and offsets against the representation they were cut
        from), and the ID-addressed document handles. Hydrate-by-ID is the
        AUDIT deepening hop: an invalidated relation is returned with its
        invalidation disclosed in `validity` (D48 re-reads and discloses —
        it does not refuse audit access); current-fact questions route
        through lookup, which filters both clocks.
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

    def transcript_relation(
        self, *, deployment_id: UUID, relation_id: UUID
    ) -> Envelope:
        """The S8 audit query: a relation's append-only decision history.

        Reads never trigger anything; the transcript is returned newest-last
        with each decision's rung, confidence, and features.
        """
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _RELATION_TRANSCRIPT,
                    {"deployment_id": deployment_id, "relation_id": relation_id},
                )
                .mappings()
                .all()
            )
        return Envelope(
            grain=Grain.COMPOSITE,
            transcript=tuple(TranscriptEntry.model_validate(dict(row)) for row in rows),
            freshness=_freshness(),
            negative=None
            if rows
            else Negative(
                kind=NegativeKind.KNOWN_EMPTY,
                explanation="no adjudication history for this relation",
                workaround=None,
            ),
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
        self,
        *,
        deployment_id: UUID,
        entity_id: UUID,
        observation_ids: tuple[UUID, ...],
        as_of: datetime,
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
                        "as_of": as_of,
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
    mapping = dict(row)
    return FactResult(
        fact_id=row["fact_id"],
        kind=kind,
        label=row["label"],
        evidence_count=row["evidence_count"],
        contradiction_group=mapping.get("contradiction_group"),
        validity=Validity(
            valid_from=row["valid_from"],
            valid_until=row["valid_until"],
            ingested_at=row["ingested_at"],
            invalidated_at=row["invalidated_at"],
        ),
    )


_RESOLVE_T0 = text(
    """
    WITH RECURSIVE matched AS (
        SELECT entities.entity_id, entities.canonical_name, entities.type,
               entities.status, entities.merged_into
        FROM aliases
        JOIN entities ON entities.deployment_id = aliases.deployment_id
                     AND entities.entity_id = aliases.entity_id
        WHERE aliases.deployment_id = :deployment_id
          AND aliases.normalized_lemma = :lemma
        UNION
        -- follow merge redirects to the survivor (S60: resolve returns
        -- CURRENT identities; the redirect chain is walked, never dead-ended)
        SELECT survivor.entity_id, survivor.canonical_name, survivor.type,
               survivor.status, survivor.merged_into
        FROM matched
        JOIN entities survivor ON survivor.deployment_id = :deployment_id
                              AND survivor.entity_id = matched.merged_into
        WHERE matched.status = 'merged'
    )
    SELECT DISTINCT entity_id, canonical_name, type
    FROM matched
    WHERE status = 'active'
      AND (CAST(:entity_type AS text) IS NULL OR type = :entity_type)
    """
)

_LOOKUP_RELATIONS = text(
    """
    SELECT relation_id AS fact_id,
           coalesce(fact_label, predicate) AS label,
           evidence_count, valid_from, valid_until, ingested_at, invalidated_at,
           contradiction_group
    FROM relations
    WHERE deployment_id = :deployment_id
      AND invalidated_at IS NULL
      AND (valid_from IS NULL OR valid_from <= :as_of)
      AND (valid_until IS NULL OR valid_until > :as_of)
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
           evidence_count, valid_from, valid_until, ingested_at, invalidated_at,
           contradiction_group
    FROM observations
    WHERE deployment_id = :deployment_id
      AND subject_entity_id = :entity_id
      AND invalidated_at IS NULL
      AND (valid_from IS NULL OR valid_from <= :as_of)
      AND (valid_until IS NULL OR valid_until > :as_of)
    ORDER BY evidence_count DESC, ingested_at
    """
)

_CONFIRM_OBSERVATIONS = text(
    """
    SELECT observation_id AS fact_id, statement AS label,
           evidence_count, valid_from, valid_until, ingested_at, invalidated_at,
           contradiction_group
    FROM observations
    WHERE deployment_id = :deployment_id
      AND subject_entity_id = :entity_id
      AND observation_id = ANY(:observation_ids)
      AND invalidated_at IS NULL
      AND (valid_from IS NULL OR valid_from <= :as_of)
      AND (valid_until IS NULL OR valid_until > :as_of)
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
    JOIN claims c ON c.claim_id = e.claim_id
    JOIN chunks ch ON ch.chunk_id = c.chunk_id
    JOIN documents d ON d.doc_id = e.doc_id
    LEFT JOIN document_representations r
           ON r.representation_id = ch.representation_id
    WHERE e.relation_id = :relation_id
      AND e.stance = 'supports'
    """
)

_RELATION_TRANSCRIPT = text(
    """
    SELECT outcome::text AS outcome, method::text AS method, confidence,
           related_relation_id, decided_by::text AS decided_by,
           decided_at, features
    FROM relation_adjudications
    WHERE deployment_id = :deployment_id
      AND (relation_id = :relation_id OR related_relation_id = :relation_id)
    ORDER BY decided_at, adjudication_id
    """
)
