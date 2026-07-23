"""D74 durable intent boundary for portable hard-forget manifests."""

from typing import Protocol
from typing import runtime_checkable
from uuid import UUID

from rememberstack.model import ForgetManifest


@runtime_checkable
class ForgetManifestPort(Protocol):
    """Append and enumerate immutable intent outside the protected restore set."""

    def append(self, *, manifest: ForgetManifest) -> None:
        """Durably append one manifest; identical bytes are idempotent."""
        ...

    def manifests(self, *, deployment_id: UUID) -> tuple[ForgetManifest, ...]:
        """Return every manifest for a deployment in deterministic order."""
        ...
