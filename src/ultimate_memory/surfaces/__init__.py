"""Agent-facing surfaces: the query API (API/CLI/MCP are the complete story)."""

from ultimate_memory.surfaces.http_api import build_api
from ultimate_memory.surfaces.query_engine import QueryEngine

__all__ = ("QueryEngine", "build_api")
