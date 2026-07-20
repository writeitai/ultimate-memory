"""Client-surface values that are safe in the dependency-light base install."""

from typing import Literal
from typing import Self
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import JsonValue
from pydantic import model_validator

_SECRET_CONFIGURATION_KEYS = frozenset(
    {
        "accesstoken",
        "apikey",
        "credential",
        "credentials",
        "password",
        "refreshtoken",
        "secret",
        "token",
    }
)


class ConnectorNotFoundError(Exception):
    """A connector id is not present in this deployment."""


class ToolDescriptor(BaseModel):
    """One deployment recipe rendered as a typed SDK/MCP tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    input_schema: dict[str, object]
    output_grain: str
    answer_intent: str


class ConnectorCreate(BaseModel):
    """Deployment-side connector configuration sent by a client.

    ``credential_ref`` names a secret already held by the deployment. Raw
    credentials never become client-surface configuration.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    configuration: dict[str, JsonValue] = Field(default_factory=dict)
    credential_ref: str | None = None

    @model_validator(mode="after")
    def _credentials_are_references(self) -> Self:
        """Reject conventional secret fields at any configuration depth."""
        secret_key = _find_secret_key(self.configuration)
        if secret_key is not None:
            raise ValueError(
                f"configuration field {secret_key!r} looks like a credential;"
                " store it deployment-side and use credential_ref"
            )
        return self


class ConnectorDescriptor(BaseModel):
    """One managed connector, never an instruction to execute it client-side."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector_id: UUID
    kind: str
    name: str
    status: Literal["active", "paused", "error"]
    configuration: dict[str, JsonValue] = Field(default_factory=dict)
    credential_ref: str | None = None
    message: str | None = None


def _find_secret_key(value: object) -> str | None:
    """Return the first conventional credential key in nested JSON-like data."""
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = key.casefold().replace("-", "").replace("_", "")
            if normalized in _SECRET_CONFIGURATION_KEYS:
                return key
            found = _find_secret_key(nested)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _find_secret_key(nested)
            if found is not None:
                return found
    return None
