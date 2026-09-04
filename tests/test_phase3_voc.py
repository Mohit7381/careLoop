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


def test_corroboration_picks_largest_theme_and_respects_floor(reviews, journey_cfg):
    from app.agents.analyst.phase3_voc import corroborate, run_voc
    from app.schemas.contracts import EvidenceItem, Finding
    _, voc = run_voc(reviews, journey_cfg["voc"], next_rank=10)
    wh = [Finding(rank=1, origin="warehouse", stage="pharmacy_checkout",
                  hypothesis="h", confidence="high",
                  confirm_via="run the confirming experiment please",
                  evidence=[EvidenceItem(type="snapshot", metric="m", value=1.0)])]
    corroborate(wh, voc, journey_cfg["voc"])
    # pharmacy_checkout themes: app/technical (8) and price (3).
    # 8 >= floor -> app/technical wins; price(3) must never attach.
    assert wh[0].theme == "app/technical" and wh[0].review_count == 8


# ---- Phase 3.5: LLM-driven correlation (2026-09-04) ----
# corroborate() only matches same-stage; these prove the LLM pass catches
# real cross-stage correlations the deterministic lookup structurally can't,
# without ever overriding a deterministic hit or trusting a fabricated theme.

def test_correlate_with_llm_catches_a_cross_stage_correlation(reviews, journey_cfg):
    from app.agents.analyst.phase3_voc import corroborate, correlate_with_llm, run_voc
    from app.schemas.contracts import Finding
    _, voc = run_voc(reviews, journey_cfg["voc"], next_rank=10)

    # payment/refund (41 reviews) is pre-mapped to routing_stage "payments" -
    # a "re_engagement"-stage finding can NEVER corroborate against it via
    # stage equality, no matter how large the cluster is.
    wh = [Finding(rank=1, origin="warehouse", stage="re_engagement",
                  hypothesis="Users who abandon mid-checkout after a failed payment never "
                             "return, even after a re-engagement reminder push.",
                  confidence="medium", confirm_via="check reminder click-through vs completion")]
    corroborate(wh, voc, journey_cfg["voc"])
    assert wh[0].theme is None  # confirms the deterministic pass genuinely misses this

    def stub_llm(ctx: dict) -> dict:
        assert ctx["warehouse_finding"]["stage"] == "re_engagement"
        assert any(t["theme"] == "payment/refund" for t in ctx["voc_themes"])
        return {
            "correlated": True,
            "theme": "payment/refund",
            "rationale": "Users abandoning after a failed payment never return even to a "
                         "reminder - same root cause as the payment/refund complaints.",
        }

    correlate_with_llm(wh, voc, stub_llm)
    assert wh[0].theme == "payment/refund"
    assert wh[0].review_count == 41
    assert wh[0].correlation_rationale


def test_correlate_with_llm_never_overrides_a_deterministic_match(reviews, journey_cfg):
    from app.agents.analyst.phase3_voc import corroborate, correlate_with_llm, run_voc
    from app.schemas.contracts import Finding
    _, voc = run_voc(reviews, journey_cfg["voc"], next_rank=10)
    wh = [Finding(rank=1, origin="warehouse", stage="pharmacy_checkout",
                  hypothesis="h", confidence="high", confirm_via="c")]
    corroborate(wh, voc, journey_cfg["voc"])
    assert wh[0].theme == "app/technical"

    def fail_llm(ctx: dict) -> dict:
        raise AssertionError("must never be called - this finding already has a theme")

    correlate_with_llm(wh, voc, fail_llm)
    assert wh[0].theme == "app/technical"  # untouched


def test_correlate_with_llm_discards_a_theme_name_the_data_does_not_have(reviews, journey_cfg):
    from app.agents.analyst.phase3_voc import correlate_with_llm, run_voc
    from app.schemas.contracts import Finding
    _, voc = run_voc(reviews, journey_cfg["voc"], next_rank=10)
    wh = [Finding(rank=1, origin="warehouse", stage="re_engagement",
                  hypothesis="h", confidence="low", confirm_via="c")]

    def hallucinating_llm(ctx: dict) -> dict:
        return {"correlated": True, "theme": "does-not-exist", "rationale": "made up"}

    correlate_with_llm(wh, voc, hallucinating_llm)
    assert wh[0].theme is None  # never trust a theme name the data doesn't back up


def test_correlate_with_llm_respects_its_call_budget(reviews, journey_cfg):
    from app.agents.analyst.phase3_voc import correlate_with_llm, run_voc
    from app.schemas.contracts import Finding
    _, voc = run_voc(reviews, journey_cfg["voc"], next_rank=10)
    wh = [Finding(rank=i, origin="warehouse", stage="re_engagement",
                  hypothesis=f"h{i}", confidence="low", confirm_via="c") for i in range(1, 6)]

    calls = []

    def counting_llm(ctx: dict) -> dict:
        calls.append(ctx)
        return {"correlated": False}

    correlate_with_llm(wh, voc, counting_llm, budget=2)
    assert len(calls) == 2
