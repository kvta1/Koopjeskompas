import re
from decimal import Decimal

from koopjeskompas.domain.models import Deal


class UnknownMechanicError(ValueError):
    pass


_FIXED_FRACTION_MECHANICS: dict[str, Decimal] = {
    "2e halve prijs": Decimal("0.25"),
    "2e gratis": Decimal("0.50"),
    "1+1 gratis": Decimal("0.50"),
    "2+1 gratis": Decimal(1) / Decimal(3),
    "3 voor 2": Decimal(1) / Decimal(3),
}
_PERCENT_RE = re.compile(r"(\d+)\s*%\s*korting")
_N_VOOR_PRICE_RE = re.compile(r"(\d+)\s*voor\s*€\s*(\d+(?:[.,]\d{1,2})?)")


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

    normalized = " ".join(mechanic.lower().split())

    if normalized in _FIXED_FRACTION_MECHANICS:
        return _FIXED_FRACTION_MECHANICS[normalized]

    if match := _PERCENT_RE.fullmatch(normalized):
        percent = Decimal(match.group(1))
        if percent > 100:
            raise UnknownMechanicError(mechanic)
        return percent / Decimal(100)

    if match := _N_VOOR_PRICE_RE.fullmatch(normalized):
        n = Decimal(match.group(1))
        if n == 0:
            raise UnknownMechanicError(mechanic)
        total = Decimal(match.group(2).replace(",", "."))
        return _fraction_from_prices(_require_normal_price(normal_price), total / n)

    raise UnknownMechanicError(mechanic)


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
