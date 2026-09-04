"""app/agents/analyst/analyst.py — negative and positive VoC classification
must run CONCURRENTLY, not sequentially (2026-09-04 bug fix).

Sequential execution added the two passes' wall-clock time together once
the positive pass was introduced, which read as "the analysing stage is
running but nothing is happening" for however long the now-serialized
second pass took. (Correction, PR #22 review: sphere's create call is
synchronous on this deployment — a batch is ~20-45s, not "up to ~180s
polling" as an earlier commit message here claimed; concurrency still
matters because the passes' costs were adding instead of overlapping, but
the dominant cost of the positive pass is its own batch COUNT — see
test_analyst_positive_sample_cap.py — not the scheduling relative to the
negative pass.)"""
import time

from app.agents.analyst.analyst import run_analyst
from app.schemas.contracts import RunState, Snapshot, SnapshotRow

CALL_DELAY = 0.3


def _slow_voc_llm(ctx):
    time.sleep(CALL_DELAY)
    return {"classifications": []}


def _fast_funnel_llm(ctx):
    return {"done": True, "findings": []}


def _state() -> RunState:
    return RunState(
        run_id=1, journey="pd_checkout", window_start="2026-08-01", window_end="2026-08-30", demo_mode=False,
        snapshot=Snapshot(stages=[SnapshotRow(stage="created", dimension="all", segment="all",
                                              entered=1000, converted=950)]),
    )


def test_negative_and_positive_voc_classification_run_concurrently():
    reviews = ([{"text": "gagal bayar", "score": 1, "at": "2026-08-10"}] * 3
              + [{"text": "cepat sekali", "score": 5, "at": "2026-08-11"}] * 3)

    t0 = time.monotonic()
    run_analyst(_state(), llm=_fast_funnel_llm, reviews=reviews, voc_llm=_slow_voc_llm)
    elapsed = time.monotonic() - t0

    # Sequential would take ~2x CALL_DELAY; concurrent takes ~1x. Generous
    # margin for CI scheduling jitter, but well short of double.
    assert elapsed < CALL_DELAY * 1.6, (
        f"VoC classification took {elapsed:.2f}s — looks sequential, not concurrent "
        f"(expected close to {CALL_DELAY:.2f}s)")
