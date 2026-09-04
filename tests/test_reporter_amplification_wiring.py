"""app/pipeline/nodes/reporter.py — wiring propose_feature_amplifications()
into reporter_node's output (2026-09-04)."""
from unittest.mock import patch

from app.pipeline.nodes import reporter as reporter_module
from app.pipeline.state import initial_state
from app.schemas.contracts import CodeGap, Finding, Remedy, ShippedCommit, ShippedFix


def _shipped_fix_dict() -> dict:
    return ShippedFix(
        finding_rank=1, origin="warehouse", stage="pharmacy_checkout", repo="timor/oms",
        remedy_proposal="Retention push before final abandon",
        evidence_file="Retention.java", evidence_line=42,
        commit=ShippedCommit(sha="abc123def456", short_sha="abc123de", author="jdoe",
                             date="2026-08-20", message="Add retention push"),
    ).model_dump()


def _base_state() -> dict:
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    state["journey"] = "pd_checkout"
    state["top_gap_to_stage"] = "created"
    state["snapshot"] = {
        "stages": [{"stage": "created", "dimension": "all", "segment": "all", "entered": 1000, "converted": 600, "suppressed": False}],
        "previous_stages": [{"stage": "created", "dimension": "all", "segment": "all", "entered": 1000, "converted": 500, "suppressed": False}],
        "segments": [], "reasons": [], "ct_events": [],
    }
    state["findings"] = [Finding(rank=1, origin="warehouse", stage="created", hypothesis="h",
                                 confidence="high", confirm_via="x").model_dump()]
    state["shipped_fixes"] = [_shipped_fix_dict()]
    state["voc"] = {}
    return state


@patch.object(reporter_module, "make_use_case_llm")
def test_reporter_node_populates_feature_amplifications_from_a_favourable_shipped_fix(mock_factory):
    def amplification_llm(ctx):
        return {"suggestions": [{
            "suggestion_type": "tech", "title": "Widen to consultation abandon too",
            "description": "Reuse the same push hook in consultation.",
            "rationale": "The metric moved favourably; the same mechanism may help elsewhere.",
        }]}

    # First call inside reporter_node is trend-narrative's llm=None path (llm
    # param passed explicitly below), second is make_use_case_llm for
    # amplification — mock_factory backs only the latter since llm=None here.
    mock_factory.return_value = amplification_llm

    result = reporter_module.reporter_node(_base_state(), llm=None)

    assert len(result["feature_amplifications"]) == 1
    assert result["feature_amplifications"][0]["title"] == "Widen to consultation abandon too"


@patch.object(reporter_module, "make_use_case_llm", return_value=None)
def test_reporter_node_reports_no_amplifications_when_the_use_case_is_unavailable(mock_factory):
    result = reporter_module.reporter_node(_base_state(), llm=None)

    assert result["feature_amplifications"] == []
