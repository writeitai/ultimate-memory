"""Provider adapter package."""

from typing import TYPE_CHECKING

from ultimate_memory.adapters.codex_writer import CodexAgentAdapterSettings
from ultimate_memory.adapters.codex_writer import CodexCLIAgentAdapter
from ultimate_memory.adapters.codex_writer import CodexCLIWriterAdapter
from ultimate_memory.adapters.codex_writer import CodexWriterAdapterSettings
from ultimate_memory.adapters.openrouter import OpenRouterModelProvider
from ultimate_memory.adapters.openrouter import OpenRouterProviderError
from ultimate_memory.adapters.openrouter import OpenRouterSettings

if TYPE_CHECKING:
    from ultimate_memory.adapters.markitdown_converter import (
        MARKITDOWN_CONVERTER_VERSION,
    )
    from ultimate_memory.adapters.markitdown_converter import MarkitdownConverter

__all__ = (
    "CodexCLIAgentAdapter",
    "CodexCLIWriterAdapter",
    "CodexAgentAdapterSettings",
    "CodexWriterAdapterSettings",
    "MARKITDOWN_CONVERTER_VERSION",
    "MarkitdownConverter",
    "OpenRouterModelProvider",
    "OpenRouterProviderError",
    "OpenRouterSettings",
)


def __getattr__(name: str) -> object:
    """Load the media converter only for processes that actually compose it."""
    if name == "MARKITDOWN_CONVERTER_VERSION":
        from ultimate_memory.adapters.markitdown_converter import (
            MARKITDOWN_CONVERTER_VERSION,
        )

        return MARKITDOWN_CONVERTER_VERSION
    if name == "MarkitdownConverter":
        from ultimate_memory.adapters.markitdown_converter import MarkitdownConverter

        return MarkitdownConverter
    raise AttributeError(name)
