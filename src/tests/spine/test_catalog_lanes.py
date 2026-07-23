"""Behavior tests for the stage/lane pairing rule (D67, application-enforced)."""

from rememberstack.spine.catalog_contract import lane_is_valid
from rememberstack.spine.catalog_contract import UNLANED_STAGES


def test_plane_e_stages_require_a_concrete_lane() -> None:
    """A per-document stage must carry steady or backfill, never NULL."""
    assert lane_is_valid(stage="extract_claims", lane="steady")
    assert lane_is_valid(stage="convert", lane="backfill")
    assert not lane_is_valid(stage="extract_claims", lane=None)


def test_scheduled_stages_must_be_unlaned() -> None:
    """A K/P debounce- or schedule-triggered stage must have a NULL lane."""
    for stage in UNLANED_STAGES:
        assert lane_is_valid(stage=stage, lane=None)
        assert not lane_is_valid(stage=stage, lane="steady")
        assert not lane_is_valid(stage=stage, lane="backfill")
