"""The closed gap-class set, and what happens to everything the model invents."""
import pytest

from app.agents.code_scout.assessor import bracket_safe, normalise_gap_class
from app.pipeline.nodes.prd_generator import GAP_CLASS_SOLUTION_HINTS
from app.schemas.contracts import CodeGap, GapClass


@pytest.mark.parametrize("raw,expected", [
    ("logic_flaw", "logic_flaw"),
    ("Missing Retention Hook", "missing_retention_hook"),
    ("missing_notification_hook", "missing_retention_hook"),
    ("no re-engagement nudge before kill", "missing_retention_hook"),
    ("client_side_ux_issue", "ux_gap"),
    ("configuration-only-no-usage-evidence", "unclassified"),
    ("missing_consultation_event_types", "unclassified"),
    (None, "unclassified"),
])
def test_invented_classes_land_somewhere_honest(raw, expected):
    assert normalise_gap_class(raw)[0] == expected


def test_every_gap_class_has_a_prd_hint():
    """prd_generator indexes GAP_CLASS_SOLUTION_HINTS[gap.gap_class] — a class
    with no hint is a KeyError at PRD time, after the whole run succeeded."""
    assert set(GapClass.__args__) <= set(GAP_CLASS_SOLUTION_HINTS)


def test_unclassified_satisfies_the_codegap_contract():
    CodeGap(finding_rank=1, origin="warehouse", stage="pharmacy_checkout", service="oms",
            repo="timor/oms", mechanism_found=True, gap_class="unclassified",
            gap_statement="located; assessment unavailable", file="X.java", line=1)


def test_bracket_safe_leaves_nothing_for_the_model_to_echo():
    assert "<" not in bracket_safe("Map<String, List<Order>>") 
    assert bracket_safe("") == "" and bracket_safe(None) == ""
