"""The evaluation-harness skeleton (WP-0.5, D22): suites over golden canaries.

The harness loads a suite's canary cases from the spine, evaluates each with
the suite's registered evaluator, records the run in `eval_runs`, and returns
a report CI gates on. A suite with cases but no registered evaluator fails
those cases — absence of measurement is never compliance. Real evaluators
arrive with their phases; this skeleton owns loading, reporting, and the
CI-blocking contract.
"""

from collections.abc import Callable
from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.model import CanaryCase
from ultimate_memory.model import CaseFailure
from ultimate_memory.model import EvalSuite
from ultimate_memory.model import SuiteReport

CaseEvaluator = Callable[[CanaryCase], bool]
"""Evaluates one canary: True = the guarded behavior holds."""


class EvalHarness:
    """Run evaluation suites over the golden canaries and record the history."""

    def __init__(self, *, engine: Engine) -> None:
        """Bind the harness to the spine; evaluators register per suite."""
        self._engine = engine
        self._evaluators: dict[EvalSuite, CaseEvaluator] = {}

    def register_evaluator(self, *, suite: EvalSuite, evaluator: CaseEvaluator) -> None:
        """Bind a suite's evaluator (phases plug their real logic in here)."""
        self._evaluators[suite] = evaluator

    def run_suite(
        self, *, deployment_id: UUID, suite: EvalSuite, component_version: str
    ) -> SuiteReport:
        """Evaluate every canary in the suite and persist the run's verdict."""
        cases = self._load_cases(deployment_id=deployment_id, suite=suite)
        failures = tuple(
            failure
            for case in cases
            if (failure := self._evaluate(case=case)) is not None
        )
        report = SuiteReport(suite=suite, total_cases=len(cases), failures=failures)
        self._record_run(
            deployment_id=deployment_id,
            report=report,
            component_version=component_version,
        )
        return report

    def _evaluate(self, *, case: CanaryCase) -> CaseFailure | None:
        """Run one canary; no registered evaluator is itself a failure."""
        evaluator = self._evaluators.get(case.suite)
        if evaluator is None:
            return CaseFailure(
                canary_id=case.canary_id,
                description=case.description,
                reason=f"no evaluator registered for suite {case.suite}",
            )
        if evaluator(case):
            return None
        return CaseFailure(
            canary_id=case.canary_id,
            description=case.description,
            reason="guarded behavior does not hold",
        )

    def _load_cases(
        self, *, deployment_id: UUID, suite: EvalSuite
    ) -> tuple[CanaryCase, ...]:
        """Load the suite's canaries from the spine."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                _SELECT_CANARIES, {"deployment_id": deployment_id, "suite": suite}
            ).mappings()
            return tuple(
                CanaryCase(
                    canary_id=row["canary_id"],
                    suite=EvalSuite(row["suite"]),
                    description=row["description"],
                    input=row["input"],
                    expected=row["expected"],
                )
                for row in rows
            )

    def _record_run(
        self, *, deployment_id: UUID, report: SuiteReport, component_version: str
    ) -> None:
        """Append the run to eval_runs — the D22 measurement history."""
        with self._engine.begin() as connection:
            connection.execute(
                _INSERT_RUN,
                {
                    "eval_run_id": uuid4(),
                    "deployment_id": deployment_id,
                    "suite": report.suite,
                    "component_version": component_version,
                    "metrics": {
                        "total_cases": report.total_cases,
                        "failures": [
                            failure.model_dump(mode="json")
                            for failure in report.failures
                        ],
                    },
                    "passed": report.passed,
                },
            )


_SELECT_CANARIES = text(
    """
    SELECT canary_id, suite, description, input, expected
    FROM canary_cases
    WHERE deployment_id = :deployment_id AND suite = :suite
    ORDER BY created_at, canary_id
    """
)

_INSERT_RUN = text(
    """
    INSERT INTO eval_runs (
        eval_run_id, deployment_id, suite, component_version, metrics, passed
    ) VALUES (
        :eval_run_id, :deployment_id, :suite, :component_version, :metrics, :passed
    )
    """
).bindparams(bindparam("metrics", type_=JSON))
