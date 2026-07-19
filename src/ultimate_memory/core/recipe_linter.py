"""The recipe registration linter (D50/D41): grain semantics, mechanically.

A recipe declares two enums — `output_grain` and `answer_intent` — and a
`chain` of primitive ops. The database CHECK enforces the headline bar
(`current_facts` ⇒ `fact` grain); this linter enforces the *chain-level*
rules the DB cannot see, so a registration that would let a recipe lie about
what it returns is rejected before it ever reaches a surface:

- **`current_facts` may ride only validity-filtered fact primitives.** This
  is the D41 bar in full: a recipe that answers "what holds now" must compose
  lookups/aggregates that filter both temporal clocks — never a claims search,
  which is evidence ("what a source *asserted*"), not fact.
- **The chain's terminal grain must match `output_grain`.** A recipe that
  ends on a claims search cannot advertise `fact`; one that ends on a K-page
  read cannot advertise `evidence`. The grain a caller reads is the grain the
  last step actually produces.
- **Each intent implies a shape.** `assertion_history` is evidence-grain,
  `change_feed` ends on the delta, `audit` ends on a decision trail. These
  keep the MCP tool a caller sees honest about what it will get back.

`fuse` and `rerank` are **grain-transparent**: they reorder, so their grain
is whatever their inputs carry. A fact neighborhood reranked by graph distance
is still fact; the linter resolves a transparent op's grain from the steps it
consumes rather than pinning one.
"""

from dataclasses import dataclass

from ultimate_memory.model import Grain
from ultimate_memory.model import Recipe
from ultimate_memory.model import RecipeAnswerIntent


class RecipeLintError(Exception):
    """A recipe registration the linter rejected, with the reason stated."""


@dataclass(frozen=True)
class _OpSpec:
    """What a chain op produces, for the mechanical grain checks."""

    grain: Grain | None  # None means grain-transparent (inherits from inputs)
    validity_filtered: bool  # a live-fact primitive (the current_facts bar)
    min_inputs: int = 0  # prior steps this op must consume


# The op vocabulary a recipe chain may compose (retrieval §3). Grain-transparent
# operators carry `grain=None` and inherit from the steps they fuse/rerank.
_OPS: dict[str, _OpSpec] = {
    "lookup_relations": _OpSpec(Grain.FACT, validity_filtered=True),
    "lookup_observations": _OpSpec(Grain.FACT, validity_filtered=True),
    "aggregate": _OpSpec(Grain.FACT, validity_filtered=True),
    "search_claims": _OpSpec(Grain.EVIDENCE, validity_filtered=False),
    "hydrate_relation": _OpSpec(Grain.COMPOSITE, validity_filtered=False),
    "transcript": _OpSpec(Grain.COMPOSITE, validity_filtered=False),
    "delta": _OpSpec(Grain.COMPOSITE, validity_filtered=False),
    "pages_about": _OpSpec(Grain.COMPILED, validity_filtered=False),
    "fuse": _OpSpec(None, validity_filtered=False, min_inputs=1),
    "rerank": _OpSpec(None, validity_filtered=False, min_inputs=1),
}

KNOWN_OPS = frozenset(_OPS)
"""The primitive ops a recipe chain may name (the executor implements each)."""


def lint_recipe(recipe: Recipe) -> None:
    """Validate a recipe against the D50/D41 grain rules, or raise.

    Runs before every registration: a chain that would let a recipe
    misreport its grain, or a `current_facts` recipe that reaches for
    evidence, never becomes a row. Raises `RecipeLintError` naming the first
    violation; returns None when the recipe is well-formed.
    """
    _check_ops_and_inputs(recipe)
    terminal_grain = _resolve_grain(recipe, len(recipe.chain) - 1)
    if terminal_grain != recipe.output_grain:
        raise RecipeLintError(
            f"recipe {recipe.name!r} declares output_grain"
            f" {recipe.output_grain.value!r} but its chain ends on a"
            f" {terminal_grain.value!r}-grain op"
        )
    _check_intent(recipe)


def _check_ops_and_inputs(recipe: Recipe) -> None:
    """Every op is known, and every input references an earlier step."""
    for index, step in enumerate(recipe.chain):
        spec = _OPS.get(step.op)
        if spec is None:
            raise RecipeLintError(
                f"recipe {recipe.name!r} step {index} names unknown op"
                f" {step.op!r}; known ops: {', '.join(sorted(KNOWN_OPS))}"
            )
        if len(step.inputs) < spec.min_inputs:
            raise RecipeLintError(
                f"recipe {recipe.name!r} step {index} ({step.op}) needs at"
                f" least {spec.min_inputs} input(s)"
            )
        for referenced in step.inputs:
            if not 0 <= referenced < index:
                raise RecipeLintError(
                    f"recipe {recipe.name!r} step {index} references step"
                    f" {referenced}, which is not an earlier step"
                )


def _resolve_grain(recipe: Recipe, index: int) -> Grain:
    """The grain a step produces — inherited through transparent operators."""
    spec = _OPS[recipe.chain[index].op]
    if spec.grain is not None:
        return spec.grain
    grains = {_resolve_grain(recipe, i) for i in recipe.chain[index].inputs}
    if len(grains) != 1:
        raise RecipeLintError(
            f"recipe {recipe.name!r} step {index} ({recipe.chain[index].op})"
            f" fuses inputs of differing grains {sorted(g.value for g in grains)}"
        )
    return next(iter(grains))


def _check_intent(recipe: Recipe) -> None:
    """The answer_intent → chain-shape rules (the mechanical grain bar)."""
    intent = recipe.answer_intent
    if intent is RecipeAnswerIntent.CURRENT_FACTS:
        if recipe.output_grain is not Grain.FACT:
            raise RecipeLintError(
                f"recipe {recipe.name!r} answers current_facts but is not"
                " fact-grain (the D41 bar)"
            )
        for index, step in enumerate(recipe.chain):
            spec = _OPS[step.op]
            if spec.grain is None:
                continue  # a transparent op inherits its inputs' fact grain
            if not (spec.validity_filtered and spec.grain is Grain.FACT):
                raise RecipeLintError(
                    f"recipe {recipe.name!r} answers current_facts but step"
                    f" {index} ({step.op}) is not a validity-filtered fact"
                    " primitive — 'what holds now' never rides evidence (D41)"
                )
    elif intent is RecipeAnswerIntent.ASSERTION_HISTORY:
        if recipe.output_grain is not Grain.EVIDENCE:
            raise RecipeLintError(
                f"recipe {recipe.name!r} answers assertion_history but is not"
                " evidence-grain — 'what sources asserted' is evidence (D41)"
            )
    elif intent is RecipeAnswerIntent.CHANGE_FEED:
        if recipe.chain[-1].op != "delta":
            raise RecipeLintError(
                f"recipe {recipe.name!r} answers change_feed but does not end"
                " on the delta primitive"
            )
    elif intent is RecipeAnswerIntent.AUDIT:
        if recipe.chain[-1].op not in {"transcript", "hydrate_relation"}:
            raise RecipeLintError(
                f"recipe {recipe.name!r} answers audit but does not end on a"
                " decision trail (transcript or hydrate_relation)"
            )
    # ORIENTATION is deliberately shape-permissive: a shaped overview may be a
    # fact aggregate, a K page, or a bundle — its honesty is the grain match
    # already checked, not a fixed op.
