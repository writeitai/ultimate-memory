"""The relation supersession cascade (D3/D4): blocking → novelty → ladder.

Adjudication operates on RELATIONS, never claims (D3): "Alice left Acme"
closes the validity window of `(alice, works_for, acme)` — one row update —
while every claim stays an immutable record of what sources asserted.
Candidates are found by `(subject, predicate)` blocking over the small
distinct-fact table, only for change-prone predicates; a novelty gate routes
clear ADDs past the LLM entirely; the ambiguous residue climbs the
small→frontier ladder. Every decision lands append-only in
`relation_adjudications` — the S8 "why do we believe…" audit surface — and
the adjudicator fails safe to coexist when unsure.
"""

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

from ultimate_memory.model import ModelRequest
from ultimate_memory.model import SupersessionOutcome
from ultimate_memory.model import SupersessionVerdict
from ultimate_memory.ports.model_provider import ModelProviderPort

ADJUDICATOR_VERSION: Final = "adjudicator-2026.07"
"""The supersession adjudicator generation (D12; replayed on rebuild, D7)."""

_ADJUDICATION_PROMPT: Final = """You adjudicate fact supersession for a memory
system. Two believed facts share a subject and a change-prone predicate:

EXISTING: {existing_label}
  evidence: {existing_evidence!r} (asserted {existing_asserted})
NEW: {new_label}
  evidence: {new_evidence!r} (asserted {new_asserted})

Decide:
- supersede: the world changed — the NEW fact replaces the EXISTING one
  (e.g. a job change); the existing fact's validity window should close.
- coexist: both hold simultaneously (e.g. dual employment). When unsure,
  prefer coexist — a wrong supersession silently hides a true fact.
- contradict: the sources describe the SAME period incompatibly; both must
  stand, surfaced together."""


class SupersessionSettings(BaseSettings):
    """The adjudicator ladder bindings (D4/D53; port-default principle)."""

    model_config = SettingsConfigDict(env_prefix="UGM_ADJUDICATOR_")

    small_model: str = Field(default="openai/gpt-5.6-luna")
    frontier_model: str = Field(default="openai/gpt-5.6-sol")
    confidence_floor: float = Field(default=0.75, ge=0.0, le=1.0)


class SupersessionAdjudicator:
    """Adjudicate each newly-created relation against its blocked candidates."""

    def __init__(
        self,
        *,
        engine: Engine,
        model_provider: ModelProviderPort,
        settings: SupersessionSettings,
    ) -> None:
        """Bind the adjudicator to the spine and the ladder models."""
        self._engine = engine
        self._model_provider = model_provider
        self._settings = settings

    def adjudicate_new_relation(
        self, *, deployment_id: UUID, relation_id: UUID
    ) -> None:
        """Run the cascade for one new relation (idempotent per generation).

        A non-change-prone predicate, or an empty blocking set, is a clear
        ADD decided by the novelty gate with no model call. Each blocked
        candidate is adjudicated on the ladder; outcomes are applied and
        recorded atomically.
        """
        with self._engine.begin() as connection:
            if self._already_adjudicated(
                connection=connection, relation_id=relation_id
            ):
                return
            subject = (
                connection.execute(
                    _LOAD_RELATION,
                    {"deployment_id": deployment_id, "relation_id": relation_id},
                )
                .mappings()
                .one_or_none()
            )
            if subject is None or subject["invalidated_at"] is not None:
                return  # gone or already retired: nothing to adjudicate
            if not subject["is_change_prone"]:
                self._record(
                    connection=connection,
                    deployment_id=deployment_id,
                    relation_id=relation_id,
                    related_relation_id=None,
                    outcome="add",
                    method="novelty_gate",
                    confidence=1.0,
                    features={"reason": "predicate is not change-prone"},
                )
                return
            candidates = (
                connection.execute(
                    _BLOCK_CANDIDATES,
                    {
                        "deployment_id": deployment_id,
                        "relation_id": relation_id,
                        "subject_entity_id": subject["subject_entity_id"],
                        "predicate": subject["predicate"],
                    },
                )
                .mappings()
                .all()
            )
            if not candidates:
                self._record(
                    connection=connection,
                    deployment_id=deployment_id,
                    relation_id=relation_id,
                    related_relation_id=None,
                    outcome="add",
                    method="novelty_gate",
                    confidence=1.0,
                    features={"reason": "no blocked candidates"},
                )
                return
            for candidate in candidates:
                self._adjudicate_pair(
                    connection=connection,
                    deployment_id=deployment_id,
                    new=dict(subject),
                    new_relation_id=relation_id,
                    old=dict(candidate),
                )

    def _adjudicate_pair(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        new: dict[str, object],
        new_relation_id: UUID,
        old: dict[str, object],
    ) -> None:
        """Climb the ladder for one blocked pair and apply the outcome."""
        prompt = _ADJUDICATION_PROMPT.format(
            existing_label=old["label"],
            existing_evidence=old["evidence_text"],
            existing_asserted=old["asserted_at"] or "unknown",
            new_label=new["label"],
            new_evidence=new["evidence_text"],
            new_asserted=new["asserted_at"] or "unknown",
        )
        verdict = self._model_provider.generate(
            request=ModelRequest(model=self._settings.small_model, prompt=prompt),
            response_type=SupersessionVerdict,
        )
        method = "small_model"
        model = self._settings.small_model
        if verdict.confidence < self._settings.confidence_floor:
            verdict = self._model_provider.generate(
                request=ModelRequest(
                    model=self._settings.frontier_model, prompt=prompt
                ),
                response_type=SupersessionVerdict,
            )
            method = "frontier_llm"
            model = self._settings.frontier_model
        features: dict[str, object] = {"model": model, "rationale": verdict.rationale}
        old_relation_id = UUID(str(old["relation_id"]))
        if verdict.outcome is SupersessionOutcome.SUPERSEDE:
            # the boundary: the new testimony's assertion time, else now —
            # recorded so the closure is auditable (D3/D41 seeding refines it)
            connection.execute(
                _CLOSE_WINDOW,
                {
                    "deployment_id": deployment_id,
                    "relation_id": old_relation_id,
                    "boundary_asserted": new["asserted_at"],
                },
            )
            self._record(
                connection=connection,
                deployment_id=deployment_id,
                relation_id=old_relation_id,
                related_relation_id=new_relation_id,
                outcome="supersede",
                method=method,
                confidence=verdict.confidence,
                features={**features, "boundary": str(new["asserted_at"] or "now")},
            )
        elif verdict.outcome is SupersessionOutcome.CONTRADICT:
            group = old["contradiction_group"] or uuid4()
            connection.execute(
                _SET_CONTRADICTION_GROUP,
                {
                    "deployment_id": deployment_id,
                    "relation_ids": [old_relation_id, new_relation_id],
                    "group_id": group,
                },
            )
            self._record(
                connection=connection,
                deployment_id=deployment_id,
                relation_id=new_relation_id,
                related_relation_id=old_relation_id,
                outcome="contradict",
                method=method,
                confidence=verdict.confidence,
                features={**features, "contradiction_group": str(group)},
            )
        else:  # coexist — the fail-safe: both stand, nothing changes
            self._record(
                connection=connection,
                deployment_id=deployment_id,
                relation_id=new_relation_id,
                related_relation_id=old_relation_id,
                outcome="noop",
                method=method,
                confidence=verdict.confidence,
                features=features,
            )

    def _already_adjudicated(
        self, *, connection: Connection, relation_id: UUID
    ) -> bool:
        """Replay check (D7): any decision of this generation is terminal."""
        return (
            connection.execute(
                _COUNT_ADJUDICATIONS,
                {
                    "relation_id": relation_id,
                    "adjudicator_version": ADJUDICATOR_VERSION,
                },
            ).scalar_one()
            > 0
        )

    def _record(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        relation_id: UUID,
        related_relation_id: UUID | None,
        outcome: str,
        method: str,
        confidence: float,
        features: dict[str, object],
    ) -> None:
        """Append one decision to the transcript (never overwritten)."""
        connection.execute(
            _INSERT_ADJUDICATION,
            {
                "adjudication_id": uuid4(),
                "deployment_id": deployment_id,
                "relation_id": relation_id,
                "related_relation_id": related_relation_id,
                "outcome": outcome,
                "method": method,
                "confidence": confidence,
                "features": features,
                "adjudicator_version": ADJUDICATOR_VERSION,
            },
        )


_LOAD_RELATION = text(
    """
    SELECT r.relation_id, r.subject_entity_id, r.predicate, r.object_entity_id,
           r.invalidated_at, r.contradiction_group,
           coalesce(r.fact_label,
                    subject.canonical_name || ' ' || r.predicate || ' '
                    || object.canonical_name) AS label,
           p.is_change_prone,
           evidence.claim_text AS evidence_text,
           evidence.asserted_at
    FROM relations r
    JOIN predicates p ON p.deployment_id = r.deployment_id
                     AND p.predicate = r.predicate
    JOIN entities subject ON subject.entity_id = r.subject_entity_id
    JOIN entities object ON object.entity_id = r.object_entity_id
    LEFT JOIN LATERAL (
        SELECT c.claim_text, c.asserted_at
        FROM relation_evidence e
        JOIN claims c ON c.claim_id = e.claim_id
        WHERE e.relation_id = r.relation_id AND e.stance = 'supports'
        ORDER BY c.ingested_at DESC
        LIMIT 1
    ) evidence ON true
    WHERE r.deployment_id = :deployment_id AND r.relation_id = :relation_id
    """
)

_BLOCK_CANDIDATES = text(
    """
    SELECT r.relation_id, r.object_entity_id, r.contradiction_group,
           coalesce(r.fact_label,
                    subject.canonical_name || ' ' || r.predicate || ' '
                    || object.canonical_name) AS label,
           evidence.claim_text AS evidence_text,
           evidence.asserted_at
    FROM relations r
    JOIN entities subject ON subject.entity_id = r.subject_entity_id
    JOIN entities object ON object.entity_id = r.object_entity_id
    LEFT JOIN LATERAL (
        SELECT c.claim_text, c.asserted_at
        FROM relation_evidence e
        JOIN claims c ON c.claim_id = e.claim_id
        WHERE e.relation_id = r.relation_id AND e.stance = 'supports'
        ORDER BY c.ingested_at DESC
        LIMIT 1
    ) evidence ON true
    WHERE r.deployment_id = :deployment_id
      AND r.subject_entity_id = :subject_entity_id
      AND r.predicate = :predicate
      AND r.relation_id <> :relation_id
      AND r.invalidated_at IS NULL
      AND (r.valid_until IS NULL OR r.valid_until > now())
    ORDER BY r.ingested_at
    """
)

_CLOSE_WINDOW = text(
    """
    UPDATE relations
    SET valid_until = coalesce(:boundary_asserted, now()), updated_at = now()
    WHERE deployment_id = :deployment_id AND relation_id = :relation_id
      AND valid_until IS NULL
    """
)

_SET_CONTRADICTION_GROUP = text(
    """
    UPDATE relations SET contradiction_group = :group_id, updated_at = now()
    WHERE deployment_id = :deployment_id AND relation_id = ANY(:relation_ids)
    """
)

_COUNT_ADJUDICATIONS = text(
    """
    SELECT count(*) FROM relation_adjudications
    WHERE (relation_id = :relation_id OR related_relation_id = :relation_id)
      AND adjudicator_version = :adjudicator_version
      AND outcome IN ('add', 'noop', 'supersede', 'contradict')
    """
)

_INSERT_ADJUDICATION = text(
    """
    INSERT INTO relation_adjudications (
        adjudication_id, deployment_id, relation_id, related_relation_id,
        outcome, method, confidence, features, adjudicator_version
    ) VALUES (
        :adjudication_id, :deployment_id, :relation_id, :related_relation_id,
        :outcome, :method, :confidence, :features, :adjudicator_version
    )
    """
).bindparams(bindparam("features", type_=JSON))
