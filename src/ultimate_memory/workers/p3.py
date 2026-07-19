"""The P3 corpus filesystem builder (e0 §6, D40/D49): the navigable tree.

A real directory tree, rebuilt whole and published as an immutable snapshot
with a pointer swap — the same rebuild-first discipline as P2 (D7). It holds
no truth: every file is generated from Postgres plus the artifacts, and the
tree is discardable.

The tree exists to make navigation cheaper than search. An agent reads ONE
`_index.md` and learns what every file in that directory is about (each
member row carries the document's PageIndex root summary, already stored by
the structure stage), so navigation cost is O(index files read), not
O(documents opened). Every level also carries `llms.txt` — orientation
before contents.

**The two-tier path contract (F6) is the load-bearing rule.**

- *Tier 1 — stable, ID-addressed leaves that never move across rebuilds*:
  `entities/<type>/<entity_id>/` and `documents/<doc_id>/`. Lineage-anchored
  (D55), so a living document's canonical path survives its versions. These
  are the durable targets agents and K pages may store.
- *Tier 2 — view paths* (`by-source/…`, `by-topic/…`), freely reorganizable
  as the corpus grows; every view stub carries its canonical Tier-1 path in
  frontmatter, so a moved stub is never a lost document.

Fully deterministic, zero LLM: a directory-level synthesis is a K page's
job (a second uncited understanding layer would drift), so `_index.md`
LINKS K and never competes with it.
"""

from collections.abc import Iterable
from datetime import datetime
from datetime import UTC
import hashlib
import json
from pathlib import PurePosixPath
from typing import Final
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from ultimate_memory.model import ObjectKey
from ultimate_memory.ports.object_store import ObjectStorePort
from ultimate_memory.spine.projection import ProjectionCatalog

P3_BUILDER_VERSION: Final = "p3-corpusfs-2026.07"
"""The builder's component version (D12)."""

INDEX_FILE: Final = "_index.md"
MANIFEST_FILE: Final = "llms.txt"


class CorpusFsSettings(BaseSettings):
    """The P3 builder's knobs (starting points to measure, D22)."""

    model_config = SettingsConfigDict(env_prefix="UGM_P3_")

    snapshot_prefix: str = Field(default="corpusfs/snapshots")
    shard_threshold: int = Field(default=150, ge=2)
    """Above this many entries a directory shards deterministically — an
    unbounded directory is unbrowsable for an agent and slow to list."""


class CorpusFsBuilder:
    """Build, validate, publish one corpus-filesystem snapshot."""

    def __init__(
        self,
        *,
        catalog: ProjectionCatalog,
        snapshot_store: ObjectStorePort,
        settings: CorpusFsSettings | None = None,
    ) -> None:
        """Bind the builder to the spine and the corpusfs bucket."""
        self._catalog = catalog
        self._snapshot_store = snapshot_store
        self._settings = settings or CorpusFsSettings()

    def build(
        self, *, deployment_id: UUID, version: str | None = None
    ) -> dict[str, object]:
        """Rebuild the whole tree, publish it, swap the pointer."""
        version = version or datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S%f")
        prefix = f"{self._settings.snapshot_prefix}/{deployment_id}/{version}"
        snapshot_id = self._catalog.open_snapshot(
            deployment_id=deployment_id,
            plane="P3_corpusfs",
            version=version,
            store_prefix=prefix,
        )
        try:
            files = self._render(deployment_id=deployment_id)
            for path, content in sorted(files.items()):
                self._snapshot_store.write_bytes(
                    key=ObjectKey(f"{prefix}/{path}"), content=content.encode("utf-8")
                )
            manifest = {
                "version": version,
                "files": {
                    path: hashlib.sha256(content.encode("utf-8")).hexdigest()
                    for path, content in files.items()
                },
            }
            self._snapshot_store.write_bytes(
                key=ObjectKey(f"{prefix}/MANIFEST.json"),
                content=json.dumps(manifest).encode("utf-8"),
            )
        except Exception as error:
            self._catalog.mark_failed(
                snapshot_id=snapshot_id,
                validation={"gate": "exception", "error": str(error)[:500]},
            )
            raise
        published = self._catalog.publish(
            deployment_id=deployment_id,
            snapshot_id=snapshot_id,
            plane="P3_corpusfs",
            row_counts={"files": len(files)},
            validation={"gate": "passed", "builder": P3_BUILDER_VERSION},
            built_from_watermark=None,
        )
        return {
            "snapshot_id": snapshot_id,
            "version": version,
            "files": len(files),
            "published": published,
        }

    def _render(self, *, deployment_id: UUID) -> dict[str, str]:
        """Render every file of the tree, keyed by its snapshot-relative path."""
        documents = self._catalog.corpus_documents(deployment_id=deployment_id)
        entities = self._catalog.corpus_entities(deployment_id=deployment_id)
        links = self._catalog.entity_document_links(deployment_id=deployment_id)
        by_entity: dict[UUID, list[UUID]] = {}
        for link in links:
            by_entity.setdefault(UUID(str(link["entity_id"])), []).append(
                UUID(str(link["doc_id"]))
            )
        documents_by_id = {UUID(str(doc["doc_id"])): doc for doc in documents}

        files: dict[str, str] = {}
        # ── Tier 1: canonical, ID-addressed leaves (never move) ──────────
        for document in documents:
            path = _document_path(doc_id=UUID(str(document["doc_id"])))
            files[f"{path}/{INDEX_FILE}"] = _document_stub(
                document=document, canonical_path=path
            )
        for entity in entities:
            entity_id = UUID(str(entity["entity_id"]))
            path = _entity_path(entity_id=entity_id, entity_type=str(entity["type"]))
            files[f"{path}/{INDEX_FILE}"] = _entity_index(
                entity=entity,
                documents=[
                    documents_by_id[doc_id]
                    for doc_id in by_entity.get(entity_id, [])
                    if doc_id in documents_by_id
                ],
            )
        # ── Tier 2: view subtrees (reorganizable; stubs carry Tier 1) ────
        views: dict[str, list[dict[str, object]]] = {}
        for document in documents:
            for view_path in _view_paths(document=document):
                views.setdefault(view_path, []).append(document)
        for view_path, members in views.items():
            for shard, shard_members in _shards(
                members=members, threshold=self._settings.shard_threshold
            ).items():
                directory = f"{view_path}/{shard}" if shard else view_path
                for document in shard_members:
                    stub = _stub_name(document=document)
                    files[f"{directory}/{stub}"] = _document_stub(
                        document=document,
                        canonical_path=_document_path(
                            doc_id=UUID(str(document["doc_id"]))
                        ),
                        view_path=directory,
                    )
                files[f"{directory}/{INDEX_FILE}"] = _directory_index(
                    directory=directory, members=shard_members
                )
                files[f"{directory}/{MANIFEST_FILE}"] = _directory_manifest(
                    directory=directory, members=shard_members
                )
        # ── facet and root orientation ───────────────────────────────────
        files.update(
            _facet_indexes(
                files=files, documents=documents, entities=entities, views=views
            )
        )
        return files


def _document_path(*, doc_id: UUID) -> str:
    """The canonical Tier-1 path: lineage-anchored, stable across versions."""
    return f"documents/{doc_id}"


def _entity_path(*, entity_id: UUID, entity_type: str) -> str:
    """The canonical Tier-1 path for one entity."""
    return f"entities/{_slug(entity_type)}/{entity_id}"


def _view_paths(*, document: dict[str, object]) -> tuple[str, ...]:
    """The Tier-2 views one document appears in — one stub per view.

    Views come from the configured facet skeleton (the top level is
    configured, never emergent) plus the document's placement hint. A
    document with no hint still lands in the source and time views, so the
    tree is never partially navigable.
    """
    paths = [f"by-source/{_slug(str(document['source_kind']))}"]
    stamp = document.get("source_modified_at") or document.get("published_at")
    if isinstance(stamp, datetime):
        paths.append(f"by-time/{stamp.year:04d}/{stamp.month:02d}")
    placement = document.get("placement_path")
    if isinstance(placement, str) and placement.strip("/"):
        paths.append(
            f"by-topic/{'/'.join(_slug(part) for part in placement.strip('/').split('/'))}"
        )
    return tuple(paths)


def _shards(
    *, members: list[dict[str, object]], threshold: int
) -> dict[str, list[dict[str, object]]]:
    """Split an oversized directory deterministically (bounded fan-out).

    Sharding is alphabetical by stub name so a rebuild puts the same
    document in the same shard — a view path may reorganize between
    rebuilds by design, but never *randomly* within one.
    """
    ordered = sorted(members, key=_stub_name_of)
    if len(ordered) <= threshold:
        return {"": ordered}
    shards: dict[str, list[dict[str, object]]] = {}
    for document in ordered:
        initial = _stub_name_of(document)[:1].lower()
        shards.setdefault(initial if initial.isalnum() else "other", []).append(
            document
        )
    return shards


def _stub_name_of(document: dict[str, object]) -> str:
    """Sort key / shard key for one member."""
    return _stub_name(document=document)


def _stub_name(*, document: dict[str, object]) -> str:
    """The view stub's filename: readable, deterministic, collision-free."""
    title = str(document.get("title") or "untitled")
    return f"{_slug(title)}-{str(document['doc_id'])[:8]}.md"


def _document_stub(
    *, document: dict[str, object], canonical_path: str, view_path: str | None = None
) -> str:
    """One generated stub: orientation + canonical path + artifact pointer.

    `grep -r` over stubs is content-ish lookup with zero API calls, so the
    title, summary, and pointers are IN the file — and every view stub
    names its Tier-1 canonical path, so a reorganized view never loses the
    document.
    """
    summary = str(document.get("root_summary") or "").strip()
    frontmatter = {
        "doc_id": str(document["doc_id"]),
        "canonical_path": canonical_path,
        "version_id": str(document.get("version_id") or ""),
        "content_hash": str(document.get("content_hash") or ""),
        "artifact_uri": str(document.get("markdown_uri") or ""),
        "source_kind": str(document.get("source_kind") or ""),
        "source_ref": str(document.get("source_ref") or ""),
    }
    if view_path is not None:
        frontmatter["view_path"] = view_path
    lines = ["---"]
    lines.extend(f"{key}: {value}" for key, value in frontmatter.items())
    lines.append("---")
    lines.append("")
    lines.append(f"# {document.get('title') or 'Untitled document'}")
    lines.append("")
    if summary:
        lines.append(summary)
        lines.append("")
    lines.append(f"- Canonical path: `{canonical_path}/`")
    lines.append(f"- Full text: `{document.get('markdown_uri') or '(not converted)'}`")
    lines.append("")
    return "\n".join(lines)


def _entity_index(
    *, entity: dict[str, object], documents: list[dict[str, object]]
) -> str:
    """An entity's Tier-1 page: profile plus the documents evidencing it."""
    lines = [
        "---",
        f"entity_id: {entity['entity_id']}",
        f"type: {entity['type']}",
        f"canonical_path: {_entity_path(entity_id=UUID(str(entity['entity_id'])), entity_type=str(entity['type']))}",
        "---",
        "",
        f"# {entity['canonical_name']}",
        "",
        f"{entity['type']} · {entity.get('mention_count') or 0} mention(s)"
        f" · graph degree {entity.get('graph_degree') or 0}",
        "",
    ]
    profile = str(entity.get("profile_summary") or "").strip()
    if profile:
        lines.extend([profile, ""])
    lines.append("## Documents mentioning this entity")
    lines.append("")
    lines.extend(_member_table(members=documents))
    return "\n".join(lines)


def _directory_index(*, directory: str, members: list[dict[str, object]]) -> str:
    """The member table: every file's one-line meaning, from Postgres.

    This is the load-bearing property of the tree — one read tells an agent
    what everything here is about. Deterministic by contract: no LLM call
    lives inside the projection builder (a directory-level synthesis is a K
    page's job, e0 §6).
    """
    sources = sorted({str(member["source_kind"]) for member in members})
    stamps = [
        member.get("source_modified_at") or member.get("published_at")
        for member in members
    ]
    dated = sorted(stamp for stamp in stamps if isinstance(stamp, datetime))
    span = f" · {dated[0].date()}–{dated[-1].date()}" if dated else ""
    lines = [
        f"# {directory}",
        "",
        f"{len(members)} document(s) · sources: {', '.join(sources)}{span}",
        "",
        "## Contents",
        "",
    ]
    lines.extend(_member_table(members=members))
    lines.extend(
        [
            "",
            "## Navigation",
            "",
            f"- Parent: `{PurePosixPath(directory).parent}/{INDEX_FILE}`",
            "- Canonical (never-moving) paths for these documents are in each"
            " stub's `canonical_path` frontmatter.",
            "",
        ]
    )
    return "\n".join(lines)


def _member_table(*, members: Iterable[dict[str, object]]) -> list[str]:
    """One row per child carrying its root summary — navigation, not search."""
    rows = ["| File | What it is | Source | Date |", "|---|---|---|---|"]
    for member in sorted(members, key=_stub_name_of):
        summary = " ".join(str(member.get("root_summary") or "").split())[:160]
        stamp = member.get("source_modified_at") or member.get("published_at")
        date = stamp.date().isoformat() if isinstance(stamp, datetime) else "—"
        rows.append(
            f"| `{_stub_name(document=member)}` | {summary or '—'} |"
            f" {member.get('source_kind') or '—'} | {date} |"
        )
    if len(rows) == 2:
        rows.append("| — | (empty) | — | — |")
    return rows


def _directory_manifest(*, directory: str, members: list[dict[str, object]]) -> str:
    """`llms.txt`: orientation before contents (the navigation-manifest pattern)."""
    lines = [
        f"# {directory}",
        "",
        f"> {len(members)} document(s). Read {INDEX_FILE} for the member table"
        " — every file's one-line meaning — before opening any file.",
        "",
        "## Files",
        "",
    ]
    lines.extend(
        f"- [{_stub_name(document=member)}]({_stub_name(document=member)}):"
        f" {' '.join(str(member.get('root_summary') or '').split())[:120] or 'no summary'}"
        for member in sorted(members, key=_stub_name_of)
    )
    lines.append("")
    return "\n".join(lines)


def _facet_indexes(
    *,
    files: dict[str, str],
    documents: tuple[dict[str, object], ...],
    entities: tuple[dict[str, object], ...],
    views: dict[str, list[dict[str, object]]],
) -> dict[str, str]:
    """Facet-level and root orientation — the top of the navigation ladder."""
    rendered: dict[str, str] = {}
    facets: dict[str, set[str]] = {}
    for view_path in views:
        facet = view_path.split("/", 1)[0]
        facets.setdefault(facet, set()).add(view_path)
    for facet, paths in facets.items():
        listing = "\n".join(
            f"- `{path}/` — {len(views[path])} document(s)" for path in sorted(paths)
        )
        rendered[f"{facet}/{INDEX_FILE}"] = (
            f"# {facet}\n\n{len(paths)} view(s) in this facet.\n\n{listing}\n"
        )
    rendered[f"documents/{INDEX_FILE}"] = (
        "# documents\n\nCanonical (Tier 1) document leaves — these paths never"
        f" move across rebuilds.\n\n{len(documents)} lineage(s).\n"
    )
    rendered[f"entities/{INDEX_FILE}"] = (
        "# entities\n\nCanonical (Tier 1) entity leaves — these paths never move"
        f" across rebuilds.\n\n{len(entities)} active entity/entities.\n"
    )
    rendered[MANIFEST_FILE] = _root_manifest(
        documents=documents, entities=entities, facets=sorted(facets)
    )
    rendered[INDEX_FILE] = (
        "# Corpus\n\n"
        f"{len(documents)} document(s), {len(entities)} entity/entities.\n\n"
        "## How to navigate\n\n"
        "1. `cat llms.txt` — facets and where things live.\n"
        f"2. `cat <facet>/{INDEX_FILE}` — what kinds of things exist there.\n"
        f"3. `cat <directory>/{INDEX_FILE}` — the member table: every file's\n"
        "   one-line meaning.\n"
        "4. `cat <stub>.md` — orientation, canonical path, artifact pointer.\n\n"
        "Durable paths live under `documents/` and `entities/` (Tier 1) and\n"
        "never move; view subtrees reorganize as the corpus grows.\n"
    )
    return rendered


def _root_manifest(
    *,
    documents: tuple[dict[str, object], ...],
    entities: tuple[dict[str, object], ...],
    facets: list[str],
) -> str:
    """The root orientation file an agent reads first."""
    lines = [
        "# Corpus filesystem",
        "",
        "> A generated, rebuildable view over the memory's documents and"
        " entities. Nothing here is source of truth; every file names the"
        " artifact it points at.",
        "",
        f"- {len(documents)} document lineage(s)",
        f"- {len(entities)} active entity/entities",
        "",
        "## Facets",
        "",
    ]
    lines.extend(f"- `{facet}/` (view paths — reorganizable)" for facet in facets)
    lines.extend(
        [
            "- `documents/` (canonical, stable per lineage)",
            "- `entities/` (canonical, stable per entity)",
            "",
            "## Contract",
            "",
            "Paths under `documents/` and `entities/` are stable across"
            " rebuilds and safe to store. View paths may reorganize; every"
            " view stub carries its canonical path in frontmatter.",
            "",
        ]
    )
    return "\n".join(lines)


def _slug(value: str) -> str:
    """A filesystem-safe, deterministic slug."""
    cleaned = "".join(
        character.lower() if character.isalnum() else "-" for character in value.strip()
    )
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "untitled"
