"""Hardcoded store lists, exported once from OpenStreetMap (see the .overpassql files)."""

from importlib.resources import files
from pathlib import Path

from pydantic import TypeAdapter

from koopjeskompas.domain.models import Store

_STORES = TypeAdapter(list[Store])

LEIDEN_AH = files(__package__) / "leiden_ah.json"


def load_stores(path: Path | None = None) -> list[Store]:
    """Load and validate a store list; defaults to the packaged Leiden AH stores."""
    source = path if path is not None else LEIDEN_AH
    return _STORES.validate_json(source.read_bytes())
