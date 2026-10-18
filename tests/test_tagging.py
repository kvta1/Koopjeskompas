import pytest

from koopjeskompas.domain.models import Cuisine, Diet, Preferences
from koopjeskompas.domain.tagging import (
    BASELINE_RELEVANCE,
    Tag,
    passes_hard_filters,
    relevance,
    tag_product,
)

VEGETARIAN = Preferences(diet=Diet.VEGETARIAN)
VEGAN = Preferences(diet=Diet.VEGAN)


@pytest.mark.parametrize(
    ("product", "vegetarian", "vegan"),
    [
        ("AH Kipfilet", False, False),
        ("Gerookte kippendijen", False, False),
        ("Unox Rookworst", False, False),
        ("Rundergehakt 500g", False, False),
        ("Zalmfilet", False, False),
        ("Ansjovis in olijfolie", False, False),
        ("Garnalen", False, False),
        ("Groentekroket", False, False),  # unknown filling: excluded to be safe
        ("Geitenkaas", True, False),
        ("Halfvolle melk", True, False),
        ("Scharreleieren 10 stuks", True, False),
        ("Griekse yoghurt", True, False),
        ("Bloemenhoning", True, False),
        ("Kikkererwten", True, True),
        ("Vleestomaten", True, True),
        ("Pindakaas", True, True),
        ("Havermelk", True, True),
        ("Kokosmelk", True, True),
        ("Vegetarische kipstuckjes", True, False),
        ("Vegaburger", True, False),
        ("Vegan kaas", True, True),
        ("Plantaardige yoghurt", True, True),
    ],
)
def test_diet_hard_filter(product: str, vegetarian: bool, vegan: bool) -> None:
    tags = tag_product(product)
    assert passes_hard_filters(tags, VEGETARIAN) is vegetarian
    assert passes_hard_filters(tags, VEGAN) is vegan
    assert passes_hard_filters(tags, Preferences()) is True


@pytest.mark.parametrize(
    ("product", "lactose_free_ok", "gluten_free_ok"),
    [
        ("Halfvolle melk", False, True),
        ("Lactosevrije melk", True, True),
        ("Volkoren brood", True, False),
        ("Glutenvrij brood", True, True),
        ("Spaghetti", True, False),
        ("Appels", True, True),
    ],
)
def test_allergy_hard_filters(
    product: str, lactose_free_ok: bool, gluten_free_ok: bool
) -> None:
    tags = tag_product(product)
    assert passes_hard_filters(tags, Preferences(lactose_free=True)) is lactose_free_ok
    assert passes_hard_filters(tags, Preferences(gluten_free=True)) is gluten_free_ok


@pytest.mark.parametrize(
    ("product", "cuisine"),
    [
        ("Hummus naturel", Cuisine.MIDDLE_EASTERN),
        ("Kikkererwten", Cuisine.MIDDLE_EASTERN),
        ("Aubergines", Cuisine.MIDDLE_EASTERN),
        ("Verse pesto", Cuisine.ITALIAN),
        ("Buffelmozzarella", Cuisine.ITALIAN),
        ("Biologische tofu", Cuisine.ASIAN),
        ("Wokgroente", Cuisine.ASIAN),
        ("Tortilla wraps", Cuisine.MEXICAN),
        ("Rode curry pasta", Cuisine.INDIAN),
    ],
)
def test_cuisine_tags(product: str, cuisine: Cuisine) -> None:
    assert cuisine in tag_product(product)


def test_unrelated_product_has_no_cuisine() -> None:
    assert not tag_product("Appels") & set(Cuisine)


def test_short_keywords_only_match_whole_words() -> None:
    # "ei" must not match inside "romeinse".
    assert Tag.EGG not in tag_product("Romeinse sla")


@pytest.mark.parametrize(
    ("product", "cuisines", "expected"),
    [
        ("Hummus", frozenset(), 1.0),
        ("Appels", frozenset(), 1.0),
        ("Hummus", frozenset({Cuisine.MIDDLE_EASTERN}), 1.0),
        ("Hummus", frozenset({Cuisine.ITALIAN, Cuisine.MIDDLE_EASTERN}), 1.0),
        ("Appels", frozenset({Cuisine.MIDDLE_EASTERN}), BASELINE_RELEVANCE),
        ("Hummus", frozenset({Cuisine.ITALIAN}), BASELINE_RELEVANCE),
    ],
)
def test_relevance(product: str, cuisines: frozenset[Cuisine], expected: float) -> None:
    assert relevance(tag_product(product), Preferences(cuisines=cuisines)) == expected
