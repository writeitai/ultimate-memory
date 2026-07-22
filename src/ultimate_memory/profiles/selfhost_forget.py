"""One explicit self-host composition for D74 hard-forget and readiness."""

from datetime import datetime
from pathlib import Path
from typing import Self
from uuid import UUID

from sqlalchemy.engine import Engine

from ultimate_memory.adapters.selfhost import LanceChunkIndex
from ultimate_memory.adapters.selfhost import LocalFSForgetManifestStore
from ultimate_memory.adapters.selfhost import LocalFSObjectStore
from ultimate_memory.adapters.selfhost import LocalGitRepository
from ultimate_memory.adapters.selfhost import SelfHostProjectionPurger
from ultimate_memory.model import ForgetManifest
from ultimate_memory.model import PipelineStage
from ultimate_memory.spine import ForgetCatalog
from ultimate_memory.spine import LifecycleCatalog
from ultimate_memory.spine import ProjectionCatalog
from ultimate_memory.workers import CorpusFsBuilder
from ultimate_memory.workers import DeletionService
from ultimate_memory.workers import GraphRebuildWorker
from ultimate_memory.workers import HandlerRegistry
from ultimate_memory.workers import HardForgetHandler
from ultimate_memory.workers import HardForgetReadiness
from ultimate_memory.workers import HardForgetService
from ultimate_memory.workers import KnowledgeCommitDriver
from ultimate_memory.workers import KnowledgeCycleForgetRebuilder
from ultimate_memory.workers import ProjectionPairForgetRebuilder


class SelfHostHardForget:
    """The self-host request, worker registration, admission, and startup gate."""

    def __init__(
        self,
        *,
        catalog: ForgetCatalog,
        service: HardForgetService,
        handler: HardForgetHandler,
        readiness: HardForgetReadiness,
    ) -> None:
        """Retain one shared coordinator graph for every self-host surface."""
        self._catalog = catalog
        self._service = service
        self._handler = handler
        self._readiness = readiness

    @classmethod
    def compose(
        cls,
        *,
        engine: Engine,
        manifest_root: Path,
        object_roots: tuple[Path, ...],
        snapshot_root: Path,
        lance_root: Path,
        p2_cache_root: Path,
        mount_root: Path,
        knowledge_repository: Path,
        knowledge_author_name: str,
        knowledge_author_email: str,
        rebuild_workdir: Path,
        knowledge_driver: KnowledgeCommitDriver,
    ) -> Self:
        """Compose only existing production workers and selected self-host stores."""
        if not object_roots:
            raise ValueError("hard-forget requires at least one ordinary object root")
        catalog = ForgetCatalog(engine=engine)
        manifest_store = LocalFSForgetManifestStore(root=manifest_root)
        object_purgers = tuple(LocalFSObjectStore(root=root) for root in object_roots)
        snapshot_store = LocalFSObjectStore(root=snapshot_root)
        projection_catalog = ProjectionCatalog(engine=engine)
        k_git = LocalGitRepository(
            repository=knowledge_repository,
            path_catalog=catalog,
            author_name=knowledge_author_name,
            author_email=knowledge_author_email,
        )
        service = HardForgetService(
            catalog=catalog, manifest_store=manifest_store, k_git=k_git
        )
        handler = HardForgetHandler(
            catalog=catalog,
            deletion=DeletionService(catalog=LifecycleCatalog(engine=engine)),
            object_purgers=object_purgers,
            p1=LanceChunkIndex(root=lance_root),
            projection_rebuilder=ProjectionPairForgetRebuilder(
                graph=GraphRebuildWorker(
                    catalog=projection_catalog, snapshot_store=snapshot_store
                ),
                corpus=CorpusFsBuilder(
                    catalog=projection_catalog, snapshot_store=snapshot_store
                ),
                workdir=rebuild_workdir,
            ),
            projection_purger=SelfHostProjectionPurger(
                object_purger=snapshot_store,
                catalog=projection_catalog,
                p2_cache_root=p2_cache_root,
                mount_root=mount_root,
            ),
            knowledge_rebuilder=KnowledgeCycleForgetRebuilder(driver=knowledge_driver),
            k_git=k_git,
        )
        readiness = HardForgetReadiness(
            catalog=catalog,
            manifest_store=manifest_store,
            request_service=service,
            handler=handler,
        )
        return cls(
            catalog=catalog, service=service, handler=handler, readiness=readiness
        )

    def register(self, *, registry: HandlerRegistry) -> None:
        """Install the one unlaned hard-forget worker handler."""
        registry.register(stage=PipelineStage.HARD_FORGET, handler=self._handler)

    def request(
        self,
        *,
        deployment_id: UUID,
        doc_id: UUID,
        forget_id: UUID,
        requested_at: datetime,
    ) -> ForgetManifest:
        """Submit one lineage request through the crash-safe acceptance cut."""
        return self._service.request(
            deployment_id=deployment_id,
            doc_id=doc_id,
            forget_id=forget_id,
            requested_at=requested_at,
        )

    def ensure_ready(self, *, deployment_id: UUID) -> tuple[UUID, ...]:
        """Re-honor every portable manifest before serving begins."""
        return self._readiness.ensure_ready(deployment_id=deployment_id)

    def assert_available(self, *, deployment_id: UUID) -> None:
        """Implement the shared public/mount admission perimeter."""
        self._catalog.assert_available(deployment_id=deployment_id)

    def guard_ingest(
        self,
        *,
        deployment_id: UUID,
        source_kind: str,
        source_ref: str,
        content_hash: str,
    ) -> None:
        """Implement E0's before-bytes barrier and irreversible ingest guard."""
        self._catalog.guard_ingest(
            deployment_id=deployment_id,
            source_kind=source_kind,
            source_ref=source_ref,
            content_hash=content_hash,
        )
