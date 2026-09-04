"""
Agent 1 — Fetcher. OWNER: Alief.

Deterministic, no LLM. Runs the fixed Metabase query pack (read-only,
Redshift DB 39) for the requested window AND the previous window, per the
active journey. ALSO fetches PII-scrubbed Play Store reviews for the same
journey — the Analyst's phase 3 (VoC classification + correlation) needs
the actual review set, not just the funnel snapshot.

STUB: in demo_mode this loads the frozen PD fixtures
(fixtures/{journey}/snapshot.json — Nakul's starter freeze; Alief's Day-1
blessed two-window freeze supersedes it, same shape — and
fixtures/{journey}/reviews_scrubbed.json). Swap `_load_snapshot` for a real
Metabase API call and `_load_reviews` for the real Play Store scraper
before Day 2. Keep both return shapes identical — snapshot validated
against app.schemas.contracts.Snapshot; reviews are the raw scrubbed dicts
app.agents.analyst.phase3_voc.run_voc already expects.

2026-09-04: reviews now flow through GraphState (state["reviews"]) instead
of the Analyst quietly re-reading reviews_scrubbed.json itself in demo
mode - that shortcut bypassed the Fetcher entirely and isn't how a live
run would ever get real reviews. run_analyst() still has its own
demo-mode fallback for callers that construct RunState directly (tests,
scripts) without going through this pipeline node.
"""
import json
from pathlib import Path

from app.pipeline.state import GraphState
from app.schemas.contracts import Snapshot

FIXTURES_DIR = Path("fixtures")


def _load_snapshot(journey: str) -> dict:
    path = FIXTURES_DIR / journey / "snapshot.json"
    return json.loads(path.read_text())


def _load_reviews(journey: str) -> list[dict]:
    path = FIXTURES_DIR / journey / "reviews_scrubbed.json"
    return json.loads(path.read_text()) if path.exists() else []


def fetcher_node(state: GraphState) -> GraphState:
    if not state.get("demo_mode", True):
        raise NotImplementedError(
            "Live extraction not wired yet. Alief: (1) swap _load_snapshot for a real "
            "Metabase query-pack call, chunked <60s each, k>=25 suppression applied "
            "before this function returns; (2) swap _load_reviews for the real Play "
            "Store scraper (see app.integrations — no scraper client exists yet, this "
            "is a new integration, not a swap) — PII must be scrubbed at ingest here, "
            "same as the demo fixture, before reviews ever reach state."
        )

    journey = state.get("journey", "pd_checkout")
    snapshot = Snapshot(**_load_snapshot(journey))
    reviews = _load_reviews(journey)

    return {
        **state,
        "status": "analyzing",
        "snapshot": snapshot.model_dump(),
        "reviews": reviews,
    }
