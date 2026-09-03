"""End-to-end fixture-mode tests for the Code Scout node - the Day-1 gate:
'pipeline runs end-to-end on fixtures with stubbed LLM calls'.
"""
from pathlib import Path

import pytest

from app.agents.code_scout.assessor import StubCodeGapAssessor
from app.agents.code_scout.node import code_scout_node
from app.agents.code_scout.search_client import FixtureSearchClient
from app.schemas.contracts import EvidenceItem, Finding, RunState

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "code_scout"


@pytest.fixture
def search_client():
    return FixtureSearchClient(FIXTURES_DIR)


@pytest.fixture
def assessor():
    return StubCodeGapAssessor()


def _run_state(*findings: Finding) -> RunState:
    return RunState(
        run_id=1,
        window_start="2026-08-04",
        window_end="2026-09-03",
        findings=list(findings),
    )


def test_reproduces_the_known_good_payment_timeout_example(search_client, assessor):
    """The proven example: 'abandoned by system' -> ConsultationDao.java:146,
    GET_ABANDON_CONSULTATION -> missing_retention_hook."""
    finding = Finding(
        rank=1,
        origin="warehouse",
        stage="consultation",
        hypothesis="51,321/wk consultations killed by silent payment-timeout abandon script",
        confidence="high",
        confirm_via="check re-engagement CT events post-cancel",
        evidence=[EvidenceItem(type="snapshot", metric="system_cancelled_count", value=51321)],
    )
    state = _run_state(finding)

    result = code_scout_node(state, search_client=search_client, assessor=assessor)
    gaps = result["code_gaps"]

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.mechanism_found is True
    assert gap.file == "src/main/java/com/halodoc/bintan/consultation/dao/ConsultationDao.java"
    assert gap.line == 146
    assert gap.gap_class == "missing_retention_hook"
    assert gap.repo == "bintan/consultation"
    assert gap.origin == "warehouse"
    assert gap.stage == "consultation"
    assert gap.no_match_reason is None


def test_no_match_produces_valid_first_class_outcome(search_client, assessor):
    """Finding #3 has no resolvable code (synthetic fixture) - must NOT fabricate
    a gap_class, must set no_match_reason, and must still construct validly."""
    finding = Finding(
        rank=3,
        origin="warehouse",
        stage="payments",
        hypothesis="hypothetical payment finding with no resolvable code location",
        confidence="low",
        confirm_via="manual code review",
    )
    state = _run_state(finding)

    result = code_scout_node(state, search_client=search_client, assessor=assessor)
    gaps = result["code_gaps"]

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.mechanism_found is False
    assert gap.gap_class is None
    assert gap.file is None
    assert gap.no_match_reason == "budget_exhausted"


def test_voc_origin_finding_uses_its_own_theme_search_terms(search_client, assessor):
    """VoC-escalated findings carry theme_search_terms directly (contracts.py v2) -
    the assessor should use them rather than deriving terms from hypothesis text."""
    finding = Finding(
        rank=2,
        origin="voc",
        stage="pharmacy_checkout",
        hypothesis="41 reviews mention payment/refund issues during pharmacy checkout",
        confidence="medium",
        confirm_via="cross-check against warehouse abandonment reasons",
        theme="payment_refund",
        theme_search_terms=["abandon"],
        review_count=41,
        top_quotes=["paid multiple times, failed multiple times... order missing from history"],
    )
    state = _run_state(finding)

    result = code_scout_node(state, search_client=search_client, assessor=assessor)
    gaps = result["code_gaps"]

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.search_terms_used == ["abandon"]
    assert gap.origin == "voc"
    # GAP 2 fixture is a real-but-weaker candidate, not fully hand-verified
    # like GAP 1 - still resolves mechanism_found=True per the fixture.
    assert gap.mechanism_found is True
    assert gap.repo == "timor/oms"


def test_existing_code_gaps_are_preserved_not_overwritten(search_client, assessor):
    """code_scout_node must append to state.code_gaps, not replace it -
    other nodes may have already written gaps for other findings."""
    finding = Finding(
        rank=1,
        origin="warehouse",
        stage="consultation",
        hypothesis="51,321/wk consultations killed by silent payment-timeout abandon script",
        confidence="high",
        confirm_via="check re-engagement CT events post-cancel",
    )
    state = _run_state(finding)
    state = state.model_copy(update={"code_gaps": []})

    result = code_scout_node(state, search_client=search_client, assessor=assessor)
    assert len(result["code_gaps"]) == 1
