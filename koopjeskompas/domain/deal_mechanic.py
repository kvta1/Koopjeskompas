import re
from decimal import Decimal

from koopjeskompas.domain.models import Deal


class UnknownMechanicError(ValueError):
    pass


_FIXED_FRACTION_MECHANICS: dict[str, Decimal] = {
    "2e halve prijs": Decimal("0.25"),
    "2e gratis": Decimal("0.50"),
    "3 voor 2": Decimal(1) / Decimal(3),
}
# "1+1 gratis", "2 + 3 GRATIS": pay for n, get m more free.
_PLUS_FREE_RE = re.compile(r"(?P<paid>\d+)\+(?P<free>\d+) gratis")
_PERCENT_RE = re.compile(r"(\d+)\s*%\s*korting")
# A price: "€5", "€ 4.50", or AH's bare "5.99". Without a euro sign the price needs
# decimals, otherwise "3 voor 2" (buy three, pay two) would read as three for €2.
_PRICE = r"(?:€\s*(?P<euro>\d+(?:[.,]\d{1,2})?)|(?P<bare>\d+[.,]\d{1,2}))"
# "2 voor €5", "3 VOOR 5.99", "4 stapelen voor 2.49" (buy 4 for €2.49), or just
# "voor 0.99" (one item for €0.99).
_N_VOOR_PRICE_RE = re.compile(rf"(?:(?P<n>\d+)\s*(?:stapelen\s*)?)?voor\s*{_PRICE}")
# "1 euro korting", "€1,50 korting", "2.50 korting": a fixed amount off the normal
# price. A bare number needs decimals, so it can't be confused with a percentage.
_AMOUNT_OFF_RE = re.compile(
    rf"(?:{_PRICE}|(?P<amount>\d+(?:[.,]\d{{1,2}})?)\s*euro)\s*korting"
)


def parse_deal_mechanic(
    mechanic: str | None,
    normal_price: Decimal | None = None,
    deal_price: Decimal | None = None,
) -> Decimal:
    """Normalize a Dutch deal mechanic into a discount fraction in [0, 1].

    The fraction is the share of the normal price you save: "25% korting" -> 0.25,
    "2e halve prijs" -> 0.25 (half off one of two items). Mechanics defined by a
    price ("2 voor €5", or no mechanic but a deal price) need ``normal_price``.
    """
    if normal_price is not None and normal_price <= 0:
        raise ValueError("normal_price must be positive")

    if mechanic is None or not mechanic.strip():
        if deal_price is None:
            raise ValueError("deal_price is required when there is no mechanic")
        return _fraction_from_prices(_require_normal_price(normal_price), deal_price)

    normalized = re.sub(r"\s*\+\s*", "+", " ".join(mechanic.lower().split()))

    if normalized in _FIXED_FRACTION_MECHANICS:
        return _FIXED_FRACTION_MECHANICS[normalized]

    if match := _PLUS_FREE_RE.fullmatch(normalized):
        paid, free = int(match["paid"]), int(match["free"])
        if paid == 0:
            raise UnknownMechanicError(mechanic)
        return Decimal(free) / Decimal(paid + free)

    if match := _PERCENT_RE.fullmatch(normalized):
        percent = Decimal(match.group(1))
        if percent > 100:
            raise UnknownMechanicError(mechanic)
        return percent / Decimal(100)

    if match := _N_VOOR_PRICE_RE.fullmatch(normalized):
        n = Decimal(match["n"] or 1)
        if n == 0:
            raise UnknownMechanicError(mechanic)
        total = _matched_price(match)
        return _fraction_from_prices(_require_normal_price(normal_price), total / n)

    if match := _AMOUNT_OFF_RE.fullmatch(normalized):
        normal = _require_normal_price(normal_price)
        deal = max(Decimal(0), normal - _matched_price(match))
        return _fraction_from_prices(normal, deal)

    raise UnknownMechanicError(mechanic)


def _matched_price(match: re.Match[str]) -> Decimal:
    groups = match.groupdict()
    price = groups["euro"] or groups["bare"] or groups.get("amount")
    if price is None:  # unreachable: every regex alternative captures a price
        raise UnknownMechanicError(match.string)
    return Decimal(price.replace(",", "."))


def deal_discount(deal: Deal) -> Decimal | None:
    """Discount fraction of a deal, or None if it cannot be determined."""
    try:
        return parse_deal_mechanic(
            deal.mechanic_string, deal.normal_price, deal.deal_price
        )
    except ValueError:
        return None


def _require_normal_price(normal_price: Decimal | None) -> Decimal:
    if normal_price is None:
        raise ValueError("normal_price is required for price-based mechanics")
    return normal_price


def _fraction_from_prices(normal_price: Decimal, deal_price: Decimal) -> Decimal:
    """Share of the normal price saved; 0 if the 'deal' is not actually cheaper."""
    if deal_price < 0:
        raise ValueError("deal_price must not be negative")
    saving = (normal_price - deal_price) / normal_price
    return max(Decimal(0), saving)
