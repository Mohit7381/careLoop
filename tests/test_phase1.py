"""Golden asserts from the frozen PD baseline — if these break, either the
fixture changed or the math regressed."""
from app.agents.analyst import phase1
from app.schemas.contracts import SnapshotRow


def test_funnel_table_golden(snapshot, journey_cfg):
    table = phase1.funnel_table(snapshot, journey_cfg["stages"])
    assert [r["stage"] for r in table] == ["created", "confirmed", "delivered"]
    assert table[0]["count"] == 647191
    assert abs(table[1]["conversion_from_previous"] - 0.3548) < 0.001  # 35.5%
    assert abs(table[2]["conversion_from_previous"] - 0.6923) < 0.001  # censoring visible


def test_largest_drop_is_created_to_confirmed(snapshot, journey_cfg):
    table = phase1.funnel_table(snapshot, journey_cfg["stages"])
    gap = phase1.largest_drop(table)
    assert gap["from_stage"] == "created" and gap["to_stage"] == "confirmed"
    assert gap["lost"] == 647191 - 229622
    assert abs(gap["share_of_prev"] - 0.6452) < 0.001


def test_reason_clustering_normalizes_case_and_splits_artifacts(snapshot, journey_cfg):
    clusters = phase1.cluster_reasons(snapshot.reasons, journey_cfg["artifact_reasons"])
    # casing merged: "Items unavailable" + "ITEMS UNAVAILABLE"
    assert clusters["user_reasons"]["items unavailable"] == 2474 + 1433
    # rx-gated + non split rows merged under one normalized key
    assert clusters["user_reasons"]["user abandon the cart"] == 79515 + 32478
    # artifacts split out, not counted as user abandonment
    assert clusters["artifact_reasons"]["address changed"] == 33898 + 1213
    assert 0.14 < clusters["artifact_share"] < 0.19


def test_k_suppression():
    rows = [SnapshotRow(stage="s", dimension="d", segment="tiny", entered=12, converted=3),
            SnapshotRow(stage="s", dimension="d", segment="big", entered=500, converted=100)]
    out = phase1.suppress(rows)
    assert out[0].suppressed and out[0].entered == 0
    assert not out[1].suppressed


def test_category_first_tag_normalization():
    raw = "Contraceptions & Hormone,Special Offer,Medicines & Treatments;"
    assert phase1.normalize_category(raw) == "Contraceptions & Hormone"
    assert phase1.normalize_category(";") == "unknown"
    assert phase1.normalize_category("") == "unknown"


def test_the_analyst_is_told_which_rate_is_right_censored():
    """Live run 7 called confirmed->delivered 'relatively healthy' at 69.23%.
    That rate is an artefact of the window, and the model had no way to know."""
    from app.agents.analyst.phase1 import censoring_caveats
    caveats = censoring_caveats(["created", "confirmed", "delivered"], ["delivered"])
    assert len(caveats) == 1
    assert "confirmed -> delivered" in caveats[0] and "RIGHT-CENSORED" in caveats[0]
    assert censoring_caveats(["created", "confirmed", "delivered"], []) == []
    assert censoring_caveats(["created"], ["created"]) == []       # nothing upstream
