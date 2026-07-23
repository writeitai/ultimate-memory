"""The deterministic section snap (D57, e1 §3): LLM spans → block partition.

The structurer LLM proposes section boundaries as character spans, and being
an LLM it can propose anything — overlaps, gaps, reversed spans, offsets past
the end of the document, absurd nesting. Chunks are runs of whole blocks that
must never cross a section, so sections MUST be unions of whole blocks; this
module is the deterministic layer that makes that true for every possible
input ("LLM proposes, a deterministic layer disposes").

The algorithm is pure and total: proposed spans + the block grid in, a
well-formed section tree out, never an exception. Malformed input degrades to
a coarser but correct partition; the worst case is the synthetic root alone.
"""

from collections.abc import Sequence
from typing import Final

from rememberstack.model import Block
from rememberstack.model import ProposedSection
from rememberstack.model import SnappedSection

SECTION_ROLES: Final = frozenset(
    {
        "body",
        "abstract",
        "introduction",
        "results",
        "methods",
        "discussion",
        "conclusion",
        "references",
        "appendix",
        "table",
        "figure_caption",
        "nav",
        "boilerplate",
        "legal",
    }
)
"""The section_role enum (D39): anything else the LLM invents becomes body."""

_MAX_DEPTH: Final = 16
"""Nesting deeper than this is flattened away — the blocks stay with the
deepest surviving ancestor. A guard against pathological LLM recursion, not a
semantic limit; real documents never approach it."""


def snap_sections(
    *,
    proposed: Sequence[ProposedSection],
    blocks: Sequence[Block],
    title: str | None,
    markdown_chars: int,
) -> tuple[SnappedSection, ...]:
    """Normalize a proposed section tree onto the block grid (e1 §3).

    The five steps, in order: (1) every proposed start snaps BACKWARD to the
    start of the block containing it; (2) siblings sort by snapped start,
    longer proposed span first, emission order last, and siblings sharing a
    snapped start collapse into one — the longer span wins and adopts the
    loser's children; (3) siblings tile forward — each ends where the next
    begins, the last at its parent's end, so blocks before the first child
    are the parent's direct content; (4) children clip to their parent's
    range and empty sections are pruned; (5) the root always spans the whole
    block sequence.

    Returns depth-first document order, root first. The empty document gets
    the lone root with the empty block range ``0..-1``.
    """
    root_title = title or ""
    last_block = len(blocks) - 1
    root = SnappedSection(
        node_path="0",
        parent_path=None,
        title=root_title,
        role="body",
        block_start=0,
        block_end=last_block,
        char_start=0,
        char_end=markdown_chars,
        summary="",
        ordinal=0,
    )
    if last_block < 0:
        return (root,)
    output: list[SnappedSection] = [root]
    _snap_level(
        nodes=proposed,
        parent_path="0",
        parent_start=0,
        parent_end=last_block,
        blocks=blocks,
        depth=1,
        output=output,
    )
    return tuple(output)


def _snap_level(
    *,
    nodes: Sequence[ProposedSection],
    parent_path: str,
    parent_start: int,
    parent_end: int,
    blocks: Sequence[Block],
    depth: int,
    output: list[SnappedSection],
) -> None:
    """Snap one sibling level into the parent's block range, then recurse."""
    if depth >= _MAX_DEPTH:
        return
    candidates = _ordered_candidates(
        nodes=nodes, parent_start=parent_start, parent_end=parent_end, blocks=blocks
    )
    for index, (start, node, adopted) in enumerate(candidates):
        end = (
            candidates[index + 1][0] - 1  # tile: end where the next begins
            if index + 1 < len(candidates)
            else parent_end
        )
        if end < start:
            continue  # empty after tiling/clipping: pruned
        path = f"{parent_path}.{index}"
        output.append(
            SnappedSection(
                node_path=path,
                parent_path=parent_path,
                title=node.title,
                role=_sanitize_role(role=node.role),
                block_start=start,
                block_end=end,
                char_start=blocks[start].char_start,
                char_end=blocks[end].char_end,
                summary=node.summary,
                ordinal=len(output),
            )
        )
        _snap_level(
            nodes=(*node.children, *adopted),
            parent_path=path,
            parent_start=start,
            parent_end=end,
            blocks=blocks,
            depth=depth + 1,
            output=output,
        )


def _ordered_candidates(
    *,
    nodes: Sequence[ProposedSection],
    parent_start: int,
    parent_end: int,
    blocks: Sequence[Block],
) -> list[tuple[int, ProposedSection, tuple[ProposedSection, ...]]]:
    """Snap starts, order siblings, collapse same-start ties (steps 1–2).

    Yields ``(snapped_start, winner, adopted_children)`` with strictly
    increasing starts; a tie's loser is dropped and its children are adopted
    by the winner so a duplicated heading cannot erase a subtree. Step 4's
    clipping is applied here where it prunes whole nodes: a zero-length
    proposal, and a proposal whose char span lies entirely outside its
    parent's char range, are empty after clipping — pruned, never inflated
    into a real section by the start clamp + tiling (Codex review).
    """
    parent_char_start = blocks[parent_start].char_start
    parent_char_end = blocks[parent_end].char_end
    snapped: list[tuple[int, int, int, ProposedSection]] = []
    for emission_index, node in enumerate(nodes):
        if node.char_end <= node.char_start:
            continue  # zero-length (or reversed): pruned
        if node.char_end <= parent_char_start or node.char_start >= parent_char_end:
            continue  # no overlap with the parent: empty after clipping
        start = _snap_start(char=node.char_start, blocks=blocks)
        start = max(start, parent_start)
        if start > parent_end:
            continue  # entirely outside the parent: pruned by clipping
        proposed_length = node.char_end - node.char_start
        snapped.append((start, -proposed_length, emission_index, node))
    snapped.sort(key=lambda entry: entry[:3])
    candidates: list[tuple[int, ProposedSection, tuple[ProposedSection, ...]]] = []
    for start, _, _, node in snapped:
        if candidates and candidates[-1][0] == start:
            winner_start, winner, adopted = candidates[-1]
            candidates[-1] = (winner_start, winner, (*adopted, *node.children))
            continue
        candidates.append((start, node, ()))
    return candidates


def _snap_start(*, char: int, blocks: Sequence[Block]) -> int:
    """Step 1: the ordinal of the block containing ``char``, snapping backward.

    A char before the first block clamps to block 0; a char past the last
    block's end clamps to the last block. Chars falling between blocks (in
    inter-block whitespace) belong to the preceding block — backward snap.
    """
    if char <= blocks[0].char_start:
        return 0
    for ordinal in range(len(blocks) - 1, -1, -1):
        if blocks[ordinal].char_start <= char:
            return ordinal
    return 0


def _sanitize_role(*, role: str) -> str:
    """An invented role name degrades to body — the enum is the contract."""
    normalized = role.strip().lower()
    return normalized if normalized in SECTION_ROLES else "body"
