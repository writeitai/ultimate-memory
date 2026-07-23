"""D74 public HTTP admission-barrier behavior."""

from typing import cast
from uuid import UUID

from fastapi.testclient import TestClient

from rememberstack.model import ForgetInProgressError
from rememberstack.surfaces.http_api import build_api
from rememberstack.surfaces.query_engine import QueryEngine

_DEPLOYMENT_ID = UUID("74000000-0000-0000-0000-000000000001")


class ClosedAdmission:
    """Fail-closed perimeter fake for one active forget."""

    def assert_available(self, *, deployment_id: UUID) -> None:
        """Reject before any query-engine method can run."""
        raise ForgetInProgressError(str(deployment_id))


class Ready:
    def ensure_ready(self, *, deployment_id: UUID) -> tuple[UUID, ...]:
        return ()


def test_public_api_returns_stable_forget_in_progress_negative() -> None:
    """Block all public traffic at composition rather than inside every query."""
    app = build_api(
        engine=cast(QueryEngine, object()),
        deployment_id=_DEPLOYMENT_ID,
        admission=ClosedAdmission(),
        readiness=Ready(),
    )

    response = TestClient(app).get("/resolve", params={"name": "anything"})

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "forget_in_progress"}}
