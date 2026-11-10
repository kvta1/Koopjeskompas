from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Diet(StrEnum):
    NONE = "none"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"


class Cuisine(StrEnum):
    MIDDLE_EASTERN = "middle_eastern"
    ITALIAN = "italian"
    ASIAN = "asian"
    MEXICAN = "mexican"
    INDIAN = "indian"


class Coordinates(BaseModel):
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RangeProduct(BaseModel):
    """One product of a range deal ("Alle AH Verse pizza's"), with its own price."""

    model_config = ConfigDict(frozen=True)

    name: str
    normal_price: Decimal = Field(gt=0)
    normal_price_per_kg: Decimal | None = Field(default=None, gt=0)
    # How it's sold, as the chain writes it: "6 x 0,33 l", "24 x 30 cl", "300 ml".
    unit_size: str | None = None
    # The volume in litres, when the chain's own price data gives it (Jumbo: its price
    # per litre). More reliable than a title: "Corona Cero 330 ml" holds 1.32 l.
    litres: Decimal | None = Field(default=None, gt=0)


class Deal(BaseModel):
    """A national promotion of one chain; every store of that chain carries it.

    A range deal ("2 voor €12 on all fresh pizzas") lists its ``products``: the range
    has no single normal price, so each product's discount is worked out separately.
    """

    model_config = ConfigDict(frozen=True)

    chain: str
    product_name: str
    # The chain's own product category, e.g. "Vlees". Helps tagging when the name
    # alone says nothing ("Wahid" is a halal meat brand).
    category: str | None = None
    normal_price: Decimal | None = Field(default=None, gt=0)
    # Needed for per-weight mechanics ("100 gram voor 1.39"): the pack price can't be
    # compared with a price per 100 g, the normal price per kilo can.
    normal_price_per_kg: Decimal | None = Field(default=None, gt=0)
    deal_price: Decimal | None = Field(default=None, ge=0)
    mechanic_string: str | None = None
    valid_from: date
    valid_to: date
    # A tuple, not a list: a frozen model with a list field could still be mutated.
    products: tuple[RangeProduct, ...] = ()

    @model_validator(mode="after")
    def _check_validity_window(self) -> Self:
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be before valid_from")
        return self

    def is_active_on(self, day: date) -> bool:
        return self.valid_from <= day <= self.valid_to


class Store(BaseModel):
    model_config = ConfigDict(frozen=True)

    chain: str
    name: str
    location: Coordinates
    address: str | None = None


class Preferences(BaseModel):
    model_config = ConfigDict(frozen=True)

    diet: Diet = Diet.NONE
    cuisines: frozenset[Cuisine] = frozenset()
    gluten_free: bool = False
    lactose_free: bool = False
