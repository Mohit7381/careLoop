"""routes_analysis._validate_dimensions — the "refuse requests outside the
data's scope" half of prompt-scoped analysis (decision #13). Validated
against the journey's own routing table at request time, before a run is
ever created, rather than letting an unknown dimension silently produce a
zero-findings run with no explanation."""
import pytest
from fastapi import HTTPException

from app.api.routes_analysis import _validate_dimensions


def test_no_dimensions_is_unscoped():
    assert _validate_dimensions("pd_checkout", None) == []
    assert _validate_dimensions("pd_checkout", []) == []


def test_known_routing_categories_pass_through():
    assert _validate_dimensions("pd_checkout", ["payments", "consultation"]) == ["payments", "consultation"]


def test_unknown_dimension_is_refused_with_the_valid_set():
    with pytest.raises(HTTPException) as exc_info:
        _validate_dimensions("pd_checkout", ["payments", "not_a_real_dimension"])

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert "not_a_real_dimension" in detail["message"]
    assert "payments" not in detail["message"]  # only the unknown one(s) are named
    assert "payments" in detail["valid_dimensions"]
