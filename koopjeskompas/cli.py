"""Command-line entry point. Wires the pieces together; holds no logic of its own."""

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

import boto3
import uvicorn
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    CredentialRetrievalError,
    NoCredentialsError,
)

from koopjeskompas.api.app import create_app, get_today, openapi_json
from koopjeskompas.cloud.aws.s3 import open_s3_snapshots
from koopjeskompas.domain.models import Coordinates, Cuisine, Diet, Preferences
from koopjeskompas.domain.scoring import (
    ScoringWeights,
    chain_ranking_days,
    rank_stores,
)
from koopjeskompas.ingestion.ah.source import AhSource
from koopjeskompas.ingestion.jumbo.source import JumboSource
from koopjeskompas.ingestion.lidl.source import LidlSource
from koopjeskompas.ingestion.cache import deals_path, load_snapshots, save_deals
from koopjeskompas.ingestion.source import DealSource, SourceError, SourceResult
from koopjeskompas.publish import (
    REGION,
    STACK_NAME,
    PublishError,
    find_data_bucket,
    publish_deals,
    snapshots,
)
from koopjeskompas.report import format_ranking
from koopjeskompas.stores import load_stores, save_stores
from koopjeskompas.stores.osm import (
    DEFAULT_SERVER,
    OverpassError,
    fetch_overpass,
    overpass_query,
    stores_from_overpass,
)

DEFAULT_DATA_DIR = Path("data")
# One source per chain, by the name used on the command line and in data/raw/.
SOURCES: dict[str, Callable[[], DealSource]] = {
    "ah": AhSource,
    "jumbo": JumboSource,
    "lidl": LidlSource,
}
DEFAULT_OPENAPI_PATH = Path("frontend/openapi.json")
DEFAULT_STORES_PATH = Path("koopjeskompas/stores/nl_stores.json")
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

    fetch = subcommands.add_parser(
        "fetch-deals", help="fetch and cache this week's deals of every chain"
    )
    fetch.add_argument(
        "--from-raw",
        action="store_true",
        help="re-parse the responses saved by an earlier fetch instead of asking again",
    )
    fetch.add_argument(
        "--chain",
        choices=list(SOURCES),
        action="append",
        help="only this chain; repeat for several (default: all)",
    )
    fetch.set_defaults(handler=_fetch_deals)

    stores = subcommands.add_parser(
        "fetch-stores",
        help="fetch every store of every chain in the Netherlands from OpenStreetMap",
    )
    stores.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        help="the Overpass server to ask (default: %(default)s)",
    )
    stores.add_argument(
        "--from-raw",
        action="store_true",
        help="re-convert the answer saved by an earlier fetch instead of asking again",
    )
    stores.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_STORES_PATH,
        help="where to write the stores (default: %(default)s)",
    )
    stores.set_defaults(handler=_fetch_stores)

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
        help="upload the cached deals to a demo: AWS (`aws login`) or Azure (`az login`)",
    )
    publish.add_argument(
        "--cloud",
        choices=["aws", "azure"],
        default="aws",
        help="which demo (default: %(default)s)",
    )
    publish.add_argument(
        "--bucket",
        help="AWS: the data bucket (default: read from the deployed stack's outputs)",
    )
    publish.add_argument(
        "--stack",
        default=STACK_NAME,
        help="AWS: the CDK stack to read it from (default: %(default)s)",
    )
    publish.add_argument(
        "--container-url",
        default=os.environ.get("DEALS_CONTAINER_URL"),
        help="Azure: the Blob container, https://<account>.blob.core.windows.net/data "
        "(default: $DEALS_CONTAINER_URL; Terraform's output deals_container_url)",
    )
    publish.set_defaults(handler=_publish_deals)

    return parser


def _today(args: argparse.Namespace) -> date:
    today: date = args.today or date.today()
    return today


def _fetch_deals(args: argparse.Namespace) -> int:
    """Run each chain's source on its own: one failing doesn't cost the others."""
    today = _today(args)
    failed = 0
    for key in args.chain or list(SOURCES):
        source = SOURCES[key]()
        raw_dir = args.data_dir / "raw" / key / today.isoformat()
        try:
            if args.from_raw:
                result = source.reparse(raw_dir, today)
            else:
                result = source.fetch(raw_dir, today)
        except SourceError as error:
            print(f"Fetching {source.chain} deals failed: {error}", file=sys.stderr)
            failed += 1
            continue
        _report(result, deals_path(args.data_dir, source.chain))
    # Nonzero when any chain failed, so a script notices; what worked is saved anyway.
    return 1 if failed else 0


def _report(result: SourceResult, path: Path) -> None:
    save_deals(path, result.deals)
    print(f"{result.title}: {len(result.deals)} deals saved to {path}")
    for note in result.notes:
        print(note)
    if result.skipped:
        print(f"Skipped {len(result.skipped)} malformed items (see warnings above)")
    if result.no_discount:
        print(
            "Deals without a determinable discount (unrecognised mechanic, or no "
            "normal price to compare with); kept, but they score zero:"
        )
        for mechanic, count in result.no_discount.most_common():
            print(f"  {count:3d}x {mechanic}")


def _fetch_stores(args: argparse.Namespace) -> int:
    raw_path = (
        args.data_dir / "raw" / "osm" / _today(args).isoformat() / "nl_stores.json"
    )
    try:
        if args.from_raw:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        else:
            payload = fetch_overpass(overpass_query(), args.server)
            # Saved before converting, so a conversion bug never needs a refetch.
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(payload), encoding="utf-8")
    except (OverpassError, FileNotFoundError) as error:
        print(f"Fetching stores failed: {error}", file=sys.stderr)
        return 1

    result = stores_from_overpass(payload)
    if not result.stores:
        # Never replace the list with nothing: that would silently remove every store.
        print(
            "Found no stores, so nothing was written. If the server lacks area data, "
            "it can't find 'the Netherlands': try another --server.",
            file=sys.stderr,
        )
        return 1

    output: Path = args.output
    before = len(load_stores(output)) if output.exists() else 0
    save_stores(output, result.stores)
    print(f"{len(result.stores)} stores written to {output} (was {before})")
    if result.duplicates:
        print(f"Merged {result.duplicates} stores that were mapped twice")
    if result.other_chains:
        biggest = ", ".join(
            f"{brand} {n}" for brand, n in result.other_chains.most_common(5)
        )
        total = result.other_chains.total()
        print(f"Other chains' supermarkets, not kept: {total} ({biggest}, ...)")
    if result.skipped:
        print(f"Skipped {len(result.skipped)}:")
        for reason in result.skipped:
            print(f"  {reason}")
    return 0


def _rank(args: argparse.Namespace) -> int:
    snapshots = load_snapshots(args.data_dir)
    if not snapshots:
        print(
            f"No deals cached in {args.data_dir / 'deals'}; "
            "run 'koopjeskompas fetch-deals' first."
        )
        return 1
    deals = [deal for chain_deals in snapshots.values() for deal in chain_deals]
    today = _today(args)

    preferences = Preferences(
        diet=args.diet,
        cuisines=frozenset(args.cuisine),
        lactose_free=args.lactose_free,
        gluten_free=args.gluten_free,
    )
    rankings = rank_stores(
        # Only chains with deals: the others' stores would look empty.
        stores=[store for store in load_stores() if store.chain in snapshots],
        deals=deals,
        preferences=preferences,
        location=Coordinates(latitude=args.lat, longitude=args.lon),
        today=today,
        weights=ScoringWeights(max_distance_km=args.radius_km, top_k=args.top_k),
        chain_days=chain_ranking_days(deals, today),
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
        if args.cloud == "azure":
            return _publish_to_azure(args.container_url, files)
        return _publish_to_aws(args.bucket, args.stack, files)
    except PublishError as error:
        print(error, file=sys.stderr)
        return 1


def _publish_to_aws(bucket: str | None, stack: str, files: list[Path]) -> int:
    try:
        bucket = bucket or find_data_bucket(
            boto3.client("cloudformation", region_name=REGION), stack
        )
        target = open_s3_snapshots(bucket, region=REGION)
        keys = publish_deals(target, files)
    except (BotoCoreError, ClientError) as error:
        print(f"Talking to AWS failed: {error}", file=sys.stderr)
        if _signed_out(error):
            print(
                "Your AWS session is missing or expired: run 'aws login'.",
                file=sys.stderr,
            )
        return 1
    for key in keys:
        print(f"Uploaded {target.location}/{key}")
    print(
        "New Lambda environments use it at once; warm ones keep the previous snapshot "
        "until AWS recycles them, within hours."
    )
    return 0


def _publish_to_azure(container_url: str | None, files: list[Path]) -> int:
    if not container_url:
        raise PublishError(
            "Which Blob container? Pass --container-url or set DEALS_CONTAINER_URL "
            "(terraform -chdir=infra/azure output -raw deals_container_url)."
        )
    # Imported here, as in api/container.py: an AWS publish never loads the Azure SDK.
    from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

    from koopjeskompas.cloud.azure.blob import open_blob_snapshots

    target = open_blob_snapshots(container_url)
    try:
        keys = publish_deals(target, files)
    except ClientAuthenticationError as error:
        # DefaultAzureCredential found no identity: on the laptop, that's az login.
        print(f"Signing in to Azure failed: {error}", file=sys.stderr)
        print("Not signed in to Azure: run 'az login'.", file=sys.stderr)
        return 1
    except HttpResponseError as error:
        print(f"Talking to Azure failed: {error.message}", file=sys.stderr)
        if error.status_code == 403:
            print(
                "Signed in, but not allowed to write there: you need the role "
                "'Storage Blob Data Contributor' on the container (Terraform gives it "
                "to whoever applies; a new role can take a few minutes to work).",
                file=sys.stderr,
            )
        return 1
    for key in keys:
        print(f"Uploaded {target.location}/{key}")
    print(
        "New replicas use it at once; a running one keeps the previous snapshot until "
        "it scales to zero (5 minutes without requests) or restarts."
    )
    return 0


# Error codes AWS answers with when the credentials are stale or invalid.
_EXPIRED_CODES = {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId"}


def _signed_out(error: BotoCoreError | ClientError) -> bool:
    """Whether signing in again would help; other errors, such as a missing
    dependency or a stack that doesn't exist, get no misleading 'aws login' hint."""
    if isinstance(error, ClientError):
        return error.response.get("Error", {}).get("Code") in _EXPIRED_CODES
    return isinstance(error, (NoCredentialsError, CredentialRetrievalError))


def _openapi(args: argparse.Namespace) -> int:
    path: Path = args.output
    path.write_text(openapi_json(create_app(data_dir=args.data_dir)), encoding="utf-8")
    print(f"OpenAPI schema written to {path}")
    return 0
