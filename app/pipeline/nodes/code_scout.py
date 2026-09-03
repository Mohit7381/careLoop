"""
Agent 3 — Code Scout node wrapper. OWNER: Harshit (logic) / Mohit (wiring).

Thin adapter: converts the orchestrator's dict GraphState to/from the
pydantic RunState that app.agents.code_scout.node.code_scout_node speaks
natively, and injects the search client + assessor (fixture-backed in
demo_mode, live GitLab + a rule-based stand-in assessor otherwise — the
real `code-gap-assessment` sphere use case still needs wiring the same
way analyst.py's _sphere_llm does once Nakul confirms the params shape).
"""
from pathlib import Path

from app.agents.code_scout.assessor import StubCodeGapAssessor
from app.agents.code_scout.node import code_scout_node as _code_scout_node
from app.agents.code_scout.search_client import FixtureSearchClient, LiveGitlabSearchClient
from app.config import get_settings
from app.pipeline.state import GraphState
from app.schemas.contracts import RunState

FIXTURES_DIR = Path("fixtures/code_scout")


def code_scout_node(state: GraphState) -> GraphState:
    run_state = RunState(**{k: v for k, v in state.items() if k != "error"})
    settings = get_settings()

    if state.get("demo_mode", True):
        search_client = FixtureSearchClient(FIXTURES_DIR)
    else:
        search_client = LiveGitlabSearchClient(host=settings.gitlab_base_url, token=settings.gitlab_read_token)
    assessor = StubCodeGapAssessor()  # TODO(Harshit/Nakul): swap for the real code-gap-assessment sphere call

    result = _code_scout_node(run_state, search_client=search_client, assessor=assessor)

    return {**state, "status": "reporting", "code_gaps": [g.model_dump() for g in result["code_gaps"]]}
