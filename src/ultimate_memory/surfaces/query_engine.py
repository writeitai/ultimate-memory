"""The zero-LLM query engine (retrieval §2-§3): resolve, lookup, search, hydrate.

The one correctness rule is D48: projections (P1 Lance) may NOMINATE
candidates, but every returned record has passed by-ID hydration against the
live Postgres spine — a superseded fact can never be served as current, and
nominations hydration rejects are counted in `dropped_by_hydration` so ranked
results are honest about their denominator. No primitive calls an LLM; reads
never trigger anything.
"""

from collections.abc import Iterator
from collections.abc import Sequence
from datetime import datetime
from datetime import UTC
from uuid import UUID

from sqlalchemy import text
from sqlalchemy import TextClause
from sqlalchemy.engine import Engine

from ultimate_memory.core.ranking import DEFAULT_RRF_K
from ultimate_memory.core.ranking import reciprocal_rank_fusion
from ultimate_memory.core.ranking import rerank_by_signal
from ultimate_memory.model import AggregateBucket
from ultimate_memory.model import AggregateReport
from ultimate_memory.model import ChangeRecord
from ultimate_memory.model import EmbeddingRequest
from ultimate_memory.model import EntityCandidate
from ultimate_memory.model import Envelope
from ultimate_memory.model import EvidenceResult
from ultimate_memory.model import FactResult
from ultimate_memory.model import Freshness
from ultimate_memory.model import Grain
from ultimate_memory.model import Negative
from ultimate_memory.model import NegativeKind
from ultimate_memory.model import PageRef
from ultimate_memory.model import RankedItem
from ultimate_memory.model import ScanRow
from ultimate_memory.model import SourceRecord
from ultimate_memory.model import TranscriptEntry
from ultimate_memory.model import Truncation
from ultimate_memory.model import Validity
from ultimate_memory.ports.model_provider import ModelProviderPort
from ultimate_memory.ports.p1_index import P1SearchPort
from ultimate_memory.spine.entity_registry import normalized_lemma

DEFAULT_DELTA_LIMIT = 500
"""How many change-feed rows one `delta` page returns before truncating —
a starting point to measure, not a committed constant (retrieval §13)."""

DEFAULT_SCAN_BATCH = 1_000
"""How many rows the batch `scan` cursor fetches per round-trip."""

_RERANK_SIGNALS = {"graph_distance": True, "evidence_count": False}
"""The inspectable rerank signals and whether each sorts ascending: nearer
the focal entity wins (ascending), more corroboration wins (descending)."""


class QueryEngine:
    """The typed read path over one deployment's spine and P1 indexes."""

    def __init__(
        self,
        *,
        engine: Engine,
        search_index: P1SearchPort,
        model_provider: ModelProviderPort,
        embedding_model: str,
        batch_engine: Engine | None = None,
    ) -> None:
        """Bind the engine to the spine, the P1 indexes, and the embedder.

        Embedding a query string is not an LLM call (retrieval §3): the
        provider's embed endpoint is the semantic channel's entry.

        `batch_engine` is the SEPARATE resource pool the batch surface uses
        (retrieval §9): `scan`'s streaming exports run against it so a large
        export can never starve the interactive connection pool. It defaults
        to the interactive engine — correct for a single-pool deployment —
        but a deployment that wants isolation passes a second engine bound
        to its own connection pool.
        """
        self._engine = engine
        self._search_index = search_index
        self._model_provider = model_provider
        self._embedding_model = embedding_model
        self._batch_engine = batch_engine or engine

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

    def transcript(
        self, *, deployment_id: UUID, subject_kind: str, subject_id: UUID
    ) -> Envelope:
        """The S8/S32/S35 audit query: any subject's decision history.

        "Why do we believe this?" as a first-class read, uniform across the
        four subjects a decision is about: a supersession-adjudicated
        `relation` or `observation`, a resolved/merged `entity` (its
        resolution decisions braided with its merges), or a compiled
        `k_page` (its compile provenance). Returned newest-last; reads never
        trigger anything. An empty history is `known_empty`, not a guess; an
        unknown kind is a `boundary` naming the four that exist.
        """
        statement = _TRANSCRIPT_BY_KIND.get(subject_kind)
        if statement is None:
            return Envelope(
                grain=Grain.COMPOSITE,
                freshness=_freshness(),
                negative=Negative(
                    kind=NegativeKind.BOUNDARY,
                    explanation=(f"no transcript for subject kind {subject_kind!r}"),
                    workaround="use one of: relation, observation, entity, k_page",
                ),
            )
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    statement,
                    {"deployment_id": deployment_id, "subject_id": subject_id},
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
                explanation=f"no decision history for this {subject_kind}",
                workaround=None,
            ),
        )

    def transcript_relation(
        self, *, deployment_id: UUID, relation_id: UUID
    ) -> Envelope:
        """A relation's decision history — the `transcript` primitive, relation
        arm (kept as the named surface the HTTP API and recipes bind to)."""
        return self.transcript(
            deployment_id=deployment_id, subject_kind="relation", subject_id=relation_id
        )

    def fuse(
        self, *, rankings: Sequence[Sequence[UUID]], k: int = DEFAULT_RRF_K
    ) -> Envelope:
        """RRF-merge parallel channel rankings into one order (D9/S46).

        An operator, not a spine read: the same reciprocal-rank fusion a
        recipe applies, exposed so an agent's ad-hoc channel set fuses
        identically. The grain is EVIDENCE — a fused order is over
        nominations still to be confirmed by id-hydration (D48), never
        current-fact truth on its own.
        """
        fused = reciprocal_rank_fusion(rankings=rankings, k=k)
        return Envelope(
            grain=Grain.EVIDENCE,
            ranking=fused,
            freshness=_freshness(),
            negative=None
            if fused
            else Negative(
                kind=NegativeKind.KNOWN_EMPTY,
                explanation="no channel supplied any candidate to fuse",
                workaround=None,
            ),
        )

    def rerank(self, *, items: Sequence[RankedItem], signal: str) -> Envelope:
        """Reorder candidates by one inspectable signal (D9/S46/S48).

        `graph_distance` and `evidence_count` are the shipped signals; each
        item carries its own signal value, so the stage is inspectable, not
        a black box. `cross_encoder` is a flagged capability that needs a
        configured reranker port and is off by default — asking for it, or
        for any unknown signal, is a typed `boundary`, never a silent
        identity sort.
        """
        if signal == "cross_encoder":
            return self._rerank_boundary(
                explanation=(
                    "cross-encoder reranking needs a configured reranker port"
                    " and is off by default"
                ),
                workaround="use graph_distance or evidence_count",
            )
        ascending = _RERANK_SIGNALS.get(signal)
        if ascending is None:
            return self._rerank_boundary(
                explanation=f"no rerank signal {signal!r}",
                workaround="use graph_distance or evidence_count",
            )
        ranked = rerank_by_signal(items=items, signal=signal, ascending=ascending)
        return Envelope(grain=Grain.EVIDENCE, ranking=ranked, freshness=_freshness())

    def delta(
        self,
        *,
        deployment_id: UUID,
        since: datetime,
        kinds: tuple[str, ...] | None = None,
        limit: int = DEFAULT_DELTA_LIMIT,
    ) -> Envelope:
        """The change feed as a query: what changed since `since` (S13/S14/S30).

        Four timestamped change types across the evidence kinds and K pages:
        `new` (ingested after `since`), `invalidated` (retracted after it),
        `capped` (a relation whose validity window a supersede closed — dated
        by the adjudication), and `recompiled` (a K page rebuilt after it).
        `kinds` filters to a subset of {relation, observation, claim, page}.
        Ordered newest-first and bounded: hitting `limit` sets an explicit
        truncation marker (never a silent cut), and the caller resumes from
        the oldest `at` it saw.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")
        kind_filter = list(kinds) if kinds else None
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _DELTA_FEED,
                    {
                        "deployment_id": deployment_id,
                        "since": since,
                        "kinds": kind_filter,
                        "fetch": limit + 1,
                    },
                )
                .mappings()
                .all()
            )
        truncated = len(rows) > limit
        changes = tuple(
            ChangeRecord(
                kind=row["kind"],
                change=row["change"],
                id=row["id"],
                label=row["label"],
                at=row["at"],
            )
            for row in rows[:limit]
        )
        return Envelope(
            grain=Grain.COMPOSITE,
            as_of_believed_at=since,
            changes=changes,
            freshness=_freshness(),
            truncation=Truncation(
                truncated=truncated,
                returned=len(changes),
                estimated_total=len(changes),
                total_is_exact=not truncated,
            ),
            negative=None
            if changes
            else Negative(
                kind=NegativeKind.KNOWN_EMPTY,
                explanation="nothing changed in the requested window",
                workaround=None,
            ),
        )

    def pages_about(
        self,
        *,
        deployment_id: UUID,
        entity_id: UUID | None = None,
        key_kind: str | None = None,
        key_value: str | None = None,
    ) -> Envelope:
        """Which K pages exist about a subject (S31/S45): the routing index,
        read backwards.

        The rule-key inverted index built to ROUTE writes doubles as the
        reader's discovery index — mechanically, no LLM. Pass an `entity_id`
        (shorthand for the `entity` key) or an explicit `key_kind`/`key_value`
        (`predicate`, `community`, `doc_source`). Each page reports its
        compile state and a `stale` flag — inputs changed but not yet
        recompiled — so discovery never presents an out-of-date page as
        fresh. COMPILED grain: these are pre-paid syntheses, not raw facts.
        """
        if entity_id is not None:
            key_kind, key_value = "entity", str(entity_id)
        if key_kind is None or key_value is None:
            raise ValueError("pages_about needs an entity_id or a key_kind+key_value")
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _PAGES_ABOUT,
                    {
                        "deployment_id": deployment_id,
                        "key_kind": key_kind,
                        "key_value": key_value,
                    },
                )
                .mappings()
                .all()
            )
        pages = tuple(
            PageRef(
                artifact_id=row["artifact_id"],
                page_kind=row["page_kind"],
                git_path=row["git_path"],
                page_summary=row["page_summary"],
                last_compiled_at=row["last_compiled_at"],
                status=row["status"],
                stale=row["stale"],
            )
            for row in rows
        )
        return Envelope(
            grain=Grain.COMPILED,
            pages=pages,
            freshness=_freshness(),
            negative=None
            if pages
            else Negative(
                kind=NegativeKind.KNOWN_EMPTY,
                explanation=f"no K pages route on {key_kind}={key_value!r}",
                workaround="query the primitives directly; K synthesis is optional",
            ),
        )

    def aggregate(
        self,
        *,
        deployment_id: UUID,
        form: str,
        subject_entity_id: UUID | None = None,
        predicate: str | None = None,
        entity_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> Envelope:
        """An enumerated aggregate — never a general GROUP BY (retrieval §9).

        Each `form` is a bounded SQL shape with a predictable cost, because
        an unbounded ad-hoc aggregation over 10⁸ rows is a denial of service
        against the spine (the escape hatch is `scan`). The forms: `count`,
        `group_by_predicate`, `group_by_object`, `timeline` (an entity's
        facts by year), `delta_top_entities` (evidence gained since T,
        bounded by the delta window — S30), and `typed_absence` (entities of
        a type with no relation of a predicate — S40, answerable because the
        ontology types entities). An unknown form is a typed `boundary`.
        """
        builder = _AGGREGATE_FORMS.get(form)
        if builder is None:
            return Envelope(
                grain=Grain.FACT,
                freshness=_freshness(),
                negative=Negative(
                    kind=NegativeKind.BOUNDARY,
                    explanation=f"no enumerated aggregate {form!r}",
                    workaround=f"use one of: {', '.join(sorted(_AGGREGATE_FORMS))}",
                ),
            )
        statement, needs = builder
        parameters = {
            "deployment_id": deployment_id,
            "subject_entity_id": subject_entity_id,
            "predicate": predicate,
            "entity_type": entity_type,
            "since": since,
            "limit": limit,
        }
        for required, value in (
            ("subject_entity_id", subject_entity_id),
            ("predicate", predicate),
            ("entity_type", entity_type),
            ("since", since),
        ):
            if required in needs and value is None:
                raise ValueError(f"aggregate {form!r} requires {required}")
        with self._engine.connect() as connection:
            rows = connection.execute(statement, parameters).mappings().all()
        buckets = tuple(
            AggregateBucket(
                key=None if row["key"] is None else str(row["key"]),
                count=row["count"],
                entity_id=row.get("entity_id"),
            )
            for row in rows
        )
        total = sum(bucket.count for bucket in buckets)
        return Envelope(
            grain=Grain.FACT,
            as_of_believed_at=since,
            aggregate=AggregateReport(
                form=form,
                buckets=buckets,
                total=total,
                bounded_by="delta window" if form == "delta_top_entities" else None,
            ),
            freshness=_freshness(),
        )

    def scan(
        self, *, deployment_id: UUID, kind: str, batch_size: int = DEFAULT_SCAN_BATCH
    ) -> Iterator[ScanRow]:
        """The batch surface (S53): stream a filtered export, row by row.

        A generator over the SEPARATE batch pool (`batch_engine`), using a
        server-side cursor so a full export streams in bounded memory and
        never buffers 10⁸ rows or starves the interactive pool. Same
        zero-LLM read, same grain labels; no interactive-latency promise.
        `kind` selects the export: `relation`, `observation`, or `claim`. An
        unknown kind raises rather than streaming a silent empty export.
        """
        statement = _SCAN_EXPORTS.get(kind)
        if statement is None:
            raise ValueError(
                f"no scan export {kind!r}; use relation, observation, or claim"
            )
        connection = self._batch_engine.connect().execution_options(stream_results=True)
        try:
            result = connection.execute(statement, {"deployment_id": deployment_id})
            for partition in result.mappings().partitions(batch_size):
                for row in partition:
                    yield ScanRow(
                        kind=kind, id=row["id"], label=row["label"], at=row["at"]
                    )
        finally:
            connection.close()

    def _rerank_boundary(self, *, explanation: str, workaround: str) -> Envelope:
        """A rerank request the engine cannot honor, as a typed boundary."""
        return Envelope(
            grain=Grain.EVIDENCE,
            freshness=_freshness(),
            negative=Negative(
                kind=NegativeKind.BOUNDARY,
                explanation=explanation,
                workaround=workaround,
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
    SELECT 'relation' AS subject_kind,
           outcome::text AS outcome, method::text AS method, confidence,
           related_relation_id AS related_id, decided_by::text AS decided_by,
           decided_at, features
    FROM relation_adjudications
    WHERE deployment_id = :deployment_id
      AND (relation_id = :subject_id OR related_relation_id = :subject_id)
    ORDER BY decided_at, adjudication_id
    """
)

_OBSERVATION_TRANSCRIPT = text(
    """
    SELECT 'observation' AS subject_kind,
           outcome::text AS outcome, method::text AS method, confidence,
           related_observation_id AS related_id, decided_by::text AS decided_by,
           decided_at, features
    FROM observation_adjudications
    WHERE deployment_id = :deployment_id
      AND (observation_id = :subject_id OR related_observation_id = :subject_id)
    ORDER BY decided_at, adjudication_id
    """
)

_ENTITY_TRANSCRIPT = text(
    """
    -- an entity's decision history braids two append-only logs: how each of
    -- its mentions resolved (resolution_decisions) and every merge it took
    -- part in (merge_events), newest-last across both
    SELECT 'entity' AS subject_kind,
           CASE WHEN is_new_entity THEN 'new_entity' ELSE 'linked' END AS outcome,
           method::text AS method, confidence,
           mention_id AS related_id, decided_by::text AS decided_by,
           decided_at, features
    FROM resolution_decisions
    WHERE deployment_id = :deployment_id AND entity_id = :subject_id
    UNION ALL
    SELECT 'entity' AS subject_kind,
           'merge' AS outcome, 'merge_event' AS method, NULL::real AS confidence,
           absorbed_id AS related_id, decided_by::text AS decided_by,
           decided_at, evidence AS features
    FROM merge_events
    WHERE deployment_id = :deployment_id
      AND (survivor_id = :subject_id OR absorbed_id = :subject_id)
    ORDER BY decided_at
    """
)

_KPAGE_TRANSCRIPT = text(
    """
    -- a K page's provenance is its compile history: each recompilation, what
    -- it cited, and the writer that produced it (S35)
    SELECT 'k_page' AS subject_kind,
           'compiled' AS outcome, writer_version AS method,
           NULL::real AS confidence, artifact_id AS related_id,
           'writer'::text AS decided_by, compiled_at AS decided_at,
           jsonb_build_object('cited', cited_count, 'uncited', uncited_count,
               'evidence_added', evidence_added,
               'evidence_removed', evidence_removed) AS features
    FROM knowledge_compilations
    WHERE deployment_id = :deployment_id AND artifact_id = :subject_id
    ORDER BY compiled_at, compilation_id
    """
)

_TRANSCRIPT_BY_KIND = {
    "relation": _RELATION_TRANSCRIPT,
    "observation": _OBSERVATION_TRANSCRIPT,
    "entity": _ENTITY_TRANSCRIPT,
    "k_page": _KPAGE_TRANSCRIPT,
}


_DELTA_FEED = text(
    """
    -- the change feed: one timestamped row per change, unioned across the
    -- evidence kinds and K pages, filtered by :since and an optional :kinds
    -- subset. Every branch dates its change on a real column, so a follow-up
    -- delta resumes deterministically from the oldest `at` returned.
    WITH feed AS (
        SELECT 'relation' AS kind, 'new' AS change, relation_id AS id,
               coalesce(fact_label, predicate) AS label, ingested_at AS at
        FROM relations
        WHERE deployment_id = :deployment_id AND ingested_at > :since
        UNION ALL
        SELECT 'relation', 'invalidated', relation_id,
               coalesce(fact_label, predicate), invalidated_at
        FROM relations
        WHERE deployment_id = :deployment_id AND invalidated_at > :since
        UNION ALL
        -- a supersede caps the OLD relation's window (ra.relation_id), dated
        -- by the adjudication that closed it
        SELECT 'relation', 'capped', r.relation_id,
               coalesce(r.fact_label, r.predicate), ra.decided_at
        FROM relation_adjudications ra
        JOIN relations r ON r.deployment_id = ra.deployment_id
                        AND r.relation_id = ra.relation_id
        WHERE ra.deployment_id = :deployment_id
          AND ra.outcome = 'supersede' AND ra.decided_at > :since
        UNION ALL
        SELECT 'observation', 'new', observation_id, statement, ingested_at
        FROM observations
        WHERE deployment_id = :deployment_id AND ingested_at > :since
        UNION ALL
        SELECT 'observation', 'invalidated', observation_id, statement,
               invalidated_at
        FROM observations
        WHERE deployment_id = :deployment_id AND invalidated_at > :since
        UNION ALL
        SELECT 'claim', 'new', claim_id, left(claim_text, 80), ingested_at
        FROM claims
        WHERE deployment_id = :deployment_id AND ingested_at > :since
        UNION ALL
        SELECT 'page', 'recompiled', artifact_id, NULL, compiled_at
        FROM knowledge_compilations
        WHERE deployment_id = :deployment_id AND compiled_at > :since
    )
    SELECT kind, change, id, label, at
    FROM feed
    WHERE CAST(:kinds AS text[]) IS NULL OR kind = ANY(:kinds)
    ORDER BY at DESC, id
    LIMIT :fetch
    """
)

_PAGES_ABOUT = text(
    """
    -- the rule-key inverted index read backwards: which artifacts route on
    -- (:key_kind, :key_value). One row per artifact (a page may hold several
    -- matching rules), each carrying its compile state and a stale flag —
    -- a page whose refresh is still queued has not caught up to its inputs.
    SELECT * FROM (
        SELECT DISTINCT ON (a.artifact_id)
               a.artifact_id, a.page_kind::text AS page_kind, a.git_path,
               a.page_summary, a.last_compiled_at, a.status::text AS status,
               (a.status::text = 'stale' OR EXISTS (
                    SELECT 1 FROM knowledge_refresh_queue q
                    WHERE q.deployment_id = a.deployment_id
                      AND q.artifact_id = a.artifact_id
                      AND q.processed_at IS NULL
               )) AS stale
        FROM knowledge_rule_keys rk
        JOIN knowledge_page_rules pr ON pr.deployment_id = rk.deployment_id
                                    AND pr.rule_id = rk.rule_id
        JOIN knowledge_artifacts a ON a.deployment_id = pr.deployment_id
                                  AND a.artifact_id = pr.artifact_id
        WHERE rk.deployment_id = :deployment_id
          AND rk.key_kind = CAST(:key_kind AS rule_key_kind)
          AND rk.key_value = :key_value
          AND a.status::text <> 'tombstoned'
        ORDER BY a.artifact_id
    ) page
    ORDER BY page.last_compiled_at DESC NULLS LAST, page.artifact_id
    """
)

_AGG_COUNT = text(
    """
    SELECT NULL::text AS key, count(*) AS count, NULL::uuid AS entity_id
    FROM relations
    WHERE deployment_id = :deployment_id AND invalidated_at IS NULL
      AND (CAST(:subject_entity_id AS uuid) IS NULL
           OR subject_entity_id = :subject_entity_id)
      AND (CAST(:predicate AS text) IS NULL OR predicate = :predicate)
    """
)

_AGG_GROUP_BY_PREDICATE = text(
    """
    SELECT predicate AS key, count(*) AS count, NULL::uuid AS entity_id
    FROM relations
    WHERE deployment_id = :deployment_id AND invalidated_at IS NULL
      AND subject_entity_id = :subject_entity_id
    GROUP BY predicate
    ORDER BY count DESC, predicate
    LIMIT :limit
    """
)

_AGG_GROUP_BY_OBJECT = text(
    """
    SELECT e.canonical_name AS key, count(*) AS count,
           r.object_entity_id AS entity_id
    FROM relations r
    JOIN entities e ON e.deployment_id = r.deployment_id
                   AND e.entity_id = r.object_entity_id
    WHERE r.deployment_id = :deployment_id AND r.invalidated_at IS NULL
      AND r.subject_entity_id = :subject_entity_id
      AND (CAST(:predicate AS text) IS NULL OR r.predicate = :predicate)
    GROUP BY e.canonical_name, r.object_entity_id
    ORDER BY count DESC, e.canonical_name
    LIMIT :limit
    """
)

_AGG_TIMELINE = text(
    """
    SELECT to_char(date_trunc('year', coalesce(valid_from, ingested_at)),
                   'YYYY') AS key,
           count(*) AS count, NULL::uuid AS entity_id
    FROM relations
    WHERE deployment_id = :deployment_id AND invalidated_at IS NULL
      AND (subject_entity_id = :subject_entity_id
           OR object_entity_id = :subject_entity_id)
    GROUP BY 1
    ORDER BY 1
    """
)

_AGG_DELTA_TOP_ENTITIES = text(
    """
    -- evidence gained since T, grouped by the subject entity, bounded by the
    -- delta window (S30): a leaderboard of what moved, not a full-history scan
    SELECT e.canonical_name AS key, count(*) AS count,
           r.subject_entity_id AS entity_id
    FROM relations r
    JOIN entities e ON e.deployment_id = r.deployment_id
                   AND e.entity_id = r.subject_entity_id
    WHERE r.deployment_id = :deployment_id AND r.ingested_at > :since
    GROUP BY e.canonical_name, r.subject_entity_id
    ORDER BY count DESC, e.canonical_name
    LIMIT :limit
    """
)

_AGG_TYPED_ABSENCE = text(
    """
    -- entities of a type with NO live relation of a predicate (S40): an
    -- anti-join, answerable because the ontology types entities. Each bucket
    -- IS one absent entity (count 1), so the total is how many lack it.
    SELECT e.canonical_name AS key, 1 AS count, e.entity_id AS entity_id
    FROM entities e
    WHERE e.deployment_id = :deployment_id AND e.status = 'active'
      AND e.type = :entity_type
      AND NOT EXISTS (
          SELECT 1 FROM relations r
          WHERE r.deployment_id = e.deployment_id
            AND r.subject_entity_id = e.entity_id
            AND r.predicate = :predicate
            AND r.invalidated_at IS NULL
      )
    ORDER BY e.canonical_name
    LIMIT :limit
    """
)

_AGGREGATE_FORMS: dict[str, tuple[TextClause, frozenset[str]]] = {
    "count": (_AGG_COUNT, frozenset()),
    "group_by_predicate": (_AGG_GROUP_BY_PREDICATE, frozenset({"subject_entity_id"})),
    "group_by_object": (_AGG_GROUP_BY_OBJECT, frozenset({"subject_entity_id"})),
    "timeline": (_AGG_TIMELINE, frozenset({"subject_entity_id"})),
    "delta_top_entities": (_AGG_DELTA_TOP_ENTITIES, frozenset({"since"})),
    "typed_absence": (_AGG_TYPED_ABSENCE, frozenset({"entity_type", "predicate"})),
}

_SCAN_EXPORTS = {
    "relation": text(
        """
        SELECT relation_id AS id, coalesce(fact_label, predicate) AS label,
               ingested_at AS at
        FROM relations
        WHERE deployment_id = :deployment_id
        ORDER BY ingested_at, relation_id
        """
    ),
    "observation": text(
        """
        SELECT observation_id AS id, statement AS label, ingested_at AS at
        FROM observations
        WHERE deployment_id = :deployment_id
        ORDER BY ingested_at, observation_id
        """
    ),
    "claim": text(
        """
        SELECT claim_id AS id, left(claim_text, 120) AS label,
               ingested_at AS at
        FROM claims
        WHERE deployment_id = :deployment_id
        ORDER BY ingested_at, claim_id
        """
    ),
}
