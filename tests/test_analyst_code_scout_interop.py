"""The Analyst -> Code Scout seam.

Every suite in this repo passed while three contract breaks sat on that
boundary (PR #3 review B1-B3): `confidence` typed as float against a
Literal, a `RunStatus` missing "scanning_code", and a routing vocabulary
covering four of the journey's six categories. Each suite was green because
none of them crossed the seam — the Analyst's tests stop at its own output
and Code Scout's start from hand-written Findings.

These tests cross it. They take the real replayed Analyst run and assert
Code Scout can consume every finding it produces, and that the journey
config and the routing table agree about the vocabulary.
"""
import json
from pathlib import Path

import pytest
import yaml

from app.agents.analyst import phase1
from app.agents.analyst.analyst import run_analyst
from app.agents.code_scout.assessor import StubCodeGapAssessor
from app.agents.code_scout.node import code_scout_node
from app.agents.code_scout.routing import repos_for_stage
from app.agents.code_scout.search_client import FixtureSearchClient
from app.integrations.sphere import SphereClient
from app.schemas.contracts import Confidence, Finding, RunState, Snapshot

ROOT = Path(__file__).parent.parent
FIX = ROOT / "fixtures" / "pd_checkout"
JOURNEY_DIR = ROOT / "config" / "journeys"
JOURNEYS = sorted(p.stem for p in JOURNEY_DIR.glob("*.yaml"))


@pytest.fixture(scope="module")
def analyst_state() -> RunState:
    """A real recorded Analyst session, not hand-written Findings."""
    ids = json.loads((FIX / "sphere_ids.json").read_text())
    template_id = next(u["template_id"] for u in ids["use_cases"]
                       if u["name"] == "funnel-hypothesis-generation")
    client = SphereClient(mode="replay")
    state = RunState(
        run_id=9001, journey="pd_checkout", demo_mode=True, status="analyzing",
        window_start="2026-08-27", window_end="2026-09-02",
        prev_window_start="2026-08-20", prev_window_end="2026-08-26",
        snapshot=Snapshot(**json.loads((FIX / "snapshot.json").read_text())),
    )
    return run_analyst(
        state,
        llm=lambda ctx: client.call("funnel-hypothesis-generation", template_id,
                                    {"analysis_context": json.dumps(ctx)}),
        cohort_cuts=json.loads((FIX / "cohort_cuts.json").read_text()),
        reviews=json.loads((FIX / "reviews_scrubbed.json").read_text()),
    )


# --- the seam itself -------------------------------------------------------

def test_code_scout_consumes_every_real_analyst_finding(analyst_state):
    """The regression guard for PR #3 B1/B2. A type break anywhere in Finding
    or RunState fails here instead of at the first live run."""
    assert analyst_state.findings, "replay session produced no findings"

    out = code_scout_node(
        analyst_state,
        search_client=FixtureSearchClient(ROOT / "fixtures" / "code_scout"),
        assessor=StubCodeGapAssessor(),
    )
    gaps = out["code_gaps"]
    assert gaps, "Code Scout produced nothing from a real Analyst run"

    # Round-trips: every gap re-validates, and every finding it names exists.
    ranks = {f.rank for f in analyst_state.findings}
    for gap in gaps:
        assert gap.finding_rank in ranks
        assert gap.stage in {f.stage for f in analyst_state.findings}


def test_analyst_handoff_status_is_the_code_scout_entry_status(analyst_state):
    """run_analyst hands over status="scanning_code"; a RunStatus enum that
    omits it rejects the whole state object (PR #3 B2)."""
    assert analyst_state.status == "scanning_code"
    RunState(**analyst_state.model_dump())  # must re-validate unchanged


def test_every_stage_the_analyst_emits_is_routable(analyst_state):
    for finding in analyst_state.findings:
        repos = repos_for_stage(finding.stage, analyst_state.journey)
        assert repos, f"finding #{finding.rank} routes to '{finding.stage}' with no repo"


# --- vocabulary agreement, across every journey ----------------------------

@pytest.mark.parametrize("journey", JOURNEYS)
def test_every_routing_category_resolves(journey):
    """PR #3 B3: the routing table covered 4 of the journey's 6 categories, so
    a finding routed to 'delivery' or 'stock' raised. Adding a journey with an
    unmapped category now fails here rather than mid-demo."""
    cfg = yaml.safe_load((JOURNEY_DIR / f"{journey}.yaml").read_text())
    for category in cfg["routing"]:
        repos = repos_for_stage(category, journey)
        assert repos, f"{journey}: '{category}' resolves to no repo"
        for r in repos:
            assert "/" in r["repo"], f"{journey}: malformed repo '{r['repo']}'"


@pytest.mark.parametrize("journey", JOURNEYS)
def test_voc_themes_route_to_real_categories(journey):
    cfg = yaml.safe_load((JOURNEY_DIR / f"{journey}.yaml").read_text())
    routing = set(cfg["routing"])
    for theme in cfg["voc"]["themes"]:
        assert theme["routing_stage"] in routing, (
            f"{journey}: VoC theme '{theme['name']}' routes to "
            f"'{theme['routing_stage']}', which is not a routing category")


def test_every_confidence_literal_survives_the_seam():
    """`confidence` was a float on one side and a Literal on the other, and
    every real finding was rejected. Pin the vocabulary from the contract."""
    for level in Confidence.__args__:
        f = Finding(rank=1, origin="warehouse", stage="pharmacy_checkout",
                    hypothesis="x", confidence=level, confirm_via="y")
        assert f.confidence == level


# --- journey_events --------------------------------------------------------

def test_journey_events_are_real_events_only(analyst_state):
    """Code Scout searches source for these, so an event the journey does not
    actually emit sends it hunting for a string that cannot exist."""
    emitted = {e.event_name for e in analyst_state.snapshot.ct_events}
    warehouse = [f for f in analyst_state.findings if f.origin == "warehouse"]
    assert warehouse

    for finding in warehouse:
        assert finding.journey_events, f"finding #{finding.rank} has no search seed"
        assert set(finding.journey_events) <= emitted


def test_configured_events_absent_from_the_snapshot_are_dropped(snapshot):
    """Exercises the intersection directly, on the confirmed->delivered gap.

    The pd_checkout gap the Analyst actually picks is created->confirmed,
    whose configured events all happen to be present — so asserting on that
    gap would pass even with the filter removed. This uses the one gap where
    the config and the snapshot genuinely disagree: 'order_delivered' is
    configured for the delivered stage and is not in the snapshot.
    """
    cfg = yaml.safe_load((JOURNEY_DIR / "pd_checkout.yaml").read_text())
    emitted = {e.event_name for e in snapshot.ct_events}
    assert "order_delivered" in cfg["journey_events"]["delivered"]
    assert "order_delivered" not in emitted

    events = phase1.events_for_gap(
        {"from_stage": "confirmed", "to_stage": "delivered"},
        cfg["journey_events"], snapshot.ct_events)

    assert "order_delivered" not in events
    assert events == ["order_placed", "order_abandoned"]


def test_events_for_gap_is_empty_without_a_gap(snapshot):
    cfg = yaml.safe_load((JOURNEY_DIR / "pd_checkout.yaml").read_text())
    assert phase1.events_for_gap(None, cfg["journey_events"], snapshot.ct_events) == []


def test_voc_findings_carry_theme_terms_not_journey_events(analyst_state):
    for finding in [f for f in analyst_state.findings if f.origin == "voc"]:
        assert finding.journey_events == []
        assert finding.theme_search_terms
