"""Add the `reconcile` pipeline stage (Phase 3, D54/D55).

Reconciliation — currency transitions, the D54 recount, per-shape closure,
and the `evidence_changed` emission — runs as its own queued stage at the
end of a version's chain, so it inherits the work ledger's claim/retry/
idempotency machinery like every other stage (its processing_id doubles as
the run's `reconciliation_id`, which is what makes a retried run re-emit
its ledger rows as no-ops).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p3_05_0009"
down_revision: str | None = "p3_01_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Append the enum value (additive; existing rows untouched)."""
    op.execute("ALTER TYPE pipeline_stage ADD VALUE IF NOT EXISTS 'reconcile'")


def downgrade() -> None:
    """PostgreSQL cannot remove an enum value in place; additive no-op."""
