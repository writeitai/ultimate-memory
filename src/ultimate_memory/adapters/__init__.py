"""Provider adapter package."""

from ultimate_memory.adapters.markitdown_converter import MARKITDOWN_CONVERTER_VERSION
from ultimate_memory.adapters.markitdown_converter import MarkitdownConverter
from ultimate_memory.adapters.openrouter import OpenRouterModelProvider
from ultimate_memory.adapters.openrouter import OpenRouterProviderError
from ultimate_memory.adapters.openrouter import OpenRouterSettings

__all__ = (
    "MARKITDOWN_CONVERTER_VERSION",
    "MarkitdownConverter",
    "OpenRouterModelProvider",
    "OpenRouterProviderError",
    "OpenRouterSettings",
)
