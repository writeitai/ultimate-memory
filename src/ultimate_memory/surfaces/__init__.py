"""Agent-facing surfaces, imported lazily to keep the client wheel light."""

from __future__ import annotations

from importlib import import_module
from typing import Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ultimate_memory.model.client import ToolDescriptor as ToolDescriptor
    from ultimate_memory.surfaces.cli import main as cli_main  # noqa: F401
    from ultimate_memory.surfaces.consumption_skill import (
        ConsumptionSkillSurface as ConsumptionSkillSurface,
    )
    from ultimate_memory.surfaces.graph_queries import GraphQueries as GraphQueries
    from ultimate_memory.surfaces.http_api import build_api as build_api
    from ultimate_memory.surfaces.mcp import RecipeMcpServer as RecipeMcpServer
    from ultimate_memory.surfaces.query_engine import QueryEngine as QueryEngine
    from ultimate_memory.surfaces.recipe_executor import (
        EXECUTABLE_OPS as EXECUTABLE_OPS,
    )
    from ultimate_memory.surfaces.recipe_executor import (
        RecipeExecutionError as RecipeExecutionError,
    )
    from ultimate_memory.surfaces.recipe_executor import (
        RecipeExecutor as RecipeExecutor,
    )
    from ultimate_memory.surfaces.recipe_surface import (
        InvalidArgumentError as InvalidArgumentError,
    )
    from ultimate_memory.surfaces.recipe_surface import (
        MissingArgumentError as MissingArgumentError,
    )
    from ultimate_memory.surfaces.recipe_surface import RecipeSurface as RecipeSurface
    from ultimate_memory.surfaces.recipe_surface import (
        UnknownRecipeError as UnknownRecipeError,
    )
    from ultimate_memory.surfaces.remote_mcp import (
        RemoteRecipeMcpServer as RemoteRecipeMcpServer,
    )
    from ultimate_memory.surfaces.remote_mcp import serve_mcp_stdio as serve_mcp_stdio
    from ultimate_memory.surfaces.sdk import MemoryApiError as MemoryApiError
    from ultimate_memory.surfaces.sdk import MemoryClient as MemoryClient

_EXPORTS = {
    "EXECUTABLE_OPS": ("ultimate_memory.surfaces.recipe_executor", "EXECUTABLE_OPS"),
    "ConsumptionSkillSurface": (
        "ultimate_memory.surfaces.consumption_skill",
        "ConsumptionSkillSurface",
    ),
    "GraphQueries": ("ultimate_memory.surfaces.graph_queries", "GraphQueries"),
    "InvalidArgumentError": (
        "ultimate_memory.surfaces.recipe_surface",
        "InvalidArgumentError",
    ),
    "MemoryApiError": ("ultimate_memory.surfaces.sdk", "MemoryApiError"),
    "MemoryClient": ("ultimate_memory.surfaces.sdk", "MemoryClient"),
    "MissingArgumentError": (
        "ultimate_memory.surfaces.recipe_surface",
        "MissingArgumentError",
    ),
    "QueryEngine": ("ultimate_memory.surfaces.query_engine", "QueryEngine"),
    "RecipeExecutionError": (
        "ultimate_memory.surfaces.recipe_executor",
        "RecipeExecutionError",
    ),
    "RecipeExecutor": ("ultimate_memory.surfaces.recipe_executor", "RecipeExecutor"),
    "RecipeMcpServer": ("ultimate_memory.surfaces.mcp", "RecipeMcpServer"),
    "RecipeSurface": ("ultimate_memory.surfaces.recipe_surface", "RecipeSurface"),
    "RemoteRecipeMcpServer": (
        "ultimate_memory.surfaces.remote_mcp",
        "RemoteRecipeMcpServer",
    ),
    "ToolDescriptor": ("ultimate_memory.model.client", "ToolDescriptor"),
    "UnknownRecipeError": (
        "ultimate_memory.surfaces.recipe_surface",
        "UnknownRecipeError",
    ),
    "build_api": ("ultimate_memory.surfaces.http_api", "build_api"),
    "cli_main": ("ultimate_memory.surfaces.cli", "main"),
    "serve_mcp_stdio": ("ultimate_memory.surfaces.remote_mcp", "serve_mcp_stdio"),
}

__all__ = (
    "EXECUTABLE_OPS",
    "ConsumptionSkillSurface",
    "GraphQueries",
    "InvalidArgumentError",
    "MemoryApiError",
    "MemoryClient",
    "MissingArgumentError",
    "QueryEngine",
    "RecipeExecutionError",
    "RecipeExecutor",
    "RecipeMcpServer",
    "RecipeSurface",
    "RemoteRecipeMcpServer",
    "ToolDescriptor",
    "UnknownRecipeError",
    "build_api",
    "cli_main",
    "serve_mcp_stdio",
)


def __getattr__(name: str) -> Any:
    """Load each surface only when callers request it."""
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
