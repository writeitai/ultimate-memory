"""Structural contracts for D74 portable intent and erasure capabilities."""

from uuid import UUID

from ultimate_memory.model import ForgetManifest
from ultimate_memory.model import ObjectKey
from ultimate_memory.ports import ForgetManifestPort
from ultimate_memory.ports import KGitPurgePort
from ultimate_memory.ports import ObjectPurgePort
from ultimate_memory.ports import P1PurgePort
from ultimate_memory.ports import ProjectionPurgePort


class RecordingForgetStore:
    """Minimal manifest fake with the port's immutable append shape."""

    def __init__(self) -> None:
        self.items: dict[UUID, ForgetManifest] = {}

    def append(self, *, manifest: ForgetManifest) -> None:
        current = self.items.get(manifest.forget_id)
        if (
            current is not None
            and current.canonical_bytes() != manifest.canonical_bytes()
        ):
            raise ValueError("conflicting manifest")
        self.items[manifest.forget_id] = manifest

    def manifests(self, *, deployment_id: UUID) -> tuple[ForgetManifest, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self.items.values()
                    if item.deployment_id == deployment_id
                ),
                key=lambda item: str(item.forget_id),
            )
        )


class RecordingPurgeAdapter:
    """One structural fake implementing all four narrow store capabilities."""

    def purge_objects(
        self, *, keys: tuple[ObjectKey, ...], prefixes: tuple[ObjectKey, ...]
    ) -> None:
        pass

    def purge_rows(
        self,
        *,
        deployment_id: UUID,
        chunk_ids: tuple[UUID, ...],
        claim_ids: tuple[UUID, ...],
        fact_ids: tuple[UUID, ...],
        entity_ids: tuple[UUID, ...],
    ) -> None:
        pass

    def purge_projections(
        self, *, deployment_id: UUID, prefixes: tuple[ObjectKey, ...]
    ) -> None:
        pass

    def purge_artifacts(
        self, *, deployment_id: UUID, forget_id: UUID, artifact_ids: tuple[UUID, ...]
    ) -> None:
        pass


_manifest_assignment: ForgetManifestPort = RecordingForgetStore()
_object_assignment: ObjectPurgePort = RecordingPurgeAdapter()
_p1_assignment: P1PurgePort = RecordingPurgeAdapter()
_projection_assignment: ProjectionPurgePort = RecordingPurgeAdapter()
_k_assignment: KGitPurgePort = RecordingPurgeAdapter()


def test_d74_protocols_are_runtime_checkable_and_capability_sized() -> None:
    """Keep one two-operation intent port and four single-operation purge hooks."""
    assert isinstance(_manifest_assignment, ForgetManifestPort)
    assert isinstance(_object_assignment, ObjectPurgePort)
    assert isinstance(_p1_assignment, P1PurgePort)
    assert isinstance(_projection_assignment, ProjectionPurgePort)
    assert isinstance(_k_assignment, KGitPurgePort)

    assert _public_operations(ForgetManifestPort) == {"append", "manifests"}
    assert _public_operations(ObjectPurgePort) == {"purge_objects"}
    assert _public_operations(P1PurgePort) == {"purge_rows"}
    assert _public_operations(ProjectionPurgePort) == {"purge_projections"}
    assert _public_operations(KGitPurgePort) == {"purge_artifacts"}


def _public_operations(protocol: type[object]) -> set[str]:
    return {
        name
        for name, value in protocol.__dict__.items()
        if not name.startswith("_") and callable(value)
    }
