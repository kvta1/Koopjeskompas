"""The parsed-deal cache: a JSON file per chain that stands in for a database (MVP)."""

from pathlib import Path

from pydantic import TypeAdapter

from koopjeskompas.chains import CHAINS
from koopjeskompas.domain.models import Deal

_DEALS = TypeAdapter(list[Deal])


def deals_path(data_dir: Path, chain: str) -> Path:
    return data_dir / "deals" / f"{chain.lower()}.json"


def save_deals(path: Path, deals: list[Deal]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_DEALS.dump_json(deals, indent=2))


def load_deals(path: Path) -> list[Deal]:
    return _DEALS.validate_json(path.read_bytes())


def load_snapshots(data_dir: Path) -> dict[str, list[Deal]]:
    """Every registered chain's cached deals, by chain name.

    A chain without a snapshot is left out rather than an error: one chain whose
    fetch failed shouldn't take the others down. No snapshot at all gives ``{}``.
    """
    return {
        chain.name: load_deals(path)
        for chain in CHAINS
        if (path := deals_path(data_dir, chain.name)).exists()
    }
