"""app/pipeline/nodes/reporter.py — attaching a measured metric to a
ShippedFix Code Scout already detected (closed-loop impact, 2026-09-04).

PR #22 review (Nakul): fix["stage"] is a routing CATEGORY
(pharmacy_checkout/payments/…) and StageDelta.stage is a funnel STAGE
(created/confirmed/delivered) — different vocabularies. These tests use
deliberately DIFFERENT values for the two so a regression back to comparing
them directly (instead of against top_gap_to_stage) fails loudly, unlike
the original version of these tests, which used "created" for both and let
that exact bug hide behind a passing suite.
"""
from app.pipeline.nodes.reporter import _delta_rows, _measure_shipped_impact
from app.schemas.contracts import AdoptionDelta, StageDelta


def _fix(finding_rank=1, stage="pharmacy_checkout") -> dict:
    return {
        "finding_rank": finding_rank, "origin": "warehouse", "stage": stage, "repo": "timor/oms",
        "remedy_proposal": "Retention push before final abandon",
        "evidence_file": "Retention.java", "evidence_line": 42,
        "commit": {"sha": "abc123def456", "short_sha": "abc123de", "author": "a",
                   "date": "2026-08-20", "message": "m"},
    }


def test_prefers_an_adoption_event_named_on_the_findings_own_journey_events():
    fix = _fix()
    deltas = [StageDelta(stage="created", previous_rate=0.5, current_rate=0.6, delta_pp=10.0)]
    adoption = [AdoptionDelta(feature="retention_push_sent", previous_count=100, current_count=150, trend="faster")]
    events_by_rank = {1: {"retention_push_sent"}}

    out = _measure_shipped_impact(fix, deltas, adoption, events_by_rank, top_gap_to_stage="created")

    assert out["metric_ref"] == "adoption:retention_push_sent"
    assert out["metric_unit"] == "events"
    assert out["previous_value"] == 100.0
    assert out["current_value"] == 150.0
    assert out["pct_change"] == 50.0


def test_falls_back_to_the_runs_top_gap_stage_when_no_adoption_event_matches():
    fix = _fix(stage="pharmacy_checkout")  # routing category — deliberately NOT "created"
    deltas = [StageDelta(stage="created", previous_rate=0.5, current_rate=0.6, delta_pp=10.0)]
    adoption: list[AdoptionDelta] = []
    events_by_rank: dict[int, set] = {1: set()}

    out = _measure_shipped_impact(fix, deltas, adoption, events_by_rank, top_gap_to_stage="created")

    assert out["metric_ref"] == "stage:created"
    assert out["metric_unit"] == "%"
    assert out["previous_value"] == 50.0
    assert out["current_value"] == 60.0
    assert out["pct_change"] == 20.0


def test_returns_nothing_measurable_when_top_gap_to_stage_is_unknown():
    fix = _fix(stage="pharmacy_checkout")
    deltas = [StageDelta(stage="created", previous_rate=0.5, current_rate=0.6, delta_pp=10.0)]
    adoption: list[AdoptionDelta] = []
    events_by_rank: dict[int, set] = {1: set()}

    out = _measure_shipped_impact(fix, deltas, adoption, events_by_rank, top_gap_to_stage=None)

    assert out == {}


def test_returns_nothing_measurable_rather_than_pick_an_unrelated_row():
    fix = _fix(stage="pharmacy_checkout")
    deltas = [StageDelta(stage="created", previous_rate=0.5, current_rate=0.6, delta_pp=10.0)]
    adoption: list[AdoptionDelta] = []
    events_by_rank: dict[int, set] = {1: set()}

    out = _measure_shipped_impact(fix, deltas, adoption, events_by_rank, top_gap_to_stage="some_other_stage")

    assert out == {}


def test_a_maturing_stage_delta_is_never_used_for_impact():
    fix = _fix(stage="pharmacy_checkout")
    deltas = [StageDelta(stage="delivered", previous_rate=0.9, current_rate=0.95, delta_pp=5.0, maturing=True)]

    out = _measure_shipped_impact(fix, deltas, [], {1: set()}, top_gap_to_stage="delivered")

    assert out == {}


def test_delta_rows_only_includes_shipped_fixes_that_have_a_measured_metric():
    unmeasured = _fix(finding_rank=1)
    measured = {**_fix(finding_rank=2), "metric_name": "conversion rate at 'created'",
                "metric_unit": "%", "previous_value": 50.0, "current_value": 60.0, "pct_change": 20.0}

    rows = _delta_rows([], [], set(), [], [unmeasured, measured])

    ids = [r["id"] for r in rows]
    assert "shipped:1" not in ids
    assert "shipped:2" in ids
    row = next(r for r in rows if r["id"] == "shipped:2")
    assert row["pct_change"] == 20.0
