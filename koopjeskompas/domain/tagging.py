"""Tier-1 preference matching: a hand-built Dutch keyword taxonomy.

Product names are split into lowercase word tokens. A keyword matches a token if
they are equal or, for keywords of at least ``_MIN_COMPOUND_LEN`` characters, if
the token starts or ends with it — Dutch glues words together, so "kip" must
match "kipfilet" and "kaas" must match "geitenkaas".

Diet tags are a blocklist: a product with no recognisable animal-product keyword
passes the vegetarian/vegan filter. Keywords lean towards over-matching, because
hiding a vegetarian product is cheaper than showing a meat one.
"""

import re
from collections.abc import Iterable
from enum import StrEnum

from koopjeskompas.domain.models import Cuisine, Diet, Preferences


class Tag(StrEnum):
    MEAT = "meat"
    FISH = "fish"
    DAIRY = "dairy"
    EGG = "egg"
    HONEY = "honey"
    GLUTEN = "gluten"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    # Labelled vegetarian but not vegan, e.g. a vegaburger: usually egg or dairy.
    VEGETARIAN_LABEL = "vegetarian_label"
    LACTOSE_FREE = "lactose_free"
    GLUTEN_FREE = "gluten_free"


# Relevance of a diet-compatible deal that matches none of the preferred
# cuisines. Non-zero, because a cheap staple is still worth something.
BASELINE_RELEVANCE = 0.2

_MIN_COMPOUND_LEN = 3
_TOKEN_RE = re.compile(r"[a-zà-ÿ]+")

_MEAT = frozenset({
    "vlees", "kip", "rund", "varken", "kalf", "lam", "lams", "gehakt", "spek",
    "ham", "worst", "salami", "bacon", "kalkoen", "eend", "biefstuk", "schnitzel",
    "burger", "shoarma", "döner", "kebab", "gyros", "frikandel", "kroket",
    "bitterbal", "americain", "carpaccio", "chorizo", "pastrami", "prosciutto",
    "pancetta", "rosbief", "entrecote", "ossenhaas", "varkenshaas", "karbonade",
    "slavink", "spareribs", "cervelaat", "fricandeau", "hotdog",
})  # fmt: skip
_FISH = frozenset({
    "vis", "zalm", "tonijn", "garnaal", "garnalen", "kabeljauw", "haring",
    "makreel", "mossel", "mosselen", "pangasius", "tilapia", "kibbeling",
    "sardine", "sardines", "forel", "schol", "scampi", "surimi", "krab",
    "kreeft", "oester", "oesters", "lekkerbekje", "ansjovis",
})  # fmt: skip
_DAIRY = frozenset({
    "melk", "kaas", "yoghurt", "kwark", "boter", "room", "vla", "zuivel", "feta",
    "mozzarella", "mascarpone", "ricotta", "halloumi", "burrata", "parmezaan",
    "parmigiano", "brie", "camembert", "skyr", "labneh", "paneer", "fraiche",
})  # fmt: skip
_EGG = frozenset({"ei", "eieren", "eier", "mayonaise"})
_HONEY = frozenset({"honing"})
_GLUTEN = frozenset({
    "brood", "tarwe", "rogge", "gerst", "spelt", "pasta", "spaghetti", "penne",
    "fusilli", "tagliatelle", "lasagne", "ravioli", "tortellini", "couscous",
    "bulgur", "crackers", "beschuit", "koek", "cake", "croissant", "pizza",
    "wraps", "tortilla", "pita", "naan", "ciabatta", "focaccia", "noedels",
    "mie", "bami", "bier", "paneermeel",
})  # fmt: skip

_VEGETARIAN_MARKERS = frozenset({"vegetarisch", "vega", "veggie"})
_VEGAN_MARKERS = frozenset({"vegan", "plantaardig"})
_LACTOSE_FREE_MARKERS = frozenset({"lactosevrij"})
_GLUTEN_FREE_MARKERS = frozenset({"glutenvrij"})

# Tokens that contain a keyword but are not what the keyword suggests.
_NOT_MEAT = frozenset({"vleestomaat", "vleestomaten"})
_PLANT_BASED_PREFIXES = (
    "soja", "haver", "amandel", "kokos", "rijst", "pinda", "noten", "cacao",
    "cashew",
)  # fmt: skip

_CUISINE_KEYWORDS: dict[Cuisine, frozenset[str]] = {
    Cuisine.MIDDLE_EASTERN: frozenset({
        "kikkererwten", "hummus", "humus", "falafel", "tahin", "tahini",
        "couscous", "bulgur", "aubergine", "granaatappel", "feta", "halloumi",
        "labneh", "pita", "zaatar", "sumak", "komijn", "dadels", "linzen",
        "munt", "pistache", "harissa", "freekeh", "shoarma",
    }),
    Cuisine.ITALIAN: frozenset({
        "pasta", "spaghetti", "penne", "fusilli", "tagliatelle", "lasagne",
        "ravioli", "tortellini", "gnocchi", "risotto", "pesto", "mozzarella",
        "parmezaan", "parmigiano", "burrata", "ricotta", "mascarpone", "pizza",
        "focaccia", "ciabatta", "prosciutto", "basilicum", "passata", "polenta",
    }),
    Cuisine.ASIAN: frozenset({
        "tofu", "tempeh", "sojasaus", "ketjap", "sambal", "noedels", "mie",
        "miso", "gember", "kokosmelk", "sushi", "nori", "wasabi", "paksoi",
        "tauge", "taugé", "sesamolie", "edamame", "kimchi", "bami", "nasi",
        "loempia", "wok",
    }),
    Cuisine.MEXICAN: frozenset({
        "tortilla", "wraps", "taco", "tacos", "burrito", "nachos", "salsa",
        "guacamole", "avocado", "jalapeno", "jalapeño", "kidneybonen",
        "chipotle", "enchilada", "fajita",
    }),
    Cuisine.INDIAN: frozenset({
        "curry", "masala", "naan", "dal", "paneer", "tikka", "korma",
        "chutney", "basmati", "kurkuma", "linzen", "tandoori", "biryani",
    }),
}  # fmt: skip


def tag_product(product_name: str) -> frozenset[str]:
    """Return the diet, allergen and cuisine tags for a product name."""
    tokens = _TOKEN_RE.findall(product_name.lower())
    tags: set[str] = set()

    is_vegan = _matches(tokens, _VEGAN_MARKERS)
    is_vegetarian = is_vegan or _matches(tokens, _VEGETARIAN_MARKERS)

    if not is_vegetarian:
        if _matches([t for t in tokens if t not in _NOT_MEAT], _MEAT):
            tags.add(Tag.MEAT)
        if _matches(tokens, _FISH):
            tags.add(Tag.FISH)
    if not is_vegan:
        animal_tokens = [t for t in tokens if not t.startswith(_PLANT_BASED_PREFIXES)]
        if _matches(animal_tokens, _DAIRY):
            tags.add(Tag.DAIRY)
        if _matches(tokens, _EGG):
            tags.add(Tag.EGG)
        if _matches(tokens, _HONEY):
            tags.add(Tag.HONEY)
    if _matches(tokens, _GLUTEN):
        tags.add(Tag.GLUTEN)

    if is_vegan:
        tags.add(Tag.VEGAN)
    elif is_vegetarian:
        tags.add(Tag.VEGETARIAN_LABEL)
    if is_vegetarian or not tags & {Tag.MEAT, Tag.FISH}:
        tags.add(Tag.VEGETARIAN)
    if _matches(tokens, _LACTOSE_FREE_MARKERS):
        tags.add(Tag.LACTOSE_FREE)
    if _matches(tokens, _GLUTEN_FREE_MARKERS):
        tags.add(Tag.GLUTEN_FREE)

    for cuisine, keywords in _CUISINE_KEYWORDS.items():
        if _matches(tokens, keywords):
            tags.add(cuisine)

    return frozenset(tags)


def passes_hard_filters(tags: frozenset[str], preferences: Preferences) -> bool:
    """Diet and allergy preferences exclude a deal outright; they never just lower it."""
    if preferences.diet is Diet.VEGETARIAN and Tag.VEGETARIAN not in tags:
        return False
    if preferences.diet is Diet.VEGAN and tags & {
        Tag.MEAT,
        Tag.FISH,
        Tag.DAIRY,
        Tag.EGG,
        Tag.HONEY,
        Tag.VEGETARIAN_LABEL,
    }:
        return False
    if preferences.lactose_free and Tag.DAIRY in tags and Tag.LACTOSE_FREE not in tags:
        return False
    if preferences.gluten_free and Tag.GLUTEN in tags and Tag.GLUTEN_FREE not in tags:
        return False
    return True


def relevance(tags: frozenset[str], preferences: Preferences) -> float:
    """How well a (diet-compatible) product fits the preferred cuisines, in [0, 1]."""
    if not preferences.cuisines:
        return 1.0
    if tags & preferences.cuisines:
        return 1.0
    return BASELINE_RELEVANCE


def _matches(tokens: Iterable[str], keywords: frozenset[str]) -> bool:
    return any(_token_matches(token, kw) for token in tokens for kw in keywords)


def _token_matches(token: str, keyword: str) -> bool:
    if token == keyword:
        return True
    if len(keyword) < _MIN_COMPOUND_LEN:
        return False
    return token.startswith(keyword) or token.endswith(keyword)
