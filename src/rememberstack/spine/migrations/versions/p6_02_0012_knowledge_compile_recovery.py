"""Persist the finalize payload needed to recover a published K cycle."""

from collections.abc import Sequence

from alembic import op

revision: str = "p6_02_0012"
down_revision: str | None = "p4_01_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE = """
ALTER TABLE knowledge_compilations
  ADD COLUMN cycle_id uuid,
  ADD COLUMN page_summary text,
  ADD COLUMN content_hash text,
  ADD COLUMN citations jsonb,
  ADD COLUMN failed_at timestamptz,
  ADD COLUMN failure text;

CREATE INDEX ix_kcompilations_pending_cycle
  ON knowledge_compilations (deployment_id, cycle_id, compiled_at)
  WHERE git_commit IS NULL AND failed_at IS NULL;

COMMENT ON COLUMN knowledge_compilations.cycle_id IS
  'One driver publish batch. Every page in a cycle is finalized in one Postgres transaction.';
COMMENT ON COLUMN knowledge_compilations.page_summary IS
  'Recovery copy of the writer summary; required to finalize after a post-publish process crash.';
COMMENT ON COLUMN knowledge_compilations.content_hash IS
  'Recovery copy of the compiled markdown hash; also verifies that remote HEAD contains the pending output.';
COMMENT ON COLUMN knowledge_compilations.citations IS
  'Recovery copy of the typed binding citation set; counts alone cannot reconstruct citation identities.';
COMMENT ON COLUMN knowledge_compilations.failed_at IS
  'Set when a pending cycle was never published or no longer matches remote HEAD.';
COMMENT ON COLUMN knowledge_compilations.failure IS
  'Visible reason a pending cycle could not be recovered; its pages remain stale.';
"""

_DOWNGRADE = """
DROP INDEX IF EXISTS ix_kcompilations_pending_cycle;
ALTER TABLE knowledge_compilations
  DROP COLUMN IF EXISTS failure,
  DROP COLUMN IF EXISTS failed_at,
  DROP COLUMN IF EXISTS citations,
  DROP COLUMN IF EXISTS content_hash,
  DROP COLUMN IF EXISTS page_summary,
  DROP COLUMN IF EXISTS cycle_id;
"""


def upgrade() -> None:
    """Add durable pending-cycle recovery data without rewriting old transcripts."""
    op.execute(_UPGRADE)


def downgrade() -> None:
    """Remove the WP-6.2 recovery payload and pending-cycle index."""
    op.execute(_DOWNGRADE)
