"""Pure canonical identity helpers for D74 hard-forget guards."""

import hashlib
import json
from uuid import UUID


def source_identity_hash(
    *, deployment_id: UUID, source_kind: str, source_ref: str
) -> str:
    """Hash one unambiguous deployment-owned connector identity tuple."""
    canonical = json.dumps(
        [str(deployment_id), source_kind, source_ref],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
