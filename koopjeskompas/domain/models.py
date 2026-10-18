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


class Deal(BaseModel):
    """A national promotion of one chain; every store of that chain carries it."""

    model_config = ConfigDict(frozen=True)

    chain: str
    product_name: str
    normal_price: Decimal | None = Field(default=None, gt=0)
    deal_price: Decimal | None = Field(default=None, ge=0)
    mechanic_string: str | None = None
    valid_from: date
    valid_to: date

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


class Preferences(BaseModel):
    model_config = ConfigDict(frozen=True)

    diet: Diet = Diet.NONE
    cuisines: frozenset[Cuisine] = frozenset()
    gluten_free: bool = False
    lactose_free: bool = False
