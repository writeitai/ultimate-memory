"""Local-directory mount publisher: the four D51 read-only views as plain paths."""

from pathlib import Path
from uuid import UUID

from ultimate_memory.model import PublishedMounts


class LocalMountPublisher:
    """Publish the P3, artifact, raw, and Plane-K views as local directory trees."""

    def __init__(self, *, root: Path) -> None:
        """Bind the publisher to the directory that holds per-deployment views."""
        self._root = root.resolve()

    def publish(self, *, deployment_id: UUID) -> PublishedMounts:
        """Publish and return the exact four read-only deployment views."""
        base = self._root / str(deployment_id)
        locators = {
            name: base / name for name in ("p3", "artifacts", "raw", "knowledge")
        }
        for path in locators.values():
            path.mkdir(parents=True, exist_ok=True)
        return PublishedMounts(
            deployment_id=deployment_id,
            p3=str(locators["p3"]),
            artifacts=str(locators["artifacts"]),
            raw=str(locators["raw"]),
            knowledge=str(locators["knowledge"]),
            read_only=True,
        )
