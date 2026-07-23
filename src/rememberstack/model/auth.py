"""Provider-neutral values for the D50/D60 single-deployment auth perimeter."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import SecretBytes


class PerimeterCredential(BaseModel):
    """Opaque perimeter credential passed to the configured auth adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme: Annotated[str, Field(min_length=1)]
    value: SecretBytes


class AuthenticatedContext(BaseModel):
    """Authenticated principal inside one deployment-wide trust domain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    principal: Annotated[str, Field(min_length=1)]
