"""app/pipeline/nodes/report_writer.py — "Shipped fixes & measured impact"
section (closed-loop impact, 2026-09-04)."""
from app.pipeline.nodes.report_writer import report_writer_node
from app.pipeline.state import initial_state


def _state_with_shipped_fix(with_metric: bool) -> dict:
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    metric = dict(metric_name="conversion rate at 'created'", metric_unit="%",
                  previous_value=50.0, current_value=60.0, pct_change=20.0,
                  metric_ref="stage:created") if with_metric else {}
    state["shipped_fixes"] = [{
        "finding_rank": 1, "origin": "warehouse", "stage": "created", "repo": "timor/oms",
        "remedy_proposal": "Retention push before final abandon",
        "evidence_file": "Retention.java", "evidence_line": 42,
        "commit": {"sha": "abc123def456", "short_sha": "abc123de", "author": "jdoe",
                   "date": "2026-08-20", "message": "Add retention push"},
        **metric,
    }]
    return state


def test_report_includes_a_shipped_fix_with_its_measured_impact():
    result = report_writer_node(_state_with_shipped_fix(with_metric=True))
    report = result["artifacts"][-1]["content"]

    assert "## Shipped fixes & measured impact" in report
    assert "abc123de" in report
    assert "up 20.0%" in report


def test_report_is_honest_when_no_fix_shipped_this_run():
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    result = report_writer_node(state)
    report = result["artifacts"][-1]["content"]

    assert "_none detected this run_" in report


def test_report_includes_a_feature_amplification_idea():
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    state["feature_amplifications"] = [{
        "finding_rank": 1, "origin": "warehouse", "stage": "created", "service": "oms", "repo": "timor/oms",
        "suggestion_type": "tech", "title": "Widen to consultation abandon too",
        "description": "Reuse RetentionService.push in the consultation abandon path.",
        "rationale": "The metric moved +20.0%; the same hook could recover more elsewhere.",
        "verification_status": "unverified",
    }]
    result = report_writer_node(state)
    report = result["artifacts"][-1]["content"]

    assert "## Feature amplification ideas (built on shipped wins)" in report
    assert "Widen to consultation abandon too" in report


def test_report_is_honest_when_nothing_shipped_favourably_yet():
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    result = report_writer_node(state)
    report = result["artifacts"][-1]["content"]

    assert "no shipped fix moved a metric favourably yet" in report


def test_report_includes_growth_ideas_and_labels_their_inspiration():
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    state["growth_ideas"] = [
        {"title": "One-tap saved payment method", "description": "Let repeat buyers skip payment entry.",
         "rationale": "Reduces friction.", "inspiration": "industry_pattern", "target_stage": None, "evidence": []},
        {"title": "Cart-recovery nudge", "description": "Prompt stalled rx-gated orders.",
         "rationale": "255293 rx-gated orders entered this stage.", "inspiration": "funnel_data",
         "target_stage": "pharmacy_checkout",
         "evidence": [{"type": "drilldown", "metric": "entered", "value": 255293.0}]},
    ]
    result = report_writer_node(state)
    report = result["artifacts"][-1]["content"]

    assert "## Growth ideas" in report
    assert "One-tap saved payment method" in report
    assert "general industry pattern, not Halodoc-specific data" in report
    assert "grounded in this run's own funnel data" in report
    assert "[pharmacy_checkout]" in report


def test_report_labels_a_positive_review_grounded_idea_correctly():
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    state["growth_ideas"] = [
        {"title": "Highlight fast delivery at checkout", "description": "Show an ETA badge.",
         "rationale": "8 positive reviews already praise fast delivery.", "inspiration": "positive_review",
         "target_stage": None, "evidence": [{"type": "drilldown", "metric": "count", "value": 8.0}]},
    ]
    result = report_writer_node(state)
    report = result["artifacts"][-1]["content"]

    assert "grounded in this run's own positive reviews" in report
    assert "general industry pattern" not in report


def test_report_is_honest_when_no_growth_ideas_proposed():
    state = initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-30", demo_mode=True)
    result = report_writer_node(state)
    report = result["artifacts"][-1]["content"]

    assert "_none proposed this run_" in report
