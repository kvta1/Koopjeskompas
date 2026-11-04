from pathlib import Path

import pytest
from pydantic import ValidationError

from koopjeskompas.stores import load_stores

# Generous bounding box around the municipality of Leiden.
LEIDEN_LAT = (52.12, 52.19)
LEIDEN_LON = (4.43, 4.54)


def test_packaged_leiden_stores_are_valid() -> None:
    stores = load_stores()
    assert len(stores) >= 5
    assert {s.chain for s in stores} == {"AH"}
    assert len({s.name for s in stores}) == len(stores), "store names must be unique"
    for store in stores:
        assert LEIDEN_LAT[0] <= store.location.latitude <= LEIDEN_LAT[1], store.name
        assert LEIDEN_LON[0] <= store.location.longitude <= LEIDEN_LON[1], store.name
        assert store.address


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
