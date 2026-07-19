"""The watch loop (lifecycle §2, D55): one recorded poll cycle per pass.

The efficiency ladder's cheapest exits live here: unchanged revision → no
fetch; a file being actively edited coalesces to one ingested version per
stability window (the debounce discipline); identical bytes are the
content-hash no-op downstream. Deletion observations tombstone the lineage
loudly; the cascade is the delete worker's job.
"""

from datetime import datetime
from datetime import timedelta
from datetime import UTC
from typing import Final
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from ultimate_memory.model import DocumentUpload
from ultimate_memory.model import SyncCycleSummary
from ultimate_memory.ports.connector import WatchedSourcePort
from ultimate_memory.spine.sync import SyncCatalog
from ultimate_memory.workers.e0 import UploadIngestor

DEFAULT_VERSIONING_MODE_BY_KIND: Final = {
    # spike 6's starting heuristic: edit-in-place leans living;
    # replace-whole-file and rolling logs lean archival (snapshot)
    "watched_directory": "living",
    "google_drive": "living",
    "upload": "snapshot",
}


class SyncSettings(BaseSettings):
    """The watch loop's knobs (starting points, D22)."""

    model_config = SettingsConfigDict(env_prefix="UGM_SYNC_")

    debounce_quiet_seconds: float = Field(default=120.0, ge=0.0)


class SyncCycleRunner:
    """Run one recorded poll cycle for one (deployment, source kind)."""

    def __init__(
        self, *, catalog: SyncCatalog, ingestor: UploadIngestor, settings: SyncSettings
    ) -> None:
        """Bind the runner to the cycle catalog, ingest path, and settings."""
        self._catalog = catalog
        self._ingestor = ingestor
        self._settings = settings

    def run_cycle(
        self, *, deployment_id: UUID, source_kind: str, source: WatchedSourcePort
    ) -> SyncCycleSummary:
        """One poll pass: observe, debounce, ingest, tombstone, record."""
        known = self._catalog.known_revisions(
            deployment_id=deployment_id, source_kind=source_kind
        )
        cycle_id = self._catalog.open_cycle(
            deployment_id=deployment_id, source_kind=source_kind
        )
        items = source.poll(known=known)
        ingested: list[UUID] = []
        deletions: list[UUID] = []
        unchanged = 0
        debounced = 0
        now = datetime.now(tz=UTC)
        quiet = timedelta(seconds=self._settings.debounce_quiet_seconds)
        versioning_mode = DEFAULT_VERSIONING_MODE_BY_KIND.get(source_kind, "snapshot")
        for item in items:
            if item.deleted:
                lineage = self._catalog.observe_deletion(
                    deployment_id=deployment_id,
                    source_kind=source_kind,
                    source_ref=item.source_ref,
                )
                if lineage is not None:
                    deletions.append(lineage)
                continue
            if known.get(item.source_ref) == item.revision:
                unchanged += 1  # revision no-op: no fetch, no bytes moved
                continue
            if now - item.modified_at < quiet:
                debounced += 1  # actively edited: coalesce to a later cycle
                continue
            content = source.fetch(source_ref=item.source_ref)
            result = self._ingestor.ingest_observed(
                deployment_id=deployment_id,
                source_kind=source_kind,
                source_ref=item.source_ref,
                upload=DocumentUpload(
                    filename=item.filename or item.source_ref,
                    mime=item.mime,
                    content=content,
                ),
                versioning_mode=versioning_mode,
                source_modified_at=item.modified_at,
                source_version_ref=item.revision,
                sync_cycle_id=cycle_id,
            )
            if result.created:
                ingested.append(result.version_id)
            else:
                unchanged += 1  # content-hash no-op (revision churn, same bytes)
        self._catalog.complete_cycle(cycle_id=cycle_id, observed=len(items))
        return SyncCycleSummary(
            cycle_id=cycle_id,
            observed=len(items),
            ingested=tuple(ingested),
            unchanged=unchanged,
            debounced=debounced,
            deletions_observed=tuple(deletions),
        )
