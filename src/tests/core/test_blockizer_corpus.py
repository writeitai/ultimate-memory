"""The blockizer golden corpus: locked hashes per BLOCKIZER_VERSION (WP-0.7, D57)."""

import json
from pathlib import Path

from markdown_it import __version__ as markdown_it_version

from ultimate_memory.core import block_hash
from ultimate_memory.core import blockize
from ultimate_memory.core import BLOCKIZER_VERSION

_CORPUS = Path(__file__).resolve().parents[1] / "blockizer_corpus"


def test_seed_document_hash_sequence_is_locked() -> None:
    """A parser or normalization change trips this lock — drift is a version bump."""
    expected = json.loads((_CORPUS / "expected_hashes.json").read_text())
    source = (_CORPUS / "seed_mixed.md").read_text()

    assert expected["blockizer_version"] == BLOCKIZER_VERSION
    assert expected["parser"] == f"markdown-it-py=={markdown_it_version}"

    blocks = blockize(document_md=source)
    observed = [
        {"ordinal": block.ordinal, "type": block.type.value, "hash": block.block_hash}
        for block in blocks
    ]
    assert observed == expected["blocks"]


def test_offsets_slice_the_source_exactly() -> None:
    """Every block's offsets are a real slice of document.md (the grounding chain)."""
    source = (_CORPUS / "seed_mixed.md").read_text()
    for block in blockize(document_md=source):
        raw = source[block.char_start : block.char_end]
        assert raw
        assert block_hash(raw=raw) == block.block_hash


def test_reflow_does_not_change_identity() -> None:
    """A pure hard-wrap change never changes a block's hash (D56 reuse depends on it)."""
    wrapped = "One sentence split\nacross three\nsource lines.\n"
    reflowed = "One sentence split across three source lines.\n"
    (wrapped_block,) = blockize(document_md=wrapped)
    (reflowed_block,) = blockize(document_md=reflowed)
    assert wrapped_block.block_hash == reflowed_block.block_hash


def test_edit_changes_exactly_the_edited_block() -> None:
    """Editing one paragraph changes only its hash — the D56 edit-locality property."""
    original = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n"
    edited = "First paragraph.\n\nSecond paragraph, edited.\n\nThird paragraph.\n"
    before = [block.block_hash for block in blockize(document_md=original)]
    after = [block.block_hash for block in blockize(document_md=edited)]
    assert before[0] == after[0]
    assert before[1] != after[1]
    assert before[2] == after[2]
