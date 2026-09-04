"""app/pipeline/nodes/suggestion.py — wires Code Scout's alternate Rev 3
flow (explore -> suggest -> verify) into the graph, previously built+tested
but left unwired pending a three-way decision (Nakul/Mohit/Harshit).
Wired in per Harshit's explicit ask (2026-09-04 hackathon chat)."""
from app.pipeline.nodes.suggestion import suggestion_node
from app.pipeline.state import initial_state


def test_demo_mode_produces_real_mixed_suggestions_from_fixtures():
    """End-to-end on the real fixtures (fixtures/code_scout_suggestions/) —
    proves the wrapper actually wires FixtureExploreSearchClient +
    StubFeatureSuggestionAssessor, not just that it doesn't crash."""
    state = initial_state(
        run_id=1, window_start="a", window_end="b", demo_mode=True, journey="pd_checkout",
    )
    state["findings"] = [
        {
            "rank": 1, "origin": "warehouse", "stage": "consultation",
            "hypothesis": "consultations killed by silent payment-timeout abandon script",
            "confidence": "high", "confirm_via": "x",
        }
    ]

    result = suggestion_node(state)
    suggestions = result["suggestions"]

    assert suggestions, "the proven consultation fixture should produce at least one suggestion"
    assert all(isinstance(s, dict) for s in suggestions)  # dumped to plain dicts for GraphState
    types = {s["suggestion_type"] for s in suggestions}
    assert "business" in types and "tech" in types  # the whole point: not tech-only


def test_a_finding_with_no_matching_fixture_produces_no_suggestions_honestly():
    """No hand-verified area for this finding -> empty, not a fabricated
    generic placeholder (StubFeatureSuggestionAssessor's own discipline)."""
    state = initial_state(run_id=1, window_start="a", window_end="b", demo_mode=True, journey="pd_checkout")
    state["findings"] = [
        {
            "rank": 1, "origin": "warehouse", "stage": "stock",
            "hypothesis": "totally unrelated finding with no proven fixture area",
            "confidence": "low", "confirm_via": "x",
        }
    ]

    result = suggestion_node(state)

    assert result["suggestions"] == []
