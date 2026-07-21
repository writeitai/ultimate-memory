"""Self-host composition root for the optional local operational commands."""

from datetime import datetime
from pathlib import Path
from typing import Self
from uuid import UUID

import sqlalchemy
from sqlalchemy.engine import Engine

from ultimate_memory.adapters.selfhost import LocalFSObjectStore
from ultimate_memory.adapters.selfhost import SelfHostTaskQueue
from ultimate_memory.model import DeadLetterReplayResult
from ultimate_memory.model import OperationalReport
from ultimate_memory.model import ProcessingLane
from ultimate_memory.spine import OperationalCatalog
from ultimate_memory.spine import OperationalSettings
from ultimate_memory.spine import ProjectionCatalog
from ultimate_memory.spine import WorkLedger
from ultimate_memory.spine import WorkLedgerSettings
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers import CorpusFsBuilder
from ultimate_memory.workers import DeadLetterReplayer
from ultimate_memory.workers import GraphRebuildWorker


class SelfHostOperations:
    """Compose local adapters around one explicitly owned database engine."""

    def __init__(self, *, engine: Engine) -> None:
        """Take ownership of an engine created for one CLI invocation."""
        self._engine = engine

    @classmethod
    def from_settings(cls) -> Self:
        """Create the local composition from the typed database setting."""
        return cls(
            engine=sqlalchemy.create_engine(load_database_settings().sqlalchemy_url())
        )

    def close(self) -> None:
        """Dispose the command-owned connection pool."""
        self._engine.dispose()

    def inspect(self, *, deployment_id: UUID) -> OperationalReport:
        """Build one bounded typed report."""
        return OperationalCatalog(
            engine=self._engine, settings=OperationalSettings()
        ).inspect(deployment_id=deployment_id)

    def replay(
        self,
        *,
        deployment_id: UUID,
        processing_id: UUID,
        attempt_allowance: int,
        lane: ProcessingLane | None,
        not_before: datetime | None,
    ) -> DeadLetterReplayResult:
        """Compose the authoritative replay transition with local delivery."""
        ledger = WorkLedger(engine=self._engine, settings=WorkLedgerSettings())
        return DeadLetterReplayer(
            ledger=ledger, queue=SelfHostTaskQueue(ledger=ledger)
        ).replay(
            deployment_id=deployment_id,
            processing_id=processing_id,
            attempt_allowance=attempt_allowance,
            lane=lane,
            not_before=not_before,
        )

    def rebuild(
        self,
        *,
        plane: str,
        deployment_id: UUID,
        snapshot_root: Path,
        workdir: Path,
        version: str,
    ) -> dict[str, object]:
        """Invoke the existing whole-rebuild implementation for P2 or P3."""
        catalog = ProjectionCatalog(engine=self._engine)
        store = LocalFSObjectStore(root=snapshot_root)
        if plane == "p2":
            return GraphRebuildWorker(catalog=catalog, snapshot_store=store).rebuild(
                deployment_id=deployment_id, workdir=workdir, version=version
            )
        if plane == "p3":
            return CorpusFsBuilder(catalog=catalog, snapshot_store=store).build(
                deployment_id=deployment_id, version=version
            )
        raise ValueError(f"unknown projection plane {plane!r}")
