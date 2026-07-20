"""Public dependency-light client API."""

from ultimate_memory.model.client import ConnectorCreate
from ultimate_memory.model.client import ConnectorDescriptor
from ultimate_memory.model.client import ConnectorNotFoundError
from ultimate_memory.model.client import ToolDescriptor
from ultimate_memory.surfaces.sdk import ClientSettings
from ultimate_memory.surfaces.sdk import MemoryApiError
from ultimate_memory.surfaces.sdk import MemoryClient

__all__ = (
    "ClientSettings",
    "ConnectorCreate",
    "ConnectorDescriptor",
    "ConnectorNotFoundError",
    "MemoryApiError",
    "MemoryClient",
    "ToolDescriptor",
)
