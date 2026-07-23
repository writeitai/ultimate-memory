"""Executable self-host composition for the WP-0.4c Compose quickstart."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Self
from typing import TYPE_CHECKING
from uuid import UUID

from alembic import command
from alembic.config import Config
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url

from rememberstack.adapters import OpenRouterModelProvider
from rememberstack.adapters import OpenRouterSettings
from rememberstack.adapters.selfhost import LocalFSForgetManifestStore
from rememberstack.adapters.selfhost import MinIOObjectStore
from rememberstack.adapters.selfhost import MinIOSettings
from rememberstack.model import DeploymentBootstrapInput
from rememberstack.model import PipelineStage
from rememberstack.spine import DeploymentBootstrapper
from rememberstack.spine import RecipeRegistry
from rememberstack.spine import seed_canonical_recipes
from rememberstack.spine.settings import load_database_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

    from rememberstack.adapters.selfhost import SelfHostWorkerLoop

_SUPPORTED_WORKER_STAGES = (PipelineStage.CONVERT, PipelineStage.STRUCTURE)


class SelfHostSettings(BaseSettings):
    """One fresh self-host deployment's profile and process settings."""

    model_config = SettingsConfigDict(
        env_prefix="REMEMBERSTACK_SELFHOST_", extra="ignore"
    )

    deployment_id: UUID
    deployment_slug: str = Field(default="local", min_length=1)
    deployment_name: str = Field(default="Local memory", min_length=1)
    default_language: str = Field(default="en", min_length=1)
    raw_bucket_name: str = Field(default="remember-raw", min_length=1)
    artifacts_bucket_name: str = Field(default="remember-artifacts", min_length=1)
    corpusfs_bucket_name: str = Field(default="remember-corpusfs", min_length=1)
    lance_root: Path = Path("/var/lib/rememberstack/lance")
    forget_manifest_root: Path = Path("/var/lib/rememberstack/forget-manifests")
    migration_config: Path = Path("alembic.ini")
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65_535)
    worker_rate_per_s: float = Field(default=20.0, gt=0)
    worker_burst: float = Field(default=20.0, ge=1)
    worker_fallback_poll_s: float = Field(default=5.0, gt=0)
    worker_session_s: float = Field(default=3_600.0, gt=0)


class _FreshDeploymentReadiness:
    """Fail closed if a fresh quickstart sees portable forget history.

    WP-0.4c establishes a fresh-deployment Compose skeleton. It must never
    silently serve a restored deployment whose D74 manifests require the full
    hard-forget recovery composition; finding any manifest stops startup.
    """

    def __init__(self, *, store: LocalFSForgetManifestStore) -> None:
        """Bind the separately durable manifest root."""
        self._store = store

    def ensure_ready(self, *, deployment_id: UUID) -> tuple[UUID, ...]:
        """Accept an empty root and refuse every non-empty restore."""
        manifests = self._store.manifests(deployment_id=deployment_id)
        if manifests:
            raise RuntimeError(
                "the Compose quickstart found portable hard-forget manifests;"
                " restore requires the complete D74 self-host recovery profile"
            )
        return ()


class SelfHostProfile:
    """Compose the existing API and E0 workers over PostgreSQL, MinIO, and Lance."""

    def __init__(
        self,
        *,
        settings: SelfHostSettings,
        engine: Engine,
        raw_store: MinIOObjectStore,
        artifact_store: MinIOObjectStore,
        corpusfs_store: MinIOObjectStore,
        model_provider: OpenRouterModelProvider,
    ) -> None:
        """Retain one dependency graph for an API, setup, or worker process."""
        self._settings = settings
        self._engine = engine
        self._raw_store = raw_store
        self._artifact_store = artifact_store
        self._corpusfs_store = corpusfs_store
        self._model_provider = model_provider

    @classmethod
    def from_settings(cls) -> Self:
        """Load every external value through its typed settings boundary."""
        profile_settings = SelfHostSettings.model_validate({})
        minio_settings = MinIOSettings.model_validate({})
        return cls(
            settings=profile_settings,
            engine=sqlalchemy.create_engine(
                load_database_settings().sqlalchemy_url(), pool_pre_ping=True
            ),
            raw_store=MinIOObjectStore(
                bucket=profile_settings.raw_bucket_name, settings=minio_settings
            ),
            artifact_store=MinIOObjectStore(
                bucket=profile_settings.artifacts_bucket_name, settings=minio_settings
            ),
            corpusfs_store=MinIOObjectStore(
                bucket=profile_settings.corpusfs_bucket_name, settings=minio_settings
            ),
            model_provider=OpenRouterModelProvider(
                settings=OpenRouterSettings.model_validate({})
            ),
        )

    def close(self) -> None:
        """Dispose this process's explicitly owned database pool."""
        self._engine.dispose()

    def setup(self) -> None:
        """Apply migrations, provision buckets, bootstrap core rows, and seed recipes."""
        migration = Config(str(self._settings.migration_config))
        migration.set_main_option(
            "sqlalchemy.url", load_database_settings().sqlalchemy_url()
        )
        command.upgrade(config=migration, revision="head")
        self._raw_store.ensure_bucket()
        self._artifact_store.ensure_bucket()
        self._corpusfs_store.ensure_bucket()
        self._settings.forget_manifest_root.mkdir(parents=True, exist_ok=True)
        DeploymentBootstrapper(engine=self._engine).bootstrap_deployment(
            deployment_input=DeploymentBootstrapInput(
                deployment_id=self._settings.deployment_id,
                slug=self._settings.deployment_slug,
                name=self._settings.deployment_name,
                default_language=self._settings.default_language,
                raw_bucket=f"s3://{self._settings.raw_bucket_name}",
                artifacts_bucket=f"s3://{self._settings.artifacts_bucket_name}",
                corpusfs_bucket=f"s3://{self._settings.corpusfs_bucket_name}",
            )
        )
        seed_canonical_recipes(
            registry=RecipeRegistry(engine=self._engine),
            deployment_id=self._settings.deployment_id,
        )

    def api(self) -> FastAPI:
        """Build the existing HTTP surface over this self-host dependency graph."""
        from rememberstack.adapters.selfhost.lance import LanceChunkIndex
        from rememberstack.spine import DocumentCatalog
        from rememberstack.spine import ForgetCatalog
        from rememberstack.surfaces import build_api
        from rememberstack.surfaces import QueryEngine
        from rememberstack.surfaces import RecipeExecutor
        from rememberstack.surfaces import RecipeSurface
        from rememberstack.workers.e0 import UploadIngestor

        query_engine = QueryEngine(
            engine=self._engine,
            search_index=LanceChunkIndex(root=self._settings.lance_root),
            model_provider=self._model_provider,
            embedding_model="qwen/qwen3-embedding-8b",
        )
        app = build_api(
            engine=query_engine,
            deployment_id=self._settings.deployment_id,
            admission=ForgetCatalog(engine=self._engine),
            readiness=_FreshDeploymentReadiness(
                store=LocalFSForgetManifestStore(
                    root=self._settings.forget_manifest_root
                )
            ),
            surface=RecipeSurface(
                registry=RecipeRegistry(engine=self._engine),
                executor=RecipeExecutor(query_engine=query_engine),
                deployment_id=self._settings.deployment_id,
            ),
            ingest=UploadIngestor(
                catalog=DocumentCatalog(engine=self._engine),
                raw_store=self._raw_store,
                admission=ForgetCatalog(engine=self._engine),
            ),
        )

        @app.get("/healthz", include_in_schema=False)
        def healthz() -> dict[str, str]:
            """Prove the process can reach its authoritative PostgreSQL spine."""
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
            return {"status": "ok"}

        return app

    def worker_loop(self, *, stage: PipelineStage) -> SelfHostWorkerLoop:
        """Build one E0 route's ordinary LISTEN/NOTIFY worker loop."""
        from rememberstack.adapters.selfhost import SelfHostTaskQueue
        from rememberstack.adapters.selfhost import SelfHostWorkerLoop
        from rememberstack.adapters.selfhost import TokenBucket
        from rememberstack.core import ConversionRouter
        from rememberstack.core import MarkdownPassthroughConverter
        from rememberstack.model import ProcessingLane
        from rememberstack.spine import DocumentCatalog
        from rememberstack.spine import WorkLedger
        from rememberstack.spine import WorkLedgerSettings
        from rememberstack.workers import ConvertHandler
        from rememberstack.workers import HandlerRegistry
        from rememberstack.workers import StructureHandler
        from rememberstack.workers import Worker

        if stage not in _SUPPORTED_WORKER_STAGES:
            raise ValueError(f"the Compose skeleton has no handler for stage {stage}")
        catalog = DocumentCatalog(engine=self._engine)
        registry = HandlerRegistry()
        if stage is PipelineStage.CONVERT:
            registry.register(
                stage=stage,
                handler=ConvertHandler(
                    catalog=catalog,
                    raw_store=self._raw_store,
                    artifact_store=self._artifact_store,
                    router=ConversionRouter(
                        routes={"text/markdown": MarkdownPassthroughConverter()}
                    ),
                ),
            )
        else:
            registry.register(
                stage=stage,
                handler=StructureHandler(
                    catalog=catalog,
                    artifact_store=self._artifact_store,
                    model_provider=self._model_provider,
                ),
            )
        ledger = WorkLedger(engine=self._engine, settings=WorkLedgerSettings())
        return SelfHostWorkerLoop(
            worker=Worker(
                ledger=ledger, registry=registry, queue=SelfHostTaskQueue(ledger=ledger)
            ),
            deployment_id=self._settings.deployment_id,
            stage=stage,
            lane=ProcessingLane.STEADY,
            bucket=TokenBucket(
                rate_per_s=self._settings.worker_rate_per_s,
                capacity=self._settings.worker_burst,
            ),
            database_url=_psycopg_url(),
            fallback_poll_s=self._settings.worker_fallback_poll_s,
        )

    def run_worker(self, *, stage: PipelineStage) -> None:
        """Run one configured E0 route until the process is stopped or fails."""
        loop = self.worker_loop(stage=stage)
        while True:
            loop.run_for(duration_s=self._settings.worker_session_s)


def create_api() -> FastAPI:
    """Uvicorn factory for the self-host API process."""
    return SelfHostProfile.from_settings().api()


def main(argv: list[str] | None = None) -> int:
    """Run setup, API, or one E0 worker process for Docker Compose."""
    parser = argparse.ArgumentParser(description="rememberstack self-host profile")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("setup", help="migrate and bootstrap the deployment")
    subparsers.add_parser("api", help="serve the deployment HTTP API")
    worker = subparsers.add_parser("worker", help="run one E0 worker route")
    worker.add_argument(
        "--stage",
        choices=tuple(stage.value for stage in _SUPPORTED_WORKER_STAGES),
        required=True,
    )
    args = parser.parse_args(argv)
    settings = SelfHostSettings.model_validate({})
    if args.command == "api":
        import uvicorn

        uvicorn.run(
            create_api(),
            host=settings.api_host,
            port=settings.api_port,
            access_log=True,
        )
        return 0
    profile = SelfHostProfile.from_settings()
    try:
        if args.command == "setup":
            profile.setup()
            return 0
        profile.run_worker(stage=PipelineStage(args.stage))
        return 0
    finally:
        profile.close()


def _psycopg_url() -> str:
    """Remove SQLAlchemy's driver suffix for psycopg's native connection parser."""
    url = make_url(load_database_settings().sqlalchemy_url())
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


if __name__ == "__main__":
    sys.exit(main())
