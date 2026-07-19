"""D61 seam for watched sources: poll observations, fetch bytes (lifecycle §2)."""

from collections.abc import Mapping
from typing import Protocol
from typing import runtime_checkable

from ultimate_memory.model import SourceItem


@runtime_checkable
class WatchedSourcePort(Protocol):
    """One watched source: enumerate current items and detect deletions."""

    def poll(self, *, known: Mapping[str, str]) -> tuple[SourceItem, ...]:
        """Report every current item plus a deleted-marked item for each
        known source_ref no longer present. `known` maps source_ref → the
        last ingested revision, so unchanged items can skip fetch entirely.
        """
        ...

    def fetch(self, *, source_ref: str) -> bytes:
        """The item's current bytes (called only for changed items)."""
        ...
