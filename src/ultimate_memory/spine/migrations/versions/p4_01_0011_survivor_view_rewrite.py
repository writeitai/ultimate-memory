"""Rewrite `v_graph_survivor` without the per-row correlated subquery.

The WP-4.1 spike battery caught the shipped form being quadratic when its
columns are actually materialized: the survivor was picked by a correlated
`(SELECT … ORDER BY depth DESC LIMIT 1)` per output row over the un-indexed
recursive CTE — invisible to `count(*)` (dead-column elimination) but
O(n²) for the real export. At 32k entities the projection export took
50.6 s; the `DISTINCT ON` form below produces the identical terminal-row
semantics in 0.03 s (`plan/analysis/p2_spike_battery.md`). Same columns,
same cycle guard, same contract — only the plan shape changes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p4_01_0011"
down_revision: str | None = "p3_07_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REWRITTEN = """
CREATE OR REPLACE VIEW v_graph_survivor AS
WITH RECURSIVE chain(entity_id, cur, depth) AS (
  SELECT entity_id, entity_id, 0 FROM entities
  UNION ALL
  SELECT c.entity_id, e.merged_into, c.depth + 1
  FROM chain c JOIN entities e ON e.entity_id = c.cur
  WHERE e.merged_into IS NOT NULL AND c.depth < 64          -- cycle / runaway guard
)
SELECT DISTINCT ON (entity_id) entity_id, cur AS survivor
FROM chain ORDER BY entity_id, depth DESC   -- the terminal row per chain, one pass
"""

_ORIGINAL = """
CREATE OR REPLACE VIEW v_graph_survivor AS
WITH RECURSIVE chain(entity_id, cur, depth) AS (
  SELECT entity_id, entity_id, 0 FROM entities
  UNION ALL
  SELECT c.entity_id, e.merged_into, c.depth + 1
  FROM chain c JOIN entities e ON e.entity_id = c.cur
  WHERE e.merged_into IS NOT NULL AND c.depth < 64
)
SELECT entity_id,
       (SELECT cur FROM chain x WHERE x.entity_id = chain.entity_id ORDER BY depth DESC LIMIT 1) AS survivor
FROM chain GROUP BY entity_id
"""


def upgrade() -> None:
    """Swap in the single-pass survivor resolution (same columns/semantics)."""
    op.execute(_REWRITTEN)


def downgrade() -> None:
    """Restore the original (quadratic) form."""
    op.execute(_ORIGINAL)
