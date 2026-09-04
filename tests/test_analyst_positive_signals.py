"""app/agents/analyst/analyst.py — wiring top_strength + positive review
classification through to growth_ideas end to end (2026-09-04)."""
from app.agents.analyst.analyst import run_analyst
from app.schemas.contracts import RunState, Snapshot, SnapshotRow


def _scripted_llm(ctx):
    if ctx.get("drilldown_trail"):
        assert "top_strength" in ctx and "positive_voc_signals" in ctx
        ideas = []
        if ctx["top_strength"]:
            ideas.append({
                "title": "Extend the strong checkout step", "description": "d",
                "rationale": f"conversion_rate {ctx['top_strength']['conversion_rate']}",
                "inspiration": "funnel_data",
                "evidence": [f"top_strength conversion_rate: {ctx['top_strength']['conversion_rate']}"],
            })
        if ctx["positive_voc_signals"]:
            count = ctx["positive_voc_signals"][0]["count"]
            ideas.append({
                "title": "Double down on fast delivery", "description": "d",
                "rationale": f"{count} praise this already", "inspiration": "positive_review",
                "evidence": [f"{count} positive reviews"],
            })
        return {"done": True, "findings": [], "growth_ideas": ideas}
    return {"done": False, "next_question": {"dimension": "pd_category", "rationale": "r"}}


def _reviews():
    negative = [{"text": "gagal bayar terus", "score": 1, "at": "2026-08-10"} for _ in range(3)]
    positive = [{"text": "pengiriman sangat cepat", "score": 5, "at": "2026-08-11"} for _ in range(8)]
    return negative + positive


def test_run_analyst_wires_top_strength_and_positive_voc_into_growth_ideas():
    state = RunState(
        run_id=1, journey="pd_checkout", window_start="2026-08-01", window_end="2026-08-30", demo_mode=True,
        snapshot=Snapshot(stages=[
            SnapshotRow(stage="created", dimension="all", segment="all", entered=1000, converted=950),
            SnapshotRow(stage="confirmed", dimension="all", segment="all", entered=950, converted=200),
        ]),
    )

    out = run_analyst(state, llm=_scripted_llm, reviews=_reviews())

    inspirations = {g.inspiration for g in out.growth_ideas}
    assert "funnel_data" in inspirations
    assert "positive_review" in inspirations
    funnel_idea = next(g for g in out.growth_ideas if g.inspiration == "funnel_data")
    assert any(abs(e.value - 0.95) < 0.001 for e in funnel_idea.evidence)


def test_run_analyst_skips_positive_classification_when_no_positive_themes_configured(monkeypatch):
    """A journey with no positive_themes configured yet must not crash — just
    produce no positive_voc_signals, matching the "hold off on the taxonomy"
    escape hatch this feature was designed to support."""
    import app.agents.analyst.analyst as analyst_module

    real_load_journey = analyst_module.load_journey

    def load_journey_without_positive_themes(journey):
        cfg = dict(real_load_journey(journey))
        cfg["voc"] = {k: v for k, v in cfg["voc"].items() if k != "positive_themes"}
        return cfg

    monkeypatch.setattr(analyst_module, "load_journey", load_journey_without_positive_themes)

    state = RunState(
        run_id=1, journey="pd_checkout", window_start="2026-08-01", window_end="2026-08-30", demo_mode=True,
        snapshot=Snapshot(stages=[
            SnapshotRow(stage="created", dimension="all", segment="all", entered=1000, converted=950),
        ]),
    )

    def llm(ctx):
        assert ctx.get("positive_voc_signals") == []
        return {"done": True, "findings": []}

    out = run_analyst(state, llm=llm, reviews=_reviews())
    assert out.growth_ideas == []
