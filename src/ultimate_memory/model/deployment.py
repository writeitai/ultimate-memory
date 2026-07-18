"""Typed values and conflicts for deployment bootstrap."""

from typing import Annotated
from typing import TypeAlias
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import StringConstraints

NonEmptyStrictString: TypeAlias = Annotated[
    str, StringConstraints(strict=True, min_length=1)
]


class DeploymentBootstrapInput(BaseModel):
    """Explicit profile-owned values required to bootstrap one deployment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    slug: NonEmptyStrictString
    name: NonEmptyStrictString
    description: str | None = None
    default_language: NonEmptyStrictString
    raw_bucket: NonEmptyStrictString
    artifacts_bucket: NonEmptyStrictString
    corpusfs_bucket: NonEmptyStrictString
    knowledge_repo_uri: str | None = None


class DeploymentBootstrapResult(BaseModel):
    """Verified deployment and universal-core counts after bootstrap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    deployment_created: bool
    entity_types_count: int
    predicates_count: int
    predicate_signatures_count: int


class DeploymentBootstrapConflictError(RuntimeError):
    """Base class for a known bootstrap state conflict."""


class DeploymentConflictError(DeploymentBootstrapConflictError):
    """A deployment identity or mapped profile value conflicts with input."""


class CoreManifestConflictError(DeploymentBootstrapConflictError):
    """Stored core registry state conflicts with the immutable manifest."""
