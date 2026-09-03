"""VoC classification + escalation against the REAL scrubbed 600-review fixture."""
from app.agents.analyst.phase3_voc import classify_review, run_voc


def test_single_primary_theme_priority_order(journey_cfg):
    themes = journey_cfg["voc"]["themes"]
    # mentions both payment AND doctor -> payment/refund wins (higher priority)
    t = classify_review("sudah bayar tapi dokter tidak menjawab", themes)
    assert t == "payment/refund"


def test_real_fixture_escalations(reviews, journey_cfg):
    findings, voc = run_voc(reviews, journey_cfg["voc"], next_rank=1)
    escalated = {f.theme: f.review_count for f in findings}
    # golden: payment/refund (41) and consultation/doctor (21) cross threshold 20
    assert escalated.get("payment/refund") == 41
    assert escalated.get("consultation/doctor") == 21
    assert len(findings) == 2  # delivery(9), app/technical(8) etc. stay below
    for f in findings:
        assert f.origin == "voc" and f.review_count > 20
        assert f.theme_search_terms  # pre-derived for Code Scout
        assert f.top_quotes and all("@" not in q for q in f.top_quotes)  # scrubbed


def test_escalation_routes_to_journey_categories(reviews, journey_cfg):
    findings, _ = run_voc(reviews, journey_cfg["voc"], next_rank=1)
    stages = {f.theme: f.stage for f in findings}
    assert stages["payment/refund"] == "payments"
    assert stages["consultation/doctor"] == "consultation"
