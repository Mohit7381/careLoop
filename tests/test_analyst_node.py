"""End-to-end Analyst node on fixtures with a stubbed LLM — the golden run."""
import json
from pathlib import Path

from app.agents.analyst.analyst import run_analyst
from app.schemas.contracts import RunState, Snapshot

FIX = Path(__file__).parent.parent / "fixtures" / "pd_checkout"


def test_golden_run(cohort_cuts, reviews):
    state = RunState(
        run_id=1, journey="pd_checkout",
        window_start="2026-08-27", window_end="2026-09-02",
        prev_window_start="2026-08-20", prev_window_end="2026-08-26",
        status="analyzing",
        snapshot=Snapshot(**json.loads((FIX / "snapshot.json").read_text())),
    )
    llm_script = iter([
        {"done": False, "next_question": {"dimension": "consultation_required",
                                          "rationale": "rx gating vs the 64% abandonment"}},
        {"done": True, "findings": [{
            "hypothesis": "rx-gated orders confirm at 30.0% vs 39.0% non-rx (-9pp)",
            "stage": "pharmacy_checkout", "confidence": "high",
            "evidence": ["255293", "76641", "391898", "152981"],
            "confirm_via": "A/B a prescription-cart resume flow; watch rx confirm rate"}]},
    ])
    out = run_analyst(state, llm=lambda ctx: next(llm_script),
                      cohort_cuts=cohort_cuts, reviews=reviews)

    # warehouse finding survived the evidence gate
    wh = [f for f in out.findings if f.origin == "warehouse"]
    assert wh and wh[0].stage == "pharmacy_checkout"
    # journey_events populated from real ct_events (decision #11) - "orders"
    # in the hypothesis stems to the fixture's order_placed/order_abandoned
    assert "order_placed" in wh[0].journey_events or "order_abandoned" in wh[0].journey_events
    # VoC escalations appended after warehouse ranks
    voc = [f for f in out.findings if f.origin == "voc"]
    assert {f.theme for f in voc} == {"payment/refund", "consultation/doctor"}
    assert all(f.rank > wh[-1].rank for f in voc)
    # trail persisted, status advanced
    assert out.drilldown_trail and out.drilldown_trail[0].dimension == "consultation_required"
    assert out.status == "scanning_code"
    assert out.voc.reviews_meta["negatives"] == 92
