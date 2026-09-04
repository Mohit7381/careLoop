"""
End-to-end orchestrator test on the real PD fixtures (Day-1 gate): runs the
full graph — real Analyst (Nakul), real Code Scout (Harshit), my Reporter/
PRD Generator/Report Writer/Delivery — with no network calls. Proves the
three teams' pieces actually compose, not just pass in isolation.
"""
from app.pipeline.graph import compiled_graph
from app.pipeline.state import initial_state


def _run():
    state = initial_state(
        run_id=1,
        window_start="2026-08-27",
        window_end="2026-09-02",
        demo_mode=True,
        journey="pd_checkout",
        prev_window_start="2026-08-20",
        prev_window_end="2026-08-26",
    )
    return compiled_graph.invoke(state)


def test_pipeline_runs_end_to_end_on_pd_fixtures():
    final_state = _run()

    assert final_state["status"] == "completed"
    assert final_state["findings"], "Analyst should produce at least one finding on the fixture"
    assert final_state["code_gaps"], "Code Scout should route at least one gap"
    assert final_state["prd_draft"] is not None
    assert "DRAFT" in final_state["prd_draft"]

    report = next(a for a in final_state["artifacts"] if a["kind"] == "report_md")
    assert "CareLoop Analysis Report" in report["content"]


def test_golden_run_reproduces_the_real_pd_findings():
    """
    Uses SphereClient(mode="replay") — a real recorded session (4 drill-down
    turns, fixtures/llm_replay/funnel-hypothesis-generation/) against real
    fixture data, not a hand-written script (PR #1 review M2). Reproduces 3
    warehouse findings (all pharmacy_checkout, the real drill-down chased
    the created->confirmed gap through reason clusters, price bands, and the
    rx-gated split) plus the 2 real VoC escalations.
    """
    final_state = _run()

    findings = sorted(final_state["findings"], key=lambda f: f["rank"])
    warehouse = [f for f in findings if f["origin"] == "warehouse"]
    voc = [f for f in findings if f["origin"] == "voc"]

    assert len(warehouse) == 3
    assert all(f["stage"] == "pharmacy_checkout" for f in warehouse)
    assert all(f["confidence"] in ("high", "medium", "low") for f in warehouse)
    assert {f["theme"] for f in voc} == {"payment/refund", "consultation/doctor"}

    top_gap = next(g for g in final_state["code_gaps"] if g["finding_rank"] == warehouse[0]["rank"])
    assert top_gap["mechanism_found"] is True
    assert top_gap["repo"] == "timor/oms"


def test_confirmed_stage_is_marked_maturing_not_delivered():
    """
    'confirmed' row IS the confirmed->delivered conversion rate, so it's the
    one that's right-censored by a fresh window — not 'delivered' itself
    (100%->100% by construction, flagging it changes nothing). Caught in
    review (PR #1 B3): the original predicate tested the wrong row.
    """
    final_state = _run()

    deltas = {d["stage"]: d for d in final_state["trend_report"]["deltas"]}
    assert deltas["confirmed"]["maturing"] is True
    assert deltas["delivered"]["maturing"] is False
    assert deltas["created"]["maturing"] is False
