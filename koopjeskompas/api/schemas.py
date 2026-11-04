"""The HTTP contract: request and response models of the API.

These are deliberately separate from the domain models. The domain can change shape
(a new field on ``Deal``, say) without silently changing what API clients receive, and
the API can present things differently (a flat ``mechanic`` text, coordinates as
``lat``/``lon``) without the domain having to know.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from koopjeskompas.domain.models import Cuisine, Diet
from koopjeskompas.domain.scoring import ScoredDeal, ScoringWeights, StoreRanking

_DEFAULTS = ScoringWeights()


class _ApiModel(BaseModel):
    # Reject unknown fields: a typo like "cuisine" instead of "cuisines" should be an
    # error, not a request that silently ignores the user's preference.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Location(_ApiModel):
    lat: float = Field(ge=-90, le=90, examples=[52.1664])
    lon: float = Field(ge=-180, le=180, examples=[4.4817])


class RankRequest(_ApiModel):
    location: Location
    diet: Diet = Field(
        default=Diet.NONE,
        description="A hard filter: non-matching deals are excluded, not ranked lower.",
    )
    cuisines: list[Cuisine] = Field(default=[], examples=[["middle_eastern"]])
    gluten_free: bool = False
    lactose_free: bool = False
    radius_km: float = Field(default=_DEFAULTS.max_distance_km, gt=0, le=50)
    top_k: int = Field(
        default=_DEFAULTS.top_k,
        ge=1,
        le=50,
        description="How many of a store's best deals count towards its score.",
    )
    distance_weight: float = Field(
        default=_DEFAULTS.distance_weight,
        ge=0,
        le=10,
        description="How much distance counts against a store; 0 ignores distance.",
    )


class StoreOut(_ApiModel):
    chain: str
    name: str
    address: str | None
    lat: float
    lon: float


class DealOut(_ApiModel):
    product_name: str
    category: str | None
    mechanic: str | None = Field(
        description='The chain\'s own text, e.g. "2 VOOR 4.00"'
    )
    discount: float = Field(description="Share of the normal price saved, 0–1")
    relevance: float = Field(description="Fit with the preferred cuisines, 0–1")
    value: float = Field(
        description=(
            "What the deal is worth: discount × relevance, or for a range deal the "
            "median of its products' values"
        )
    )
    products_counted: int = Field(
        description="For a range deal, the products its median is taken over; else 0"
    )
    valid_from: date
    valid_to: date

    @classmethod
    def from_scored(cls, scored: ScoredDeal) -> "DealOut":
        deal = scored.deal
        return cls(
            product_name=deal.product_name,
            category=deal.category,
            mechanic=deal.mechanic_string,
            discount=scored.discount,
            relevance=scored.relevance,
            value=scored.value,
            products_counted=scored.products_counted,
            valid_from=deal.valid_from,
            valid_to=deal.valid_to,
        )


class RankedStore(_ApiModel):
    rank: int = Field(ge=1)
    store: StoreOut
    score: float
    basket_score: float = Field(description="Sum of the values of the top deals")
    distance_km: float
    top_deals: list[DealOut]

    @classmethod
    def from_ranking(cls, rank: int, ranking: StoreRanking) -> "RankedStore":
        store = ranking.store
        return cls(
            rank=rank,
            store=StoreOut(
                chain=store.chain,
                name=store.name,
                address=store.address,
                lat=store.location.latitude,
                lon=store.location.longitude,
            ),
            score=ranking.score,
            basket_score=ranking.basket_score,
            distance_km=ranking.distance_km,
            top_deals=[DealOut.from_scored(d) for d in ranking.top_deals],
        )


class RankResponse(_ApiModel):
    ranked_on: date = Field(description="Only deals active on this day count")
    stores: list[RankedStore]


class Health(_ApiModel):
    status: str
