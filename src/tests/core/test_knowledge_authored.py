"""Pure WP-6.6 authored-frontmatter and declaration-lint proofs."""

from uuid import UUID

import pytest

from ultimate_memory.core import authored_declaration_is_empty
from ultimate_memory.core import KnowledgeAuthoredDeclarationError
from ultimate_memory.core import parse_knowledge_authored_frontmatter
from ultimate_memory.model import EntityRuleParams
from ultimate_memory.model import KnowledgeEvidenceRole
from ultimate_memory.model import PredicateBeatRuleParams

_LINEAGE_ID = UUID("66000000-0000-0000-0000-000000000001")
_RELATION_ID = UUID("66000000-0000-0000-0000-000000000002")
_ENTITY_ID = UUID("66000000-0000-0000-0000-000000000003")


def test_frontmatter_parser_reads_shorthands_and_rich_rules() -> None:
    """JSON-compatible YAML becomes typed citations, rules, and normalized pages."""
    markdown = f"""---
title: A plan
cites:
  - supports:claim:{_LINEAGE_ID}:chunk-stable
  - relation:{_RELATION_ID}
watch:
  - entity:{_ENTITY_ID}
  - {{"kind":"predicate_beat","predicate":"works_for"}}
  - page:as-is/ordering-flow
---
# A plan
"""

    declaration = parse_knowledge_authored_frontmatter(markdown=markdown)

    assert declaration.citations is not None
    assert declaration.citations[0].role is KnowledgeEvidenceRole.CITES
    assert declaration.citations[0].relation_id == _RELATION_ID
    assert declaration.citations[1].role is KnowledgeEvidenceRole.SUPPORTS
    assert declaration.citations[1].claim_lineage_id == _LINEAGE_ID
    assert declaration.watch_rules == (
        EntityRuleParams(entity_id=_ENTITY_ID),
        PredicateBeatRuleParams(predicate="works_for"),
    )
    assert declaration.watched_page_paths == ("as-is/ordering-flow.md",)


def test_inline_empty_lists_are_explicit_declaration_removals() -> None:
    """Missing keys preserve prior declarations while explicit empty lists clear them."""
    absent = parse_knowledge_authored_frontmatter(markdown="# No header\n")
    explicit = parse_knowledge_authored_frontmatter(
        markdown="---\ncites: []\nwatch: []\n---\n# Empty\n"
    )

    assert absent.citations is None
    assert absent.watch_rules is None
    assert absent.watched_page_paths is None
    assert explicit.citations == ()
    assert explicit.watch_rules == ()
    assert explicit.watched_page_paths == ()


@pytest.mark.parametrize(
    ("markdown", "message"),
    (
        ("---\ncites: [broken\n---\n", "valid JSON"),
        ("---\nwatch:\n  nested: value\n---\n", "flat list"),
        ("---\nwatch:\n  - page:../escape\n---\n", "normalized relative"),
        ("---\ncites:\n  - relation:not-a-uuid\n---\n", "invalid UUID"),
        ("---\ncites: []\ncites: []\n---\n", "repeats"),
        ("---\ncites: []\n", "closing delimiter"),
    ),
)
def test_malformed_owned_frontmatter_fails_visibly(markdown: str, message: str) -> None:
    """Authored declaration errors never degrade to an invisible empty declaration."""
    with pytest.raises(KnowledgeAuthoredDeclarationError, match=message):
        parse_knowledge_authored_frontmatter(markdown=markdown)


def test_declaration_lint_counts_every_alerting_channel() -> None:
    """Only a page with no citations, rule watches, or page watches is invisible."""
    assert authored_declaration_is_empty(
        citation_count=0, watch_rule_count=0, page_watch_count=0
    )
    assert not authored_declaration_is_empty(
        citation_count=0, watch_rule_count=1, page_watch_count=0
    )
    with pytest.raises(ValueError, match="non-negative"):
        authored_declaration_is_empty(
            citation_count=-1, watch_rule_count=0, page_watch_count=0
        )
