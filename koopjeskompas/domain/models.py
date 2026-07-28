from pydantic import BaseModel
from datetime import date
from typing import Optional
from enum import Enum
from decimal import Decimal

class Deal(BaseModel):
    chain: str
    product_name: str
    # normal_price: Decimal
    # deal_price: Decimal
    mechanic_string: str | None = None
    valid_from: date
    valid_to: date

class Store(BaseModel):
    chain_name: str
    latitude: float
    longitude: float

class Diet(str, Enum):
    NONE = "none"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan" 

class Preferences(BaseModel):
    diet : Diet = Diet.NONE
    cuisines: set[str] = set()
    gluten_free: bool = False
    lactose_free: bool = False
