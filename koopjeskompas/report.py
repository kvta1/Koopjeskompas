"""Plain-text rendering of a store ranking for the terminal."""

from koopjeskompas.domain.scoring import ScoredDeal, StoreRanking


def format_ranking(rankings: list[StoreRanking]) -> str:
    if not rankings:
        return "No stores within range."
    blocks = [_format_store(i, r) for i, r in enumerate(rankings, start=1)]
    return "\n\n".join(blocks)


def _format_store(position: int, ranking: StoreRanking) -> str:
    store = ranking.store
    where = f" ({store.address})" if store.address else ""
    header = (
        f"{position}. {store.name}{where}"
        f" | {ranking.distance_km:.1f} km | score {ranking.score:.3f}"
    )
    if not ranking.top_deals:
        return f"{header}\n     no matching deals"
    return "\n".join([header, *(_format_deal(d) for d in ranking.top_deals)])


def _format_deal(scored: ScoredDeal) -> str:
    mechanic = scored.deal.mechanic_string or "deal price"
    return f"   {scored.discount:4.0%}  {scored.deal.product_name}  [{mechanic}]"
