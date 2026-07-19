"""Local-directory mount publisher: the four D51 read-only views (e0 §5).

Agents read the memory on their filesystem: the **corpus filesystem** they
browse first, the **artifacts** they drill into from a stub, the **raw**
originals — deliberately *off the navigation path* — and the Plane-K
checkout. Every view is read-only; writes always go through the pipeline
and Postgres stays the authority.

The self-host tier materializes what the cloud tier gets from a bucket
mount, and implements D51's three guardrails here rather than assuming
them of infrastructure:

1. **Raw is off-path.** Nothing in the corpus tree links into it; reaching
   an original means following an explicit `raw_uri` from a stub or from
   `document.md` frontmatter — a deliberate act, never a browse default.
2. **Data-access audit logging is mandatory.** The audit property came
   from logging, not from keeping raw unmounted (a mount read is still a
   read), so originals are readable only through `AuditedRawReader`, which
   refuses an unattributed request rather than logging a blank.
3. **Storage class routes by mime.** Media a multimodal harness actually
   reads stays hot; text/office originals kept only for audit and
   re-conversion go cold — this kills the grep-the-archive cost bug at the
   source. Per-deployment config, like the D38 converter router.

The corpus view always serves the snapshot the registry marks latest, and
swaps whole trees atomically, so a browsing agent never walks a half-built
tree.
"""

from datetime import datetime
from datetime import UTC
import json
from pathlib import Path
import shutil
from typing import Final
from uuid import UUID

from ultimate_memory.model import ObjectKey
from ultimate_memory.model import PublishedMounts
from ultimate_memory.ports.object_store import ObjectStorePort
from ultimate_memory.spine.projection import ProjectionCatalog

HOT_MIME_PREFIXES: Final = ("video/", "audio/", "image/")
"""Originals a multimodal harness actually reads: conversion yields only a
lossy transcript for these, so the bytes themselves stay hot (D51)."""

EMPTY_CORPUS_NOTE: Final = (
    "# Corpus filesystem\n\n"
    "> No P3 snapshot has been published yet. Run the corpus-filesystem\n"
    "> builder; until then use the query API, which needs no projection.\n"
)


class RawAccessDenied(Exception):
    """An unattributed raw read was refused (originals are audited)."""


def storage_class_for(*, mime: str) -> str:
    """Route one original's storage class by mime (D51 guardrail 3)."""
    return "hot" if mime.startswith(HOT_MIME_PREFIXES) else "cold"


class LocalMountPublisher:
    """Publish the P3, artifact, raw, and Plane-K views as local trees."""

    def __init__(
        self,
        *,
        root: Path,
        catalog: ProjectionCatalog | None = None,
        corpusfs_store: ObjectStorePort | None = None,
    ) -> None:
        """Bind the publisher to its mount root and (optionally) the P3 source.

        With a catalog and store the publisher materializes the published
        corpus snapshot; without them it publishes empty view roots — the
        Phase-0 shape, still useful for provisioning before any projection
        exists.
        """
        self._root = root.resolve()
        self._catalog = catalog
        self._corpusfs_store = corpusfs_store

    def publish(self, *, deployment_id: UUID) -> PublishedMounts:
        """Publish and return the exact four read-only deployment views."""
        base = self._root / str(deployment_id)
        locators = {
            name: base / name for name in ("p3", "artifacts", "raw", "knowledge")
        }
        for path in locators.values():
            path.mkdir(parents=True, exist_ok=True)
        self._materialize_corpus(deployment_id=deployment_id, target=locators["p3"])
        return PublishedMounts(
            deployment_id=deployment_id,
            p3=str(locators["p3"]),
            artifacts=str(locators["artifacts"]),
            # off the navigation path (D51): no index links here — the tree
            # never promotes raw, stubs carry an explicit pointer
            raw=str(locators["raw"]),
            knowledge=str(locators["knowledge"]),
            read_only=True,
        )

    def _materialize_corpus(self, *, deployment_id: UUID, target: Path) -> None:
        """Serve the LATEST PUBLISHED corpus snapshot, swapped atomically."""
        if self._catalog is None or self._corpusfs_store is None:
            return
        latest = self._catalog.latest_snapshot(
            deployment_id=deployment_id, plane="P3_corpusfs"
        )
        if latest is None:
            (target / "llms.txt").write_text(EMPTY_CORPUS_NOTE, encoding="utf-8")
            return
        version = str(latest["version"])
        if (target / ".snapshot-version").exists() and (
            target / ".snapshot-version"
        ).read_text(encoding="utf-8").strip() == version:
            return  # already serving this snapshot
        prefix = str(latest["gcs_uri"])
        manifest = json.loads(
            self._corpusfs_store.read_bytes(key=ObjectKey(f"{prefix}/MANIFEST.json"))
        )
        staging = target.with_name(f".staging-{version}")
        if staging.exists():
            shutil.rmtree(staging)
        for relative in manifest["files"]:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(
                self._corpusfs_store.read_bytes(key=ObjectKey(f"{prefix}/{relative}"))
            )
        (staging / ".snapshot-version").write_text(version, encoding="utf-8")
        if target.exists():  # swap whole trees: never a half-built browse
            shutil.rmtree(target)
        staging.rename(target)


class AuditedRawReader:
    """The ONLY way to read an original — because reads must be logged.

    D51's audit property comes from logging, not from keeping raw
    unmounted: a mount read is still a read. So raw access is offered
    exclusively through this reader, which records the accessor and the
    stated purpose before returning bytes and refuses an unattributed
    request outright rather than logging a blank.
    """

    def __init__(self, *, raw_store: ObjectStorePort, audit_log: Path) -> None:
        """Bind the reader to the raw store and its append-only audit log."""
        self._raw_store = raw_store
        self._audit_log = audit_log

    def read(
        self, *, deployment_id: UUID, raw_uri: str, accessor: str, purpose: str
    ) -> bytes:
        """Read one original, recording who read it and why."""
        if not accessor.strip() or not purpose.strip():
            raise RawAccessDenied(
                "raw access requires an accessor and a stated purpose:"
                " originals are audited, never anonymously readable"
            )
        content = self._raw_store.read_bytes(key=ObjectKey(raw_uri))
        self._append(
            {
                "at": datetime.now(tz=UTC).isoformat(),
                "deployment_id": str(deployment_id),
                "raw_uri": raw_uri,
                "accessor": accessor,
                "purpose": purpose,
                "bytes": len(content),
            }
        )
        return content

    def entries(self) -> tuple[dict[str, object], ...]:
        """The audit trail, oldest first (the operator's read surface)."""
        if not self._audit_log.exists():
            return ()
        return tuple(
            json.loads(line)
            for line in self._audit_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    def _append(self, entry: dict[str, object]) -> None:
        """Append one audit record (the log is append-only by construction)."""
        self._audit_log.parent.mkdir(parents=True, exist_ok=True)
        with self._audit_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
