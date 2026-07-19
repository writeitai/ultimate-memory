"""The review queue (D24, registries §8, lifecycle §4): reversible verdicts.

Clusters, not pairs; only the expected-impact middle band reaches humans;
every action appends a reversible, provenance-stamped record — a merge
verdict lands in `merge_events` (decided_by=human), a support_withdrawn
verdict lands as a currency event (restore) or an invalidation with its
adjudication (invalidate). `uncertain` is the only non-terminal outcome and
deliberately leaves the marker standing.
"""

from typing import Final
from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine

from ultimate_memory.model import ReviewDecisionError
from ultimate_memory.model import ReviewItem
from ultimate_memory.spine.clustering import apply_merge

REVIEW_RECONCILIATION_NAMESPACE: Final = UUID("5e51e77e-0000-4000-8000-000000000000")


class ReviewQueue:
    """List, flag, and decide review items over an explicitly composed engine."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the queue to the spine database."""
        self._engine = engine

    def pending(
        self, *, deployment_id: UUID, limit: int = 20
    ) -> tuple[ReviewItem, ...]:
        """Open items ranked by expected impact (D24's routing score)."""
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _SELECT_PENDING, {"deployment_id": deployment_id, "limit": limit}
                )
                .mappings()
                .all()
            )
        return tuple(ReviewItem.model_validate(dict(row)) for row in rows)

    def flag_support_withdrawn(
        self,
        *,
        deployment_id: UUID,
        fact_kind: str,
        fact_id: UUID,
        claim_id: UUID,
        diff: dict[str, object],
    ) -> UUID:
        """Queue the only support_withdrawn trigger (lifecycle §4): a new
        toolchain generation re-read the unchanged file and did not re-derive
        the claim — no mechanical verdict is derivable."""
        review_id = uuid4()
        with self._engine.begin() as connection:
            connection.execute(
                _INSERT_REVIEW,
                {
                    "review_id": review_id,
                    "deployment_id": deployment_id,
                    "item_kind": "support_withdrawn",
                    "candidate": {
                        "fact_kind": fact_kind,
                        "fact_id": str(fact_id),
                        "claim_id": str(claim_id),
                        "diff": diff,
                    },
                    "blast_radius": 1,
                    "confidence": 0.5,
                    "expected_impact": 0.5,
                },
            )
        return review_id

    def decide_merge(
        self,
        *,
        deployment_id: UUID,
        review_id: UUID,
        verdict: str,
        reviewer: str,
        note: str | None = None,
    ) -> tuple[UUID, ...]:
        """Apply a merge-cluster verdict: merge performs it, not_merge closes.

        Returns the merge-event ids a `merge` verdict produced (empty for
        `not_merge`). Every merge is decided_by=human and fully reversible.
        """
        if verdict not in ("merge", "not_merge"):
            raise ReviewDecisionError(
                f"verdict {verdict!r} is not valid for a merge_cluster item"
            )
        with self._engine.begin() as connection:
            item = self._claim_item(
                connection=connection,
                deployment_id=deployment_id,
                review_id=review_id,
                expected_kind="merge_cluster",
            )
            events: tuple[UUID, ...] = ()
            if verdict == "merge":
                candidate = _candidate(item=item)
                survivor = UUID(str(candidate["survivor_id"]))
                events = tuple(
                    apply_merge(
                        connection=connection,
                        deployment_id=deployment_id,
                        survivor_id=survivor,
                        absorbed_id=UUID(str(absorbed)),
                        trigger_lemmas=[str(candidate.get("trigger_lemma", ""))],
                        evidence={"review_id": str(review_id), "note": note},
                        blast_radius=int(str(item["blast_radius"])),
                        decided_by="human",
                    )
                    for absorbed in list(candidate["absorbed_ids"])  # type: ignore[arg-type]
                )
                events = tuple(event for event in events if event is not None)
            connection.execute(
                _CLOSE_REVIEW,
                {
                    "review_id": review_id,
                    "status": "accepted" if verdict == "merge" else "rejected",
                    "verdict": verdict,
                    "verdict_note": note,
                    "assigned_to": reviewer,
                    "result_decision_id": events[0] if events else None,
                },
            )
        return events

    def decide_support_withdrawn(
        self,
        *,
        deployment_id: UUID,
        review_id: UUID,
        verdict: str,
        reviewer: str,
        note: str | None = None,
    ) -> None:
        """Apply a support_withdrawn triage verdict (lifecycle §4).

        restore_support: the old claim was right (the extractor regressed) —
        a currency event reinstates it and the fact's support recounts.
        invalidate_fact: the old claim was an extraction artifact — the fact
        leaves the current layer with a recorded adjudication.
        uncertain: non-terminal; the marker deliberately stands (deferred).
        """
        if verdict not in ("restore_support", "invalidate_fact", "uncertain"):
            raise ReviewDecisionError(
                f"verdict {verdict!r} is not valid for a support_withdrawn item"
            )
        with self._engine.begin() as connection:
            item = self._claim_item(
                connection=connection,
                deployment_id=deployment_id,
                review_id=review_id,
                expected_kind="support_withdrawn",
            )
            candidate = _candidate(item=item)
            fact_kind = str(candidate["fact_kind"])
            fact_id = UUID(str(candidate["fact_id"]))
            claim_id = UUID(str(candidate["claim_id"]))
            if verdict == "restore_support":
                self._restore_support(
                    connection=connection,
                    deployment_id=deployment_id,
                    fact_kind=fact_kind,
                    fact_id=fact_id,
                    claim_id=claim_id,
                    review_id=review_id,
                )
            elif verdict == "invalidate_fact":
                self._invalidate_fact(
                    connection=connection,
                    deployment_id=deployment_id,
                    fact_kind=fact_kind,
                    fact_id=fact_id,
                    claim_id=claim_id,
                    review_id=review_id,
                )
            connection.execute(
                _CLOSE_REVIEW,
                {
                    "review_id": review_id,
                    "status": "deferred" if verdict == "uncertain" else "accepted",
                    "verdict": verdict,
                    "verdict_note": note,
                    "assigned_to": reviewer,
                    "result_decision_id": None,
                },
            )

    def _restore_support(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        fact_kind: str,
        fact_id: UUID,
        claim_id: UUID,
        review_id: UUID,
    ) -> None:
        """The restore path: currency event + claim flag + support recount."""
        doc_id = connection.execute(_CLAIM_DOC, {"claim_id": claim_id}).scalar_one()
        connection.execute(
            _INSERT_CURRENCY_EVENT,
            {
                "event_id": uuid4(),
                "deployment_id": deployment_id,
                "claim_id": claim_id,
                "doc_id": doc_id,
                # a review decision is its own reconciliation run; stable per
                # review so a retried verdict re-emits as a no-op (UNIQUE)
                "reconciliation_id": review_id,
            },
        )
        connection.execute(_RESTORE_CLAIM_CURRENCY, {"claim_id": claim_id})
        self._recount(connection=connection, fact_kind=fact_kind, fact_id=fact_id)

    def _invalidate_fact(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        fact_kind: str,
        fact_id: UUID,
        claim_id: UUID,
        review_id: UUID,
    ) -> None:
        """The invalidate path: learned-wrong, recorded, out of the current layer."""
        if fact_kind == "relation":
            connection.execute(
                _INVALIDATE_RELATION,
                {"deployment_id": deployment_id, "relation_id": fact_id},
            )
            connection.execute(
                _INSERT_RELATION_ADJUDICATION,
                {
                    "adjudication_id": uuid4(),
                    "deployment_id": deployment_id,
                    "relation_id": fact_id,
                    "features": {
                        "action": "invalidate_fact",
                        "review_id": str(review_id),
                        "claim_id": str(claim_id),
                    },
                },
            )
        else:
            connection.execute(
                _INVALIDATE_OBSERVATION,
                {"deployment_id": deployment_id, "observation_id": fact_id},
            )
            connection.execute(
                _INSERT_OBSERVATION_ADJUDICATION,
                {
                    "adjudication_id": uuid4(),
                    "deployment_id": deployment_id,
                    "observation_id": fact_id,
                    "triggering_claim_id": claim_id,
                    "features": {
                        "action": "invalidate_fact",
                        "review_id": str(review_id),
                    },
                },
            )

    def _recount(
        self, *, connection: Connection, fact_kind: str, fact_id: UUID
    ) -> None:
        """The D54 lineage-distinct recount after a currency change."""
        statement = (
            _RECOUNT_RELATION if fact_kind == "relation" else _RECOUNT_OBSERVATION
        )
        connection.execute(statement, {"fact_id": fact_id})

    def _claim_item(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        review_id: UUID,
        expected_kind: str,
    ) -> dict[str, object]:
        """Lock one open item of the expected kind, or raise a typed error."""
        row = (
            connection.execute(
                _SELECT_ITEM_LOCKED,
                {"deployment_id": deployment_id, "review_id": review_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ReviewDecisionError(f"review item {review_id} does not exist")
        if row["status"] not in ("pending", "deferred"):
            raise ReviewDecisionError(
                f"review item {review_id} is already {row['status']}"
            )
        if row["item_kind"] != expected_kind:
            raise ReviewDecisionError(
                f"review item {review_id} is a {row['item_kind']}, "
                f"not a {expected_kind}"
            )
        return dict(row)


_SELECT_PENDING = text(
    """
    SELECT review_id, item_kind::text AS item_kind, candidate, blast_radius,
           confidence, expected_impact, status::text AS status, created_at
    FROM review_queue
    WHERE deployment_id = :deployment_id AND status IN ('pending', 'deferred')
    ORDER BY expected_impact DESC, created_at
    LIMIT :limit
    """
)

_SELECT_ITEM_LOCKED = text(
    """
    SELECT review_id, item_kind::text AS item_kind, candidate, blast_radius,
           status::text AS status
    FROM review_queue
    WHERE deployment_id = :deployment_id AND review_id = :review_id
    FOR UPDATE
    """
)

_INSERT_REVIEW = text(
    """
    INSERT INTO review_queue (
        review_id, deployment_id, item_kind, candidate, blast_radius,
        confidence, expected_impact
    ) VALUES (
        :review_id, :deployment_id, :item_kind, :candidate, :blast_radius,
        :confidence, :expected_impact
    )
    """
).bindparams(bindparam("candidate", type_=JSON))

_CLOSE_REVIEW = text(
    """
    UPDATE review_queue
    SET status = :status, verdict = :verdict, verdict_note = :verdict_note,
        assigned_to = :assigned_to, result_decision_id = :result_decision_id,
        resolved_at = now()
    WHERE review_id = :review_id
    """
)

_CLAIM_DOC = text("SELECT doc_id FROM claims WHERE claim_id = :claim_id")

_INSERT_CURRENCY_EVENT = text(
    """
    INSERT INTO testimony_currency_events (
        event_id, deployment_id, claim_id, doc_id, reconciliation_id,
        became_current, reason
    ) VALUES (
        :event_id, :deployment_id, :claim_id, :doc_id, :reconciliation_id,
        true, 'review_restored'
    )
    """
)

_RESTORE_CLAIM_CURRENCY = text(
    "UPDATE claims SET is_current_testimony = true WHERE claim_id = :claim_id"
)

_INVALIDATE_RELATION = text(
    """
    UPDATE relations SET invalidated_at = now(), updated_at = now()
    WHERE deployment_id = :deployment_id AND relation_id = :relation_id
      AND invalidated_at IS NULL
    """
)

_INVALIDATE_OBSERVATION = text(
    """
    UPDATE observations SET invalidated_at = now(), updated_at = now()
    WHERE deployment_id = :deployment_id AND observation_id = :observation_id
      AND invalidated_at IS NULL
    """
)

_INSERT_RELATION_ADJUDICATION = text(
    """
    INSERT INTO relation_adjudications (
        adjudication_id, deployment_id, relation_id, outcome, method,
        confidence, features, adjudicator_version, decided_by
    ) VALUES (
        :adjudication_id, :deployment_id, :relation_id, 'noop', 'exact',
        1.0, :features, 'review-2026.07', 'human'
    )
    """
).bindparams(bindparam("features", type_=JSON))

_INSERT_OBSERVATION_ADJUDICATION = text(
    """
    INSERT INTO observation_adjudications (
        adjudication_id, deployment_id, observation_id, outcome, method,
        confidence, triggering_claim_id, features, adjudicator_version,
        decided_by
    ) VALUES (
        :adjudication_id, :deployment_id, :observation_id, 'noop', 'exact',
        1.0, :triggering_claim_id, :features, 'review-2026.07', 'human'
    )
    """
).bindparams(bindparam("features", type_=JSON))

_RECOUNT_RELATION = text(
    """
    UPDATE relations SET evidence_count = (
        SELECT count(DISTINCT evidence.doc_id)
        FROM relation_evidence evidence
        JOIN claims ON claims.claim_id = evidence.claim_id
        WHERE evidence.relation_id = :fact_id
          AND evidence.stance = 'supports'
          AND claims.is_current_testimony
    ), updated_at = now()
    WHERE relation_id = :fact_id
    """
)

_RECOUNT_OBSERVATION = text(
    """
    UPDATE observations SET evidence_count = (
        SELECT count(DISTINCT evidence.doc_id)
        FROM observation_evidence evidence
        JOIN claims ON claims.claim_id = evidence.claim_id
        WHERE evidence.observation_id = :fact_id
          AND evidence.stance = 'supports'
          AND claims.is_current_testimony
    ), updated_at = now()
    WHERE observation_id = :fact_id
    """
)


def _candidate(*, item: dict[str, object]) -> dict[str, object]:
    """The item's candidate payload as a typed mapping."""
    candidate = item["candidate"]
    if not isinstance(candidate, dict):
        raise ReviewDecisionError("review item carries a malformed candidate")
    return candidate
