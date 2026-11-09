from pathlib import Path

import pytest
from pydantic import ValidationError

from koopjeskompas.domain.distance import haversine_km
from koopjeskompas.domain.models import Coordinates
from koopjeskompas.stores import load_stores

# Generous bounding box around the European Netherlands.
NL_LAT = (50.7, 53.6)
NL_LON = (3.3, 7.3)
LEIDEN_BREESTRAAT = Coordinates(latitude=52.1570015, longitude=4.4919905)


def test_packaged_stores_cover_the_netherlands() -> None:
    stores = load_stores()
    assert len(stores) > 900  # about 1,000 AHs; far fewer means a fetch went wrong
    assert {s.chain for s in stores} == {"AH"}
    for store in stores:
        assert NL_LAT[0] <= store.location.latitude <= NL_LAT[1], store.name
        assert NL_LON[0] <= store.location.longitude <= NL_LON[1], store.name
        assert store.name.startswith("AH ")
    # Names repeat across towns ("AH Dorpsstraat"); name and address together don't.
    keys = [(s.name, s.address) for s in stores]
    assert len(set(keys)) == len(keys)


def test_packaged_stores_include_leidens() -> None:
    stores = load_stores()
    nearest = min(stores, key=lambda s: haversine_km(s.location, LEIDEN_BREESTRAAT))
    assert nearest.name == "AH Breestraat"
    assert any(s.name == "AH XL Bevrijdingsplein" for s in stores)


def test_load_stores_from_path(tmp_path: Path) -> None:
    path = tmp_path / "stores.json"
    path.write_text(
        '[{"chain": "Jumbo", "name": "Jumbo X",'
        ' "location": {"latitude": 52.0, "longitude": 4.0}}]'
    )
    (store,) = load_stores(path)
    assert store.name == "Jumbo X"
    assert store.address is None


def test_load_stores_rejects_invalid_data(tmp_path: Path) -> None:
    path = tmp_path / "stores.json"
    path.write_text('[{"chain": "AH", "name": "Nowhere"}]')
    with pytest.raises(ValidationError):
        load_stores(path)
