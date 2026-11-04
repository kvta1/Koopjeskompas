from datetime import date
from decimal import Decimal
from pathlib import Path

from koopjeskompas.domain.models import Deal, RangeProduct
from koopjeskompas.ingestion.cache import deals_path, load_deals, save_deals


def test_deals_survive_a_round_trip(tmp_path: Path) -> None:
    deals = [
        Deal(
            chain="AH",
            product_name="AH Hummus naturel",
            normal_price=Decimal("2.29"),
            mechanic_string="3 voor 5.99",
            valid_from=date(2026, 10, 12),
            valid_to=date(2026, 10, 18),
        ),
        Deal(
            chain="AH",
            product_name="Kikkererwten",
            mechanic_string="25% korting",
            valid_from=date(2026, 10, 12),
            valid_to=date(2026, 10, 18),
        ),
        Deal(
            chain="AH",
            product_name="AH Yorkham van de versafdeling",
            mechanic_string="100 GRAM VOOR 1.99",
            valid_from=date(2026, 11, 2),
            valid_to=date(2026, 11, 8),
            products=(
                RangeProduct(
                    name="AH Yorkham",
                    normal_price=Decimal("3.49"),
                    normal_price_per_kg=Decimal("31.73"),
                ),
            ),
        ),
    ]
    path = deals_path(tmp_path, "AH")
    save_deals(path, deals)
    assert path == tmp_path / "deals" / "ah.json"
    assert load_deals(path) == deals
