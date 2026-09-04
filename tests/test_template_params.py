"""Every live sphere call must send exactly the key its template renders.

Sphere substitutes only the placeholder a template names and silently ignores
everything else, so a wrong key does not fail — it sends an EMPTY prompt. The
first live API run did exactly that: the model replied "analysis_context is
empty" and the run finished with zero warehouse findings and no error.
"""
import json

import pytest

from app.integrations import sphere
from app.integrations.sphere import TEMPLATE_PARAM, TemplateParamError, _check_params


def test_every_provisioned_use_case_is_in_the_registry():
    ids = json.load(open("fixtures/pd_checkout/sphere_ids.json"))
    assert {u["name"] for u in ids["use_cases"]} == set(TEMPLATE_PARAM)


def test_a_wrong_key_is_refused_not_sent_empty():
    with pytest.raises(TemplateParamError):
        _check_params("funnel-hypothesis-generation", {"top_gap": "x", "phase1": "y"})
    with pytest.raises(TemplateParamError):
        _check_params("trend-narrative", {"delta_rows": "[]"})
    _check_params("trend-narrative", {"delta_table": "[]"})       # correct: no raise


def _capture(monkeypatch):
    sent = {}
    def fake_call(self, use_case, template_id, params):
        sent["use_case"], sent["params"] = use_case, params
        _check_params(use_case, params)
        return {}
    monkeypatch.setattr(sphere.SphereClient, "call", fake_call)
    monkeypatch.setattr(sphere, "_app_token", lambda: "t")
    monkeypatch.setattr(sphere, "_live_llm_wanted", lambda demo: True)
    return sent


def test_the_analyst_node_sends_analysis_context(monkeypatch):
    sent = _capture(monkeypatch)
    from app.pipeline.nodes.analyst import _sphere_llm
    _sphere_llm()({"top_gap": {"lost": 1}, "phase1": {}})
    assert set(sent["params"]) == {"analysis_context"}
    assert json.loads(sent["params"]["analysis_context"])["top_gap"] == {"lost": 1}


@pytest.mark.parametrize("use_case", sorted(TEMPLATE_PARAM))
def test_the_factory_always_wraps_under_the_registered_key(monkeypatch, use_case):
    sent = _capture(monkeypatch)
    llm = sphere.make_use_case_llm(use_case, demo_mode=True)
    assert llm is not None
    llm({"anything": [1, 2], "else": "x"})
    assert set(sent["params"]) == {TEMPLATE_PARAM[use_case]}


def test_create_timeout_covers_a_full_synchronous_model_call():
    """POST /v1/chat-ai/requests blocks for the whole model call (live-verified
    2026-09-04); a 15 s create timeout killed every real call in run 11. Keep
    it at or above the ~60 s ingress window so the client, not the gateway,
    is never the thing that cuts a healthy call."""
    from app.integrations import sphere
    assert sphere.CREATE_TIMEOUT_S >= 60
