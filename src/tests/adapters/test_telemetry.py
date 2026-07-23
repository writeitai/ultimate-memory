"""Provider-neutral and self-host telemetry adapter contracts."""

from datetime import datetime
from datetime import UTC
from io import StringIO
import json

from rememberstack.adapters.selfhost import JsonLineTelemetry
from rememberstack.model import TelemetryAttribute
from rememberstack.model import TelemetryEvent


def _event() -> TelemetryEvent:
    return TelemetryEvent(
        name="worker.run",
        occurred_at=datetime(2026, 7, 21, tzinfo=UTC),
        attributes=(TelemetryAttribute(name="outcome", value="dead_lettered"),),
    )


def test_json_lines_preserves_exception_cause_chain() -> None:
    """The local exporter keeps structured data and both chained exceptions."""
    stream = StringIO()
    telemetry = JsonLineTelemetry(stream=stream)
    try:
        try:
            raise KeyError("root cause")
        except KeyError as cause:
            raise ValueError("outer failure") from cause
    except ValueError as error:
        telemetry.export_exception(event=_event(), exception=error)

    payload = json.loads(stream.getvalue())
    assert payload["name"] == "worker.run"
    assert payload["exception"]["type"] == "ValueError"
    assert "KeyError: 'root cause'" in payload["exception"]["traceback"]
    assert "ValueError: outer failure" in payload["exception"]["traceback"]


def test_json_lines_flushes_one_event_per_line() -> None:
    """Ordinary event output is valid compact JSON with one trailing newline."""
    stream = StringIO()
    JsonLineTelemetry(stream=stream).export_event(event=_event())
    assert stream.getvalue().count("\n") == 1
    assert json.loads(stream.getvalue())["attributes"][0] == {
        "name": "outcome",
        "value": "dead_lettered",
    }
