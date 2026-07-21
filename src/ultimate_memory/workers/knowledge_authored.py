"""Authored checkout synchronization and reliable subscription dispatch delivery."""

from pathlib import Path
from typing import Protocol
from uuid import UUID

from ultimate_memory.core import knowledge_content_hash
from ultimate_memory.core import parse_knowledge_authored_frontmatter
from ultimate_memory.model import ClaimedWork
from ultimate_memory.model import KnowledgeAuthoredPageSync
from ultimate_memory.model import KnowledgeAuthoredSyncResult
from ultimate_memory.model import KnowledgeDispatchStatus
from ultimate_memory.model import KnowledgePageKind
from ultimate_memory.model import KnowledgeWorkflowDelivery
from ultimate_memory.model import NonRetryableHandlerError
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import ProcessingTarget
from ultimate_memory.spine.knowledge import KnowledgeControlPlane
from ultimate_memory.workers.base import HandlerOutcome


class KnowledgeWorkflowDispatcher(Protocol):
    """External workflow-delivery port; consumers are idempotent by dispatch ID."""

    def deliver(self, *, delivery: KnowledgeWorkflowDelivery) -> None:
        """Deliver one delta-carrying authored/subscription notification."""
        ...


class KnowledgeAuthoredSynchronizer:
    """Discover authored Markdown in one exact checkout and sync its declarations."""

    def __init__(self, *, control_plane: KnowledgeControlPlane) -> None:
        """Bind checkout discovery to the authoritative Plane-K control state."""
        self._control_plane = control_plane

    def sync_checkout(
        self, *, deployment_id: UUID, worktree: Path, git_revision: str
    ) -> KnowledgeAuthoredSyncResult:
        """Register new Markdown as authored and resync every known authored body."""
        states = self._control_plane.artifact_path_states(deployment_id=deployment_id)
        bodies = {state.git_path: state for state in states}
        curation_paths = {
            state.curation_path for state in states if state.curation_path is not None
        }
        registered: list[UUID] = []
        synced: list[UUID] = []
        linted: list[UUID] = []
        for target in sorted(worktree.rglob("*.md")):
            relative = target.relative_to(worktree)
            if ".git" in relative.parts:
                continue
            git_path = relative.as_posix()
            state = bodies.get(git_path)
            if git_path in curation_paths or (
                state is not None and state.page_kind is KnowledgePageKind.COMPILED
            ):
                continue
            markdown = target.read_text(encoding="utf-8")
            result = self._control_plane.sync_authored_page(
                sync=KnowledgeAuthoredPageSync(
                    deployment_id=deployment_id,
                    git_path=git_path,
                    markdown=markdown,
                    content_hash=knowledge_content_hash(markdown=markdown),
                    git_revision=git_revision,
                    declaration=parse_knowledge_authored_frontmatter(markdown=markdown),
                )
            )
            if result.registered:
                registered.append(result.artifact_id)
            else:
                synced.append(result.artifact_id)
            if result.lint_flagged:
                linted.append(result.artifact_id)
        return KnowledgeAuthoredSyncResult(
            registered_artifact_ids=tuple(registered),
            synced_artifact_ids=tuple(synced),
            lint_flag_artifact_ids=tuple(linted),
        )


class KnowledgeDispatchHandler:
    """Deliver one D67 knowledge-dispatch target through the external workflow port."""

    def __init__(
        self,
        *,
        control_plane: KnowledgeControlPlane,
        dispatcher: KnowledgeWorkflowDispatcher,
    ) -> None:
        """Bind domain dispatch state to one delivery adapter."""
        self._control_plane = control_plane
        self._dispatcher = dispatcher

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Deliver at least once and keep both delivery/mirror failures visible."""
        if (
            work.target_kind is not ProcessingTarget.KNOWLEDGE_DISPATCH
            or work.stage is not PipelineStage.DISPATCH_KNOWLEDGE
        ):
            raise NonRetryableHandlerError(
                "dispatch handler requires the knowledge_dispatch/dispatch_knowledge route"
            )
        record = self._control_plane.begin_dispatch(dispatch_id=work.target_id)
        if record.status is KnowledgeDispatchStatus.DONE:
            return HandlerOutcome()
        delivery = KnowledgeWorkflowDelivery(
            dispatch_id=record.dispatch_id,
            workflow_endpoint=record.workflow_endpoint,
            payload=record.payload,
        )
        try:
            self._dispatcher.deliver(delivery=delivery)
        except Exception as delivery_error:
            try:
                self._control_plane.fail_dispatch(dispatch_id=record.dispatch_id)
            except Exception as mirror_error:
                raise ExceptionGroup(
                    "workflow delivery and dispatch failure-mirror both failed",
                    [delivery_error, mirror_error],
                ) from delivery_error
            raise
        self._control_plane.complete_dispatch(dispatch_id=record.dispatch_id)
        return HandlerOutcome()
