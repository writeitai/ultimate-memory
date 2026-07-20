"""Typed Plane-K control-plane values (D45)."""

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated
from typing import Literal
from typing import TypeAlias
from uuid import UUID

from pydantic import AfterValidator
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import JsonValue
from pydantic import model_validator

from ultimate_memory.model.queue import UTCDateTime

SHA256: TypeAlias = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _sorted_unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    """Canonicalize a set-valued string parameter."""
    return tuple(sorted(set(values)))


def _sorted_unique_uuids(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
    """Canonicalize a set-valued UUID parameter."""
    return tuple(sorted(set(values), key=str))


def _sorted_unique_candidate_layers(
    values: tuple["KnowledgeCandidateLayer", ...],
) -> tuple["KnowledgeCandidateLayer", ...]:
    """Canonicalize a set-valued candidate-layer parameter."""
    return tuple(sorted(set(values), key=lambda value: value.value))


CanonicalStrings: TypeAlias = Annotated[
    tuple[str, ...], AfterValidator(_sorted_unique_strings)
]
CanonicalUUIDs: TypeAlias = Annotated[
    tuple[UUID, ...], AfterValidator(_sorted_unique_uuids)
]


class KnowledgeRuleKind(StrEnum):
    """The closed, mechanically evaluated D45 routing-rule vocabulary."""

    ENTITY = "entity"
    ENTITY_SUBTREE = "entity_subtree"
    PREDICATE_BEAT = "predicate_beat"
    COMMUNITY = "community"
    DOC_SET = "doc_set"
    SCOPE_INTERESTS = "scope_interests"
    MANUAL = "manual"


class KnowledgeRuleKeyKind(StrEnum):
    """The four coarse keys supported by the routing inverted index."""

    ENTITY = "entity"
    PREDICATE = "predicate"
    COMMUNITY = "community"
    DOC_SOURCE = "doc_source"


class KnowledgeCandidateLayer(StrEnum):
    """Candidate grains a rule may select for a compiled page."""

    RELATIONS = "relations"
    OBSERVATIONS = "observations"
    CLAIMS = "claims"


CanonicalCandidateLayers: TypeAlias = Annotated[
    tuple[KnowledgeCandidateLayer, ...], AfterValidator(_sorted_unique_candidate_layers)
]


class KnowledgeLayer(StrEnum):
    """The three content tiers sharing one compile mechanism (D47)."""

    K1 = "K1"
    K2 = "K2"
    K3 = "K3"


class KnowledgePageKind(StrEnum):
    """The D46 page ownership contract."""

    COMPILED = "compiled"
    AUTHORED = "authored"


class KnowledgePlanAction(StrEnum):
    """Append-only planner structure actions supported by the schema."""

    CREATE_PAGE = "create_page"
    SPLIT_PAGE = "split_page"
    MERGE_PAGES = "merge_pages"
    MOVE_PAGE = "move_page"
    RETIRE_PAGE = "retire_page"
    ADJUST_RULE = "adjust_rule"
    CONVERT_KIND = "convert_kind"


class KnowledgePlanTrigger(StrEnum):
    """Reasons a planner may make a durable structure decision."""

    ORPHAN_EVIDENCE = "orphan_evidence"
    SIZE_OVERFLOW = "size_overflow"
    COMMUNITY_CHANGE = "community_change"
    REFLECTION = "reflection"
    WRITER_SUGGESTION = "writer_suggestion"
    HUMAN = "human"


class KnowledgePlanStatus(StrEnum):
    """Review state for a structure decision."""

    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"


class KnowledgeEvidenceRole(StrEnum):
    """How a K citation uses one evidence target."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CITES = "cites"


class EntityRuleParams(BaseModel):
    """Everything about one entity, optionally narrowed by fact layer/predicate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[KnowledgeRuleKind.ENTITY] = KnowledgeRuleKind.ENTITY
    entity_id: UUID
    predicates: CanonicalStrings = ()
    layers: CanonicalCandidateLayers = (
        KnowledgeCandidateLayer.RELATIONS,
        KnowledgeCandidateLayer.OBSERVATIONS,
        KnowledgeCandidateLayer.CLAIMS,
    )


class EntitySubtreeRuleParams(BaseModel):
    """One entity plus the transitive subjects that are ``part_of`` it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[KnowledgeRuleKind.ENTITY_SUBTREE] = KnowledgeRuleKind.ENTITY_SUBTREE
    root_entity_id: UUID
    predicates: CanonicalStrings = ()
    layers: CanonicalCandidateLayers = (
        KnowledgeCandidateLayer.RELATIONS,
        KnowledgeCandidateLayer.OBSERVATIONS,
        KnowledgeCandidateLayer.CLAIMS,
    )


class PredicateBeatRuleParams(BaseModel):
    """Relations of one governed predicate, optionally pinned to either endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[KnowledgeRuleKind.PREDICATE_BEAT] = KnowledgeRuleKind.PREDICATE_BEAT
    predicate: str
    subject_entity_id: UUID | None = None
    object_entity_id: UUID | None = None


class CommunityRuleParams(BaseModel):
    """Evidence about members of one detected entity community."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[KnowledgeRuleKind.COMMUNITY] = KnowledgeRuleKind.COMMUNITY
    community_id: UUID
    layers: CanonicalCandidateLayers = (
        KnowledgeCandidateLayer.RELATIONS,
        KnowledgeCandidateLayer.OBSERVATIONS,
        KnowledgeCandidateLayer.CLAIMS,
    )


class DocSetRuleParams(BaseModel):
    """Evidence from one source family, with optional snapshot metadata filters.

    ``source_kind`` is required because it is the only document key represented
    by ``knowledge_rule_keys``. MIME, origin, and time are exact secondary SQL
    filters after that coarse key hit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[KnowledgeRuleKind.DOC_SET] = KnowledgeRuleKind.DOC_SET
    source_kind: str
    mime: str | None = None
    origin: Literal["external", "system_generated"] | None = None
    source_modified_from: UTCDateTime | None = None
    source_modified_until: UTCDateTime | None = None

    @model_validator(mode="after")
    def require_ordered_time_range(self) -> "DocSetRuleParams":
        """Reject a document window whose upper bound precedes its lower bound."""
        if (
            self.source_modified_from is not None
            and self.source_modified_until is not None
            and self.source_modified_until < self.source_modified_from
        ):
            raise ValueError(
                "source_modified_until must not precede source_modified_from"
            )
        return self


class ScopeInterestsRuleParams(BaseModel):
    """Delegate selection to the existing registry interests of one scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[KnowledgeRuleKind.SCOPE_INTERESTS] = KnowledgeRuleKind.SCOPE_INTERESTS
    scope_id: UUID


class ManualRuleParams(BaseModel):
    """An explicit editorial assignment of entities or evidence IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[KnowledgeRuleKind.MANUAL] = KnowledgeRuleKind.MANUAL
    entity_ids: CanonicalUUIDs = ()
    relation_ids: CanonicalUUIDs = ()
    observation_ids: CanonicalUUIDs = ()
    claim_ids: CanonicalUUIDs = ()
    doc_ids: CanonicalUUIDs = ()

    @model_validator(mode="after")
    def require_a_target(self) -> "ManualRuleParams":
        """Reject a manual rule that can never select anything."""
        if not any(
            (
                self.entity_ids,
                self.relation_ids,
                self.observation_ids,
                self.claim_ids,
                self.doc_ids,
            )
        ):
            raise ValueError("manual rule requires at least one target")
        return self


KnowledgeRuleParams = Annotated[
    EntityRuleParams
    | EntitySubtreeRuleParams
    | PredicateBeatRuleParams
    | CommunityRuleParams
    | DocSetRuleParams
    | ScopeInterestsRuleParams
    | ManualRuleParams,
    Field(discriminator="kind"),
]


class KnowledgePlanDecisionCreate(BaseModel):
    """One planner structure decision to append to the durable transcript."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: UUID
    deployment_id: UUID
    scope_id: UUID | None = None
    action: KnowledgePlanAction
    payload: dict[str, JsonValue]
    trigger: KnowledgePlanTrigger
    planner_version: str
    status: KnowledgePlanStatus = KnowledgePlanStatus.PROPOSED


class KnowledgeArtifactCreate(BaseModel):
    """The Postgres handle for one Plane-K git path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    deployment_id: UUID
    layer: KnowledgeLayer
    page_kind: KnowledgePageKind
    git_path: str
    scope_id: UUID | None = None
    parent_artifact_id: UUID | None = None
    curation_path: str | None = None
    artifact_kind: str | None = None
    writer_version: str | None = None


class KnowledgePageRuleCreate(BaseModel):
    """One page-owned routing rule and the plan decision that authorized it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: UUID
    deployment_id: UUID
    artifact_id: UUID
    plan_decision_id: UUID
    params: KnowledgeRuleParams


class KnowledgeRuleKey(BaseModel):
    """One materialized coarse key for routing changed evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: KnowledgeRuleKeyKind
    value: str


class KnowledgeCitation(BaseModel):
    """One citation with exactly one schema-supported evidence target."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: KnowledgeEvidenceRole
    claim_id: UUID | None = None
    relation_id: UUID | None = None
    doc_id: UUID | None = None

    @model_validator(mode="after")
    def require_exactly_one_target(self) -> "KnowledgeCitation":
        """Mirror the ``knowledge_artifact_evidence`` exactly-one CHECK."""
        if (
            sum(
                target is not None
                for target in (self.claim_id, self.relation_id, self.doc_id)
            )
            != 1
        ):
            raise ValueError("citation requires exactly one evidence target")
        return self


class KnowledgeEvidenceTarget(BaseModel):
    """One role-independent claim, relation, or document exclusion target."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: UUID | None = None
    relation_id: UUID | None = None
    doc_id: UUID | None = None

    @model_validator(mode="after")
    def require_exactly_one_target(self) -> "KnowledgeEvidenceTarget":
        """Keep exclusions at the same exactly-one evidence grain as citations."""
        if (
            sum(
                target is not None
                for target in (self.claim_id, self.relation_id, self.doc_id)
            )
            != 1
        ):
            raise ValueError("evidence target requires exactly one ID")
        return self


class KnowledgeCompilationWrite(BaseModel):
    """Validated compile metadata to commit atomically to the control plane."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    compilation_id: UUID
    deployment_id: UUID
    artifact_id: UUID
    inputs_hash: SHA256
    candidate_count: int = Field(ge=0)
    uncited_count: int = Field(ge=0)
    citations: tuple[KnowledgeCitation, ...]
    evidence_invalidated: int = Field(default=0, ge=0)
    writer_version: str
    page_summary: str
    content_hash: SHA256
    tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    session_transcript_uri: str | None = None

    @model_validator(mode="after")
    def require_bounded_uncited_count(self) -> "KnowledgeCompilationWrite":
        """Keep the offered-but-unused count within the candidate manifest."""
        if self.uncited_count > self.candidate_count:
            raise ValueError("uncited_count cannot exceed candidate_count")
        return self


class KnowledgeFactFingerprint(BaseModel):
    """The D45 state of one relation or observation candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["relation", "observation"]
    fact_id: UUID
    valid_from: UTCDateTime | None = None
    valid_until: UTCDateTime | None = None
    invalidated_at: UTCDateTime | None = None
    evidence_count: int = Field(ge=0)
    contradict_count: int = Field(ge=0)
    contradiction_group: UUID | None = None


class KnowledgeClaimFingerprint(BaseModel):
    """Stable D54 claim grain: document lineage plus chunk content, never claim ID."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lineage_id: UUID
    chunk_content_hash: str


class KnowledgeRuleConfiguration(BaseModel):
    """The hash-visible configuration of one active page rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: UUID
    kind: KnowledgeRuleKind
    params: dict[str, JsonValue]


class KnowledgeInputSnapshot(BaseModel):
    """Every deterministic input that decides whether a compiled page is stale."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: tuple[KnowledgeFactFingerprint, ...] = ()
    claims: tuple[KnowledgeClaimFingerprint, ...] = ()
    rules: tuple[KnowledgeRuleConfiguration, ...] = ()
    curation_hash: str | None = None
    child_summary_hashes: tuple[str, ...] = ()
    shared_model_summary_hash: str | None = None
    writer_version: str


class KnowledgeCompileContext(BaseModel):
    """Git/model inputs supplied to the Postgres-owned manifest computation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    curation_hash: str | None = None
    shared_model_summary_hash: str | None = None
    writer_version: str


class KnowledgeCompileArtifact(BaseModel):
    """One compiled artifact as seen by the dependency scheduler."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    deployment_id: UUID
    scope_id: UUID | None = None
    parent_artifact_id: UUID | None = None
    git_path: str
    artifact_kind: str | None = None
    page_summary: str | None = None
    stale: bool

    @field_validator("git_path")
    @classmethod
    def require_safe_markdown_path(cls, value: str) -> str:
        """Keep driver-owned writes relative, normalized, and Markdown-only."""
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or ".." in path.parts
            or str(path) != value
            or path.suffix != ".md"
        ):
            raise ValueError("git_path must be a normalized relative Markdown path")
        return value


class KnowledgePageCompileRequest(BaseModel):
    """Deterministic context passed to the future per-page compiler seam."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact: KnowledgeCompileArtifact
    child_summaries: dict[UUID, str] = Field(default_factory=dict)
    shared_model_summary: str | None = None


class KnowledgePageCompileOutput(BaseModel):
    """Structured page output consumed and validated by the commit driver."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    compilation: KnowledgeCompilationWrite
    markdown: str


class KnowledgePendingCycle(BaseModel):
    """One recoverable publish batch whose Postgres finalize step is pending."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: UUID
    deployment_id: UUID
    compilations: tuple[KnowledgeCompilationWrite, ...] = Field(min_length=1)


class KnowledgeCommitCycleResult(BaseModel):
    """Observable outcome of one locked checkout/compile/publish cycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checkout_revision: str
    published_revision: str | None = None
    compiled_artifact_ids: tuple[UUID, ...] = ()
    recovered_cycle_ids: tuple[UUID, ...] = ()


class KnowledgeEvidenceDelta(BaseModel):
    """Fact/document/community identifiers changed since the previous K cycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation_ids: tuple[UUID, ...] = ()
    observation_ids: tuple[UUID, ...] = ()
    claim_ids: tuple[UUID, ...] = ()
    doc_ids: tuple[UUID, ...] = ()
    community_ids: tuple[UUID, ...] = ()


class KnowledgeArtifactHash(BaseModel):
    """One artifact's recorded and freshly computed staleness keys."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    recorded_hash: str | None
    computed_hash: str
