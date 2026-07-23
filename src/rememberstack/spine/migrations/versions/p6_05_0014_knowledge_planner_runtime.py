"""Add transcript-bearing planner runs and compiled-edit quarantine."""

from collections.abc import Sequence

from alembic import op

revision: str = "p6_05_0014"
down_revision: str | None = "p6_04_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE = """
CREATE TABLE knowledge_plan_runs (
  run_id                 uuid PRIMARY KEY,
  deployment_id          uuid NOT NULL REFERENCES deployments,
  scope_id               uuid,
  run_kind               text NOT NULL CHECK (run_kind IN ('planner','reflection')),
  trigger                plan_trigger NOT NULL,
  component_version      text NOT NULL,
  input_hash             text NOT NULL,
  session_transcript_uri text NOT NULL,
  status                 text NOT NULL CHECK (status IN ('succeeded','failed')),
  failure                text,
  tokens                 integer CHECK (tokens IS NULL OR tokens >= 0),
  cost_usd               numeric CHECK (cost_usd IS NULL OR cost_usd >= 0),
  completed_at           timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (deployment_id, scope_id)
    REFERENCES scopes (deployment_id, scope_id) ON DELETE CASCADE,
  CHECK ((status = 'failed') = (failure IS NOT NULL))
);

CREATE INDEX ix_kplan_runs_deployment
  ON knowledge_plan_runs (deployment_id, completed_at DESC);

ALTER TABLE knowledge_plan_decisions
  ADD COLUMN plan_run_id uuid REFERENCES knowledge_plan_runs (run_id),
  ADD COLUMN confidence numeric,
  ADD COLUMN blast_radius integer,
  ADD COLUMN expected_impact numeric,
  ADD COLUMN reviewed_by text,
  ADD COLUMN reviewed_at timestamptz,
  ADD COLUMN application_commit text;

ALTER TABLE knowledge_plan_decisions
  ADD CONSTRAINT ck_kplan_confidence
    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  ADD CONSTRAINT ck_kplan_blast_radius
    CHECK (blast_radius IS NULL OR blast_radius >= 0),
  ADD CONSTRAINT ck_kplan_expected_impact
    CHECK (expected_impact IS NULL OR expected_impact >= 0),
  ADD CONSTRAINT ck_kplan_review_pair
    CHECK ((reviewed_by IS NULL) = (reviewed_at IS NULL));

ALTER TABLE knowledge_artifact_evidence
  ADD COLUMN claim_lineage_id uuid,
  ADD COLUMN claim_chunk_content_hash text;

UPDATE knowledge_artifact_evidence e
SET claim_lineage_id = resolved.doc_id,
    claim_chunk_content_hash = resolved.chunk_content_hash
FROM (
  SELECT DISTINCT ON (c.claim_id)
         c.claim_id, c.doc_id, ch.chunk_content_hash
  FROM claims c
  JOIN chunks ch
    ON ch.deployment_id = c.deployment_id AND ch.chunk_id = c.chunk_id
  ORDER BY c.claim_id, c.ingested_at DESC
) resolved
WHERE e.claim_id = resolved.claim_id;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM knowledge_artifact_evidence
    WHERE claim_id IS NOT NULL AND claim_lineage_id IS NULL
  ) THEN
    RAISE EXCEPTION
      'cannot migrate unresolved knowledge_artifact_evidence claim citations';
  END IF;
END $$;

DELETE FROM knowledge_artifact_evidence e
USING (
  SELECT evidence_link_id
  FROM (
    SELECT evidence_link_id,
           row_number() OVER (
             PARTITION BY artifact_id, role, claim_lineage_id,
                          claim_chunk_content_hash, relation_id, doc_id
             ORDER BY evidence_link_id
           ) AS duplicate_ordinal
    FROM knowledge_artifact_evidence
  ) ranked
  WHERE duplicate_ordinal > 1
) duplicates
WHERE e.evidence_link_id = duplicates.evidence_link_id;

DROP INDEX ux_kae_link;
DROP INDEX ix_kae_claim;
ALTER TABLE knowledge_artifact_evidence
  DROP CONSTRAINT knowledge_artifact_evidence_check,
  DROP COLUMN claim_id,
  ADD CONSTRAINT ck_kae_claim_coordinate_pair CHECK (
    (claim_lineage_id IS NULL) = (claim_chunk_content_hash IS NULL)
  ),
  ADD CONSTRAINT ck_kae_exactly_one_target CHECK (
    num_nonnulls(claim_lineage_id, relation_id, doc_id) = 1
  );
CREATE UNIQUE INDEX ux_kae_link ON knowledge_artifact_evidence (
  artifact_id, role, claim_lineage_id, claim_chunk_content_hash, relation_id, doc_id
) NULLS NOT DISTINCT;
CREATE INDEX ix_kae_claim_coordinate ON knowledge_artifact_evidence (
  claim_lineage_id, claim_chunk_content_hash
) WHERE claim_lineage_id IS NOT NULL;

CREATE TABLE knowledge_quarantines (
  quarantine_id          uuid PRIMARY KEY,
  decision_id            uuid NOT NULL UNIQUE
    REFERENCES knowledge_plan_decisions (decision_id),
  deployment_id          uuid NOT NULL REFERENCES deployments,
  artifact_id            uuid NOT NULL,
  recorded_content_hash  text NOT NULL,
  detected_content_hash  text NOT NULL,
  proposed_sidecar_entry text NOT NULL,
  status                 text NOT NULL DEFAULT 'proposed'
    CHECK (status IN ('proposed','curation_accepted','adopted','rejected')),
  resolution_note        text,
  curation_content_hash  text,
  detected_at            timestamptz NOT NULL DEFAULT now(),
  resolved_at            timestamptz,
  FOREIGN KEY (deployment_id, artifact_id)
    REFERENCES knowledge_artifacts (deployment_id, artifact_id) ON DELETE CASCADE,
  CHECK ((status = 'proposed') = (resolved_at IS NULL)),
  CHECK (status <> 'curation_accepted' OR curation_content_hash IS NOT NULL)
);

CREATE UNIQUE INDEX ux_kquarantine_open_artifact
  ON knowledge_quarantines (artifact_id) WHERE status = 'proposed';

COMMENT ON TABLE knowledge_plan_runs IS
  'Append-only D52 transcript ledger for planner and independent reflection sessions, including terminal failures.';
COMMENT ON COLUMN knowledge_plan_decisions.expected_impact IS
  'D24-style blast_radius * (1 - confidence), computed by the deterministic driver rather than the proposing agent.';
COMMENT ON COLUMN knowledge_plan_decisions.application_commit IS
  'Git revision whose tree first reflects an applied structural decision; NULL while driver reconciliation is pending.';
COMMENT ON TABLE knowledge_quarantines IS
  'Direct compiled-body edits preserved verbatim as proposed curation, excluded from compilation until explicit curation, adoption, or rejection triage.';
COMMENT ON COLUMN knowledge_artifact_evidence.claim_lineage_id IS
  'D54-stable claim citation coordinate; paired with claim_chunk_content_hash, never a raw extraction-generation claim ID.';
"""

_DOWNGRADE = """
DROP TABLE IF EXISTS knowledge_quarantines;

ALTER TABLE knowledge_artifact_evidence ADD COLUMN claim_id uuid;
UPDATE knowledge_artifact_evidence e
SET claim_id = resolved.claim_id
FROM (
  SELECT DISTINCT ON (c.doc_id, ch.chunk_content_hash)
         c.doc_id, ch.chunk_content_hash, c.claim_id
  FROM claims c
  JOIN chunks ch
    ON ch.deployment_id = c.deployment_id AND ch.chunk_id = c.chunk_id
  ORDER BY c.doc_id, ch.chunk_content_hash, c.is_current_testimony DESC,
           c.ingested_at DESC
) resolved
WHERE e.claim_lineage_id = resolved.doc_id
  AND e.claim_chunk_content_hash = resolved.chunk_content_hash;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM knowledge_artifact_evidence
    WHERE claim_lineage_id IS NOT NULL AND claim_id IS NULL
  ) THEN
    RAISE EXCEPTION
      'cannot downgrade unresolved knowledge_artifact_evidence claim coordinates';
  END IF;
END $$;
DROP INDEX ix_kae_claim_coordinate;
DROP INDEX ux_kae_link;
ALTER TABLE knowledge_artifact_evidence
  DROP CONSTRAINT ck_kae_exactly_one_target,
  DROP CONSTRAINT ck_kae_claim_coordinate_pair,
  DROP COLUMN claim_chunk_content_hash,
  DROP COLUMN claim_lineage_id,
  ADD CHECK (num_nonnulls(claim_id, relation_id, doc_id) = 1);
CREATE UNIQUE INDEX ux_kae_link ON knowledge_artifact_evidence (
  artifact_id, role, claim_id, relation_id, doc_id
) NULLS NOT DISTINCT;
CREATE INDEX ix_kae_claim ON knowledge_artifact_evidence (claim_id)
  WHERE claim_id IS NOT NULL;

ALTER TABLE knowledge_plan_decisions
  DROP CONSTRAINT IF EXISTS ck_kplan_review_pair,
  DROP CONSTRAINT IF EXISTS ck_kplan_expected_impact,
  DROP CONSTRAINT IF EXISTS ck_kplan_blast_radius,
  DROP CONSTRAINT IF EXISTS ck_kplan_confidence,
  DROP COLUMN IF EXISTS application_commit,
  DROP COLUMN IF EXISTS reviewed_at,
  DROP COLUMN IF EXISTS reviewed_by,
  DROP COLUMN IF EXISTS expected_impact,
  DROP COLUMN IF EXISTS blast_radius,
  DROP COLUMN IF EXISTS confidence,
  DROP COLUMN IF EXISTS plan_run_id;

DROP TABLE IF EXISTS knowledge_plan_runs;
"""


def upgrade() -> None:
    """Add the WP-6.5 planner ledger, impact routing, and quarantine records."""
    op.execute(_UPGRADE)


def downgrade() -> None:
    """Remove the WP-6.5 planner runtime schema extension."""
    op.execute(_DOWNGRADE)
