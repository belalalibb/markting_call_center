from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "config" / "examples"


@pytest.fixture(scope="session")
def example_blueprint_dicts() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(EXAMPLES.glob("activity_*.yaml")):
        out[p.stem] = yaml.safe_load(p.read_text())
    return out
