"""The recipe surface (retrieval §7): one rendering of the registry for all.

The API, CLI, and MCP surfaces must expose the SAME recipes — "the MCP tool
list renders from the recipe registry; the CLI mirrors the API 1:1" — so the
rendering and dispatch live here, once, and each surface is a thin transport
over it. That is how parity is a property, not a promise: there is a single
place that turns a registry row into a callable tool.

Two responsibilities:

- **Render** each active recipe as a `ToolDescriptor` — name, description,
  and a real JSON-Schema `input_schema` built from the recipe's typed
  parameters (this is what an MCP `tools/list` returns, and what the API
  advertises at `/recipes`).
- **Run** a recipe by name: coerce the caller's string-ish arguments to the
  types the primitives need (a uuid string to a UUID, an ISO instant to a
  datetime), then hand them to the `RecipeExecutor`. Coercion is the surface's
  job precisely because every transport delivers arguments as text.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict

from ultimate_memory.model import Envelope
from ultimate_memory.model import Recipe
from ultimate_memory.spine.recipes import RecipeRegistry
from ultimate_memory.surfaces.recipe_executor import RecipeExecutor


class UnknownRecipeError(Exception):
    """A recipe name the registry has no active row for."""


class MissingArgumentError(Exception):
    """A required recipe parameter the caller did not supply."""


class ToolDescriptor(BaseModel):
    """One recipe rendered as a callable tool (the MCP `tools/list` entry).

    `input_schema` is a JSON-Schema object describing the recipe's typed
    parameters — the same schema the MCP client validates against and the API
    advertises. `output_grain` and `answer_intent` travel too, so a caller
    can see what KIND of answer a tool returns before calling it (D49/D50).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    input_schema: dict[str, object]
    output_grain: str
    answer_intent: str


# How a recipe's declared parameter type renders into JSON Schema, and how a
# transport's text argument coerces back to what the primitives expect.
_TYPE_SCHEMA: dict[str, dict[str, object]] = {
    "uuid": {"type": "string", "format": "uuid"},
    "string": {"type": "string"},
    "integer": {"type": "integer"},
    "timestamp": {"type": "string", "format": "date-time"},
}


def _coerce_uuid(value: object) -> UUID:
    """Coerce a transport argument to a UUID."""
    return value if isinstance(value, UUID) else UUID(str(value))


def _coerce_timestamp(value: object) -> datetime:
    """Coerce a transport argument to a datetime (ISO 8601)."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


_COERCERS: dict[str, Any] = {
    "uuid": _coerce_uuid,
    "string": str,
    "integer": int,
    "timestamp": _coerce_timestamp,
}


class RecipeSurface:
    """Render and run the deployment's recipes — the shared surface logic."""

    def __init__(
        self, *, registry: RecipeRegistry, executor: RecipeExecutor, deployment_id: UUID
    ) -> None:
        """Bind the surface to the registry, the executor, and the deployment."""
        self._registry = registry
        self._executor = executor
        self._deployment_id = deployment_id

    def descriptors(self) -> tuple[ToolDescriptor, ...]:
        """Every active recipe as a callable tool descriptor (the tool list)."""
        return tuple(
            _descriptor(recipe)
            for recipe in self._registry.active(deployment_id=self._deployment_id)
        )

    def run(self, *, name: str, arguments: dict[str, object]) -> Envelope:
        """Run one recipe by name over coerced arguments (UnknownRecipeError
        if no active row exists; MissingArgumentError if a required parameter
        is absent)."""
        recipe = self._registry.by_name(deployment_id=self._deployment_id, name=name)
        if recipe is None:
            raise UnknownRecipeError(name)
        return self._executor.execute(
            deployment_id=self._deployment_id,
            recipe=recipe,
            arguments=_coerce_arguments(recipe=recipe, arguments=arguments),
        )


def _descriptor(recipe: Recipe) -> ToolDescriptor:
    """Render one recipe as a JSON-Schema-carrying tool descriptor."""
    properties: dict[str, object] = {}
    required: list[str] = []
    for name, spec in recipe.parameters.items():
        declared = spec if isinstance(spec, dict) else {}
        properties[name] = dict(
            _TYPE_SCHEMA.get(str(declared.get("type")), {"type": "string"})
        )
        if declared.get("required"):
            required.append(name)
    schema: dict[str, object] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return ToolDescriptor(
        name=recipe.name,
        description=recipe.description,
        input_schema=schema,
        output_grain=recipe.output_grain.value,
        answer_intent=recipe.answer_intent.value,
    )


def _coerce_arguments(
    *, recipe: Recipe, arguments: dict[str, object]
) -> dict[str, object]:
    """Coerce transport arguments to the types the primitives expect.

    Only declared parameters are passed through; a required parameter that is
    absent (or explicitly null) is a MissingArgumentError, never a silent
    default that would change the answer's meaning.
    """
    coerced: dict[str, object] = {}
    for name, spec in recipe.parameters.items():
        declared = spec if isinstance(spec, dict) else {}
        value = arguments.get(name)
        if value is None:
            if declared.get("required"):
                raise MissingArgumentError(
                    f"recipe {recipe.name!r} requires argument {name!r}"
                )
            continue
        coerce = _COERCERS.get(str(declared.get("type")), str)
        coerced[name] = coerce(value)
    return coerced
