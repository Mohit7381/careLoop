"""app/agents/analyst/analyst.py — a failure in the optional positive-review
pass must never fail the mandatory complaint pass or the whole run
(PR #22 review fix, 2026-09-04).

classify_reviews() already guards each sphere BATCH internally; this
guards everything else that can go wrong around it (a malformed
positive_themes_cfg entry, for example) — praise classification is
grounding for growth_ideas, never load-bearing.
"""
from unittest.mock import patch

from app.agents.analyst.analyst import run_analyst
from app.schemas.contracts import RunState, Snapshot, SnapshotRow


def _state() -> RunState:
    return RunState(
        run_id=1, journey="pd_checkout", window_start="2026-08-01", window_end="2026-08-30", demo_mode=False,
        snapshot=Snapshot(stages=[SnapshotRow(stage="created", dimension="all", segment="all",
                                              entered=1000, converted=950)]),
    )


def _fast_funnel_llm(ctx):
    return {"done": True, "findings": []}


def test_a_broken_positive_pass_does_not_fail_the_run():
    reviews = ([{"text": "gagal bayar", "score": 1, "at": "2026-08-10"}] * 3
              + [{"text": "cepat sekali", "score": 5, "at": "2026-08-11"}] * 3)

    def voc_llm(ctx):
        payload = ctx["reviews_batch"]
        if payload["polarity"] == "positive":
            raise RuntimeError("simulated failure outside classify_reviews' own per-batch guard")
        return {"classifications": []}

    out = run_analyst(_state(), llm=_fast_funnel_llm, reviews=reviews, voc_llm=voc_llm)

    # The run completes; the complaint pass and its findings are unaffected.
    assert out.status == "scanning_code"
    assert out.voc is not None
    # The praise pass produced nothing, honestly, rather than crashing the run.
    assert out.findings is not None


@patch("app.agents.analyst.analyst.classify_reviews")
def test_a_broken_positive_pass_still_lets_the_negative_pass_complete(mock_classify):
    def side_effect(llm, reviews, themes_cfg, lexical_fallback, scope_hint=None, polarity="negative"):
        if polarity == "positive":
            raise KeyError("routing_stage")  # e.g. a malformed positive_themes_cfg entry
        return ["payment/refund"] * len(reviews), {"classifier": "semantic"}

    mock_classify.side_effect = side_effect

    reviews = [{"text": "gagal bayar", "score": 1, "at": "2026-08-10"}]
    out = run_analyst(_state(), llm=_fast_funnel_llm, reviews=reviews, voc_llm=lambda ctx: {})

    assert out.voc.reviews_meta["negatives"] == 1
    assert out.status == "scanning_code"
