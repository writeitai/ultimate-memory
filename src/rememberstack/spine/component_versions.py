"""Transactional component-version registration and resolution."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from rememberstack.model import ComponentVersionConflictError
from rememberstack.model import ComponentVersionError
from rememberstack.model import ComponentVersionNotFoundError
from rememberstack.model import ComponentVersionRecord
from rememberstack.model import PipelineComponent
from rememberstack.model import RegisterComponentVersionInput
from rememberstack.model import RegisterComponentVersionResult

_INSERT_COMPONENT_VERSION = text(
    """
    INSERT INTO pipeline_component_versions (
        deployment_id,
        component,
        version,
        model_name,
        prompt_hash,
        embedding_dim,
        params,
        notes
    ) VALUES (
        :deployment_id,
        :component,
        :version,
        :model_name,
        :prompt_hash,
        :embedding_dim,
        :params,
        :notes
    )
    ON CONFLICT (deployment_id, component, version) DO NOTHING
    RETURNING deployment_id
    """
).bindparams(bindparam("params", type_=JSON))

_SELECT_COMPONENT_VERSION = """
SELECT
    deployment_id,
    component,
    version,
    model_name,
    prompt_hash,
    embedding_dim,
    params,
    notes,
    configured_at
FROM pipeline_component_versions
WHERE deployment_id = :deployment_id
  AND component = :component
  AND version = :version
"""


class ComponentVersionRegistrar:
    """Register and resolve immutable component versions through an injected engine."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind catalog operations to an explicitly composed SQLAlchemy engine."""
        self._engine = engine

    def register_component_version(
        self, *, component_version_input: RegisterComponentVersionInput
    ) -> RegisterComponentVersionResult:
        """Compare or insert one component definition in one owned transaction."""
        try:
            with self._engine.begin() as connection:
                values = _component_version_values(
                    component_version_input=component_version_input
                )
                inserted = connection.execute(
                    statement=_INSERT_COMPONENT_VERSION, parameters=values
                ).scalar_one_or_none()
                if inserted is not None:
                    return _registration_result(
                        component_version_input=component_version_input, created=True
                    )

                existing = (
                    connection.execute(
                        statement=text(f"{_SELECT_COMPONENT_VERSION} FOR UPDATE"),
                        parameters=_component_version_key(
                            deployment_id=component_version_input.deployment_id,
                            component=component_version_input.component,
                            version=component_version_input.version,
                        ),
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is None:
                    raise ComponentVersionError(
                        "component version disappeared during registration"
                    )
                if _stored_definition(row=existing) != _input_definition(
                    component_version_input=component_version_input
                ):
                    raise ComponentVersionConflictError(
                        "component-version definition conflicts with the registered key"
                    )
                return _registration_result(
                    component_version_input=component_version_input, created=False
                )
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23503":
                raise ComponentVersionError(
                    "deployment_id does not reference a registered deployment"
                ) from error
            raise

    def resolve_component_version(
        self, *, deployment_id: UUID, component: PipelineComponent, version: str
    ) -> ComponentVersionRecord:
        """Resolve one component definition by its complete primary-key triple."""
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    statement=text(_SELECT_COMPONENT_VERSION),
                    parameters=_component_version_key(
                        deployment_id=deployment_id,
                        component=component,
                        version=version,
                    ),
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ComponentVersionNotFoundError(
                "component version does not exist for the requested key"
            )
        return ComponentVersionRecord.model_validate(dict(row))


def _component_version_key(
    *, deployment_id: UUID, component: PipelineComponent, version: str
) -> dict[str, object]:
    """Map the complete schema primary key to bound SQL values."""
    return {
        "deployment_id": deployment_id,
        "component": component.value,
        "version": version,
    }


def _component_version_values(
    *, component_version_input: RegisterComponentVersionInput
) -> dict[str, object]:
    """Map every explicit input to its corresponding catalog column."""
    return {
        **_component_version_key(
            deployment_id=component_version_input.deployment_id,
            component=component_version_input.component,
            version=component_version_input.version,
        ),
        **_input_definition(component_version_input=component_version_input),
    }


def _input_definition(
    *, component_version_input: RegisterComponentVersionInput
) -> dict[str, object]:
    """Canonicalize the complete immutable input definition for comparison."""
    return {
        "model_name": component_version_input.model_name,
        "prompt_hash": component_version_input.prompt_hash,
        "embedding_dim": component_version_input.embedding_dim,
        "params": dict(component_version_input.params),
        "notes": component_version_input.notes,
    }


def _stored_definition(*, row: RowMapping) -> dict[str, object]:
    """Canonicalize stored definition fields with semantic JSON-map equality."""
    params = row["params"]
    if not isinstance(params, Mapping):
        raise ComponentVersionError(
            "stored component-version params are not a JSON object"
        )
    return {
        "model_name": row["model_name"],
        "prompt_hash": row["prompt_hash"],
        "embedding_dim": row["embedding_dim"],
        "params": dict(params),
        "notes": row["notes"],
    }


def _registration_result(
    *, component_version_input: RegisterComponentVersionInput, created: bool
) -> RegisterComponentVersionResult:
    """Build the exact settled registration result shape."""
    return RegisterComponentVersionResult(
        deployment_id=component_version_input.deployment_id,
        component=component_version_input.component,
        version=component_version_input.version,
        created=created,
    )
