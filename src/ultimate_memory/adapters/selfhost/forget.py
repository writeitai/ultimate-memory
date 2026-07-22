"""Dedicated append-only local store for portable D74 forget intent."""

import os
from pathlib import Path
from uuid import UUID
from uuid import uuid4

from ultimate_memory.model import ForgetManifest
from ultimate_memory.model import ForgetManifestConflictError


class LocalFSForgetManifestStore:
    """Persist content-free manifests outside the ordinary data restore root."""

    def __init__(self, *, root: Path) -> None:
        """Bind an explicitly provisioned manifest root; absence is unsafe."""
        self._root = root.resolve(strict=True)
        if not self._root.is_dir():
            raise NotADirectoryError(self._root)

    def append(self, *, manifest: ForgetManifest) -> None:
        """Atomically append exact canonical bytes, idempotent by ``forget_id``."""
        content = manifest.canonical_bytes()
        destination = self._path(forget_id=manifest.forget_id)
        temporary = self._root / f".{manifest.forget_id}.{uuid4()}.tmp"
        try:
            with temporary.open(mode="xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if destination.read_bytes() != content:
                    raise ForgetManifestConflictError(
                        f"forget_id {manifest.forget_id} already has different bytes"
                    ) from None
            else:
                self._sync_root()
        finally:
            temporary.unlink(missing_ok=True)

    def manifests(self, *, deployment_id: UUID) -> tuple[ForgetManifest, ...]:
        """Enumerate and validate this deployment's manifests by forget identity."""
        result: list[ForgetManifest] = []
        for path in sorted(self._root.glob("*.json")):
            manifest = ForgetManifest.model_validate_json(path.read_bytes())
            if path.stem != str(manifest.forget_id):
                raise ForgetManifestConflictError(
                    f"manifest filename {path.name!r} disagrees with its forget_id"
                )
            if manifest.deployment_id == deployment_id:
                result.append(manifest)
        return tuple(result)

    def _path(self, *, forget_id: UUID) -> Path:
        """Return the fixed UUID-only destination for one immutable manifest."""
        return self._root / f"{forget_id}.json"

    def _sync_root(self) -> None:
        """Make the newly linked directory entry durable before acknowledging append."""
        descriptor = os.open(self._root, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
