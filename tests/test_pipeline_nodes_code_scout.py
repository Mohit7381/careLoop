"""app/pipeline/nodes/code_scout.py - resilience + path-filtering coverage
(PR #3 review, ported onto the merged find_gap()/Remedy-Loop architecture),
plus the real live-LLM wiring for the Remedy Loop (gap #2 from the PR #3
follow-up: _unwired_live_llm() used to raise NotImplementedError).

Before this: _live_search_fn's requests call had nothing catching it, and
since it's called from inside remedy_loop.py's verify_remedy() for every
remedy on every gap, one flaky GitLab response during verification crashed
code_scout_node's ENTIRE run - taking down every other gap's already-located
mechanism and already-verified remedies with it.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.agents.code_scout.errors import CodeScoutExternalError
from app.config import Settings
from app.pipeline.nodes import code_scout as code_scout_module
from app.schemas.contracts import CodeGap, Finding, RunState


def _gap(finding_rank: int, repo: str) -> CodeGap:
    return CodeGap(
        finding_rank=finding_rank,
        origin="warehouse",
        stage="pharmacy_checkout",
        service=repo.rsplit("/", 1)[-1],
        repo=repo,
        mechanism_found=True,
        gap_class="missing_retention_hook",
        gap_statement="g",
    )


def _finding(rank: int) -> Finding:
    return Finding(
        rank=rank, origin="warehouse", stage="pharmacy_checkout",
        hypothesis="h", confidence="high", confirm_via="x",
    )


@patch("app.pipeline.nodes.code_scout.requests.get")
def test_live_search_fn_wraps_a_network_failure(mock_get):
    mock_get.side_effect = requests.ConnectionError("connection refused")
    search_fn = code_scout_module._live_search_fn(Settings())
    with pytest.raises(CodeScoutExternalError):
        search_fn("timor/oms", "abandon")


@patch("app.pipeline.nodes.code_scout.requests.get")
def test_live_search_fn_wraps_a_non_2xx_response(mock_get):
    resp = MagicMock(status_code=500)
    resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    mock_get.return_value = resp
    search_fn = code_scout_module._live_search_fn(Settings())
    with pytest.raises(CodeScoutExternalError):
        search_fn("timor/oms", "abandon")


@patch("app.pipeline.nodes.code_scout.requests.get")
def test_live_search_fn_filters_out_doc_and_test_hits(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"path": "context/database_schema.md", "startline": 1, "data": "..."},
            {"path": "src/test/java/OrderDaoTest.java", "startline": 2, "data": "..."},
            {"path": "src/main/java/com/halodoc/timor/oms/OrderDao.java", "startline": 3, "data": "abandon"},
        ],
    )
    search_fn = code_scout_module._live_search_fn(Settings())
    hits = search_fn("timor/oms", "abandon")

    assert len(hits) == 1
    assert hits[0]["path"] == "src/main/java/com/halodoc/timor/oms/OrderDao.java"


@patch("app.pipeline.nodes.code_scout.run_remedy_loop")
def test_a_failing_gap_remedy_loop_does_not_abort_other_gaps(mock_run_remedy_loop):
    """One gap's run_remedy_loop() blowing up (a GitLab outage mid-
    verification) must not lose the other gaps' already-verified remedies."""
    ok_gap_with_remedies = _gap(2, "timor/fulfilment")
    mock_run_remedy_loop.side_effect = [
        CodeScoutExternalError("simulated GitLab outage"),
        ok_gap_with_remedies,
    ]

    run_state = RunState(
        run_id=1, window_start="a", window_end="b", demo_mode=False,
        findings=[_finding(1), _finding(2)],
    )
    gaps = [_gap(1, "timor/oms"), _gap(2, "timor/fulfilment")]

    result = code_scout_module._run_remedies(run_state, gaps)

    assert len(result) == 2
    # The failed gap keeps its located mechanism (mechanism_found stays True)
    # but ships with no remedies, rather than losing the whole run.
    assert result[0].finding_rank == 1
    assert result[0].mechanism_found is True
    assert result[0].remedies == []
    assert result[1] is ok_gap_with_remedies


@patch("app.pipeline.nodes.code_scout.SphereClient")
def test_live_remedy_llm_calls_the_right_use_case_and_template(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.call.return_value = {"remedies": []}

    llm = code_scout_module._live_remedy_llm(Settings())
    out = llm({"mode": "remedy_proposal", "finding": "f"})

    assert out == {"remedies": []}
    args = mock_client.call.call_args.args
    assert args[0] == "code-gap-assessment"
    assert args[1] == 21689
    ctx = json.loads(args[2]["code_context"])
    assert ctx == {"mode": "remedy_proposal", "finding": "f"}


@patch("app.pipeline.nodes.code_scout.SphereClient")
def test_live_remedy_llm_wraps_a_client_failure(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.call.side_effect = RuntimeError("sphere call failed for code-gap-assessment: FAILED")

    llm = code_scout_module._live_remedy_llm(Settings())
    with pytest.raises(CodeScoutExternalError):
        llm({"mode": "remedy_verification"})


class _AssessFailsAfterLocating:
    """explore()/find_gap() succeeds (mechanism located), but assess()
    fails - proves node.py isolates this instead of crashing."""

    def find_gap(self, finding_rank, repo, search_terms):
        from app.agents.code_scout.search_client import GapLocation

        return GapLocation(file="OrderDao.java", line=1, snippet="..."), 1


class _FailingAssessor:
    def propose_search_terms(self, finding):
        return ["abandon"]

    def assess(self, finding, file, snippet):
        raise CodeScoutExternalError("simulated Sphere outage during classification")


def test_a_failing_assess_call_does_not_crash_and_reports_honestly():
    """A real sphere-backed assess() can fail at runtime. That must not crash
    the node, must not fabricate a class — and must not discard the file the
    search just found. Live run 4 lost nine located mechanisms this way."""
    from app.agents.code_scout.node import code_scout_node

    state = RunState(
        run_id=1, window_start="a", window_end="b",
        findings=[_finding(1)],
    )
    result = code_scout_node(state, search_client=_AssessFailsAfterLocating(), assessor=_FailingAssessor())
    gaps = result["code_gaps"]

    # The mechanism WAS located — that survives. Only the classification is
    # unavailable, and the gap says so instead of pretending nothing was found.
    assert len(gaps) == 1
    assert gaps[0].mechanism_found is True
    assert gaps[0].gap_class == "unclassified"
    assert gaps[0].file == "OrderDao.java"
    assert "assessment unavailable" in gaps[0].gap_statement
