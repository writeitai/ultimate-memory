"""Evaluation package: the D22 harness and the golden suites."""

from ultimate_memory.eval.consumption import make_retrieval_evaluator
from ultimate_memory.eval.consumption import make_s58_evaluator
from ultimate_memory.eval.consumption import S58_CANARIES
from ultimate_memory.eval.consumption import seed_s58_canaries
from ultimate_memory.eval.contradiction import CONTRADICTION_PRECISION_FLOOR
from ultimate_memory.eval.contradiction import CONTRADICTION_RECALL_FLOOR
from ultimate_memory.eval.contradiction import run_contradiction_suite
from ultimate_memory.eval.contradiction import seed_contradiction_cases
from ultimate_memory.eval.harness import CaseEvaluator
from ultimate_memory.eval.harness import EvalHarness
from ultimate_memory.eval.lifecycle import flag_rate_by_extractor
from ultimate_memory.eval.lifecycle import register_lifecycle_evaluator
from ultimate_memory.eval.lifecycle import run_lifecycle_suite
from ultimate_memory.eval.resolution import PRECISION_FLOOR
from ultimate_memory.eval.resolution import RECALL_FLOOR
from ultimate_memory.eval.resolution import run_resolution_suite
from ultimate_memory.eval.resolution import seed_synthetic_golden_pairs
from ultimate_memory.eval.skeleton import make_skeleton_evaluator
from ultimate_memory.eval.skeleton import seed_skeleton_canaries
from ultimate_memory.eval.skeleton import SKELETON_CANARIES

__all__ = (
    "CONTRADICTION_PRECISION_FLOOR",
    "CONTRADICTION_RECALL_FLOOR",
    "CaseEvaluator",
    "make_retrieval_evaluator",
    "make_s58_evaluator",
    "run_contradiction_suite",
    "flag_rate_by_extractor",
    "register_lifecycle_evaluator",
    "run_lifecycle_suite",
    "seed_contradiction_cases",
    "seed_s58_canaries",
    "S58_CANARIES",
    "EvalHarness",
    "PRECISION_FLOOR",
    "RECALL_FLOOR",
    "run_resolution_suite",
    "seed_synthetic_golden_pairs",
    "SKELETON_CANARIES",
    "make_skeleton_evaluator",
    "seed_skeleton_canaries",
)
