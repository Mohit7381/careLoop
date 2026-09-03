"""
Agent 1 — Fetcher. OWNER: Alief.

Deterministic, no LLM. Runs the fixed Metabase query pack (read-only,
Redshift DB 39) for the requested window AND the previous window (same
query, shifted dates — needed by the Reporter for period-over-period
deltas), plus the scrubbed Play Store review fixture for VoC.

This file is a STUB: in demo_mode it loads the frozen JSON fixtures in
app/fixtures/. Replace `_load_warehouse_snapshot` and `_load_voc_reviews`
with real Metabase API calls (see app/integrations/metabase_client.py)
before Day 2. Keep the return shape identical — it's validated against
app.schemas.contracts.Snapshot / Voc below.
"""
import json
from pathlib import Path
from typing import Any

from app.pipeline.state import GraphState
from app.schemas.contracts import Snapshot, Voc

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def _load_warehouse_snapshot() -> dict[str, Any]:
    with open(FIXTURES_DIR / "funnel_snapshot.json") as f:
        return json.load(f)


def _load_voc_reviews() -> dict[str, Any]:
    with open(FIXTURES_DIR / "voc_reviews.json") as f:
        return json.load(f)


def fetcher_node(state: GraphState) -> GraphState:
    if not state.get("demo_mode", True):
        raise NotImplementedError(
            "Live Metabase extraction not wired yet — see app/integrations/metabase_client.py. "
            "Alief: swap the fixture loads below for real query-pack calls, chunked <60s each, "
            "k>=25 suppression applied before this function returns."
        )

    raw = _load_warehouse_snapshot()
    voc_raw = _load_voc_reviews()

    ct_events = [{**e, "window": "current"} for e in raw["current"]["ct_events"]] + [
        {**e, "window": "previous"} for e in raw["previous"].get("ct_events", [])
    ]

    snapshot = Snapshot(
        stages=raw["current"]["stages"],
        segments=raw["segments"],
        reasons=raw["current"]["reasons"],
        ct_events=ct_events,
        previous_stages=raw["previous"]["stages"],
    )
    voc = Voc(
        reviews_meta=voc_raw["reviews_meta"],
        themes=voc_raw["themes"],
        per_finding_quotes={},  # populated later by Analyst once findings are ranked
    )

    return {
        **state,
        "status": "extracting",
        "snapshot": snapshot.model_dump(),
        "voc": voc.model_dump(),
    }
