"""The test-tier task queue: records announcements in memory, delivers nothing."""

from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict

from ultimate_memory.model import QueueRoute
from ultimate_memory.model import UTCDateTime


class RecordedAnnouncement(BaseModel):
    """One announce call as the port received it, for assertions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    processing_id: UUID
    route_snapshot: QueueRoute
    not_before_snapshot: UTCDateTime


class RecordingTaskQueue:
    """Satisfies the task-queue port; tests assert on the recorded announcements."""

    def __init__(self) -> None:
        """Start with an empty announcement log."""
        self.announcements: list[RecordedAnnouncement] = []

    def announce(
        self,
        *,
        processing_id: UUID,
        route_snapshot: QueueRoute,
        not_before_snapshot: UTCDateTime,
    ) -> None:
        """Record the announcement; delivery is the test's job, if any."""
        self.announcements.append(
            RecordedAnnouncement(
                processing_id=processing_id,
                route_snapshot=route_snapshot,
                not_before_snapshot=not_before_snapshot,
            )
        )
