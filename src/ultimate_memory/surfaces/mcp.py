"""The MCP surface (retrieval §7, D50): the tool list IS the recipe registry.

An MCP client discovers tools with `tools/list` and invokes one with
`tools/call`. Here both render straight off the recipe registry through the
shared `RecipeSurface`: every active recipe is a tool, and calling it runs the
recipe's chain. Adding a query pattern is adding a registry row — the tool
list updates with no code change, exactly as the design requires.

This class is the protocol *logic* — the two method results, shaped as MCP
expects. A deployment profile wraps it in a stdio (or SSE) JSON-RPC loop; the
transport is plumbing, and keeping it out of here lets the rendering and
dispatch be tested directly against the registry.
"""

from ultimate_memory.surfaces.recipe_surface import MissingArgumentError
from ultimate_memory.surfaces.recipe_surface import RecipeSurface
from ultimate_memory.surfaces.recipe_surface import UnknownRecipeError


class RecipeMcpServer:
    """Render and dispatch the recipe registry as MCP tools."""

    def __init__(self, *, surface: RecipeSurface) -> None:
        """Bind the MCP server to the shared recipe surface."""
        self._surface = surface

    def list_tools(self) -> dict[str, object]:
        """The `tools/list` result: one MCP tool per active recipe.

        Each tool carries its name, description, and JSON-Schema
        `inputSchema` — the recipe registry rendered verbatim, so the tool
        list an agent sees is always exactly the registry's active rows.
        """
        return {
            "tools": [
                {
                    "name": descriptor.name,
                    "description": descriptor.description,
                    "inputSchema": descriptor.input_schema,
                }
                for descriptor in self._surface.descriptors()
            ]
        }

    def call_tool(
        self, *, name: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        """The `tools/call` result: run the recipe, return its envelope as text.

        The answer is the D49 envelope serialized to JSON in one text content
        block. An unknown tool or a missing required argument is a protocol
        error result (`isError`), not an exception across the wire — the
        client re-plans against a stated failure.
        """
        try:
            envelope = self._surface.run(name=name, arguments=arguments)
        except (UnknownRecipeError, MissingArgumentError) as error:
            return {"content": [{"type": "text", "text": str(error)}], "isError": True}
        return {
            "content": [{"type": "text", "text": envelope.model_dump_json()}],
            "isError": False,
        }
