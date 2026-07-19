"""Agent-facing surfaces: the query API (API/CLI/MCP are the complete story)."""

from ultimate_memory.surfaces.cli import main as cli_main
from ultimate_memory.surfaces.graph_queries import GraphQueries
from ultimate_memory.surfaces.http_api import build_api
from ultimate_memory.surfaces.query_engine import QueryEngine
from ultimate_memory.surfaces.recipe_executor import RecipeExecutionError
from ultimate_memory.surfaces.recipe_executor import RecipeExecutor

__all__ = (
    "GraphQueries",
    "QueryEngine",
    "RecipeExecutionError",
    "RecipeExecutor",
    "build_api",
    "cli_main",
)
