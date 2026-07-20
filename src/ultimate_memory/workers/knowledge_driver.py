"""Deterministic Plane-K routing, scheduling, and single-commit driver."""

from collections.abc import Collection
from collections.abc import Mapping
from pathlib import Path
from pathlib import PurePosixPath
from tempfile import TemporaryDirectory
import traceback
from typing import Protocol
from uuid import UUID
from uuid import uuid4

from ultimate_memory.core import knowledge_compile_order
from ultimate_memory.core import knowledge_content_hash
from ultimate_memory.core import validate_knowledge_page_output
from ultimate_memory.model import KnowledgeCommitCycleResult
from ultimate_memory.model import KnowledgeCompilationFailure
from ultimate_memory.model import KnowledgeCompileArtifact
from ultimate_memory.model import KnowledgeCompileContext
from ultimate_memory.model import KnowledgeEvidenceDelta
from ultimate_memory.model import KnowledgeEvidenceTarget
from ultimate_memory.model import KnowledgePageCompileOutput
from ultimate_memory.model import KnowledgePageCompileRequest
from ultimate_memory.model import KnowledgePendingCycle
from ultimate_memory.ports import KGitRemotePort
from ultimate_memory.spine.knowledge import KnowledgeControlPlane


class KnowledgePageCompiler(Protocol):
    """The future WP-6.3/6.4 page compiler consumed by this mechanical loop."""

    def compile_page(
        self, *, request: KnowledgePageCompileRequest
    ) -> KnowledgePageCompileOutput:
        """Return one structured page without publishing or mutating another page."""
        ...


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


class KnowledgeCommitDriver:
    """Compile a dependency-ordered batch and publish it through one git writer."""

    def __init__(
        self,
        *,
        control_plane: KnowledgeControlPlane,
        git_remote: KGitRemotePort,
        compiler: KnowledgePageCompiler,
    ) -> None:
        """Bind the commit loop to its Postgres, git, and page-compiler seams."""
        self._control_plane = control_plane
        self._git_remote = git_remote
        self._compiler = compiler

    def run_cycle(
        self,
        *,
        deployment_id: UUID,
        exclusions_by_artifact: Mapping[UUID, Collection[KnowledgeEvidenceTarget]],
    ) -> KnowledgeCommitCycleResult:
        """Recover prior work, compile stale pages, publish once, then finalize."""
        with self._control_plane.commit_lease(deployment_id=deployment_id):
            with TemporaryDirectory(prefix="ugm-k-cycle-") as temporary:
                worktree = Path(temporary)
                checkout = self._git_remote.checkout(destination=worktree)
                recovered = self._recover_pending_cycles(
                    deployment_id=deployment_id,
                    worktree=worktree,
                    git_revision=checkout.root,
                )
                artifacts = self._control_plane.compile_artifacts(
                    deployment_id=deployment_id
                )
                schedule = knowledge_compile_order(artifacts=artifacts)
                if not schedule:
                    return KnowledgeCommitCycleResult(
                        checkout_revision=checkout.root, recovered_cycle_ids=recovered
                    )

                known_paths = self._control_plane.artifact_git_paths(
                    deployment_id=deployment_id
                )
                compiled = self._compile_schedule(
                    artifacts=artifacts,
                    schedule=schedule,
                    known_paths=known_paths,
                    worktree=worktree,
                    exclusions_by_artifact=exclusions_by_artifact,
                )
                for artifact, output in compiled:
                    _write_compiled_page(
                        worktree=worktree,
                        git_path=artifact.git_path,
                        markdown=output.markdown,
                    )

                cycle_id = uuid4()
                compilations = tuple(output.compilation for _, output in compiled)
                self._control_plane.record_pending_compilations(
                    cycle_id=cycle_id, compilations=compilations
                )
                published = self._git_remote.publish(worktree=worktree)
                self._control_plane.commit_compilations(
                    compilations=compilations, git_commit=published.root
                )
                return KnowledgeCommitCycleResult(
                    checkout_revision=checkout.root,
                    published_revision=published.root,
                    compiled_artifact_ids=tuple(
                        artifact.artifact_id for artifact, _ in compiled
                    ),
                    recovered_cycle_ids=recovered,
                )

    def _recover_pending_cycles(
        self, *, deployment_id: UUID, worktree: Path, git_revision: str
    ) -> tuple[UUID, ...]:
        """Finalize cycles present at HEAD and abandon those never published."""
        artifacts = {
            artifact.artifact_id: artifact
            for artifact in self._control_plane.compile_artifacts(
                deployment_id=deployment_id
            )
        }
        recovered: list[UUID] = []
        for cycle in self._control_plane.pending_cycles(deployment_id=deployment_id):
            if _pending_cycle_matches_worktree(
                cycle=cycle, artifacts=artifacts, worktree=worktree
            ):
                self._control_plane.commit_compilations(
                    compilations=cycle.compilations, git_commit=git_revision
                )
                recovered.append(cycle.cycle_id)
            else:
                self._control_plane.fail_pending_cycle(
                    deployment_id=deployment_id,
                    cycle_id=cycle.cycle_id,
                    failure="remote HEAD does not contain the pending cycle output",
                )
        return tuple(recovered)

    def _compile_schedule(
        self,
        *,
        artifacts: tuple[KnowledgeCompileArtifact, ...],
        schedule: tuple[KnowledgeCompileArtifact, ...],
        known_paths: Collection[str],
        worktree: Path,
        exclusions_by_artifact: Mapping[UUID, Collection[KnowledgeEvidenceTarget]],
    ) -> tuple[tuple[KnowledgeCompileArtifact, KnowledgePageCompileOutput], ...]:
        """Invoke one-page compilers in order while carrying fresh summaries forward."""
        summaries = {
            artifact.artifact_id: artifact.page_summary
            for artifact in artifacts
            if artifact.page_summary is not None
        }
        model_summaries: dict[UUID | None, str] = {
            artifact.scope_id: artifact.page_summary
            for artifact in artifacts
            if artifact.artifact_kind == "model_page"
            and artifact.page_summary is not None
        }
        changed_summaries: set[UUID] = set()
        changed_model_scopes: set[UUID | None] = set()
        outputs: list[tuple[KnowledgeCompileArtifact, KnowledgePageCompileOutput]] = []
        for artifact in schedule:
            child_ids = {
                child.artifact_id
                for child in artifacts
                if child.parent_artifact_id == artifact.artifact_id
            }
            model_changed = (
                artifact.artifact_kind != "model_page"
                and artifact.scope_id in changed_model_scopes
            )
            if not (
                artifact.stale
                or child_ids.intersection(changed_summaries)
                or model_changed
            ):
                continue
            child_summaries = {
                child.artifact_id: summaries[child.artifact_id]
                for child in artifacts
                if child.artifact_id in child_ids and child.artifact_id in summaries
            }
            exclusions = tuple(exclusions_by_artifact.get(artifact.artifact_id, ()))
            previous_markdown = _read_optional_compiler_input(
                worktree=worktree, git_path=artifact.git_path
            )
            curation_markdown = (
                None
                if artifact.curation_path is None
                else _read_optional_compiler_input(
                    worktree=worktree, git_path=artifact.curation_path
                )
            )
            output = self._compiler.compile_page(
                request=KnowledgePageCompileRequest(
                    artifact=artifact,
                    child_summaries=child_summaries,
                    shared_model_summary=(
                        None
                        if artifact.artifact_kind == "model_page"
                        else model_summaries.get(artifact.scope_id)
                    ),
                    curation_hash=(
                        None
                        if curation_markdown is None
                        else knowledge_content_hash(markdown=curation_markdown)
                    ),
                    curation_markdown=curation_markdown,
                    previous_markdown=previous_markdown,
                    exclusions=exclusions,
                )
            )
            try:
                validate_knowledge_page_output(
                    artifact=artifact,
                    output=output,
                    known_git_paths=known_paths,
                    exclusions=exclusions,
                )
                self._control_plane.validate_citations(
                    deployment_id=artifact.deployment_id,
                    citations=output.compilation.citations,
                )
            except Exception as error:
                compilation = output.compilation
                failure_trace = traceback.format_exc()
                try:
                    self._control_plane.record_failed_compilation(
                        failure=KnowledgeCompilationFailure(
                            compilation_id=compilation.compilation_id,
                            deployment_id=compilation.deployment_id,
                            artifact_id=compilation.artifact_id,
                            inputs_hash=compilation.inputs_hash,
                            candidate_count=compilation.candidate_count,
                            claims_cut_count=compilation.claims_cut_count,
                            writer_version=compilation.writer_version,
                            failure=failure_trace,
                            session_transcript_uri=compilation.session_transcript_uri,
                        )
                    )
                except Exception as ledger_error:
                    raise ExceptionGroup(
                        "page validation and failure-ledger recording both failed",
                        (error, ledger_error),
                    ) from None
                raise
            new_summary = output.compilation.page_summary
            if new_summary != artifact.page_summary:
                changed_summaries.add(artifact.artifact_id)
                if artifact.artifact_kind == "model_page":
                    changed_model_scopes.add(artifact.scope_id)
            summaries[artifact.artifact_id] = new_summary
            if artifact.artifact_kind == "model_page":
                model_summaries[artifact.scope_id] = new_summary
            outputs.append((artifact, output))
        return tuple(outputs)


def _pending_cycle_matches_worktree(
    *,
    cycle: KnowledgePendingCycle,
    artifacts: Mapping[UUID, KnowledgeCompileArtifact],
    worktree: Path,
) -> bool:
    """Return whether remote HEAD contains every exact pending page body."""
    for compilation in cycle.compilations:
        artifact = artifacts.get(compilation.artifact_id)
        if artifact is None:
            return False
        try:
            target = _worktree_target(worktree=worktree, git_path=artifact.git_path)
        except ValueError:
            return False
        if not target.is_file():
            return False
        try:
            markdown = target.read_text(encoding="utf-8")
        except UnicodeError:
            return False
        if knowledge_content_hash(markdown=markdown) != compilation.content_hash:
            return False
    return True


def _write_compiled_page(*, worktree: Path, git_path: str, markdown: str) -> None:
    """Atomically replace one validated path inside the disposable checkout."""
    target = _worktree_target(worktree=worktree, git_path=git_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4()}.tmp")
    temporary.write_text(markdown, encoding="utf-8")
    temporary.replace(target)


def _read_optional_compiler_input(*, worktree: Path, git_path: str) -> str | None:
    """Read one repository-native compiler input without widening its path surface."""
    target = _worktree_target(worktree=worktree, git_path=git_path)
    if not target.is_file():
        return None
    return target.read_text(encoding="utf-8")


def _worktree_target(*, worktree: Path, git_path: str) -> Path:
    """Map a validated repository-native POSIX path into a local checkout."""
    target = worktree.joinpath(*PurePosixPath(git_path).parts)
    root = worktree.resolve()
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError(f"compiled page path escapes worktree: {git_path}")
    return target
