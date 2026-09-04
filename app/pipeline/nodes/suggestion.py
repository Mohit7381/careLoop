"""
Suggestion node wrapper. OWNER: Harshit (logic) / Mohit (wiring).

Wires Code Scout's alternate Rev 3 flow (explore -> suggest -> verify,
app/agents/code_scout/suggestion_node.py) into the graph, alongside the
existing find_gap()-based code_scout_node rather than replacing it: a
Suggestion is a generative improvement idea (tech, business, or process —
contracts.py decision #11) and a CodeGap is a diagnosed bug with a cited
mechanism. A finding can produce either, both, or neither.

This was previously built and fully tested but deliberately left out of
app/pipeline/graph.py pending a three-way call (Nakul/Mohit/Harshit) on
whether it ships — Harshit asked for it explicitly (2026-09-04 hackathon
chat), so it's wired in here.
"""
import logging
from pathlib import Path

from app.agents.code_scout.explore_search_client import FixtureExploreSearchClient, LiveGitlabExploreSearchClient
from app.agents.code_scout.suggestion_assessor import SpherePlatformFeatureSuggestionAssessor, StubFeatureSuggestionAssessor
from app.agents.code_scout.suggestion_node import suggestion_code_scout_node as _suggestion_code_scout_node
from app.config import get_settings
from app.pipeline.state import GraphState
from app.schemas.contracts import RunState

logger = logging.getLogger("careloop.suggestions")

FIXTURES_DIR = Path("fixtures/code_scout_suggestions")


def suggestion_node(state: GraphState) -> GraphState:
    run_state = RunState(**{k: v for k, v in state.items() if k not in ("error", "reviews")})
    settings = get_settings()

    # Same gate as every other node: LIVE_LLM=true means real sphere + GitLab
    # even over the frozen fixture. This node checked demo_mode alone, so a
    # live run (runs 16-22) shipped the scripted demo suggestions under a live
    # header while the Analyst, Code Scout and PRD were real.
    from app.integrations.sphere import _live_llm_wanted
    if not _live_llm_wanted(state.get("demo_mode", True)):
        search_client = FixtureExploreSearchClient(FIXTURES_DIR)
        assessor = StubFeatureSuggestionAssessor()
    else:
        search_client = LiveGitlabExploreSearchClient(host=settings.gitlab_base_url, token=settings.gitlab_read_token)
        assessor = SpherePlatformFeatureSuggestionAssessor()

    try:
        result = _suggestion_code_scout_node(run_state, search_client=search_client, assessor=assessor)
    except Exception as exc:                      # a suggestions outage must not lose the run
        # Run 23 failed here after the Analyst and Code Scout had already
        # succeeded, so seven findings and seven gaps never got a report or a
        # PRD. Suggestions are the optional layer: ship none, say so.
        logger.warning("suggestion node failed (%s) — continuing without suggestions", exc)
        return {**state, "suggestions": []}

    return {**state, "suggestions": [s.model_dump() for s in result["suggestions"]]}
