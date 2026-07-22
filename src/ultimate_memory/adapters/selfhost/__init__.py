"""Self-host adapters: pg delivery shell, local-FS object store, local mounts (WP-0.4a)."""

from typing import TYPE_CHECKING

from ultimate_memory.adapters.selfhost.forget import LocalFSForgetManifestStore
from ultimate_memory.adapters.selfhost.git import LocalGitRepository
from ultimate_memory.adapters.selfhost.minio import MinIOObjectStore
from ultimate_memory.adapters.selfhost.minio import MinIOSettings
from ultimate_memory.adapters.selfhost.mounts import AuditedRawReader
from ultimate_memory.adapters.selfhost.mounts import LocalMountPublisher
from ultimate_memory.adapters.selfhost.mounts import RawAccessDenied
from ultimate_memory.adapters.selfhost.mounts import storage_class_for
from ultimate_memory.adapters.selfhost.object_store import LocalFSObjectStore
from ultimate_memory.adapters.selfhost.object_store import ObjectAlreadyExistsError
from ultimate_memory.adapters.selfhost.object_store import ObjectKeyEscapesRootError
from ultimate_memory.adapters.selfhost.projection import SelfHostProjectionPurger
from ultimate_memory.adapters.selfhost.queue import SelfHostTaskQueue
from ultimate_memory.adapters.selfhost.queue import SelfHostWorkerLoop
from ultimate_memory.adapters.selfhost.queue import TokenBucket
from ultimate_memory.adapters.selfhost.telemetry import JsonLineTelemetry
from ultimate_memory.adapters.selfhost.watcher import LocalDirectoryWatcher

if TYPE_CHECKING:
    from ultimate_memory.adapters.selfhost.lance import LanceChunkIndex

__all__ = (
    "LanceChunkIndex",
    "LocalFSForgetManifestStore",
    "LocalGitRepository",
    "LocalDirectoryWatcher",
    "JsonLineTelemetry",
    "LocalFSObjectStore",
    "AuditedRawReader",
    "LocalMountPublisher",
    "MinIOObjectStore",
    "MinIOSettings",
    "RawAccessDenied",
    "storage_class_for",
    "ObjectAlreadyExistsError",
    "ObjectKeyEscapesRootError",
    "SelfHostTaskQueue",
    "SelfHostProjectionPurger",
    "SelfHostWorkerLoop",
    "TokenBucket",
)


def __getattr__(name: str) -> object:
    """Load the heavy LanceDB adapter only when a composition actually needs it."""
    if name == "LanceChunkIndex":
        from ultimate_memory.adapters.selfhost.lance import LanceChunkIndex

        return LanceChunkIndex
    raise AttributeError(name)
