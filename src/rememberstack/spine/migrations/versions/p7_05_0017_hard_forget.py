"""Add the D74 hard-forget manifest materialization and worker vocabulary."""

from collections.abc import Sequence

from rememberstack.spine.migrations._helpers import apply_ddl
from rememberstack.spine.migrations._helpers import drop_tables
from rememberstack.spine.migrations._helpers import drop_types

revision: str = "p7_05_0017"
down_revision: str | None = "p7_02_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DDL = r"""ALTER TYPE pipeline_component ADD VALUE IF NOT EXISTS 'forgetter';
ALTER TYPE pipeline_stage ADD VALUE IF NOT EXISTS 'hard_forget';
CREATE TYPE forget_manifest_status AS ENUM ('preparing','accepted','complete');

CREATE TABLE forget_manifests (
  forget_id            uuid PRIMARY KEY,                 -- stable portable intent identity
  deployment_id        uuid NOT NULL REFERENCES deployments, -- deployment that owns the lineage
  doc_id                uuid NOT NULL,                    -- lineage target; intentionally retained for replay
  schema_version        smallint NOT NULL,                -- portable manifest schema version
  manifest_hash         text,                             -- set with manifest before portable append
  manifest              jsonb,                            -- content-free immutable IDs, hashes, and keys
  source_identity_hash  text,                             -- irreversible stable-source ingest guard
  content_hashes        text[] NOT NULL DEFAULT '{}',     -- irreversible raw-content ingest guards
  status                forget_manifest_status NOT NULL DEFAULT 'preparing', -- admission lifecycle
  prepared_at           timestamptz NOT NULL DEFAULT now(), -- barrier establishment time
  accepted_at           timestamptz,                      -- portable append acknowledgement time
  completed_at          timestamptz,                      -- latest successful full purge time
  last_verified_at      timestamptz,                      -- latest all-store readiness re-honor
  UNIQUE (deployment_id, doc_id),
  UNIQUE (deployment_id, forget_id),
  CHECK ((status = 'preparing') OR
         (manifest_hash IS NOT NULL AND manifest IS NOT NULL AND accepted_at IS NOT NULL)),
  CHECK ((status = 'complete') = (completed_at IS NOT NULL))
);
COMMENT ON TABLE forget_manifests IS
  'D74 hard-forget manifest materialization: preparing is the admission barrier; accepted means portable intent is durable; complete never lets readiness skip external-store re-honor.';
CREATE INDEX ix_forget_source_guard
  ON forget_manifests (deployment_id, source_identity_hash)
  WHERE source_identity_hash IS NOT NULL;
CREATE INDEX ix_forget_content_guard ON forget_manifests USING gin (content_hashes);
"""


def upgrade() -> None:
    """Add one manifest table plus the unlaned hard-forget work identity."""
    apply_ddl(sql=_DDL)


def downgrade() -> None:
    """Drop reversible D74 objects; additive pipeline enum values remain."""
    drop_tables(table_names=("forget_manifests",))
    drop_types(type_names=("forget_manifest_status",))
