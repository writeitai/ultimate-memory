"""Record capped writer bundles and inert writer suggestions."""

from collections.abc import Sequence

from alembic import op

revision: str = "p6_04_0013"
down_revision: str | None = "p6_02_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE = """
ALTER TABLE knowledge_compilations
  ADD COLUMN claims_cut_count integer NOT NULL DEFAULT 0,
  ADD COLUMN suggestions jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE knowledge_compilations
  ADD CONSTRAINT ck_kcompilations_claims_cut_nonnegative
  CHECK (claims_cut_count >= 0);

COMMENT ON COLUMN knowledge_compilations.claims_cut_count IS
  'Rule-matched D54 claim coordinates omitted by the settings-bound writer bundle cap.';
COMMENT ON COLUMN knowledge_compilations.suggestions IS
  'Typed writer suggestions retained as planner inputs; compilation never applies them directly.';
COMMENT ON COLUMN knowledge_compilations.cited_count IS
  'Offered fact and D54 claim-coordinate candidates covered by accepted citations.';
COMMENT ON COLUMN knowledge_compilations.uncited_count IS
  'Offered fact and D54 claim-coordinate candidates not covered by accepted citations.';
"""

_DOWNGRADE = """
ALTER TABLE knowledge_compilations
  DROP CONSTRAINT IF EXISTS ck_kcompilations_claims_cut_nonnegative,
  DROP COLUMN IF EXISTS suggestions,
  DROP COLUMN IF EXISTS claims_cut_count;
"""


def upgrade() -> None:
    """Add the WP-6.4 bundle-cut and suggestion ledger fields."""
    op.execute(_UPGRADE)


def downgrade() -> None:
    """Remove the WP-6.4 writer ledger extension."""
    op.execute(_DOWNGRADE)
