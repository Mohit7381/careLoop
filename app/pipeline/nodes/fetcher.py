"""
Agent 1 — Fetcher. OWNER: Alief.

Deterministic, no LLM. Runs the fixed Metabase query pack (read-only,
Redshift DB 39) for the requested window AND the previous window, per the
active journey.

STUB: in demo_mode this loads the frozen PD fixture
(fixtures/{journey}/snapshot.json — Nakul's starter freeze; Alief's Day-1
blessed two-window freeze supersedes it, same shape). Swap
`_load_snapshot` for a real Metabase API call before Day 2. Keep the
return shape identical — validated against app.schemas.contracts.Snapshot.
"""
import json
from pathlib import Path

from app.pipeline.state import GraphState
from app.schemas.contracts import Snapshot

FIXTURES_DIR = Path("fixtures")


def _load_snapshot(journey: str) -> dict:
    path = FIXTURES_DIR / journey / "snapshot.json"
    return json.loads(path.read_text())


def fetcher_node(state: GraphState) -> GraphState:
    if not state.get("demo_mode", True):
        raise NotImplementedError(
            "Live Metabase extraction not wired yet — see app/integrations/metabase_client.py. "
            "Alief: swap _load_snapshot for a real query-pack call, chunked <60s each, "
            "k>=25 suppression applied before this function returns."
        )

    journey = state.get("journey", "pd_checkout")
    snapshot = Snapshot(**_load_snapshot(journey))

    return {
        **state,
        "status": "analyzing",
        "snapshot": snapshot.model_dump(),
    }
