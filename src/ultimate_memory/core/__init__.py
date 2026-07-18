"""Pure domain logic package."""

from ultimate_memory.core.core_manifest import CORE_MANIFEST
from ultimate_memory.core.core_manifest import CoreManifest
from ultimate_memory.core.core_manifest import EntityTypeDefinition
from ultimate_memory.core.core_manifest import PredicateDefinition
from ultimate_memory.core.core_manifest import PredicateSignatureDefinition

__all__ = (
    "CORE_MANIFEST",
    "CoreManifest",
    "EntityTypeDefinition",
    "PredicateDefinition",
    "PredicateSignatureDefinition",
    "BLOCKIZER_VERSION",
    "block_hash",
    "blockize",
)
from ultimate_memory.core.blockizer import block_hash
from ultimate_memory.core.blockizer import blockize
from ultimate_memory.core.blockizer import BLOCKIZER_VERSION
