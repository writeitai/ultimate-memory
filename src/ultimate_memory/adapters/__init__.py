"""Provider adapter package."""

from ultimate_memory.adapters.codex_writer import CodexAgentAdapterSettings
from ultimate_memory.adapters.codex_writer import CodexCLIAgentAdapter
from ultimate_memory.adapters.codex_writer import CodexCLIWriterAdapter
from ultimate_memory.adapters.codex_writer import CodexWriterAdapterSettings
from ultimate_memory.adapters.markitdown_converter import MARKITDOWN_CONVERTER_VERSION
from ultimate_memory.adapters.markitdown_converter import MarkitdownConverter
from ultimate_memory.adapters.openrouter import OpenRouterModelProvider
from ultimate_memory.adapters.openrouter import OpenRouterProviderError
from ultimate_memory.adapters.openrouter import OpenRouterSettings

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
