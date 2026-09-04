"""GET /v1/analysis/runs — run history. The dashboard's table used to start
empty on every page load/new tab even though every run was already sitting
in analysis_runs; nothing served them back. Tests _run_summary() directly
(pure function on an ORM row) rather than spinning up a TestClient, matching
this project's existing "test the function, not the framework" convention.
"""
import datetime

from app.api.routes_analysis import _run_summary
from app.db.models import AnalysisRun, DropOffFinding


def _run(**overrides) -> AnalysisRun:
    kwargs = dict(
        id=1, journey="pd_checkout", window_start="2026-08-27", window_end="2026-09-02",
        status="completed", failed_stage=None, config={}, created_at=datetime.datetime(2026, 9, 4, 12, 0),
    )
    kwargs.update(overrides)
    run = AnalysisRun(**kwargs)
    run.findings = []
    return run


def _finding(rank: int, hypothesis: str) -> DropOffFinding:
    return DropOffFinding(
        rank=rank, origin="warehouse", stage="pharmacy_checkout", hypothesis=hypothesis,
        segments=[], evidence=[], confidence="high", confirm_via="x",
    )


def test_unscoped_run_has_no_prompt_or_scope_summary():
    s = _run_summary(_run())
    assert s.prompt is None
    assert s.scope_summary is None


def test_scoped_run_surfaces_the_prompt_and_a_human_readable_summary():
    scope = {
        "prompt": "why are users dropping off after adding items to cart",
        "from_stage": "created", "to_stage": "confirmed",
        "dimensions": ["item_count"], "review_days": None,
        "matched_on": ["stage:created"], "unresolved": [],
    }
    s = _run_summary(_run(config={"scope": scope}))
    assert s.prompt == scope["prompt"]
    assert "created to confirmed" in s.scope_summary


def test_top_finding_is_the_lowest_ranked_one_regardless_of_list_order():
    run = _run()
    run.findings = [_finding(3, "third"), _finding(1, "first"), _finding(2, "second")]
    s = _run_summary(run)
    assert s.top_finding == "first"
    assert s.findings_count == 3


def test_no_findings_is_an_honest_none_not_a_placeholder_string():
    s = _run_summary(_run())
    assert s.top_finding is None
    assert s.findings_count == 0


def test_failed_run_reports_the_failed_stage_instead_of_a_finding():
    run = _run(status="failed", failed_stage="scanning_code")
    run.findings = [_finding(1, "would have been the top finding")]
    s = _run_summary(run)
    assert s.top_finding == "Failed at scanning_code"


def test_failed_run_with_no_stage_recorded_is_still_honest():
    s = _run_summary(_run(status="failed", failed_stage=None))
    assert s.top_finding == "Failed at an unknown stage"


def test_old_dimensions_only_config_predating_scope_does_not_crash():
    """Runs created before `scope` existed on config only ever had
    {"dimensions": [...]}. Must degrade to "no prompt" honestly, not raise."""
    s = _run_summary(_run(config={"dimensions": ["payments"]}))
    assert s.prompt is None
    assert s.scope_summary is None
