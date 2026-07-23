"""The D43 contradiction eval gate (WP-2.5): the SHIPPING criterion.

"Never silently resolve" is policy enforced in E3 + eval, not a schema
invariant — so the adjudicator ships only behind this gate: contradiction
precision/recall over golden statement pairs, recorded in `eval_runs`
(suite `contradiction`) and blocking below the floors.
"""

from typing import Final
from uuid import UUID
from uuid import uuid4
from uuid import uuid5

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Engine

from rememberstack.model import ObservationOutcome
from rememberstack.spine.observation_adjudication import ObservationAdjudicator

CONTRADICTION_PRECISION_FLOOR: Final = 0.90
"""Gate floor: flagged contradictions must be real (starting point, D22)."""

CONTRADICTION_RECALL_FLOOR: Final = 0.80
"""Gate floor: real contradictions must be flagged (starting point, D22)."""

_CASE_NAMESPACE: Final = UUID("c0217ad1-0000-4000-8000-000000000000")

SYNTHETIC_CONTRADICTION_CASES: Final[tuple[dict[str, object], ...]] = (
    {
        "description": "same period, incompatible revenue figures",
        "existing": "Acme's FY2023 revenue was $5M.",
        "new": "Acme's FY2023 revenue was $7M.",
        "expected_contradiction": True,
    },
    {
        "description": "same period, incompatible headcount figures",
        "existing": "Acme's headcount at year-end 2023 was 500.",
        "new": "Acme's headcount at year-end 2023 was 800.",
        "expected_contradiction": True,
    },
    {
        "description": "different property is never a contradiction",
        "existing": "Acme's FY2023 revenue was $5M.",
        "new": "Acme's FY2023 profit was $1M.",
        "expected_contradiction": False,
    },
    {
        "description": "different period is never a contradiction",
        "existing": "Acme's FY2023 revenue was $5M.",
        "new": "Acme's Q1-2023 revenue was $2M.",
        "expected_contradiction": False,
    },
    {
        "description": "a changing state moving on is supersession, not conflict",
        "existing": "Acme's headcount is 500.",
        "new": "Acme's headcount is 600 as of 2025.",
        "expected_contradiction": False,
    },
)


def seed_contradiction_cases(*, engine: Engine, deployment_id: UUID) -> None:
    """Insert or refresh the golden pairs (stable per-deployment ids)."""
    with engine.begin() as connection:
        for case in SYNTHETIC_CONTRADICTION_CASES:
            connection.execute(
                _UPSERT_CASE,
                {
                    "canary_id": uuid5(
                        _CASE_NAMESPACE, f"{deployment_id}:{case['description']}"
                    ),
                    "deployment_id": deployment_id,
                    "description": case["description"],
                    "input": {"existing": case["existing"], "new": case["new"]},
                    "expected": {"contradiction": case["expected_contradiction"]},
                },
            )


def run_contradiction_suite(
    *,
    engine: Engine,
    adjudicator: ObservationAdjudicator,
    deployment_id: UUID,
    component_version: str,
) -> dict[str, object]:
    """Judge every golden pair; record P/R; block below the floors.

    Precision: of the pairs the adjudicator flags contradict, how many are
    real. Recall: of the real contradictions, how many are flagged. An empty
    or one-sided golden set never passes (0/0 blocks, D22).
    """
    with engine.connect() as connection:
        cases = (
            connection.execute(_SELECT_CASES, {"deployment_id": deployment_id})
            .mappings()
            .all()
        )
    tp = fp = fn = tn = 0
    for case in cases:
        outcome, _confidence = adjudicator.judge_statements(
            existing=str(case["input"]["existing"]), new=str(case["input"]["new"])
        )
        flagged = outcome is ObservationOutcome.CONTRADICT
        actual = bool(case["expected"]["contradiction"])
        if flagged and actual:
            tp += 1
        elif flagged and not actual:
            fp += 1
        elif not flagged and actual:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    # a one-sided golden set never passes (Codex review): both real
    # contradictions AND real non-contradictions must be measured, or the
    # gate cannot see false positives / false negatives at all.
    passed = (
        precision is not None
        and recall is not None
        and (tp + fn) > 0
        and (fp + tn) > 0
        and precision >= CONTRADICTION_PRECISION_FLOOR
        and recall >= CONTRADICTION_RECALL_FLOOR
    )
    metrics = {
        "precision": precision,
        "recall": recall,
        "cases": tp + fp + fn + tn,
        "floors": {
            "precision": CONTRADICTION_PRECISION_FLOOR,
            "recall": CONTRADICTION_RECALL_FLOOR,
        },
    }
    with engine.begin() as connection:
        connection.execute(
            _RECORD_RUN,
            {
                "eval_run_id": uuid4(),
                "deployment_id": deployment_id,
                "component_version": component_version,
                "metrics": metrics,
                "passed": passed,
            },
        )
    return {**metrics, "passed": passed}


_UPSERT_CASE = text(
    """
    INSERT INTO canary_cases (
        canary_id, deployment_id, suite, description, input, expected
    ) VALUES (
        :canary_id, :deployment_id, 'contradiction', :description,
        :input, :expected
    )
    ON CONFLICT (canary_id) DO UPDATE
        SET description = EXCLUDED.description,
            input = EXCLUDED.input,
            expected = EXCLUDED.expected
    """
).bindparams(bindparam("input", type_=JSON), bindparam("expected", type_=JSON))

_SELECT_CASES = text(
    """
    SELECT description, input, expected FROM canary_cases
    WHERE deployment_id = :deployment_id AND suite = 'contradiction'
    ORDER BY canary_id
    """
)

_RECORD_RUN = text(
    """
    INSERT INTO eval_runs (
        eval_run_id, deployment_id, suite, component_version, metrics, passed
    ) VALUES (
        :eval_run_id, :deployment_id, 'contradiction', :component_version,
        :metrics, :passed
    )
    """
).bindparams(bindparam("metrics", type_=JSON))
