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
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from koopjeskompas.api.schemas import Health, RankedStore, RankRequest, RankResponse
from koopjeskompas.domain.models import Coordinates, Deal, Preferences, Store
from koopjeskompas.domain.scoring import ScoringWeights, rank_stores, ranking_day
from koopjeskompas.ingestion.cache import deals_path, load_deals
from koopjeskompas.stores import load_stores

CHAIN = "AH"


def create_app(data_dir: Path) -> FastAPI:
    """Build the app for the cache in ``data_dir``.

    A factory rather than a module-level ``app``, so tests and the CLI can each point
    it at their own data directory without global configuration.
    """
    app = FastAPI(
        title="Koopjeskompas",
        summary="Ranks nearby supermarkets by how good their deals are for you.",
        version="0.1.0",
    )
    app.state.data_dir = data_dir
    app.state.stores = load_stores()  # packaged and fixed: load once
    app.include_router(router)

    # The web page is served elsewhere (Vite's dev server locally, CloudFront later),
    # so a visitor to the API itself gets its docs rather than a bare 404. Left out of
    # the OpenAPI schema: it's not part of the API.
    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


def openapi_json(app: FastAPI) -> str:
    """The app's OpenAPI schema as text, the way ``frontend/openapi.json`` stores it.

    The web page generates its TypeScript types from that file, so the frontend can't
    drift from the request and response models in ``schemas.py`` unnoticed.
    """
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


# --- dependencies: what an endpoint needs, swappable in tests ---------------


def get_deals(request: Request) -> list[Deal]:
    # Read on every request: the cache is small, and this way a new fetch-deals run
    # is picked up without restarting the server.
    path = deals_path(request.app.state.data_dir, CHAIN)
    try:
        return load_deals(path)
    except FileNotFoundError:
        # 503, not 500: the server works, but it has no data to serve yet.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No deals cached at {path}; run 'koopjeskompas fetch-deals' first.",
        ) from None


def get_stores(request: Request) -> list[Store]:
    stores: list[Store] = request.app.state.stores
    return stores


def get_today() -> date:
    return date.today()


Deals = Annotated[list[Deal], Depends(get_deals)]
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
def rank(body: RankRequest, deals: Deals, stores: Stores, today: Today) -> RankResponse:
    """Rank the stores within ``radius_km`` of ``location``, best first.

    Each store comes with the deals that earned its score. If the cached deals have
    all ended (or not yet begun), they are ranked as of their nearest day instead,
    and ``ranked_on`` says which day that was.
    """
    day = ranking_day(deals, today)
    rankings = rank_stores(
        stores=stores,
        deals=deals,
        preferences=Preferences(
            diet=body.diet,
            cuisines=frozenset(body.cuisines),
            gluten_free=body.gluten_free,
            lactose_free=body.lactose_free,
        ),
        location=Coordinates(latitude=body.location.lat, longitude=body.location.lon),
        today=day,
        weights=ScoringWeights(
            top_k=body.top_k,
            distance_weight=body.distance_weight,
            max_distance_km=body.radius_km,
        ),
    )
    return RankResponse(
        ranked_on=day,
        stores=[
            RankedStore.from_ranking(position, ranking)
            for position, ranking in enumerate(rankings, start=1)
        ],
    )
