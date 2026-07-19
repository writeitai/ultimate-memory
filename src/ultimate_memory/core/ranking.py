"""Pure rank operators (retrieval §3: `fuse`, `rerank`): the D9 fusion math.

These are the fusion and reranking stages as *pure* functions — no spine, no
ports, no I/O — so the same code fuses an agent's ad-hoc channel set and a
recipe's fixed one, and every stage is inspectable rather than a black box.

**Reciprocal-rank fusion (RRF).** When several channels each return a ranked
list — semantic search, BM25, FTS — they cannot be compared by raw score:
a cosine distance and a BM25 score are different units, and two embedding
families are not on the same scale either. RRF sidesteps that by scoring an
item purely on its *ranks*: an item that placed 1st in one channel and 3rd in
another scores ``1/(k+1) + 1/(k+3)``. The constant ``k`` (≈60, a starting
point to be measured, not a committed constant) damps the top ranks so one
channel cannot dominate on a single high placement. Items no channel returned
score zero and drop out. The result is one order that rewards agreement
across channels without ever comparing incomparable scores.

**Reranking** is the same currency read differently: given a set of items each
carrying a named signal (graph distance to a focal entity, evidence count),
reorder by that signal. It is a stage, not a verdict — the caller sees the
signal value on every item and can chain another stage on top.
"""

from collections.abc import Sequence
from uuid import UUID

from ultimate_memory.model import RankedItem

DEFAULT_RRF_K = 60
"""The RRF damping constant (D9). A starting point to measure, not a constant:
larger flattens channel-placement weight, smaller sharpens the top ranks."""


def reciprocal_rank_fusion(
    *, rankings: Sequence[Sequence[UUID]], k: int = DEFAULT_RRF_K
) -> tuple[RankedItem, ...]:
    """Fuse several ranked id lists into one RRF-scored order (D9/S46).

    Each inner sequence is one channel's ranking, best first. An item's
    score is the sum over channels of ``1/(k + rank)`` (rank 1-based), so
    agreement across channels wins without ever comparing raw scores. Ties
    break on the id's own order for determinism. `k` must be positive.
    """
    if k < 1:
        raise ValueError("the RRF constant k must be at least 1")
    scores: dict[UUID, float] = {}
    contributions: dict[UUID, dict[str, float]] = {}
    for channel, ranking in enumerate(rankings):
        for rank, item_id in enumerate(ranking, start=1):
            increment = 1.0 / (k + rank)
            scores[item_id] = scores.get(item_id, 0.0) + increment
            contributions.setdefault(item_id, {})[f"channel_{channel}"] = increment
    ordered = sorted(scores, key=lambda item_id: (-scores[item_id], item_id.bytes))
    return tuple(
        RankedItem(
            item_id=item_id, score=scores[item_id], signals=contributions[item_id]
        )
        for item_id in ordered
    )


def rerank_by_signal(
    *, items: Sequence[RankedItem], signal: str, ascending: bool = False
) -> tuple[RankedItem, ...]:
    """Reorder items by one named signal each already carries (D9/S46/S48).

    `graph_distance` reranks ascending (nearer the focal entity is more
    relevant); `evidence_count` reranks descending (more corroboration
    first). An item missing the signal sorts last in either direction
    rather than raising — a partial signal is a weaker rerank, not an
    error. The new `score` is the signal value, and `signals` is preserved
    so a later stage can read every contribution.
    """
    missing = float("inf") if ascending else float("-inf")

    def key(item: RankedItem) -> tuple[float, bytes]:
        value = item.signals.get(signal, missing)
        return (value if ascending else -value, item.item_id.bytes)

    return tuple(
        item.model_copy(update={"score": item.signals.get(signal, missing)})
        for item in sorted(items, key=key)
    )
