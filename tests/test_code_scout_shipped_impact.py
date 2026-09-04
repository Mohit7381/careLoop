"""app/pipeline/nodes/code_scout.py — wiring detect_shipped_fixes() into the
node's output (closed-loop impact, 2026-09-04)."""
from unittest.mock import patch

from app.pipeline.nodes import code_scout as code_scout_module
from app.schemas.contracts import CodeGap, Finding, Remedy, RunState, ShippedCommit


def _gap_with_exists_remedy() -> CodeGap:
    return CodeGap(
        finding_rank=1, origin="warehouse", stage="pharmacy_checkout",
        service="oms", repo="timor/oms",
        mechanism_found=True, gap_class="missing_retention_hook", gap_statement="g",
        remedies=[Remedy(proposal="Retention push before final abandon", signature="s",
                         status="exists", evidence_file="Retention.java", evidence_line=42)],
    )


class _FakeCommitClient:
    def blame_line(self, repo, file, line):
        return ShippedCommit(sha="abc123def456", short_sha="abc123de", author="jdoe",
                             date="2026-08-20", message="Add retention push")


@patch.object(code_scout_module, "_commit_client", return_value=_FakeCommitClient())
@patch.object(code_scout_module, "_code_scout_node")
@patch.object(code_scout_module, "_run_remedies")
def test_code_scout_node_reports_a_shipped_fix_when_its_commit_postdates_the_baseline(
    mock_run_remedies, mock_inner_node, _mock_commit_client,
):
    gap = _gap_with_exists_remedy()
    mock_inner_node.return_value = {"code_gaps": [gap]}
    mock_run_remedies.return_value = [gap]

    state = {
        "run_id": 1, "journey": "pd_checkout", "window_start": "2026-08-01",
        "window_end": "2026-08-30", "prev_window_end": "2026-08-15", "demo_mode": False,
        "findings": [Finding(rank=1, origin="warehouse", stage="pharmacy_checkout",
                             hypothesis="h", confidence="high", confirm_via="x").model_dump()],
    }

    result = code_scout_module.code_scout_node(state)

    assert len(result["shipped_fixes"]) == 1
    sf = result["shipped_fixes"][0]
    assert sf["finding_rank"] == 1
    assert sf["commit"]["short_sha"] == "abc123de"


@patch.object(code_scout_module, "_commit_client", return_value=_FakeCommitClient())
@patch.object(code_scout_module, "_code_scout_node")
@patch.object(code_scout_module, "_run_remedies")
def test_code_scout_node_reports_nothing_shipped_before_any_baseline_is_known(
    mock_run_remedies, mock_inner_node, _mock_commit_client,
):
    gap = _gap_with_exists_remedy()
    mock_inner_node.return_value = {"code_gaps": [gap]}
    mock_run_remedies.return_value = [gap]

    state = {
        "run_id": 1, "journey": "pd_checkout", "window_start": "not-a-date",
        "window_end": "2026-08-30", "prev_window_end": None, "demo_mode": False,
        "findings": [],
    }

    result = code_scout_module.code_scout_node(state)

    assert result["shipped_fixes"] == []
