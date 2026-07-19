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

from ultimate_memory.model import ClaimForEmbedding
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

        True if any claim, any ledgered decision, or any occurrence link
        exists — a chunk whose extraction yielded only drops is still done,
        and a chunk that REUSED prior claims (D56, occurrence links only) is
        equally done.
        """
        with self._engine.connect() as connection:
            return (
                connection.execute(
                    _SELECT_EXTRACTED,
                    {"chunk_id": chunk_id, "extractor_version": extractor_version},
                ).scalar_one()
                > 0
            )

    def prior_extracted_chunk(
        self,
        *,
        deployment_id: UUID,
        doc_id: UUID,
        chunk_id: UUID,
        extraction_input_hash: str,
    ) -> UUID | None:
        """The D56 reuse lookup: an already-extracted chunk with the same key.

        Searches the LINEAGE (extraction never reuses across documents —
        identical text in another document is that document's own testimony)
        for a different chunk carrying the same ``extraction_input_hash``
        that is already extracted. The key embeds the extractor and
        structurer versions, so a match is by construction the same
        generation reading the same stable inputs.
        """
        with self._engine.connect() as connection:
            return connection.execute(
                _SELECT_PRIOR_EXTRACTED,
                {
                    "deployment_id": deployment_id,
                    "doc_id": doc_id,
                    "chunk_id": chunk_id,
                    "extraction_input_hash": extraction_input_hash,
                },
            ).scalar_one_or_none()

    def attach_reused_claims(
        self, *, deployment_id: UUID, chunk_id: UUID, prior_chunk_id: UUID
    ) -> int:
        """Re-attach a prior chunk's claims to a new version's chunk (D56/F4).

        Copies the occurrence rows — claim ids with their derivation labels
        and locators — so one immutable claim attaches to every version-chunk
        that carried it. Idempotent: already-attached claims are skipped.
        Returns how many attachments this call created.
        """
        with self._engine.begin() as connection:
            result = connection.execute(
                _COPY_CHUNK_CLAIMS,
                {
                    "deployment_id": deployment_id,
                    "chunk_id": chunk_id,
                    "prior_chunk_id": prior_chunk_id,
                },
            )
        return result.rowcount or 0

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

    def claims_for_embedding(
        self, *, chunk_ids: tuple[UUID, ...], embedding_version: str
    ) -> tuple[ClaimForEmbedding, ...]:
        """Claims of a chunk set still lacking this embedding generation."""
        if not chunk_ids:
            return ()
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    _SELECT_CLAIMS_FOR_EMBEDDING,
                    {
                        "chunk_ids": list(chunk_ids),
                        "embedding_version": embedding_version,
                    },
                )
                .mappings()
                .all()
            )
        return tuple(ClaimForEmbedding.model_validate(dict(row)) for row in rows)

    def record_claim_embeddings(
        self, *, claim_ids: tuple[UUID, ...], embedding_version: str
    ) -> None:
        """Stamp embedded claims with their ref (= claim_id) and generation."""
        if not claim_ids:
            return
        with self._engine.begin() as connection:
            connection.execute(
                _STAMP_CLAIM_EMBEDDINGS,
                {"claim_ids": list(claim_ids), "embedding_version": embedding_version},
            )

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
         + (SELECT count(*) FROM chunk_claims
            WHERE chunk_id = :chunk_id)
    """
)

_SELECT_PRIOR_EXTRACTED = text(
    """
    SELECT c.chunk_id
    FROM chunks c
    WHERE c.deployment_id = :deployment_id
      AND c.doc_id = :doc_id
      AND c.chunk_id <> :chunk_id
      AND c.extraction_input_hash = :extraction_input_hash
      AND (EXISTS (SELECT 1 FROM chunk_claims x WHERE x.chunk_id = c.chunk_id)
           OR EXISTS (SELECT 1 FROM claim_extraction_decisions d
                      WHERE d.chunk_id = c.chunk_id))
    ORDER BY c.created_at DESC
    LIMIT 1
    """
)

_COPY_CHUNK_CLAIMS = text(
    """
    INSERT INTO chunk_claims (
        deployment_id, chunk_id, claim_id,
        derivation_kind, evidence_mode, source_locators
    )
    SELECT :deployment_id, :chunk_id, prior.claim_id,
           prior.derivation_kind, prior.evidence_mode, prior.source_locators
    FROM chunk_claims prior
    WHERE prior.chunk_id = :prior_chunk_id
      AND NOT EXISTS (SELECT 1 FROM chunk_claims existing
                      WHERE existing.chunk_id = :chunk_id
                        AND existing.claim_id = prior.claim_id)
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

_SELECT_CLAIMS_FOR_EMBEDDING = text(
    """
    SELECT claim_id, doc_id, chunk_id, claim_text,
           is_current_testimony, is_attributed
    FROM claims
    WHERE chunk_id = ANY(:chunk_ids)
      AND (embedding_version IS NULL OR embedding_version <> :embedding_version)
    ORDER BY ingested_at, claim_id
    """
)

_STAMP_CLAIM_EMBEDDINGS = text(
    """
    UPDATE claims
    SET embedding_ref = claim_id::text, embedding_version = :embedding_version
    WHERE claim_id = ANY(:claim_ids)
    """
)
