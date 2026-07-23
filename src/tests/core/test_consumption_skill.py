"""Pure contract tests for the D51 deployment-rendered consumption skill."""

from uuid import UUID

from rememberstack.core import CONSUMPTION_SKILL_VERSION
from rememberstack.core import render_consumption_skill
from rememberstack.model import ConsumptionDeployment
from rememberstack.model import ConsumptionRecipe
from rememberstack.model import ConsumptionScope
from rememberstack.model import ConsumptionSkillContext
from rememberstack.model import Grain
from rememberstack.model import PublishedMounts
from rememberstack.model import RecipeAnswerIntent

_DEPLOYMENT_ID = UUID("55000000-0000-0000-0000-000000000001")


def _context(
    *, mounted: bool, knowledge_page_count: int, recipes: bool = True
) -> ConsumptionSkillContext:
    """Build one small deployment context for renderer proofs."""
    mounts = (
        PublishedMounts(
            deployment_id=_DEPLOYMENT_ID,
            p3="/memory/corpus",
            artifacts="/memory/artifacts",
            raw="/memory/raw",
            knowledge="/memory/knowledge",
            read_only=True,
        )
        if mounted
        else None
    )
    return ConsumptionSkillContext(
        deployment=ConsumptionDeployment(
            deployment_id=_DEPLOYMENT_ID,
            slug="acme-memory",
            name="Acme migration",
            description="Evidence for the migration programme",
            default_language="en",
            scopes=(
                ConsumptionScope(
                    slug="target-state",
                    name="Target state",
                    git_path="scopes/target-state",
                ),
            ),
            knowledge_page_count=knowledge_page_count,
        ),
        recipes=(
            (
                ConsumptionRecipe(
                    name="relation_current",
                    description="Current relations for one subject.",
                    output_grain=Grain.FACT,
                    answer_intent=RecipeAnswerIntent.CURRENT_FACTS,
                ),
                ConsumptionRecipe(
                    name="pages_about",
                    description="Compiled pages about an entity.",
                    output_grain=Grain.COMPILED,
                    answer_intent=RecipeAnswerIntent.ORIENTATION,
                ),
            )
            if recipes
            else ()
        ),
        mounts=mounts,
    )


def test_rendered_skill_teaches_the_complete_s58_motion() -> None:
    """The fixed curriculum covers every load-bearing S58 decision."""
    skill = render_consumption_skill(
        context=_context(mounted=True, knowledge_page_count=2)
    )

    assert skill.version == CONSUMPTION_SKILL_VERSION
    assert skill.filename == "SKILL.md"
    assert "orient, verify, audit" in skill.content
    assert 'Questions of the form "is this true now?" go here' in skill.content
    assert "`claims_as_of` means **what sources asserted" in skill.content
    assert "`support: withdrawn`" in skill.content
    assert "report the competing sides" in skill.content
    assert "prefer them for navigation, reading, and grep" in skill.content
    assert "hydrate the fact to claims" in skill.content
    assert "/memory/corpus" in skill.content
    assert "`target-state`" in skill.content
    assert "`relation_current` — `fact` / `current_facts`" in skill.content


def test_empty_k_and_unmounted_surfaces_degrade_honestly() -> None:
    """No K pages or mounts produces explicit fallbacks, never fake availability."""
    skill = render_consumption_skill(
        context=_context(mounted=False, knowledge_page_count=0)
    )

    assert "known empty: no K pages are registered" in skill.content
    assert "fall back to the P3 corpus tree when mounted, or to search" in skill.content
    assert "No mounts are available in this harness" in skill.content
    assert "/memory/corpus" not in skill.content


def test_only_enabled_recipes_are_advertised() -> None:
    """Unavailable recipes and parameters are never presented as callable."""
    skill = render_consumption_skill(
        context=_context(mounted=False, knowledge_page_count=0, recipes=False)
    )

    assert "`pages_about`" not in skill.content
    assert "No recipes are enabled" in skill.content
    assert "This deployment does not enable a `claims_as_of` recipe" in skill.content
    assert "include_superseded_testimony" not in skill.content


def test_claims_as_of_is_described_as_callable_only_when_enabled() -> None:
    """An active history recipe gets exact, grain-safe callable guidance."""
    context = _context(mounted=False, knowledge_page_count=0, recipes=False)
    context = context.model_copy(
        update={
            "recipes": (
                ConsumptionRecipe(
                    name="claims_as_of",
                    description="Historical source assertions.",
                    output_grain=Grain.EVIDENCE,
                    answer_intent=RecipeAnswerIntent.ASSERTION_HISTORY,
                ),
            )
        }
    )

    skill = render_consumption_skill(context=context)

    assert "This deployment enables `claims_as_of`" in skill.content
    assert "use it only for assertion history" in skill.content
