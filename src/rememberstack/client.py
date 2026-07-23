"""Public dependency-light client API."""

from rememberstack.model.client import ConnectorCreate
from rememberstack.model.client import ConnectorDescriptor
from rememberstack.model.client import ConnectorNotFoundError
from rememberstack.model.client import ToolDescriptor
from rememberstack.surfaces.sdk import ClientSettings
from rememberstack.surfaces.sdk import MemoryApiError
from rememberstack.surfaces.sdk import MemoryClient

__all__ = (
    "ClientSettings",
    "ConnectorCreate",
    "ConnectorDescriptor",
    "ConnectorNotFoundError",
    "MemoryApiError",
    "MemoryClient",
    "ToolDescriptor",
)
