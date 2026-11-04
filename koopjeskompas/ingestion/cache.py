"""The parsed-deal cache: a JSON file per chain that stands in for a database (MVP)."""

from pathlib import Path

from pydantic import TypeAdapter

from koopjeskompas.domain.models import Deal

_DEALS = TypeAdapter(list[Deal])


def deals_path(data_dir: Path, chain: str) -> Path:
    return data_dir / "deals" / f"{chain.lower()}.json"


def save_deals(path: Path, deals: list[Deal]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_DEALS.dump_json(deals, indent=2))


def load_deals(path: Path) -> list[Deal]:
    return _DEALS.validate_json(path.read_bytes())
