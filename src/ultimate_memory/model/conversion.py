"""D38 conversion-module values: converter output and its typed failures."""

from pydantic import BaseModel
from pydantic import ConfigDict


class ConversionResult(BaseModel):
    """What a converter route produced from one raw input.

    `document_md` is the clean Markdown rendering — the immutable coordinate
    system everything downstream references by offset (D57). Source maps and
    derived assets (media routes, D65) extend this model when their routes
    arrive; every converter can always deliver the Markdown itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_md: str
    warnings: tuple[str, ...] = ()


class ConversionError(Exception):
    """A converter could not produce Markdown from the input bytes.

    Deterministic for given bytes, so retrying cannot help — handlers treat
    this as non-retryable and dead-letter the work with the cause chained.
    """


class UnroutableMimeError(Exception):
    """No configured conversion route accepts the input's MIME type (D38)."""
