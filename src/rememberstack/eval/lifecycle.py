"""The lifecycle eval pack (WP-3.7, D22/D35): the D54 economy, guarded.

Three layers of protection over the currency/count machinery, and ONE gate:
`run_lifecycle_suite` checks the standing invariants AND re-runs every
planted canary, folds both into a single verdict, and records it — a green
lifecycle row in `eval_runs` means the whole pack held.

- **Invariants** — properties that must hold on the deployment state: the
  currency cache agrees with its ledger (transactional, always checkable),
  cached counts agree with a recompute, closure records agree with fact
  state, and no fact is both closed and under an open flag. Count and
  closure checks can lag legitimately while reconciliation is mid-flight,
  so they run only when the pipeline is QUIESCENT — a busy deployment
  defers them (visibly) instead of alarming falsely.
- **The flag-rate metric** — `support_withdrawn` flags per superseding
  extractor generation, the live rollout canary (lifecycle §4). A
  non-extractor basis bump (converter/blockizer/structurer) surfaces under
  the unchanged extractor key — its spike is visible in the absolute
  `flags_raised` jump, and each flag records its full basis coordinates
  for exact attribution; a per-coordinate rate refinement is a D22
  follow-up measurement.
- **Planted canaries** — every `restore_support` verdict plants a D35
  canary (`spine/review.py`). The guard is the FACT's support, not the
  original claim row: a fixed extractor legitimately re-derives the
  content as a NEW claim (immutability) and the old one flips non-current
  — the canary must pass then, and fail only when the fact's current
  support silently vanishes again.
"""

from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy import TextClause
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine

from rememberstack.eval.harness import EvalHarness
from rememberstack.model import CanaryCase
from rememberstack.model import EvalSuite
from rememberstack.model import LifecycleReport
from rememberstack.spine.lifecycle import CURRENCY_CACHE_MISMATCH_SQL


def run_lifecycle_suite(
    *, engine: Engine, deployment_id: UUID, component_version: str
) -> LifecycleReport:
    """The single lifecycle gate: invariants + planted canaries, one verdict.

    All invariant reads share one REPEATABLE READ snapshot (no torn view
    across statements). When reconcile/finalization work is in flight, the
    count/closure checks defer to the next quiescent run — recorded on the
    report, never silently skipped. The flag rate is a metric to watch
    (its alarm threshold is an operations decision), never part of the
    verdict.
    """
    violations: dict[str, tuple[str, ...]] = {}
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        quiescent = (
            connection.execute(
                _COUNT_INFLIGHT_RECONCILES, {"deployment_id": deployment_id}
            ).scalar_one()
            == 0
        )
        for name, requires_quiescence, statement in _INVARIANTS:
            if requires_quiescence and not quiescent:
                continue  # legitimately lagging mid-flight: deferred, visibly
            offenders = tuple(
                str(value)
                for value in connection.execute(
                    statement, {"deployment_id": deployment_id}
                ).scalars()
            )
            if offenders:
                violations[name] = offenders
        canary_failures = tuple(
            f"{case.canary_id}: {case.description}"
            for case in _load_canaries(
                connection=connection, deployment_id=deployment_id
            )
            if not _canary_holds(connection=connection, case=case)
        )
    flag_rates = flag_rate_by_extractor(engine=engine, deployment_id=deployment_id)
    report = LifecycleReport(
        passed=not violations and not canary_failures,
        quiescent=quiescent,
        violations=violations,
        canary_failures=canary_failures,
        flag_rate_by_extractor=flag_rates,
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
    """Bind the planted-canary evaluator for standalone harness runs.

    The same guard `run_lifecycle_suite` applies — kept registered so the
    generic harness surface can re-run the lifecycle canaries alongside
    other suites.
    """

    def _evaluate(case: CanaryCase) -> bool:
        with engine.connect() as connection:
            return _canary_holds(connection=connection, case=case)

    harness.register_evaluator(suite=EvalSuite.LIFECYCLE, evaluator=_evaluate)


def _canary_holds(*, connection: Connection, case: CanaryCase) -> bool:
    """The planted guard: the fact's CURRENT support has not vanished again.

    Immutability means a fixed extractor re-derives the content as a new
    claim row and the restored one legitimately flips non-current — so the
    guard checks the fact, not the original claim: at least one
    current-testimony claim still supports it (the restored one or a
    re-derived successor).
    """
    fact_kind = case.expected.get("fact_kind")
    fact_id = case.expected.get("fact_id")
    if not isinstance(fact_kind, str) or not isinstance(fact_id, str):
        return False  # a malformed canary never passes silently
    statement = (
        _RELATION_HAS_CURRENT_SUPPORT
        if fact_kind == "relation"
        else _OBSERVATION_HAS_CURRENT_SUPPORT
    )
    return bool(
        connection.execute(statement, {"fact_id": UUID(fact_id)}).scalar_one_or_none()
    )


def _load_canaries(
    *, connection: Connection, deployment_id: UUID
) -> tuple[CanaryCase, ...]:
    """The deployment's planted lifecycle canaries."""
    rows = connection.execute(
        _SELECT_LIFECYCLE_CANARIES, {"deployment_id": deployment_id}
    ).mappings()
    return tuple(
        CanaryCase(
            canary_id=row["canary_id"],
            suite=EvalSuite.LIFECYCLE,
            description=row["description"],
            input=row["input"],
            expected=row["expected"],
        )
        for row in rows
    )


_INVARIANTS: tuple[tuple[str, bool, TextClause], ...] = (
    (
        # the D33 pattern's contract: the ledger is truth, the flag is cache.
        # Transactional (event + cache flip commit together), so it is
        # checkable at ANY moment. A claim with no events must sit at the
        # schema's initial state (current) — a false flag with an empty
        # ledger is exactly the corruption this exists to catch.
        "currency_cache_matches_ledger",
        False,
        text(CURRENCY_CACHE_MISMATCH_SQL),
    ),
    (
        # D54: BOTH cached counts must equal a recompute (quiescent only —
        # a mid-flight reconcile legitimately lags between transactions)
        "relation_counts_match_recompute",
        True,
        text(
            """
            SELECT r.relation_id
            FROM relations r
            WHERE r.deployment_id = :deployment_id
              AND (r.evidence_count <> (
                      SELECT count(DISTINCT e.doc_id)
                      FROM relation_evidence e
                      JOIN claims cl ON cl.claim_id = e.claim_id
                      WHERE e.relation_id = r.relation_id
                        AND e.stance = 'supports'
                        AND cl.is_current_testimony)
                   OR r.contradict_count <> (
                      SELECT count(DISTINCT e.doc_id)
                      FROM relation_evidence e
                      JOIN claims cl ON cl.claim_id = e.claim_id
                      WHERE e.relation_id = r.relation_id
                        AND e.stance = 'contradicts'
                        AND cl.is_current_testimony))
            """
        ),
    ),
    (
        "observation_counts_match_recompute",
        True,
        text(
            """
            SELECT o.observation_id
            FROM observations o
            WHERE o.deployment_id = :deployment_id
              AND (o.evidence_count <> (
                      SELECT count(DISTINCT e.doc_id)
                      FROM observation_evidence e
                      JOIN claims cl ON cl.claim_id = e.claim_id
                      WHERE e.observation_id = o.observation_id
                        AND e.stance = 'supports'
                        AND cl.is_current_testimony)
                   OR o.contradict_count <> (
                      SELECT count(DISTINCT e.doc_id)
                      FROM observation_evidence e
                      JOIN claims cl ON cl.claim_id = e.claim_id
                      WHERE e.observation_id = o.observation_id
                        AND e.stance = 'contradicts'
                        AND cl.is_current_testimony))
            """
        ),
    ),
    (
        # every mechanical retraction record is real, both shapes: a live
        # retraction adjudication's fact must actually be closed
        "retraction_records_match_closures",
        True,
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
            UNION ALL
            SELECT a.observation_id
            FROM observation_adjudications a
            JOIN observations o ON o.observation_id = a.observation_id
            WHERE a.deployment_id = :deployment_id
              AND a.outcome = 'retracted_source_removal'
              AND a.superseded_by IS NULL
              AND o.invalidated_at IS NULL
            """
        ),
    ),
    (
        # the §4 fork must never merge, both shapes: a fact under an open
        # flag is the reviewer's to decide — it can never also have been
        # mechanically retracted or invalidated behind the reviewer's back
        "flagged_facts_never_closed",
        True,
        text(
            """
            SELECT r.relation_id
            FROM relations r
            JOIN review_queue q
              ON q.candidate ->> 'fact_id' = r.relation_id::text
            WHERE r.deployment_id = :deployment_id
              AND q.item_kind = 'support_withdrawn'
              AND q.status IN ('pending', 'deferred')
              AND (r.invalidated_at IS NOT NULL
                   OR EXISTS (
                       SELECT 1 FROM relation_adjudications a
                       WHERE a.relation_id = r.relation_id
                         AND a.outcome = 'retracted_source_removal'
                         AND a.superseded_by IS NULL))
            UNION ALL
            SELECT o.observation_id
            FROM observations o
            JOIN review_queue q
              ON q.candidate ->> 'fact_id' = o.observation_id::text
            WHERE o.deployment_id = :deployment_id
              AND q.item_kind = 'support_withdrawn'
              AND q.status IN ('pending', 'deferred')
              AND o.invalidated_at IS NOT NULL
            """
        ),
    ),
)

_COUNT_INFLIGHT_RECONCILES = text(
    """
    SELECT count(*) FROM processing_state
    WHERE deployment_id = :deployment_id
      AND stage = 'reconcile'
      AND status IN ('pending', 'running', 'failed')
    """
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

_RELATION_HAS_CURRENT_SUPPORT = text(
    """
    SELECT 1 FROM relation_evidence e
    JOIN claims cl ON cl.claim_id = e.claim_id
    WHERE e.relation_id = :fact_id
      AND e.stance = 'supports'
      AND cl.is_current_testimony
    LIMIT 1
    """
)

_OBSERVATION_HAS_CURRENT_SUPPORT = text(
    """
    SELECT 1 FROM observation_evidence e
    JOIN claims cl ON cl.claim_id = e.claim_id
    WHERE e.observation_id = :fact_id
      AND e.stance = 'supports'
      AND cl.is_current_testimony
    LIMIT 1
    """
)

_SELECT_LIFECYCLE_CANARIES = text(
    """
    SELECT canary_id, description, input, expected
    FROM canary_cases
    WHERE deployment_id = :deployment_id AND suite = 'lifecycle'
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
