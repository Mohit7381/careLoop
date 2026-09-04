"""app/agents/code_scout/amplify.py — explore_shipped_feature (2026-09-04):
auto-fetches every shipped fix with a favourable measured metric and
explores each for follow-on ideas."""
from app.agents.code_scout.amplify import propose_feature_amplifications
from app.schemas.contracts import ShippedCommit, ShippedFix


def _fix(finding_rank=1, pct_change=20.0, metric_name="conversion rate at 'created'") -> ShippedFix:
    kwargs = {}
    if metric_name is not None:
        kwargs = dict(metric_name=metric_name, metric_unit="%", previous_value=50.0,
                     current_value=60.0, pct_change=pct_change, metric_ref="stage:created")
    return ShippedFix(
        finding_rank=finding_rank, origin="warehouse", stage="created", repo="timor/oms",
        remedy_proposal="Retention push before final abandon",
        evidence_file="Retention.java", evidence_line=42, evidence_snippet="if (shouldAbandon) {...}",
        commit=ShippedCommit(sha="abc123def456", short_sha="abc123de", author="jdoe",
                             date="2026-08-20", message="Add retention push"),
        **kwargs,
    )


def test_no_llm_means_no_amplifications_not_a_crash():
    assert propose_feature_amplifications(None, [_fix()]) == []


def test_only_positively_moved_shipped_fixes_are_explored():
    calls = []

    def llm(ctx):
        calls.append(ctx)
        return {"suggestions": []}

    fixes = [_fix(finding_rank=1, pct_change=20.0), _fix(finding_rank=2, pct_change=-5.0),
             _fix(finding_rank=3, metric_name=None)]  # negative move, and unmeasured — neither qualifies
    propose_feature_amplifications(llm, fixes)

    assert len(calls) == 1
    assert calls[0]["shipped_fix"]["pct_change"] == 20.0


def test_parses_a_well_formed_suggestion():
    def llm(ctx):
        return {"suggestions": [{
            "suggestion_type": "tech", "title": "Widen to consultation abandon too",
            "description": "Reuse RetentionService.push in the consultation abandon path.",
            "rationale": "Since retention_push_sent moved +20.0%, the same hook could recover more elsewhere.",
        }]}

    out = propose_feature_amplifications(llm, [_fix()])

    assert len(out) == 1
    s = out[0]
    assert s.suggestion_type == "tech"
    assert s.finding_rank == 1
    assert s.repo == "timor/oms"
    assert s.service == "oms"
    assert s.verification_status == "unverified"


def test_a_business_suggestion_gets_not_applicable_verification_status():
    def llm(ctx):
        return {"suggestions": [{
            "suggestion_type": "business", "title": "Extend the incentive to loyal users",
            "description": "Offer the same nudge to repeat customers.",
            "rationale": "The metric moved +20.0% for new users; loyal users may respond similarly.",
        }]}

    out = propose_feature_amplifications(llm, [_fix()])

    assert out[0].verification_status == "not_applicable"


def test_a_malformed_suggestion_is_dropped_not_crashed_on():
    def llm(ctx):
        return {"suggestions": [{"suggestion_type": "tech"}]}  # missing title/description/rationale

    assert propose_feature_amplifications(llm, [_fix()]) == []


def test_an_unrecognised_suggestion_type_is_dropped():
    def llm(ctx):
        return {"suggestions": [{"suggestion_type": "revert", "title": "t", "description": "d", "rationale": "r"}]}

    assert propose_feature_amplifications(llm, [_fix()]) == []


def test_a_failing_llm_call_drops_that_candidate_not_the_whole_run():
    def flaky_llm(ctx):
        raise RuntimeError("sphere outage")

    assert propose_feature_amplifications(flaky_llm, [_fix()]) == []


def test_respects_the_call_budget():
    calls = []

    def llm(ctx):
        calls.append(ctx)
        return {"suggestions": []}

    fixes = [_fix(finding_rank=i, pct_change=10.0) for i in range(1, 6)]
    propose_feature_amplifications(llm, fixes, budget=2)

    assert len(calls) == 2
