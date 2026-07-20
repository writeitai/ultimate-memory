"""Agent-facing surfaces: the query API (API/CLI/MCP are the complete story)."""

from ultimate_memory.surfaces.cli import main as cli_main
from ultimate_memory.surfaces.consumption_skill import ConsumptionSkillSurface
from ultimate_memory.surfaces.graph_queries import GraphQueries
from ultimate_memory.surfaces.http_api import build_api
from ultimate_memory.surfaces.mcp import RecipeMcpServer
from ultimate_memory.surfaces.query_engine import QueryEngine
from ultimate_memory.surfaces.recipe_executor import EXECUTABLE_OPS
from ultimate_memory.surfaces.recipe_executor import RecipeExecutionError
from ultimate_memory.surfaces.recipe_executor import RecipeExecutor
from ultimate_memory.surfaces.recipe_surface import InvalidArgumentError
from ultimate_memory.surfaces.recipe_surface import MissingArgumentError
from ultimate_memory.surfaces.recipe_surface import RecipeSurface
from ultimate_memory.surfaces.recipe_surface import ToolDescriptor
from ultimate_memory.surfaces.recipe_surface import UnknownRecipeError

__all__ = (
    "EXECUTABLE_OPS",
    "ConsumptionSkillSurface",
    "GraphQueries",
    "InvalidArgumentError",
    "MissingArgumentError",
    "QueryEngine",
    "RecipeExecutionError",
    "RecipeExecutor",
    "RecipeMcpServer",
    "RecipeSurface",
    "ToolDescriptor",
    "UnknownRecipeError",
    "build_api",
    "cli_main",
)
