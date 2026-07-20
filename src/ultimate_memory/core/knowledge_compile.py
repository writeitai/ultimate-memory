"""Pure scheduling and output-validation rules for Plane-K cycles (D45)."""

from collections.abc import Collection
from collections.abc import Sequence
import posixpath
from urllib.parse import unquote
from urllib.parse import urlsplit
from uuid import UUID

from markdown_it import MarkdownIt

from ultimate_memory.core.knowledge_hashing import knowledge_content_hash
from ultimate_memory.model import KnowledgeCitation
from ultimate_memory.model import KnowledgeCompileArtifact
from ultimate_memory.model import KnowledgeEvidenceTarget
from ultimate_memory.model import KnowledgePageCompileOutput


class KnowledgeCompileGraphError(ValueError):
    """The persisted compiled-page parent graph cannot be scheduled safely."""


class KnowledgePageValidationError(ValueError):
    """A page compiler returned output that the driver must not publish."""


def knowledge_compile_order(
    *, artifacts: Sequence[KnowledgeCompileArtifact]
) -> tuple[KnowledgeCompileArtifact, ...]:
    """Order the potential stale/model propagation closure deterministically.

    Active ancestors are traversed because a changed child summary can stale them
    inside this cycle. Likewise, a stale shared model can stale every page in its
    scope. The driver skips those potential dependants when the freshly compiled
    summary is unchanged.
    """
    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    if len(by_id) != len(artifacts):
        raise KnowledgeCompileGraphError(
            "compile graph contains duplicate artifact IDs"
        )
    deployments = {artifact.deployment_id for artifact in artifacts}
    if len(deployments) > 1:
        raise KnowledgeCompileGraphError("compile graph crosses deployments")
    model_scopes = [
        artifact.scope_id
        for artifact in artifacts
        if artifact.artifact_kind == "model_page"
    ]
    if len(model_scopes) != len(set(model_scopes)):
        raise KnowledgeCompileGraphError(
            "compile graph has multiple model pages for one scope"
        )

    depths: dict[UUID, int] = {}
    visiting: set[UUID] = set()

    def depth(*, artifact_id: UUID) -> int:
        """Resolve one node's root distance while detecting parent cycles."""
        known = depths.get(artifact_id)
        if known is not None:
            return known
        if artifact_id in visiting:
            raise KnowledgeCompileGraphError("compile graph contains a parent cycle")
        visiting.add(artifact_id)
        parent_id = by_id[artifact_id].parent_artifact_id
        value = (
            0
            if parent_id is None or parent_id not in by_id
            else depth(artifact_id=parent_id) + 1
        )
        visiting.remove(artifact_id)
        depths[artifact_id] = value
        return value

    for artifact_id in by_id:
        depth(artifact_id=artifact_id)

    selected = {artifact.artifact_id for artifact in artifacts if artifact.stale}
    stale_model_scopes = {
        artifact.scope_id
        for artifact in artifacts
        if artifact.stale and artifact.artifact_kind == "model_page"
    }
    selected.update(
        artifact.artifact_id
        for artifact in artifacts
        if artifact.scope_id in stale_model_scopes
    )
    frontier = list(selected)
    while frontier:
        artifact_id = frontier.pop()
        parent_id = by_id[artifact_id].parent_artifact_id
        if parent_id is not None and parent_id in by_id and parent_id not in selected:
            selected.add(parent_id)
            frontier.append(parent_id)

    scheduled = (artifact for artifact in artifacts if artifact.artifact_id in selected)
    return tuple(
        sorted(
            scheduled,
            key=lambda artifact: (
                (
                    0
                    if artifact.artifact_kind == "model_page" and artifact.stale
                    else 2
                    if artifact.parent_artifact_id is None
                    and artifact.git_path == "_index.md"
                    else 1
                ),
                -depths[artifact.artifact_id],
                artifact.git_path,
                str(artifact.artifact_id),
            ),
        )
    )


def validate_knowledge_page_output(
    *,
    artifact: KnowledgeCompileArtifact,
    output: KnowledgePageCompileOutput,
    known_git_paths: Collection[str],
    exclusions: Collection[KnowledgeEvidenceTarget],
) -> None:
    """Enforce artifact binding, content hash, exclusions, and internal links."""
    compilation = output.compilation
    if compilation.deployment_id != artifact.deployment_id:
        raise KnowledgePageValidationError("compilation crosses deployments")
    if compilation.artifact_id != artifact.artifact_id:
        raise KnowledgePageValidationError("compilation targets a different artifact")
    if compilation.content_hash != knowledge_content_hash(markdown=output.markdown):
        raise KnowledgePageValidationError(
            "compiled Markdown content hash does not match"
        )

    excluded = {_target_key(target=target) for target in exclusions}
    used = {
        _citation_target_key(citation=citation) for citation in compilation.citations
    }
    if overlap := excluded.intersection(used):
        rendered = ", ".join(f"{kind}:{value}" for kind, value in sorted(overlap))
        raise KnowledgePageValidationError(
            f"compiled page cites excluded evidence: {rendered}"
        )

    unresolved = _unresolved_internal_links(
        markdown=output.markdown,
        source_path=artifact.git_path,
        known_git_paths=known_git_paths,
    )
    if unresolved:
        raise KnowledgePageValidationError(
            f"compiled page has unresolved internal links: {', '.join(unresolved)}"
        )


def _target_key(*, target: KnowledgeEvidenceTarget) -> tuple[str, str]:
    """Return the role-independent identity of one exclusion target."""
    if target.claim_id is not None:
        return "claim", str(target.claim_id)
    if target.relation_id is not None:
        return "relation", str(target.relation_id)
    if target.doc_id is not None:
        return "doc", str(target.doc_id)
    raise AssertionError("validated evidence target has no ID")


def _citation_target_key(*, citation: KnowledgeCitation) -> tuple[str, str]:
    """Return the role-independent identity of one citation target."""
    if citation.claim_id is not None:
        return "claim", str(citation.claim_id)
    if citation.relation_id is not None:
        return "relation", str(citation.relation_id)
    if citation.doc_id is not None:
        return "doc", str(citation.doc_id)
    raise AssertionError("validated citation has no ID")


def _unresolved_internal_links(
    *, markdown: str, source_path: str, known_git_paths: Collection[str]
) -> tuple[str, ...]:
    """Return relative Markdown links that do not resolve to registered artifacts."""
    known = set(known_git_paths)
    unresolved: set[str] = set()
    for block in MarkdownIt("commonmark").parse(markdown):
        tokens = (block, *(block.children or ()))
        for token in tokens:
            if token.type != "link_open":
                continue
            href = token.attrGet("href")
            if not isinstance(href, str):
                continue
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            raw_path = unquote(parsed.path)
            if raw_path.startswith("/"):
                resolved = posixpath.normpath(raw_path.lstrip("/"))
            else:
                resolved = posixpath.normpath(
                    posixpath.join(posixpath.dirname(source_path), raw_path)
                )
            if resolved == ".." or resolved.startswith("../") or resolved not in known:
                unresolved.add(href)
    return tuple(sorted(unresolved))
