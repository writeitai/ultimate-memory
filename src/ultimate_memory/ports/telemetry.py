"""D61 telemetry seam preserving structured data and real exception objects."""

from typing import Protocol
from typing import runtime_checkable

from ultimate_memory.model import TelemetryEvent


@runtime_checkable
class TelemetryPort(Protocol):
    """Export telemetry without importing a vendor SDK or hiding exporter failure."""

    def export_event(self, *, event: TelemetryEvent) -> None:
        """Export one structured event and let exporter failures propagate."""
        ...

    def export_exception(
        self, *, event: TelemetryEvent, exception: BaseException
    ) -> None:
        """Export the event with the original exception object and cause chain."""
        ...
