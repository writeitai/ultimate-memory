"""Deployment surface for rendering and publishing the D51 consumption skill."""

from pathlib import Path
from uuid import UUID
from uuid import uuid4

from ultimate_memory.core import render_consumption_skill
from ultimate_memory.model import ConsumptionRecipe
from ultimate_memory.model import ConsumptionSkillContext
from ultimate_memory.model import PublishedMounts
from ultimate_memory.model import Recipe
from ultimate_memory.model import RenderedConsumptionSkill
from ultimate_memory.spine.consumption import ConsumptionCatalog
from ultimate_memory.spine.recipes import RecipeRegistry


class ConsumptionSkillSurface:
    """Render the skill from one deployment's live registries and mounts."""

    def __init__(
        self,
        *,
        catalog: ConsumptionCatalog,
        recipes: RecipeRegistry,
        deployment_id: UUID,
    ) -> None:
        """Bind the renderer to one deployment and its two spine read models."""
        self._catalog = catalog
        self._recipes = recipes
        self._deployment_id = deployment_id

    @property
    def deployment_id(self) -> UUID:
        """The one deployment this skill surface renders."""
        return self._deployment_id

    def render(
        self, *, mounts: PublishedMounts | None = None
    ) -> RenderedConsumptionSkill:
        """Render the current deployment-specific skill without writing it."""
        if mounts is not None and mounts.deployment_id != self._deployment_id:
            raise ValueError(
                "the mount set and consumption skill serve different deployments"
            )
        recipes = tuple(
            ConsumptionRecipe(
                name=recipe.name,
                description=recipe.description,
                output_grain=recipe.output_grain,
                answer_intent=recipe.answer_intent,
            )
            for recipe in _latest_recipes(
                recipes=self._recipes.active(deployment_id=self._deployment_id)
            )
        )
        return render_consumption_skill(
            context=ConsumptionSkillContext(
                deployment=self._catalog.deployment(deployment_id=self._deployment_id),
                recipes=recipes,
                mounts=mounts,
            )
        )

    def publish(self, *, directory: Path, rendered: RenderedConsumptionSkill) -> Path:
        """Atomically publish one already-rendered ``SKILL.md`` artifact."""
        if rendered.deployment_id != self._deployment_id:
            raise ValueError(
                "the rendered skill and publisher serve different deployments"
            )
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / rendered.filename
        staging = directory / f".{rendered.filename}.{uuid4().hex}.tmp"
        staging.write_text(data=rendered.content, encoding="utf-8")
        staging.replace(target=destination)
        return destination


def _latest_recipes(*, recipes: tuple[Recipe, ...]) -> tuple[Recipe, ...]:
    """Keep one latest active recipe per name from registry-ordered rows."""
    seen: set[str] = set()
    latest: list[Recipe] = []
    for recipe in recipes:
        if recipe.name in seen:
            continue
        seen.add(recipe.name)
        latest.append(recipe)
    return tuple(latest)
