"""Extension-pack installation (registries §4/§7, D15): enable a pack as a unit.

Installing writes the pack's registry rows for one deployment — entity types,
predicates, and domain/range signatures, all `tier='extension'` with the pack
id — after verifying every anchor exists (extend-never-fork: an extension
type MUST declare a registered parent; a pack that forks is refused whole).
Idempotent: enabling twice is a no-op.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine

from ultimate_memory.core.extension_packs import ExtensionPack


class PackAnchorError(Exception):
    """A pack type's parent is not registered — extend-never-fork refused it."""


def install_pack(*, engine: Engine, deployment_id: UUID, pack: ExtensionPack) -> None:
    """Enable one pack for one deployment in a single transaction."""
    with engine.begin() as connection:
        _require_anchors(connection=connection, deployment_id=deployment_id, pack=pack)
        connection.execute(
            _UPSERT_PACK,
            {
                "pack_id": pack.pack_id,
                "name": pack.name,
                "description": pack.description,
            },
        )
        connection.execute(
            _ENABLE_PACK, {"deployment_id": deployment_id, "pack_id": pack.pack_id}
        )
        for entity_type in pack.entity_types:
            connection.execute(
                _INSERT_TYPE,
                {
                    "deployment_id": deployment_id,
                    "type": entity_type.type,
                    "parent_type": entity_type.parent_type,
                    "description": entity_type.description,
                    "examples": list(entity_type.examples),
                    "pack_id": pack.pack_id,
                },
            )
        for predicate in pack.predicates:
            connection.execute(
                _INSERT_PREDICATE,
                {
                    "deployment_id": deployment_id,
                    "predicate": predicate.predicate,
                    "description": predicate.description,
                    "synonyms": list(predicate.synonyms),
                    "is_change_prone": predicate.is_change_prone,
                    "pack_id": pack.pack_id,
                },
            )
            for subject_type, object_type in predicate.signatures:
                connection.execute(
                    _INSERT_SIGNATURE,
                    {
                        "deployment_id": deployment_id,
                        "predicate": predicate.predicate,
                        "subject_type": subject_type,
                        "object_type": object_type,
                    },
                )


def _require_anchors(
    *, connection: Connection, deployment_id: UUID, pack: ExtensionPack
) -> None:
    """Refuse the whole pack if any parent anchor is unregistered (D15)."""
    pack_types = {entity_type.type for entity_type in pack.entity_types}
    registered = {
        row[0]
        for row in connection.execute(_SELECT_TYPES, {"deployment_id": deployment_id})
    }
    known = registered | pack_types
    for entity_type in pack.entity_types:
        if entity_type.parent_type not in known:
            raise PackAnchorError(
                f"pack {pack.pack_id!r} type {entity_type.type!r} anchors to "
                f"unregistered parent {entity_type.parent_type!r} "
                "(extend-never-fork, D15)"
            )
    signature_types = {
        entity_type
        for predicate in pack.predicates
        for pair in predicate.signatures
        for entity_type in pair
    }
    unknown = signature_types - known
    if unknown:
        raise PackAnchorError(
            f"pack {pack.pack_id!r} signatures reference unregistered "
            f"types {sorted(unknown)!r}"
        )


_SELECT_TYPES = text(
    "SELECT type FROM entity_types WHERE deployment_id = :deployment_id"
)

_UPSERT_PACK = text(
    """
    INSERT INTO extension_packs (pack_id, name, description)
    VALUES (:pack_id, :name, :description)
    ON CONFLICT (pack_id) DO NOTHING
    """
)

_ENABLE_PACK = text(
    """
    INSERT INTO deployment_extension_packs (deployment_id, pack_id)
    VALUES (:deployment_id, :pack_id)
    ON CONFLICT (deployment_id, pack_id) DO NOTHING
    """
)

_INSERT_TYPE = text(
    """
    INSERT INTO entity_types (
        deployment_id, type, parent_type, description, examples, tier, pack_id
    ) VALUES (
        :deployment_id, :type, :parent_type, :description, :examples,
        'extension', :pack_id
    )
    ON CONFLICT (deployment_id, type) DO NOTHING
    """
)

_INSERT_PREDICATE = text(
    """
    INSERT INTO predicates (
        deployment_id, predicate, parent_predicate, description, synonyms,
        is_change_prone, tier, pack_id
    ) VALUES (
        :deployment_id, :predicate, 'related_to', :description, :synonyms,
        :is_change_prone, 'extension', :pack_id
    )
    ON CONFLICT (deployment_id, predicate) DO NOTHING
    """
)

_INSERT_SIGNATURE = text(
    """
    INSERT INTO predicate_signatures (
        deployment_id, predicate, subject_type, object_type
    ) VALUES (
        :deployment_id, :predicate, :subject_type, :object_type
    )
    ON CONFLICT (deployment_id, predicate, subject_type, object_type) DO NOTHING
    """
)
