"""The ``ugm`` CLI: a dependency-light client plus an optional local review UI.

Query, ingest, connector management, and MCP all talk to the deployment HTTP
API. Only ``ugm review`` imports the server extra and connects to the spine.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
from pydantic import JsonValue

from ultimate_memory.model.adjudication import ReviewDecisionError
from ultimate_memory.model.client import ConnectorCreate
from ultimate_memory.surfaces.remote_mcp import RemoteRecipeMcpServer
from ultimate_memory.surfaces.remote_mcp import serve_mcp_stdio
from ultimate_memory.surfaces.sdk import MemoryApiError
from ultimate_memory.surfaces.sdk import MemoryClient

if TYPE_CHECKING:
    from ultimate_memory.spine.review import ReviewQueue

_MERGE_VERDICTS = ("merge", "not_merge")
_TRIAGE_VERDICTS = ("restore_support", "invalidate_fact", "uncertain")


def main(argv: list[str] | None = None) -> int:
    """The ``ugm`` entry point; returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "review":
            return _run_review(args)
        if args.command == "query":
            return _run_query(args)
        if args.command == "ingest":
            return _run_ingest(args)
        if args.command == "connectors":
            return _run_connectors(args)
        if args.command == "mcp":
            return _run_mcp()
    except MemoryApiError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    parser.print_help()
    return 2


def _run_review(args: argparse.Namespace) -> int:
    """Compose the optional local ReviewQueue over the spine."""
    try:
        from sqlalchemy import create_engine

        from ultimate_memory.spine.review import ReviewQueue
        from ultimate_memory.spine.settings import load_database_settings
    except ModuleNotFoundError:
        print(
            "error: review commands require the 'ultimate-memory[server]' extra",
            file=sys.stderr,
        )
        return 1

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
    """Run a query command through the typed remote SDK."""
    with MemoryClient.from_settings() as client:
        if args.query_command == "list":
            for descriptor in client.recipes():
                print(descriptor.model_dump_json())
            return 0
        try:
            arguments = dict(_split_arg(pair) for pair in args.arg)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        print(
            client.run_recipe(name=args.recipe, arguments=arguments).model_dump_json()
        )
        return 0


def _run_ingest(args: argparse.Namespace) -> int:
    """Push one local file to the deployment's E0 ingress."""
    try:
        with MemoryClient.from_settings() as client:
            result = client.ingest(
                args.file,
                mime=args.mime,
                title=args.title,
                source_kind=args.source_kind,
                source_ref=args.source_ref,
                source_modified_at=args.source_modified_at,
                versioning_mode=args.versioning_mode,
                source_version_ref=args.source_version_ref,
            )
    except OSError as error:
        print(f"error: could not read {args.file}: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(result.model_dump_json())
    return 0


def _run_connectors(args: argparse.Namespace) -> int:
    """Manage connector configuration on the deployment API."""
    with MemoryClient.from_settings() as client:
        if args.connector_command == "list":
            for connector in client.connectors():
                print(connector.model_dump_json())
            return 0
        if args.connector_command == "add":
            try:
                configuration: dict[str, JsonValue] = dict(
                    _split_arg(pair) for pair in args.config
                )
                connector = ConnectorCreate(
                    kind=args.kind,
                    name=args.name,
                    configuration=configuration,
                    credential_ref=args.credential_ref,
                )
            except ValueError as error:
                print(f"error: {error}", file=sys.stderr)
                return 2
            result = client.add_connector(connector=connector)
        elif args.connector_command == "pause":
            result = client.pause_connector(connector_id=args.connector_id)
        else:
            result = client.connector_status(connector_id=args.connector_id)
    print(result.model_dump_json())
    return 0


def _run_mcp() -> int:
    """Expose the remote deployment recipe registry over MCP stdio."""
    with MemoryClient.from_settings() as client:
        return serve_mcp_stdio(server=RemoteRecipeMcpServer(client=client))


def query_list(*, client: httpx.Client) -> int:
    """Print recipes from an injected client (the parity-testable CLI seam)."""
    try:
        for descriptor in MemoryClient(client=client).recipes():
            print(descriptor.model_dump_json())
    except MemoryApiError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def query_run(*, client: httpx.Client, name: str, arg_pairs: list[str]) -> int:
    """Run one recipe through an injected client and print its envelope."""
    try:
        arguments = dict(_split_arg(pair) for pair in arg_pairs)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        envelope = MemoryClient(client=client).run_recipe(
            name=name, arguments=arguments
        )
    except MemoryApiError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(envelope.model_dump_json())
    return 0


def _split_arg(pair: str) -> tuple[str, str]:
    """Split one ``key=value`` argument, or raise a clear error."""
    key, separator, value = pair.partition("=")
    if not separator or not key:
        raise ValueError(f"argument {pair!r} is not key=value")
    return key, value


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
    """Build the client-first command grammar."""
    parser = argparse.ArgumentParser(prog="ugm")
    commands = parser.add_subparsers(dest="command")

    review = commands.add_parser("review", help="the D24 local review queue")
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

    query = commands.add_parser("query", help="query deployment recipes")
    query_commands = query.add_subparsers(dest="query_command", required=True)
    query_commands.add_parser("list", help="list the remote recipe tools")
    run = query_commands.add_parser("run", help="run one recipe by name")
    run.add_argument("recipe", help="the recipe name (see `ugm query list`)")
    run.add_argument(
        "--arg", action="append", default=[], metavar="KEY=VALUE", help="repeatable"
    )

    ingest = commands.add_parser("ingest", help="push a file through E0")
    ingest.add_argument("file", type=Path)
    ingest.add_argument("--mime")
    ingest.add_argument("--title")
    ingest.add_argument("--source-kind")
    ingest.add_argument("--source-ref")
    ingest.add_argument("--source-modified-at", type=datetime.fromisoformat)
    ingest.add_argument(
        "--versioning-mode", choices=("snapshot", "living"), default="snapshot"
    )
    ingest.add_argument("--source-version-ref")

    connectors = commands.add_parser(
        "connectors", help="manage deployment-side connectors"
    )
    connector_commands = connectors.add_subparsers(
        dest="connector_command", required=True
    )
    connector_commands.add_parser("list", help="list connectors")
    add = connector_commands.add_parser("add", help="add connector configuration")
    add.add_argument("kind")
    add.add_argument("--name", required=True)
    add.add_argument("--config", action="append", default=[], metavar="KEY=VALUE")
    add.add_argument("--credential-ref")
    pause = connector_commands.add_parser("pause", help="pause a connector")
    pause.add_argument("connector_id", type=UUID)
    status = connector_commands.add_parser("status", help="show connector status")
    status.add_argument("connector_id", type=UUID)

    commands.add_parser("mcp", help="serve remote recipes over MCP stdio")
    return parser


if __name__ == "__main__":  # pragma: no cover - exercised via the entry point
    raise SystemExit(main())
