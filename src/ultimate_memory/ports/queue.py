"""D67 delivery-only announcement seam over committed Postgres work truth."""

from typing import Protocol
from typing import runtime_checkable
from uuid import UUID

from ultimate_memory.model import QueueRoute
from ultimate_memory.model import UTCDateTime


@runtime_checkable
class TaskQueuePort(Protocol):
    """Announce an existing row using non-authoritative route and due snapshots."""

    def announce(
        self,
        *,
        processing_id: UUID,
        route_snapshot: QueueRoute,
        not_before_snapshot: UTCDateTime,
    ) -> None:
        """Schedule at-least-once delivery without creating or mutating work state."""
        ...
