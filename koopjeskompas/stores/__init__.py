"""Store lists, exported from OpenStreetMap and packaged (see the .overpassql files).

``koopjeskompas fetch-stores`` writes ``nl_ah.json`` from ``nl_ah.overpassql``.
"""

from importlib.resources import files
from pathlib import Path

from pydantic import TypeAdapter

from koopjeskompas.domain.models import Store

_STORES = TypeAdapter(list[Store])

LEIDEN_AH = files(__package__) / "leiden_ah.json"
NL_AH_QUERY = files(__package__) / "nl_ah.overpassql"


def load_stores(path: Path | None = None) -> list[Store]:
    """Load and validate a store list; defaults to the packaged Leiden AH stores."""
    source = path if path is not None else LEIDEN_AH
    return _STORES.validate_json(source.read_bytes())


def save_stores(path: Path, stores: list[Store]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_STORES.dump_json(stores, indent=2) + b"\n")
