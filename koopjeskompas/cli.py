"""Command-line entry point. Wires the pieces together; holds no logic of its own."""

import argparse
from collections.abc import Sequence
from pathlib import Path

DEFAULT_DATA_DIR = Path("data")


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result: int = args.handler(args)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="koopjeskompas",
        description="Rank nearby supermarkets by how good their deals are for you.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="where raw responses and parsed deals are cached (default: %(default)s)",
    )
    subcommands = parser.add_subparsers(required=True, metavar="COMMAND")

    fetch = subcommands.add_parser("fetch-deals", help="fetch and cache AH bonus deals")
    fetch.set_defaults(handler=_fetch_deals)

    rank = subcommands.add_parser("rank", help="rank stores using the cached deals")
    rank.set_defaults(handler=_rank)

    return parser


def _fetch_deals(args: argparse.Namespace) -> int:
    raise NotImplementedError


def _rank(args: argparse.Namespace) -> int:
    raise NotImplementedError
