"""The lifecycle eval pack (WP-3.7, D22/D35): the D54 economy, guarded.

Three layers of protection over the currency/count machinery:

- **Invariants** — properties that must hold on ANY deployment state at any
  time: the currency cache agrees with its ledger, cached counts agree with
  a recompute, closure records agree with fact state, and no fact is both
  closed and under an open flag. A violation means the machinery itself
  broke — the suite fails loudly with the offending ids.
- **The flag-rate metric** — `support_withdrawn` flags per extractor
  generation, the live rollout canary (lifecycle §4): a spike right after
  an upgrade is the corpus-level regression alarm. Recorded in every
  suite run's metrics, queryable from `eval_runs` (the dashboard surface).
- **Planted canaries** — every `restore_support` verdict plants a D35
  canary (`spine/review.py`), and this pack's evaluator re-checks each on
  every run: the restored claim must still be current testimony, so no
  future extractor generation ships while silently missing it again.
"""

from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy import TextClause
from sqlalchemy.engine import Engine

from ultimate_memory.eval.harness import EvalHarness
from ultimate_memory.model import CanaryCase
from ultimate_memory.model import EvalSuite
from ultimate_memory.model import LifecycleReport


def run_lifecycle_suite(
    *, engine: Engine, deployment_id: UUID, component_version: str
) -> LifecycleReport:
    """Check every invariant, compute the flag rate, record the run.

    ``passed`` is the invariant verdict alone — the flag rate is a metric
    to watch (its alarm threshold is an operations decision), never a
    mechanical gate.
    """
    violations: dict[str, tuple[str, ...]] = {}
    with engine.connect() as connection:
        for name, statement in _INVARIANTS:
            offenders = tuple(
                str(value)
                for value in connection.execute(
                    statement, {"deployment_id": deployment_id}
                ).scalars()
            )
            if offenders:
                violations[name] = offenders
    flag_rates = flag_rate_by_extractor(engine=engine, deployment_id=deployment_id)
    report = LifecycleReport(
        passed=not violations, violations=violations, flag_rate_by_extractor=flag_rates
    )
    with engine.begin() as connection:
        connection.execute(
            _RECORD_RUN,
            {
                "eval_run_id": uuid4(),
                "deployment_id": deployment_id,
                "component_version": component_version,
                "metrics": report.model_dump(mode="json"),
                "passed": report.passed,
            },
        )
    return report


def flag_rate_by_extractor(
    *, engine: Engine, deployment_id: UUID
) -> dict[str, dict[str, float]]:
    """`support_withdrawn` flags per superseding extractor generation.

    The rollout canary (lifecycle §4): a spike right after an upgrade means
    the new generation is failing to re-derive what the corpus still says.
    Shape (a starting point, D22): per generation V —
    ``flags_raised`` (flags whose diff names V as the superseding
    generation), ``current_claims`` (V's live corpus coverage), and
    ``flag_rate = flags / (flags + current_claims)`` — a saturating
    proportion that reads 1.0 when a generation only withdraws and never
    re-derives, and falls toward 0 as its coverage dominates.
    """
    with engine.connect() as connection:
        coverage = {
            row["extractor_version"]: row["current_claims"]
            for row in connection.execute(
                _COUNT_GENERATION_COVERAGE, {"deployment_id": deployment_id}
            ).mappings()
        }
        flags = {
            row["to_version"]: row["flags"]
            for row in connection.execute(
                _COUNT_FLAGS, {"deployment_id": deployment_id}
            ).mappings()
        }
    return {
        version: {
            "current_claims": float(coverage.get(version, 0)),
            "flags_raised": float(flags.get(version, 0)),
            "flag_rate": (
                flags.get(version, 0)
                / (flags.get(version, 0) + coverage.get(version, 0))
                if flags.get(version, 0) or coverage.get(version, 0)
                else 0.0
            ),
        }
        for version in sorted({*coverage, *flags})
    }


def register_lifecycle_evaluator(*, harness: EvalHarness, engine: Engine) -> None:
    """Bind the planted-canary evaluator: a restored claim stays current.

    Each `restore_support` verdict planted one case; the guard holds while
    the claim is current testimony — either the reviewer's reinstatement
    still stands, or a fixed extractor re-derived it. A generation that
    silently loses it again fails the canary and cannot ship (D35).
    """

    def _evaluate(case: CanaryCase) -> bool:
        claim_id = case.expected.get("current_claim_id")
        if not isinstance(claim_id, str):
            return False  # a malformed canary never passes silently
        with engine.connect() as connection:
            return bool(
                connection.execute(
                    _CLAIM_IS_CURRENT, {"claim_id": UUID(claim_id)}
                ).scalar_one_or_none()
            )

    harness.register_evaluator(suite=EvalSuite.LIFECYCLE, evaluator=_evaluate)


_INVARIANTS: tuple[tuple[str, TextClause], ...] = (
    (
        # the D33 pattern's contract: the ledger is truth, the flag is cache
        "currency_cache_matches_ledger",
        text(
            """
            SELECT cl.claim_id
            FROM claims cl
            JOIN LATERAL (
                SELECT e.became_current
                FROM testimony_currency_events e
                WHERE e.claim_id = cl.claim_id
                ORDER BY e.occurred_at DESC, e.event_id DESC
                LIMIT 1
            ) last ON true
            WHERE cl.deployment_id = :deployment_id
              AND cl.is_current_testimony <> last.became_current
            """
        ),
    ),
    (
        # D54: the cached counts must equal a recompute at any moment
        "relation_counts_match_recompute",
        text(
            """
            SELECT r.relation_id
            FROM relations r
            WHERE r.deployment_id = :deployment_id
              AND r.evidence_count <> (
                  SELECT count(DISTINCT e.doc_id)
                  FROM relation_evidence e
                  JOIN claims cl ON cl.claim_id = e.claim_id
                  WHERE e.relation_id = r.relation_id
                    AND e.stance = 'supports'
                    AND cl.is_current_testimony
              )
            """
        ),
    ),
    (
        "observation_counts_match_recompute",
        text(
            """
            SELECT o.observation_id
            FROM observations o
            WHERE o.deployment_id = :deployment_id
              AND o.evidence_count <> (
                  SELECT count(DISTINCT e.doc_id)
                  FROM observation_evidence e
                  JOIN claims cl ON cl.claim_id = e.claim_id
                  WHERE e.observation_id = o.observation_id
                    AND e.stance = 'supports'
                    AND cl.is_current_testimony
              )
            """
        ),
    ),
    (
        # every mechanical retraction is recorded, and every record is real:
        # a retraction adjudication's relation must actually be closed
        "retraction_records_match_closures",
        text(
            """
            SELECT a.relation_id
            FROM relation_adjudications a
            JOIN relations r ON r.relation_id = a.relation_id
            WHERE a.deployment_id = :deployment_id
              AND a.outcome = 'retracted_source_removal'
              AND a.superseded_by IS NULL
              AND r.valid_until IS NULL
              AND r.invalidated_at IS NULL
            """
        ),
    ),
    (
        # the §4 fork must never merge: a fact under an open flag is the
        # reviewer's to decide — it can never also be mechanically closed
        "flagged_facts_never_closed",
        text(
            """
            SELECT r.relation_id
            FROM relations r
            JOIN review_queue q
              ON q.candidate ->> 'fact_id' = r.relation_id::text
            WHERE r.deployment_id = :deployment_id
              AND q.item_kind = 'support_withdrawn'
              AND q.status IN ('pending', 'deferred')
              AND EXISTS (
                  SELECT 1 FROM relation_adjudications a
                  WHERE a.relation_id = r.relation_id
                    AND a.outcome = 'retracted_source_removal'
                    AND a.superseded_by IS NULL
              )
            """
        ),
    ),
)

_COUNT_GENERATION_COVERAGE = text(
    """
    SELECT extractor_version, count(*) AS current_claims
    FROM claims
    WHERE deployment_id = :deployment_id AND is_current_testimony
    GROUP BY extractor_version
    """
)

_COUNT_FLAGS = text(
    """
    SELECT q.candidate -> 'diff' ->> 'to_extractor_version' AS to_version,
           count(*) AS flags
    FROM review_queue q
    WHERE q.deployment_id = :deployment_id
      AND q.item_kind = 'support_withdrawn'
    GROUP BY q.candidate -> 'diff' ->> 'to_extractor_version'
    """
)

_CLAIM_IS_CURRENT = text(
    """
    SELECT is_current_testimony FROM claims WHERE claim_id = :claim_id
    """
)

_RECORD_RUN = text(
    """
    INSERT INTO eval_runs (
        eval_run_id, deployment_id, suite, component_version, metrics, passed
    ) VALUES (
        :eval_run_id, :deployment_id, 'lifecycle', :component_version,
        :metrics, :passed
    )
    """
).bindparams(bindparam("metrics", type_=JSON))
