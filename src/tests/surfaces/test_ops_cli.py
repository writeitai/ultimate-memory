"""Thin CLI wiring for the existing P2/P3 rebuild implementations."""

import json
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy

from ultimate_memory.spine import settings as settings_module
from ultimate_memory.surfaces import cli_main
from ultimate_memory.workers import CorpusFsBuilder
from ultimate_memory.workers import GraphRebuildWorker

_DEPLOYMENT_ID = UUID("74000000-0000-0000-0000-000000000001")


class _Settings:
    def sqlalchemy_url(self) -> str:
        return "postgresql+psycopg://unused"


class _Engine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


@pytest.mark.parametrize("plane", ["p2", "p3"])
def test_ops_rebuild_invokes_the_existing_builder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    plane: str,
) -> None:
    """The admin surface adds no second rebuild implementation."""
    engine = _Engine()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(settings_module, "load_database_settings", lambda: _Settings())
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda _url: engine)

    def rebuild(
        _self: GraphRebuildWorker,
        *,
        deployment_id: UUID,
        workdir: Path,
        version: str | None = None,
    ) -> dict[str, object]:
        calls.append(
            {
                "plane": "p2",
                "deployment_id": deployment_id,
                "workdir": workdir,
                "version": version,
            }
        )
        return {"plane": "p2", "published": True}

    def build(
        _self: CorpusFsBuilder, *, deployment_id: UUID, version: str | None = None
    ) -> dict[str, object]:
        calls.append(
            {"plane": "p3", "deployment_id": deployment_id, "version": version}
        )
        return {"plane": "p3", "published": True}

    monkeypatch.setattr(GraphRebuildWorker, "rebuild", rebuild)
    monkeypatch.setattr(CorpusFsBuilder, "build", build)
    workdir = tmp_path / "work"
    result = cli_main(
        [
            "ops",
            "rebuild",
            "--plane",
            plane,
            "--deployment",
            str(_DEPLOYMENT_ID),
            "--snapshot-root",
            str(tmp_path / "snapshots"),
            "--workdir",
            str(workdir),
            "--version",
            "drill-v1",
        ]
    )

    assert result == 0
    assert calls[0]["plane"] == plane
    assert calls[0]["deployment_id"] == _DEPLOYMENT_ID
    assert calls[0]["version"] == "drill-v1"
    if plane == "p2":
        assert calls[0]["workdir"] == workdir
    assert json.loads(capsys.readouterr().out) == {"plane": plane, "published": True}
    assert engine.disposed is True
