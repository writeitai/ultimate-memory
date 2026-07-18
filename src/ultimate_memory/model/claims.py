"""E2 claim-extraction values: call responses, grounding, and ledger records (D31-D35)."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

_NonEmpty = Annotated[str, Field(min_length=1)]


class SelectionVerdict(StrEnum):
    """Selection's per-candidate outcome (D31/D35)."""

    KEEP = "keep"
    KEEP_FLAGGED = "keep_flagged"
    DROP = "drop"


class SelectionCandidate(BaseModel):
    """One proposition Selection judged inside the target chunk."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_span: _NonEmpty
    verdict: SelectionVerdict
    drop_reason: str | None = None
    protected_class: str | None = None


class SelectionResponse(BaseModel):
    """The Selection call's structured output: every judged candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[SelectionCandidate, ...]


class AddedContext(BaseModel):
    """One substring decontextualization added, tagged with its bundle source (D32)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: _NonEmpty
    source_kind: _NonEmpty  # header | neighbour | prefix | hint
    source_ref: str | None = None


class CandidateClaim(BaseModel):
    """One decontextualized, decomposed claim before the deterministic gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_text: _NonEmpty
    source_span: _NonEmpty
    added_context: tuple[AddedContext, ...] = ()
    entailment_self_verdict: bool
    is_attributed: bool = False


class ClaimifyResponse(BaseModel):
    """The fused call's structured output: decontextualize + decompose + ground."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claims: tuple[CandidateClaim, ...]


class ClaimRecord(BaseModel):
    """One accepted claim row: past the deterministic grounding gate (D32)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: UUID
    deployment_id: UUID
    doc_id: UUID
    chunk_id: UUID
    section_id: UUID | None
    claim_text: _NonEmpty
    source_span: _NonEmpty
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    added_context: tuple[AddedContext, ...]
    is_attributed: bool
    entailment_self_verdict: bool
    kept_flagged: bool
    extractor_version: _NonEmpty


class DecisionType(StrEnum):
    """The D33 ledger's decision kinds."""

    SELECTION_DROP = "selection_drop"
    SELECTION_KEEP_FLAGGED = "selection_keep_flagged"
    DECONTEXT_EDIT = "decontext_edit"


class DecisionRecord(BaseModel):
    """One append-only extraction-transcript row (D33)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: UUID
    deployment_id: UUID
    doc_id: UUID
    chunk_id: UUID
    claim_id: UUID | None
    decision_type: DecisionType
    source_span: str | None
    reason: str | None
    edit_detail: dict[str, object] | None
    protected_class: str | None
    extractor_version: _NonEmpty


class ClaimForEmbedding(BaseModel):
    """One claim row as the claim-embed stage loads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: UUID
    doc_id: UUID
    chunk_id: UUID
    claim_text: _NonEmpty
    is_current_testimony: bool
    is_attributed: bool


class FactForLabeling(BaseModel):
    """One relation as the label stage loads it (names resolved for the label)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation_id: UUID
    subject_name: _NonEmpty
    predicate: _NonEmpty
    object_name: _NonEmpty
    status: _NonEmpty


class ObservationForEmbedding(BaseModel):
    """One observation as the label stage loads it (obs_label is the text)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: UUID
    obs_label: _NonEmpty
    status: _NonEmpty


class FactLabelResponse(BaseModel):
    """The fact-labeler call's structured output: one readable sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: _NonEmpty
