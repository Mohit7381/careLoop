"""app/agents/analyst/analyst.py — the positive-review pass is sampled, not
run over every positive review (PR #22 review fix, 2026-09-04).

On the fixture corpus, 499 of 600 reviews score >= 4 - 25 batches at
BATCH_SIZE=20, 5 sequential rounds at PARALLEL_BATCHES=5, versus the
complaint pass's own 1 round for 92 negatives. That is the actual dominant
cost (run 33: Analyst 226s vs 131s on main for the same prompt) - running
the two passes concurrently helps them not ADD, but does nothing about the
positive pass's own 5-round cost. Capping the sample to the most recent
reviews brings it to the same 1-round scale as the complaint pass.
"""
from app.agents.analyst.analyst import MAX_POSITIVE_SAMPLE, _most_recent_positive, run_analyst
from app.schemas.contracts import RunState, Snapshot, SnapshotRow


def test_most_recent_positive_caps_at_the_configured_limit():
    reviews = [{"text": "cepat", "score": 5, "at": f"2026-08-{i:02d}"} for i in range(1, 30)]

    sample = _most_recent_positive(reviews, limit=10)

    assert len(sample) == 10
    assert all(r["at"] >= "2026-08-20" for r in sample)  # the 10 most recent dates


def test_most_recent_positive_excludes_reviews_below_the_positive_threshold():
    reviews = [
        {"text": "biasa saja", "score": 3, "at": "2026-08-20"},
        {"text": "bagus", "score": 4, "at": "2026-08-19"},
        {"text": "buruk", "score": 1, "at": "2026-08-18"},
    ]

    sample = _most_recent_positive(reviews)

    assert len(sample) == 1
    assert sample[0]["text"] == "bagus"


def test_default_cap_matches_the_documented_batch_budget():
    # 60 reviews at BATCH_SIZE=20 is exactly 3 batches - one round at
    # PARALLEL_BATCHES=5, the same scale as the complaint pass's typical size.
    assert MAX_POSITIVE_SAMPLE == 60


def test_run_analyst_only_sends_the_capped_sample_to_the_positive_pass():
    calls = []

    def voc_llm(ctx):
        payload = ctx["reviews_batch"]
        if payload["polarity"] == "positive":
            calls.append(len(payload["reviews"]))
        return {"classifications": []}

    def funnel_llm(ctx):
        return {"done": True, "findings": []}

    reviews = ([{"text": "gagal bayar", "score": 1, "at": "2026-08-01"}] * 3
              + [{"text": "cepat sekali", "score": 5, "at": f"2026-08-{i:02d}"} for i in range(2, 92)])
    # 90 positive reviews in the fixture, well above MAX_POSITIVE_SAMPLE (60)

    state = RunState(
        run_id=1, journey="pd_checkout", window_start="2026-08-01", window_end="2026-08-30", demo_mode=False,
        snapshot=Snapshot(stages=[SnapshotRow(stage="created", dimension="all", segment="all",
                                              entered=1000, converted=950)]),
    )
    run_analyst(state, llm=funnel_llm, reviews=reviews, voc_llm=voc_llm)

    assert sum(calls) <= MAX_POSITIVE_SAMPLE
