"""Persistence boundary for the WP-7.2 portable scale report."""

from typing import Final
from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Engine

from rememberstack.model import OperationalScaleReport

OPERATIONAL_SCALE_VERSION: Final = "operational-scale-2026.07"


def record_operational_scale_report(
    *,
    engine: Engine,
    deployment_id: UUID,
    report: OperationalScaleReport,
    component_version: str = OPERATIONAL_SCALE_VERSION,
) -> UUID:
    """Append one complete provider-neutral scale report to eval history."""
    eval_run_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            _INSERT_RUN,
            {
                "eval_run_id": eval_run_id,
                "deployment_id": deployment_id,
                "component_version": component_version,
                "metrics": report.model_dump(mode="json"),
                "passed": report.passed,
            },
        )
    return eval_run_id


_INSERT_RUN = text(
    """
    INSERT INTO eval_runs (
        eval_run_id, deployment_id, suite, component_version, metrics, passed
    ) VALUES (
        :eval_run_id, :deployment_id, 'operational', :component_version,
        :metrics, :passed
    )
    """
).bindparams(bindparam("metrics", type_=JSON))
