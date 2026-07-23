"""The stock self-host profile exposes the complete implemented runtime shape."""

from pathlib import Path
import re

from rememberstack.model import PipelineStage
from rememberstack.profiles.selfhost import _expected_components
from rememberstack.profiles.selfhost import _SUPPORTED_WORKER_STAGES

_ROOT = Path(__file__).resolve().parents[3]


def test_selfhost_composes_every_implemented_continuous_route() -> None:
    """Ten real handlers run; enum-only/fused stages do not get dummy workers."""
    assert _SUPPORTED_WORKER_STAGES == (
        PipelineStage.CONVERT,
        PipelineStage.STRUCTURE,
        PipelineStage.CHUNK,
        PipelineStage.EMBED_CHUNK,
        PipelineStage.EXTRACT_CLAIMS,
        PipelineStage.NORMALIZE_RELATIONS,
        PipelineStage.ADJUDICATE_SUPERSESSION,
        PipelineStage.EMBED_CLAIM,
        PipelineStage.RECONCILE,
        PipelineStage.LABEL_RELATION,
    )
    assert tuple(_expected_components()) == _SUPPORTED_WORKER_STAGES


def test_enum_only_and_fused_stages_are_not_advertised_as_workers() -> None:
    """A stage enum is not proof that an independently runnable handler exists."""
    assert {
        PipelineStage.GROUND_CLAIMS,
        PipelineStage.RESOLVE_ENTITIES,
        PipelineStage.ADJUDICATE_OBSERVATIONS,
        PipelineStage.EMBED_RELATION,
        PipelineStage.EMBED_OBSERVATION,
        PipelineStage.LABEL_OBSERVATION,
        PipelineStage.CROSSREF,
        PipelineStage.REFRESH_PROFILE,
    }.isdisjoint(_SUPPORTED_WORKER_STAGES)


def test_compose_wires_the_exact_supported_worker_set_and_projection_job() -> None:
    """Keep deployable Compose wiring in lockstep with the executable profile."""
    compose = (_ROOT / "compose.yaml").read_text(encoding="utf-8")
    composed_stages = tuple(
        PipelineStage(value)
        for value in re.findall(r'command: \["worker", "--stage", "([^"]+)"\]', compose)
    )

    assert composed_stages == _SUPPORTED_WORKER_STAGES
    assert 'profiles: ["operations"]' in compose
    assert 'command: ["project", "--plane", "all"]' in compose
