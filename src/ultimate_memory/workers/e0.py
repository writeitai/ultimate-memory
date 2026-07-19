"""The minimal E0 chain (D36): upload → ingest → convert → synthetic-root structure.

The upload connector performs ingest synchronously (bytes to the raw store,
rows + convert work atomically through the catalog); convert and structure are
queued stage handlers. Artifacts land ID-addressed in the artifacts store
(`<doc_id>/<content_hash>/<representation_id>/…`, D37/D65); Postgres carries
only the index.
"""

from datetime import datetime
import hashlib
import json
from pathlib import PurePosixPath
from typing import Final
from uuid import NAMESPACE_URL
from uuid import UUID
from uuid import uuid4
from uuid import uuid5

from ultimate_memory.core import blockize
from ultimate_memory.core import BLOCKIZER_VERSION
from ultimate_memory.core import ConversionRouter
from ultimate_memory.model import ClaimedWork
from ultimate_memory.model import ConversionError
from ultimate_memory.model import DocumentUpload
from ultimate_memory.model import EnqueueWork
from ultimate_memory.model import IngestedVersion
from ultimate_memory.model import NonRetryableHandlerError
from ultimate_memory.model import ObjectAlreadyExistsError
from ultimate_memory.model import ObjectKey
from ultimate_memory.model import PipelineStage
from ultimate_memory.model import RepresentationRecord
from ultimate_memory.model import SyntheticRootRecord
from ultimate_memory.model import UnroutableMimeError
from ultimate_memory.model import UploadRecord
from ultimate_memory.ports.object_store import ObjectStorePort
from ultimate_memory.spine.document_catalog import DocumentCatalog
from ultimate_memory.workers.base import HandlerOutcome
from ultimate_memory.workers.e1 import E1_CHUNK_VERSION

E0_CONVERT_VERSION: Final = "e0-convert-2026.07"
"""The convert sub-worker's component version (D12 idempotency key member)."""

E0_STRUCTURE_VERSION: Final = "e0-structure-2026.07"
"""The synthetic-root structurer's component version (D39)."""

UPLOAD_SOURCE_KIND: Final = "upload"
"""The one-shot upload connector's source kind (D55 lineage identity)."""


class UploadIngestor:
    """The upload connector's ingest: bytes to the raw store, rows + work to the spine.

    A one-shot upload has no connector-native identity, so its lineage IS its
    content: `source_ref = content_hash` and a content-derived `doc_id`, which
    makes re-ingesting identical bytes a deterministic no-op (D55) and lets
    the raw object be written before any row exists.
    """

    def __init__(self, *, catalog: DocumentCatalog, raw_store: ObjectStorePort) -> None:
        """Bind the connector to the catalog and the deployment's raw bucket."""
        self._catalog = catalog
        self._raw_store = raw_store

    def ingest(self, *, deployment_id: UUID, upload: DocumentUpload) -> IngestedVersion:
        """Ingest one uploaded file and enqueue its convert work."""
        content_hash = hashlib.sha256(upload.content).hexdigest()
        doc_id = uuid5(NAMESPACE_URL, f"ugm:upload:{deployment_id}:{content_hash}")
        suffix = PurePosixPath(upload.filename).suffix
        raw_uri = f"{doc_id}/{content_hash}/original{suffix}"
        try:
            self._raw_store.write_bytes(key=ObjectKey(raw_uri), content=upload.content)
        except ObjectAlreadyExistsError:
            pass  # identical bytes already landed — ingest retries are no-ops
        return self._catalog.record_upload(
            record=UploadRecord(
                deployment_id=deployment_id,
                doc_id=doc_id,
                source_kind=UPLOAD_SOURCE_KIND,
                source_ref=content_hash,
                source_uri=None,
                title=upload.title or PurePosixPath(upload.filename).stem,
                content_hash=content_hash,
                mime=upload.mime,
                byte_size=len(upload.content),
                raw_uri=raw_uri,
            ),
            convert_component_version=E0_CONVERT_VERSION,
        )

    def ingest_observed(
        self,
        *,
        deployment_id: UUID,
        source_kind: str,
        source_ref: str,
        upload: DocumentUpload,
        versioning_mode: str,
        source_modified_at: datetime | None,
        source_version_ref: str | None,
        sync_cycle_id: UUID | None,
    ) -> IngestedVersion:
        """Ingest one WATCHED observation of a lineage (D55).

        Identity is connector-native (source_kind, source_ref) — bytes
        cannot identify a lineage (they change; that is the premise). A
        changed file becomes a new VERSION of its lineage; identical bytes
        are the content-hash no-op.
        """
        content_hash = hashlib.sha256(upload.content).hexdigest()
        doc_id = uuid5(NAMESPACE_URL, f"ugm:{source_kind}:{deployment_id}:{source_ref}")
        suffix = PurePosixPath(upload.filename).suffix
        raw_uri = f"{doc_id}/{content_hash}/original{suffix}"
        try:
            self._raw_store.write_bytes(key=ObjectKey(raw_uri), content=upload.content)
        except ObjectAlreadyExistsError:
            pass
        return self._catalog.record_upload(
            record=UploadRecord(
                deployment_id=deployment_id,
                doc_id=doc_id,
                source_kind=source_kind,
                source_ref=source_ref,
                source_uri=source_ref,
                title=upload.title or PurePosixPath(upload.filename).stem,
                content_hash=content_hash,
                mime=upload.mime,
                byte_size=len(upload.content),
                raw_uri=raw_uri,
                versioning_mode=versioning_mode,
                source_modified_at=source_modified_at,
                source_version_ref=source_version_ref,
                sync_cycle_id=sync_cycle_id,
            ),
            convert_component_version=E0_CONVERT_VERSION,
        )


class ConvertHandler:
    """The convert stage (D38/D57): raw bytes → document.md + blocks + manifest.

    One representation per run: converter output and the deterministic block
    sequence are written ID-addressed to the artifacts store, then recorded as
    an immutable `document_representations` row (D65). Chains structure.
    """

    def __init__(
        self,
        *,
        catalog: DocumentCatalog,
        raw_store: ObjectStorePort,
        artifact_store: ObjectStorePort,
        router: ConversionRouter,
    ) -> None:
        """Bind the handler to its catalog, both stores, and the route table."""
        self._catalog = catalog
        self._raw_store = raw_store
        self._artifact_store = artifact_store
        self._router = router

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Convert one document version and record its representation.

        Replay before regenerate (D65/D7): a representation this toolchain
        already produced for the version is re-chained as-is — the converter
        is never re-called on a retried or replayed attempt.
        """
        source = self._catalog.convert_source(
            version_id=_payload_uuid(work=work, field="version_id")
        )
        try:
            converter = self._router.converter_for(mime=source.mime)
        except UnroutableMimeError as err:
            # deterministic for this input — retrying cannot help (D12); the
            # version's own status must not keep claiming in-flight work:
            self._catalog.mark_version_failed(
                version_id=source.version_id, error=str(err)
            )
            raise NonRetryableHandlerError(str(err)) from err
        existing = self._catalog.existing_representation(
            version_id=source.version_id,
            route=converter.name,
            converter_version=converter.version,
            blockizer_version=BLOCKIZER_VERSION,
        )
        if existing is not None:
            return self._structure_follow_up(
                work=work, version_id=source.version_id, representation_id=existing
            )
        content = self._raw_store.read_bytes(key=ObjectKey(source.raw_uri))
        try:
            result = converter.convert(content=content, mime=source.mime)
        except ConversionError as err:
            self._catalog.mark_version_failed(
                version_id=source.version_id, error=str(err)
            )
            raise NonRetryableHandlerError(str(err)) from err
        blocks = blockize(document_md=result.document_md)

        representation_id = uuid4()
        base = f"{source.doc_id}/{source.content_hash}/{representation_id}"
        markdown_bytes = result.document_md.encode("utf-8")
        markdown_hash = hashlib.sha256(markdown_bytes).hexdigest()
        blocks_bytes = _json_bytes(
            payload={
                "blockizer_version": BLOCKIZER_VERSION,
                "block_count": len(blocks),
                "markdown_chars": len(result.document_md),
                "blocks": [block.model_dump(mode="json") for block in blocks],
            }
        )
        manifest_bytes = _json_bytes(
            payload={
                "route": converter.name,
                "converter": {"name": converter.name, "version": converter.version},
                "blockizer_version": BLOCKIZER_VERSION,
                "execution": "library-local",
                "markdown_sha256": markdown_hash,
                "source_map": None,
                "derived_assets": [],
                "warnings": list(result.warnings),
            }
        )
        meta_bytes = _json_bytes(
            payload={
                "doc_id": str(source.doc_id),
                "version_id": str(source.version_id),
                "representation_id": str(representation_id),
                "content_hash": source.content_hash,
                "mime": source.mime,
                "title": source.title,
                "route": converter.name,
            }
        )
        artifacts = {
            f"{base}/document.md": markdown_bytes,
            f"{base}/blocks.json": blocks_bytes,
            f"{base}/conversion.json": manifest_bytes,
            f"{base}/meta.json": meta_bytes,
        }
        for uri, payload_bytes in artifacts.items():
            self._artifact_store.write_bytes(key=ObjectKey(uri), content=payload_bytes)

        self._catalog.record_representation(
            record=RepresentationRecord(
                representation_id=representation_id,
                deployment_id=source.deployment_id,
                version_id=source.version_id,
                route=converter.name,
                converter_name=converter.name,
                converter_version=converter.version,
                blockizer_version=BLOCKIZER_VERSION,
                markdown_uri=f"{base}/document.md",
                blocks_uri=f"{base}/blocks.json",
                conversion_uri=f"{base}/conversion.json",
                meta_uri=f"{base}/meta.json",
                markdown_hash=markdown_hash,
                manifest_hash=hashlib.sha256(manifest_bytes).hexdigest(),
            )
        )
        return self._structure_follow_up(
            work=work, version_id=source.version_id, representation_id=representation_id
        )

    def _structure_follow_up(
        self, *, work: ClaimedWork, version_id: UUID, representation_id: UUID
    ) -> HandlerOutcome:
        """Chain the structure stage for one (version, representation)."""
        return HandlerOutcome(
            follow_up=(
                EnqueueWork(
                    deployment_id=work.deployment_id,
                    target_kind=work.target_kind,
                    target_id=work.target_id,
                    stage=PipelineStage.STRUCTURE,
                    component_version=E0_STRUCTURE_VERSION,
                    content_hash=work.content_hash,
                    lane=work.lane,
                    payload={
                        "version_id": str(version_id),
                        "representation_id": str(representation_id),
                    },
                ),
            )
        )


class StructureHandler:
    """The structure stage, synthetic-root form (D39): every document gets a root.

    Reads the representation's blocks.json for the full span, writes the
    single `role=body` root section, and completes the chain — representation
    ready, live-reading pointer set, lineage currency moved (D54).
    """

    def __init__(
        self, *, catalog: DocumentCatalog, artifact_store: ObjectStorePort
    ) -> None:
        """Bind the handler to its catalog and the deployment's artifacts bucket."""
        self._catalog = catalog
        self._artifact_store = artifact_store

    def handle(self, *, work: ClaimedWork) -> HandlerOutcome:
        """Give one representation its synthetic root and flip currency."""
        source = self._catalog.structure_source(
            representation_id=_payload_uuid(work=work, field="representation_id")
        )
        blocks_doc = json.loads(
            self._artifact_store.read_bytes(key=ObjectKey(source.blocks_uri))
        )
        self._catalog.record_synthetic_root(
            record=SyntheticRootRecord(
                section_id=uuid4(),
                deployment_id=source.deployment_id,
                doc_id=source.doc_id,
                version_id=source.version_id,
                representation_id=source.representation_id,
                block_count=blocks_doc["block_count"],
                markdown_chars=blocks_doc["markdown_chars"],
                title=source.title,
                structurer_version=E0_STRUCTURE_VERSION,
            )
        )
        return HandlerOutcome(
            follow_up=(
                EnqueueWork(
                    deployment_id=work.deployment_id,
                    target_kind=work.target_kind,
                    target_id=work.target_id,
                    stage=PipelineStage.CHUNK,
                    component_version=E1_CHUNK_VERSION,
                    content_hash=work.content_hash,
                    lane=work.lane,
                    payload={
                        "version_id": str(source.version_id),
                        "representation_id": str(source.representation_id),
                    },
                ),
            )
        )


def _payload_uuid(*, work: ClaimedWork, field: str) -> UUID:
    """Read a required UUID from the claimed payload; absence is non-retryable."""
    value = (work.payload or {}).get(field)
    if not isinstance(value, str):
        raise NonRetryableHandlerError(
            f"stage {work.stage} work {work.processing_id} carries no {field!r} payload"
        )
    return UUID(value)


def _json_bytes(*, payload: dict[str, object]) -> bytes:
    """Serialize one artifact JSON document deterministically."""
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
