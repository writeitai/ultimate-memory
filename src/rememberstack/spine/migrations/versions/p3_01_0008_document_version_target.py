"""Add the `document_version` processing target (Phase 3, D55/D12).

With multi-version lineages, the E-chain's idempotency key must name the
VERSION being processed: keying convert/structure/chunk work on the lineage
would make a second version's work collide with the first version's
completed row and never run. The enum gains the precise target.

Two lifecycle audit columns land alongside it:

- ``documents.deleted_sync_cycle_id`` — a source-observed deletion is
  stamped with the cycle that observed it, so reconciliation's
  finalization barrier can place the deletion inside its cycle.
- ``connector_sync_cycles.failed_items`` — a poll pass that lost items to
  per-item errors says so on its own row; reconciliation must never treat
  a lossy cycle's observation set as complete.

And one constraint falls: ``UNIQUE (deployment_id, doc_id, content_hash)``
on ``document_versions`` encoded a one-version-per-content rule that D55
does not have — a version is an OBSERVATION event, and content reverted
A→B→A legitimately recurs as a third version of the same content object
(content_objects still dedups the bytes themselves).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p3_01_0008"
down_revision: str | None = "p2_06_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Append the enum value and the two audit columns (all additive)."""
    op.execute(
        "ALTER TYPE processing_target ADD VALUE IF NOT EXISTS 'document_version'"
    )
    op.execute("ALTER TABLE documents ADD COLUMN deleted_sync_cycle_id uuid")
    op.execute(
        "ALTER TABLE connector_sync_cycles"
        " ADD COLUMN failed_items integer NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE document_versions"
        " DROP CONSTRAINT document_versions_deployment_id_doc_id_content_hash_key"
    )


def downgrade() -> None:
    """Restore the constraint, drop the columns; the enum value stays."""
    op.execute(
        "ALTER TABLE document_versions"
        " ADD CONSTRAINT document_versions_deployment_id_doc_id_content_hash_key"
        " UNIQUE (deployment_id, doc_id, content_hash)"
    )
    op.execute("ALTER TABLE connector_sync_cycles DROP COLUMN failed_items")
    op.execute("ALTER TABLE documents DROP COLUMN deleted_sync_cycle_id")
