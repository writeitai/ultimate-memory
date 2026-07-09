"""ultimate-memory: a layered, scale-oriented memory system for AI agents.

"ultimate-memory" is the working title; the public name is decided before release
(see questions.md #11a).
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

try:
    __version__ = version("ultimate-memory")
except PackageNotFoundError:  # running from a checkout without installation
    __version__ = "0.0.0+uninstalled"
