"""
End-to-end pipeline test on fixtures (Day-1 gate: runs fully with stubbed
LLM calls, no network). This is what proves the orchestrator + Reporter +
PRD Generator + delivery contract works before Nakul/Harshit swap in real
LLM/GitLab calls.
"""
from app.pipeline.graph import compiled_graph
from app.pipeline.state import initial_state


def test_pipeline_runs_end_to_end_on_fixtures():
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    final_state = compiled_graph.invoke(state)

    assert final_state["status"] == "completed"
    assert final_state["findings"], "Analyst should produce at least one finding on the fixture"
    assert final_state["code_gaps"], "Code Scout should route at least one gap"
    assert final_state["prd_draft"] is not None
    assert "DRAFT" in final_state["prd_draft"]

    report = next(a for a in final_state["artifacts"] if a["kind"] == "report_md")
    assert "CareLoop Analysis Report" in report["content"]


def test_top_finding_is_the_known_good_payment_timeout_gap():
    state = initial_state(run_id=2, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    final_state = compiled_graph.invoke(state)

    top = sorted(final_state["findings"], key=lambda f: f["rank"])[0]
    # stage is a routing category (rev 2, per Harshit), not the funnel-stage id — the
    # payment_processing funnel drop routes to "consultation" because that's where the
    # abandon-kill code actually lives (ConsultationDao), not payment-service.
    assert top["stage"] == "consultation"

    top_gap = next(g for g in final_state["code_gaps"] if g["finding_rank"] == top["rank"])
    assert top_gap["mechanism_found"] is True
    assert top_gap["gap_class"] == "missing_retention_hook"
    assert top_gap["file"] == "ConsultationDao.java"
    assert top_gap["line"] == 146
