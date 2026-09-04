"""Test bootstrap.

The environment is pinned HERE, before any app module is imported, because
Settings reads .env and a developer's .env may say LIVE_LLM=true. That is a
fine thing to have on a laptop and a terrible thing to inherit in a test run:
the suite hung for minutes making real sphere calls the moment the flag
existed. Environment variables beat .env in pydantic-settings, so setting them
here isolates every test from whatever the repo checkout happens to contain.
"""
import os

os.environ["DEMO_MODE"] = "true"
os.environ["LIVE_LLM"] = "false"
os.environ.pop("SPHERE_APP_TOKEN", None)
os.environ["SPHERE_PLATFORM_APP_TOKEN"] = ""
os.environ["GITLAB_READ_TOKEN"] = ""

import json
from pathlib import Path

import pytest

from app.config import get_settings

get_settings.cache_clear()

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


@pytest.fixture()
def pipeline_state() -> dict:
    """A completed run's state, up to the point the PRD generator sees it."""
    from app.pipeline.graph import compiled_graph
    from app.pipeline.state import initial_state
    out = compiled_graph.invoke(initial_state(
        run_id=1, window_start="2026-08-27", window_end="2026-09-02",
        demo_mode=True, journey="pd_checkout",
        prev_window_start="2026-08-20", prev_window_end="2026-08-26"))
    # report_writer runs after the PRD node and rewrites artifacts into dicts;
    # hand the PRD node the shape it actually sees at its own point in the graph.
    return {**out, "artifacts": []}
