"""Add the D67 work-ledger route for WP-6.6 knowledge dispatches."""

from collections.abc import Sequence

from alembic import op

revision: str = "p6_06_0015"
down_revision: str | None = "p6_05_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Append the dispatch target and stage used by the generic D12 worker."""
    op.execute(
        "ALTER TYPE processing_target ADD VALUE IF NOT EXISTS 'knowledge_dispatch'"
    )
    op.execute("ALTER TYPE pipeline_stage ADD VALUE IF NOT EXISTS 'dispatch_knowledge'")
    op.execute(
        """
        CREATE UNIQUE INDEX ux_krefresh_open_authored_review
        ON knowledge_refresh_queue (deployment_id, artifact_id)
        WHERE trigger = 'authored_review' AND processed_at IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_kdispatch_pending_subscription
        ON knowledge_dispatches (deployment_id, subscription_id)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    """PostgreSQL enum additions are intentionally additive across downgrades."""
    op.execute("DROP INDEX IF EXISTS ux_kdispatch_pending_subscription")
    op.execute("DROP INDEX IF EXISTS ux_krefresh_open_authored_review")
