"""The response envelope (D49): the answer's machine-readable self-account.

Every query-engine result carries its grain, validity, freshness stamps, the
nominate-then-drop honesty count (D48), and — when the answer is a "no" — a
typed negative from the fixed taxonomy (retrieval §5). The walking skeleton
carries the minimal envelope; the full contract grows on these same fields.
"""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from ultimate_memory.model.adjudication import TranscriptEntry
from ultimate_memory.model.queue import UTCDateTime


class Grain(StrEnum):
    """The D49 grain type-system: what kind of truth a result is."""

    FACT = "fact"
    EVIDENCE = "evidence"
    COMPILED = "compiled"
    COMPOSITE = "composite"


class NegativeKind(StrEnum):
    """The fixed negative-answer taxonomy (S29/S39/S55)."""

    UNKNOWN_ENTITY = "unknown_entity"
    KNOWN_EMPTY = "known_empty"
    BOUNDARY = "boundary"


class Negative(BaseModel):
    """One typed 'no': each kind demands a different agent reaction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: NegativeKind
    explanation: Annotated[str, Field(min_length=1)]
    workaround: str | None = None


class Validity(BaseModel):
    """A result's bi-temporal state as hydration re-read it (D48)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    valid_from: UTCDateTime | None
    valid_until: UTCDateTime | None
    ingested_at: UTCDateTime
    invalidated_at: UTCDateTime | None


class Freshness(BaseModel):
    """Per-source freshness stamps (S42): what lag the answer could carry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pg_live_ts: UTCDateTime
    p1_written_inline: bool = True  # the skeleton writes P1 inline; a real
    # write-lag horizon replaces this constant with measurement (retrieval §5)
    p2_snapshot_version: str | None = None  # which graph snapshot answered
    p2_snapshot_ts: UTCDateTime | None = None


class EntityCandidate(BaseModel):
    """One ranked resolve candidate (never a silent guess, S51)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: UUID
    canonical_name: str
    type: str
    tier: str  # which resolution tier surfaced it (T0 in the skeleton)


class FactResult(BaseModel):
    """One fact-grain record: a live relation or observation, hydrated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: UUID
    kind: str  # relation | observation
    label: str
    evidence_count: int
    validity: Validity
    contradiction_group: UUID | None = None  # S23: co-members never silent


class EvidenceResult(BaseModel):
    """One evidence-grain record: a claim with its provenance anchors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: UUID
    doc_id: UUID
    chunk_id: UUID
    claim_text: str
    source_span: str
    char_start: int
    char_end: int
    is_attributed: bool
    is_current_testimony: bool


class SourceRecord(BaseModel):
    """One hydrated source document handle (S5: down to the artifact URI)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: UUID
    title: str | None
    source_kind: str
    markdown_uri: str | None


class GraphNode(BaseModel):
    """One entity the traversal reached, with its hop distance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: UUID
    name: str
    type: str
    hops: int = Field(ge=0)


class GraphEdge(BaseModel):
    """One traversed relation, carrying its bi-temporal state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation_id: UUID
    subject_id: UUID
    object_id: UUID
    predicate: str
    fact: str | None
    evidence_count: int
    valid_from: UTCDateTime | None
    valid_until: UTCDateTime | None
    ingested_at: UTCDateTime | None
    invalidated_at: UTCDateTime | None


class GraphPath(BaseModel):
    """One connection between two entities — a COMPOUND result.

    A path revalidates as a unit (S17/S21): if hydration drops any edge,
    the whole path drops, because a path with a hole is not a shorter
    path — it is a different (and false) claim about connection.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    length: int = Field(ge=1)
    nodes: tuple[GraphNode, ...] = Field(min_length=2)
    edges: tuple[GraphEdge, ...] = Field(min_length=1)


class RankedItem(BaseModel):
    """One item in a fused or reranked ordering (retrieval §3: `fuse`/`rerank`).

    `score` is the operator's output — the RRF sum for `fuse`, the signal
    value for `rerank` — and the tuple order IS the rank. `signals` keeps
    each contributing value visible, because the rerankers are meant to be
    inspectable stages (D9), not a black-box sort.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: UUID
    score: float
    signals: dict[str, float] = Field(default_factory=dict)


class ChangeRecord(BaseModel):
    """One entry in the `delta` change feed (S13/S14/S30).

    `kind` is what changed (relation | observation | claim | page) and
    `change` is how (new | invalidated | capped | recompiled). `at` is the
    instant that placed it in the feed — the ingestion, invalidation, or
    recompilation time the caller's `since` was compared against — so a
    follow-up `delta` can resume from the last `at` it saw.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str  # relation | observation | claim | page
    change: str  # new | invalidated | capped | recompiled
    id: UUID
    label: str | None
    at: UTCDateTime


class AggregateBucket(BaseModel):
    """One group in an enumerated aggregate (retrieval §9): a key and its count.

    `key` is the group label — a predicate, an object entity, a timeline
    period, or an entity id rendered as text — and `null` for the single
    bucket of a plain count. `entity_id` is populated when the group IS an
    entity (group-by-object, delta-top-entities, typed-absence), so the
    agent can hop straight to it without re-resolving the label.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str | None
    count: int = Field(ge=0)
    entity_id: UUID | None = None


class AggregateReport(BaseModel):
    """An enumerated aggregate's result: the form asked, and its buckets.

    Aggregation is enumerated, never general (retrieval §9): each `form`
    is a bounded SQL shape with a predictable cost. `total` is the sum
    across buckets (or the single count); `bounded_by` names the cap when
    the shape rides a bounded feed (e.g. delta-top-entities), so a reader
    knows the ranking is over the window, not all of history.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    form: str
    buckets: tuple[AggregateBucket, ...] = ()
    total: int = Field(ge=0)
    bounded_by: str | None = None


class PageRef(BaseModel):
    """One K page the `pages_about` discovery index reports (S31/S45).

    The rule-key inverted index that routes writes, read backwards: which
    pages exist about an entity or key. `stale` mirrors the refresh state —
    a page whose inputs changed but has not recompiled — so discovery never
    presents an out-of-date page as fresh without saying so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    page_kind: str
    git_path: str | None
    page_summary: str | None
    last_compiled_at: UTCDateTime | None
    status: str
    stale: bool = False


class ScanRow(BaseModel):
    """One row of a `scan` batch export (S53): id, kind, label, feed instant.

    The batch surface streams the same zero-LLM reads as the interactive
    primitives under a separate resource pool (retrieval §9). A row is
    deliberately minimal — id plus enough to route a hydrate — because a
    scan is an export to a compiler or auditor, not a rendered answer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    id: UUID
    label: str | None
    at: UTCDateTime | None = None


class Truncation(BaseModel):
    """The explicit cap marker (S18/S49): no silent top-k ever.

    ``estimated_total`` is what the traversal could see before the cap;
    ``continuation`` carries the opaque cursor a follow-up call passes back.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    truncated: bool
    returned: int = Field(ge=0)
    estimated_total: int = Field(ge=0)
    total_is_exact: bool = True  # false when the count itself hit its cap
    continuation: str | None = None


class Envelope(BaseModel):
    """The minimal D49 envelope: results plus the answer's self-account."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    grain: Grain
    as_of_valid_at: UTCDateTime | None = None  # echo of the applied valid_at
    as_of_believed_at: UTCDateTime | None = None  # echo of the applied believed_at
    entities: tuple[EntityCandidate, ...] = ()
    facts: tuple[FactResult, ...] = ()
    evidence: tuple[EvidenceResult, ...] = ()
    sources: tuple[SourceRecord, ...] = ()
    transcript: tuple["TranscriptEntry", ...] = ()  # S8: the audit surface
    nodes: tuple[GraphNode, ...] = ()  # S18: neighborhood members
    paths: tuple[GraphPath, ...] = ()  # S17/S21: compound connections
    edges: tuple[GraphEdge, ...] = ()  # the traversed relations
    ranking: tuple[RankedItem, ...] = ()  # S46: fused / reranked order
    changes: tuple[ChangeRecord, ...] = ()  # S13/S14/S30: the delta feed
    aggregate: AggregateReport | None = None  # S26–S30/S40: enumerated only
    pages: tuple[PageRef, ...] = ()  # S31/S45: pages_about discovery
    freshness: Freshness
    truncation: Truncation | None = None  # S18/S49: caps are never silent
    dropped_by_hydration: int = 0
    negative: Negative | None = None
