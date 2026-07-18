"""Evaluation package: the D22 harness and the golden suites."""

from ultimate_memory.eval.harness import CaseEvaluator
from ultimate_memory.eval.harness import EvalHarness
from ultimate_memory.eval.resolution import PRECISION_FLOOR
from ultimate_memory.eval.resolution import RECALL_FLOOR
from ultimate_memory.eval.resolution import run_resolution_suite
from ultimate_memory.eval.resolution import seed_synthetic_golden_pairs
from ultimate_memory.eval.skeleton import make_skeleton_evaluator
from ultimate_memory.eval.skeleton import seed_skeleton_canaries
from ultimate_memory.eval.skeleton import SKELETON_CANARIES

__all__ = (
    "CaseEvaluator",
    "EvalHarness",
    "PRECISION_FLOOR",
    "RECALL_FLOOR",
    "run_resolution_suite",
    "seed_synthetic_golden_pairs",
    "SKELETON_CANARIES",
    "make_skeleton_evaluator",
    "seed_skeleton_canaries",
)
