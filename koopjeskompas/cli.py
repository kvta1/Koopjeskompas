"""Command-line entry point. Wires the pieces together; holds no logic of its own."""

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import boto3
import uvicorn
from botocore.exceptions import BotoCoreError, ClientError

from koopjeskompas.api.app import create_app, get_today, openapi_json
from koopjeskompas.domain.models import Coordinates, Cuisine, Diet, Preferences
from koopjeskompas.domain.scoring import ScoringWeights, rank_stores
from koopjeskompas.ingestion.ah.client import AhApiError, AhClient, load_raw_week
from koopjeskompas.ingestion.ah.parser import parse_bonus_week
from koopjeskompas.ingestion.cache import deals_path, load_deals, save_deals
from koopjeskompas.publish import (
    REGION,
    STACK_NAME,
    PublishError,
    find_data_bucket,
    publish_deals,
    snapshots,
)
from koopjeskompas.report import format_ranking
from koopjeskompas.stores import load_stores

DEFAULT_DATA_DIR = Path("data")
DEFAULT_OPENAPI_PATH = Path("frontend/openapi.json")
LEIDEN_CENTRAAL = Coordinates(latitude=52.1664, longitude=4.4817)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
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
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="the date to fetch, rank or serve for, as YYYY-MM-DD (default: today)",
    )
    subcommands = parser.add_subparsers(required=True, metavar="COMMAND")

    fetch = subcommands.add_parser("fetch-deals", help="fetch and cache AH bonus deals")
    fetch.add_argument(
        "--from-raw",
        action="store_true",
        help="re-parse the responses saved by an earlier fetch instead of asking AH",
    )
    fetch.set_defaults(handler=_fetch_deals)

    rank = subcommands.add_parser("rank", help="rank stores using the cached deals")
    rank.add_argument("--lat", type=float, default=LEIDEN_CENTRAAL.latitude)
    rank.add_argument("--lon", type=float, default=LEIDEN_CENTRAAL.longitude)
    rank.add_argument("--diet", type=Diet, choices=list(Diet), default=Diet.NONE)
    rank.add_argument(
        "--cuisine",
        type=Cuisine,
        choices=list(Cuisine),
        action="append",
        default=[],
        help="preferred cuisine; repeat for several",
    )
    rank.add_argument("--lactose-free", action="store_true")
    rank.add_argument("--gluten-free", action="store_true")
    rank.add_argument(
        "--radius-km", type=float, default=ScoringWeights().max_distance_km
    )
    rank.add_argument("--top-k", type=int, default=ScoringWeights().top_k)
    rank.set_defaults(handler=_rank)

    serve = subcommands.add_parser(
        "serve", help="run the web API (interactive docs at /docs)"
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(handler=_serve)

    openapi = subcommands.add_parser(
        "openapi", help="write the API's OpenAPI schema, for the web page's types"
    )
    openapi.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OPENAPI_PATH,
        help="where to write it (default: %(default)s)",
    )
    openapi.set_defaults(handler=_openapi)

    publish = subcommands.add_parser(
        "publish-deals",
        help="upload the cached deals to the AWS demo (needs `aws login`)",
    )
    publish.add_argument(
        "--bucket",
        help="the data bucket (default: read from the deployed stack's outputs)",
    )
    publish.add_argument(
        "--stack",
        default=STACK_NAME,
        help="the CDK stack to read it from (default: %(default)s)",
    )
    publish.set_defaults(handler=_publish_deals)

    return parser


def _today(args: argparse.Namespace) -> date:
    today: date = args.today or date.today()
    return today


def _fetch_deals(args: argparse.Namespace) -> int:
    today = _today(args)
    raw_dir = args.data_dir / "raw" / "ah" / today.isoformat()
    try:
        if args.from_raw:
            week = load_raw_week(raw_dir, today)
        else:
            week = AhClient(raw_dir=raw_dir).fetch_bonus_week(today)
    except AhApiError as error:
        print(f"Fetching AH deals failed: {error}", file=sys.stderr)
        return 1

    result = parse_bonus_week(week)
    path = deals_path(args.data_dir, "AH")
    save_deals(path, result.deals)

    period = week.period
    print(
        f"AH bonus {period.bonus_start_date} to {period.bonus_end_date}: "
        f"{len(result.deals)} deals saved to {path}"
    )
    if result.ranges_priced:
        print(
            f"Range deals priced per product: {result.ranges_priced} "
            f"({result.range_products} products)"
        )
    if week.failed_sections:
        print(f"Sections that failed: {', '.join(week.failed_sections)}")
    if week.failed_ranges:
        print(
            f"Range lookups that failed or are missing: {len(week.failed_ranges)}; "
            "those ranges stay unscored"
        )
    if result.skipped:
        print(f"Skipped {len(result.skipped)} malformed items (see warnings above)")
    if result.no_discount:
        print(
            "Deals without a determinable discount (unrecognised mechanic, or no "
            "normal price to compare with); kept, but they score zero:"
        )
        for mechanic, count in result.no_discount.most_common():
            print(f"  {count:3d}x {mechanic}")
    return 0


def _rank(args: argparse.Namespace) -> int:
    path = deals_path(args.data_dir, "AH")
    if not path.exists():
        print(f"No cached deals at {path}; run 'koopjeskompas fetch-deals' first.")
        return 1

    preferences = Preferences(
        diet=args.diet,
        cuisines=frozenset(args.cuisine),
        lactose_free=args.lactose_free,
        gluten_free=args.gluten_free,
    )
    rankings = rank_stores(
        stores=load_stores(),
        deals=load_deals(path),
        preferences=preferences,
        location=Coordinates(latitude=args.lat, longitude=args.lon),
        today=_today(args),
        weights=ScoringWeights(max_distance_km=args.radius_km, top_k=args.top_k),
    )
    print(format_ranking(rankings))
    return 0


def _serve(args: argparse.Namespace) -> int:
    app = create_app(data_dir=args.data_dir)
    if args.today is not None:
        # Rank as if it were that day, e.g. to demo with an older deal cache. Without
        # --today the server asks for the real date on every request.
        fixed_day: date = args.today
        app.dependency_overrides[get_today] = lambda: fixed_day
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _publish_deals(args: argparse.Namespace) -> int:
    try:
        files = snapshots(args.data_dir / "deals")
        bucket = args.bucket or find_data_bucket(
            boto3.client("cloudformation", region_name=REGION), args.stack
        )
        keys = publish_deals(boto3.client("s3", region_name=REGION), bucket, files)
    except PublishError as error:
        print(error, file=sys.stderr)
        return 1
    except (BotoCoreError, ClientError) as error:
        # Expired credentials and a stack that doesn't exist both end up here.
        print(f"AWS refused: {error}. Signed in? Try 'aws login'.", file=sys.stderr)
        return 1
    for key in keys:
        print(f"Uploaded s3://{bucket}/{key}")
    print(
        "New Lambda environments use it at once; warm ones keep the previous snapshot "
        "until AWS recycles them, within hours."
    )
    return 0


def _openapi(args: argparse.Namespace) -> int:
    path: Path = args.output
    path.write_text(openapi_json(create_app(data_dir=args.data_dir)), encoding="utf-8")
    print(f"OpenAPI schema written to {path}")
    return 0
