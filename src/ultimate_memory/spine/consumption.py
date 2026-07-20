"""Postgres read model for deployment-rendered consumption skills."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.model import ConsumptionDeployment
from ultimate_memory.model import ConsumptionScope


class ConsumptionDeploymentNotFoundError(LookupError):
    """The requested active deployment does not exist in this spine."""


class ConsumptionCatalog:
    """Read the deployment, scopes, and K availability needed by the skill."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the catalog to the Postgres spine."""
        self._engine = engine

    def deployment(self, *, deployment_id: UUID) -> ConsumptionDeployment:
        """Return one active deployment's complete skill-facing read model."""
        with self._engine.connect() as connection:
            deployment = (
                connection.execute(_SELECT_DEPLOYMENT, {"deployment_id": deployment_id})
                .mappings()
                .one_or_none()
            )
            if deployment is None:
                raise ConsumptionDeploymentNotFoundError(str(deployment_id))
            scopes = tuple(
                ConsumptionScope(
                    slug=str(row["slug"]),
                    name=str(row["name"]),
                    description=row["description"],
                    git_path=row["git_path"],
                )
                for row in connection.execute(
                    _SELECT_SCOPES, {"deployment_id": deployment_id}
                ).mappings()
            )
            knowledge_page_count = connection.execute(
                _COUNT_KNOWLEDGE_PAGES, {"deployment_id": deployment_id}
            ).scalar_one()
        return ConsumptionDeployment(
            deployment_id=deployment["deployment_id"],
            slug=str(deployment["slug"]),
            name=str(deployment["name"]),
            description=deployment["description"],
            default_language=str(deployment["default_language"]),
            scopes=scopes,
            knowledge_page_count=knowledge_page_count,
        )


_SELECT_DEPLOYMENT = text(
    """
    SELECT deployment_id, slug, name, description, default_language
    FROM deployments
    WHERE deployment_id = :deployment_id AND status = 'active'
    """
)

_SELECT_SCOPES = text(
    """
    SELECT slug, name, description, git_path
    FROM scopes
    WHERE deployment_id = :deployment_id
    ORDER BY slug
    """
)

_COUNT_KNOWLEDGE_PAGES = text(
    """
    SELECT count(*)
    FROM knowledge_artifacts
    WHERE deployment_id = :deployment_id AND status <> 'tombstoned'
    """
)
