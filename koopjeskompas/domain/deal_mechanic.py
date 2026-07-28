from decimal import Decimal
import re

_FIXED_FRACTION_MECHANICS: dict[str, Decimal] = {
    "2e halve prijs": Decimal("0.25"),
    "2e gratis": Decimal("0.50"),
    "1+1 gratis": Decimal("0.50"),
    "3 voor 2": Decimal(1) / Decimal(3),
}
_PERCENT_RE = re.compile(r"(\d+)%\s*korting")
_N_VOOR_PRICE_RE = re.compile(r"(\d+)\s*voor\s*€\s*([\d.,]+)")


def parse_deal_mechanic(mechanic: str, normal_price: Decimal, deal_price: Decimal) -> Decimal:
    """Returns a discount_fraction in [0, 1]"""
    if normal_price <= 0:
        raise ValueError("normal_price must be positive")
    
    if mechanic is None:
        if deal_price is None:
            raise ValueError("deal_price is required when mechanic is None")
        return _fraction_from_prices(normal_price, deal_price)
    
    normalized = mechanic.strip().lower()

    if normalized in _FIXED_FRACTION_MECHANICS:
        return _FIXED_FRACTION_MECHANICS[normalized]

    if match := _PERCENT_RE.fullmatch(normalized):
        return Decimal(match.group(1) / Decimal(100))
    
    if match := _N_VOOR_PRICE_RE.fullmatch(normalized):
        n = Decimal(match.group(1))
        total = Decimal(match.group(2).replace(",", "."))
        return _fraction_from_prices(normal_price, total / n)

    raise UnknownMechanicError(mechanic)
    
    
    

def _fraction_from_prices(normal_price: Decimal, deal_price: Decimal) -> Decimal:
    fraction = deal_price/normal_price
    return fraction

class UnknownMechanicError(ValueError):
    pass