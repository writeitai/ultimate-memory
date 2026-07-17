"""Shared value identifying a checked-out or published Plane-K revision."""

from typing import Annotated

from pydantic import ConfigDict
from pydantic import Field
from pydantic import RootModel


class KRevision(RootModel[Annotated[str, Field(min_length=1)]]):
    """Opaque git revision returned by the narrow Plane-K remote seam."""

    model_config = ConfigDict(frozen=True)
