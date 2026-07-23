"""Add the `invalidated` adjudication outcome (WP-2.6 review verdicts).

A review's invalidate_fact verdict sets a fact's invalidated_at; recording
that action as `noop` would make the append-only adjudication ledger lie on
replay (a rebuild would retain the fact). The enum gains the truthful value.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p2_06_0007"
down_revision: str | None = "p0_02_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Append the enum value (additive; existing rows untouched)."""
    op.execute("ALTER TYPE adjudication_outcome ADD VALUE IF NOT EXISTS 'invalidated'")


def downgrade() -> None:
    """PostgreSQL cannot remove an enum value in place; the value is
    additive and unused rows are impossible to strand, so downgrade is a
    deliberate no-op (documented, not silent)."""
