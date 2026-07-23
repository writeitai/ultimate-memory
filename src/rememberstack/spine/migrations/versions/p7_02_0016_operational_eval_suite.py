"""Add the WP-7.2 operational scale eval suite."""

from collections.abc import Sequence

from alembic import op

revision: str = "p7_02_0016"
down_revision: str | None = "p6_06_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Append the provider-neutral operational measurement suite."""
    op.execute("ALTER TYPE eval_suite ADD VALUE IF NOT EXISTS 'operational'")


def downgrade() -> None:
    """PostgreSQL cannot remove an enum value in place; additive no-op."""
