"""Shared SQL check for D74's deployment-wide ordinary-work barrier."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


def active_forget_id_on(*, connection: Connection, deployment_id: UUID) -> UUID | None:
    """Return the deployment's one blocking forget identity on an open connection."""
    value = connection.execute(
        _ACTIVE_FORGET, {"deployment_id": deployment_id}
    ).scalar_one_or_none()
    return value if isinstance(value, UUID) else None


_ACTIVE_FORGET = text(
    """
    SELECT forget_id
    FROM forget_manifests
    WHERE deployment_id = :deployment_id
      AND status <> 'complete'
    ORDER BY prepared_at, forget_id
    LIMIT 1
    """
)
