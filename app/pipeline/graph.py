"""
The CareLoop LangGraph pipeline: Fetcher -> Analyst -> Code Scout ->
Suggestion -> Reporter -> PRD Generator -> Report Writer -> Delivery.
Sequential per the team's rev-1 spec (no parallel branches yet).

Suggestion (Code Scout's Rev 3 alternate flow, contracts.py decision #11)
runs alongside code_scout rather than replacing it: a Suggestion is a
generative tech/business/process improvement idea, a CodeGap is a
diagnosed bug with a cited mechanism — a finding can produce either, both,
or neither. Was previously built+tested but left unwired pending a
three-way call (Nakul/Mohit/Harshit); wired in per Harshit's explicit ask.
"""
from langgraph.graph import END, StateGraph

from app.pipeline.nodes.analyst import analyst_node
from app.pipeline.nodes.code_scout import code_scout_node
from app.pipeline.nodes.delivery import delivery_node
from app.pipeline.nodes.fetcher import fetcher_node
from app.pipeline.nodes.prd_generator import prd_generator_node
from app.pipeline.nodes.report_writer import report_writer_node
from app.pipeline.nodes.reporter import reporter_node
from app.pipeline.nodes.suggestion import suggestion_node
from app.pipeline.state import GraphState


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("fetcher", fetcher_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("code_scout", code_scout_node)
    graph.add_node("suggestion", suggestion_node)
    graph.add_node("reporter", reporter_node)
    graph.add_node("prd_generator", prd_generator_node)
    graph.add_node("report_writer", report_writer_node)
    graph.add_node("delivery", delivery_node)

    graph.set_entry_point("fetcher")
    graph.add_edge("fetcher", "analyst")
    graph.add_edge("analyst", "code_scout")
    graph.add_edge("code_scout", "suggestion")
    graph.add_edge("suggestion", "reporter")
    graph.add_edge("reporter", "prd_generator")
    graph.add_edge("prd_generator", "report_writer")
    graph.add_edge("report_writer", "delivery")
    graph.add_edge("delivery", END)

    return graph.compile()


compiled_graph = build_graph()
