"""The live suggestion assessor must use the same sphere conventions as every
other caller: host/token from app settings (run 23 died on KeyError
'SPHERE_BASE_URL'), the whole task dict as the single {code_context} param
(anything else renders an empty prompt), and a timeout that covers the
synchronous model call."""
import json
from unittest.mock import MagicMock, patch

import app.pipeline.nodes.suggestion as node
from app.agents.code_scout.suggestion_assessor import SpherePlatformFeatureSuggestionAssessor
from app.schemas.contracts import Finding


def test_constructor_needs_no_extra_env(monkeypatch):
    monkeypatch.delenv("SPHERE_BASE_URL", raising=False)
    monkeypatch.delenv("SPHERE_APP_TOKEN", raising=False)
    a = SpherePlatformFeatureSuggestionAssessor()
    assert a.base_url.startswith("http")
    assert a.service_type == "funnel-analysis"


@patch("app.agents.code_scout.suggestion_assessor.requests.post")
def test_task_is_sent_as_the_single_code_context_param(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"status": "SUCCESS", "data": {"search_terms": ["abandon"]}})
    mock_post.return_value.raise_for_status = lambda: None
    a = SpherePlatformFeatureSuggestionAssessor(base_url="http://sphere", app_token="t")
    a.propose_search_terms(Finding(rank=1, origin="warehouse", stage="pharmacy_checkout",
                                   hypothesis="h", confidence="high", confirm_via="x"))
    body = mock_post.call_args.kwargs["json"]
    assert set(body["params"]) == {"code_context"}
    assert json.loads(body["params"]["code_context"])["task"] == "propose_search_terms"
    assert mock_post.call_args.kwargs["timeout"] >= 60


def test_a_suggestion_outage_does_not_fail_the_run(monkeypatch):
    def boom(run_state, *, search_client, assessor):
        raise RuntimeError("sphere down")
    with patch.object(node, "_suggestion_code_scout_node", boom):
        out = node.suggestion_node({"run_id": 1, "journey": "pd_checkout", "window_start": "a", "window_end": "b",
                                    "demo_mode": True, "findings": [], "code_gaps": [], "suggestions": []})
    assert out["suggestions"] == []
