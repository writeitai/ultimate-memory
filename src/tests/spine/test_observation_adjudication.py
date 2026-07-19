"""WP-2.5 acceptance: the D43 worked examples, the fail-safe contract, and
the contradiction eval gate (the shipping criterion)."""

from collections.abc import Iterator
from datetime import timedelta
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

from ultimate_memory.adapters.testing import FakeModelProvider
from ultimate_memory.eval import run_contradiction_suite
from ultimate_memory.eval import seed_contradiction_cases
from ultimate_memory.model import DeploymentBootstrapInput
from ultimate_memory.spine import DeploymentBootstrapper
from ultimate_memory.spine import OBSERVATION_ADJUDICATOR_VERSION
from ultimate_memory.spine import ObservationAdjudicator
from ultimate_memory.spine import ObservationSettings
from ultimate_memory.spine.settings import load_database_settings

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOYMENT_ID = UUID("f0000000-0000-0000-0000-000000000001")


def _semantic_router(prompt: str, type_name: str) -> dict[str, object]:
    """A deterministic D43 stand-in judging the worked examples correctly:
    same property + same period + different value -> contradict; changing
    state (no period marker on both) with different value -> supersede;
    same value -> evidence; different property/period -> new."""
    if type_name != "ObservationVerdict":
        raise AssertionError(f"unexpected generate call: {type_name}")
    lines = [
        line for line in prompt.splitlines() if line.startswith(("EXISTING:", "NEW:"))
    ]
    existing, new = (line.split(":", 1)[1].strip().strip("'\"") for line in lines)

    def parse(statement: str) -> tuple[str, str, str]:
        period = ""
        for marker in ("FY2023", "Q1-2023", "year-end 2023"):
            if marker in statement:
                period = marker
        prop = (
            "revenue"
            if "revenue" in statement
            else (
                "headcount"
                if "headcount" in statement
                else ("profit" if "profit" in statement else "other")
            )
        )
        value = statement.rsplit(" ", 1)[-1].rstrip(".")
        return prop, period, value

    p1, per1, v1 = parse(existing)
    p2, per2, v2 = parse(new)
    if p1 != p2 or (per1 and per2 and per1 != per2):
        return {"outcome": "new", "confidence": 0.9}
    if v1 == v2:
        return {"outcome": "evidence", "confidence": 0.9}
    if per1 and per2 and per1 == per2:
        return {"outcome": "contradict", "confidence": 0.9}
    return {"outcome": "supersede", "confidence": 0.9, "rationale": "state moved"}


@pytest.fixture(scope="module")
def database_engine() -> Iterator[Engine]:
    """Apply structural head and expose the accepted PostgreSQL integration engine."""
    try:
        database_url = load_database_settings().sqlalchemy_url()
    except ValidationError:
        pytest.skip("UGM_DATABASE_URL is required for real PostgreSQL D43 proofs")
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
    """A fresh deployment per proof."""
    with database_engine.begin() as connection:
        for table in (
            "observation_adjudications",
            "observation_evidence",
            "observations",
            "claims",
        ):
            connection.execute(statement=text(f"TRUNCATE TABLE {table} CASCADE"))
        connection.execute(statement=text("TRUNCATE TABLE deployments CASCADE"))
    DeploymentBootstrapper(engine=database_engine).bootstrap_deployment(
        deployment_input=DeploymentBootstrapInput(
            deployment_id=_DEPLOYMENT_ID,
            slug="d43-test",
            name="Observation adjudication proofs",
            default_language="en",
            raw_bucket="mem://raw",
            artifacts_bucket="mem://artifacts",
            corpusfs_bucket="mem://corpusfs",
        )
    )


def _adjudicator(
    *, engine: Engine, router=None, **overrides: object
) -> tuple[ObservationAdjudicator, FakeModelProvider]:
    """One composed adjudicator with the semantic router by default."""
    provider = FakeModelProvider(generate_router=router or _semantic_router)
    return (
        ObservationAdjudicator(
            engine=engine,
            model_provider=provider,
            settings=ObservationSettings(**overrides),  # type: ignore[arg-type]
        ),
        provider,
    )


def _entity(*, engine: Engine) -> UUID:
    """One Organization entity."""
    entity_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO entities (entity_id, deployment_id, type,"
                " canonical_name, normalized_name)"
                " VALUES (:e, :d, 'Organization', 'Acme', 'acme')"
            ),
            {"e": entity_id, "d": _DEPLOYMENT_ID},
        )
    return entity_id


def _add(*, adjudicator: ObservationAdjudicator, entity: UUID, statement: str) -> UUID:
    """One observation through the cascade with a fresh claim."""
    return adjudicator.add_observation(
        deployment_id=_DEPLOYMENT_ID,
        subject_entity_id=entity,
        statement=statement,
        claim_id=uuid4(),
        doc_id=uuid4(),
    )


def test_headcount_supersession_caps_and_preserves_the_time_slice(
    database_engine: Engine,
) -> None:
    """The D43 worked example: 500 -> 600 caps O1 and keeps its statement —
    an observation is a time-slice, never an in-place edit."""
    adjudicator, provider = _adjudicator(engine=database_engine)
    acme = _entity(engine=database_engine)
    first = _add(
        adjudicator=adjudicator, entity=acme, statement="Acme's headcount is 500"
    )
    assert provider.generated_prompts == []  # first mention: zero LLM
    second = _add(
        adjudicator=adjudicator, entity=acme, statement="Acme's headcount is 600"
    )
    with database_engine.connect() as connection:
        rows = {
            row["observation_id"]: dict(row)
            for row in connection.execute(
                text(
                    "SELECT observation_id, statement, valid_until, invalidated_at"
                    " FROM observations"
                )
            ).mappings()
        }
        cap_reason = connection.execute(
            text(
                "SELECT count(*) FROM observation_adjudications"
                " WHERE observation_id = :o AND outcome = 'supersede'"
            ),
            {"o": first},
        ).scalar_one()
    assert rows[first]["statement"] == "Acme's headcount is 500"  # unchanged
    assert rows[first]["valid_until"] is not None  # capped
    assert rows[first]["invalidated_at"] is None  # ended, not wrong
    assert rows[second]["valid_until"] is None  # the current slice
    assert cap_reason == 1  # every cap writes its reason row


def test_fixed_period_figures_contradict_and_both_stand(
    database_engine: Engine,
) -> None:
    """The no-cap rule: conflicting FY2023 revenue figures are NEVER
    superseded — both stand with a shared contradiction_group."""
    adjudicator, _ = _adjudicator(engine=database_engine)
    acme = _entity(engine=database_engine)
    first = _add(
        adjudicator=adjudicator, entity=acme, statement="Acme's FY2023 revenue was $5M"
    )
    second = _add(
        adjudicator=adjudicator, entity=acme, statement="Acme's FY2023 revenue was $7M"
    )
    with database_engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT observation_id, valid_until, contradiction_group"
                    " FROM observations"
                )
            )
            .mappings()
            .all()
        )
    by_id = {row["observation_id"]: dict(row) for row in rows}
    assert by_id[first]["valid_until"] is None  # NOT capped (no-cap rule)
    assert by_id[second]["valid_until"] is None
    groups = {row["contradiction_group"] for row in rows}
    assert len(groups) == 1 and None not in groups  # shared, both stand


def test_corpus_redundancy_collapses_with_zero_llm(database_engine: Engine) -> None:
    """The biggest saver: an exact re-assertion adds evidence, no new row,
    no model call."""
    adjudicator, provider = _adjudicator(engine=database_engine)
    acme = _entity(engine=database_engine)
    first = _add(
        adjudicator=adjudicator, entity=acme, statement="Acme is based in Brno"
    )
    second = _add(
        adjudicator=adjudicator, entity=acme, statement="Acme is based in Brno"
    )
    assert second == first
    assert provider.generated_prompts == []
    with database_engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM observations")
        ).scalar_one()
        links = connection.execute(
            text("SELECT count(*) FROM observation_evidence")
        ).scalar_one()
    assert count == 1
    assert links == 2


def test_supersede_below_margin_is_coerced_to_coexist(database_engine: Engine) -> None:
    """THE BINDING CONTRACT: below the supersede margin the cap is refused —
    the failure mode is a duplicate, never an overwrite."""

    def low_margin_router(prompt: str, type_name: str) -> dict[str, object]:
        return {"outcome": "supersede", "confidence": 0.79}  # above the 0.75
        # ladder floor (no frontier re-ask), below the 0.8 supersede margin

    adjudicator, _ = _adjudicator(engine=database_engine, router=low_margin_router)
    acme = _entity(engine=database_engine)
    first = _add(
        adjudicator=adjudicator, entity=acme, statement="Acme's headcount is 500"
    )
    second = _add(
        adjudicator=adjudicator, entity=acme, statement="Acme's headcount is 600"
    )
    with database_engine.connect() as connection:
        capped = connection.execute(
            text("SELECT count(*) FROM observations WHERE valid_until IS NOT NULL")
        ).scalar_one()
        coerced = connection.execute(
            text(
                "SELECT features->>'reason' FROM observation_adjudications"
                " WHERE observation_id = :o"
            ),
            {"o": second},
        ).scalar_one()
    assert capped == 0  # no silent caps — nothing was capped at all
    assert first != second  # both rows stand (the duplicate failure mode)
    assert "below margin" in str(coerced)


def test_contradiction_eval_gate_records_and_blocks(database_engine: Engine) -> None:
    """The D43 SHIPPING criterion: contradiction P/R over the golden set,
    green with the semantic judge, failing with a judge that never flags."""
    seed_contradiction_cases(engine=database_engine, deployment_id=_DEPLOYMENT_ID)
    adjudicator, _ = _adjudicator(engine=database_engine)
    report = run_contradiction_suite(
        engine=database_engine,
        adjudicator=adjudicator,
        deployment_id=_DEPLOYMENT_ID,
        component_version=OBSERVATION_ADJUDICATOR_VERSION,
    )
    assert report["passed"], report
    assert report["precision"] == 1.0
    assert report["recall"] == 1.0

    def never_flags(prompt: str, type_name: str) -> dict[str, object]:
        return {"outcome": "new", "confidence": 0.9}

    blind, _ = _adjudicator(engine=database_engine, router=never_flags)
    regression = run_contradiction_suite(
        engine=database_engine,
        adjudicator=blind,
        deployment_id=_DEPLOYMENT_ID,
        component_version=OBSERVATION_ADJUDICATOR_VERSION,
    )
    assert not regression["passed"]
    with database_engine.connect() as connection:
        runs = connection.execute(
            text("SELECT count(*) FROM eval_runs WHERE suite = 'contradiction'")
        ).scalar_one()
    assert runs == 2


def test_s9_headcount_as_of_mid_window(database_engine: Engine) -> None:
    """S9: after the 500 -> 600 supersession, an as-of read inside O1's
    window answers 500 (the capped time-slice)."""
    from ultimate_memory.surfaces import QueryEngine

    class _NullSearch:
        def search_claims(self, **_: object) -> tuple[str, ...]:
            return ()

        def search_facts(self, **_: object) -> tuple[str, ...]:
            return ()

    adjudicator, provider = _adjudicator(engine=database_engine)
    acme = _entity(engine=database_engine)
    _add(adjudicator=adjudicator, entity=acme, statement="Acme's headcount is 500")
    _add(adjudicator=adjudicator, entity=acme, statement="Acme's headcount is 600")
    with database_engine.connect() as connection:
        cap = connection.execute(
            text("SELECT valid_until FROM observations WHERE valid_until IS NOT NULL")
        ).scalar_one()
    mid_window = cap - timedelta(microseconds=1)  # just inside O1's window

    engine = QueryEngine(
        engine=database_engine,
        search_index=_NullSearch(),
        model_provider=provider,
        embedding_model="qwen/qwen3-embedding-8b",
    )
    current = engine.lookup_observations(deployment_id=_DEPLOYMENT_ID, entity_id=acme)
    assert [fact.label for fact in current.facts] == ["Acme's headcount is 600"]
    era = engine.lookup_observations(
        deployment_id=_DEPLOYMENT_ID, entity_id=acme, valid_at=mid_window
    )
    assert "Acme's headcount is 500" in {fact.label for fact in era.facts}
