"""API tests through FastAPI's TestClient: real HTTP requests, no server needed."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from koopjeskompas.api.app import create_app, get_today, openapi_json
from koopjeskompas.domain.models import Deal, RangeProduct
from koopjeskompas.ingestion.cache import deals_path, save_deals

TODAY = date(2026, 11, 4)
FRONTEND_SCHEMA = Path(__file__).parents[2] / "frontend" / "openapi.json"
LEIDEN_CENTRAAL = {"lat": 52.1664, "lon": 4.4817}


def make_deal(name: str, mechanic: str, **overrides: Any) -> Deal:
    fields: dict[str, Any] = {
        "chain": "AH",
        "product_name": name,
        "mechanic_string": mechanic,
        "valid_from": date(2026, 11, 2),
        "valid_to": date(2026, 11, 8),
    }
    return Deal.model_validate(fields | overrides)


DEALS = [
    make_deal("AH Hummus naturel", "25% korting"),
    make_deal("AH Kipfilet", "1+1 gratis", category="Vlees"),
    make_deal(
        "Alle AH Verse pizza's",
        "2 VOOR 12.00",
        products=(
            RangeProduct(
                name="AH Pizza mozzarella pesto", normal_price=Decimal("6.89")
            ),
            RangeProduct(name="AH Pizza salami", normal_price=Decimal("6.99")),
        ),
    ),
    make_deal(
        "Last week's deal",
        "50% korting",
        valid_from=date(2026, 10, 26),
        valid_to=date(2026, 11, 1),
    ),
]


@pytest.fixture
def app(tmp_path: Path) -> Iterator[FastAPI]:
    save_deals(deals_path(tmp_path, "AH"), DEALS)
    app = create_app(data_dir=tmp_path)
    # Dependency injection at work: the endpoint asks for "today", the test decides.
    app.dependency_overrides[get_today] = lambda: TODAY
    yield app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def rank(client: TestClient, **body: Any) -> Any:
    response = client.post("/api/rank", json={"location": LEIDEN_CENTRAAL, **body})
    assert response.status_code == 200, response.text
    return response.json()


def deal_names(store: Any) -> list[str]:
    return [d["product_name"] for d in store["top_deals"]]


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_root_redirects_to_the_docs(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
    assert "/" not in client.get("/openapi.json").json()["paths"]


def test_ranks_the_leiden_stores_nearest_first(client: TestClient) -> None:
    result = rank(client)

    assert result["ranked_on"] == "2026-11-04"
    stores = result["stores"]
    assert [s["rank"] for s in stores] == list(range(1, len(stores) + 1))
    # All stores share AH's deals, so distance decides.
    assert stores[0]["store"]["name"] == "AH Breestraat"
    distances = [s["distance_km"] for s in stores]
    assert distances == sorted(distances)
    assert all(d <= 5 for d in distances)


def test_response_explains_each_score(client: TestClient) -> None:
    store = rank(client)["stores"][0]

    assert set(store) == {
        "rank", "store", "score", "basket_score", "distance_km", "top_deals"
    }  # fmt: skip
    assert set(store["store"]) == {"chain", "name", "address", "lat", "lon"}
    hummus = next(
        d for d in store["top_deals"] if d["product_name"].endswith("Hummus naturel")
    )
    assert hummus == {
        "product_name": "AH Hummus naturel",
        "category": None,
        "mechanic": "25% korting",
        "discount": 0.25,
        "relevance": 1.0,
        "value": 0.25,
        "products_counted": 0,
        "valid_from": "2026-11-02",
        "valid_to": "2026-11-08",
    }
    assert "Last week's deal" not in deal_names(store)


def test_vegetarian_is_a_hard_filter(client: TestClient) -> None:
    store = rank(client, diet="vegetarian")["stores"][0]

    assert "AH Kipfilet" not in deal_names(store)
    pizzas = next(d for d in store["top_deals"] if d["product_name"].startswith("Alle"))
    assert pizzas["products_counted"] == 1  # the salami pizza doesn't count


def test_cuisines_change_relevance(client: TestClient) -> None:
    store = rank(client, cuisines=["italian"])["stores"][0]
    relevance = {d["product_name"]: d["relevance"] for d in store["top_deals"]}
    assert relevance["Alle AH Verse pizza's"] == 1.0
    assert relevance["AH Hummus naturel"] < 1.0


def test_radius_and_top_k(client: TestClient) -> None:
    assert rank(client, radius_km=0.5)["stores"] == []
    (first, *_) = rank(client, top_k=1)["stores"]
    assert len(first["top_deals"]) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},  # no location
        {"location": {"lat": 100, "lon": 4.5}},  # latitude out of range
        {"location": LEIDEN_CENTRAAL, "diet": "pescatarian"},
        {"location": LEIDEN_CENTRAAL, "cuisines": ["dutch"]},
        {"location": LEIDEN_CENTRAAL, "radius_km": 0},
        {"location": LEIDEN_CENTRAAL, "top_k": 0},
        {"location": LEIDEN_CENTRAAL, "cuisine": ["italian"]},  # typo: unknown field
    ],
)
def test_invalid_requests_are_rejected_with_a_reason(
    client: TestClient, body: dict[str, Any]
) -> None:
    response = client.post("/api/rank", json=body)
    assert response.status_code == 422
    (error, *_) = response.json()["detail"]
    assert error["loc"][0] == "body"
    assert error["msg"]


def test_without_cached_deals_the_api_says_what_to_do(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post("/api/rank", json={"location": LEIDEN_CENTRAAL})
    assert response.status_code == 503
    assert "fetch-deals" in response.json()["detail"]
    # The rest of the API still works.
    assert client.get("/api/health").status_code == 200


def test_a_new_fetch_is_picked_up_without_a_restart(
    client: TestClient, tmp_path: Path
) -> None:
    save_deals(deals_path(tmp_path, "AH"), [make_deal("AH Tahin", "2e halve prijs")])
    store = rank(client)["stores"][0]
    assert deal_names(store) == ["AH Tahin"]


def test_openapi_documents_the_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert {"/api/health", "/api/rank"} <= set(schema["paths"])
    assert "503" in schema["paths"]["/api/rank"]["post"]["responses"]


def test_the_frontend_has_the_current_openapi_schema(app: FastAPI) -> None:
    # The web page's TypeScript types are generated from this file. If this fails,
    # the API changed: run `uv run koopjeskompas openapi`, then in frontend/
    # `npm run gen:api`, and commit both files.
    assert FRONTEND_SCHEMA.read_text(encoding="utf-8") == openapi_json(app)
