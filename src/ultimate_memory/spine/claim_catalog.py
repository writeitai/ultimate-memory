"""The E2 claim catalog: accepted claims, the decision ledger, occurrence links.

One transaction lands a chunk's whole extraction: claims rows (which the
schema's CHECK constraints only admit past the deterministic grounding gate),
their `chunk_claims` occurrence links (D56/F4), and the append-only decision
transcript (D33). Replay reads what is stored and never re-calls the model.
"""

from uuid import UUID

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.model import ClaimForNormalization
from ultimate_memory.model import ClaimRecord
from ultimate_memory.model import DecisionRecord


class ClaimCatalog:
    """E2 row writes and replay checks over an explicitly composed engine."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the catalog to the spine database."""
        self._engine = engine

    def chunk_already_extracted(
        self, *, chunk_id: UUID, extractor_version: str
    ) -> bool:
        """Whether this extractor generation already processed the chunk (D12/D7).

        True if any claim or any ledgered decision exists — a chunk whose
        extraction yielded only drops is still done, not pending.
        """
        with self._engine.connect() as connection:
            return (
                connection.execute(
                    _SELECT_EXTRACTED,
                    {"chunk_id": chunk_id, "extractor_version": extractor_version},
                ).scalar_one()
                > 0
            )

    def claims_for_chunks(
        self, *, chunk_ids: tuple[UUID, ...]
    ) -> tuple[ClaimForNormalization, ...]:
        """Load the accepted claims of a chunk set for normalization (E3)."""
        if not chunk_ids:
            return ()
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _SELECT_CLAIMS_FOR_CHUNKS, {"chunk_ids": list(chunk_ids)}
                )
                .mappings()
                .all()
            )
        return tuple(ClaimForNormalization.model_validate(dict(row)) for row in rows)

    def record_extraction(
        self, *, claims: tuple[ClaimRecord, ...], decisions: tuple[DecisionRecord, ...]
    ) -> None:
        """Land one chunk's claims, occurrence links, and decisions atomically."""
        if not claims and not decisions:
            return
        with self._engine.begin() as connection:
            for claim in claims:
                payload = claim.model_dump(mode="json")
                payload["added_context"] = [
                    context.model_dump(mode="json") for context in claim.added_context
                ]
                connection.execute(_INSERT_CLAIM, payload)
                connection.execute(
                    _INSERT_CHUNK_CLAIM,
                    {
                        "deployment_id": claim.deployment_id,
                        "chunk_id": claim.chunk_id,
                        "claim_id": claim.claim_id,
                    },
                )
            for decision in decisions:
                connection.execute(_INSERT_DECISION, decision.model_dump(mode="json"))


_SELECT_EXTRACTED = text(
    """
    SELECT (SELECT count(*) FROM claims
            WHERE chunk_id = :chunk_id
              AND extractor_version = :extractor_version)
         + (SELECT count(*) FROM claim_extraction_decisions
            WHERE chunk_id = :chunk_id
              AND extractor_version = :extractor_version)
    """
)

_INSERT_CLAIM = text(
    """
    INSERT INTO claims (
        claim_id, deployment_id, doc_id, chunk_id, section_id,
        claim_text, source_span, char_start, char_end, added_context,
        is_attributed, anchor_ok, window_membership_ok,
        entailment_self_verdict, kept_flagged, extractor_version
    ) VALUES (
        :claim_id, :deployment_id, :doc_id, :chunk_id, :section_id,
        :claim_text, :source_span, :char_start, :char_end, :added_context,
        :is_attributed, true, true,
        :entailment_self_verdict, :kept_flagged, :extractor_version
    )
    """
).bindparams(bindparam("added_context", type_=JSON))

_INSERT_CHUNK_CLAIM = text(
    """
    INSERT INTO chunk_claims (deployment_id, chunk_id, claim_id, derivation_kind)
    VALUES (:deployment_id, :chunk_id, :claim_id, 'passthrough')
    """
)

_INSERT_DECISION = text(
    """
    INSERT INTO claim_extraction_decisions (
        decision_id, deployment_id, doc_id, chunk_id, claim_id,
        decision_type, source_span, reason, edit_detail,
        protected_class, extractor_version
    ) VALUES (
        :decision_id, :deployment_id, :doc_id, :chunk_id, :claim_id,
        :decision_type, :source_span, :reason, :edit_detail,
        :protected_class, :extractor_version
    )
    """
).bindparams(bindparam("edit_detail", type_=JSON))

_SELECT_CLAIMS_FOR_CHUNKS = text(
    """
    SELECT claim_id, doc_id, chunk_id, claim_text, is_attributed
    FROM claims
    WHERE chunk_id = ANY(:chunk_ids)
    ORDER BY ingested_at, claim_id
    """
)
