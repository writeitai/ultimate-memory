"""Add the `lifecycle` eval suite (Phase 3, WP-3.7, D22/D35).

The lifecycle pack guards the D54 economy itself: cache-vs-ledger currency
coherence, cached-count correctness, closure-record coherence, and the
flag-rate rollout canary — the invariants that must hold on ANY deployment
state, plus the regression canaries planted by `restore_support` verdicts.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p3_07_0010"
down_revision: str | None = "p3_05_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Append the enum value (additive; existing rows untouched)."""
    op.execute("ALTER TYPE eval_suite ADD VALUE IF NOT EXISTS 'lifecycle'")


def downgrade() -> None:
    """PostgreSQL cannot remove an enum value in place; additive no-op."""
