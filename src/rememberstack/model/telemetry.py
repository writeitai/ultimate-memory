"""Structured telemetry values that remain independent of exporter SDKs."""

from typing import Annotated

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from rememberstack.model.queue import UTCDateTime

TelemetryScalar = str | int | float | bool | None


class TelemetryAttribute(BaseModel):
    """One immutable structured attribute on a telemetry event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Annotated[str, Field(min_length=1)]
    value: TelemetryScalar


class TelemetryEvent(BaseModel):
    """Provider-neutral structured event ready for export."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Annotated[str, Field(min_length=1)]
    occurred_at: UTCDateTime
    attributes: tuple[TelemetryAttribute, ...]
