"""This week's beer as AH and Jumbo listed it, captured on 2026-11-10.

``ah_range_<segment>.json``: AH's lookups of four beer ranges (Hertog Jan/Amstel/
Bavaria/Warsteiner, herfstbok, Heineken, Leffe/Tripel Karmeliet).
``jumbo_promotion_<id>.json``: the page data of three Jumbo beer promotions (pils,
Leffe/Kasteel, Grolsch specials).
"""

import json
from pathlib import Path
from typing import Any

BEER_FIXTURES = Path(__file__).parent / "fixtures" / "beer"


def ah_range(segment_id: int) -> Any:
    return json.loads((BEER_FIXTURES / f"ah_range_{segment_id}.json").read_text())


def jumbo_promotion_data(promotion_id: str) -> str:
    """The saved page data, as JumboClient writes it (``nuxt.script_json``)."""
    return (BEER_FIXTURES / f"jumbo_promotion_{promotion_id}.json").read_text()
