from app.agents.analyst.validator import validate_finding
from app.schemas.contracts import EvidenceItem, Finding


def _f(**kw):
    base = dict(rank=1, origin="warehouse", stage="pharmacy_checkout",
                hypothesis="h", confidence="high",
                confirm_via="Segment abandonment by rx flag and A/B a stock pre-check")
    base.update(kw)
    return Finding(**base)


def test_cited_snapshot_number_passes(snapshot):
    f = _f(evidence=[EvidenceItem(type="snapshot", metric="created", value=647191)])
    ok, why = validate_finding(f, snapshot, [])
    assert ok, why


def test_uncited_number_rejected(snapshot):
    f = _f(evidence=[EvidenceItem(type="snapshot", metric="made_up", value=123456789)])
    ok, why = validate_finding(f, snapshot, [])
    assert not ok and "no evidence value" in why


def test_derivable_rate_passes(snapshot):
    # 229622 / 647191 = 0.3548 — a ratio of two known numbers is citable
    f = _f(evidence=[EvidenceItem(type="drilldown", metric="confirm_rate", value=0.3548)])
    ok, why = validate_finding(f, snapshot, [])
    assert ok, why


def test_no_evidence_rejected(snapshot):
    ok, why = validate_finding(_f(evidence=[]), snapshot, [])
    assert not ok and "no evidence" in why


def test_trivial_confirm_via_rejected(snapshot):
    f = _f(confirm_via="tbd",
           evidence=[EvidenceItem(type="snapshot", metric="created", value=647191)])
    ok, why = validate_finding(f, snapshot, [])
    assert not ok and "confirm_via" in why


def test_voc_finding_needs_review_count(snapshot):
    good = _f(origin="voc", stage="payments", review_count=41)
    bad = _f(origin="voc", stage="payments", review_count=None)
    assert validate_finding(good, snapshot, [])[0]
    assert not validate_finding(bad, snapshot, [])[0]


def test_a_rate_from_a_cut_the_run_never_answered_is_rejected(snapshot, cohort_cuts):
    """Found on a scoped demo run: the scope allowed only item_count, the trail
    shows stock_status REJECTED, yet a finding citing the stock rates
    0.0928 / 0.0073 was kept. The old rule accepted any rate that ANY two known
    numbers happened to divide to — 1433 / 201617 = 0.0071, an "ITEMS
    UNAVAILABLE" reason count over last week's confirmed count. Not evidence.
    """
    from app.schemas.contracts import DrilldownStep, EvidenceItem, Finding
    trail = [
        DrilldownStep(question="q", dimension="stock_status", result_rows=[],
                      note="rejected: not whitelisted"),
        DrilldownStep(question="q", dimension="item_count",
                      result_rows=cohort_cuts["item_count"]["rows"]),
    ]
    smuggled = Finding(
        rank=3, origin="warehouse", stage="pharmacy_checkout", hypothesis="stock",
        confidence="high", confirm_via="hold stock-outs and measure confirm rate",
        evidence=[EvidenceItem(type="drilldown", metric="rate", value=0.0928),
                  EvidenceItem(type="drilldown", metric="rate", value=0.0073)])
    ok, why = validate_finding(smuggled, snapshot, trail, shown=set())
    assert not ok, why

    # ...while a rate the run DID show, item_count's 1_item conversion, passes
    row = next(r for r in cohort_cuts["item_count"]["rows"] if r["segment"] == "1_item")
    legit = smuggled.model_copy(update={"evidence": [
        EvidenceItem(type="drilldown", metric="1_item rate",
                     value=round(row["converted"] / row["entered"], 4))]})
    ok, why = validate_finding(legit, snapshot, trail, shown=set())
    assert ok, why
