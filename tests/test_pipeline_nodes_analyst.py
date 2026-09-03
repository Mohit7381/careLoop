"""app/pipeline/nodes/analyst.py — prompt-scoped analysis (decision #13):
_apply_scope() narrows run_analyst()'s findings to the requested routing
categories without touching how the Analyst explored (ranks, drilldown
trail, and voc summary all stay as run_analyst() produced them)."""
from app.pipeline.nodes.analyst import _apply_scope
from app.schemas.contracts import Finding, RunState


def _finding(rank: int, stage: str, origin: str = "warehouse") -> Finding:
    return Finding(rank=rank, origin=origin, stage=stage, hypothesis="h", confidence="high", confirm_via="x")


def _state(requested_dimensions: list[str], findings: list[Finding]) -> RunState:
    return RunState(
        run_id=1, window_start="a", window_end="b",
        requested_dimensions=requested_dimensions, findings=findings,
    )


def test_no_requested_dimensions_is_a_no_op():
    findings = [_finding(1, "pharmacy_checkout"), _finding(2, "payments")]
    out = _apply_scope(_state([], findings))
    assert out.findings == findings


def test_filters_findings_outside_the_requested_scope():
    kept = _finding(2, "payments")
    out = _apply_scope(_state(["payments"], [_finding(1, "pharmacy_checkout"), kept, _finding(3, "delivery")]))
    assert out.findings == [kept]


def test_multiple_dimensions_union_together():
    a, b = _finding(1, "payments"), _finding(2, "delivery")
    out = _apply_scope(_state(["payments", "delivery"], [a, b, _finding(3, "stock")]))
    assert out.findings == [a, b]


def test_ranks_are_not_renumbered_after_filtering():
    """A finding scoped down to one survivor keeps its true severity rank —
    #3 stays #3, it does not get relabelled #1 just because it's now the
    only thing on screen (that would overstate it)."""
    third_ranked = _finding(3, "payments")
    out = _apply_scope(_state(["payments"], [_finding(1, "pharmacy_checkout"), _finding(2, "delivery"), third_ranked]))
    assert out.findings == [third_ranked]
    assert out.findings[0].rank == 3


def test_scope_matching_nothing_is_an_honest_empty_result():
    out = _apply_scope(_state(["consultation"], [_finding(1, "pharmacy_checkout")]))
    assert out.findings == []
