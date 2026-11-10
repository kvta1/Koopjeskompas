"""Store lists, exported from OpenStreetMap and packaged (see the .overpassql files).

``koopjeskompas fetch-stores`` writes ``nl_stores.json``: every store of every chain in
``koopjeskompas/chains.py``, from one OpenStreetMap query (``osm.overpass_query``).
"""

from importlib.resources import files
from pathlib import Path

from pydantic import TypeAdapter

from koopjeskompas.domain.models import Store

_STORES = TypeAdapter(list[Store])

NL_STORES = files(__package__) / "nl_stores.json"


def load_stores(path: Path | None = None) -> list[Store]:
    """Load and validate a store list; defaults to every known chain's Dutch stores."""
    source = path if path is not None else NL_STORES
    return _STORES.validate_json(source.read_bytes())


def save_stores(path: Path, stores: list[Store]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_STORES.dump_json(stores, indent=2) + b"\n")
