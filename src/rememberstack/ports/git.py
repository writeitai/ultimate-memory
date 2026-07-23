"""D45/D61 remote interaction used by the single-writer Plane-K driver."""

from pathlib import Path
from typing import Protocol
from typing import runtime_checkable

from rememberstack.model import KRevision


@runtime_checkable
class KGitRemotePort(Protocol):
    """Checkout and publish driver-owned Plane-K commits through one remote."""

    def checkout(self, *, destination: Path) -> KRevision:
        """Create the driver's working checkout and return its current revision."""
        ...

    def publish(self, *, worktree: Path) -> KRevision:
        """Publish the commit prepared by the K driver and return its revision."""
        ...
