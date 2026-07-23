"""Focused request-admission and crash-recovery tests for D74."""

from datetime import datetime
from datetime import timezone
from typing import cast
from uuid import UUID

import pytest

from rememberstack.model import EnqueueOutcome
from rememberstack.model import ForgetInProgressError
from rememberstack.model import ForgetManifest
from rememberstack.model import ForgetManifestRecord
from rememberstack.model import ForgetManifestStatus
from rememberstack.model import ForgetRedactionRequiredError
from rememberstack.spine import ForgetCatalog
from rememberstack.workers import HardForgetService

_DEPLOYMENT_ID = UUID("74000000-0000-0000-0000-000000000001")
_DOC_ID = UUID("74000000-0000-0000-0000-000000000002")
_FORGET_ID = UUID("74000000-0000-0000-0000-000000000003")
_NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _manifest() -> ForgetManifest:
    return ForgetManifest(
        forget_id=_FORGET_ID,
        deployment_id=_DEPLOYMENT_ID,
        doc_id=_DOC_ID,
        requested_at=_NOW,
    )


def _progress(
    *,
    manifest: ForgetManifest | None = None,
    status: ForgetManifestStatus = ForgetManifestStatus.PREPARING,
) -> ForgetManifestRecord:
    return ForgetManifestRecord(
        forget_id=_FORGET_ID,
        deployment_id=_DEPLOYMENT_ID,
        doc_id=_DOC_ID,
        manifest=manifest,
        manifest_hash=manifest.sha256() if manifest is not None else None,
        status=status,
        prepared_at=_NOW,
        accepted_at=_NOW if status is not ForgetManifestStatus.PREPARING else None,
        completed_at=_NOW if status is ForgetManifestStatus.COMPLETE else None,
        last_verified_at=None,
    )


class FakeCatalog:
    """Small stateful fake exposing the service's straight-line decisions."""

    def __init__(
        self,
        *,
        existing: ForgetManifestRecord | None = None,
        prepared: ForgetManifestRecord | None = None,
        drained: bool = True,
    ) -> None:
        self.existing = existing
        self.prepared = prepared or _progress()
        self.drained = drained
        self.events: list[str] = []

    def record_for_doc(
        self, *, deployment_id: UUID, doc_id: UUID
    ) -> ForgetManifestRecord | None:
        self.events.append("lookup")
        return self.existing

    def prepare(
        self, *, deployment_id: UUID, doc_id: UUID, forget_id: UUID
    ) -> ForgetManifestRecord:
        self.events.append("prepare")
        return self.prepared

    def ordinary_work_is_drained(self, *, deployment_id: UUID) -> bool:
        self.events.append("drain")
        return self.drained

    def cancel_unstored_preparation(
        self, *, deployment_id: UUID, forget_id: UUID
    ) -> bool:
        self.events.append("cancel")
        return True

    def inventory_and_store_manifest(
        self,
        *,
        deployment_id: UUID,
        doc_id: UUID,
        forget_id: UUID,
        requested_at: datetime,
    ) -> ForgetManifest:
        self.events.append("store-local")
        return _manifest()

    def accept_and_enqueue(self, *, manifest: ForgetManifest) -> EnqueueOutcome:
        self.events.append("accept-and-enqueue")
        return EnqueueOutcome(
            processing_id=_FORGET_ID, created=True, promoted_to_steady=False
        )


class FakeManifestStore:
    """Record the portable append position in the service sequence."""

    def __init__(self, *, events: list[str]) -> None:
        self.events = events

    def append(self, *, manifest: ForgetManifest) -> None:
        self.events.append("append-portable")

    def manifests(self, *, deployment_id: UUID) -> tuple[ForgetManifest, ...]:
        return ()


class FakeKGit:
    """Return configured owner-redaction blockers without editing content."""

    def __init__(self, *, blockers: tuple[tuple[str, ...], ...] = ()) -> None:
        self.blockers = list(blockers)
        self.calls = 0

    def blocking_redaction_paths(
        self, *, deployment_id: UUID, doc_id: UUID
    ) -> tuple[str, ...]:
        self.calls += 1
        return self.blockers.pop(0) if self.blockers else ()

    def purge_artifacts(
        self, *, deployment_id: UUID, forget_id: UUID, artifact_ids: tuple[UUID, ...]
    ) -> None:
        raise AssertionError("request admission must not purge K")

    def verify_artifacts_purged(
        self, *, deployment_id: UUID, forget_id: UUID, artifact_ids: tuple[UUID, ...]
    ) -> None:
        raise AssertionError("request admission must not verify K purge")


def _service(*, catalog: FakeCatalog, k_git: FakeKGit) -> HardForgetService:
    return HardForgetService(
        catalog=cast(ForgetCatalog, catalog),
        manifest_store=FakeManifestStore(events=catalog.events),
        k_git=k_git,
    )


def test_owner_redaction_blocks_before_admission_changes() -> None:
    """Report exact paths without creating a preparing barrier."""
    catalog = FakeCatalog()
    service = _service(catalog=catalog, k_git=FakeKGit(blockers=(("K2/private.md",),)))

    with pytest.raises(ForgetRedactionRequiredError) as raised:
        service.request(
            deployment_id=_DEPLOYMENT_ID,
            doc_id=_DOC_ID,
            forget_id=_FORGET_ID,
            requested_at=_NOW,
        )

    assert raised.value.paths == ("K2/private.md",)
    assert catalog.events == ["lookup"]


def test_request_waits_fail_closed_for_running_ordinary_work() -> None:
    """Keep preparing admission closed while already-running work drains."""
    catalog = FakeCatalog(drained=False)
    service = _service(catalog=catalog, k_git=FakeKGit())

    with pytest.raises(ForgetInProgressError):
        service.request(
            deployment_id=_DEPLOYMENT_ID,
            doc_id=_DOC_ID,
            forget_id=_FORGET_ID,
            requested_at=_NOW,
        )

    assert catalog.events == ["lookup", "prepare", "drain"]


def test_second_preflight_reopens_only_an_unstored_preparation() -> None:
    """Cancel safely when owner content changes before any manifest append attempt."""
    catalog = FakeCatalog()
    service = _service(
        catalog=catalog, k_git=FakeKGit(blockers=((), ("K1/curation.yaml",)))
    )

    with pytest.raises(ForgetRedactionRequiredError):
        service.request(
            deployment_id=_DEPLOYMENT_ID,
            doc_id=_DOC_ID,
            forget_id=_FORGET_ID,
            requested_at=_NOW,
        )

    assert catalog.events == ["lookup", "prepare", "drain", "cancel"]


def test_manifest_is_local_then_portable_before_accept_and_enqueue() -> None:
    """Preserve the crash-safe ordering of the acceptance cut."""
    catalog = FakeCatalog()
    service = _service(catalog=catalog, k_git=FakeKGit())

    result = service.request(
        deployment_id=_DEPLOYMENT_ID,
        doc_id=_DOC_ID,
        forget_id=_FORGET_ID,
        requested_at=_NOW,
    )

    assert result == _manifest()
    assert catalog.events == [
        "lookup",
        "prepare",
        "drain",
        "store-local",
        "append-portable",
        "accept-and-enqueue",
    ]


def test_stored_preparing_retry_reuses_exact_bytes_without_cancelling() -> None:
    """Recover an ambiguous append crash through an idempotent exact retry."""
    manifest = _manifest()
    progress = _progress(manifest=manifest)
    catalog = FakeCatalog(existing=progress, prepared=progress)
    k_git = FakeKGit(blockers=(("late-owner-change.md",),))
    service = _service(catalog=catalog, k_git=k_git)

    result = service.request(
        deployment_id=_DEPLOYMENT_ID,
        doc_id=_DOC_ID,
        forget_id=_FORGET_ID,
        requested_at=_NOW,
    )

    assert result == manifest
    assert k_git.calls == 0
    assert catalog.events == [
        "lookup",
        "prepare",
        "append-portable",
        "accept-and-enqueue",
    ]
