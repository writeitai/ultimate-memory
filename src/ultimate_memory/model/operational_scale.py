"""Typed results for the WP-7.2 portable operational scale battery."""

from typing import Annotated
from typing import get_args
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

OperationalScaleName = Literal[
    "d23_schema_shape",
    "hub_registry_blocking",
    "hub_lineage_recount",
    "provider_neutral_batching",
]

OPERATIONAL_SCALE_NAMES = frozenset(get_args(OperationalScaleName))


class OperationalScaleMeasurement(BaseModel):
    """One fixed-profile measurement and its non-SLA observations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: OperationalScaleName
    profile: str
    scale: dict[str, Annotated[int, Field(ge=0)]]
    metrics: dict[str, object]
    limitations: tuple[str, ...] = ()
    passed: bool


class OperationalScaleReport(BaseModel):
    """The complete four-measurement WP-7.2 report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    measurements: Annotated[
        tuple[OperationalScaleMeasurement, ...], Field(min_length=4, max_length=4)
    ]

    @model_validator(mode="after")
    def complete_battery(self) -> "OperationalScaleReport":
        """Reject duplicate or absent measurements."""
        names = {measurement.name for measurement in self.measurements}
        if names != OPERATIONAL_SCALE_NAMES:
            missing = sorted(OPERATIONAL_SCALE_NAMES - names)
            extra = sorted(names - OPERATIONAL_SCALE_NAMES)
            raise ValueError(
                f"operational scale names mismatch: missing={missing}, extra={extra}"
            )
        return self

    @property
    def passed(self) -> bool:
        """The report passes only when every structural invariant holds."""
        return all(measurement.passed for measurement in self.measurements)
