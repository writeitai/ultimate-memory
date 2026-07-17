"""D50/D60 auth-perimeter seam for a single-deployment trust domain."""

from typing import Protocol
from typing import runtime_checkable

from ultimate_memory.model import AuthenticatedContext
from ultimate_memory.model import PerimeterCredential


@runtime_checkable
class AuthPerimeterPort(Protocol):
    """Authenticate perimeter credentials without introducing internal tenancy."""

    def authenticate(self, *, credential: PerimeterCredential) -> AuthenticatedContext:
        """Return the authenticated principal and its one deployment context."""
        ...
