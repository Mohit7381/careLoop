"""LangGraph wiring - STUB.

Mohit owns the real orchestrator (build table row 4: "Orchestrator + Reporter
+ PRD + delivery"). This file doesn't exist in his repo yet as far as I know
- it shows how code_scout_node plugs into a sequential StateGraph so the
integration shape is proven before that repo exists. Swap this whole file
for his real graph.py once you have access; only the code_scout wiring
pattern below (the add_node call + its position between "analyst" and
"reporter") needs to survive that swap.

The fetcher/analyst/reporter nodes here are throwaway placeholders, NOT
real implementations of Alief/Nakul/Mohit's workstreams - they exist only
so the graph can be built and run end-to-end. Don't ship them.
"""
from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agents.code_scout.assessor import CodeGapAssessor
from app.agents.code_scout.node import code_scout_node
from app.agents.code_scout.search_client import SearchClient
from app.schemas.contracts import RunState


def _placeholder_fetcher_node(state: RunState) -> dict:
    """Stand-in for Agent 1 (Alief). Real node populates state.snapshot."""
    return {"status": "extracting"}


def _placeholder_analyst_node(state: RunState) -> dict:
    """Stand-in for Agent 2 (Nakul). Real node populates state.findings and
    state.drilldown_trail. This placeholder is a passthrough - findings must
    already be present on the state handed to the graph, or code_scout has
    nothing to process (see tests/test_graph_wiring.py)."""
    return {"status": "analyzing"}


def _placeholder_reporter_node(state: RunState) -> dict:
    """Stand-in for Agent 4 (Mohit). Real node populates trend_report and
    prd_draft, then delivers via Garuda."""
    return {"status": "completed"}


def build_graph(*, search_client: SearchClient, assessor: CodeGapAssessor):
    """Sequential pipeline: Fetcher -> Analyst -> Code Scout -> Reporter.

    Only "code_scout" below is a real node. search_client/assessor are
    injected here (not hardcoded) so the same graph-building code works for
    both Day-1 fixture mode and Day-2 live mode - just pass a different
    pair of implementations in.
    """
    graph = StateGraph(RunState)

    graph.add_node("fetcher", _placeholder_fetcher_node)
    graph.add_node("analyst", _placeholder_analyst_node)
    graph.add_node(
        "code_scout",
        partial(code_scout_node, search_client=search_client, assessor=assessor),
    )
    graph.add_node("reporter", _placeholder_reporter_node)

    graph.add_edge(START, "fetcher")
    graph.add_edge("fetcher", "analyst")
    graph.add_edge("analyst", "code_scout")
    graph.add_edge("code_scout", "reporter")
    graph.add_edge("reporter", END)

    return graph.compile()
