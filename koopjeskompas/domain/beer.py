"""Beer deals: which deals are beer, how each product is packed, and its price per litre.

Pure, like the rest of the domain. The beer section (PLAN.md §9.5) compares beer the way
biernet.nl does: per product, by price per litre, in three groups (crates, cans,
bottles). A deal like "Alle Heineken multipacks: 25% korting" is a range of products,
from a single 33 cl can to a crate; each becomes its own ``BeerOffer``.

What a product says about itself varies by chain, as seen in November 2026:
Jumbo mostly names it ("Stella Artois Krat 24x330ML", "Leffe Flessen 6 x 30 cl"), AH
sometimes ("bier krat", "pilsener bier bl.", "pils 24fl", "draaidop") and often only
gives a size ("6 x 0,33 l"). So an explicit word wins, and otherwise the Dutch
conventions decide (decided 2026-11-10): 24 bottles of 25-30 cl are a crate, 25, 30,
45 and 75 cl are bottles, 33 and 50 cl are cans. That last one is a guess some
Belgian 33 cl bottles get wrong; the page always shows the exact pack, so a wrong
guess is visible.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from koopjeskompas.domain.deal_mechanic import product_discount
from koopjeskompas.domain.models import Deal, RangeProduct


class Packaging(StrEnum):
    CRATE = "krat"
    CAN = "blik"
    BOTTLE = "fles"


@dataclass(frozen=True)
class Pack:
    """How much beer a product holds: ``units`` of ``unit_litres`` each, if known."""

    litres: Decimal
    units: int | None = None
    unit_litres: Decimal | None = None


@dataclass(frozen=True)
class BeerOffer:
    chain: str
    product: str  # e.g. "Hertog Jan Pilsener bier krat"
    deal: str  # the deal it's part of, e.g. "Alle Hertog Jan, Amstel, ... multipacks"
    mechanic: str | None  # "25% KORTING"
    packaging: Packaging
    pack: Pack
    size_text: str  # as the chain wrote it: "24 x 30 cl"
    normal_price: Decimal
    deal_price: Decimal
    price_per_litre: Decimal  # with the deal
    discount: Decimal
    alcohol_free: bool
    valid_from: date
    valid_to: date


# --- is it beer? ------------------------------------------------------------

_BEER_WORDS = (
    r"bier|bieren|beer|pils|pilsener|pilsner|lager|ipa|neipa|weizen|weizener|"
    r"witbier|tripel|triple|dubbel|bock|bok|bockbier|bokbier|radler|stout|porter|"
    r"abdijbier|speciaalbier|krat|blond"
)
# Brands that sell (nearly) only beer, for deals named after the brand alone:
# "Texels", "Jopen, Uiltje, Brewdog of TwoChefs", "Leffe of Kasteelbier".
_BEER_BRANDS = (
    r"heineken|amstel|bavaria|hertog jan|warsteiner|grolsch|brand|jupiler|leffe|"
    r"kasteel|karmeliet|texels|jopen|uiltje|brewdog|two ?chefs|alfa|stella artois|"
    r"corona|peroni|veltins|grimbergen|la chouffe|affligem|duvel|westmalle|"
    r"la trappe|palm|hoegaarden|desperados|bud|budweiser|kornuit|gulpener|"
    r"lindeboom|dommelsch|hollandia|st\.? ?pierre|brugse zot|lowlander|"
    r"moersleutel|frontaal|weihenstephan|erdinger|paulaner|franziskaner|"
    r"liefmans|chimay|carlsberg|tuborg|guinness|perlenbacher|kronenbacher"
)
# Wine and spirits share beer's shelf ("Bier en wijn"); these words rule a name out.
_NOT_BEER = (
    r"wijn|wijnen|wine|whisky|whiskey|vodka|rum|gin|jenever|likeur|port|sherry|"
    r"cava|prosecco|champagne|cider|merlot|cabernet|chardonnay|sauvignon|pinot|"
    r"rioja|tempranillo|primitivo|garganega|shiraz|malbec"
)
# Dutch glues words together ("herfstbokbieren", "dubbelbock"), so the words that end
# such compounds count at the end of a word, not only as a word of their own.
_BEER = re.compile(
    rf"\b(?:{_BEER_WORDS}|{_BEER_BRANDS})\b|(?:bier|bieren|bock|bok)\b",
    re.IGNORECASE,
)
_NOT = re.compile(rf"\b(?:{_NOT_BEER})\b", re.IGNORECASE)


def is_beer(name: str) -> bool:
    """Whether a deal or product name is beer: a beer word or brand, and no wine or
    spirits word ("Amstel Rosé bier" is beer; "Diverse prijswinnende wijnen" isn't)."""
    return bool(_BEER.search(name)) and not _NOT.search(name)


_ALCOHOL_FREE = re.compile(
    r"\b0[.,]0\b|0[.,]0\s*%|alcoholvrij|alkoholfrei|alcohol-free|non-alcoholic|"
    r"<\s*0[.,]5\s*%|\b0[.,][0-5]\s*%",
    re.IGNORECASE,
)


def is_alcohol_free(name: str) -> bool:
    """0.0, "alcoholvrij", or at most 0.5% (the Dutch limit for alcohol-free)."""
    return bool(_ALCOHOL_FREE.search(name))


# --- how much, and how is it packed? ----------------------------------------

_LITRES = {"ml": Decimal("0.001"), "cl": Decimal("0.01"), "l": Decimal(1)}
_AMOUNT = r"(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\b"
_MULTI = re.compile(
    rf"(\d+)\s*[x×]\s*{_AMOUNT}", re.IGNORECASE
)  # "6 x 0,33 l", "24x330ML"
_SINGLE = re.compile(_AMOUNT, re.IGNORECASE)  # "300 ml", "1,8 l"
_COUNT = re.compile(
    r"\b(\d+)\s*-?\s*(?:pack|krat|fl|stuks)\b", re.IGNORECASE
)  # "6-pack", "24fl"


def _litres(number: str, unit: str) -> Decimal:
    return Decimal(number.replace(",", ".")) * _LITRES[unit.lower()]


def parse_pack(text: str) -> Pack | None:
    """The volume in a product's size and title: "24 x 30 cl" is 24 × 0.3 l.

    Give the size first and the title after it ("1,8 l Heineken Witpils 6-pack"): AH
    often puts the count in the title and the size in a field of its own. A lone size
    is one unit, unless a count says otherwise; then a size over a litre is the whole
    pack (6 × 0.3 l) and a smaller one is each unit. Over a litre with no count, the
    number of units is unknown ("bier krat", "7,2 l").
    """
    if match := _MULTI.search(text):
        units, unit = int(match[1]), _litres(match[2], match[3])
        return Pack(litres=units * unit, units=units, unit_litres=unit)
    match = _SINGLE.search(text)
    if match is None:
        return None
    size = _litres(match[1], match[2])
    count = _COUNT.search(text)
    if count is None:
        if size > 1:
            return Pack(litres=size)
        return Pack(litres=size, units=1, unit_litres=size)
    units = int(count[1])
    if size > 1:
        return Pack(litres=size, units=units, unit_litres=size / units)
    return Pack(litres=units * size, units=units, unit_litres=size)


_CRATE = re.compile(r"\bkrat\b|\b\d+\s*fl\b", re.IGNORECASE)  # "krat", "24fl"
_CAN = re.compile(r"\bblik(?:ken)?\b|\bbl\.?(?=\s|$)|\bcan\b", re.IGNORECASE)  # "bl."
_BOTTLE = re.compile(r"\bfles(?:sen)?\b|\bdraaidop\b|\bbeugel\b", re.IGNORECASE)
_MULTIPACK = re.compile(r"\b\d+\s*-?\s*pack\b|\btray\b", re.IGNORECASE)
_BOTTLE_SIZES = {Decimal("0.25"), Decimal("0.3"), Decimal("0.45"), Decimal("0.75")}


def packaging(text: str, pack: Pack) -> Packaging | None:
    """Crate, can or bottle: an explicit word first, then Dutch conventions by size."""
    if _CRATE.search(text):
        return Packaging.CRATE
    if _CAN.search(text):
        return Packaging.CAN
    if _BOTTLE.search(text):
        return Packaging.BOTTLE
    unit = pack.unit_litres
    if unit is None:
        return None
    unit = unit.normalize()
    if unit in {Decimal("0.25"), Decimal("0.3")} and (pack.units or 0) >= 20:
        # A crate of bottles, unless it's sold as a pack: "24-pack" is a tray.
        if not _MULTIPACK.search(text):
            return Packaging.CRATE
    if unit in _BOTTLE_SIZES:
        return Packaging.BOTTLE
    if unit in {Decimal("0.33"), Decimal("0.5"), Decimal("0.44"), Decimal("0.355")}:
        return Packaging.CAN  # the guess: some Belgian 33 cl bottles land here
    return None


# --- the offers -------------------------------------------------------------


def beer_offers(deals: list[Deal], today: date) -> list[BeerOffer]:
    """Every beer product on offer ``today``, cheapest per litre first.

    A product is kept when its packaging and volume are known and the deal's discount
    can be worked out for it.
    """
    offers = []
    for deal in deals:
        if not deal.is_active_on(today) or not is_beer(deal.product_name):
            continue
        for product in deal.products:
            offer = _offer(deal, product)
            if offer is not None:
                offers.append(offer)
    return sorted(offers, key=lambda o: (o.price_per_litre, o.product))


def _offer(deal: Deal, product: RangeProduct) -> BeerOffer | None:
    # A product of a beer deal is beer unless its own name says wine or spirits.
    if _NOT.search(product.name):
        return None
    size_text = product.unit_size or ""
    text = f"{size_text} {product.name}"  # the size first: see parse_pack
    pack = parse_pack(text)
    if pack is None and product.normal_price_per_litre is not None:
        # No size written anywhere (Jumbo's "xx"): the price per litre still says it.
        pack = Pack(litres=product.normal_price / product.normal_price_per_litre)
    if pack is None or pack.litres <= 0:
        return None
    kind = packaging(text, pack)
    discount = product_discount(deal, product)
    if kind is None or discount is None:
        return None
    deal_price = (product.normal_price * (1 - discount)).quantize(Decimal("0.01"))
    return BeerOffer(
        chain=deal.chain,
        product=product.name,
        deal=deal.product_name,
        mechanic=deal.mechanic_string,
        packaging=kind,
        pack=pack,
        size_text=size_text or _size_in(product.name),
        normal_price=product.normal_price,
        deal_price=deal_price,
        price_per_litre=(deal_price / pack.litres).quantize(Decimal("0.01")),
        discount=discount,
        alcohol_free=is_alcohol_free(product.name),
        valid_from=deal.valid_from,
        valid_to=deal.valid_to,
    )


def _size_in(name: str) -> str:
    """The size as written in a product's name, for display: "6 x 33 cl"."""
    match = _MULTI.search(name) or _SINGLE.search(name)
    return match[0] if match else ""
