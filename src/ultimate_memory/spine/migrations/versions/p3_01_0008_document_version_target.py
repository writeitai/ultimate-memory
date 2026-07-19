"""Add the `document_version` processing target (Phase 3, D55/D12).

With multi-version lineages, the E-chain's idempotency key must name the
VERSION being processed: keying convert/structure/chunk work on the lineage
would make a second version's work collide with the first version's
completed row and never run. The enum gains the precise target.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p3_01_0008"
down_revision: str | None = "p2_06_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Append the enum value (additive; existing rows untouched)."""
    op.execute(
        "ALTER TYPE processing_target ADD VALUE IF NOT EXISTS 'document_version'"
    )


def downgrade() -> None:
    """PostgreSQL cannot remove an enum value in place; additive no-op."""
