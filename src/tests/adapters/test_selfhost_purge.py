"""D74 erasure capability tests for the existing self-host stores."""

from pathlib import Path
from uuid import UUID

from ultimate_memory.adapters.selfhost import LanceChunkIndex
from ultimate_memory.adapters.selfhost import LocalFSObjectStore
from ultimate_memory.model import ObjectKey
from ultimate_memory.model import P1ChunkRow
from ultimate_memory.model import P1ClaimRow
from ultimate_memory.model import P1EntityRow
from ultimate_memory.model import P1FactRow
from ultimate_memory.ports import ObjectPurgePort
from ultimate_memory.ports import P1PurgePort

_DEPLOYMENT_ID = UUID("74000000-0000-0000-0000-000000000001")
_OTHER_DEPLOYMENT_ID = UUID("74000000-0000-0000-0000-000000000002")
_DOC_ID = UUID("74000000-0000-0000-0000-000000000003")
_VERSION_ID = UUID("74000000-0000-0000-0000-000000000004")


def test_local_object_purge_is_exact_prefix_aware_and_idempotent(
    tmp_path: Path,
) -> None:
    """Delete nominated bytes and markers while preserving unrelated objects."""
    store = LocalFSObjectStore(root=tmp_path / "objects")
    adapter: ObjectPurgePort = store
    exact = ObjectKey("raw/forgotten.bin")
    under_prefix = ObjectKey("artifacts/forgotten/transcript.json")
    similar_prefix = ObjectKey("artifacts/forgotten-extra/control.json")
    survivor = ObjectKey("raw/control.bin")
    store.write_bytes(key=exact, content=b"forgotten", storage_class="cold")
    store.write_bytes(key=under_prefix, content=b"forgotten")
    store.write_bytes(key=similar_prefix, content=b"also prefix-matched")
    store.write_bytes(key=survivor, content=b"control")

    adapter.purge_objects(keys=(exact,), prefixes=(ObjectKey("artifacts/forgotten"),))
    adapter.purge_objects(keys=(exact,), prefixes=(ObjectKey("artifacts/forgotten"),))

    assert not (tmp_path / "objects/raw/forgotten.bin").exists()
    assert not (tmp_path / "objects/raw/forgotten.bin.storage-class").exists()
    assert not (tmp_path / "objects/artifacts/forgotten").exists()
    assert not (tmp_path / "objects/artifacts/forgotten-extra").exists()
    assert store.read_bytes(key=survivor) == b"control"


def test_lance_purge_removes_only_nominated_deployment_rows(tmp_path: Path) -> None:
    """Erase all four P1 channels by UUID and accept an exact retry."""
    index = LanceChunkIndex(root=tmp_path / "lance")
    adapter: P1PurgePort = index
    forgotten = _ids(suffix=10)
    survivor = _ids(suffix=20)
    _seed_p1(index=index, deployment_id=_DEPLOYMENT_ID, ids=forgotten)
    _seed_p1(index=index, deployment_id=_OTHER_DEPLOYMENT_ID, ids=survivor)

    adapter.purge_rows(
        deployment_id=_DEPLOYMENT_ID,
        chunk_ids=(forgotten[0],),
        claim_ids=(forgotten[1],),
        fact_ids=(forgotten[2],),
        entity_ids=(forgotten[3],),
    )
    adapter.purge_rows(
        deployment_id=_DEPLOYMENT_ID,
        chunk_ids=(forgotten[0],),
        claim_ids=(forgotten[1],),
        fact_ids=(forgotten[2],),
        entity_ids=(forgotten[3],),
    )

    assert index.table_count(table="chunks") == 1
    assert index.table_count(table="claims") == 1
    assert index.table_count(table="facts") == 1
    assert index.table_count(table="entities") == 1
    assert index.chunk_vectors(
        deployment_id=str(_OTHER_DEPLOYMENT_ID), chunk_ids=(str(survivor[0]),)
    ) == {str(survivor[0]): (0.0, 1.0)}
    assert index.entity_vectors(
        deployment_id=str(_OTHER_DEPLOYMENT_ID), entity_ids=(str(survivor[3]),)
    ) == {str(survivor[3]): (0.0, 1.0)}


def _ids(*, suffix: int) -> tuple[UUID, UUID, UUID, UUID]:
    """Return stable chunk, claim, fact, and entity IDs for one fixture row set."""
    return (
        UUID(f"74000000-0000-0000-0000-{suffix:012d}"),
        UUID(f"74000000-0000-0000-0000-{suffix + 1:012d}"),
        UUID(f"74000000-0000-0000-0000-{suffix + 2:012d}"),
        UUID(f"74000000-0000-0000-0000-{suffix + 3:012d}"),
    )


def _seed_p1(
    *, index: LanceChunkIndex, deployment_id: UUID, ids: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """Write one related row into each P1 channel."""
    chunk_id, claim_id, fact_id, entity_id = ids
    vector = (0.0, 1.0)
    index.upsert_chunks(
        rows=(
            P1ChunkRow(
                chunk_id=chunk_id,
                deployment_id=deployment_id,
                doc_id=_DOC_ID,
                version_id=_VERSION_ID,
                section_role="body",
                text="fixture chunk",
                vector=vector,
            ),
        )
    )
    index.upsert_claims(
        rows=(
            P1ClaimRow(
                claim_id=claim_id,
                deployment_id=deployment_id,
                doc_id=_DOC_ID,
                chunk_id=chunk_id,
                text="fixture claim",
                is_current_testimony=True,
                is_attributed=True,
                vector=vector,
            ),
        )
    )
    index.upsert_facts(
        rows=(
            P1FactRow(
                fact_id=fact_id,
                deployment_id=deployment_id,
                kind="relation",
                label="fixture fact",
                status="active",
                vector=vector,
            ),
        )
    )
    index.upsert_entities(
        rows=(
            P1EntityRow(
                entity_id=entity_id,
                deployment_id=deployment_id,
                type="Person",
                canonical_name="Fixture Entity",
                vector=vector,
            ),
        )
    )
