"""In-memory telemetry exporter preserving exception identity for tests."""

from ultimate_memory.model import TelemetryEvent


class RecordingTelemetry:
    """Record structured events and original exception objects in call order."""

    def __init__(self) -> None:
        """Start with no exports."""
        self.events: list[TelemetryEvent] = []
        self.exceptions: list[tuple[TelemetryEvent, BaseException]] = []

    def export_event(self, *, event: TelemetryEvent) -> None:
        """Record a non-exception event."""
        self.events.append(event)

    def export_exception(
        self, *, event: TelemetryEvent, exception: BaseException
    ) -> None:
        """Record the exact exception instance supplied by the worker."""
        self.exceptions.append((event, exception))
