"""
Agent 2 — Analyst node wrapper. OWNER: Nakul (logic) / Mohit (wiring).

Thin adapter: converts the orchestrator's dict GraphState to/from the
pydantic RunState that app.agents.analyst.analyst.run_analyst speaks
natively, and supplies the `llm` callable (sphere-platform in real mode,
SphereClient(mode="replay") in demo_mode — a real recorded LLM session
against the real fixture data, not a hand-written script: see
fixtures/llm_replay/funnel-hypothesis-generation/{0..4}.json, 4
drill-down turns landing on 5 real findings including the rx-gated
30.0%-vs-39.0% one. Switched from a 2-turn hand-written stand-in per
PR #1 review M2 — that script reproduced less than the real verified
run already sitting in the tree.
"""
import json
from pathlib import Path
from typing import Any

from app.agents.analyst.analyst import run_analyst
from app.config import get_settings
from app.integrations.sphere import SphereClient
from app.pipeline.state import GraphState
from app.schemas.contracts import RunState

SPHERE_IDS_PATH = Path("fixtures/pd_checkout/sphere_ids.json")


def _demo_llm() -> Any:
    client = SphereClient(mode="replay")
    return lambda ctx: client.call("funnel-hypothesis-generation", 0, ctx)


def _sphere_llm() -> Any:
    settings = get_settings()
    ids = json.loads(SPHERE_IDS_PATH.read_text())
    template_id = next(
        u["template_id"] for u in ids["use_cases"] if u["name"] == settings.llm_use_case_funnel_dropoff
    )
    client = SphereClient(mode="sphere", service_type=settings.sphere_platform_service_type)

    def llm(ctx: dict) -> dict:
        params = {k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v)) for k, v in ctx.items()}
        return client.call(settings.llm_use_case_funnel_dropoff, template_id, params)

    return llm


def analyst_node(state: GraphState) -> GraphState:
    run_state = RunState(**{k: v for k, v in state.items() if k != "error"})
    llm = _demo_llm() if state.get("demo_mode", True) else _sphere_llm()

    out = run_analyst(run_state, llm=llm)

    return {**state, **out.model_dump()}
