"""The web API: a thin HTTP layer over the domain's ``rank_stores``.

Like the CLI, it holds no logic of its own. It validates the request (Pydantic does
that from ``RankRequest``), gathers the inputs through FastAPI dependencies, calls the
domain and translates the result into the response models.

Read-only by design: it reads the deal cache that ``koopjeskompas fetch-deals`` wrote
and never contacts a supermarket during a request.

The endpoints are plain ``def`` functions, not ``async def``. Scoring is CPU-bound and
reading the cache is a small local file, so there is nothing to await; FastAPI runs
sync endpoints in a thread pool, so they don't block the server either.
"""

import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from koopjeskompas.api.schemas import (
    BeerOfferOut,
    BeerResponse,
    ChainOut,
    Health,
    RankedStore,
    RankRequest,
    RankResponse,
)
from koopjeskompas.domain.beer import Packaging, beer_offers
from koopjeskompas.domain.models import Coordinates, Deal, Preferences, Store
from koopjeskompas.domain.scoring import (
    ScoringWeights,
    chain_ranking_days,
    rank_stores,
)
from koopjeskompas.ingestion.cache import load_snapshots
from koopjeskompas.stores import load_stores


def create_app(data_dir: Path, cors_origins: Sequence[str] = ()) -> FastAPI:
    """Build the app for the cache in ``data_dir``.

    A factory rather than a module-level ``app``, so tests and the CLI can each point
    it at their own data directory without global configuration.

    ``cors_origins`` are the web pages on another domain that may call the API from a
    browser, e.g. ``https://<name>.azurestaticapps.net``. None by default: locally
    (Vite's proxy) and on AWS (CloudFront) page and API share one origin, and a
    browser needs no permission for that.
    """
    app = FastAPI(
        title="Koopjeskompas",
        summary="Ranks nearby supermarkets by how good their deals are for you.",
        version="0.1.0",
    )
    app.state.data_dir = data_dir
    app.state.stores = load_stores()  # packaged and fixed: load once
    app.include_router(router)
    if cors_origins:
        _allow_cross_origin(app, cors_origins)

    # The web page is served elsewhere (Vite's dev server locally, CloudFront later),
    # so a visitor to the API itself gets its docs rather than a bare 404. Left out of
    # the OpenAPI schema: it's not part of the API.
    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


def _allow_cross_origin(app: FastAPI, origins: Sequence[str]) -> None:
    """Let the pages at ``origins``, and only those, call the API from a browser.

    A page's JavaScript may only read answers from its own origin (scheme, host and
    port), unless the other server says otherwise: that's CORS. For a JSON POST the
    browser first asks with an OPTIONS request (the "preflight"); this middleware
    answers it and adds ``Access-Control-Allow-Origin`` to the real answer. It's a
    browser rule, not access control: curl ignores it, and the API is public anyway.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),  # exact origins, never "*"
        allow_methods=["GET", "POST"],
        # What the page sends: JSON, and the body hash that CloudFront needs on AWS
        # (frontend/src/api/client.ts), harmless here.
        allow_headers=["Content-Type", "x-amz-content-sha256"],
        max_age=3600,  # the browser may reuse a preflight answer for an hour
    )


def openapi_json(app: FastAPI) -> str:
    """The app's OpenAPI schema as text, the way ``frontend/openapi.json`` stores it.

    The web page generates its TypeScript types from that file, so the frontend can't
    drift from the request and response models in ``schemas.py`` unnoticed.
    """
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


# --- dependencies: what an endpoint needs, swappable in tests ---------------


def get_snapshots(request: Request) -> dict[str, list[Deal]]:
    """Every chain's cached deals, by chain name; chains without a snapshot are absent.

    Read on every request: the cache is small, and this way a new fetch-deals run
    is picked up without restarting the server.
    """
    data_dir = request.app.state.data_dir
    snapshots = load_snapshots(data_dir)
    if not snapshots:
        # 503, not 500: the server works, but it has no data to serve yet.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"No deals cached in {data_dir / 'deals'}; "
                "run 'koopjeskompas fetch-deals' first."
            ),
        )
    return snapshots


def get_stores(request: Request) -> list[Store]:
    stores: list[Store] = request.app.state.stores
    return stores


def get_today() -> date:
    return date.today()


Snapshots = Annotated[dict[str, list[Deal]], Depends(get_snapshots)]
Stores = Annotated[list[Store], Depends(get_stores)]
Today = Annotated[date, Depends(get_today)]


# --- endpoints ---------------------------------------------------------------

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> Health:
    return Health(status="ok")


@router.post(
    "/rank",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "No deals cached yet"}
    },
)
def rank(
    body: RankRequest, snapshots: Snapshots, stores: Stores, today: Today
) -> RankResponse:
    """Rank the stores within ``radius_km`` of ``location``, best first.

    Each store comes with the deals that earned its score. Only chains with cached
    deals take part: a store of a chain without them would look like a store with no
    deals. If a chain's cached deals have all ended (or not yet begun), they are
    ranked as of their nearest day instead, and ``chains`` says which day that was.
    """
    deals = [deal for chain_deals in snapshots.values() for deal in chain_deals]
    days = {chain: today for chain in snapshots} | chain_ranking_days(deals, today)
    rankings = rank_stores(
        stores=[store for store in stores if store.chain in snapshots],
        deals=deals,
        preferences=Preferences(
            diet=body.diet,
            cuisines=frozenset(body.cuisines),
            gluten_free=body.gluten_free,
            lactose_free=body.lactose_free,
        ),
        location=Coordinates(latitude=body.location.lat, longitude=body.location.lon),
        today=today,
        weights=ScoringWeights(
            top_k=body.top_k,
            distance_weight=body.distance_weight,
            max_distance_km=body.radius_km,
        ),
        chain_days=days,
    )
    return RankResponse(
        ranked_on=today,
        chains=[ChainOut(chain=chain, deals_on=day) for chain, day in days.items()],
        stores=[
            RankedStore.from_ranking(position, ranking)
            for position, ranking in enumerate(rankings, start=1)
        ],
    )


@router.get(
    "/beer",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "No deals cached yet"}
    },
)
def beer(snapshots: Snapshots, today: Today) -> BeerResponse:
    """This week's beer deals of every chain, as crates, cans and bottles, each list
    cheapest per litre first. National: deals are the same in every store of a chain.

    Each chain's deals count on its own day, as in ``/api/rank``: a chain whose cached
    deals have run out shows them as of their last day.
    """
    deals = [deal for chain_deals in snapshots.values() for deal in chain_deals]
    days = {chain: today for chain in snapshots} | chain_ranking_days(deals, today)
    offers = sorted(
        (
            offer
            for chain, chain_deals in snapshots.items()
            for offer in beer_offers(chain_deals, days[chain])
        ),
        key=lambda offer: (offer.price_per_litre, offer.product),
    )

    def of(kind: Packaging) -> list[BeerOfferOut]:
        return [BeerOfferOut.from_offer(o) for o in offers if o.packaging is kind]

    return BeerResponse(
        ranked_on=today,
        chains=[ChainOut(chain=chain, deals_on=day) for chain, day in days.items()],
        crates=of(Packaging.CRATE),
        cans=of(Packaging.CAN),
        bottles=of(Packaging.BOTTLE),
    )
