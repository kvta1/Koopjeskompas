from datetime import date

from koopjeskompas.domain.models import Coordinates, Deal, Store
from koopjeskompas.domain.scoring import ScoredDeal, StoreRanking
from koopjeskompas.report import format_ranking


def scored(name: str, mechanic: str, products_counted: int = 0) -> ScoredDeal:
    deal = Deal(
        chain="AH",
        product_name=name,
        mechanic_string=mechanic,
        valid_from=date(2026, 11, 2),
        valid_to=date(2026, 11, 8),
    )
    return ScoredDeal(
        deal=deal,
        discount=0.2,
        relevance=1.0,
        value=0.2,
        products_counted=products_counted,
    )


def ranking(*deals: ScoredDeal) -> StoreRanking:
    store = Store(
        chain="AH",
        name="AH Breestraat",
        address="Breestraat 130, Leiden",
        location=Coordinates(latitude=52.158, longitude=4.489),
    )
    return StoreRanking(
        store=store, score=0.1, basket_score=0.2, distance_km=1.3, top_deals=deals
    )


def test_formats_stores_and_their_deals() -> None:
    text = format_ranking([ranking(scored("AH Spruitjes", "VOOR 0.99"))])
    assert text == (
        "1. AH Breestraat (Breestraat 130, Leiden) | 1.3 km | score 0.100\n"
        "    20%  AH Spruitjes  [VOOR 0.99]"
    )


def test_range_deals_say_how_many_products_counted() -> None:
    text = format_ranking(
        [
            ranking(
                scored("Alle AH Verse pizza's", "2 VOOR 12.00", products_counted=8),
                scored("AH Yorkham van de versafdeling", "100 GRAM VOOR 1.99", 1),
            )
        ]
    )
    assert "Alle AH Verse pizza's  [2 VOOR 12.00]  median of 8 products" in text
    assert "[100 GRAM VOOR 1.99]  median of 1 product" in text


def test_no_stores() -> None:
    assert format_ranking([]) == "No stores within range."


def test_store_without_matching_deals() -> None:
    assert format_ranking([ranking()]).endswith("no matching deals")
