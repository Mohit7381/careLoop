"""Suggestion - Code Scout's alternate output shape (Rev 3), kept additive
alongside CodeGap/Remedy (see contracts.py's module docstring, decision
#11). Tests its model_post_init validation the same way
test_contracts_codegap.py does for CodeGap."""
import pytest
from pydantic import ValidationError

from app.schemas.contracts import Finding, RunState, Suggestion


def _base_kwargs(**overrides):
    kwargs = dict(
        finding_rank=1,
        origin="warehouse",
        stage="consultation",
        service="consultation",
        repo="bintan/consultation",
        suggestion_type="tech",
        title="placeholder",
        description="placeholder",
        rationale="placeholder",
    )
    kwargs.update(overrides)
    return kwargs


def test_business_suggestion_defaults_to_not_applicable():
    suggestion = Suggestion(**_base_kwargs(suggestion_type="business"))
    assert suggestion.verification_status == "not_applicable"
    assert suggestion.evidence_file is None


def test_business_suggestion_rejects_a_verification_status():
    with pytest.raises(ValueError, match="only applies to suggestion_type='tech'"):
        Suggestion(**_base_kwargs(suggestion_type="business", verification_status="absent"))


def test_process_suggestion_rejects_a_verification_status():
    with pytest.raises(ValueError, match="only applies to suggestion_type='tech'"):
        Suggestion(**_base_kwargs(suggestion_type="process", verification_status="exists"))


def test_tech_suggestion_can_be_absent_with_no_evidence():
    suggestion = Suggestion(**_base_kwargs(suggestion_type="tech", verification_status="absent"))
    assert suggestion.evidence_file is None


def test_tech_suggestion_exists_requires_evidence_file():
    with pytest.raises(ValueError, match="evidence_file is required"):
        Suggestion(**_base_kwargs(suggestion_type="tech", verification_status="exists"))


def test_tech_suggestion_exists_with_evidence_succeeds():
    suggestion = Suggestion(
        **_base_kwargs(
            suggestion_type="tech",
            verification_status="exists",
            evidence_file="ConsultationDao.java",
            evidence_line=146,
        )
    )
    assert suggestion.verification_status == "exists"


def test_tech_suggestion_can_be_unverified_with_no_evidence():
    """review S3/item #9: "unverified" - budget exhausted or the
    verification call itself failed - is distinct from "not_applicable"
    (nothing to check). Neither requires evidence_file."""
    suggestion = Suggestion(**_base_kwargs(suggestion_type="tech", verification_status="unverified"))
    assert suggestion.evidence_file is None


def test_business_suggestion_rejects_unverified():
    with pytest.raises(ValueError, match="only applies to suggestion_type='tech'"):
        Suggestion(**_base_kwargs(suggestion_type="business", verification_status="unverified"))


def test_run_state_carries_suggestions_alongside_code_gaps():
    state = RunState(
        run_id=1, window_start="a", window_end="b",
        suggestions=[Suggestion(**_base_kwargs())],
    )
    assert len(state.suggestions) == 1
    assert state.suggestions_for(1) == state.suggestions
    assert state.suggestions_for(2) == []


def test_finding_journey_events_defaults_to_empty_and_is_additive():
    finding = Finding(
        rank=1, origin="warehouse", stage="consultation", hypothesis="h",
        confidence="high", confirm_via="x",
    )
    assert finding.journey_events == []

    with_events = Finding(
        rank=1, origin="warehouse", stage="consultation", hypothesis="h",
        confidence="high", confirm_via="x",
        journey_events=["consultation_payment_timeout"],
    )
    assert with_events.journey_events == ["consultation_payment_timeout"]


def test_run_state_rejects_unknown_fields_instead_of_silently_dropping_them():
    """review B2: pydantic's default extra="ignore" silently dropped
    journey/demo_mode/prev_window_start/prev_window_end/failed_stage on a
    real handoff payload - losing `journey` is the serious one, since it's
    the key that resolves routing. extra="forbid" makes the next contract
    drift fail loudly instead."""
    with pytest.raises(ValidationError):
        RunState(run_id=1, window_start="a", window_end="b", not_a_real_field=True)
