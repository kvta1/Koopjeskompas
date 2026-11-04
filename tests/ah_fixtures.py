"""The captured AH responses in ``tests/fixtures/ah/``, shared by the parser and CLI tests.

One place that knows where they live, so a test module can move without breaking a
relative ``Path(__file__).parent / ...``.
"""

import json
from pathlib import Path
from typing import Any

AH_FIXTURES = Path(__file__).parent / "fixtures" / "ah"


def load_ah_fixture(name: str) -> Any:
    """The parsed JSON of one captured response, e.g. ``"metadata.json"``."""
    return json.loads((AH_FIXTURES / name).read_text())
