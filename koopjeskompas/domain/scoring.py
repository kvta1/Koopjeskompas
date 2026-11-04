"""Store scoring (PLAN.md §6).

    deal_value(d)   = discount_fraction(d) × relevance(d, prefs)        ∈ [0, 1]
    basket_score(s) = Σ over the top-k deal values of the store's chain
    score(s)        = w_b · basket_score / k − w_d · min(distance / d_max, 1)

Only the top k deals count, so a chain with a huge promotion folder does not win
on volume alone. Stores further away than ``max_distance_km`` are left out.
"""

import heapq
from collections.abc import Iterable, Sequence
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from koopjeskompas.domain.deal_mechanic import deal_discount
from koopjeskompas.domain.distance import haversine_km
from koopjeskompas.domain.models import Coordinates, Deal, Preferences, Store
from koopjeskompas.domain.tagging import passes_hard_filters, relevance, tag_product


class ScoringWeights(BaseModel):
    model_config = ConfigDict(frozen=True)

    top_k: int = Field(default=10, ge=1)
    basket_weight: float = Field(default=1.0, ge=0)
    distance_weight: float = Field(default=0.4, ge=0)
    max_distance_km: float = Field(default=5.0, gt=0)


class ScoredDeal(BaseModel):
    model_config = ConfigDict(frozen=True)

    deal: Deal
    discount: float
    relevance: float
    value: float


class StoreRanking(BaseModel):
    model_config = ConfigDict(frozen=True)

    store: Store
    score: float
    basket_score: float
    distance_km: float
    top_deals: tuple[ScoredDeal, ...]


def deal_value(discount: float, relevance: float) -> float:
    if not (0 <= discount <= 1 and 0 <= relevance <= 1):
        raise ValueError("discount and relevance must be in [0, 1]")
    return discount * relevance


def basket_score(values: Iterable[float], top_k: int) -> float:
    return sum(heapq.nlargest(top_k, values))


def store_score(basket: float, distance_km: float, weights: ScoringWeights) -> float:
    distance_penalty = min(distance_km / weights.max_distance_km, 1.0)
    return (
        weights.basket_weight * basket / weights.top_k
        - weights.distance_weight * distance_penalty
    )


def score_deals(
    deals: Iterable[Deal], preferences: Preferences, today: date
) -> list[ScoredDeal]:
    """Score the active, diet-compatible deals, best first.

    Deals whose discount cannot be determined are skipped rather than guessed.
    """
    scored = []
    for deal in deals:
        if not deal.is_active_on(today):
            continue
        tags = tag_product(deal.product_name, deal.category)
        if not passes_hard_filters(tags, preferences):
            continue
        discount = deal_discount(deal)
        if discount is None:
            continue
        rel = relevance(tags, preferences)
        value = deal_value(float(discount), rel)
        if value > 0:
            scored.append(
                ScoredDeal(
                    deal=deal, discount=float(discount), relevance=rel, value=value
                )
            )
    scored.sort(key=lambda s: s.value, reverse=True)
    return scored


def rank_stores(
    stores: Sequence[Store],
    deals: Iterable[Deal],
    preferences: Preferences,
    location: Coordinates,
    today: date,
    weights: ScoringWeights = ScoringWeights(),
) -> list[StoreRanking]:
    """Rank the stores within ``weights.max_distance_km`` of ``location``, best first."""
    deals_by_chain: dict[str, list[Deal]] = {}
    for deal in deals:
        deals_by_chain.setdefault(deal.chain.casefold(), []).append(deal)

    # Deals are national per chain, so score them once per chain, not per store.
    top_deals_by_chain = {
        chain: tuple(score_deals(chain_deals, preferences, today)[: weights.top_k])
        for chain, chain_deals in deals_by_chain.items()
    }

    rankings = []
    for store in stores:
        distance = haversine_km(location, store.location)
        if distance > weights.max_distance_km:
            continue
        top_deals = top_deals_by_chain.get(store.chain.casefold(), ())
        basket = basket_score((d.value for d in top_deals), weights.top_k)
        rankings.append(
            StoreRanking(
                store=store,
                score=store_score(basket, distance, weights),
                basket_score=basket,
                distance_km=distance,
                top_deals=top_deals,
            )
        )
    rankings.sort(key=lambda r: (-r.score, r.distance_km, r.store.name))
    return rankings
