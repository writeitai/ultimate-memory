"""D51/D61 portable publication boundary for four read-only mount views."""

from typing import Protocol
from typing import runtime_checkable
from uuid import UUID

from rememberstack.model import PublishedMounts


@runtime_checkable
class MountPublisherPort(Protocol):
    """Publish P3, artifact, raw, and Plane-K views without mount mechanics."""

    def publish(self, *, deployment_id: UUID) -> PublishedMounts:
        """Publish and return the exact four read-only deployment views."""
        ...
