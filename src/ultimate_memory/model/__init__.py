"""Shared provider-boundary values with no dependency on other application layers."""

from ultimate_memory.model.auth import AuthenticatedContext
from ultimate_memory.model.auth import PerimeterCredential
from ultimate_memory.model.blocks import Block
from ultimate_memory.model.blocks import BlockType
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
from ultimate_memory.model.claims import SelectionCandidate
from ultimate_memory.model.claims import SelectionResponse
from ultimate_memory.model.claims import SelectionVerdict
from ultimate_memory.model.component_version import ComponentVersionConflictError
from ultimate_memory.model.component_version import ComponentVersionError
from ultimate_memory.model.component_version import ComponentVersionNotFoundError
from ultimate_memory.model.component_version import ComponentVersionRecord
from ultimate_memory.model.component_version import PipelineComponent
from ultimate_memory.model.component_version import RegisterComponentVersionInput
from ultimate_memory.model.component_version import RegisterComponentVersionResult
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
from ultimate_memory.model.documents import StructureSource
from ultimate_memory.model.documents import SyntheticRootRecord
from ultimate_memory.model.documents import UploadRecord
from ultimate_memory.model.evaluation import CanaryCase
from ultimate_memory.model.evaluation import CaseFailure
from ultimate_memory.model.evaluation import EvalSuite
from ultimate_memory.model.evaluation import SuiteReport
from ultimate_memory.model.git import KRevision
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
from ultimate_memory.model.relations import ClaimForNormalization
from ultimate_memory.model.relations import EntityRef
from ultimate_memory.model.relations import NormalizationResponse
from ultimate_memory.model.relations import ObservationCandidate
from ultimate_memory.model.relations import RelationCandidate
from ultimate_memory.model.relations import ResolvedEntity
from ultimate_memory.model.telemetry import TelemetryAttribute
from ultimate_memory.model.telemetry import TelemetryEvent

__all__ = (
    "AddedContext",
    "AuthenticatedContext",
    "Block",
    "BlockType",
    "CanaryCase",
    "CandidateClaim",
    "CaseFailure",
    "ChunkForEmbedding",
    "ChunkRecord",
    "ChunkSource",
    "ChunkSourceNotFoundError",
    "ClaimForEmbedding",
    "ClaimForNormalization",
    "ClaimRecord",
    "ClaimedWork",
    "ClaimifyResponse",
    "ComponentVersionConflictError",
    "ComponentVersionError",
    "ComponentVersionNotFoundError",
    "ComponentVersionRecord",
    "ContextPrefix",
    "ConversionError",
    "ConversionResult",
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
    "EntityRef",
    "EvalSuite",
    "FactForLabeling",
    "FactLabelResponse",
    "HandlerAlreadyRegisteredError",
    "IngestedVersion",
    "KRevision",
    "LaneRouteError",
    "ModelRequest",
    "NonRetryableHandlerError",
    "NormalizationResponse",
    "ObjectAlreadyExistsError",
    "ObjectKey",
    "ObjectKeyEscapesRootError",
    "ObservationCandidate",
    "ObservationForEmbedding",
    "P1ChunkRow",
    "P1ClaimRow",
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
    "RecordCall",
    "RegisterComponentVersionInput",
    "RegisterComponentVersionResult",
    "RelationCandidate",
    "RepresentationNotFoundError",
    "RepresentationRecord",
    "ResolvedEntity",
    "RunResultOutcome",
    "SectionSpan",
    "SelectionCandidate",
    "SelectionResponse",
    "SelectionVerdict",
    "StructureSource",
    "StructuredResponseModel",
    "SuiteReport",
    "SyntheticRootRecord",
    "TelemetryAttribute",
    "TelemetryEvent",
    "UTCDateTime",
    "UnknownStageHandlerError",
    "UnroutableMimeError",
    "UploadRecord",
    "WorkLedgerError",
    "WorkNotFoundError",
    "WorkNotRunningError",
)
