"""WP-6.2 pure scheduling and compiled-page validation proofs."""

from uuid import UUID
from uuid import uuid4

import pytest

from ultimate_memory.core import knowledge_compile_order
from ultimate_memory.core import knowledge_content_hash
from ultimate_memory.core import KnowledgeCompileGraphError
from ultimate_memory.core import KnowledgePageValidationError
from ultimate_memory.core import validate_knowledge_page_output
from ultimate_memory.model import KnowledgeCitation
from ultimate_memory.model import KnowledgeCompilationWrite
from ultimate_memory.model import KnowledgeCompileArtifact
from ultimate_memory.model import KnowledgeEvidenceRole
from ultimate_memory.model import KnowledgeEvidenceTarget
from ultimate_memory.model import KnowledgePageCompileOutput

_DEPLOYMENT_ID = UUID("62000000-0000-0000-0000-000000000001")


def _artifact(
    *,
    git_path: str,
    parent_artifact_id: UUID | None = None,
    artifact_kind: str | None = None,
    scope_id: UUID | None = None,
    stale: bool = True,
) -> KnowledgeCompileArtifact:
    """Build one compact scheduler node."""
    return KnowledgeCompileArtifact(
        artifact_id=uuid4(),
        deployment_id=_DEPLOYMENT_ID,
        scope_id=scope_id,
        parent_artifact_id=parent_artifact_id,
        git_path=git_path,
        artifact_kind=artifact_kind,
        stale=stale,
    )


def _output(
    *,
    artifact: KnowledgeCompileArtifact,
    markdown: str,
    citations: tuple[KnowledgeCitation, ...] = (),
) -> KnowledgePageCompileOutput:
    """Build one hash-bound compiler result."""
    return KnowledgePageCompileOutput(
        compilation=KnowledgeCompilationWrite(
            compilation_id=uuid4(),
            deployment_id=artifact.deployment_id,
            artifact_id=artifact.artifact_id,
            inputs_hash="0" * 64,
            candidate_count=len(citations),
            uncited_count=0,
            citations=citations,
            writer_version="writer-test",
            page_summary="A concise test summary.",
            content_hash=knowledge_content_hash(markdown=markdown),
        ),
        markdown=markdown,
    )


def test_compile_order_is_model_then_deepest_children_then_root() -> None:
    """Active siblings stay out while stale propagation ancestors enter the batch."""
    root = _artifact(git_path="_index.md")
    parent = _artifact(git_path="topics/parent.md", parent_artifact_id=root.artifact_id)
    child = _artifact(git_path="topics/child.md", parent_artifact_id=parent.artifact_id)
    active_sibling = _artifact(
        git_path="topics/current.md", parent_artifact_id=parent.artifact_id, stale=False
    )
    model = _artifact(git_path="model.md", artifact_kind="model_page", scope_id=uuid4())

    assert knowledge_compile_order(
        artifacts=(root, active_sibling, child, model, parent)
    ) == (model, child, parent, root)


def test_compile_order_includes_active_ancestors_of_stale_child() -> None:
    """A child summary change can be propagated to active parents in this cycle."""
    root = _artifact(git_path="_index.md", stale=False)
    parent = _artifact(
        git_path="topics/parent.md", parent_artifact_id=root.artifact_id, stale=False
    )
    child = _artifact(git_path="topics/child.md", parent_artifact_id=parent.artifact_id)
    unrelated = _artifact(git_path="unrelated.md", stale=False)

    assert knowledge_compile_order(artifacts=(root, unrelated, child, parent)) == (
        child,
        parent,
        root,
    )


def test_compile_order_puts_top_level_index_after_other_roots() -> None:
    """The deployment root index remains the final page even in a forest."""
    root_index = _artifact(git_path="_index.md")
    other_root = _artifact(git_path="topic.md")

    assert knowledge_compile_order(artifacts=(root_index, other_root)) == (
        other_root,
        root_index,
    )


def test_compile_order_rejects_ambiguous_shared_model() -> None:
    """One scope cannot provide two different shared model summaries."""
    scope_id = uuid4()
    first = _artifact(
        git_path="first-model.md", artifact_kind="model_page", scope_id=scope_id
    )
    second = _artifact(
        git_path="second-model.md", artifact_kind="model_page", scope_id=scope_id
    )

    with pytest.raises(KnowledgeCompileGraphError, match="multiple model pages"):
        knowledge_compile_order(artifacts=(first, second))


def test_compile_order_rejects_parent_cycle() -> None:
    """A corrupt graph fails before any compiler or git writer is invoked."""
    first = _artifact(git_path="first.md")
    second = _artifact(git_path="second.md", parent_artifact_id=first.artifact_id)
    first = first.model_copy(update={"parent_artifact_id": second.artifact_id})

    with pytest.raises(KnowledgeCompileGraphError, match="parent cycle"):
        knowledge_compile_order(artifacts=(first, second))


def test_page_validation_accepts_resolved_and_external_links() -> None:
    """Relative/root links resolve against registered artifact paths; URLs need not."""
    artifact = _artifact(git_path="topics/source.md")
    markdown = (
        "[Sibling](sibling.md#detail) [Root](/_index.md) "
        "[External](https://example.com) [Here](#section)\n"
    )

    validate_knowledge_page_output(
        artifact=artifact,
        output=_output(artifact=artifact, markdown=markdown),
        known_git_paths=("topics/source.md", "topics/sibling.md", "_index.md"),
        exclusions=(),
    )


@pytest.mark.parametrize(
    "markdown",
    (
        "[Missing](missing.md)\n",
        "[Escape](../../outside.md)\n",
        "[Encoded escape](%2e%2e/%2e%2e/outside.md)\n",
    ),
)
def test_page_validation_rejects_unresolved_internal_links(markdown: str) -> None:
    """Neither absent targets nor repository escapes can enter a published page."""
    artifact = _artifact(git_path="topics/source.md")

    with pytest.raises(KnowledgePageValidationError, match="unresolved internal"):
        validate_knowledge_page_output(
            artifact=artifact,
            output=_output(artifact=artifact, markdown=markdown),
            known_git_paths=("topics/source.md",),
            exclusions=(),
        )


def test_page_validation_rejects_excluded_citation_and_hash_drift() -> None:
    """Curation exclusions and the exact body hash are mechanical publish gates."""
    artifact = _artifact(git_path="source.md")
    claim_id = uuid4()
    output = _output(
        artifact=artifact,
        markdown="# Source\n",
        citations=(
            KnowledgeCitation(role=KnowledgeEvidenceRole.SUPPORTS, claim_id=claim_id),
        ),
    )

    with pytest.raises(KnowledgePageValidationError, match="excluded evidence"):
        validate_knowledge_page_output(
            artifact=artifact,
            output=output,
            known_git_paths=(artifact.git_path,),
            exclusions=(KnowledgeEvidenceTarget(claim_id=claim_id),),
        )

    drifted = output.model_copy(update={"markdown": "# Changed after hashing\n"})
    with pytest.raises(KnowledgePageValidationError, match="content hash"):
        validate_knowledge_page_output(
            artifact=artifact,
            output=drifted,
            known_git_paths=(artifact.git_path,),
            exclusions=(),
        )
