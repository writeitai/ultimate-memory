"""The E1 chunker's bound properties (e1 §4): determinism, anchors, boundaries."""

from uuid import uuid4

from rememberstack.core import blockize
from rememberstack.core import ChunkerParams
from rememberstack.core import is_anchor
from rememberstack.core import pack_blocks
from rememberstack.model import Block
from rememberstack.model import SectionSpan


def _root_section(*, block_count: int) -> tuple[SectionSpan, ...]:
    """A synthetic root spanning the whole block grid."""
    return (
        SectionSpan(
            section_id=uuid4(),
            node_path="0",
            role="body",
            block_start=0,
            block_end=block_count - 1,
        ),
    )


def _document(*, paragraphs: int) -> tuple[str, tuple[Block, ...]]:
    """A deterministic document of distinct multi-word paragraphs."""
    source = "\n\n".join(
        f"Paragraph {index} says something specific about topic {index}."
        for index in range(paragraphs)
    )
    return source, blockize(document_md=source)


def test_packing_is_deterministic_and_partitions_the_grid() -> None:
    """Chunks are a non-overlapping, gap-free partition of the section's blocks."""
    source, blocks = _document(paragraphs=40)
    params = ChunkerParams(token_budget=30)
    sections = _root_section(block_count=len(blocks))

    first = pack_blocks(
        blocks=blocks, sections=sections, document_md=source, params=params
    )
    second = pack_blocks(
        blocks=blocks, sections=sections, document_md=source, params=params
    )
    assert first == second

    covered: list[int] = []
    for chunk in first:
        assert chunk.block_start <= chunk.block_end
        covered.extend(range(chunk.block_start, chunk.block_end + 1))
    assert covered == list(range(len(blocks)))


def test_chunks_never_cross_a_section_boundary_and_only_leaves_pack() -> None:
    """A section boundary is always a chunk boundary, and only the deepest
    partition packs — the production shape includes the parent (Codex review:
    packing every tree node would chunk each block twice)."""
    source, blocks = _document(paragraphs=6)
    half = len(blocks) // 2
    sections = (
        SectionSpan(  # the parent — spans everything, must NOT pack
            section_id=uuid4(),
            node_path="0",
            role="body",
            block_start=0,
            block_end=len(blocks) - 1,
        ),
        SectionSpan(
            section_id=uuid4(),
            node_path="0.0",
            role="body",
            block_start=0,
            block_end=half - 1,
        ),
        SectionSpan(
            section_id=uuid4(),
            node_path="0.1",
            role="body",
            block_start=half,
            block_end=len(blocks) - 1,
        ),
    )
    chunks = pack_blocks(
        blocks=blocks,
        sections=sections,
        document_md=source,
        params=ChunkerParams(token_budget=10_000),
    )
    assert len(chunks) == 2
    assert chunks[0].block_end == half - 1
    assert chunks[1].block_start == half
    covered = [
        ordinal
        for chunk in chunks
        for ordinal in range(chunk.block_start, chunk.block_end + 1)
    ]
    assert covered == list(range(len(blocks)))  # each block exactly once


def test_leaf_order_is_numeric_not_lexical() -> None:
    """Section '0.2' packs before '0.10' (Codex review: lexical order breaks
    chunk ordinals and D56 neighbor inputs on wide trees)."""
    source, blocks = _document(paragraphs=12)
    third = len(blocks) // 3
    paths = ("0.2", "0.10", "0.1")  # deliberately shuffled, lexically tricky
    starts = (third, 2 * third, 0)
    ends = (2 * third - 1, len(blocks) - 1, third - 1)
    sections = tuple(
        SectionSpan(
            section_id=uuid4(),
            node_path=path,
            role="body",
            block_start=start,
            block_end=end,
        )
        for path, start, end in zip(paths, starts, ends, strict=True)
    )
    chunks = pack_blocks(
        blocks=blocks,
        sections=sections,
        document_md=source,
        params=ChunkerParams(token_budget=10_000),
    )
    assert [chunk.block_start for chunk in chunks] == [0, third, 2 * third]


def test_an_oversized_block_ships_as_its_own_chunk() -> None:
    """A block alone over budget is never split — it becomes one oversized chunk."""
    huge = "word " * 500
    source = f"Small one.\n\n{huge.strip()}.\n\nSmall two.\n"
    blocks = blockize(document_md=source)
    chunks = pack_blocks(
        blocks=blocks,
        sections=_root_section(block_count=len(blocks)),
        document_md=source,
        params=ChunkerParams(token_budget=50),
    )
    oversized = [chunk for chunk in chunks if chunk.token_count > 50]
    assert len(oversized) == 1
    assert oversized[0].block_start == oversized[0].block_end


def test_an_early_edit_perturbs_boundaries_only_to_the_next_anchor() -> None:
    """The anchor property (e1 §4): packing after an anchor is independent of
    everything before it, so chunk identities re-align at the first anchor."""
    source, blocks = _document(paragraphs=120)
    params = ChunkerParams(token_budget=25, anchor_modulus=8, anchor_min_gap_tokens=0)
    edited_source = source.replace("topic 0", "topic zero, freshly edited,")
    edited_blocks = blockize(document_md=edited_source)

    anchored = [
        block.ordinal
        for block in blocks
        if is_anchor(block_hash=block.block_hash, params=params)
    ]
    assert anchored, "the corpus must contain at least one anchor for this proof"

    original = pack_blocks(
        blocks=blocks,
        sections=_root_section(block_count=len(blocks)),
        document_md=source,
        params=params,
    )
    edited = pack_blocks(
        blocks=edited_blocks,
        sections=_root_section(block_count=len(edited_blocks)),
        document_md=edited_source,
        params=params,
    )
    original_hashes = {chunk.chunk_content_hash for chunk in original}
    realigned = [
        chunk
        for chunk in edited
        if chunk.block_start > anchored[0]
        and chunk.chunk_content_hash in original_hashes
    ]
    assert realigned, "post-anchor chunks must re-align with the original packing"


def test_empty_section_packs_to_no_chunks() -> None:
    """An empty document's root section yields zero chunks, not a degenerate one."""
    chunks = pack_blocks(
        blocks=(),
        sections=(
            SectionSpan(
                section_id=uuid4(),
                node_path="0",
                role="body",
                block_start=0,
                block_end=-1,
            ),
        ),
        document_md="",
        params=ChunkerParams(),
    )
    assert chunks == ()


def test_parent_direct_content_is_packed_not_dropped() -> None:
    """Codex review: blocks a parent owns directly — before its first child
    and in gaps between children — must reach chunks, attributed to the
    parent. A leaf-only walk silently dropped them from chunking, embedding,
    and extraction."""
    source, blocks = _document(paragraphs=9)
    parent = SectionSpan(
        section_id=uuid4(), node_path="0", role="body", block_start=0, block_end=8
    )
    early_child = SectionSpan(  # blocks 0..2 before it belong to the parent
        section_id=uuid4(), node_path="0.0", role="methods", block_start=3, block_end=4
    )
    late_child = SectionSpan(  # blocks 5..6 between children: parent again
        section_id=uuid4(), node_path="0.1", role="results", block_start=7, block_end=8
    )
    chunks = pack_blocks(
        blocks=blocks,
        sections=(parent, early_child, late_child),
        document_md=source,
        params=ChunkerParams(token_budget=10_000),
    )
    covered = sorted(
        ordinal
        for chunk in chunks
        for ordinal in range(chunk.block_start, chunk.block_end + 1)
    )
    assert covered == list(range(9))  # every block exactly once
    owners = {
        (chunk.block_start, chunk.block_end): chunk.section_id for chunk in chunks
    }
    assert owners[(0, 2)] == parent.section_id  # leading run: parent-direct
    assert owners[(3, 4)] == early_child.section_id
    assert owners[(5, 6)] == parent.section_id  # gap run: parent-direct
    assert owners[(7, 8)] == late_child.section_id
