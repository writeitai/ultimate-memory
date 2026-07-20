"""Shared provider-boundary values with no dependency on other application layers."""

from ultimate_memory.model.adjudication import ObservationOutcome
from ultimate_memory.model.adjudication import ObservationVerdict
from ultimate_memory.model.adjudication import RelationUpsert
from ultimate_memory.model.adjudication import ReviewDecisionError
from ultimate_memory.model.adjudication import ReviewItem
from ultimate_memory.model.adjudication import SupersessionOutcome
from ultimate_memory.model.adjudication import SupersessionVerdict
from ultimate_memory.model.adjudication import TranscriptEntry
from ultimate_memory.model.auth import AuthenticatedContext
from ultimate_memory.model.auth import PerimeterCredential
from ultimate_memory.model.blocks import Block
from ultimate_memory.model.blocks import BlockType
from ultimate_memory.model.chunks import CarryForwardSource
from ultimate_memory.model.chunks import ChunkForEmbedding
from ultimate_memory.model.chunks import ChunkRecord
from ultimate_memory.model.chunks import ChunkSource
from ultimate_memory.model.chunks import ChunkSourceNotFoundError
from ultimate_memory.model.chunks import ContextPrefix
from ultimate_memory.model.chunks import EmbeddingUpdate
from ultimate_memory.model.chunks import P1ChunkRow
from ultimate_memory.model.chunks import P1ClaimRow
from ultimate_memory.model.chunks import P1FactRow
from ultimate_memory.model.chunks import PackedChunk
from ultimate_memory.model.chunks import SectionSpan
from ultimate_memory.model.claims import AddedContext
from ultimate_memory.model.claims import CandidateClaim
from ultimate_memory.model.claims import ClaimForEmbedding
from ultimate_memory.model.claims import ClaimifyResponse
from ultimate_memory.model.claims import ClaimRecord
from ultimate_memory.model.claims import DecisionRecord
from ultimate_memory.model.claims import DecisionType
from ultimate_memory.model.claims import FactForLabeling
from ultimate_memory.model.claims import FactLabelResponse
from ultimate_memory.model.claims import ObservationForEmbedding
from ultimate_memory.model.claims import OtherPredicateGrammarError
from ultimate_memory.model.claims import SelectionCandidate
from ultimate_memory.model.claims import SelectionResponse
from ultimate_memory.model.claims import SelectionVerdict
from ultimate_memory.model.client import ConnectorCreate
from ultimate_memory.model.client import ConnectorDescriptor
from ultimate_memory.model.client import ConnectorNotFoundError
from ultimate_memory.model.client import ToolDescriptor
from ultimate_memory.model.clustering import ClusterConfig
from ultimate_memory.model.clustering import MergeProposal
from ultimate_memory.model.clustering import NeighborhoodReport
from ultimate_memory.model.clustering import UnmergeError
from ultimate_memory.model.component_version import ComponentVersionConflictError
from ultimate_memory.model.component_version import ComponentVersionError
from ultimate_memory.model.component_version import ComponentVersionNotFoundError
from ultimate_memory.model.component_version import ComponentVersionRecord
from ultimate_memory.model.component_version import PipelineComponent
from ultimate_memory.model.component_version import RegisterComponentVersionInput
from ultimate_memory.model.component_version import RegisterComponentVersionResult
from ultimate_memory.model.consumption import ConsumptionDeployment
from ultimate_memory.model.consumption import ConsumptionRecipe
from ultimate_memory.model.consumption import ConsumptionScope
from ultimate_memory.model.consumption import ConsumptionSkillContext
from ultimate_memory.model.consumption import RenderedConsumptionSkill
from ultimate_memory.model.consumption import S58Answer
from ultimate_memory.model.conversion import ConversionError
from ultimate_memory.model.conversion import ConversionResult
from ultimate_memory.model.conversion import UnroutableMimeError
from ultimate_memory.model.deployment import CoreManifestConflictError
from ultimate_memory.model.deployment import DeploymentBootstrapConflictError
from ultimate_memory.model.deployment import DeploymentBootstrapInput
from ultimate_memory.model.deployment import DeploymentBootstrapResult
from ultimate_memory.model.deployment import DeploymentConflictError
from ultimate_memory.model.documents import ConvertSource
from ultimate_memory.model.documents import DocumentUpload
from ultimate_memory.model.documents import DocumentVersionNotFoundError
from ultimate_memory.model.documents import IngestedVersion
from ultimate_memory.model.documents import RepresentationNotFoundError
from ultimate_memory.model.documents import RepresentationRecord
from ultimate_memory.model.documents import SourceItem
from ultimate_memory.model.documents import StructureSource
from ultimate_memory.model.documents import SyncCycleSummary
from ultimate_memory.model.documents import SyntheticRootRecord
from ultimate_memory.model.documents import UploadRecord
from ultimate_memory.model.envelope import AggregateBucket
from ultimate_memory.model.envelope import AggregateReport
from ultimate_memory.model.envelope import ChangeRecord
from ultimate_memory.model.envelope import CoMember
from ultimate_memory.model.envelope import Contradiction
from ultimate_memory.model.envelope import EntityCandidate
from ultimate_memory.model.envelope import Envelope
from ultimate_memory.model.envelope import EnvelopePart
from ultimate_memory.model.envelope import EvidenceResult
from ultimate_memory.model.envelope import FactResult
from ultimate_memory.model.envelope import FactSupport
from ultimate_memory.model.envelope import Freshness
from ultimate_memory.model.envelope import Grain
from ultimate_memory.model.envelope import GraphEdge
from ultimate_memory.model.envelope import GraphNode
from ultimate_memory.model.envelope import GraphPath
from ultimate_memory.model.envelope import IdentityRegime
from ultimate_memory.model.envelope import KFreshness
from ultimate_memory.model.envelope import Negative
from ultimate_memory.model.envelope import NegativeKind
from ultimate_memory.model.envelope import PageRef
from ultimate_memory.model.envelope import RankedItem
from ultimate_memory.model.envelope import ScanRow
from ultimate_memory.model.envelope import SourceRecord
from ultimate_memory.model.envelope import Truncation
from ultimate_memory.model.envelope import Validity
from ultimate_memory.model.evaluation import CanaryCase
from ultimate_memory.model.evaluation import CaseFailure
from ultimate_memory.model.evaluation import EvalSuite
from ultimate_memory.model.evaluation import LifecycleReport
from ultimate_memory.model.evaluation import SuiteReport
from ultimate_memory.model.git import KRevision
from ultimate_memory.model.knowledge import CommunityRuleParams
from ultimate_memory.model.knowledge import DocSetRuleParams
from ultimate_memory.model.knowledge import EntityRuleParams
from ultimate_memory.model.knowledge import EntitySubtreeRuleParams
from ultimate_memory.model.knowledge import KnowledgeArtifactCreate
from ultimate_memory.model.knowledge import KnowledgeArtifactHash
from ultimate_memory.model.knowledge import KnowledgeCandidateLayer
from ultimate_memory.model.knowledge import KnowledgeCitation
from ultimate_memory.model.knowledge import KnowledgeClaimFingerprint
from ultimate_memory.model.knowledge import KnowledgeCommitCycleResult
from ultimate_memory.model.knowledge import KnowledgeCompilationWrite
from ultimate_memory.model.knowledge import KnowledgeCompileArtifact
from ultimate_memory.model.knowledge import KnowledgeCompileContext
from ultimate_memory.model.knowledge import KnowledgeEvidenceDelta
from ultimate_memory.model.knowledge import KnowledgeEvidenceRole
from ultimate_memory.model.knowledge import KnowledgeEvidenceTarget
from ultimate_memory.model.knowledge import KnowledgeFactFingerprint
from ultimate_memory.model.knowledge import KnowledgeFactSheetFact
from ultimate_memory.model.knowledge import KnowledgeFactSheetSnapshot
from ultimate_memory.model.knowledge import KnowledgeInputSnapshot
from ultimate_memory.model.knowledge import KnowledgeLayer
from ultimate_memory.model.knowledge import KnowledgePageCompileOutput
from ultimate_memory.model.knowledge import KnowledgePageCompileRequest
from ultimate_memory.model.knowledge import KnowledgePageKind
from ultimate_memory.model.knowledge import KnowledgePageRuleCreate
from ultimate_memory.model.knowledge import KnowledgePendingCycle
from ultimate_memory.model.knowledge import KnowledgePlanAction
from ultimate_memory.model.knowledge import KnowledgePlanDecisionCreate
from ultimate_memory.model.knowledge import KnowledgePlanStatus
from ultimate_memory.model.knowledge import KnowledgePlanTrigger
from ultimate_memory.model.knowledge import KnowledgeRenderedFactSheet
from ultimate_memory.model.knowledge import KnowledgeRuleConfiguration
from ultimate_memory.model.knowledge import KnowledgeRuleKey
from ultimate_memory.model.knowledge import KnowledgeRuleKeyKind
from ultimate_memory.model.knowledge import KnowledgeRuleKind
from ultimate_memory.model.knowledge import KnowledgeRuleParams
from ultimate_memory.model.knowledge import ManualRuleParams
from ultimate_memory.model.knowledge import PredicateBeatRuleParams
from ultimate_memory.model.knowledge import ScopeInterestsRuleParams
from ultimate_memory.model.lifecycle import CurrencyTransition
from ultimate_memory.model.lifecycle import ReconciliationDelta
from ultimate_memory.model.model_provider import EmbeddingRequest
from ultimate_memory.model.model_provider import EmbeddingResponse
from ultimate_memory.model.model_provider import ModelRequest
from ultimate_memory.model.model_provider import StructuredResponseModel
from ultimate_memory.model.mounts import PublishedMounts
from ultimate_memory.model.object_store import ObjectAlreadyExistsError
from ultimate_memory.model.object_store import ObjectKey
from ultimate_memory.model.object_store import ObjectKeyEscapesRootError
from ultimate_memory.model.processing import ClaimedWork
from ultimate_memory.model.processing import DeferReason
from ultimate_memory.model.processing import EnqueueOutcome
from ultimate_memory.model.processing import EnqueueWork
from ultimate_memory.model.processing import HandlerAlreadyRegisteredError
from ultimate_memory.model.processing import LaneRouteError
from ultimate_memory.model.processing import NonRetryableHandlerError
from ultimate_memory.model.processing import ProcessingStatus
from ultimate_memory.model.processing import ProcessingTarget
from ultimate_memory.model.processing import RecordCall
from ultimate_memory.model.processing import RunResultOutcome
from ultimate_memory.model.processing import UnknownStageHandlerError
from ultimate_memory.model.processing import WorkLedgerError
from ultimate_memory.model.processing import WorkNotFoundError
from ultimate_memory.model.processing import WorkNotRunningError
from ultimate_memory.model.queue import PipelineStage
from ultimate_memory.model.queue import ProcessingLane
from ultimate_memory.model.queue import QueueRoute
from ultimate_memory.model.queue import UTCDateTime
from ultimate_memory.model.recipes import Recipe
from ultimate_memory.model.recipes import RecipeAnswerIntent
from ultimate_memory.model.recipes import RecipeStep
from ultimate_memory.model.relations import ClaimForNormalization
from ultimate_memory.model.relations import EntityRef
from ultimate_memory.model.relations import NormalizationResponse
from ultimate_memory.model.relations import ObservationCandidate
from ultimate_memory.model.relations import RelationCandidate
from ultimate_memory.model.relations import ResolvedEntity
from ultimate_memory.model.resolution import AdjudicationVerdict
from ultimate_memory.model.resolution import P1EntityRow
from ultimate_memory.model.resolution import ResolutionCandidate
from ultimate_memory.model.resolution import ResolverConfig
from ultimate_memory.model.resolution import TypeThresholds
from ultimate_memory.model.retrieval_spikes import RETRIEVAL_SPIKE_NAMES
from ultimate_memory.model.retrieval_spikes import RetrievalSpikeMeasurement
from ultimate_memory.model.retrieval_spikes import RetrievalSpikeName
from ultimate_memory.model.retrieval_spikes import RetrievalSpikeReport
from ultimate_memory.model.sections import PersistedSectionTree
from ultimate_memory.model.sections import ProposedSection
from ultimate_memory.model.sections import SectionTreeRecord
from ultimate_memory.model.sections import SnappedSection
from ultimate_memory.model.sections import StructureResponse
from ultimate_memory.model.telemetry import TelemetryAttribute
from ultimate_memory.model.telemetry import TelemetryEvent

__all__ = (
    "AddedContext",
    "AdjudicationVerdict",
    "AggregateBucket",
    "AggregateReport",
    "AuthenticatedContext",
    "Block",
    "BlockType",
    "CanaryCase",
    "CandidateClaim",
    "CaseFailure",
    "CarryForwardSource",
    "ChangeRecord",
    "CoMember",
    "Contradiction",
    "ChunkForEmbedding",
    "ChunkRecord",
    "ChunkSource",
    "ChunkSourceNotFoundError",
    "ClaimForEmbedding",
    "ClaimForNormalization",
    "ClaimRecord",
    "ClaimedWork",
    "ClaimifyResponse",
    "ClusterConfig",
    "ComponentVersionConflictError",
    "ComponentVersionError",
    "ComponentVersionNotFoundError",
    "ComponentVersionRecord",
    "ConnectorCreate",
    "ConnectorDescriptor",
    "ConnectorNotFoundError",
    "ContextPrefix",
    "ConversionError",
    "ConversionResult",
    "ConsumptionDeployment",
    "ConsumptionRecipe",
    "ConsumptionScope",
    "ConsumptionSkillContext",
    "ConvertSource",
    "CoreManifestConflictError",
    "DecisionRecord",
    "DecisionType",
    "DeferReason",
    "DeploymentBootstrapConflictError",
    "DeploymentBootstrapInput",
    "DeploymentBootstrapResult",
    "DeploymentConflictError",
    "DocumentUpload",
    "DocumentVersionNotFoundError",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "EmbeddingUpdate",
    "EnqueueOutcome",
    "EnqueueWork",
    "EntityCandidate",
    "EnvelopePart",
    "EntityRef",
    "Envelope",
    "GraphEdge",
    "GraphNode",
    "GraphPath",
    "Truncation",
    "EvalSuite",
    "EvidenceResult",
    "FactForLabeling",
    "FactLabelResponse",
    "FactResult",
    "FactSupport",
    "Freshness",
    "Grain",
    "IdentityRegime",
    "KFreshness",
    "HandlerAlreadyRegisteredError",
    "IngestedVersion",
    "KRevision",
    "LaneRouteError",
    "MergeProposal",
    "ModelRequest",
    "Negative",
    "NegativeKind",
    "NeighborhoodReport",
    "NonRetryableHandlerError",
    "NormalizationResponse",
    "ObjectAlreadyExistsError",
    "ObjectKey",
    "ObjectKeyEscapesRootError",
    "ObservationCandidate",
    "ObservationForEmbedding",
    "ObservationOutcome",
    "ObservationVerdict",
    "OtherPredicateGrammarError",
    "P1ChunkRow",
    "P1ClaimRow",
    "P1EntityRow",
    "P1FactRow",
    "PackedChunk",
    "PerimeterCredential",
    "PipelineComponent",
    "PipelineStage",
    "ProcessingLane",
    "ProcessingStatus",
    "ProcessingTarget",
    "PublishedMounts",
    "QueueRoute",
    "PageRef",
    "RankedItem",
    "Recipe",
    "RecipeAnswerIntent",
    "RecipeStep",
    "RecordCall",
    "RegisterComponentVersionInput",
    "RegisterComponentVersionResult",
    "RelationCandidate",
    "RelationUpsert",
    "RepresentationNotFoundError",
    "RepresentationRecord",
    "RenderedConsumptionSkill",
    "ResolutionCandidate",
    "ResolvedEntity",
    "ResolverConfig",
    "RETRIEVAL_SPIKE_NAMES",
    "RetrievalSpikeMeasurement",
    "RetrievalSpikeName",
    "RetrievalSpikeReport",
    "ReviewDecisionError",
    "ReviewItem",
    "RunResultOutcome",
    "ScanRow",
    "S58Answer",
    "SectionSpan",
    "SelectionCandidate",
    "SelectionResponse",
    "SelectionVerdict",
    "LifecycleReport",
    "CurrencyTransition",
    "CommunityRuleParams",
    "DocSetRuleParams",
    "EntityRuleParams",
    "EntitySubtreeRuleParams",
    "KnowledgeArtifactCreate",
    "KnowledgeArtifactHash",
    "KnowledgeCandidateLayer",
    "KnowledgeCitation",
    "KnowledgeClaimFingerprint",
    "KnowledgeCommitCycleResult",
    "KnowledgeCompilationWrite",
    "KnowledgeCompileArtifact",
    "KnowledgeCompileContext",
    "KnowledgeEvidenceDelta",
    "KnowledgeEvidenceTarget",
    "KnowledgeEvidenceRole",
    "KnowledgeFactFingerprint",
    "KnowledgeFactSheetFact",
    "KnowledgeFactSheetSnapshot",
    "KnowledgeInputSnapshot",
    "KnowledgeLayer",
    "KnowledgePageKind",
    "KnowledgePageCompileOutput",
    "KnowledgePageCompileRequest",
    "KnowledgePageRuleCreate",
    "KnowledgePendingCycle",
    "KnowledgePlanAction",
    "KnowledgePlanDecisionCreate",
    "KnowledgePlanStatus",
    "KnowledgePlanTrigger",
    "KnowledgeRuleConfiguration",
    "KnowledgeRuleKey",
    "KnowledgeRuleKeyKind",
    "KnowledgeRuleKind",
    "KnowledgeRuleParams",
    "KnowledgeRenderedFactSheet",
    "ManualRuleParams",
    "PredicateBeatRuleParams",
    "ReconciliationDelta",
    "ScopeInterestsRuleParams",
    "PersistedSectionTree",
    "ProposedSection",
    "SectionTreeRecord",
    "SnappedSection",
    "StructureResponse",
    "SourceItem",
    "SourceRecord",
    "StructureSource",
    "StructuredResponseModel",
    "SuiteReport",
    "SupersessionOutcome",
    "SupersessionVerdict",
    "SyncCycleSummary",
    "SyntheticRootRecord",
    "TelemetryAttribute",
    "TelemetryEvent",
    "ToolDescriptor",
    "TranscriptEntry",
    "TypeThresholds",
    "UTCDateTime",
    "UnknownStageHandlerError",
    "UnmergeError",
    "UnroutableMimeError",
    "UploadRecord",
    "Validity",
    "WorkLedgerError",
    "WorkNotFoundError",
    "WorkNotRunningError",
)
