"""The ER golden-set suite (WP-2.1, D17/D22): per-type P/R over golden pairs.

Runs the cascade's decision function over every human-adjudicated pair,
computes precision/recall per entity type, records the curves on the
`resolver_versions` row (the acceptance home) and the run in `eval_runs`.
No threshold ships as final without these curves; the floors here are
starting points to tighten as the golden set grows.
"""

from typing import Final
from uuid import UUID
from uuid import uuid4
from uuid import uuid5

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.spine.resolver import CascadeResolver

PRECISION_FLOOR: Final = 0.90
"""Suite-blocking precision floor per type (starting point, D22)."""

RECALL_FLOOR: Final = 0.80
"""Suite-blocking recall floor per type (starting point, D22)."""

_PAIR_NAMESPACE: Final = UUID("601de77a-0000-4000-8000-000000000000")

SYNTHETIC_GOLDEN_PAIRS: Final[tuple[dict[str, object], ...]] = (
    # exact / near-exact strata
    {
        "entity_type": "Organization",
        "surface_a": "Acme Corporation",
        "surface_b": "Acme Corp",
        "label": "match",
        "hardness": "easy",
        "expected_blocking_tier": "T1",
        "context_a": "Acme Corporation, the industrial supplier.",
        "context_b": "Acme Corp announced quarterly results.",
    },
    {
        "entity_type": "Organization",
        "surface_a": "Acme Corporation",
        "surface_b": "Zenith Industries",
        "label": "no_match",
        "hardness": "easy",
        "expected_blocking_tier": None,
        "context_a": None,
        "context_b": None,
    },
    # the Czech slice (registries §5): diacritics, inflection, family names
    {
        "entity_type": "Person",
        "surface_a": "Pavel Kovář",
        "surface_b": "Pavel Kovar",
        "label": "match",
        "hardness": "easy",
        "expected_blocking_tier": "T0",  # unaccent folds the diacritic
        "context_a": "Pavel Kovář of the Brno office.",
        "context_b": "an email signed Pavel Kovar, Brno office",
    },
    {
        "entity_type": "Person",
        "surface_a": "Jan Novák",
        "surface_b": "Jana Nováková",
        "label": "no_match",  # feminine surname: typically a different person
        "hardness": "hard_negative",
        "expected_blocking_tier": "T1",
        "context_a": "Jan Novák, the finance director.",
        "context_b": "Jana Nováková from the legal team.",
    },
    {
        "entity_type": "Person",
        "surface_a": "Petr Svoboda",
        "surface_b": "Petra Svobodu",  # accusative inflection of a NAME variant
        "label": "no_match",
        "hardness": "hard_negative",
        "expected_blocking_tier": "T1",
        "context_a": "Petr Svoboda leads the platform team.",
        "context_b": "the committee appointed Petra Svobodu",
    },
    {
        "entity_type": "Person",
        "surface_a": "Karel Dvořák",
        "surface_b": "Karel Dvorzak",  # phonetic spelling drift
        "label": "match",
        "hardness": "hard_positive",
        "expected_blocking_tier": "T2",
        "context_a": "Karel Dvořák, the composer's namesake in sales.",
        "context_b": "meeting notes mention Karel Dvorzak from sales",
    },
)


def seed_synthetic_golden_pairs(*, engine: Engine, deployment_id: UUID) -> None:
    """Insert or refresh the synthetic starter pairs (stable ids).

    These bootstrap the machinery and the Czech slice; real deployments grow
    the set through human adjudication (WP-0.6 tooling) — synthetic pairs
    stay marked `is_synthetic` so measured curves can be stratified.
    """
    with engine.begin() as connection:
        for pair in SYNTHETIC_GOLDEN_PAIRS:
            connection.execute(
                _UPSERT_PAIR,
                {
                    "pair_id": uuid5(
                        _PAIR_NAMESPACE,
                        f"{deployment_id}:{pair['surface_a']}|{pair['surface_b']}",
                    ),
                    "deployment_id": deployment_id,
                    **pair,
                },
            )


def run_resolution_suite(
    *,
    engine: Engine,
    resolver: CascadeResolver,
    deployment_id: UUID,
    component_version: str,
) -> dict[str, object]:
    """Judge every golden pair, record curves + the run, return the report.

    Passing means every measured type meets the precision and recall floors.
    The curves land on the resolver_versions row (notes) — the D22 record the
    exit criterion names — and the run in eval_runs.
    """
    with engine.connect() as connection:
        pairs = (
            connection.execute(_SELECT_PAIRS, {"deployment_id": deployment_id})
            .mappings()
            .all()
        )
    by_type: dict[str, dict[str, int]] = {}
    for pair in pairs:
        matched, tier = resolver.judge_pair(
            surface_a=pair["surface_a"],
            surface_b=pair["surface_b"],
            entity_type=pair["entity_type"],
            context_a=pair["context_a"],
            context_b=pair["context_b"],
        )
        counts = by_type.setdefault(
            pair["entity_type"], {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        )
        actual = pair["label"] == "match"
        if matched and actual:
            counts["tp"] += 1
        elif matched and not actual:
            counts["fp"] += 1
        elif not matched and actual:
            counts["fn"] += 1
        else:
            counts["tn"] += 1
        del tier  # per-pair deciding tier; stratified curves arrive with WP-0.6
    curves = {
        entity_type: {
            "precision": _ratio(counts["tp"], counts["tp"] + counts["fp"]),
            "recall": _ratio(counts["tp"], counts["tp"] + counts["fn"]),
            "pairs": sum(counts.values()),
        }
        for entity_type, counts in by_type.items()
    }
    passed = bool(curves) and all(
        curve["precision"] >= PRECISION_FLOOR and curve["recall"] >= RECALL_FLOOR
        for curve in curves.values()
    )
    with engine.begin() as connection:
        connection.execute(
            _RECORD_RUN,
            {
                "eval_run_id": uuid4(),
                "deployment_id": deployment_id,
                "component_version": component_version,
                "metrics": {
                    "curves": curves,
                    "floors": {"precision": PRECISION_FLOOR, "recall": RECALL_FLOOR},
                },
                "passed": passed,
            },
        )
        connection.execute(
            _RECORD_CURVES,
            {
                "deployment_id": deployment_id,
                "resolver_version": component_version,
                "notes": {"curves": curves},
            },
        )
    return {"curves": curves, "passed": passed}


def _ratio(numerator: int, denominator: int) -> float:
    """A safe ratio: an unmeasured stratum counts as perfect-by-absence 1.0."""
    return numerator / denominator if denominator else 1.0


_UPSERT_PAIR = text(
    """
    INSERT INTO golden_pairs (
        pair_id, deployment_id, entity_type, surface_a, surface_b,
        context_a, context_b, label, hardness, expected_blocking_tier,
        is_synthetic, adjudicated_by
    ) VALUES (
        :pair_id, :deployment_id, :entity_type, :surface_a, :surface_b,
        :context_a, :context_b, :label, :hardness, :expected_blocking_tier,
        true, 'synthetic-starter'
    )
    ON CONFLICT (pair_id) DO UPDATE
        SET label = EXCLUDED.label,
            hardness = EXCLUDED.hardness,
            context_a = EXCLUDED.context_a,
            context_b = EXCLUDED.context_b,
            expected_blocking_tier = EXCLUDED.expected_blocking_tier
    """
)

_SELECT_PAIRS = text(
    """
    SELECT entity_type, surface_a, surface_b, context_a, context_b, label
    FROM golden_pairs
    WHERE deployment_id = :deployment_id
    ORDER BY entity_type, pair_id
    """
)

_RECORD_RUN = text(
    """
    INSERT INTO eval_runs (
        eval_run_id, deployment_id, suite, component_version, metrics, passed
    ) VALUES (
        :eval_run_id, :deployment_id, 'resolution', :component_version,
        :metrics, :passed
    )
    """
).bindparams(bindparam("metrics", type_=JSON))

_RECORD_CURVES = text(
    """
    UPDATE resolver_versions
    SET notes = CAST(:notes AS jsonb)::text
    WHERE deployment_id = :deployment_id
      AND resolver_version = :resolver_version
    """
).bindparams(bindparam("notes", type_=JSON))
