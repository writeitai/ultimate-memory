"""The markitdown conversion route (D38): office/html/email formats → Markdown."""

import io
from typing import Final

from markitdown import MarkItDown
from markitdown import StreamInfo
from markitdown._exceptions import MarkItDownException

from rememberstack.model import ConversionError
from rememberstack.model import ConversionResult

MARKITDOWN_CONVERTER_VERSION: Final = "markitdown-0.1"
"""Pins the markitdown library generation this route was validated against."""


class MarkitdownConverter:
    """The default local route for structured text formats (html, office, email)."""

    def __init__(self) -> None:
        """Build the converter once; markitdown instances are reusable."""
        self._markitdown = MarkItDown(enable_plugins=False)

    @property
    def name(self) -> str:
        """The route name recorded on representations."""
        return "markitdown"

    @property
    def version(self) -> str:
        """The pinned markitdown route version (D38)."""
        return MARKITDOWN_CONVERTER_VERSION

    def convert(self, *, content: bytes, mime: str) -> ConversionResult:
        """Convert one input via markitdown; its failures become typed failures."""
        try:
            result = self._markitdown.convert_stream(
                io.BytesIO(content), stream_info=StreamInfo(mimetype=mime)
            )
        except MarkItDownException as err:
            raise ConversionError(f"markitdown could not convert {mime!r}") from err
        return ConversionResult(document_md=result.text_content)
