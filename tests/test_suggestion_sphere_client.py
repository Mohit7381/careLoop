import json
"""SpherePlatformFeatureSuggestionAssessor - request/response shape only.
No real SPHERE_APP_TOKEN exists yet, so requests.post is mocked; this proves
the client builds the right HTTP call and parses the right response shape,
not that the real service accepts it (see suggestion_assessor.py's
ASSUMPTIONS).

Endpoint/template_id/status-envelope match Nakul's live-confirmed
integration (app/integrations/sphere.py, PR #2) - see PR #3 review S4.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.explore_search_client import GapLocation
from app.agents.code_scout.suggestion_assessor import SpherePlatformFeatureSuggestionAssessor
from app.schemas.contracts import Finding


def _finding(**overrides) -> Finding:
    kwargs = dict(
        rank=1,
        origin="warehouse",
        stage="consultation",
        hypothesis="51,321/wk consultations killed by a silent timeout",
        confidence="high",
        confirm_via="check re-engagement CT events post-cancel",
    )
    kwargs.update(overrides)
    return Finding(**kwargs)


def _assessor() -> SpherePlatformFeatureSuggestionAssessor:
    return SpherePlatformFeatureSuggestionAssessor(base_url="https://sphere.test", app_token="tok")


def _success(data: dict) -> MagicMock:
    return MagicMock(status_code=200, json=lambda: {"status": "SUCCESS", "data": data})


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_propose_search_terms_skips_the_llm_when_journey_events_present(mock_post):
    finding = _finding(journey_events=["consultation_payment_timeout"])
    terms = _assessor().propose_search_terms(finding)
    assert terms == ["consultation_payment_timeout"]
    mock_post.assert_not_called()


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_propose_search_terms_calls_sphere_when_no_journey_events(mock_post):
    mock_post.return_value = _success({"search_terms": ["abandon", "timeout"]})
    terms = _assessor().propose_search_terms(_finding())

    assert terms == ["abandon", "timeout"]
    args, kwargs = mock_post.call_args
    assert args[0] == "https://sphere.test/v1/chat-ai/requests/validation"
    assert kwargs["headers"]["x-app-token"] == "tok"
    assert kwargs["json"]["use_case"] == "code-gap-assessment"
    assert kwargs["json"]["template_id"] == 21689
    # Template 21689 renders one placeholder, {code_context}; the task dict
    # travels inside it as a JSON string (a raw dict rendered an empty prompt).
    sent = json.loads(kwargs["json"]["params"]["code_context"])
    assert set(kwargs["json"]["params"]) == {"code_context"}
    assert sent["task"] == "propose_search_terms"


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_propose_suggestions_sends_the_full_inventory_and_parses_the_response(mock_post):
    mock_post.return_value = _success(
        {
            "suggestions": [
                {
                    "suggestion_type": "tech",
                    "title": "Add Garuda call",
                    "description": "d",
                    "rationale": "r",
                    "signature": "garuda",
                    "evidence_file": "ConsultationDao.java",
                },
                {
                    "suggestion_type": "business",
                    "title": "Grace period",
                    "description": "d2",
                    "rationale": "r2",
                },
            ]
        }
    )
    inventory = [GapLocation(file="ConsultationDao.java", line=146, snippet="...")]
    proposals = _assessor().propose_suggestions(_finding(), inventory)

    assert len(proposals) == 2
    assert proposals[0].suggestion_type == "tech"
    assert proposals[0].signature == "garuda"
    assert proposals[1].suggestion_type == "business"
    assert proposals[1].signature is None

    sent_params = json.loads(mock_post.call_args.kwargs["json"]["params"]["code_context"])
    assert sent_params["inventory"] == [
        {"file": "ConsultationDao.java", "line": 146, "snippet": "..."}
    ]


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_propose_search_terms_wraps_a_network_failure(mock_post):
    """A raw requests.RequestException must not escape the client - callers
    only need to catch CodeScoutExternalError."""
    mock_post.side_effect = requests.ConnectionError("connection refused")
    with pytest.raises(CodeScoutExternalError):
        _assessor().propose_search_terms(_finding())


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_propose_search_terms_wraps_a_non_2xx_response(mock_post):
    resp = MagicMock(status_code=500)
    resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    mock_post.return_value = resp
    with pytest.raises(CodeScoutExternalError):
        _assessor().propose_search_terms(_finding())


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_propose_search_terms_wraps_a_malformed_response_body(mock_post):
    """response.json() succeeding, status SUCCESS, but missing
    data.search_terms must not raise a raw KeyError."""
    mock_post.return_value = _success({})
    with pytest.raises(CodeScoutExternalError):
        _assessor().propose_search_terms(_finding())


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_propose_suggestions_wraps_a_malformed_response_body(mock_post):
    mock_post.return_value = _success({})
    with pytest.raises(CodeScoutExternalError):
        _assessor().propose_suggestions(_finding(), inventory=[])


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_a_failed_call_arriving_as_http_200_is_caught(mock_post):
    """S4.3: sphere-platform can return status: FAILED with a 200 status
    code - raise_for_status() alone doesn't see it. Before the fix this hit
    a bare KeyError on data.suggestions instead of a typed error."""
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"status": "FAILED", "error": "template output_schema validation failed"},
    )
    with pytest.raises(CodeScoutExternalError):
        _assessor().propose_search_terms(_finding())
