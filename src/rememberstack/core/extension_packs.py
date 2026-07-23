"""System-shipped extension packs (registries §4, D15): the Work pack.

Extensions are not second-class: a pack type lives in the same entity space,
graph, ER machinery, and relations as core types — the tier is a governance
distinction (stability commitment, golden-set obligation), not a capability
one. Every pack type anchors to a core parent (extend-never-fork); the
installer refuses a pack whose anchors don't exist.
"""

from dataclasses import dataclass
from typing import Final

_CORE_ROOTS: Final = (
    "Person",
    "Organization",
    "Place",
    "Document",
    "Event",
    "Concept",
    "Project",
    "Product",
)


@dataclass(frozen=True)
class PackEntityType:
    """One extension entity type anchored to a core parent."""

    type: str
    parent_type: str
    description: str
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class PackPredicate:
    """One extension predicate with its domain/range signatures (D18)."""

    predicate: str
    description: str
    signatures: tuple[tuple[str, str], ...]
    synonyms: tuple[str, ...] = ()
    is_change_prone: bool = False


@dataclass(frozen=True)
class ExtensionPack:
    """A predefined bundle a deployment enables as one unit."""

    pack_id: str
    name: str
    description: str
    entity_types: tuple[PackEntityType, ...] = ()
    predicates: tuple[PackPredicate, ...] = ()


def _to_any(*subjects: str) -> tuple[tuple[str, str], ...]:
    """Signatures pairing each subject with every core root ("→ any")."""
    return tuple(
        (subject, object_root) for subject in subjects for object_root in _CORE_ROOTS
    )


WORK_PACK: Final = ExtensionPack(
    pack_id="work",
    name="Work",
    description=(
        "Work-shaped concepts for assistant, agency, and project-management "
        "deployments: tasks, decisions, and goals as first-class entities."
    ),
    entity_types=(
        PackEntityType(
            type="Task",
            parent_type="Event",
            description="an intended occurrence with a lifecycle",
            examples=("migrate the billing tables", "draft the Q3 report"),
        ),
        PackEntityType(
            type="Decision",
            parent_type="Event",
            description="a commitment made at a point in time",
            examples=("adopt PostgreSQL", "freeze the API surface"),
        ),
        PackEntityType(
            type="Goal",
            parent_type="Concept",
            description="a desired state — held, not occurring",
            examples=("sub-second p99 latency", "SOC 2 compliance"),
        ),
    ),
    predicates=(
        PackPredicate(
            predicate="blocks",
            description="the subject task prevents progress on the object task",
            signatures=(("Task", "Task"),),
        ),
        PackPredicate(
            predicate="depends_on",
            description="the subject task requires the object task first",
            signatures=(("Task", "Task"),),
        ),
        PackPredicate(
            predicate="concerns",
            description="the subject task or decision is about the object",
            signatures=_to_any("Task", "Decision"),
        ),
        PackPredicate(
            predicate="decided_by",
            description="who made the decision",
            signatures=(("Decision", "Person"), ("Decision", "Organization")),
        ),
        PackPredicate(
            predicate="assigned_to",
            description="who is responsible for the task",
            signatures=(("Task", "Person"), ("Task", "Organization")),
            is_change_prone=True,
        ),
        PackPredicate(
            predicate="pursues",
            description="the project or organization works toward the goal",
            signatures=(("Project", "Goal"), ("Organization", "Goal")),
        ),
    ),
)
