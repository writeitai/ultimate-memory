"""Typed records for the D22 evaluation harness: suites, canaries, reports."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict


class EvalSuite(StrEnum):
    """Exact values of the binding Postgres ``eval_suite`` enum."""

    RESOLUTION = "resolution"
    SELECTION = "selection"
    GROUNDING = "grounding"
    RETRIEVAL = "retrieval"
    CONTRADICTION = "contradiction"
    LIFECYCLE = "lifecycle"  # appended (ALTER TYPE ADD VALUE lands last)


class CanaryCase(BaseModel):
    """One known-tricky regression case re-run per version (registries §10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canary_id: UUID
    suite: EvalSuite
    description: str
    input: dict[str, object]
    expected: dict[str, object]


class CaseFailure(BaseModel):
    """One failed case with the reason a reviewer needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canary_id: UUID
    description: str
    reason: str


class SuiteReport(BaseModel):
    """One suite run: totals, failures, and the pass verdict CI gates on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suite: EvalSuite
    total_cases: int
    failures: tuple[CaseFailure, ...]

    @property
    def passed(self) -> bool:
        """A suite passes only with zero failures (empty suites pass)."""
        return not self.failures


class LifecycleReport(BaseModel):
    """One lifecycle-suite run: invariant verdicts + the flag-rate metric.

    ``passed`` reflects the invariants alone; the flag rate is the watched
    rollout canary (its alarm threshold is an operations decision).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    quiescent: bool = True  # count/closure checks defer while mid-flight
    violations: dict[str, tuple[str, ...]] = {}
    canary_failures: tuple[str, ...] = ()
    flag_rate_by_extractor: dict[str, dict[str, float]] = {}
