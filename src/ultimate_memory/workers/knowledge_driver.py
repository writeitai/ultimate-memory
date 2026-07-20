"""Deterministic Plane-K routing and staleness driver (WP-6.1)."""

from collections.abc import Mapping
from uuid import UUID

from ultimate_memory.model import KnowledgeCompileContext
from ultimate_memory.model import KnowledgeEvidenceDelta
from ultimate_memory.spine.knowledge import KnowledgeControlPlane


class KnowledgeRoutingDriver:
    """Route an evidence delta, recompute manifests, and mark exact stale pages."""

    def __init__(self, *, control_plane: KnowledgeControlPlane) -> None:
        """Bind the deterministic driver to its Postgres control plane."""
        self._control_plane = control_plane

    def route_and_mark_stale(
        self,
        *,
        deployment_id: UUID,
        delta: KnowledgeEvidenceDelta,
        contexts: Mapping[UUID, KnowledgeCompileContext],
    ) -> tuple[UUID, ...]:
        """Narrow by keys/citations, then mark only manifest mismatches.

        Routing may intentionally over-select because four inverted key kinds
        cannot encode every rule parameter. The complete manifest comparison
        is the correctness gate, so a coarse match can never fabricate stale
        state.
        """
        routed = self._control_plane.route_delta(
            deployment_id=deployment_id, delta=delta
        )
        stale = self._control_plane.stale_artifacts(
            deployment_id=deployment_id, contexts=contexts, artifact_ids=routed
        )
        return self._control_plane.mark_stale(artifacts=stale)

    def mark_all_manifest_drift(
        self, *, deployment_id: UUID, contexts: Mapping[UUID, KnowledgeCompileContext]
    ) -> tuple[UUID, ...]:
        """Catch sidecar, summary, rule, or writer-version drift without an E delta."""
        stale = self._control_plane.stale_artifacts(
            deployment_id=deployment_id, contexts=contexts
        )
        return self._control_plane.mark_stale(artifacts=stale)
