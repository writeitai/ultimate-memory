"""The add-observation worker (D43, observations §3): block, gate, adjudicate.

The same D4 engine as relation supersession, blocked on the RESOLVED ENTITY
instead of (subject, predicate) — exact and exhaustive, so nothing about an
entity can be missed. Most volume exits with zero LLM calls (first mention,
exact re-assertion, clear novelty); only the similar-but-not-identical
residue climbs the ladder. The binding fail-safe contract (not a schema
invariant): a supersede cap is permitted ONLY against a positively matched
prior above an explicit margin, every cap writes a reason row, and anything
below the margin or incomplete MUST coexist — the failure mode is a
duplicate, never an overwrite. The no-cap rule rides the verdict: a
fixed-period measurement is never superseded, conflicting same-period
figures contradict and both stand.
"""

from collections.abc import Sequence
from typing import Final
from uuid import UUID
from uuid import uuid4

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine
from sqlalchemy.engine import RowMapping

from ultimate_memory.model import EmbeddingRequest
from ultimate_memory.model import ModelRequest
from ultimate_memory.model import ObservationOutcome
from ultimate_memory.model import ObservationVerdict
from ultimate_memory.ports.model_provider import ModelProviderPort

OBSERVATION_ADJUDICATOR_VERSION: Final = "obs-adjudicator-2026.07"
"""The observation adjudicator generation (D12; replayed on rebuild, D7)."""

_VERDICT_PROMPT: Final = """You adjudicate observations for a memory system.
Both statements are believed facts about the SAME entity:

EXISTING: {existing!r}
NEW: {new!r}

Judge semantically (there are no typed columns — "FY2023" vs "fiscal 2023"
and "headcount" vs "staff count" are your equivalence calls):
- evidence: same property, same value, overlapping validity — the new
  statement re-asserts the existing one.
- supersede: same property, a CHANGING EFFECTIVE STATE (headcount, balance,
  status), and the value changed over time — the old window should cap.
  NEVER supersede a fixed-period measurement ("FY2023 revenue was $5M"): a
  figure does not stop being true at period-end.
- contradict: same property AND same reporting period, incompatible value —
  both must stand, surfaced together. (Different property, or different
  period, is NOT a contradiction.)
- new: a different property, period, or thing — no interaction."""


class ObservationSettings(BaseSettings):
    """The observation adjudicator's ladder and gate bindings (D4/D43)."""

    model_config = SettingsConfigDict(env_prefix="UGM_OBS_")

    small_model: str = Field(default="openai/gpt-5.6-luna")
    frontier_model: str = Field(default="openai/gpt-5.6-sol")
    embedding_model: str = Field(default="qwen/qwen3-embedding-8b")
    confidence_floor: float = Field(default=0.75, ge=0.0, le=1.0)
    supersede_margin: float = Field(default=0.8, ge=0.0, le=1.0)
    novelty_floor: float = Field(default=0.3, ge=-1.0, le=1.0)
    hub_top_k: int = Field(default=5, ge=1)


class ObservationAdjudicator:
    """The one write path for observations: outcomes applied atomically."""

    def __init__(
        self,
        *,
        engine: Engine,
        model_provider: ModelProviderPort,
        settings: ObservationSettings,
    ) -> None:
        """Bind the adjudicator to the spine and its ladder/gate models."""
        self._engine = engine
        self._model_provider = model_provider
        self._settings = settings

    def add_observation(
        self,
        *,
        deployment_id: UUID,
        subject_entity_id: UUID,
        statement: str,
        claim_id: UUID,
        doc_id: UUID,
    ) -> UUID:
        """Land one asserted value/statement through the full cascade.

        Returns the observation the claim ended up evidencing (existing on
        collapse, new otherwise). One transaction; the entity block is
        advisory-lock serialized; retries are no-ops via the evidence PK and
        the replayable adjudication log (D7).
        """
        with self._engine.begin() as connection:
            connection.execute(
                _LOCK_ENTITY, {"key": f"{deployment_id}:obs:{subject_entity_id}"}
            )
            exact = connection.execute(
                _EXACT_STATEMENT,
                {
                    "deployment_id": deployment_id,
                    "subject_entity_id": subject_entity_id,
                    "statement": statement,
                },
            ).scalar_one_or_none()
            if exact is not None:
                # corpus redundancy: the biggest zero-LLM exit
                self._evidence(
                    connection=connection,
                    deployment_id=deployment_id,
                    observation_id=exact,
                    claim_id=claim_id,
                    doc_id=doc_id,
                )
                return exact
            candidates = (
                connection.execute(
                    _BLOCK_ENTITY,
                    {
                        "deployment_id": deployment_id,
                        "subject_entity_id": subject_entity_id,
                    },
                )
                .mappings()
                .all()
            )
            if not candidates:
                return self._insert_new(
                    connection=connection,
                    deployment_id=deployment_id,
                    subject_entity_id=subject_entity_id,
                    statement=statement,
                    claim_id=claim_id,
                    doc_id=doc_id,
                    outcome="add",
                    method="novelty_gate",
                    confidence=1.0,
                    features={"reason": "first observation on the entity"},
                    related=None,
                    contradiction_group=None,
                )
            ranked = self._rank(statement=statement, candidates=candidates)
            if ranked[0][1] < self._settings.novelty_floor:
                return self._insert_new(
                    connection=connection,
                    deployment_id=deployment_id,
                    subject_entity_id=subject_entity_id,
                    statement=statement,
                    claim_id=claim_id,
                    doc_id=doc_id,
                    outcome="add",
                    method="embedding",
                    confidence=1.0,
                    features={
                        "reason": "clear novelty",
                        "max_similarity": ranked[0][1],
                    },
                    related=None,
                    contradiction_group=None,
                )
            return self._adjudicate_residue(
                connection=connection,
                deployment_id=deployment_id,
                subject_entity_id=subject_entity_id,
                statement=statement,
                claim_id=claim_id,
                doc_id=doc_id,
                ranked=ranked[: self._settings.hub_top_k],
            )

    def judge_statements(
        self, *, existing: str, new: str
    ) -> tuple[ObservationOutcome, float]:
        """The bare pair-decision function — the D43 eval gate's surface."""
        verdict, method = self._ladder(existing=existing, new=new)
        del method  # the gate grades outcomes; rungs are graded per-run cost
        return verdict.outcome, verdict.confidence

    def _adjudicate_residue(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        subject_entity_id: UUID,
        statement: str,
        claim_id: UUID,
        doc_id: UUID,
        ranked: list[tuple[dict[str, object], float]],
    ) -> UUID:
        """Ladder the similar candidates; apply the first decisive outcome."""
        for candidate, similarity in ranked:
            verdict, method = self._ladder(
                existing=str(candidate["statement"]), new=statement
            )
            features: dict[str, object] = {
                "similarity": similarity,
                "rationale": verdict.rationale,
            }
            candidate_id = UUID(str(candidate["observation_id"]))
            if verdict.outcome is ObservationOutcome.EVIDENCE:
                self._evidence(
                    connection=connection,
                    deployment_id=deployment_id,
                    observation_id=candidate_id,
                    claim_id=claim_id,
                    doc_id=doc_id,
                )
                self._record(
                    connection=connection,
                    deployment_id=deployment_id,
                    observation_id=candidate_id,
                    related=None,
                    outcome="noop",
                    method=method,
                    confidence=verdict.confidence,
                    claim_id=claim_id,
                    features={**features, "resolution": "evidence-collapse"},
                )
                return candidate_id
            if verdict.outcome is ObservationOutcome.SUPERSEDE:
                if verdict.confidence < self._settings.supersede_margin:
                    # THE BINDING CONTRACT: below the margin, never cap —
                    # coexist, and say why. The failure mode is a duplicate.
                    return self._insert_new(
                        connection=connection,
                        deployment_id=deployment_id,
                        subject_entity_id=subject_entity_id,
                        statement=statement,
                        claim_id=claim_id,
                        doc_id=doc_id,
                        outcome="noop",
                        method=method,
                        confidence=verdict.confidence,
                        features={
                            **features,
                            "reason": "supersede below margin -> coexist",
                        },
                        related=candidate_id,
                        contradiction_group=None,
                    )
                capped = connection.execute(
                    _CAP_WINDOW,
                    {"deployment_id": deployment_id, "observation_id": candidate_id},
                ).rowcount
                new_id = self._insert_new(
                    connection=connection,
                    deployment_id=deployment_id,
                    subject_entity_id=subject_entity_id,
                    statement=statement,
                    claim_id=claim_id,
                    doc_id=doc_id,
                    outcome="add",
                    method=method,
                    confidence=verdict.confidence,
                    features=features,
                    related=candidate_id,
                    contradiction_group=None,
                )
                self._record(  # every cap writes its reason row — no silent caps
                    connection=connection,
                    deployment_id=deployment_id,
                    observation_id=candidate_id,
                    related=new_id,
                    outcome="supersede",
                    method=method,
                    confidence=verdict.confidence,
                    claim_id=claim_id,
                    features={**features, "capped": bool(capped)},
                )
                return new_id
            if verdict.outcome is ObservationOutcome.CONTRADICT:
                stored_group = candidate["contradiction_group"]
                group = UUID(str(stored_group)) if stored_group is not None else uuid4()
                new_id = self._insert_new(
                    connection=connection,
                    deployment_id=deployment_id,
                    subject_entity_id=subject_entity_id,
                    statement=statement,
                    claim_id=claim_id,
                    doc_id=doc_id,
                    outcome="contradict",
                    method=method,
                    confidence=verdict.confidence,
                    features={**features, "contradiction_group": str(group)},
                    related=candidate_id,
                    contradiction_group=group,
                )
                connection.execute(
                    _SET_GROUP,
                    {
                        "deployment_id": deployment_id,
                        "observation_id": candidate_id,
                        "group_id": group,
                    },
                )
                return new_id
            # ObservationOutcome.NEW: no interaction with this candidate
        return self._insert_new(
            connection=connection,
            deployment_id=deployment_id,
            subject_entity_id=subject_entity_id,
            statement=statement,
            claim_id=claim_id,
            doc_id=doc_id,
            outcome="add",
            method="small_model",
            confidence=1.0,
            features={"reason": "no candidate interacted"},
            related=None,
            contradiction_group=None,
        )

    def _ladder(self, *, existing: str, new: str) -> tuple[ObservationVerdict, str]:
        """Small-model verdict, escalating to frontier below the floor."""
        prompt = _VERDICT_PROMPT.format(existing=existing, new=new)
        verdict = self._model_provider.generate(
            request=ModelRequest(model=self._settings.small_model, prompt=prompt),
            response_type=ObservationVerdict,
        )
        if verdict.confidence >= self._settings.confidence_floor:
            return verdict, "small_model"
        frontier = self._model_provider.generate(
            request=ModelRequest(model=self._settings.frontier_model, prompt=prompt),
            response_type=ObservationVerdict,
        )
        return frontier, "frontier_llm"

    def _rank(
        self, *, statement: str, candidates: Sequence[RowMapping]
    ) -> list[tuple[dict[str, object], float]]:
        """Similarity-rank candidates (ordering only — the block is already
        exhaustive, so a skipped candidate can never cause a wrong cap)."""
        texts = (statement, *(str(c["statement"]) for c in candidates))
        vectors = self._model_provider.embed(
            request=EmbeddingRequest(model=self._settings.embedding_model, texts=texts)
        ).vectors
        query = vectors[0]
        scored = [
            (dict(candidate), _cosine(query, vector))
            for candidate, vector in zip(candidates, vectors[1:], strict=True)
        ]
        return sorted(scored, key=lambda item: item[1], reverse=True)

    def _insert_new(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        subject_entity_id: UUID,
        statement: str,
        claim_id: UUID,
        doc_id: UUID,
        outcome: str,
        method: str,
        confidence: float,
        features: dict[str, object],
        related: UUID | None,
        contradiction_group: UUID | None,
    ) -> UUID:
        """Insert one observation + evidence + its adjudication row."""
        observation_id = uuid4()
        connection.execute(
            _INSERT_OBSERVATION,
            {
                "observation_id": observation_id,
                "deployment_id": deployment_id,
                "subject_entity_id": subject_entity_id,
                "statement": statement,
                "contradiction_group": contradiction_group,
                "normalizer_version": OBSERVATION_ADJUDICATOR_VERSION,
            },
        )
        self._evidence(
            connection=connection,
            deployment_id=deployment_id,
            observation_id=observation_id,
            claim_id=claim_id,
            doc_id=doc_id,
        )
        self._record(
            connection=connection,
            deployment_id=deployment_id,
            observation_id=observation_id,
            related=related,
            outcome=outcome,
            method=method,
            confidence=confidence,
            claim_id=claim_id,
            features=features,
        )
        return observation_id

    def _evidence(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        observation_id: UUID,
        claim_id: UUID,
        doc_id: UUID,
    ) -> None:
        """Evidence-once link + the D54 lineage-distinct recount."""
        connection.execute(
            _INSERT_EVIDENCE,
            {
                "deployment_id": deployment_id,
                "observation_id": observation_id,
                "claim_id": claim_id,
                "doc_id": doc_id,
                "normalizer_version": OBSERVATION_ADJUDICATOR_VERSION,
            },
        )
        connection.execute(_RECOUNT, {"observation_id": observation_id})

    def _record(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        observation_id: UUID,
        related: UUID | None,
        outcome: str,
        method: str,
        confidence: float,
        claim_id: UUID,
        features: dict[str, object],
    ) -> None:
        """Append one decision (never overwritten) — the audit surface."""
        connection.execute(
            _INSERT_ADJUDICATION,
            {
                "adjudication_id": uuid4(),
                "deployment_id": deployment_id,
                "observation_id": observation_id,
                "related_observation_id": related,
                "outcome": outcome,
                "method": method,
                "confidence": confidence,
                "triggering_claim_id": claim_id,
                "features": features,
                "adjudicator_version": OBSERVATION_ADJUDICATOR_VERSION,
            },
        )


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Cosine similarity of two same-dimension vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


_LOCK_ENTITY = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")

_EXACT_STATEMENT = text(
    """
    SELECT observation_id FROM observations
    WHERE deployment_id = :deployment_id
      AND subject_entity_id = :subject_entity_id
      AND statement = :statement
      AND invalidated_at IS NULL
    """
)

_BLOCK_ENTITY = text(
    """
    SELECT observation_id, statement, contradiction_group
    FROM observations
    WHERE deployment_id = :deployment_id
      AND subject_entity_id = :subject_entity_id
      AND invalidated_at IS NULL
      AND (valid_until IS NULL OR valid_until > now())
    ORDER BY created_at
    """
)

_INSERT_OBSERVATION = text(
    """
    INSERT INTO observations (
        observation_id, deployment_id, subject_entity_id, statement,
        obs_label, contradiction_group, normalizer_version
    ) VALUES (
        :observation_id, :deployment_id, :subject_entity_id, :statement,
        :statement, :contradiction_group, :normalizer_version
    )
    """
)

_CAP_WINDOW = text(
    """
    UPDATE observations
    SET valid_until = now(), updated_at = now()
    WHERE deployment_id = :deployment_id AND observation_id = :observation_id
      AND (valid_until IS NULL OR valid_until > now())
    """
)

_SET_GROUP = text(
    """
    UPDATE observations SET contradiction_group = :group_id, updated_at = now()
    WHERE deployment_id = :deployment_id AND observation_id = :observation_id
    """
)

_INSERT_EVIDENCE = text(
    """
    INSERT INTO observation_evidence (
        deployment_id, observation_id, claim_id, doc_id, stance,
        normalizer_version
    ) VALUES (
        :deployment_id, :observation_id, :claim_id, :doc_id, 'supports',
        :normalizer_version
    )
    ON CONFLICT (observation_id, claim_id) DO NOTHING
    """
)

_RECOUNT = text(
    """
    UPDATE observations SET evidence_count = (
        SELECT count(DISTINCT evidence.doc_id)
        FROM observation_evidence evidence
        JOIN claims ON claims.claim_id = evidence.claim_id
        WHERE evidence.observation_id = :observation_id
          AND evidence.stance = 'supports'
          AND claims.is_current_testimony
    ), updated_at = now()
    WHERE observation_id = :observation_id
    """
)

_INSERT_ADJUDICATION = text(
    """
    INSERT INTO observation_adjudications (
        adjudication_id, deployment_id, observation_id,
        related_observation_id, outcome, method, confidence,
        triggering_claim_id, features, adjudicator_version
    ) VALUES (
        :adjudication_id, :deployment_id, :observation_id,
        :related_observation_id, :outcome, :method, :confidence,
        :triggering_claim_id, :features, :adjudicator_version
    )
    """
).bindparams(bindparam("features", type_=JSON))
