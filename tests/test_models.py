from koopjeskompas.domain.models import Deal, Store, Preferences, Diet
from datetime import date



def test_instantiate_deal():
    deal = Deal(
        chain="Jumbo",
        product_name="appel",
        # normal_price=1.0,
        # deal_price=0.5,
        mechanic_string="2e halve prijs",
        valid_from=date(year=2026, month=7, day=21),
        valid_to=date(year=2026, month=7, day=25)
    )
    assert deal

def test_instantiate_store():
    store = Store(
        chain_name="Jumbo",
        latitude=52.009066,
        longitude=4.364620
    )
    assert store

def test_instantiate_preferences():
    preference = Preferences(
        diet=Diet("vegetarian"),
        cuisines=set("asian"),
    )
    assert preference