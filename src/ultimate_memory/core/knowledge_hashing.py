"""Canonical Plane-K input hashing (D45/D54)."""

import hashlib
import json

from pydantic import JsonValue
from pydantic import TypeAdapter

from ultimate_memory.model import KnowledgeInputSnapshot

_JSON_ADAPTER = TypeAdapter(JsonValue)


def knowledge_inputs_hash(*, snapshot: KnowledgeInputSnapshot) -> str:
    """Return the order-independent D45 staleness key for one page.

    Relations and observations retain their state fingerprints. Claim-grain
    candidates deliberately contain only ``(lineage, chunk_content_hash)``;
    raw claim IDs and text are absent so a semantically unchanged extraction
    generation cannot create a stale storm (D54).
    """
    payload = _JSON_ADAPTER.validate_python(
        {
            "facts": _sorted_unique(
                values=[fact.model_dump(mode="json") for fact in snapshot.facts]
            ),
            "claims": _sorted_unique(
                values=[claim.model_dump(mode="json") for claim in snapshot.claims]
            ),
            "rules": _sorted_unique(
                values=[
                    {"kind": rule.kind.value, "params": rule.params}
                    for rule in snapshot.rules
                ]
            ),
            "curation_hash": snapshot.curation_hash,
            # Multiplicity is meaningful here: two children with identical
            # summaries are still two DAG inputs, while candidate rules are a set.
            "child_summary_hashes": sorted(snapshot.child_summary_hashes),
            "shared_model_summary_hash": snapshot.shared_model_summary_hash,
            "writer_version": snapshot.writer_version,
        }
    )
    canonical = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def knowledge_summary_hash(*, summary: str) -> str:
    """Hash a child/model page summary for inclusion in a parent's manifest."""
    return hashlib.sha256(summary.encode("utf-8")).hexdigest()


def _sorted_unique(*, values: list[JsonValue]) -> list[JsonValue]:
    """Sort JSON values canonically and remove set-union duplicates."""
    by_json = {
        json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ): value
        for value in values
    }
    return [by_json[key] for key in sorted(by_json)]
