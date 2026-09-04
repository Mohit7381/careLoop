"""app/agents/analyst/phase2.py — growth_ideas, the drill-down's concluding-
turn output for GROWING transactions rather than diagnosing a loss
(2026-09-04). Same aggregate_tool/journey_cfg fixtures as test_phase2.py."""
from app.agents.analyst.aggregate_tool import AggregateTool
from app.agents.analyst.phase2 import run_drilldown
from app.schemas.contracts import GrowthIdea

GAP = {"from_stage": "created", "to_stage": "confirmed", "lost": 417569, "share_of_prev": 0.6452}
ROUTING = ["pharmacy_checkout", "payments", "delivery", "stock", "re_engagement", "consultation"]


def _make_llm(script):
    calls, last = iter(script), {}

    def llm(ctx):
        nonlocal last
        try:
            last = next(calls)
        except StopIteration:
            pass
        return last

    return llm


def test_growth_idea_grounded_in_funnel_data_requires_evidence():
    idea = GrowthIdea(title="t", description="d", rationale="r",
                      inspiration="funnel_data",
                      evidence=[{"type": "drilldown", "metric": "m", "value": 1.0}])
    assert idea.inspiration == "funnel_data"

    import pytest
    with pytest.raises(ValueError):
        GrowthIdea(title="t", description="d", rationale="r", inspiration="funnel_data", evidence=[])


def test_growth_idea_from_industry_pattern_must_carry_no_evidence():
    idea = GrowthIdea(title="t", description="d", rationale="r", inspiration="industry_pattern")
    assert idea.evidence == []

    import pytest
    with pytest.raises(ValueError):
        GrowthIdea(title="t", description="d", rationale="r", inspiration="industry_pattern",
                  evidence=[{"type": "drilldown", "metric": "m", "value": 1.0}])


def test_run_drilldown_returns_growth_ideas_from_the_concluding_turn(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    llm = _make_llm([
        {"done": True, "findings": [], "growth_ideas": [
            {"title": "One-tap saved payment method", "description": "Let repeat buyers skip payment entry.",
             "rationale": "Reduces friction at the confirmed step.",
             "inspiration": "industry_pattern"},
            {"title": "Cart-recovery nudge for rx-gated orders",
             "description": "Prompt users with a reminder when an rx-gated order stalls.",
             "rationale": "255293 rx-gated orders entered this stage",
             "inspiration": "funnel_data", "evidence": ["255293"]},
        ]},
    ])

    _, trail, growth_ideas = run_drilldown(llm, tool, GAP, {}, ROUTING, "pharmacy_checkout")

    assert len(growth_ideas) == 2
    industry, funnel = growth_ideas
    assert industry.inspiration == "industry_pattern"
    assert industry.evidence == []
    assert funnel.inspiration == "funnel_data"
    assert any(abs(e.value - 255293) < 1 for e in funnel.evidence)


def test_a_malformed_growth_idea_is_dropped_not_crashed_on(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    llm = _make_llm([
        {"done": True, "findings": [], "growth_ideas": [
            # funnel_data claimed but no evidence given -> invalid, must be dropped
            {"title": "t", "description": "d", "rationale": "r", "inspiration": "funnel_data", "evidence": []},
        ]},
    ])

    _, trail, growth_ideas = run_drilldown(llm, tool, GAP, {}, ROUTING, "pharmacy_checkout")

    assert growth_ideas == []


def test_growth_ideas_are_never_parsed_on_a_non_concluding_turn(cohort_cuts, journey_cfg):
    """A stray growth_ideas key on a mid-run turn (done=False) must not leak
    through — the prompt is told never to send it, but the parser should not
    trust that blindly either."""
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    llm = _make_llm([
        {"done": False, "next_question": {"dimension": "pd_category", "rationale": "r"},
         "growth_ideas": [{"title": "premature", "description": "d", "rationale": "r",
                          "inspiration": "industry_pattern"}]},
        {"done": True, "findings": []},
    ])

    _, trail, growth_ideas = run_drilldown(llm, tool, GAP, {}, ROUTING, "pharmacy_checkout")

    assert growth_ideas == []
