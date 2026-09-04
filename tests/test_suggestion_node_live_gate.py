"""The suggestion node must follow the same live/demo gate as the other nodes:
LIVE_LLM=true means the real sphere assessor even when demo_mode is on.
Before this, live runs showed the scripted demo suggestions next to real
findings, gaps and PRDs."""
from unittest.mock import patch

import app.pipeline.nodes.suggestion as node


def _run(monkeypatch, live: bool):
    monkeypatch.setenv("LIVE_LLM", "true" if live else "false")
    from app.config import get_settings
    get_settings.cache_clear()
    chosen = {}

    def fake_inner(run_state, *, search_client, assessor):
        chosen["assessor"] = type(assessor).__name__
        return {"suggestions": []}

    with patch.object(node, "_suggestion_code_scout_node", fake_inner), \
         patch.object(node, "SpherePlatformFeatureSuggestionAssessor", lambda: object()), \
         patch.object(node, "LiveGitlabExploreSearchClient", lambda **kw: object()):
        node.suggestion_node({"run_id": 1, "journey": "pd_checkout", "window_start": "a", "window_end": "b",
                              "demo_mode": True, "findings": [], "code_gaps": [], "suggestions": []})
    get_settings.cache_clear()
    return chosen["assessor"]


def test_demo_mode_without_live_llm_uses_the_stub(monkeypatch):
    assert _run(monkeypatch, live=False) == "StubFeatureSuggestionAssessor"


def test_live_llm_uses_the_sphere_assessor_even_in_demo_mode(monkeypatch):
    assert _run(monkeypatch, live=True) == "object"
