"""End-to-end fixture-mode tests for Code Scout's alternate Suggestion node
(Rev 3: explore -> suggest -> verify, additive alongside node.py's
find_gap()-based code_scout_node - see contracts.py's module docstring).
"""
from pathlib import Path

from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.explore_search_client import FixtureExploreSearchClient, GapLocation
from app.agents.code_scout.suggestion_assessor import StubFeatureSuggestionAssessor
from app.agents.code_scout.suggestion_node import suggestion_code_scout_node
from app.schemas.contracts import EvidenceItem, Finding, RunState

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "code_scout_suggestions"


def _clients():
    return FixtureExploreSearchClient(FIXTURES_DIR), StubFeatureSuggestionAssessor()


def _run_state(*findings: Finding) -> RunState:
    return RunState(
        run_id=1,
        window_start="2026-08-04",
        window_end="2026-09-03",
        findings=list(findings),
    )


def test_consultation_dropoff_produces_mixed_tech_and_business_suggestions():
    """The proven area: consultation abandon-kill. Must produce at least one
    tech suggestion (verified against real code) and one business suggestion
    (no code evidence needed) - proving the flow isn't tech-only."""
    search_client, assessor = _clients()
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

    result = suggestion_code_scout_node(state, search_client=search_client, assessor=assessor)
    suggestions = result["suggestions"]

    assert len(suggestions) == 2
    tech = [s for s in suggestions if s.suggestion_type == "tech"]
    business = [s for s in suggestions if s.suggestion_type == "business"]
    assert len(tech) == 1
    assert len(business) == 1

    tech_suggestion = tech[0]
    assert tech_suggestion.evidence_file == "src/main/java/com/halodoc/bintan/consultation/dao/ConsultationDao.java"
    assert tech_suggestion.verification_status == "absent"  # "garuda" confirmed absent live
    assert tech_suggestion.repo == "bintan/consultation"
    assert tech_suggestion.origin == "warehouse"
    assert tech_suggestion.stage == "consultation"

    business_suggestion = business[0]
    assert business_suggestion.verification_status == "not_applicable"
    assert business_suggestion.evidence_file is None


def test_pharmacy_dropoff_distinguishes_exists_absent_and_partial():
    """The corrected GAP 2 area (abandonOrderV2). Exercises all three real
    verification outcomes in one finding: 'garuda' absent, 'sendCommunication'
    found-but-far (partial), plus a business suggestion (not_applicable)."""
    search_client, assessor = _clients()
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

    result = suggestion_code_scout_node(state, search_client=search_client, assessor=assessor)
    suggestions = result["suggestions"]

    assert len(suggestions) == 3
    by_title = {s.title: s for s in suggestions}

    garuda = by_title["Re-engagement call before order abandon"]
    assert garuda.verification_status == "absent"
    assert garuda.origin == "voc"

    reuse = by_title["Reuse the existing communication hook"]
    assert reuse.verification_status == "partial"
    assert reuse.evidence_line == 216

    incentive = by_title["Cart-recovery incentive"]
    assert incentive.suggestion_type == "business"
    assert incentive.verification_status == "not_applicable"


def test_no_inventory_produces_zero_suggestions_not_a_fabricated_one():
    """Finding #3 explores an area with nothing in it (synthetic fixture) -
    must produce zero suggestions, never guess one to have something to show."""
    search_client, assessor = _clients()
    finding = Finding(
        rank=3,
        origin="warehouse",
        stage="payments",
        hypothesis="hypothetical payment drop-off with nothing found on exploration",
        confidence="low",
        confirm_via="manual code review",
    )
    state = _run_state(finding)

    result = suggestion_code_scout_node(state, search_client=search_client, assessor=assessor)
    assert result["suggestions"] == []


def test_existing_suggestions_are_preserved_not_overwritten():
    """suggestion_code_scout_node must append to state.suggestions, not
    replace it - other nodes may have already written suggestions for other
    findings."""
    search_client, assessor = _clients()
    finding = Finding(
        rank=1,
        origin="warehouse",
        stage="consultation",
        hypothesis="51,321/wk consultations killed by silent payment-timeout abandon script",
        confidence="high",
        confirm_via="check re-engagement CT events post-cancel",
    )
    state = _run_state(finding)

    result = suggestion_code_scout_node(state, search_client=search_client, assessor=assessor)
    assert len(result["suggestions"]) == 2


class _FlakySearchClient:
    """explore() raises for one repo, succeeds for another - proves the node
    isolates a single external failure to that repo instead of crashing the
    whole finding (or run)."""

    def __init__(self, fail_repo: str, ok_repo: str, ok_inventory: list[GapLocation]):
        self._fail_repo = fail_repo
        self._ok_repo = ok_repo
        self._ok_inventory = ok_inventory

    def explore(self, finding_rank, repo, search_terms, budget):
        if repo == self._fail_repo:
            raise CodeScoutExternalError("simulated GitLab outage")
        if repo == self._ok_repo:
            return self._ok_inventory, 1
        return [], 0

    def check_within_file(self, finding_rank, repo, file, term):
        return None


class _BusinessOnlyAssessor:
    """Minimal assessor stand-in - always proposes one business suggestion,
    which needs no code verification, so the test isolates explore()'s
    failure handling specifically."""

    def propose_search_terms(self, finding):
        return ["abandon"]

    def propose_suggestions(self, finding, inventory):
        from app.agents.code_scout.suggestion_assessor import SuggestionProposal

        return [
            SuggestionProposal(
                suggestion_type="business",
                title="Some suggestion",
                description="d",
                rationale="r",
            )
        ]


def test_a_failing_repo_search_does_not_abort_other_repos_for_the_same_finding():
    """pharmacy_checkout routes to two repos (timor/oms, timor/fulfilment).
    If explore() blows up for the first, the second must still be tried."""
    ok_inventory = [GapLocation(file="AbandonOrderService.java", line=10, snippet="...")]
    search_client = _FlakySearchClient(
        fail_repo="timor/oms", ok_repo="timor/fulfilment", ok_inventory=ok_inventory
    )
    finding = Finding(
        rank=9,
        origin="warehouse",
        stage="pharmacy_checkout",
        hypothesis="checkout drop-off",
        confidence="medium",
        confirm_via="manual review",
    )
    state = _run_state(finding)

    result = suggestion_code_scout_node(state, search_client=search_client, assessor=_BusinessOnlyAssessor())
    suggestions = result["suggestions"]

    assert len(suggestions) == 1
    assert suggestions[0].repo == "timor/fulfilment"


class _AssessorThatFailsForOneFinding:
    """Wraps the real stub, but simulates an LLM outage for one finding_rank
    - proves a bad propose_search_terms() call skips only that finding."""

    def __init__(self, failing_rank: int):
        self._failing_rank = failing_rank
        self._real = StubFeatureSuggestionAssessor()

    def propose_search_terms(self, finding):
        if finding.rank == self._failing_rank:
            raise CodeScoutExternalError("simulated Sphere outage")
        return self._real.propose_search_terms(finding)

    def propose_suggestions(self, finding, inventory):
        return self._real.propose_suggestions(finding, inventory)


def test_a_failing_finding_does_not_abort_processing_of_other_findings():
    search_client, _ = _clients()
    assessor = _AssessorThatFailsForOneFinding(failing_rank=1)

    finding1 = Finding(
        rank=1,
        origin="warehouse",
        stage="consultation",
        hypothesis="51,321/wk consultations killed by silent payment-timeout abandon script",
        confidence="high",
        confirm_via="check re-engagement CT events post-cancel",
    )
    finding2 = Finding(
        rank=2,
        origin="voc",
        stage="pharmacy_checkout",
        hypothesis="41 reviews mention payment/refund issues during pharmacy checkout",
        confidence="medium",
        confirm_via="cross-check against warehouse abandonment reasons",
        theme="payment_refund",
        theme_search_terms=["abandon"],
        review_count=41,
    )
    state = _run_state(finding1, finding2)

    result = suggestion_code_scout_node(state, search_client=search_client, assessor=assessor)
    suggestions = result["suggestions"]

    # finding #1's LLM call failed -> zero suggestions for it, but finding #2
    # still produced its full 3 - the failure didn't propagate.
    assert suggestions
    assert all(s.finding_rank == 2 for s in suggestions)
    assert len(suggestions) == 3


class _VerificationAlwaysFails:
    """Delegates explore() to a real FixtureExploreSearchClient, but
    simulates a GitLab outage specifically during check_within_file()."""

    def __init__(self, inner):
        self._inner = inner

    def explore(self, finding_rank, repo, search_terms, budget):
        return self._inner.explore(finding_rank, repo, search_terms, budget)

    def check_within_file(self, finding_rank, repo, file, term):
        raise CodeScoutExternalError("simulated GitLab outage during verification")


def test_a_failing_verification_call_reports_unverified_instead_of_crashing():
    """review S3/item #9: a verification call that failed must not read as
    "not_applicable" (nothing to check) - it's "unverified" (something to
    check, we just couldn't)."""
    fixture_client, assessor = _clients()
    search_client = _VerificationAlwaysFails(fixture_client)

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

    result = suggestion_code_scout_node(state, search_client=search_client, assessor=assessor)
    suggestions = result["suggestions"]

    assert len(suggestions) == 2
    tech = next(s for s in suggestions if s.suggestion_type == "tech")
    assert tech.verification_status == "unverified"
    assert tech.evidence_line is None

    business = next(s for s in suggestions if s.suggestion_type == "business")
    assert business.verification_status == "not_applicable"


def test_budget_exhausted_reports_unverified_not_not_applicable():
    """A tech suggestion that ran out of search budget is "we didn't check",
    not "there was nothing to check" (review S3)."""
    from app.agents.code_scout.suggestion_assessor import SuggestionProposal

    class _NoBudgetLeftAssessor:
        def propose_search_terms(self, finding):
            return ["garuda"]

        def propose_suggestions(self, finding, inventory):
            return [
                SuggestionProposal(
                    suggestion_type="tech",
                    title="Some tech suggestion",
                    description="d",
                    rationale="r",
                    signature="garuda",
                    evidence_file="ConsultationDao.java",
                )
            ]

    class _ZeroBudgetSearchClient:
        def explore(self, finding_rank, repo, search_terms, budget):
            # Consumes the entire EXPLORATION_SEARCH_BUDGET itself, leaving
            # nothing for check_within_file().
            return [GapLocation(file="ConsultationDao.java", line=1, snippet="...")], budget

        def check_within_file(self, finding_rank, repo, file, term):
            raise AssertionError("must not be called when budget_remaining <= 0")

    finding = Finding(
        rank=1,
        origin="warehouse",
        stage="consultation",
        hypothesis="h",
        confidence="high",
        confirm_via="x",
    )
    state = _run_state(finding)

    result = suggestion_code_scout_node(
        state, search_client=_ZeroBudgetSearchClient(), assessor=_NoBudgetLeftAssessor()
    )
    suggestions = result["suggestions"]

    assert len(suggestions) == 1
    assert suggestions[0].verification_status == "unverified"
