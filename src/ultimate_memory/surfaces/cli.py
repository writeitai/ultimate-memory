"""The `ugm` CLI (D24/D50, registries §8, retrieval §7): review and query.

Two surfaces over one deployment (one deployment = one trust domain, D50):

- `ugm review …` — a thin surface over the spine's ReviewQueue; every verdict
  appends the designed reversible rows. Connection comes from
  UGM_DATABASE_URL.
- `ugm query …` — mirrors the HTTP API 1:1 so an agent can shell out: it is an
  HTTP client of the running query API (UGM_API_URL), listing the recipe tool
  set and running a recipe by name. The composition (adapters) lives in the
  API process; the CLI carries no adapters, so it holds the surface boundary.

    ugm review list --deployment <uuid>
    ugm review decide <review-id> --deployment <uuid> \\
        --verdict merge|not_merge|restore_support|invalidate_fact|uncertain \\
        --reviewer <handle> [--note <text>]
    ugm query list
    ugm query run <recipe> [--arg key=value ...]
"""

import argparse
import json
import sys
from uuid import UUID

import httpx
from sqlalchemy import create_engine

from ultimate_memory.model import ReviewDecisionError
from ultimate_memory.spine.review import ReviewQueue
from ultimate_memory.spine.settings import load_api_client_settings
from ultimate_memory.spine.settings import load_database_settings

_MERGE_VERDICTS = ("merge", "not_merge")
_TRIAGE_VERDICTS = ("restore_support", "invalidate_fact", "uncertain")


def main(argv: list[str] | None = None) -> int:
    """The `ugm` entry point; returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "review":
        return _run_review(args)
    if args.command == "query":
        return _run_query(args)
    parser.print_help()
    return 2


def _run_review(args: argparse.Namespace) -> int:
    """The `ugm review …` branch: compose the ReviewQueue over the spine."""
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


def _run_query(args: argparse.Namespace) -> int:
    """The `ugm query …` branch: an HTTP client of the running query API."""
    base_url = load_api_client_settings().api_url
    with httpx.Client(base_url=base_url) as client:
        if args.query_command == "list":
            return query_list(client=client)
        return query_run(client=client, name=args.recipe, arg_pairs=args.arg)


def query_list(*, client: httpx.Client) -> int:
    """Print the recipe tool list (one JSON object per line) from `/recipes`."""
    response = client.get("/recipes")
    if response.status_code != httpx.codes.OK:
        return _report_http_error(response)
    for descriptor in response.json():
        print(json.dumps(descriptor))
    return 0


def query_run(*, client: httpx.Client, name: str, arg_pairs: list[str]) -> int:
    """Run one recipe by name over `key=value` args; print the envelope JSON."""
    try:
        arguments = dict(_split_arg(pair) for pair in arg_pairs)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    response = client.post(f"/recipe/{name}", json=arguments)
    if response.status_code != httpx.codes.OK:
        return _report_http_error(response)
    print(json.dumps(response.json()))
    return 0


def _split_arg(pair: str) -> tuple[str, str]:
    """Split one `key=value` argument, or raise a clear error."""
    key, separator, value = pair.partition("=")
    if not separator:
        raise ValueError(f"argument {pair!r} is not key=value")
    return key, value


def _report_http_error(response: httpx.Response) -> int:
    """Print a query API error to stderr and return a nonzero exit code."""
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    print(f"error: {response.status_code} {detail}", file=sys.stderr)
    return 1


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

    query = commands.add_parser("query", help="the retrieval recipes (API 1:1)")
    query_commands = query.add_subparsers(dest="query_command", required=True)
    query_commands.add_parser("list", help="the recipe tool list from /recipes")
    run = query_commands.add_parser("run", help="run one recipe by name")
    run.add_argument("recipe", help="the recipe name (see `ugm query list`)")
    run.add_argument(
        "--arg",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="a recipe argument; repeat for several",
    )
    return parser


if __name__ == "__main__":  # pragma: no cover - exercised via the entry point
    raise SystemExit(main())
