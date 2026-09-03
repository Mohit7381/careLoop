"""Proves code_scout_node actually wires into a real LangGraph StateGraph and
survives a compiled run - not just a direct function call. The placeholder
fetcher/analyst/reporter nodes are throwaway (see app/orchestrator/graph.py's
docstring); this only exercises the code_scout wiring pattern.
"""
from pathlib import Path

from app.agents.code_scout.assessor import StubCodeGapAssessor
from app.agents.code_scout.search_client import FixtureSearchClient
from app.orchestrator.graph import build_graph
from app.schemas.contracts import EvidenceItem, Finding, RunState

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "code_scout"


def test_code_scout_node_runs_inside_a_compiled_langgraph():
    graph = build_graph(
        search_client=FixtureSearchClient(FIXTURES_DIR),
        assessor=StubCodeGapAssessor(),
    )

    initial_state = RunState(
        run_id=1,
        window_start="2026-08-04",
        window_end="2026-09-03",
        findings=[
            Finding(
                rank=1,
                origin="warehouse",
                stage="consultation",
                hypothesis="51,321/wk consultations killed by silent payment-timeout abandon script",
                confidence=0.9,
                confirm_via="check re-engagement CT events post-cancel",
                evidence=[
                    EvidenceItem(type="snapshot", metric="system_cancelled_count", value=51321)
                ],
            )
        ],
    )

    final_state = graph.invoke(initial_state)

    assert final_state["status"] == "completed"
    code_gaps = final_state["code_gaps"]
    assert len(code_gaps) == 1
    gap = code_gaps[0]
    assert gap.mechanism_found is True
    assert gap.file.endswith("ConsultationDao.java")
    assert gap.line == 146
    assert gap.gap_class == "missing_retention_hook"
