"""Pure renderer for the versioned D51 agent-consumption skill."""

import json
from typing import Final

from rememberstack.model import ConsumptionRecipe
from rememberstack.model import ConsumptionScope
from rememberstack.model import ConsumptionSkillContext
from rememberstack.model import PublishedMounts
from rememberstack.model import RenderedConsumptionSkill

CONSUMPTION_SKILL_VERSION: Final = "1.0.0"


def render_consumption_skill(
    *, context: ConsumptionSkillContext
) -> RenderedConsumptionSkill:
    """Render one complete ``SKILL.md`` from typed deployment state."""
    deployment = context.deployment
    sections = (
        _header(),
        _deployment(context=context),
        _default_motion(
            knowledge_page_count=deployment.knowledge_page_count,
            recipes=context.recipes,
        ),
        _grains(),
        _testimony(recipes=context.recipes),
        _time_and_media(),
        _envelope(),
        _mounts(mounts=context.mounts),
        _recipes(recipes=context.recipes),
        _working_rules(),
    )
    return RenderedConsumptionSkill(
        deployment_id=deployment.deployment_id,
        version=CONSUMPTION_SKILL_VERSION,
        content="\n\n".join(sections).rstrip() + "\n",
    )


def _header() -> str:
    """The stable skill identity and revision."""
    return (
        "---\n"
        "name: rememberstack\n"
        "description: Use one configured RememberStack deployment without "
        "mixing facts, testimony, and compiled knowledge.\n"
        "---\n\n"
        "# Use RememberStack\n\n"
        f"Skill revision: `{CONSUMPTION_SKILL_VERSION}`. Follow these instructions "
        "when a task depends on the configured memory."
    )


def _deployment(*, context: ConsumptionSkillContext) -> str:
    """Render deployment identity, language, scopes, and current K state."""
    deployment = context.deployment
    description = (
        f"\n- Purpose: {_literal(value=deployment.description)}"
        if deployment.description
        else ""
    )
    scopes = _scope_lines(scopes=deployment.scopes)
    knowledge_state = (
        "known empty: no K pages are registered"
        if deployment.knowledge_page_count == 0
        else f"{deployment.knowledge_page_count} K page(s) are registered"
    )
    return (
        "## This deployment\n\n"
        f"- Name: {_literal(value=deployment.name)}\n"
        f"- Slug: `{deployment.slug}`\n"
        f"- Deployment id: `{deployment.deployment_id}`\n"
        f"- Default language: `{deployment.default_language}`"
        f"{description}\n"
        f"- Plane K state: {knowledge_state}.\n"
        f"- Special-purpose scopes:\n{scopes}"
    )


def _default_motion(
    *, knowledge_page_count: int, recipes: tuple[ConsumptionRecipe, ...]
) -> str:
    """Teach the one progressive-disclosure motion and honest empty-K fallback."""
    orientation_route = (
        "Read the knowledge checkout or use the active `pages_about` orientation "
        "recipe."
        if any(recipe.name == "pages_about" for recipe in recipes)
        else "Read the knowledge checkout, or use an orientation-intent recipe if "
        "one is enabled."
    )
    empty_instruction = (
        "This deployment currently has no K pages. The orientation attempt is still "
        "correct, but an empty/`known_empty` result means: fall back to the P3 corpus "
        "tree when mounted, or to search when unmounted. Never invent the missing "
        "summary."
        if knowledge_page_count == 0
        else "If K returns `known_empty`, fall back to P3 or search; never turn an "
        "empty orientation layer into an invented summary."
    )
    return (
        "## Default motion: orient, verify, audit\n\n"
        f"1. **Orient on plane K.** {orientation_route} K is cheap, pre-paid "
        "synthesis, not live-confirmed truth.\n"
        "2. **Verify on the spine.** For anything load-bearing, query the fact layer "
        "(relations or observations). A fact lookup re-checks live PostgreSQL state.\n"
        "3. **Audit on evidence.** When the stakes or ambiguity demand it, hydrate "
        "the fact to claims, source spans, documents, and finally the original.\n\n"
        f"{empty_instruction}"
    )


def _grains() -> str:
    """Teach the claim-to-fact-to-compiled terminology ladder."""
    return (
        "## Keep the grains separate\n\n"
        "- A **claim** is immutable testimony: what one source asserted. It is "
        "evidence grain and may be stale, superseded, or contradicted.\n"
        "- A **relation** links two entities; an **observation** records a value or "
        "statement about one entity. Together they are the **fact layer**: the "
        "system's adjudicated, validity-filtered holdings. Questions of the form "
        '"is this true now?" go here by default.\n'
        "- A **compiled K page** is pre-paid synthesis. It is compiled grain and "
        "must be read with its compile time, stale flag, and open-flag count.\n"
        "- A **core belief** is a stricter configured K tier, not a new source of "
        "truth.\n\n"
        "Never blend evidence and facts into one unlabeled answer. If a task asks "
        "both what someone said and what the system believes, return separate "
        "evidence-grain and fact-grain parts."
    )


def _testimony(*, recipes: tuple[ConsumptionRecipe, ...]) -> str:
    """Teach current testimony, historical opt-in, and withdrawn support."""
    recipe_names = {recipe.name for recipe in recipes}
    history_surface = (
        "This deployment enables `claims_as_of`; use it only for assertion "
        "history, never for current truth."
        if "claims_as_of" in recipe_names
        else "This deployment does not enable a `claims_as_of` recipe. Its current "
        "query surfaces do not expose superseded testimony, so do not attempt an "
        "undeclared history option."
    )
    return (
        "## Testimony currency and shaky support\n\n"
        "Claim search defaults to **current testimony**. Claims left behind by a "
        "living document's newer version or by a newer extraction generation are "
        "history, not current search results. `claims_as_of` means **what sources "
        "asserted as of a past system time**; it never means what is true now. "
        f"{history_surface}\n\n"
        "A fact with `support: withdrawn` has lost all current-testimony support "
        "because a toolchain re-read did not re-derive it. It still stands while "
        "review is open, but it is shaky: report the caveat, inspect its transcript "
        "and evidence, and do not make it load-bearing without verification."
    )


def _time_and_media() -> str:
    """Keep the three media/time coordinates and derivation labels distinct."""
    return (
        "## Time and media\n\n"
        'Do not collapse these into "the timestamp":\n\n'
        "- a source locator such as `start_ms` says **where in a file** evidence "
        "occurs;\n"
        "- `valid_from` / `valid_until` say **when a fact held in the world**;\n"
        "- `ingested_at` / `believed_at` say **when the system knew it**.\n\n"
        "For media-derived evidence, read `evidence_mode`: `source_expression` is "
        "rendered speech/text, `model_observation` is what a model reports seeing, "
        "and `model_interpretation` is the model's interpretation. When tone or a "
        "visual detail matters, follow the source locator to the raw interval or "
        "region. The transcript is a map, not the territory."
    )


def _envelope() -> str:
    """Teach response honesty fields and the distinct negative reactions."""
    return (
        "## Read the whole response envelope\n\n"
        "Check `grain`, applied `valid_at`/`believed_at`, identity regime, per-store "
        "freshness, truncation/continuation, and `dropped_by_hydration`. A result "
        "inside a live contradiction group must include or point to its co-members; "
        "report the competing sides instead of silently picking one.\n\n"
        "Negative results require different moves:\n\n"
        "- `unknown_entity`: widen resolution or search;\n"
        "- `known_empty`: the entity exists but no matching result is known within "
        "the stated freshness;\n"
        "- `boundary`: re-plan using the named workaround.\n\n"
        "Hard-forgotten material is intentionally indistinguishable from content "
        "that never existed."
    )


def _mounts(*, mounts: PublishedMounts | None) -> str:
    """Render exact mount paths or the unmounted parity rule."""
    if mounts is None:
        availability = (
            "No mounts are available in this harness. Use API, CLI, or MCP for "
            "orientation, readable artifacts, and query operations."
        )
    else:
        availability = (
            "The four read-only mounts are available:\n\n"
            f"- P3 corpus tree: `{mounts.p3}`\n"
            f"- E0 artifacts: `{mounts.artifacts}`\n"
            f"- raw originals (off the navigation path; audited): `{mounts.raw}`\n"
            f"- plane K checkout: `{mounts.knowledge}`"
        )
    return (
        "## Filesystem first\n\n"
        f"{availability}\n\n"
        "When mounts exist, prefer them for navigation, reading, and grep. Reserve "
        "API/CLI/MCP for operations with no filesystem equivalent: semantic search, "
        "graph traversal, temporal as-of queries, hydration, transcripts, and "
        "deltas. Start in P3 or K, not raw. Follow an explicit raw pointer only "
        "when the original is needed, and use the deployment's audited raw-access "
        "mechanism."
    )


def _recipes(*, recipes: tuple[ConsumptionRecipe, ...]) -> str:
    """Render only this deployment's latest active recipe versions."""
    if not recipes:
        rows = "No recipes are enabled. Use the primitive API directly."
    else:
        rows = "\n".join(
            f"- `{recipe.name}` — `{recipe.output_grain}` / "
            f"`{recipe.answer_intent}`: {_one_line(value=recipe.description)}"
            for recipe in recipes
        )
    return (
        "## Enabled recipes and surfaces\n\n"
        f"{rows}\n\n"
        "Discover the current set with `remember query list`, `GET /recipes`, or MCP "
        "tool listing. Run one with `remember query run <name> --arg key=value`, "
        "`POST /recipe/<name>`, or the same-named MCP tool. Recipe grain and intent "
        "are part of the contract; a recipe adds no capability beyond its primitive "
        "chain."
    )


def _working_rules() -> str:
    """End with a compact operational checklist for the consuming agent."""
    return (
        "## Before acting on a memory answer\n\n"
        "1. Did I use facts, not claims, for a current-truth question?\n"
        "2. Did I keep fact, evidence, and compiled grains labeled separately?\n"
        "3. Did I inspect freshness, truncation, contradictions, and withdrawn "
        "support?\n"
        "4. Did I verify load-bearing K statements on the spine?\n"
        "5. Did I hydrate to evidence or raw source when the stakes required it?"
    )


def _scope_lines(*, scopes: tuple[ConsumptionScope, ...]) -> str:
    """Render special-purpose scope rows without inventing a default K page."""
    if not scopes:
        return "  - none registered"
    return "\n".join(
        f"  - `{scope.slug}` ({_one_line(value=scope.name)})"
        + (f" at `{scope.git_path}`" if scope.git_path else "")
        + (f": {_one_line(value=scope.description)}" if scope.description else "")
        for scope in scopes
    )


def _literal(*, value: str) -> str:
    """Render deployment-controlled prose as one explicit JSON string literal."""
    literal = json.dumps(value, ensure_ascii=False).replace("`", "'")
    return f"`{literal}`"


def _one_line(*, value: str) -> str:
    """Collapse deployment-controlled display text to one Markdown-safe line."""
    return " ".join(value.split()).replace("`", "'")
