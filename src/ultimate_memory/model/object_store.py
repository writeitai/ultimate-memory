"""Provider-neutral object keys for immutable raw, artifact, and snapshot bytes."""

from typing import Annotated

from pydantic import ConfigDict
from pydantic import Field
from pydantic import RootModel


class ObjectKey(RootModel[Annotated[str, Field(min_length=1)]]):
    """Opaque non-empty key in the configured immutable object store."""

    model_config = ConfigDict(frozen=True)
