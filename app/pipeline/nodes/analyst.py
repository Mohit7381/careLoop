"""
Agent 2 — Analyst node wrapper. OWNER: Nakul (logic) / Mohit (wiring).

Thin adapter: converts the orchestrator's dict GraphState to/from the
pydantic RunState that app.agents.analyst.analyst.run_analyst speaks
natively, and supplies the `llm` callable (sphere-platform in real mode,
a scripted replay of the real verified golden run in demo_mode — no
`fixtures/llm_replay/*` exist yet, so SphereClient(mode="replay") isn't
runnable as-is; this scripted stand-in is what keeps demo_mode working
end-to-end without live credentials).
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
    """
    Scripted 2-turn replay of the real verified golden run (see
    tests/test_analyst_node.py) — rx-gated orders confirm 30.0% vs 39.0%,
    stage=pharmacy_checkout, confidence=high. Not a live LLM call.
    """
    script = iter(
        [
            {
                "done": False,
                "next_question": {
                    "dimension": "consultation_required",
                    "rationale": "rx gating vs the overall abandonment rate",
                },
            },
            {
                "done": True,
                "findings": [
                    {
                        "hypothesis": "rx-gated orders confirm at 30.0% vs 39.0% non-rx (-9pp)",
                        "stage": "pharmacy_checkout",
                        "confidence": "high",
                        "evidence": ["255293", "76641", "391898", "152981"],
                        "confirm_via": "A/B a prescription-cart resume flow; watch rx confirm rate",
                    }
                ],
            },
        ]
    )
    return lambda ctx: next(script)


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
