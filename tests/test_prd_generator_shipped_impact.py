"""app/pipeline/nodes/prd_generator.py — rendering a ShippedFix into the
deterministic PRD template and the live-LLM inputs (closed-loop impact,
2026-09-04)."""
from app.pipeline.nodes.prd_generator import _prd_inputs, _render_prd_llm_stub, _requirements_block
from app.schemas.contracts import CodeGap, Finding, Remedy, ShippedCommit, ShippedFix, TrendReport


def _shipped_fix(finding_rank=1, with_metric=True) -> ShippedFix:
    metric = dict(metric_name="conversion rate at 'created'", metric_unit="%",
                  previous_value=50.0, current_value=60.0, pct_change=20.0,
                  metric_ref="stage:created") if with_metric else {}
    return ShippedFix(
        finding_rank=finding_rank, origin="warehouse", stage="created", repo="timor/oms",
        remedy_proposal="Retention push before final abandon",
        evidence_file="Retention.java", evidence_line=42,
        commit=ShippedCommit(sha="abc123def456", short_sha="abc123de", author="jdoe",
                             date="2026-08-20", message="Add retention push"),
        **metric,
    )


def _gap_with_exists_remedy() -> CodeGap:
    return CodeGap(
        finding_rank=1, origin="warehouse", stage="created", service="oms", repo="timor/oms",
        mechanism_found=True, gap_class="missing_retention_hook", gap_statement="g",
        file="Retention.java", line=42,
        remedies=[Remedy(proposal="Retention push before final abandon", signature="s",
                         status="exists", evidence_file="Retention.java", evidence_line=42)],
    )


def _finding() -> Finding:
    return Finding(rank=1, origin="warehouse", stage="created", hypothesis="h",
                   confidence="high", confirm_via="x")


def test_requirements_block_labels_a_shipped_exists_remedy_with_its_commit_and_impact():
    gap = _gap_with_exists_remedy()
    block = _requirements_block(gap, [], [_shipped_fix()])

    assert "Shipped" in block
    assert "abc123de" in block
    assert "jdoe" in block
    assert "2026-08-20" in block
    assert "+20.0%" in block


def test_requirements_block_labels_an_exists_remedy_with_no_shipped_match_as_already_built_not_shipped():
    gap = _gap_with_exists_remedy()
    block = _requirements_block(gap, [], [])  # nothing shipped

    assert "Already built" in block
    assert "Shipped" not in block


def test_requirements_block_is_honest_when_impact_is_not_yet_measurable():
    gap = _gap_with_exists_remedy()
    block = _requirements_block(gap, [], [_shipped_fix(with_metric=False)])

    assert "Shipped" in block
    assert "not yet measurable" in block


def test_render_prd_stub_notes_the_shipped_fix_in_goals_and_success_metrics():
    gap = _gap_with_exists_remedy()
    _title, body = _render_prd_llm_stub(
        _finding(), [gap], [], TrendReport(), quotes=[],
        run_id=1, window_start="2026-08-01", window_end="2026-08-30",
        shipped=[_shipped_fix()],
    )

    assert "already SHIPPED" in body
    assert "Already measured" in body
    assert "abc123de" in body


def test_prd_inputs_only_carries_shipped_fixes_for_the_matching_finding():
    gap = _gap_with_exists_remedy()
    inputs = _prd_inputs(
        _finding(), [gap], [], TrendReport(), quotes=[],
        run_id=1, window_start="2026-08-01", window_end="2026-08-30",
        shipped=[_shipped_fix(finding_rank=1), _shipped_fix(finding_rank=2)],
    )

    assert len(inputs["shipped_fixes"]) == 1
    assert inputs["shipped_fixes"][0]["commit_sha"] == "abc123de"
    assert any("ALREADY SHIPPED" in r for r in inputs["rules"])


def test_prd_inputs_shipped_fixes_is_empty_when_nothing_shipped():
    gap = _gap_with_exists_remedy()
    inputs = _prd_inputs(
        _finding(), [gap], [], TrendReport(), quotes=[],
        run_id=1, window_start="2026-08-01", window_end="2026-08-30",
    )

    assert inputs["shipped_fixes"] == []
