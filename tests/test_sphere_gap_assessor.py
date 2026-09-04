"""SpherePlatformCodeGapAssessor - the real LLM-backed CodeGapAssessor
(gap #1 from the PR #3 follow-up: the live pipeline had only ever run
StubCodeGapAssessor). Mocks SphereClient itself (not requests/urllib
directly) since app.integrations.sphere.SphereClient is the shared,
already-tested client - this only proves this class calls it correctly and
handles its failure modes, not that the real service accepts the payload.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.agents.code_scout.assessor import SpherePlatformCodeGapAssessor
from app.agents.code_scout.errors import CodeScoutExternalError
from app.schemas.contracts import Finding


def _finding(**overrides) -> Finding:
    kwargs = dict(
        rank=1, origin="warehouse", stage="pharmacy_checkout",
        hypothesis="413,973 PD orders/wk abandoned before confirmation",
        confidence="high", confirm_via="check re-engagement CT events post-cancel",
    )
    kwargs.update(overrides)
    return Finding(**kwargs)


@patch("app.agents.code_scout.assessor.SphereClient")
def _assessor(mock_client_cls) -> tuple[SpherePlatformCodeGapAssessor, MagicMock]:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    assessor = SpherePlatformCodeGapAssessor()
    return assessor, mock_client


def test_propose_search_terms_skips_the_llm_when_journey_events_present():
    assessor, mock_client = _assessor()
    finding = _finding(journey_events=["order_abandoned"])
    assert assessor.propose_search_terms(finding) == ["order_abandoned"]
    mock_client.call.assert_not_called()


def test_propose_search_terms_skips_the_llm_for_voc_with_theme_terms():
    assessor, mock_client = _assessor()
    finding = _finding(origin="voc", theme_search_terms=["refund"])
    assert assessor.propose_search_terms(finding) == ["refund"]
    mock_client.call.assert_not_called()


def test_propose_search_terms_calls_sphere_and_uses_the_right_template():
    assessor, mock_client = _assessor()
    mock_client.call.return_value = {"search_terms": ["abandon", "timeout"]}

    terms = assessor.propose_search_terms(_finding())

    assert terms == ["abandon", "timeout"]
    args = mock_client.call.call_args.args
    assert args[0] == "code-gap-assessment"
    assert args[1] == 21689  # confirmed in fixtures/pd_checkout/sphere_ids.json
    assert "code_context" in args[2]
    import json
    ctx = json.loads(args[2]["code_context"])
    assert ctx["mode"] == "propose_search_terms"


def test_propose_search_terms_wraps_a_client_failure():
    assessor, mock_client = _assessor()
    mock_client.call.side_effect = RuntimeError("sphere call failed for code-gap-assessment: FAILED")
    with pytest.raises(CodeScoutExternalError):
        assessor.propose_search_terms(_finding())


def test_propose_search_terms_wraps_a_malformed_response():
    assessor, mock_client = _assessor()
    mock_client.call.return_value = {}
    with pytest.raises(CodeScoutExternalError):
        assessor.propose_search_terms(_finding())


def test_assess_returns_a_valid_gap_assessment():
    assessor, mock_client = _assessor()
    mock_client.call.return_value = {
        "gap_class": "missing_retention_hook",
        "gap_statement": "No notification before the abandon kill.",
        "proposed_change_location": "OrderDao.java: call Garuda before abandon",
    }

    assessment = assessor.assess(_finding(), "OrderDao.java", "snippet")

    assert assessment.gap_class == "missing_retention_hook"
    assert assessment.gap_statement == "No notification before the abandon kill."


def test_an_unrecognised_gap_class_is_recorded_not_rejected():
    """Live run 4: the model invented a class on all nine assess() calls
    ('configuration-only-no-usage-evidence', 'missing_consultation_event_types',
    ...). Rejecting them threw away nine located mechanisms. An obvious synonym
    is mapped; anything else is recorded as "unclassified" with the model's
    own words kept on the statement, so nothing is fabricated and nothing is
    lost."""
    assessor, mock_client = _assessor()

    mock_client.call.return_value = {"gap_class": "not_a_real_class", "gap_statement": "x"}
    out = assessor.assess(_finding(), "OrderDao.java", "snippet")
    assert out.gap_class == "unclassified"
    assert "not_a_real_class" in out.gap_statement

    mock_client.call.return_value = {"gap_class": "missing_notification_hook", "gap_statement": "y"}
    out = assessor.assess(_finding(), "OrderDao.java", "snippet")
    assert out.gap_class == "missing_retention_hook"
    assert "missing_notification_hook" in out.gap_statement       # the mapping is visible


def test_the_snippet_sent_to_sphere_carries_no_angle_brackets():
    """Two live assess() calls died with 'Response contains HTML tags': the
    model echoed the List<Order> generics from the Java snippet we sent."""
    assessor, mock_client = _assessor()
    mock_client.call.return_value = {"gap_class": "logic_flaw", "gap_statement": "z"}
    assessor.assess(_finding(), "OrderService.java", "List<Order> orders = Optional<Order>.empty();")
    import json
    sent = json.loads(mock_client.call.call_args.args[2]["code_context"])
    assert "<" not in sent["snippet"] and ">" not in sent["snippet"]
    assert sent["allowed_gap_classes"] == ["logic_flaw", "missing_retention_hook", "ux_gap"]
