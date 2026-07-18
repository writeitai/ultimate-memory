"""WP-2.3 acceptance: pack installation, the D18 gate on a hallucination
sample, and the D5 `other:` funnel with promotion ranking."""

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID
from uuid import uuid4

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ultimate_memory.core import ExtensionPack
from ultimate_memory.core import PackEntityType
from ultimate_memory.core import WORK_PACK
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import FactCatalog
from ultimate_memory.spine import install_pack
from ultimate_memory.spine import PackAnchorError
from ultimate_memory.spine.settings import load_database_settings
from ultimate_memory.workers.e3 import _signature_allows

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("d0000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL integration engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real PostgreSQL registry proofs")
    config = Config(str(_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config=config, revision="base")
    command.upgrade(config=config, revision="head")
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def bootstrapped_deployment(database_engine: Engine) -> None:
    """A fresh deployment (with the universal core) per proof."""
    with database_engine.begin() as connection:
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="governance-test",
            name="Governance proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )


def test_work_pack_installs_idempotently_with_anchored_rows(
    database_engine: Engine,
) -> None:
    """Enabling the Work pack writes tier=extension rows anchored to core
    parents; enabling twice is a no-op."""
    install_pack(engine=database_engine, deployment_id=_DEPLOYMENT_ID, pack=WORK_PACK)
    install_pack(  # idempotent
        engine=database_engine, deployment_id=_DEPLOYMENT_ID, pack=WORK_PACK
    )
    with database_engine.connect() as connection:
        types = (
            connection.execute(
                text(
                    "SELECT type, parent_type, tier, pack_id FROM entity_types"
                    " WHERE deployment_id = :d AND pack_id = 'work' ORDER BY type"
                ),
                {"d": _DEPLOYMENT_ID},
            )
            .mappings()
            .all()
        )
        predicates = connection.execute(
            text(
                "SELECT count(*) FROM predicates"
                " WHERE deployment_id = :d AND pack_id = 'work'"
                " AND tier = 'extension'"
            ),
            {"d": _DEPLOYMENT_ID},
        ).scalar_one()
        enabled = connection.execute(
            text(
                "SELECT count(*) FROM deployment_extension_packs"
                " WHERE deployment_id = :d AND pack_id = 'work'"
            ),
            {"d": _DEPLOYMENT_ID},
        ).scalar_one()
    assert [(row["type"], row["parent_type"]) for row in types] == [
        ("Decision", "Event"),
        ("Goal", "Concept"),
        ("Task", "Event"),
    ]
    assert all(row["tier"] == "extension" for row in types)
    assert predicates == 6
    assert enabled == 1


def test_forking_pack_is_refused_whole(database_engine: Engine) -> None:
    """A pack anchored to an unregistered parent violates extend-never-fork
    and installs NOTHING."""
    forking = ExtensionPack(
        pack_id="forking",
        name="Forking",
        description="a pack that forks instead of extending",
        entity_types=(
            PackEntityType(
                type="Widget",
                parent_type="Gadget",  # not a registered type
                description="a forked thing",
            ),
        ),
    )
    with pytest.raises(PackAnchorError):
        install_pack(engine=database_engine, deployment_id=_DEPLOYMENT_ID, pack=forking)
    with database_engine.connect() as connection:
        count = connection.execute(
            text(
                "SELECT count(*) FROM entity_types"
                " WHERE deployment_id = :d AND type = 'Widget'"
            ),
            {"d": _DEPLOYMENT_ID},
        ).scalar_one()
    assert count == 0


def test_domain_range_gate_rejects_the_hallucination_sample(
    database_engine: Engine,
) -> None:
    """The WP acceptance: pack signatures matched at ancestor level accept the
    designed shapes and reject a hallucination sample."""
    install_pack(engine=database_engine, deployment_id=_DEPLOYMENT_ID, pack=WORK_PACK)
    facts = FactCatalog(engine=database_engine)
    signatures = facts.predicate_signatures(deployment_id=_DEPLOYMENT_ID)
    parents = facts.entity_type_parents(deployment_id=_DEPLOYMENT_ID)

    def allowed(predicate: str, subject: str, object_: str) -> bool:
        return _signature_allows(
            predicate=predicate,
            subject_type=subject,
            object_type=object_,
            signatures=signatures,
            type_parents=parents,
        )

    # designed shapes accepted:
    assert allowed("blocks", "Task", "Task")
    assert allowed("assigned_to", "Task", "Person")
    assert allowed("pursues", "Organization", "Goal")
    assert allowed("concerns", "Decision", "Document")
    # the hallucination sample rejected:
    assert not allowed("blocks", "Person", "Task")  # people don't block tasks
    assert not allowed("assigned_to", "Goal", "Person")  # goals aren't assigned
    assert not allowed("pursues", "Person", "Goal")  # not in the signature
    assert not allowed("decided_by", "Task", "Person")  # tasks aren't decided
    assert not allowed("blocks", "Task", "Unregistered")  # unknown type fails closed


def test_other_funnel_registers_counts_and_ranks(database_engine: Engine) -> None:
    """The D5 escape: other:<freetext> lands as tier=other, usage-counted and
    ranked for promotion; the grammar is enforced."""
    facts = FactCatalog(engine=database_engine)
    facts.ensure_other_predicate(
        deployment_id=_DEPLOYMENT_ID, predicate="other:sponsors"
    )
    facts.ensure_other_predicate(  # idempotent
        deployment_id=_DEPLOYMENT_ID, predicate="other:sponsors"
    )
    facts.ensure_other_predicate(
        deployment_id=_DEPLOYMENT_ID, predicate="other:licenses"
    )

    subject, object_ = uuid4(), uuid4()
    with database_engine.begin() as connection:
        for entity_id, name in ((subject, "Acme"), (object_, "City Marathon")):
            connection.execute(
                text(
                    "INSERT INTO entities (entity_id, deployment_id, type,"
                    " canonical_name, normalized_name)"
                    " VALUES (:e, :d, 'Organization', :n, lower(:n))"
                ),
                {"e": entity_id, "d": _DEPLOYMENT_ID, "n": name},
            )
    for _ in range(2):  # same fact twice: one relation, ONE usage bump
        facts.upsert_relation(
            deployment_id=_DEPLOYMENT_ID,
            subject_entity_id=subject,
            predicate="other:sponsors",
            object_entity_id=object_,
            claim_id=uuid4(),
            doc_id=uuid4(),
            normalizer_version="test",
        )

    candidates = facts.promotion_candidates(deployment_id=_DEPLOYMENT_ID)
    assert candidates[0] == ("other:sponsors", 1)
    assert ("other:licenses", 0) in candidates

    # the funnel never leaks into the governed prompt vocabulary:
    prompt = facts.predicate_prompt_lines(deployment_id=_DEPLOYMENT_ID)
    assert "other:sponsors" not in prompt
    assert "works_for" in prompt
