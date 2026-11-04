"""Store scoring (PLAN.md §6).

    deal_value(d)   = discount_fraction(d) × relevance(d, prefs)        ∈ [0, 1]
    basket_score(s) = Σ over the top-k deal values of the store's chain
    score(s)        = w_b · basket_score / k − w_d · min(distance / d_max, 1)

Only the top k deals count, so a chain with a huge promotion folder does not win
on volume alone. Stores further away than ``max_distance_km`` are left out.

A range deal counts once, valued at the median over its products that pass your
diet filters (see ``_score_range``).
"""

import heapq
from collections.abc import Iterable, Sequence
from datetime import date
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from koopjeskompas.domain.deal_mechanic import deal_discount, product_discount
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
    # For a range deal: how many of its products counted towards the median.
    products_counted: int = 0


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
        result = (
            _score_range(deal, preferences)
            if deal.products
            else _score_single(deal, preferences)
        )
        if result is not None and result.value > 0:
            scored.append(result)
    scored.sort(key=lambda s: s.value, reverse=True)
    return scored


def _score_single(deal: Deal, preferences: Preferences) -> ScoredDeal | None:
    tags = tag_product(deal.product_name, deal.category)
    if not passes_hard_filters(tags, preferences):
        return None
    discount = deal_discount(deal)
    if discount is None:
        return None
    rel = relevance(tags, preferences)
    return ScoredDeal(
        deal=deal,
        discount=float(discount),
        relevance=rel,
        value=deal_value(float(discount), rel),
    )


def _score_range(deal: Deal, preferences: Preferences) -> ScoredDeal | None:
    """Score a range deal by the median of the products you could actually buy.

    A product counts only if both its own name and the range name pass the hard
    filters, so a "kip" in either still blocks it. (They are tagged separately: a
    "plantaardig" in the range name must not vouch for every product in it.)
    Products without a determinable discount don't count either; if none are left,
    neither does the range. The median rather than the best product: a range
    shouldn't be scored by its one outlier.
    """
    range_tags = tag_product(deal.product_name, deal.category)
    if not passes_hard_filters(range_tags, preferences):
        return None
    discounts: list[float] = []
    relevances: list[float] = []
    values: list[float] = []
    for product in deal.products:
        tags = tag_product(product.name, deal.category)
        if not passes_hard_filters(tags, preferences):
            continue
        tags |= range_tags  # e.g. a cuisine named only in the range name
        discount = product_discount(deal, product)
        if discount is None:
            continue
        rel = relevance(tags, preferences)
        discounts.append(float(discount))
        relevances.append(rel)
        values.append(deal_value(float(discount), rel))
    if not values:
        return None
    return ScoredDeal(
        deal=deal,
        discount=median(discounts),
        relevance=median(relevances),
        value=median(values),
        products_counted=len(values),
    )


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
