"""Plane-K Postgres control plane: manifests, routing, and staleness (D45).

The inverted key index deliberately narrows work; the typed candidate
manifest decides correctness. Some rule parameters (MIME/origin/time,
keywords, explicit evidence IDs) do not fit the schema's four key kinds, so
they receive exact secondary SQL evaluation instead of invented key types.
"""

from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import contextmanager
from uuid import UUID
from uuid import uuid4

from pydantic import JsonValue
from pydantic import TypeAdapter
from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine
from sqlalchemy.engine import RowMapping
from sqlalchemy.sql.elements import TextClause

from ultimate_memory.core import knowledge_inputs_hash
from ultimate_memory.core import knowledge_summary_hash
from ultimate_memory.model import CommunityRuleParams
from ultimate_memory.model import DocSetRuleParams
from ultimate_memory.model import EntityRuleParams
from ultimate_memory.model import EntitySubtreeRuleParams
from ultimate_memory.model import KnowledgeArtifactCreate
from ultimate_memory.model import KnowledgeArtifactHash
from ultimate_memory.model import KnowledgeCandidateLayer
from ultimate_memory.model import KnowledgeCitation
from ultimate_memory.model import KnowledgeClaimFingerprint
from ultimate_memory.model import KnowledgeCompilationFailure
from ultimate_memory.model import KnowledgeCompilationWrite
from ultimate_memory.model import KnowledgeCompileArtifact
from ultimate_memory.model import KnowledgeCompileContext
from ultimate_memory.model import KnowledgeEvidenceDelta
from ultimate_memory.model import KnowledgeFactFingerprint
from ultimate_memory.model import KnowledgeFactSheetFact
from ultimate_memory.model import KnowledgeFactSheetSnapshot
from ultimate_memory.model import KnowledgeInputSnapshot
from ultimate_memory.model import KnowledgePageRuleCreate
from ultimate_memory.model import KnowledgePendingCycle
from ultimate_memory.model import KnowledgePlanDecisionCreate
from ultimate_memory.model import KnowledgeRuleConfiguration
from ultimate_memory.model import KnowledgeRuleKey
from ultimate_memory.model import KnowledgeRuleKeyKind
from ultimate_memory.model import KnowledgeRuleKind
from ultimate_memory.model import KnowledgeRuleParams
from ultimate_memory.model import KnowledgeWriterBundle
from ultimate_memory.model import KnowledgeWriterClaim
from ultimate_memory.model import KnowledgeWriterClaimGroup
from ultimate_memory.model import KnowledgeWriterFactReference
from ultimate_memory.model import KnowledgeWriterSuggestion
from ultimate_memory.model import ManualRuleParams
from ultimate_memory.model import PredicateBeatRuleParams
from ultimate_memory.model import ScopeInterestsRuleParams

_RULE_ADAPTER = TypeAdapter(KnowledgeRuleParams)
_JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, JsonValue])


class KnowledgeCompileContextMissingError(LookupError):
    """A compiled artifact lacks its current git/model hash inputs."""


class KnowledgeCompilationError(ValueError):
    """A compilation transcript violates the control-plane contract."""


class KnowledgeCommitBusyError(RuntimeError):
    """Another process already owns this deployment's K commit cycle."""


class KnowledgeControlPlane:
    """Own the deterministic Plane-K state kept in Postgres."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the control plane to the authoritative spine."""
        self._engine = engine

    def record_plan_decision(self, *, decision: KnowledgePlanDecisionCreate) -> None:
        """Append one planner structure decision without applying it implicitly."""
        with self._engine.begin() as connection:
            connection.execute(
                _INSERT_PLAN_DECISION,
                {
                    **decision.model_dump(mode="python", exclude={"payload"}),
                    "payload": decision.model_dump(mode="json")["payload"],
                },
            )

    def create_artifact(self, *, artifact: KnowledgeArtifactCreate) -> None:
        """Register one git path in the K control plane."""
        with self._engine.begin() as connection:
            connection.execute(
                _INSERT_ARTIFACT,
                {
                    **artifact.model_dump(mode="python", exclude={"artifact_kind"}),
                    "kind": artifact.artifact_kind,
                },
            )

    def add_page_rule(self, *, rule: KnowledgePageRuleCreate) -> None:
        """Persist a typed page rule and materialize its coarse keys atomically."""
        params = _stored_params(params=rule.params)
        with self._engine.begin() as connection:
            connection.execute(
                _INSERT_PAGE_RULE,
                {
                    "rule_id": rule.rule_id,
                    "deployment_id": rule.deployment_id,
                    "artifact_id": rule.artifact_id,
                    "plan_decision_id": rule.plan_decision_id,
                    "rule_kind": rule.params.kind.value,
                    "params": params,
                },
            )
            self._replace_rule_keys(
                connection=connection,
                deployment_id=rule.deployment_id,
                rule_id=rule.rule_id,
                params=rule.params,
            )
            connection.execute(_MARK_STALE, {"artifact_id": rule.artifact_id})

    def rematerialize_rule_keys(self, *, rule_id: UUID) -> tuple[KnowledgeRuleKey, ...]:
        """Rebuild one rule's inverted keys from current authoritative state."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(_SELECT_RULE, {"rule_id": rule_id}).mappings().one()
            )
            params = _parse_rule(row=row)
            return self._replace_rule_keys(
                connection=connection,
                deployment_id=row["deployment_id"],
                rule_id=rule_id,
                params=params,
            )

    def rematerialize_derived_rule_keys(
        self,
        *,
        deployment_id: UUID,
        kinds: tuple[KnowledgeRuleKind, ...] = (
            KnowledgeRuleKind.ENTITY_SUBTREE,
            KnowledgeRuleKind.COMMUNITY,
            KnowledgeRuleKind.SCOPE_INTERESTS,
        ),
    ) -> None:
        """Refresh subtree, community, and scope expansions after their inputs move."""
        with self._engine.begin() as connection:
            rows = connection.execute(
                _SELECT_DERIVED_RULES, {"deployment_id": deployment_id}
            ).mappings()
            for row in rows:
                if KnowledgeRuleKind(str(row["rule_kind"])) not in kinds:
                    continue
                self._replace_rule_keys(
                    connection=connection,
                    deployment_id=deployment_id,
                    rule_id=row["rule_id"],
                    params=_parse_rule(row=row),
                )

    def input_snapshot(
        self, *, artifact_id: UUID, context: KnowledgeCompileContext
    ) -> KnowledgeInputSnapshot:
        """Evaluate one artifact's active-rule union into its exact D45 manifest."""
        with self._engine.connect() as connection:
            return self._input_snapshot(
                connection=connection, artifact_id=artifact_id, context=context
            )

    def fact_sheet_snapshot(
        self,
        *,
        artifact_id: UUID,
        context: KnowledgeCompileContext,
        child_summary_hashes: tuple[str, ...] | None = None,
    ) -> KnowledgeFactSheetSnapshot:
        """Hydrate an artifact's exact rule-selected facts in one repeatable read."""
        with self._engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with connection.begin():
                return self._fact_sheet_snapshot(
                    connection=connection,
                    artifact_id=artifact_id,
                    context=context,
                    child_summary_hashes=child_summary_hashes,
                )

    def writer_bundle(
        self,
        *,
        artifact_id: UUID,
        context: KnowledgeCompileContext,
        child_summary_hashes: tuple[str, ...] | None = None,
    ) -> KnowledgeWriterBundle:
        """Hydrate exact facts and current claim bodies in one repeatable read."""
        with self._engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with connection.begin():
                fact_sheet = self._fact_sheet_snapshot(
                    connection=connection,
                    artifact_id=artifact_id,
                    context=context,
                    child_summary_hashes=child_summary_hashes,
                )
                claim_groups = self._writer_claim_groups(
                    connection=connection, fact_sheet=fact_sheet
                )
                return KnowledgeWriterBundle(
                    fact_sheet=fact_sheet,
                    claim_groups=claim_groups,
                    claim_candidate_count=len(fact_sheet.input_snapshot.claims),
                    claims_cut_count=0,
                )

    def artifact_hash(
        self, *, artifact_id: UUID, context: KnowledgeCompileContext
    ) -> KnowledgeArtifactHash:
        """Return the recorded and current hash for one compiled artifact."""
        with self._engine.connect() as connection:
            row = (
                connection.execute(_SELECT_ARTIFACT_HASH, {"artifact_id": artifact_id})
                .mappings()
                .one()
            )
            snapshot = self._input_snapshot(
                connection=connection, artifact_id=artifact_id, context=context
            )
        return KnowledgeArtifactHash(
            artifact_id=artifact_id,
            recorded_hash=row["inputs_hash"],
            computed_hash=knowledge_inputs_hash(snapshot=snapshot),
        )

    def stale_artifacts(
        self,
        *,
        deployment_id: UUID,
        contexts: Mapping[UUID, KnowledgeCompileContext],
        artifact_ids: tuple[UUID, ...] | None = None,
    ) -> tuple[KnowledgeArtifactHash, ...]:
        """Return exactly the compiled pages whose complete manifest changed."""
        if artifact_ids == ():
            return ()
        statement = (
            _SELECT_FILTERED_COMPILED_ARTIFACTS
            if artifact_ids is not None
            else _SELECT_COMPILED_ARTIFACTS
        )
        with self._engine.connect() as connection:
            rows = connection.execute(
                statement,
                {
                    "deployment_id": deployment_id,
                    "artifact_ids": list(artifact_ids or ()),
                },
            ).mappings()
            stale: list[KnowledgeArtifactHash] = []
            for row in rows:
                artifact_id = row["artifact_id"]
                context = contexts.get(artifact_id)
                if context is None:
                    raise KnowledgeCompileContextMissingError(str(artifact_id))
                computed = knowledge_inputs_hash(
                    snapshot=self._input_snapshot(
                        connection=connection, artifact_id=artifact_id, context=context
                    )
                )
                if computed != row["inputs_hash"]:
                    stale.append(
                        KnowledgeArtifactHash(
                            artifact_id=artifact_id,
                            recorded_hash=row["inputs_hash"],
                            computed_hash=computed,
                        )
                    )
        return tuple(stale)

    def mark_stale(
        self, *, artifacts: Sequence[KnowledgeArtifactHash]
    ) -> tuple[UUID, ...]:
        """Mark manifest-mismatched compiled pages stale, idempotently."""
        if not artifacts:
            return ()
        marked: list[UUID] = []
        with self._engine.begin() as connection:
            for artifact in artifacts:
                artifact_id = connection.execute(
                    _MARK_STALE, {"artifact_id": artifact.artifact_id}
                ).scalar_one_or_none()
                if artifact_id is not None:
                    marked.append(artifact_id)
        return tuple(marked)

    def route_delta(
        self, *, deployment_id: UUID, delta: KnowledgeEvidenceDelta
    ) -> tuple[UUID, ...]:
        """Narrow an evidence delta to candidate artifacts using keys and citations.

        Scope-interest rules are included as a deliberate coarse fallback because
        the schema has no entity-type/metadata/keyword key kinds. Manual rules are
        checked by their explicit IDs. The caller must recompute manifests before
        marking anything stale; a coarse route is never a correctness verdict.
        """
        derived_kinds: list[KnowledgeRuleKind] = []
        if delta.community_ids:
            derived_kinds.append(KnowledgeRuleKind.COMMUNITY)
        if delta.relation_ids and self._delta_contains_part_of(
            deployment_id=deployment_id, relation_ids=delta.relation_ids
        ):
            derived_kinds.append(KnowledgeRuleKind.ENTITY_SUBTREE)
        if derived_kinds:
            self.rematerialize_derived_rule_keys(
                deployment_id=deployment_id, kinds=tuple(derived_kinds)
            )
        with self._engine.connect() as connection:
            keys = self._delta_keys(
                connection=connection, deployment_id=deployment_id, delta=delta
            )
            artifact_ids: set[UUID] = set()
            for key in keys:
                artifact_ids.update(
                    connection.execute(
                        _SELECT_ARTIFACTS_FOR_KEY,
                        {
                            "deployment_id": deployment_id,
                            "key_kind": key.kind.value,
                            "key_value": key.value,
                        },
                    ).scalars()
                )
            artifact_ids.update(
                self._citation_artifacts(
                    connection=connection, deployment_id=deployment_id, delta=delta
                )
            )
            artifact_ids.update(
                connection.execute(
                    _SELECT_SCOPE_RULE_ARTIFACTS, {"deployment_id": deployment_id}
                ).scalars()
            )
            artifact_ids.update(
                self._manual_artifacts(
                    connection=connection, deployment_id=deployment_id, delta=delta
                )
            )
        return tuple(sorted(artifact_ids, key=str))

    def _delta_contains_part_of(
        self, *, deployment_id: UUID, relation_ids: tuple[UUID, ...]
    ) -> bool:
        """Return whether a changed relation can alter subtree membership."""
        with self._engine.connect() as connection:
            return bool(
                connection.execute(
                    _SELECT_PART_OF_DELTA,
                    {
                        "deployment_id": deployment_id,
                        "relation_ids": list(relation_ids),
                    },
                ).scalar_one()
            )

    @contextmanager
    def commit_lease(self, *, deployment_id: UUID) -> Iterator[None]:
        """Hold the deployment-scoped Postgres advisory lock for one K cycle."""
        with self._engine.connect() as connection:
            acquired = bool(
                connection.execute(
                    _TRY_COMMIT_LEASE, {"deployment_id": deployment_id}
                ).scalar_one()
            )
            connection.commit()
            if not acquired:
                raise KnowledgeCommitBusyError(str(deployment_id))
            try:
                yield
            finally:
                released = bool(
                    connection.execute(
                        _RELEASE_COMMIT_LEASE, {"deployment_id": deployment_id}
                    ).scalar_one()
                )
                connection.commit()
                if not released:
                    raise KnowledgeCompilationError("Plane-K commit lease was lost")

    def compile_artifacts(
        self, *, deployment_id: UUID
    ) -> tuple[KnowledgeCompileArtifact, ...]:
        """Return the deployment's schedulable compiled-page graph."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                _SELECT_COMPILE_ARTIFACTS, {"deployment_id": deployment_id}
            ).mappings()
            return tuple(
                KnowledgeCompileArtifact.model_validate(dict(row)) for row in rows
            )

    def artifact_git_paths(self, *, deployment_id: UUID) -> tuple[str, ...]:
        """Return every live artifact path accepted by internal-link validation."""
        with self._engine.connect() as connection:
            return tuple(
                connection.execute(
                    _SELECT_ARTIFACT_GIT_PATHS, {"deployment_id": deployment_id}
                ).scalars()
            )

    def validate_citations(
        self, *, deployment_id: UUID, citations: tuple[KnowledgeCitation, ...]
    ) -> None:
        """Reject unknown or cross-deployment writer citation targets before publish."""
        with self._engine.connect() as connection:
            self._validate_citations(
                connection=connection,
                deployment_id=deployment_id,
                citations=_unique_citations(citations=citations),
            )

    def record_failed_compilation(
        self, *, failure: KnowledgeCompilationFailure
    ) -> None:
        """Append one terminal writer failure without changing live page state."""
        with self._engine.begin() as connection:
            inserted = connection.execute(
                _INSERT_FAILED_COMPILATION, failure.model_dump(mode="python")
            ).scalar_one_or_none()
            if inserted is None:
                raise KnowledgeCompilationError(
                    "failed compilation target is not an active/stale compiled artifact"
                )

    def pending_cycles(
        self, *, deployment_id: UUID
    ) -> tuple[KnowledgePendingCycle, ...]:
        """Rehydrate every unfailed, uncommitted cycle from durable finalize payloads."""
        grouped: dict[UUID, list[KnowledgeCompilationWrite]] = {}
        with self._engine.connect() as connection:
            rows = connection.execute(
                _SELECT_PENDING_COMPILATIONS, {"deployment_id": deployment_id}
            ).mappings()
            for row in rows:
                cycle_id = row["cycle_id"]
                grouped.setdefault(cycle_id, []).append(
                    KnowledgeCompilationWrite.model_validate(
                        {
                            key: row[key]
                            for key in (
                                "compilation_id",
                                "deployment_id",
                                "artifact_id",
                                "inputs_hash",
                                "candidate_count",
                                "uncited_count",
                                "claims_cut_count",
                                "citations",
                                "suggestions",
                                "evidence_invalidated",
                                "writer_version",
                                "page_summary",
                                "content_hash",
                                "tokens",
                                "cost_usd",
                                "session_transcript_uri",
                            )
                        }
                    )
                )
        return tuple(
            KnowledgePendingCycle(
                cycle_id=cycle_id,
                deployment_id=deployment_id,
                compilations=tuple(compilations),
            )
            for cycle_id, compilations in grouped.items()
        )

    def fail_pending_cycle(
        self, *, deployment_id: UUID, cycle_id: UUID, failure: str
    ) -> None:
        """Record an unpublished or unverifiable cycle without changing live pages."""
        if not failure:
            raise KnowledgeCompilationError("pending-cycle failure must be non-empty")
        with self._engine.begin() as connection:
            connection.execute(
                _FAIL_PENDING_CYCLE,
                {
                    "deployment_id": deployment_id,
                    "cycle_id": cycle_id,
                    "failure": failure,
                },
            )

    def record_pending_compilation(
        self, *, compilation: KnowledgeCompilationWrite
    ) -> None:
        """Record a validated compilation before git push without changing live state.

        ``git_commit IS NULL`` is the schema's pending marker. The currently
        committed page, citations, and artifact hash remain untouched so a
        failed push leaves the previous page internally consistent (D45 §6).
        """
        self.record_pending_compilations(
            cycle_id=compilation.compilation_id, compilations=(compilation,)
        )

    def record_pending_compilations(
        self, *, cycle_id: UUID, compilations: Sequence[KnowledgeCompilationWrite]
    ) -> None:
        """Record a complete publish batch atomically without changing live state."""
        if not compilations:
            raise KnowledgeCompilationError("pending cycle requires at least one page")
        deployment_ids = {item.deployment_id for item in compilations}
        artifact_ids = {item.artifact_id for item in compilations}
        compilation_ids = {item.compilation_id for item in compilations}
        if len(deployment_ids) != 1:
            raise KnowledgeCompilationError("pending cycle crosses deployments")
        if len(artifact_ids) != len(compilations):
            raise KnowledgeCompilationError("pending cycle repeats an artifact")
        if len(compilation_ids) != len(compilations):
            raise KnowledgeCompilationError("pending cycle repeats a compilation ID")
        with self._engine.begin() as connection:
            for compilation in compilations:
                citations = _unique_citations(citations=compilation.citations)
                self._validate_citations(
                    connection=connection,
                    deployment_id=compilation.deployment_id,
                    citations=citations,
                )
                prior = set(
                    connection.execute(
                        _SELECT_CITATIONS, {"artifact_id": compilation.artifact_id}
                    ).tuples()
                )
                current = {_citation_tuple(citation=item) for item in citations}
                connection.execute(
                    _INSERT_COMPILATION,
                    {
                        **compilation.model_dump(
                            mode="python",
                            exclude={
                                "citations",
                                "suggestions",
                                "page_summary",
                                "content_hash",
                            },
                        ),
                        "cycle_id": cycle_id,
                        "citations": [
                            item.model_dump(mode="json") for item in citations
                        ],
                        "suggestions": [
                            item.model_dump(mode="json")
                            for item in compilation.suggestions
                        ],
                        "page_summary": compilation.page_summary,
                        "content_hash": compilation.content_hash,
                        "cited_count": (
                            compilation.candidate_count - compilation.uncited_count
                        ),
                        "evidence_added": len(current - prior),
                        "evidence_removed": len(prior - current),
                    },
                )

    def commit_compilation(
        self, *, compilation: KnowledgeCompilationWrite, git_commit: str
    ) -> None:
        """Publish pending citations/artifact state after the git push succeeds."""
        self.commit_compilations(compilations=(compilation,), git_commit=git_commit)

    def commit_compilations(
        self, *, compilations: Sequence[KnowledgeCompilationWrite], git_commit: str
    ) -> None:
        """Finalize every page in one published cycle atomically and idempotently."""
        if not git_commit:
            raise KnowledgeCompilationError("git commit must be non-empty")
        if not compilations:
            raise KnowledgeCompilationError("commit cycle requires at least one page")
        if len({item.compilation_id for item in compilations}) != len(compilations):
            raise KnowledgeCompilationError("commit cycle repeats a compilation ID")
        if len({item.artifact_id for item in compilations}) != len(compilations):
            raise KnowledgeCompilationError("commit cycle repeats an artifact")
        if len({item.deployment_id for item in compilations}) != 1:
            raise KnowledgeCompilationError("commit cycle crosses deployments")
        with self._engine.begin() as connection:
            to_finalize: list[
                tuple[KnowledgeCompilationWrite, tuple[KnowledgeCitation, ...]]
            ] = []
            cycle_ids: set[UUID] = set()
            for compilation in compilations:
                citations = _unique_citations(citations=compilation.citations)
                pending = (
                    connection.execute(
                        _SELECT_COMPILATION_STATE,
                        {"compilation_id": compilation.compilation_id},
                    )
                    .mappings()
                    .one_or_none()
                )
                if pending is None:
                    raise KnowledgeCompilationError(
                        "pending compilation does not exist"
                    )
                cycle_ids.add(pending["cycle_id"])
                if pending["git_commit"] is not None:
                    if pending["git_commit"] == git_commit:
                        continue
                    raise KnowledgeCompilationError(
                        "compilation is already bound to a different git commit"
                    )
                if pending["failed_at"] is not None:
                    raise KnowledgeCompilationError("pending compilation was abandoned")
                stored_citations = _unique_citations(
                    citations=tuple(
                        KnowledgeCitation.model_validate(item)
                        for item in pending["citations"]
                    )
                )
                stored_suggestions = tuple(
                    KnowledgeWriterSuggestion.model_validate(item)
                    for item in pending["suggestions"]
                )
                if (
                    pending["deployment_id"] != compilation.deployment_id
                    or pending["artifact_id"] != compilation.artifact_id
                    or pending["inputs_hash"] != compilation.inputs_hash
                    or pending["writer_version"] != compilation.writer_version
                    or pending["candidate_count"] != compilation.candidate_count
                    or pending["cited_count"]
                    != compilation.candidate_count - compilation.uncited_count
                    or pending["uncited_count"] != compilation.uncited_count
                    or pending["claims_cut_count"] != compilation.claims_cut_count
                    or pending["evidence_invalidated"]
                    != compilation.evidence_invalidated
                    or pending["page_summary"] != compilation.page_summary
                    or pending["content_hash"] != compilation.content_hash
                    or stored_suggestions != compilation.suggestions
                    or tuple(
                        _citation_tuple(citation=item) for item in stored_citations
                    )
                    != tuple(_citation_tuple(citation=item) for item in citations)
                ):
                    raise KnowledgeCompilationError(
                        "pending compilation does not match the finalize payload"
                    )
                self._validate_citations(
                    connection=connection,
                    deployment_id=compilation.deployment_id,
                    citations=citations,
                )
                to_finalize.append((compilation, citations))

            if len(cycle_ids) != 1:
                raise KnowledgeCompilationError("commit payload crosses pending cycles")
            cycle_id = next(iter(cycle_ids))
            if cycle_id is not None:
                stored_compilation_ids = set(
                    connection.execute(
                        _SELECT_CYCLE_COMPILATION_IDS,
                        {
                            "deployment_id": compilations[0].deployment_id,
                            "cycle_id": cycle_id,
                        },
                    ).scalars()
                )
                requested_compilation_ids = {
                    compilation.compilation_id for compilation in compilations
                }
                if stored_compilation_ids != requested_compilation_ids:
                    raise KnowledgeCompilationError(
                        "commit payload does not contain the complete pending cycle"
                    )

            for compilation, citations in to_finalize:
                connection.execute(
                    _DELETE_CITATIONS, {"artifact_id": compilation.artifact_id}
                )
                for citation in citations:
                    connection.execute(
                        _INSERT_CITATION,
                        {
                            "evidence_link_id": uuid4(),
                            "deployment_id": compilation.deployment_id,
                            "artifact_id": compilation.artifact_id,
                            **citation.model_dump(mode="python"),
                        },
                    )
                updated = connection.execute(
                    _UPDATE_COMPILED_ARTIFACT,
                    {
                        "artifact_id": compilation.artifact_id,
                        "inputs_hash": compilation.inputs_hash,
                        "writer_version": compilation.writer_version,
                        "page_summary": compilation.page_summary,
                        "content_hash": compilation.content_hash,
                    },
                ).scalar_one_or_none()
                if updated is None:
                    raise KnowledgeCompilationError(
                        "compilation target is not an active/stale compiled artifact"
                    )
                connection.execute(
                    _STAMP_COMPILATION_COMMIT,
                    {
                        "compilation_id": compilation.compilation_id,
                        "git_commit": git_commit,
                    },
                )

    def _input_snapshot(
        self,
        *,
        connection: Connection,
        artifact_id: UUID,
        context: KnowledgeCompileContext,
        child_summary_hashes: tuple[str, ...] | None = None,
    ) -> KnowledgeInputSnapshot:
        """Assemble a manifest on an existing connection."""
        rule_rows = tuple(
            connection.execute(
                _SELECT_ARTIFACT_RULES, {"artifact_id": artifact_id}
            ).mappings()
        )
        facts: dict[tuple[str, UUID], KnowledgeFactFingerprint] = {}
        claims: dict[tuple[UUID, str], KnowledgeClaimFingerprint] = {}
        rules: list[KnowledgeRuleConfiguration] = []
        for row in rule_rows:
            params = _parse_rule(row=row)
            stored = _stored_params(params=params)
            rules.append(
                KnowledgeRuleConfiguration(
                    rule_id=row["rule_id"], kind=params.kind, params=stored
                )
            )
            rule_facts, rule_claims = self._candidates_for_rule(
                connection=connection, deployment_id=row["deployment_id"], params=params
            )
            for fact in rule_facts:
                facts[(fact.kind, fact.fact_id)] = fact
            for claim in rule_claims:
                claims[(claim.lineage_id, claim.chunk_content_hash)] = claim
        child_hashes = (
            tuple(
                knowledge_summary_hash(summary=summary)
                for summary in connection.execute(
                    _SELECT_CHILD_SUMMARIES, {"artifact_id": artifact_id}
                ).scalars()
            )
            if child_summary_hashes is None
            else tuple(sorted(child_summary_hashes))
        )
        return KnowledgeInputSnapshot(
            facts=tuple(facts.values()),
            claims=tuple(claims.values()),
            rules=tuple(rules),
            curation_hash=context.curation_hash,
            child_summary_hashes=child_hashes,
            shared_model_summary_hash=context.shared_model_summary_hash,
            writer_version=context.writer_version,
        )

    def _fact_sheet_snapshot(
        self,
        *,
        connection: Connection,
        artifact_id: UUID,
        context: KnowledgeCompileContext,
        child_summary_hashes: tuple[str, ...] | None,
    ) -> KnowledgeFactSheetSnapshot:
        """Build the exact display-fact snapshot on an existing transaction."""
        artifact = (
            connection.execute(
                _SELECT_FACT_SHEET_ARTIFACT, {"artifact_id": artifact_id}
            )
            .mappings()
            .one_or_none()
        )
        if artifact is None:
            raise KnowledgeCompilationError(
                "fact-sheet target is not an active/stale compiled artifact"
            )
        evidence_as_of = connection.execute(_SELECT_TRANSACTION_TIMESTAMP).scalar_one()
        input_snapshot = self._input_snapshot(
            connection=connection,
            artifact_id=artifact_id,
            context=context,
            child_summary_hashes=child_summary_hashes,
        )
        relation_ids = tuple(
            fact.fact_id for fact in input_snapshot.facts if fact.kind == "relation"
        )
        observation_ids = tuple(
            fact.fact_id for fact in input_snapshot.facts if fact.kind == "observation"
        )
        facts = (
            *self._fact_sheet_relations(
                connection=connection,
                deployment_id=artifact["deployment_id"],
                relation_ids=relation_ids,
            ),
            *self._fact_sheet_observations(
                connection=connection,
                deployment_id=artifact["deployment_id"],
                observation_ids=observation_ids,
            ),
        )
        expected = {(fact.kind, fact.fact_id) for fact in input_snapshot.facts}
        hydrated = {(fact.kind, fact.fact_id) for fact in facts}
        if hydrated != expected:
            raise KnowledgeCompilationError(
                "fact-sheet hydration does not match the rule candidate set"
            )
        return KnowledgeFactSheetSnapshot(
            artifact_id=artifact_id,
            deployment_id=artifact["deployment_id"],
            evidence_as_of=evidence_as_of,
            input_snapshot=input_snapshot,
            facts=facts,
        )

    def _writer_claim_groups(
        self, *, connection: Connection, fact_sheet: KnowledgeFactSheetSnapshot
    ) -> tuple[KnowledgeWriterClaimGroup, ...]:
        """Hydrate every current claim row at each selected D54 coordinate."""
        candidates = fact_sheet.input_snapshot.claims
        if not candidates:
            return ()
        rows = tuple(
            connection.execute(
                _SELECT_WRITER_CLAIMS,
                {
                    "deployment_id": fact_sheet.deployment_id,
                    "candidates": [item.model_dump(mode="json") for item in candidates],
                },
            ).mappings()
        )
        claim_ids = tuple(row["claim_id"] for row in rows)
        references = self._writer_fact_references(
            connection=connection,
            deployment_id=fact_sheet.deployment_id,
            facts=fact_sheet.facts,
            claim_ids=claim_ids,
        )
        grouped: dict[tuple[UUID, str], list[KnowledgeWriterClaim]] = {}
        for row in rows:
            claim_id = row["claim_id"]
            claim = KnowledgeWriterClaim.model_validate(
                {**dict(row), "fact_references": references.get(claim_id, ())}
            )
            grouped.setdefault((claim.lineage_id, claim.chunk_content_hash), []).append(
                claim
            )
        expected = {(item.lineage_id, item.chunk_content_hash) for item in candidates}
        if set(grouped) != expected:
            raise KnowledgeCompilationError(
                "writer claim hydration does not match the D54 candidate set"
            )
        return tuple(
            KnowledgeWriterClaimGroup(
                lineage_id=lineage_id,
                chunk_content_hash=chunk_hash,
                claims=tuple(sorted(claims, key=lambda claim: str(claim.claim_id))),
            )
            for (lineage_id, chunk_hash), claims in sorted(
                grouped.items(), key=lambda item: (str(item[0][0]), item[0][1])
            )
        )

    def _writer_fact_references(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        facts: tuple[KnowledgeFactSheetFact, ...],
        claim_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[KnowledgeWriterFactReference, ...]]:
        """Attach selected facts to the candidate claims that evidence them."""
        if not claim_ids:
            return {}
        rows: list[RowMapping] = []
        relation_ids = tuple(fact.fact_id for fact in facts if fact.kind == "relation")
        observation_ids = tuple(
            fact.fact_id for fact in facts if fact.kind == "observation"
        )
        if relation_ids:
            rows.extend(
                connection.execute(
                    _SELECT_WRITER_RELATION_REFERENCES,
                    {
                        "deployment_id": deployment_id,
                        "fact_ids": list(relation_ids),
                        "claim_ids": list(claim_ids),
                    },
                ).mappings()
            )
        if observation_ids:
            rows.extend(
                connection.execute(
                    _SELECT_WRITER_OBSERVATION_REFERENCES,
                    {
                        "deployment_id": deployment_id,
                        "fact_ids": list(observation_ids),
                        "claim_ids": list(claim_ids),
                    },
                ).mappings()
            )
        grouped: dict[UUID, list[KnowledgeWriterFactReference]] = {}
        for row in rows:
            grouped.setdefault(row["claim_id"], []).append(
                KnowledgeWriterFactReference.model_validate(
                    {key: row[key] for key in ("kind", "fact_id", "stance")}
                )
            )
        return {
            claim_id: tuple(
                sorted(
                    items, key=lambda item: (item.kind, str(item.fact_id), item.stance)
                )
            )
            for claim_id, items in grouped.items()
        }

    def _fact_sheet_relations(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        relation_ids: tuple[UUID, ...],
    ) -> tuple[KnowledgeFactSheetFact, ...]:
        """Hydrate exact relation candidates with stable display labels."""
        if not relation_ids:
            return ()
        rows = connection.execute(
            _SELECT_FACT_SHEET_RELATIONS,
            {"deployment_id": deployment_id, "relation_ids": list(relation_ids)},
        ).mappings()
        return tuple(KnowledgeFactSheetFact.model_validate(dict(row)) for row in rows)

    def _fact_sheet_observations(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        observation_ids: tuple[UUID, ...],
    ) -> tuple[KnowledgeFactSheetFact, ...]:
        """Hydrate exact observation candidates with stable display labels."""
        if not observation_ids:
            return ()
        rows = connection.execute(
            _SELECT_FACT_SHEET_OBSERVATIONS,
            {"deployment_id": deployment_id, "observation_ids": list(observation_ids)},
        ).mappings()
        return tuple(KnowledgeFactSheetFact.model_validate(dict(row)) for row in rows)

    def _replace_rule_keys(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        rule_id: UUID,
        params: KnowledgeRuleParams,
    ) -> tuple[KnowledgeRuleKey, ...]:
        """Compute and transactionally replace one rule's materialized keys."""
        keys = self._rule_keys(
            connection=connection, deployment_id=deployment_id, params=params
        )
        connection.execute(_DELETE_RULE_KEYS, {"rule_id": rule_id})
        for key in keys:
            connection.execute(
                _INSERT_RULE_KEY,
                {
                    "deployment_id": deployment_id,
                    "rule_id": rule_id,
                    "key_kind": key.kind.value,
                    "key_value": key.value,
                },
            )
        return keys

    def _rule_keys(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        params: KnowledgeRuleParams,
    ) -> tuple[KnowledgeRuleKey, ...]:
        """Expand one rule into every coarse key the schema can represent."""
        keys: set[tuple[KnowledgeRuleKeyKind, str]] = set()
        if isinstance(params, EntityRuleParams):
            keys.add((KnowledgeRuleKeyKind.ENTITY, str(params.entity_id)))
            keys.update(
                (KnowledgeRuleKeyKind.PREDICATE, predicate)
                for predicate in params.predicates
            )
        elif isinstance(params, EntitySubtreeRuleParams):
            members = connection.execute(
                _SELECT_SUBTREE_MEMBERS,
                {
                    "deployment_id": deployment_id,
                    "root_entity_id": params.root_entity_id,
                },
            ).scalars()
            keys.update(
                (KnowledgeRuleKeyKind.ENTITY, str(member)) for member in members
            )
            keys.update(
                (KnowledgeRuleKeyKind.PREDICATE, predicate)
                for predicate in params.predicates
            )
        elif isinstance(params, PredicateBeatRuleParams):
            keys.add((KnowledgeRuleKeyKind.PREDICATE, params.predicate))
            for entity_id in (params.subject_entity_id, params.object_entity_id):
                if entity_id is not None:
                    keys.add((KnowledgeRuleKeyKind.ENTITY, str(entity_id)))
        elif isinstance(params, CommunityRuleParams):
            keys.add((KnowledgeRuleKeyKind.COMMUNITY, str(params.community_id)))
            members = connection.execute(
                _SELECT_COMMUNITY_MEMBERS,
                {"deployment_id": deployment_id, "community_id": params.community_id},
            ).scalars()
            keys.update(
                (KnowledgeRuleKeyKind.ENTITY, str(member)) for member in members
            )
        elif isinstance(params, DocSetRuleParams):
            keys.add((KnowledgeRuleKeyKind.DOC_SOURCE, params.source_kind))
        elif isinstance(params, ScopeInterestsRuleParams):
            keys.update(
                self._scope_interest_keys(
                    connection=connection,
                    deployment_id=deployment_id,
                    scope_id=params.scope_id,
                )
            )
        elif isinstance(params, ManualRuleParams):
            keys.update(
                (KnowledgeRuleKeyKind.ENTITY, str(entity_id))
                for entity_id in params.entity_ids
            )
        return tuple(
            KnowledgeRuleKey(kind=kind, value=value)
            for kind, value in sorted(keys, key=lambda item: (item[0].value, item[1]))
        )

    def _scope_interest_keys(
        self, *, connection: Connection, deployment_id: UUID, scope_id: UUID
    ) -> set[tuple[KnowledgeRuleKeyKind, str]]:
        """Materialize the subset of registry interests representable as keys."""
        keys: set[tuple[KnowledgeRuleKeyKind, str]] = set()
        interests = connection.execute(
            _SELECT_SCOPE_INTERESTS, {"scope_id": scope_id}
        ).mappings()
        for interest in interests:
            interest_type = str(interest["interest_type"])
            value = str(interest["value"])
            if interest_type == "predicate":
                keys.add((KnowledgeRuleKeyKind.PREDICATE, value))
            elif interest_type == "entity_type":
                entities = connection.execute(
                    _SELECT_ENTITIES_OF_TYPE,
                    {"deployment_id": deployment_id, "entity_type": value},
                ).scalars()
                keys.update(
                    (KnowledgeRuleKeyKind.ENTITY, str(entity_id))
                    for entity_id in entities
                )
            elif interest_type == "metadata":
                sources = connection.execute(
                    _SELECT_DOC_SOURCES_FOR_METADATA,
                    {"deployment_id": deployment_id, "value": value},
                ).scalars()
                keys.update(
                    (KnowledgeRuleKeyKind.DOC_SOURCE, str(source)) for source in sources
                )
            # Keyword interests have no corresponding rule_key_kind. They are
            # still evaluated exactly in the candidate manifest.
        return keys

    def _candidates_for_rule(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        params: KnowledgeRuleParams,
    ) -> tuple[
        tuple[KnowledgeFactFingerprint, ...], tuple[KnowledgeClaimFingerprint, ...]
    ]:
        """Evaluate one typed rule into fact and stable claim coordinates."""
        if isinstance(params, EntityRuleParams):
            return self._entity_candidates(
                connection=connection,
                deployment_id=deployment_id,
                entity_ids=(params.entity_id,),
                layers=params.layers,
                predicates=params.predicates,
            )
        if isinstance(params, EntitySubtreeRuleParams):
            entity_ids = tuple(
                connection.execute(
                    _SELECT_SUBTREE_MEMBERS,
                    {
                        "deployment_id": deployment_id,
                        "root_entity_id": params.root_entity_id,
                    },
                ).scalars()
            )
            return self._entity_candidates(
                connection=connection,
                deployment_id=deployment_id,
                entity_ids=entity_ids,
                layers=params.layers,
                predicates=params.predicates,
            )
        if isinstance(params, PredicateBeatRuleParams):
            rows = connection.execute(
                _SELECT_PREDICATE_RELATIONS,
                {
                    "deployment_id": deployment_id,
                    "predicate": params.predicate,
                    "subject_entity_id": params.subject_entity_id,
                    "object_entity_id": params.object_entity_id,
                },
            ).mappings()
            return (_fact_fingerprints(rows=rows), ())
        if isinstance(params, CommunityRuleParams):
            entity_ids = tuple(
                connection.execute(
                    _SELECT_COMMUNITY_MEMBERS,
                    {
                        "deployment_id": deployment_id,
                        "community_id": params.community_id,
                    },
                ).scalars()
            )
            return self._entity_candidates(
                connection=connection,
                deployment_id=deployment_id,
                entity_ids=entity_ids,
                layers=params.layers,
            )
        if isinstance(params, DocSetRuleParams):
            doc_ids = tuple(
                connection.execute(
                    _SELECT_DOC_SET,
                    {
                        "deployment_id": deployment_id,
                        "source_kind": params.source_kind,
                        "mime": params.mime,
                        "origin": params.origin,
                        "source_modified_from": params.source_modified_from,
                        "source_modified_until": params.source_modified_until,
                    },
                ).scalars()
            )
            return self._document_candidates(
                connection=connection, deployment_id=deployment_id, doc_ids=doc_ids
            )
        if isinstance(params, ScopeInterestsRuleParams):
            return self._scope_candidates(
                connection=connection,
                deployment_id=deployment_id,
                scope_id=params.scope_id,
            )
        return self._manual_candidates(
            connection=connection, deployment_id=deployment_id, params=params
        )

    def _entity_candidates(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        entity_ids: tuple[UUID, ...],
        layers: tuple[KnowledgeCandidateLayer, ...],
        predicates: tuple[str, ...] = (),
    ) -> tuple[
        tuple[KnowledgeFactFingerprint, ...], tuple[KnowledgeClaimFingerprint, ...]
    ]:
        """Read selected candidate layers for a set of canonical entities."""
        if not entity_ids:
            return (), ()
        facts: list[KnowledgeFactFingerprint] = []
        claims: tuple[KnowledgeClaimFingerprint, ...] = ()
        values = {"deployment_id": deployment_id, "entity_ids": list(entity_ids)}
        if KnowledgeCandidateLayer.RELATIONS in layers:
            relation_statement = (
                _SELECT_FILTERED_ENTITY_RELATIONS
                if predicates
                else _SELECT_ENTITY_RELATIONS
            )
            facts.extend(
                _fact_fingerprints(
                    rows=connection.execute(
                        relation_statement, {**values, "predicates": list(predicates)}
                    ).mappings()
                )
            )
        if KnowledgeCandidateLayer.OBSERVATIONS in layers:
            facts.extend(
                _fact_fingerprints(
                    rows=connection.execute(
                        _SELECT_ENTITY_OBSERVATIONS,
                        {
                            "deployment_id": deployment_id,
                            "entity_ids": list(entity_ids),
                        },
                    ).mappings()
                )
            )
        if KnowledgeCandidateLayer.CLAIMS in layers:
            claims = _claim_fingerprints(
                rows=connection.execute(
                    _SELECT_ENTITY_CLAIMS,
                    {"deployment_id": deployment_id, "entity_ids": list(entity_ids)},
                ).mappings()
            )
        return tuple(facts), claims

    def _document_candidates(
        self, *, connection: Connection, deployment_id: UUID, doc_ids: tuple[UUID, ...]
    ) -> tuple[
        tuple[KnowledgeFactFingerprint, ...], tuple[KnowledgeClaimFingerprint, ...]
    ]:
        """Read facts supported by and claims belonging to a document set."""
        if not doc_ids:
            return (), ()
        values = {"deployment_id": deployment_id, "doc_ids": list(doc_ids)}
        facts = _fact_fingerprints(
            rows=connection.execute(_SELECT_DOCUMENT_FACTS, values).mappings()
        )
        claims = _claim_fingerprints(
            rows=connection.execute(_SELECT_DOCUMENT_CLAIMS, values).mappings()
        )
        return facts, claims

    def _scope_candidates(
        self, *, connection: Connection, deployment_id: UUID, scope_id: UUID
    ) -> tuple[
        tuple[KnowledgeFactFingerprint, ...], tuple[KnowledgeClaimFingerprint, ...]
    ]:
        """Evaluate every registry interest and union its deterministic matches."""
        facts: dict[tuple[str, UUID], KnowledgeFactFingerprint] = {}
        claims: dict[tuple[UUID, str], KnowledgeClaimFingerprint] = {}
        interests = tuple(
            connection.execute(
                _SELECT_SCOPE_INTERESTS, {"scope_id": scope_id}
            ).mappings()
        )
        for interest in interests:
            interest_type = str(interest["interest_type"])
            value = str(interest["value"])
            if interest_type == "entity_type":
                entity_ids = tuple(
                    connection.execute(
                        _SELECT_ENTITIES_OF_TYPE,
                        {"deployment_id": deployment_id, "entity_type": value},
                    ).scalars()
                )
                selected_facts, selected_claims = self._entity_candidates(
                    connection=connection,
                    deployment_id=deployment_id,
                    entity_ids=entity_ids,
                    layers=tuple(KnowledgeCandidateLayer),
                )
            elif interest_type == "predicate":
                selected_facts = _fact_fingerprints(
                    rows=connection.execute(
                        _SELECT_PREDICATE_RELATIONS,
                        {
                            "deployment_id": deployment_id,
                            "predicate": value,
                            "subject_entity_id": None,
                            "object_entity_id": None,
                        },
                    ).mappings()
                )
                selected_claims = _claim_fingerprints(
                    rows=connection.execute(
                        _SELECT_PREDICATE_CLAIMS,
                        {"deployment_id": deployment_id, "predicate": value},
                    ).mappings()
                )
            elif interest_type == "metadata":
                doc_ids = tuple(
                    connection.execute(
                        _SELECT_DOCS_FOR_METADATA,
                        {"deployment_id": deployment_id, "value": value},
                    ).scalars()
                )
                selected_facts, selected_claims = self._document_candidates(
                    connection=connection, deployment_id=deployment_id, doc_ids=doc_ids
                )
            else:
                claim_ids = tuple(
                    connection.execute(
                        _SELECT_KEYWORD_CLAIMS,
                        {"deployment_id": deployment_id, "keyword": value},
                    ).scalars()
                )
                selected_facts = self._facts_for_claim_ids(
                    connection=connection,
                    deployment_id=deployment_id,
                    claim_ids=claim_ids,
                )
                selected_claims = self._claims_for_ids(
                    connection=connection,
                    deployment_id=deployment_id,
                    claim_ids=claim_ids,
                )
            for fact in selected_facts:
                facts[(fact.kind, fact.fact_id)] = fact
            for claim in selected_claims:
                claims[(claim.lineage_id, claim.chunk_content_hash)] = claim
        return tuple(facts.values()), tuple(claims.values())

    def _manual_candidates(
        self, *, connection: Connection, deployment_id: UUID, params: ManualRuleParams
    ) -> tuple[
        tuple[KnowledgeFactFingerprint, ...], tuple[KnowledgeClaimFingerprint, ...]
    ]:
        """Union an explicit manual assignment without requiring indexable keys."""
        facts: dict[tuple[str, UUID], KnowledgeFactFingerprint] = {}
        claims: dict[tuple[UUID, str], KnowledgeClaimFingerprint] = {}
        entity_facts, entity_claims = self._entity_candidates(
            connection=connection,
            deployment_id=deployment_id,
            entity_ids=params.entity_ids,
            layers=tuple(KnowledgeCandidateLayer),
        )
        direct_facts: tuple[KnowledgeFactFingerprint, ...] = ()
        if params.relation_ids:
            direct_facts = _fact_fingerprints(
                rows=connection.execute(
                    _SELECT_RELATIONS_BY_IDS,
                    {
                        "deployment_id": deployment_id,
                        "relation_ids": list(params.relation_ids),
                    },
                ).mappings()
            )
        if params.observation_ids:
            direct_facts = (
                *direct_facts,
                *_fact_fingerprints(
                    rows=connection.execute(
                        _SELECT_OBSERVATIONS_BY_IDS,
                        {
                            "deployment_id": deployment_id,
                            "observation_ids": list(params.observation_ids),
                        },
                    ).mappings()
                ),
            )
        claim_facts = self._facts_for_claim_ids(
            connection=connection,
            deployment_id=deployment_id,
            claim_ids=params.claim_ids,
        )
        doc_facts, doc_claims = self._document_candidates(
            connection=connection, deployment_id=deployment_id, doc_ids=params.doc_ids
        )
        direct_claims = self._claims_for_ids(
            connection=connection,
            deployment_id=deployment_id,
            claim_ids=params.claim_ids,
        )
        for fact in (*entity_facts, *direct_facts, *claim_facts, *doc_facts):
            facts[(fact.kind, fact.fact_id)] = fact
        for claim in (*entity_claims, *direct_claims, *doc_claims):
            claims[(claim.lineage_id, claim.chunk_content_hash)] = claim
        return tuple(facts.values()), tuple(claims.values())

    def _facts_for_claim_ids(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        claim_ids: tuple[UUID, ...],
    ) -> tuple[KnowledgeFactFingerprint, ...]:
        """Resolve explicit claim IDs to the facts they support or contradict."""
        if not claim_ids:
            return ()
        return _fact_fingerprints(
            rows=connection.execute(
                _SELECT_FACTS_FOR_CLAIMS,
                {"deployment_id": deployment_id, "claim_ids": list(claim_ids)},
            ).mappings()
        )

    def _claims_for_ids(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        claim_ids: tuple[UUID, ...],
    ) -> tuple[KnowledgeClaimFingerprint, ...]:
        """Resolve raw claim IDs immediately into stable lineage/chunk coordinates."""
        if not claim_ids:
            return ()
        return _claim_fingerprints(
            rows=connection.execute(
                _SELECT_CLAIMS_BY_IDS,
                {"deployment_id": deployment_id, "claim_ids": list(claim_ids)},
            ).mappings()
        )

    def _delta_keys(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        delta: KnowledgeEvidenceDelta,
    ) -> tuple[KnowledgeRuleKey, ...]:
        """Derive the four coarse labels carried by changed evidence."""
        keys: set[tuple[KnowledgeRuleKeyKind, str]] = set()
        if delta.relation_ids:
            rows = connection.execute(
                _SELECT_RELATION_DELTA_KEYS,
                {
                    "deployment_id": deployment_id,
                    "relation_ids": list(delta.relation_ids),
                },
            ).mappings()
            for row in rows:
                keys.add((KnowledgeRuleKeyKind.ENTITY, str(row["subject_entity_id"])))
                keys.add((KnowledgeRuleKeyKind.ENTITY, str(row["object_entity_id"])))
                keys.add((KnowledgeRuleKeyKind.PREDICATE, str(row["predicate"])))
            sources = connection.execute(
                _SELECT_RELATION_DELTA_DOC_SOURCES,
                {
                    "deployment_id": deployment_id,
                    "relation_ids": list(delta.relation_ids),
                },
            ).scalars()
            keys.update(
                (KnowledgeRuleKeyKind.DOC_SOURCE, str(source)) for source in sources
            )
        if delta.observation_ids:
            entities = connection.execute(
                _SELECT_OBSERVATION_DELTA_KEYS,
                {
                    "deployment_id": deployment_id,
                    "observation_ids": list(delta.observation_ids),
                },
            ).scalars()
            keys.update(
                (KnowledgeRuleKeyKind.ENTITY, str(entity_id)) for entity_id in entities
            )
            sources = connection.execute(
                _SELECT_OBSERVATION_DELTA_DOC_SOURCES,
                {
                    "deployment_id": deployment_id,
                    "observation_ids": list(delta.observation_ids),
                },
            ).scalars()
            keys.update(
                (KnowledgeRuleKeyKind.DOC_SOURCE, str(source)) for source in sources
            )
        if delta.claim_ids:
            rows = connection.execute(
                _SELECT_CLAIM_DELTA_KEYS,
                {"deployment_id": deployment_id, "claim_ids": list(delta.claim_ids)},
            ).mappings()
            for row in rows:
                if row["entity_id"] is not None:
                    keys.add((KnowledgeRuleKeyKind.ENTITY, str(row["entity_id"])))
                keys.add((KnowledgeRuleKeyKind.DOC_SOURCE, str(row["source_kind"])))
        if delta.doc_ids:
            sources = connection.execute(
                _SELECT_DOCUMENT_DELTA_KEYS,
                {"deployment_id": deployment_id, "doc_ids": list(delta.doc_ids)},
            ).scalars()
            keys.update(
                (KnowledgeRuleKeyKind.DOC_SOURCE, str(source)) for source in sources
            )
        keys.update(
            (KnowledgeRuleKeyKind.COMMUNITY, str(community_id))
            for community_id in delta.community_ids
        )
        return tuple(
            KnowledgeRuleKey(kind=kind, value=value)
            for kind, value in sorted(keys, key=lambda item: (item[0].value, item[1]))
        )

    def _citation_artifacts(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        delta: KnowledgeEvidenceDelta,
    ) -> set[UUID]:
        """Find compiled pages citing schema-supported changed evidence."""
        artifacts: set[UUID] = set()
        for column, values in (
            ("claim_id", delta.claim_ids),
            ("relation_id", delta.relation_ids),
            ("doc_id", delta.doc_ids),
        ):
            if not values:
                continue
            statement = _citation_lookup(column=column)
            artifacts.update(
                connection.execute(
                    statement,
                    {"deployment_id": deployment_id, "evidence_ids": list(values)},
                ).scalars()
            )
        return artifacts

    def _manual_artifacts(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        delta: KnowledgeEvidenceDelta,
    ) -> set[UUID]:
        """Match explicit manual IDs that have no representable inverted key."""
        artifacts: set[UUID] = set()
        rows = connection.execute(
            _SELECT_MANUAL_RULES, {"deployment_id": deployment_id}
        ).mappings()
        changed = {
            "relation": set(delta.relation_ids),
            "observation": set(delta.observation_ids),
            "claim": set(delta.claim_ids),
            "doc": set(delta.doc_ids),
        }
        for row in rows:
            params = _parse_rule(row=row)
            if not isinstance(params, ManualRuleParams):
                continue
            if (
                changed["relation"].intersection(params.relation_ids)
                or changed["observation"].intersection(params.observation_ids)
                or changed["claim"].intersection(params.claim_ids)
                or changed["doc"].intersection(params.doc_ids)
            ):
                artifacts.add(row["artifact_id"])
        return artifacts

    def _validate_citations(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        citations: tuple[KnowledgeCitation, ...],
    ) -> None:
        """Reject citation IDs absent from this deployment's spine."""
        for citation in citations:
            if citation.claim_id is not None:
                exists = connection.execute(
                    _CLAIM_EXISTS,
                    {"deployment_id": deployment_id, "evidence_id": citation.claim_id},
                ).scalar_one()
            elif citation.relation_id is not None:
                exists = connection.execute(
                    _RELATION_EXISTS,
                    {
                        "deployment_id": deployment_id,
                        "evidence_id": citation.relation_id,
                    },
                ).scalar_one()
            else:
                exists = connection.execute(
                    _DOCUMENT_EXISTS,
                    {"deployment_id": deployment_id, "evidence_id": citation.doc_id},
                ).scalar_one()
            if not exists:
                raise KnowledgeCompilationError(
                    f"citation target does not exist in deployment: {citation}"
                )


def _stored_params(*, params: KnowledgeRuleParams) -> dict[str, JsonValue]:
    """Serialize a discriminated rule without duplicating its DB enum kind."""
    return _JSON_OBJECT_ADAPTER.validate_python(
        params.model_dump(mode="json", exclude={"kind"})
    )


def _parse_rule(*, row: RowMapping) -> KnowledgeRuleParams:
    """Validate a rule row against the typed JSON contract before evaluation."""
    stored = _JSON_OBJECT_ADAPTER.validate_python(row["params"])
    return _RULE_ADAPTER.validate_python({"kind": str(row["rule_kind"]), **stored})


def _fact_fingerprints(
    *, rows: Iterable[RowMapping]
) -> tuple[KnowledgeFactFingerprint, ...]:
    """Validate and deduplicate database fact-state rows."""
    facts: dict[tuple[str, UUID], KnowledgeFactFingerprint] = {}
    for row in rows:
        fact = KnowledgeFactFingerprint.model_validate(dict(row))
        facts[(fact.kind, fact.fact_id)] = fact
    return tuple(facts.values())


def _claim_fingerprints(
    *, rows: Iterable[RowMapping]
) -> tuple[KnowledgeClaimFingerprint, ...]:
    """Validate and deduplicate stable claim coordinates from SQL rows."""
    claims: dict[tuple[UUID, str], KnowledgeClaimFingerprint] = {}
    for row in rows:
        claim = KnowledgeClaimFingerprint.model_validate(dict(row))
        claims[(claim.lineage_id, claim.chunk_content_hash)] = claim
    return tuple(claims.values())


def _unique_citations(
    *, citations: tuple[KnowledgeCitation, ...]
) -> tuple[KnowledgeCitation, ...]:
    """Apply set semantics to repeated writer citations."""
    unique = {_citation_tuple(citation=citation): citation for citation in citations}
    return tuple(unique[key] for key in sorted(unique, key=lambda value: str(value)))


def _citation_tuple(
    *, citation: KnowledgeCitation
) -> tuple[str, UUID | None, UUID | None, UUID | None]:
    """Return the database uniqueness coordinates for one citation."""
    return (
        citation.role.value,
        citation.claim_id,
        citation.relation_id,
        citation.doc_id,
    )


def _citation_lookup(*, column: str) -> TextClause:
    """Build one allow-listed citation reverse lookup with an expanding bind."""
    if column not in {"claim_id", "relation_id", "doc_id"}:
        raise ValueError(f"unsupported citation column: {column}")
    return text(
        f"""
        SELECT DISTINCT a.artifact_id
        FROM knowledge_artifact_evidence e
        JOIN knowledge_artifacts a
          ON a.deployment_id = e.deployment_id
         AND a.artifact_id = e.artifact_id
        WHERE e.deployment_id = :deployment_id
          AND e.{column} IN :evidence_ids
          AND a.page_kind = 'compiled'
          AND a.status NOT IN ('quarantined', 'tombstoned')
        """  # noqa: S608 -- column is checked against the fixed schema allow-list above
    ).bindparams(bindparam("evidence_ids", expanding=True))


_INSERT_PLAN_DECISION = text(
    """
    INSERT INTO knowledge_plan_decisions (
        decision_id, deployment_id, scope_id, action, payload,
        trigger, planner_version, status
    ) VALUES (
        :decision_id, :deployment_id, :scope_id, :action, :payload,
        :trigger, :planner_version, :status
    )
    """
).bindparams(bindparam("payload", type_=JSON))

_INSERT_ARTIFACT = text(
    """
    INSERT INTO knowledge_artifacts (
        artifact_id, deployment_id, layer, page_kind, scope_id,
        parent_artifact_id, git_path, curation_path, kind, writer_version
    ) VALUES (
        :artifact_id, :deployment_id, :layer, :page_kind, :scope_id,
        :parent_artifact_id, :git_path, :curation_path, :kind, :writer_version
    )
    """
)

_INSERT_PAGE_RULE = text(
    """
    INSERT INTO knowledge_page_rules (
        rule_id, deployment_id, artifact_id, rule_kind, params,
        plan_decision_id
    ) VALUES (
        :rule_id, :deployment_id, :artifact_id, :rule_kind, :params,
        :plan_decision_id
    )
    """
).bindparams(bindparam("params", type_=JSON))

_SELECT_RULE = text(
    """
    SELECT rule_id, deployment_id, artifact_id, rule_kind::text AS rule_kind, params
    FROM knowledge_page_rules
    WHERE rule_id = :rule_id AND status = 'active'
    """
)

_SELECT_DERIVED_RULES = text(
    """
    SELECT rule_id, deployment_id, artifact_id, rule_kind::text AS rule_kind, params
    FROM knowledge_page_rules
    WHERE deployment_id = :deployment_id
      AND status = 'active'
      AND artifact_id IS NOT NULL
      AND rule_kind IN ('entity_subtree', 'community', 'scope_interests')
    ORDER BY rule_id
    """
)

_DELETE_RULE_KEYS = text("DELETE FROM knowledge_rule_keys WHERE rule_id = :rule_id")

_INSERT_RULE_KEY = text(
    """
    INSERT INTO knowledge_rule_keys (
        deployment_id, rule_id, key_kind, key_value
    ) VALUES (
        :deployment_id, :rule_id, :key_kind, :key_value
    )
    """
)

_SELECT_SUBTREE_MEMBERS = text(
    """
    WITH RECURSIVE members(entity_id) AS (
        SELECT e.entity_id
        FROM entities e
        WHERE e.deployment_id = :deployment_id
          AND e.entity_id = CAST(:root_entity_id AS uuid)
          AND e.status = 'active'
        UNION
        SELECT r.subject_entity_id
        FROM relations r
        JOIN members m ON m.entity_id = r.object_entity_id
        WHERE r.deployment_id = :deployment_id
          AND r.predicate = 'part_of'
          AND r.invalidated_at IS NULL
          AND r.valid_until IS NULL
    )
    SELECT entity_id FROM members ORDER BY entity_id
    """
)

_SELECT_COMMUNITY_MEMBERS = text(
    """
    SELECT entity_id
    FROM entity_graph_metrics
    WHERE deployment_id = :deployment_id AND community_id = :community_id
    ORDER BY entity_id
    """
)

_SELECT_SCOPE_INTERESTS = text(
    """
    SELECT interest_type::text AS interest_type, value
    FROM scope_interests
    WHERE scope_id = :scope_id
    ORDER BY interest_type, value
    """
)

_SELECT_ENTITIES_OF_TYPE = text(
    """
    SELECT entity_id
    FROM entities
    WHERE deployment_id = :deployment_id
      AND type = :entity_type
      AND status = 'active'
    ORDER BY entity_id
    """
)

_SELECT_DOC_SOURCES_FOR_METADATA = text(
    """
    SELECT DISTINCT d.source_kind
    FROM documents d
    LEFT JOIN document_versions v ON v.version_id = d.current_version_id
    LEFT JOIN content_objects o
      ON o.deployment_id = v.deployment_id AND o.content_hash = v.content_hash
    WHERE d.deployment_id = :deployment_id
      AND d.deleted_at IS NULL
      AND (
          d.source_kind = :value
          OR d.origin::text = :value
          OR o.mime = :value
      )
    ORDER BY d.source_kind
    """
)

_SELECT_ARTIFACT_RULES = text(
    """
    SELECT rule_id, deployment_id, rule_kind::text AS rule_kind, params
    FROM knowledge_page_rules
    WHERE artifact_id = :artifact_id AND status = 'active'
    ORDER BY rule_id
    """
)

_SELECT_CHILD_SUMMARIES = text(
    """
    SELECT page_summary
    FROM knowledge_artifacts
    WHERE parent_artifact_id = :artifact_id
      AND page_kind = 'compiled'
      AND status <> 'tombstoned'
      AND page_summary IS NOT NULL
    ORDER BY artifact_id
    """
)

_SELECT_FACT_SHEET_ARTIFACT = text(
    """
    SELECT deployment_id
    FROM knowledge_artifacts
    WHERE artifact_id = :artifact_id
      AND page_kind = 'compiled'
      AND status IN ('active', 'stale')
    """
)

_SELECT_TRANSACTION_TIMESTAMP = text("SELECT transaction_timestamp()")

_SELECT_ARTIFACT_HASH = text(
    """
    SELECT inputs_hash
    FROM knowledge_artifacts
    WHERE artifact_id = :artifact_id AND page_kind = 'compiled'
    """
)

_SELECT_COMPILED_ARTIFACTS = text(
    """
    SELECT artifact_id, inputs_hash
    FROM knowledge_artifacts
    WHERE deployment_id = :deployment_id
      AND page_kind = 'compiled'
      AND status NOT IN ('quarantined', 'tombstoned')
    ORDER BY artifact_id
    """
)

_SELECT_FILTERED_COMPILED_ARTIFACTS = text(
    """
    SELECT artifact_id, inputs_hash
    FROM knowledge_artifacts
    WHERE deployment_id = :deployment_id
      AND page_kind = 'compiled'
      AND status NOT IN ('quarantined', 'tombstoned')
      AND artifact_id IN :artifact_ids
    ORDER BY artifact_id
    """
).bindparams(bindparam("artifact_ids", expanding=True))

_MARK_STALE = text(
    """
    UPDATE knowledge_artifacts
    SET status = 'stale'
    WHERE artifact_id = :artifact_id
      AND page_kind = 'compiled'
      AND status = 'active'
    RETURNING artifact_id
    """
)

_FACT_COLUMNS_RELATION = """
    'relation' AS kind,
    r.relation_id AS fact_id,
    r.valid_from,
    r.valid_until,
    r.invalidated_at,
    r.evidence_count,
    r.contradict_count,
    r.contradiction_group
"""

_FACT_COLUMNS_OBSERVATION = """
    'observation' AS kind,
    o.observation_id AS fact_id,
    o.valid_from,
    o.valid_until,
    o.invalidated_at,
    o.evidence_count,
    o.contradict_count,
    o.contradiction_group
"""

_SELECT_FACT_SHEET_RELATIONS = text(
    """
    SELECT 'relation' AS kind,
           r.relation_id AS fact_id,
           COALESCE(
               NULLIF(btrim(r.fact_label), ''),
               subject.canonical_name || ' ' || replace(r.predicate, '_', ' ')
                 || ' ' || object.canonical_name
           ) AS label,
           r.valid_from, r.valid_until, r.ingested_at, r.invalidated_at,
           r.evidence_count, r.contradict_count, r.contradiction_group
    FROM relations r
    JOIN entities subject
      ON subject.deployment_id = r.deployment_id
     AND subject.entity_id = r.subject_entity_id
    JOIN entities object
      ON object.deployment_id = r.deployment_id
     AND object.entity_id = r.object_entity_id
    WHERE r.deployment_id = :deployment_id
      AND r.relation_id IN :relation_ids
    ORDER BY r.relation_id
    """
).bindparams(bindparam("relation_ids", expanding=True))

_SELECT_FACT_SHEET_OBSERVATIONS = text(
    """
    SELECT 'observation' AS kind,
           o.observation_id AS fact_id,
           COALESCE(NULLIF(btrim(o.obs_label), ''), o.statement) AS label,
           o.valid_from, o.valid_until, o.ingested_at, o.invalidated_at,
           o.evidence_count, o.contradict_count, o.contradiction_group
    FROM observations o
    WHERE o.deployment_id = :deployment_id
      AND o.observation_id IN :observation_ids
    ORDER BY o.observation_id
    """
).bindparams(bindparam("observation_ids", expanding=True))

_SELECT_WRITER_CLAIMS = text(
    """
    WITH wanted AS (
        SELECT *
        FROM jsonb_to_recordset(CAST(:candidates AS jsonb))
          AS item(lineage_id uuid, chunk_content_hash text)
    )
    SELECT c.claim_id, c.doc_id AS lineage_id, ch.chunk_content_hash,
           c.claim_text, c.source_span,
           COALESCE(NULLIF(btrim(d.title), ''), d.source_ref, d.doc_id::text)
             AS document_title,
           d.source_kind
    FROM wanted w
    JOIN claims c ON c.doc_id = w.lineage_id
    JOIN chunks ch
      ON ch.deployment_id = c.deployment_id AND ch.chunk_id = c.chunk_id
     AND ch.chunk_content_hash = w.chunk_content_hash
    JOIN documents d
      ON d.deployment_id = c.deployment_id AND d.doc_id = c.doc_id
    WHERE c.deployment_id = :deployment_id
      AND c.is_current_testimony
    ORDER BY c.doc_id, ch.chunk_content_hash, c.claim_id
    """
).bindparams(bindparam("candidates", type_=JSON))

_SELECT_WRITER_RELATION_REFERENCES = text(
    """
    SELECT e.claim_id, 'relation' AS kind, e.relation_id AS fact_id,
           e.stance::text AS stance
    FROM relation_evidence e
    WHERE e.deployment_id = :deployment_id
      AND e.relation_id IN :fact_ids
      AND e.claim_id IN :claim_ids
    ORDER BY e.claim_id, e.relation_id, e.stance
    """
).bindparams(
    bindparam("fact_ids", expanding=True), bindparam("claim_ids", expanding=True)
)

_SELECT_WRITER_OBSERVATION_REFERENCES = text(
    """
    SELECT e.claim_id, 'observation' AS kind, e.observation_id AS fact_id,
           e.stance::text AS stance
    FROM observation_evidence e
    WHERE e.deployment_id = :deployment_id
      AND e.observation_id IN :fact_ids
      AND e.claim_id IN :claim_ids
    ORDER BY e.claim_id, e.observation_id, e.stance
    """
).bindparams(
    bindparam("fact_ids", expanding=True), bindparam("claim_ids", expanding=True)
)

_SELECT_ENTITY_RELATIONS = text(
    f"""
    SELECT {_FACT_COLUMNS_RELATION}
    FROM relations r
    WHERE r.deployment_id = :deployment_id
      AND (
          r.subject_entity_id IN :entity_ids
          OR r.object_entity_id IN :entity_ids
      )
    ORDER BY r.relation_id
    """  # noqa: S608 -- fixed local projection fragment, no external input
).bindparams(bindparam("entity_ids", expanding=True))

_SELECT_FILTERED_ENTITY_RELATIONS = text(
    f"""
    SELECT {_FACT_COLUMNS_RELATION}
    FROM relations r
    WHERE r.deployment_id = :deployment_id
      AND (
          r.subject_entity_id IN :entity_ids
          OR r.object_entity_id IN :entity_ids
      )
      AND r.predicate IN :predicates
    ORDER BY r.relation_id
    """  # noqa: S608 -- fixed local projection fragment, no external input
).bindparams(
    bindparam("entity_ids", expanding=True), bindparam("predicates", expanding=True)
)

_SELECT_ENTITY_OBSERVATIONS = text(
    f"""
    SELECT {_FACT_COLUMNS_OBSERVATION}
    FROM observations o
    WHERE o.deployment_id = :deployment_id
      AND o.subject_entity_id IN :entity_ids
    ORDER BY o.observation_id
    """  # noqa: S608 -- fixed local projection fragment, no external input
).bindparams(bindparam("entity_ids", expanding=True))

_SELECT_ENTITY_CLAIMS = text(
    """
    SELECT DISTINCT c.doc_id AS lineage_id, ch.chunk_content_hash
    FROM mentions m
    JOIN resolution_decisions rd
      ON rd.deployment_id = m.deployment_id
     AND rd.mention_id = m.mention_id
     AND rd.superseded_by IS NULL
    JOIN claims c
      ON c.deployment_id = m.deployment_id AND c.claim_id = m.claim_id
    JOIN chunks ch
      ON ch.deployment_id = c.deployment_id AND ch.chunk_id = c.chunk_id
    WHERE m.deployment_id = :deployment_id
      AND rd.entity_id IN :entity_ids
      AND c.is_current_testimony
    ORDER BY c.doc_id, ch.chunk_content_hash
    """
).bindparams(bindparam("entity_ids", expanding=True))

_SELECT_PREDICATE_RELATIONS = text(
    f"""
    SELECT {_FACT_COLUMNS_RELATION}
    FROM relations r
    WHERE r.deployment_id = :deployment_id
      AND r.predicate = :predicate
      AND (
          CAST(:subject_entity_id AS uuid) IS NULL
          OR r.subject_entity_id = CAST(:subject_entity_id AS uuid)
      )
      AND (
          CAST(:object_entity_id AS uuid) IS NULL
          OR r.object_entity_id = CAST(:object_entity_id AS uuid)
      )
    ORDER BY r.relation_id
    """  # noqa: S608 -- fixed local projection fragment, no external input
)

_SELECT_PREDICATE_CLAIMS = text(
    """
    SELECT DISTINCT c.doc_id AS lineage_id, ch.chunk_content_hash
    FROM relations r
    JOIN relation_evidence e
      ON e.deployment_id = r.deployment_id AND e.relation_id = r.relation_id
    JOIN claims c
      ON c.deployment_id = e.deployment_id AND c.claim_id = e.claim_id
    JOIN chunks ch
      ON ch.deployment_id = c.deployment_id AND ch.chunk_id = c.chunk_id
    WHERE r.deployment_id = :deployment_id
      AND r.predicate = :predicate
      AND c.is_current_testimony
    ORDER BY c.doc_id, ch.chunk_content_hash
    """
)

_SELECT_DOC_SET = text(
    """
    SELECT d.doc_id
    FROM documents d
    LEFT JOIN document_versions v ON v.version_id = d.current_version_id
    LEFT JOIN content_objects o
      ON o.deployment_id = v.deployment_id AND o.content_hash = v.content_hash
    WHERE d.deployment_id = :deployment_id
      AND d.deleted_at IS NULL
      AND d.source_kind = :source_kind
      AND (CAST(:mime AS text) IS NULL OR o.mime = CAST(:mime AS text))
      AND (
          CAST(:origin AS text) IS NULL
          OR d.origin::text = CAST(:origin AS text)
      )
      AND (
          CAST(:source_modified_from AS timestamptz) IS NULL
          OR v.source_modified_at >= CAST(:source_modified_from AS timestamptz)
      )
      AND (
          CAST(:source_modified_until AS timestamptz) IS NULL
          OR v.source_modified_at <= CAST(:source_modified_until AS timestamptz)
      )
    ORDER BY d.doc_id
    """
)

_SELECT_DOCUMENT_FACTS = text(
    f"""
    SELECT {_FACT_COLUMNS_RELATION}
    FROM relations r
    WHERE r.deployment_id = :deployment_id
      AND EXISTS (
          SELECT 1
          FROM relation_evidence e
          JOIN claims c
            ON c.deployment_id = e.deployment_id AND c.claim_id = e.claim_id
          WHERE e.relation_id = r.relation_id
            AND e.deployment_id = r.deployment_id
            AND e.doc_id IN :doc_ids
            AND c.is_current_testimony
      )
    UNION ALL
    SELECT {_FACT_COLUMNS_OBSERVATION}
    FROM observations o
    WHERE o.deployment_id = :deployment_id
      AND EXISTS (
          SELECT 1
          FROM observation_evidence e
          JOIN claims c
            ON c.deployment_id = e.deployment_id AND c.claim_id = e.claim_id
          WHERE e.observation_id = o.observation_id
            AND e.deployment_id = o.deployment_id
            AND e.doc_id IN :doc_ids
            AND c.is_current_testimony
      )
    """  # noqa: S608 -- fixed local projection fragments, no external input
).bindparams(bindparam("doc_ids", expanding=True))

_SELECT_DOCUMENT_CLAIMS = text(
    """
    SELECT DISTINCT c.doc_id AS lineage_id, ch.chunk_content_hash
    FROM claims c
    JOIN chunks ch
      ON ch.deployment_id = c.deployment_id AND ch.chunk_id = c.chunk_id
    WHERE c.deployment_id = :deployment_id
      AND c.doc_id IN :doc_ids
      AND c.is_current_testimony
    ORDER BY c.doc_id, ch.chunk_content_hash
    """
).bindparams(bindparam("doc_ids", expanding=True))

_SELECT_DOCS_FOR_METADATA = text(
    """
    SELECT d.doc_id
    FROM documents d
    LEFT JOIN document_versions v ON v.version_id = d.current_version_id
    LEFT JOIN content_objects o
      ON o.deployment_id = v.deployment_id AND o.content_hash = v.content_hash
    WHERE d.deployment_id = :deployment_id
      AND d.deleted_at IS NULL
      AND (
          d.source_kind = :value
          OR d.origin::text = :value
          OR o.mime = :value
      )
    ORDER BY d.doc_id
    """
)

_SELECT_KEYWORD_CLAIMS = text(
    """
    SELECT claim_id
    FROM claims
    WHERE deployment_id = :deployment_id
      AND is_current_testimony
      AND position(lower(:keyword) IN lower(claim_text)) > 0
    ORDER BY claim_id
    """
)

_SELECT_FACTS_FOR_CLAIMS = text(
    f"""
    SELECT {_FACT_COLUMNS_RELATION}
    FROM relations r
    WHERE r.deployment_id = :deployment_id
      AND EXISTS (
          SELECT 1 FROM relation_evidence e
          WHERE e.relation_id = r.relation_id
            AND e.deployment_id = r.deployment_id
            AND e.claim_id IN :claim_ids
      )
    UNION ALL
    SELECT {_FACT_COLUMNS_OBSERVATION}
    FROM observations o
    WHERE o.deployment_id = :deployment_id
      AND EXISTS (
          SELECT 1 FROM observation_evidence e
          WHERE e.observation_id = o.observation_id
            AND e.deployment_id = o.deployment_id
            AND e.claim_id IN :claim_ids
      )
    """  # noqa: S608 -- fixed local projection fragments, no external input
).bindparams(bindparam("claim_ids", expanding=True))

_SELECT_CLAIMS_BY_IDS = text(
    """
    SELECT DISTINCT c.doc_id AS lineage_id, ch.chunk_content_hash
    FROM claims c
    JOIN chunks ch
      ON ch.deployment_id = c.deployment_id AND ch.chunk_id = c.chunk_id
    WHERE c.deployment_id = :deployment_id AND c.claim_id IN :claim_ids
    ORDER BY c.doc_id, ch.chunk_content_hash
    """
).bindparams(bindparam("claim_ids", expanding=True))

_SELECT_RELATIONS_BY_IDS = text(
    f"""
    SELECT {_FACT_COLUMNS_RELATION}
    FROM relations r
    WHERE r.deployment_id = :deployment_id AND r.relation_id IN :relation_ids
    """  # noqa: S608 -- fixed local projection fragment, no external input
).bindparams(bindparam("relation_ids", expanding=True))

_SELECT_OBSERVATIONS_BY_IDS = text(
    f"""
    SELECT {_FACT_COLUMNS_OBSERVATION}
    FROM observations o
    WHERE o.deployment_id = :deployment_id
      AND o.observation_id IN :observation_ids
    """  # noqa: S608 -- fixed local projection fragment, no external input
).bindparams(bindparam("observation_ids", expanding=True))

_SELECT_RELATION_DELTA_KEYS = text(
    """
    SELECT subject_entity_id, object_entity_id, predicate
    FROM relations
    WHERE deployment_id = :deployment_id AND relation_id IN :relation_ids
    """
).bindparams(bindparam("relation_ids", expanding=True))

_SELECT_RELATION_DELTA_DOC_SOURCES = text(
    """
    SELECT DISTINCT d.source_kind
    FROM relation_evidence e
    JOIN documents d
      ON d.deployment_id = e.deployment_id AND d.doc_id = e.doc_id
    WHERE e.deployment_id = :deployment_id AND e.relation_id IN :relation_ids
    """
).bindparams(bindparam("relation_ids", expanding=True))

_SELECT_PART_OF_DELTA = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM relations
        WHERE deployment_id = :deployment_id
          AND relation_id IN :relation_ids
          AND predicate = 'part_of'
    )
    """
).bindparams(bindparam("relation_ids", expanding=True))

_SELECT_OBSERVATION_DELTA_KEYS = text(
    """
    SELECT subject_entity_id
    FROM observations
    WHERE deployment_id = :deployment_id AND observation_id IN :observation_ids
    """
).bindparams(bindparam("observation_ids", expanding=True))

_SELECT_OBSERVATION_DELTA_DOC_SOURCES = text(
    """
    SELECT DISTINCT d.source_kind
    FROM observation_evidence e
    JOIN documents d
      ON d.deployment_id = e.deployment_id AND d.doc_id = e.doc_id
    WHERE e.deployment_id = :deployment_id
      AND e.observation_id IN :observation_ids
    """
).bindparams(bindparam("observation_ids", expanding=True))

_SELECT_CLAIM_DELTA_KEYS = text(
    """
    SELECT DISTINCT d.source_kind, rd.entity_id
    FROM claims c
    JOIN documents d
      ON d.deployment_id = c.deployment_id AND d.doc_id = c.doc_id
    LEFT JOIN mentions m
      ON m.deployment_id = c.deployment_id AND m.claim_id = c.claim_id
    LEFT JOIN resolution_decisions rd
      ON rd.deployment_id = m.deployment_id
     AND rd.mention_id = m.mention_id
     AND rd.superseded_by IS NULL
    WHERE c.deployment_id = :deployment_id AND c.claim_id IN :claim_ids
    """
).bindparams(bindparam("claim_ids", expanding=True))

_SELECT_DOCUMENT_DELTA_KEYS = text(
    """
    SELECT DISTINCT source_kind
    FROM documents
    WHERE deployment_id = :deployment_id AND doc_id IN :doc_ids
    """
).bindparams(bindparam("doc_ids", expanding=True))

_SELECT_ARTIFACTS_FOR_KEY = text(
    """
    SELECT DISTINCT a.artifact_id
    FROM knowledge_rule_keys k
    JOIN knowledge_page_rules r ON r.rule_id = k.rule_id
    JOIN knowledge_artifacts a
      ON a.deployment_id = r.deployment_id AND a.artifact_id = r.artifact_id
    WHERE k.deployment_id = :deployment_id
      AND k.key_kind = CAST(:key_kind AS rule_key_kind)
      AND k.key_value = :key_value
      AND r.status = 'active'
      AND a.page_kind = 'compiled'
      AND a.status NOT IN ('quarantined', 'tombstoned')
    """
)

_SELECT_SCOPE_RULE_ARTIFACTS = text(
    """
    SELECT DISTINCT a.artifact_id
    FROM knowledge_page_rules r
    JOIN knowledge_artifacts a
      ON a.deployment_id = r.deployment_id AND a.artifact_id = r.artifact_id
    WHERE r.deployment_id = :deployment_id
      AND r.rule_kind = 'scope_interests'
      AND r.status = 'active'
      AND a.page_kind = 'compiled'
      AND a.status NOT IN ('quarantined', 'tombstoned')
    """
)

_SELECT_MANUAL_RULES = text(
    """
    SELECT r.rule_id, r.deployment_id, r.artifact_id,
           r.rule_kind::text AS rule_kind, r.params
    FROM knowledge_page_rules r
    JOIN knowledge_artifacts a
      ON a.deployment_id = r.deployment_id AND a.artifact_id = r.artifact_id
    WHERE r.deployment_id = :deployment_id
      AND r.rule_kind = 'manual'
      AND r.status = 'active'
      AND a.page_kind = 'compiled'
      AND a.status NOT IN ('quarantined', 'tombstoned')
    """
)

_SELECT_CITATIONS = text(
    """
    SELECT role::text, claim_id, relation_id, doc_id
    FROM knowledge_artifact_evidence
    WHERE artifact_id = :artifact_id
    """
)

_DELETE_CITATIONS = text(
    "DELETE FROM knowledge_artifact_evidence WHERE artifact_id = :artifact_id"
)

_INSERT_CITATION = text(
    """
    INSERT INTO knowledge_artifact_evidence (
        evidence_link_id, deployment_id, artifact_id,
        claim_id, relation_id, doc_id, role
    ) VALUES (
        :evidence_link_id, :deployment_id, :artifact_id,
        :claim_id, :relation_id, :doc_id, :role
    )
    """
)

_INSERT_COMPILATION = text(
    """
    INSERT INTO knowledge_compilations (
        compilation_id, cycle_id, deployment_id, artifact_id, inputs_hash,
        candidate_count, cited_count, uncited_count, claims_cut_count,
        evidence_added, evidence_removed, evidence_invalidated,
        writer_version, tokens, cost_usd, session_transcript_uri,
        page_summary, content_hash, citations, suggestions
    ) VALUES (
        :compilation_id, :cycle_id, :deployment_id, :artifact_id, :inputs_hash,
        :candidate_count, :cited_count, :uncited_count, :claims_cut_count,
        :evidence_added, :evidence_removed, :evidence_invalidated,
        :writer_version, :tokens, :cost_usd, :session_transcript_uri,
        :page_summary, :content_hash, :citations, :suggestions
    )
    """
).bindparams(bindparam("citations", type_=JSON), bindparam("suggestions", type_=JSON))

_INSERT_FAILED_COMPILATION = text(
    """
    INSERT INTO knowledge_compilations (
        compilation_id, deployment_id, artifact_id, inputs_hash,
        candidate_count, cited_count, uncited_count, claims_cut_count,
        evidence_added, evidence_removed, evidence_invalidated,
        writer_version, session_transcript_uri, failed_at, failure
    )
    SELECT :compilation_id, :deployment_id, :artifact_id, :inputs_hash,
           :candidate_count, 0, :candidate_count, :claims_cut_count,
           0, 0, 0, :writer_version, :session_transcript_uri, now(), :failure
    FROM knowledge_artifacts
    WHERE artifact_id = :artifact_id
      AND deployment_id = :deployment_id
      AND page_kind = 'compiled'
      AND status IN ('active', 'stale')
    RETURNING compilation_id
    """
)

_SELECT_COMPILATION_STATE = text(
    """
    SELECT cycle_id, deployment_id, artifact_id, inputs_hash, writer_version,
           candidate_count, cited_count, uncited_count, claims_cut_count,
           evidence_invalidated, page_summary, content_hash, citations,
           suggestions, git_commit, failed_at
    FROM knowledge_compilations
    WHERE compilation_id = :compilation_id
    FOR UPDATE
    """
)

_SELECT_CYCLE_COMPILATION_IDS = text(
    """
    SELECT compilation_id
    FROM knowledge_compilations
    WHERE deployment_id = :deployment_id AND cycle_id = :cycle_id
    ORDER BY compilation_id
    FOR UPDATE
    """
)

_STAMP_COMPILATION_COMMIT = text(
    """
    UPDATE knowledge_compilations
    SET git_commit = :git_commit
    WHERE compilation_id = :compilation_id AND git_commit IS NULL
    """
)

_SELECT_COMPILE_ARTIFACTS = text(
    """
    SELECT artifact_id, deployment_id, scope_id, parent_artifact_id,
           git_path, curation_path, kind AS artifact_kind, page_summary,
           status = 'stale' AS stale
    FROM knowledge_artifacts
    WHERE deployment_id = :deployment_id
      AND page_kind = 'compiled'
      AND status IN ('active', 'stale')
    ORDER BY artifact_id
    """
)

_SELECT_ARTIFACT_GIT_PATHS = text(
    """
    SELECT git_path
    FROM knowledge_artifacts
    WHERE deployment_id = :deployment_id AND status <> 'tombstoned'
    ORDER BY git_path
    """
)

_SELECT_PENDING_COMPILATIONS = text(
    """
    SELECT compilation_id, cycle_id, deployment_id, artifact_id, inputs_hash,
           candidate_count, uncited_count, claims_cut_count,
           evidence_invalidated, writer_version,
           page_summary, content_hash, citations, suggestions, tokens, cost_usd,
           session_transcript_uri
    FROM knowledge_compilations
    WHERE deployment_id = :deployment_id
      AND git_commit IS NULL
      AND failed_at IS NULL
      AND cycle_id IS NOT NULL
      AND page_summary IS NOT NULL
      AND content_hash IS NOT NULL
      AND citations IS NOT NULL
    ORDER BY compiled_at, artifact_id
    """
)

_FAIL_PENDING_CYCLE = text(
    """
    UPDATE knowledge_compilations
    SET failed_at = now(), failure = :failure
    WHERE deployment_id = :deployment_id
      AND cycle_id = :cycle_id
      AND git_commit IS NULL
      AND failed_at IS NULL
    """
)

_TRY_COMMIT_LEASE = text(
    """
    SELECT pg_try_advisory_lock(
        hashtextextended('k-commit:' || CAST(:deployment_id AS text), 0)
    )
    """
)

_RELEASE_COMMIT_LEASE = text(
    """
    SELECT pg_advisory_unlock(
        hashtextextended('k-commit:' || CAST(:deployment_id AS text), 0)
    )
    """
)

_UPDATE_COMPILED_ARTIFACT = text(
    """
    UPDATE knowledge_artifacts
    SET inputs_hash = :inputs_hash,
        writer_version = :writer_version,
        page_summary = :page_summary,
        content_hash = :content_hash,
        last_compiled_at = now(),
        status = 'active'
    WHERE artifact_id = :artifact_id
      AND page_kind = 'compiled'
      AND status IN ('active', 'stale')
    RETURNING artifact_id
    """
)

_CLAIM_EXISTS = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM claims
        WHERE deployment_id = :deployment_id AND claim_id = :evidence_id
    )
    """
)

_RELATION_EXISTS = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM relations
        WHERE deployment_id = :deployment_id AND relation_id = :evidence_id
    )
    """
)

_DOCUMENT_EXISTS = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM documents
        WHERE deployment_id = :deployment_id AND doc_id = :evidence_id
    )
    """
)
