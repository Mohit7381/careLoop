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
