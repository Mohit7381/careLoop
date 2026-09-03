import json
from pathlib import Path

import pytest

from app.schemas.contracts import Snapshot

FIX = Path(__file__).parent.parent / "fixtures" / "pd_checkout"


@pytest.fixture()
def snapshot() -> Snapshot:
    return Snapshot(**json.loads((FIX / "snapshot.json").read_text()))


@pytest.fixture()
def cohort_cuts() -> dict:
    return json.loads((FIX / "cohort_cuts.json").read_text())


@pytest.fixture()
def reviews() -> list[dict]:
    return json.loads((FIX / "reviews_scrubbed.json").read_text())


@pytest.fixture()
def journey_cfg() -> dict:
    import yaml
    return yaml.safe_load((Path(__file__).parent.parent / "config/journeys/pd_checkout.yaml").read_text())
