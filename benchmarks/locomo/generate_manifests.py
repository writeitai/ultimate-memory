"""Maintenance-only exact manifest generator for the pinned LoCoMo bytes."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from benchmarks.locomo.dataset import DATASET_COMMIT
from benchmarks.locomo.dataset import item_ids_hash
from benchmarks.locomo.dataset import load_dataset
from benchmarks.locomo.model import LoCoMoQuestion
from benchmarks.locomo.model import QuestionManifest
from benchmarks.locomo.model import Tier


def generate(*, dataset_path: Path, output: Path) -> None:
    """Reproduce all three checked-in selections from the pinned dataset."""
    dataset = load_dataset(dataset_path)
    retained = {
        sample.sample_id: tuple(
            question
            for question in sample.questions
            if question.category in {1, 2, 3, 4}
        )
        for sample in dataset.samples
    }
    conv_26 = retained["conv-26"]
    smoke_ids = {
        question.item_id
        for category in range(1, 5)
        for question in tuple(item for item in conv_26 if item.category == category)[:2]
    }
    smoke = tuple(
        question.item_id for question in conv_26 if question.item_id in smoke_ids
    )
    development = tuple(
        item_id
        for sample in dataset.samples
        for item_id in _development_sample(retained[sample.sample_id])
    )
    publication = tuple(
        question.item_id
        for sample in dataset.samples
        for question in retained[sample.sample_id]
    )
    output.mkdir(parents=True, exist_ok=True)
    manifests: tuple[tuple[Tier, tuple[str, ...]], ...] = (
        ("smoke", smoke),
        ("development", development),
        ("publication", publication),
    )
    for tier, item_ids in manifests:
        manifest = QuestionManifest(
            tier=tier,
            dataset_commit=DATASET_COMMIT,
            dataset_sha256=dataset.sha256,
            item_ids=item_ids,
            item_ids_sha256=item_ids_hash(item_ids=item_ids),
        )
        (output / f"{tier}.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )


def _development_sample(questions: tuple[LoCoMoQuestion, ...]) -> tuple[str, ...]:
    """Select 20 ordered questions with deterministic category allocation."""
    counts = Counter(question.category for question in questions)
    categories = tuple(sorted(counts))
    remaining_slots = 20 - len(categories)
    total = len(questions)
    allocations: dict[int, int] = {}
    remainders: list[tuple[float, int]] = []
    for category in categories:
        raw = remaining_slots * counts[category] / total
        whole = int(raw)
        allocations[category] = 1 + whole
        remainders.append((raw - whole, category))
    unallocated = 20 - sum(allocations.values())
    for _, category in sorted(remainders, key=lambda item: (-item[0], item[1]))[
        :unallocated
    ]:
        allocations[category] += 1
    selected: set[str] = set()
    for category, allocation in allocations.items():
        selected.update(
            question.item_id
            for question in tuple(
                item for item in questions if item.category == category
            )[:allocation]
        )
    return tuple(
        question.item_id for question in questions if question.item_id in selected
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    generate(dataset_path=arguments.dataset, output=arguments.output)
