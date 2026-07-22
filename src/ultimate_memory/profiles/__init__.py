"""Explicit composition root package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ultimate_memory.profiles.selfhost import SelfHostProfile
    from ultimate_memory.profiles.selfhost import SelfHostSettings

__all__ = ("SelfHostProfile", "SelfHostSettings")


def __getattr__(name: str) -> object:
    """Load a profile only when its explicit composition root is requested."""
    if name == "SelfHostProfile":
        from ultimate_memory.profiles.selfhost import SelfHostProfile

        return SelfHostProfile
    if name == "SelfHostSettings":
        from ultimate_memory.profiles.selfhost import SelfHostSettings

        return SelfHostSettings
    raise AttributeError(name)
