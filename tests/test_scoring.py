from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from koopjeskompas.domain.models import (
    Coordinates,
    Cuisine,
    Deal,
    Diet,
    Preferences,
    Store,
)
from koopjeskompas.domain.scoring import (
    ScoringWeights,
    basket_score,
    deal_value,
    rank_stores,
    score_deals,
    store_score,
)

TODAY = date(2026, 10, 18)
LEIDEN = Coordinates(latitude=52.1601, longitude=4.4970)
# Roughly 1 km and 3 km away from LEIDEN.
NEAR = Coordinates(latitude=52.1691, longitude=4.4970)
FAR = Coordinates(latitude=52.1871, longitude=4.4970)
OUT_OF_RANGE = Coordinates(latitude=52.3791, longitude=4.9003)  # Amsterdam


def make_deal(
    product_name: str,
    chain: str = "AH",
    mechanic: str = "25% korting",
    valid_from: date = date(2026, 10, 12),
    valid_to: date = date(2026, 10, 18),
) -> Deal:
    return Deal(
        chain=chain,
        product_name=product_name,
        mechanic_string=mechanic,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def make_store(name: str, chain: str, location: Coordinates) -> Store:
    return Store(chain=chain, name=name, location=location)


unit = st.floats(min_value=0, max_value=1)
values = st.lists(unit, max_size=30)
weights_strategy = st.builds(
    ScoringWeights,
    top_k=st.integers(1, 20),
    basket_weight=st.floats(0, 10),
    distance_weight=st.floats(0, 10),
    max_distance_km=st.floats(0.1, 50),
)


# --- pure building blocks -------------------------------------------------


@given(unit, unit)
def test_deal_value_is_a_fraction(discount: float, rel: float) -> None:
    assert 0 <= deal_value(discount, rel) <= 1


@pytest.mark.parametrize(("discount", "rel"), [(-0.1, 1), (1.1, 1), (1, -0.1)])
def test_deal_value_rejects_out_of_range(discount: float, rel: float) -> None:
    with pytest.raises(ValueError):
        deal_value(discount, rel)


def test_basket_score_only_counts_top_k() -> None:
    assert basket_score([0.1, 0.9, 0.5, 0.7], top_k=2) == pytest.approx(1.6)


@given(values, unit, st.integers(1, 20))
def test_adding_a_deal_never_lowers_the_basket(
    existing: list[float], extra: float, top_k: int
) -> None:
    assert basket_score([*existing, extra], top_k) >= basket_score(existing, top_k)


@given(values, st.integers(1, 20))
def test_normalized_basket_is_a_fraction(vals: list[float], top_k: int) -> None:
    assert 0 <= basket_score(vals, top_k) / top_k <= 1


@given(
    st.floats(0, 20),
    st.floats(0, 100),
    st.floats(0, 100),
    weights_strategy,
)
def test_score_is_non_increasing_in_distance(
    basket: float, d1: float, d2: float, weights: ScoringWeights
) -> None:
    near, far = sorted((d1, d2))
    assert store_score(basket, near, weights) >= store_score(basket, far, weights)


# --- deal scoring --------------------------------------------------------


def test_score_deals_skips_inactive_unparseable_and_filtered_deals() -> None:
    deals = [
        make_deal("Hummus"),
        make_deal("Kipfilet"),  # filtered by vegetarian diet
        make_deal("Falafel", valid_to=date(2026, 10, 17)),  # expired
        make_deal("Tahin", valid_from=date(2026, 10, 19), valid_to=date(2026, 10, 25)),
        make_deal("Couscous", mechanic="gratis bezorging"),  # unknown mechanic
    ]
    scored = score_deals(deals, Preferences(diet=Diet.VEGETARIAN), TODAY)
    assert [s.deal.product_name for s in scored] == ["Hummus"]


def test_score_deals_orders_by_value() -> None:
    prefs = Preferences(cuisines=frozenset({Cuisine.MIDDLE_EASTERN}))
    deals = [
        make_deal("Appels", mechanic="1+1 gratis"),  # 0.5 × 0.2 = 0.1
        make_deal("Hummus", mechanic="25% korting"),  # 0.25 × 1 = 0.25
        make_deal("Kikkererwten", mechanic="2e gratis"),  # 0.5 × 1 = 0.5
    ]
    scored = score_deals(deals, prefs, TODAY)
    assert [s.deal.product_name for s in scored] == ["Kikkererwten", "Hummus", "Appels"]
    assert [s.value for s in scored] == pytest.approx([0.5, 0.25, 0.1])


# --- store ranking -------------------------------------------------------


def test_rank_stores_end_to_end() -> None:
    stores = [
        make_store("AH Breestraat", "AH", NEAR),
        make_store("Jumbo Haarlemmerstraat", "Jumbo", NEAR),
        make_store("AH Amsterdam", "AH", OUT_OF_RANGE),
    ]
    deals = [
        make_deal("Hummus", chain="AH", mechanic="2e gratis"),
        make_deal("Kikkererwten", chain="AH", mechanic="25% korting"),
        make_deal("Kipfilet", chain="Jumbo", mechanic="1+1 gratis"),
        make_deal("Appels", chain="Jumbo", mechanic="25% korting"),
    ]
    prefs = Preferences(
        diet=Diet.VEGETARIAN, cuisines=frozenset({Cuisine.MIDDLE_EASTERN})
    )

    ranking = rank_stores(stores, deals, prefs, LEIDEN, TODAY)

    assert [r.store.name for r in ranking] == [
        "AH Breestraat",
        "Jumbo Haarlemmerstraat",
    ]
    ah, jumbo = ranking
    assert [d.deal.product_name for d in ah.top_deals] == ["Hummus", "Kikkererwten"]
    # The chicken deal is worth zero to a vegetarian, not "less".
    assert [d.deal.product_name for d in jumbo.top_deals] == ["Appels"]
    assert ah.distance_km == pytest.approx(1.0, abs=0.05)


def test_closer_store_wins_when_deals_are_equal() -> None:
    stores = [make_store("Far", "AH", FAR), make_store("Near", "AH", NEAR)]
    ranking = rank_stores(stores, [make_deal("Hummus")], Preferences(), LEIDEN, TODAY)
    assert [r.store.name for r in ranking] == ["Near", "Far"]
    assert ranking[0].score > ranking[1].score


def test_better_deals_can_outweigh_distance() -> None:
    stores = [make_store("Near", "Jumbo", NEAR), make_store("Far", "AH", FAR)]
    deals = [
        make_deal(f"Product {i}", chain="AH", mechanic="1+1 gratis") for i in range(10)
    ]
    ranking = rank_stores(stores, deals, Preferences(), LEIDEN, TODAY)
    assert [r.store.name for r in ranking] == ["Far", "Near"]


def test_chain_matching_ignores_case() -> None:
    stores = [make_store("Store", "Albert Heijn", NEAR)]
    deals = [make_deal("Hummus", chain="albert heijn")]
    (ranking,) = rank_stores(stores, deals, Preferences(), LEIDEN, TODAY)
    assert len(ranking.top_deals) == 1


def test_top_k_limits_explanations() -> None:
    stores = [make_store("Store", "AH", NEAR)]
    deals = [make_deal(f"Product {i}") for i in range(20)]
    (ranking,) = rank_stores(
        stores, deals, Preferences(), LEIDEN, TODAY, ScoringWeights(top_k=3)
    )
    assert len(ranking.top_deals) == 3


product_names = st.sampled_from(
    ["Hummus", "Kipfilet", "Appels", "Geitenkaas", "Tofu", "Spaghetti", "Zalm"]
)
mechanics = st.sampled_from(["25% korting", "2e halve prijs", "1+1 gratis", "3 voor 2"])
deal_strategy = st.builds(make_deal, product_names, st.just("AH"), mechanics)
prefs_strategy = st.builds(
    Preferences,
    diet=st.sampled_from(Diet),
    cuisines=st.frozensets(st.sampled_from(Cuisine)),
)


@given(st.lists(deal_strategy, max_size=15), deal_strategy, prefs_strategy)
def test_adding_a_deal_never_lowers_a_store_score(
    deals: list[Deal], extra: Deal, prefs: Preferences
) -> None:
    stores = [make_store("Store", "AH", NEAR)]
    (before,) = rank_stores(stores, deals, prefs, LEIDEN, TODAY)
    (after,) = rank_stores(stores, [*deals, extra], prefs, LEIDEN, TODAY)
    assert after.score >= before.score


@given(st.lists(deal_strategy, max_size=15), prefs_strategy)
def test_vegetarian_rankings_never_contain_meat_or_fish(
    deals: list[Deal], prefs: Preferences
) -> None:
    prefs = prefs.model_copy(update={"diet": Diet.VEGETARIAN})
    stores = [make_store("Store", "AH", NEAR)]
    (ranking,) = rank_stores(stores, deals, prefs, LEIDEN, TODAY)
    shown = {d.deal.product_name for d in ranking.top_deals}
    assert not shown & {"Kipfilet", "Zalm"}
