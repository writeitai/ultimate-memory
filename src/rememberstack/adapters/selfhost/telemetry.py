"""Simple JSON-lines telemetry for self-hosted process logs."""

import json
import sys
from threading import Lock
import traceback
from typing import TextIO

from rememberstack.model import TelemetryEvent


class JsonLineTelemetry:
    """Write one complete structured event per line to a process-owned stream."""

    def __init__(self, *, stream: TextIO | None = None) -> None:
        """Use stdout by default and serialize concurrent worker writes."""
        self._stream = stream or sys.stdout
        self._lock = Lock()

    def export_event(self, *, event: TelemetryEvent) -> None:
        """Write and flush one ordinary event."""
        self._write(payload=event.model_dump(mode="json"))

    def export_exception(
        self, *, event: TelemetryEvent, exception: BaseException
    ) -> None:
        """Write the event plus the supplied exception's complete cause chain."""
        payload = event.model_dump(mode="json")
        payload["exception"] = {
            "type": type(exception).__qualname__,
            "message": str(exception),
            "traceback": "".join(
                traceback.TracebackException.from_exception(exception).format(
                    chain=True
                )
            ),
        }
        self._write(payload=payload)

    def _write(self, *, payload: dict[str, object]) -> None:
        """Keep every event atomic at the stream boundary."""
        line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()
