"""The review CLI (D24, registries §8): list and decide queue items.

A thin surface over the spine's ReviewQueue — every verdict appends the
designed reversible rows. Connection comes from UGM_DATABASE_URL; the
deployment is an explicit argument (one deployment = one trust domain, D50).

    ugm review list --deployment <uuid>
    ugm review decide <review-id> --deployment <uuid> \\
        --verdict merge|not_merge|restore_support|invalidate_fact|uncertain \\
        --reviewer <handle> [--note <text>]
"""

import argparse
import json
import sys
from uuid import UUID

from sqlalchemy import create_engine

from ultimate_memory.model import ReviewDecisionError
from ultimate_memory.spine.review import ReviewQueue
from ultimate_memory.spine.settings import load_database_settings

_MERGE_VERDICTS = ("merge", "not_merge")
_TRIAGE_VERDICTS = ("restore_support", "invalidate_fact", "uncertain")


def main(argv: list[str] | None = None) -> int:
    """The `ugm` entry point; returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command != "review":
        parser.print_help()
        return 2
    engine = create_engine(load_database_settings().sqlalchemy_url())
    try:
        queue = ReviewQueue(engine=engine)
        if args.review_command == "list":
            return _list(queue=queue, deployment_id=args.deployment)
        return _decide(
            queue=queue,
            deployment_id=args.deployment,
            review_id=args.review_id,
            verdict=args.verdict,
            reviewer=args.reviewer,
            note=args.note,
        )
    finally:
        engine.dispose()


def _list(*, queue: ReviewQueue, deployment_id: UUID) -> int:
    """Print open items ranked by expected impact, one JSON line each."""
    for item in queue.pending(deployment_id=deployment_id):
        print(
            json.dumps(
                {
                    "review_id": str(item.review_id),
                    "kind": item.item_kind,
                    "expected_impact": item.expected_impact,
                    "blast_radius": item.blast_radius,
                    "status": item.status,
                    "candidate": item.candidate,
                },
                default=str,
            )
        )
    return 0


def _decide(
    *,
    queue: ReviewQueue,
    deployment_id: UUID,
    review_id: UUID,
    verdict: str,
    reviewer: str,
    note: str | None,
) -> int:
    """Apply one verdict; the verdict picks the decision path by its name."""
    try:
        if verdict in _MERGE_VERDICTS:
            events = queue.decide_merge(
                deployment_id=deployment_id,
                review_id=review_id,
                verdict=verdict,
                reviewer=reviewer,
                note=note,
            )
            print(
                json.dumps(
                    {"verdict": verdict, "merge_events": [str(e) for e in events]}
                )
            )
        else:
            queue.decide_support_withdrawn(
                deployment_id=deployment_id,
                review_id=review_id,
                verdict=verdict,
                reviewer=reviewer,
                note=note,
            )
            print(json.dumps({"verdict": verdict}))
    except ReviewDecisionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """The `ugm review ...` argument grammar."""
    parser = argparse.ArgumentParser(prog="ugm")
    commands = parser.add_subparsers(dest="command")
    review = commands.add_parser("review", help="the D24 review queue")
    review_commands = review.add_subparsers(dest="review_command", required=True)

    listing = review_commands.add_parser("list", help="open items, impact-ranked")
    listing.add_argument("--deployment", type=UUID, required=True)

    decide = review_commands.add_parser("decide", help="apply one verdict")
    decide.add_argument("review_id", type=UUID)
    decide.add_argument("--deployment", type=UUID, required=True)
    decide.add_argument(
        "--verdict", required=True, choices=(*_MERGE_VERDICTS, *_TRIAGE_VERDICTS)
    )
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--note", default=None)
    return parser


if __name__ == "__main__":  # pragma: no cover - exercised via the entry point
    raise SystemExit(main())
