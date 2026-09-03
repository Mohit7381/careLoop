"""Per the pre-hackathon checklist: explicitly test both CodeGap branches
against contracts.py v2's model_post_init validation, before wiring real
search logic into the graph."""
import pytest

from app.schemas.contracts import CodeGap


def _base_kwargs(**overrides):
    kwargs = dict(
        finding_rank=1,
        origin="warehouse",
        stage="consultation",
        service="consultation",
        repo="bintan/consultation",
        gap_statement="placeholder",
    )
    kwargs.update(overrides)
    return kwargs


def test_mechanism_found_true_requires_gap_class():
    with pytest.raises(ValueError, match="gap_class is required"):
        CodeGap(**_base_kwargs(mechanism_found=True, gap_class=None))


def test_mechanism_found_true_with_gap_class_succeeds():
    gap = CodeGap(
        **_base_kwargs(
            mechanism_found=True,
            gap_class="missing_retention_hook",
            file="ConsultationDao.java",
            line=146,
        )
    )
    assert gap.mechanism_found is True
    assert gap.no_match_reason is None


def test_mechanism_found_false_requires_no_match_reason():
    with pytest.raises(ValueError, match="no_match_reason is required"):
        CodeGap(**_base_kwargs(mechanism_found=False, no_match_reason=None))


def test_mechanism_found_false_with_reason_succeeds():
    gap = CodeGap(
        **_base_kwargs(mechanism_found=False, no_match_reason="no_results")
    )
    assert gap.mechanism_found is False
    assert gap.gap_class is None
    assert gap.file is None
