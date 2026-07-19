"""Agent-facing surfaces: the query API (API/CLI/MCP are the complete story)."""

from ultimate_memory.surfaces.cli import main as cli_main
from ultimate_memory.surfaces.graph_queries import GraphQueries
from ultimate_memory.surfaces.http_api import build_api
from ultimate_memory.surfaces.query_engine import QueryEngine

__all__ = ("GraphQueries", "QueryEngine", "build_api", "cli_main")
