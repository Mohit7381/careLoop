"""report_writer.py — the elaborate, sectioned report (Halodoc hackathon
chat, 2026-09-04: "separate sections for all types of analysis... each
section very elaborate... brief summary on each section"). Focuses on the
two things most likely to break: honest empty-state rendering (never
crash, never fabricate), and that each real analysis type actually gets
its own section now — code gaps in particular were previously invisible
in the report entirely."""
from app.pipeline.nodes.report_writer import report_writer_node
from app.pipeline.state import initial_state


def _base_state():
    return initial_state(run_id=1, window_start="2026-08-01", window_end="2026-08-31", demo_mode=True)


def _report(state) -> str:
    result = report_writer_node(state)
    artifact = next(a for a in result["artifacts"] if a["kind"] == "report_md")
    return artifact["content"]


def test_empty_run_renders_every_section_honestly_without_crashing():
    """No snapshot, no findings, no code_gaps, no suggestions at all — every
    section must say so honestly rather than raising or inventing content."""
    report = _report(_base_state())

    assert "## 1. Funnel Analysis" in report
    assert "## 2. Customer Review Analysis" in report
    assert "## 3. Drop-off Findings" in report
    assert "## 4. Code Gaps & Bugs" in report
    assert "## 5. Suggested Improvements" in report
    assert "_no code gap" not in report  # placeholder text should read "did not run" not silently vanish
    assert "no warehouse-driven findings" in report
    assert "no improvement ideas surfaced" in report


def test_code_gaps_section_renders_mechanism_found_and_not_found_gaps():
    state = _base_state()
    state["findings"] = [
        {"rank": 1, "origin": "warehouse", "stage": "pharmacy_checkout", "hypothesis": "h", "confidence": "high", "confirm_via": "x"},
    ]
    state["code_gaps"] = [
        {
            "finding_rank": 1, "origin": "warehouse", "stage": "pharmacy_checkout",
            "service": "oms", "repo": "timor/oms", "mechanism_found": True,
            "gap_class": "missing_retention_hook", "gap_statement": "abandon kill, no notify",
            "file": "F.java", "line": 42,
            "remedies": [{"proposal": "add hook", "signature": "s", "status": "absent", "searched_terms": ["a", "b"]}],
        },
    ]

    report = _report(state)

    assert "## 4. Code Gaps & Bugs" in report
    assert "missing_retention_hook" in report
    assert "F.java:42" in report
    assert "not found in 2 searches" in report
    assert "**Summary:** 1 mechanism(s) pinned across 1 gap(s) explored, 1 remedy verdict(s)." in report


def test_suggestions_section_separates_from_code_gaps_and_labels_type():
    state = _base_state()
    state["suggestions"] = [
        {
            "finding_rank": 1, "origin": "warehouse", "stage": "pharmacy_checkout",
            "service": "oms", "repo": "timor/oms", "suggestion_type": "business",
            "title": "Cart-recovery incentive", "description": "offer a discount",
            "rationale": "recovers abandoners", "verification_status": "not_applicable",
        },
    ]

    report = _report(state)

    assert "## 5. Suggested Improvements (Business / Process / Tech)" in report
    assert "**[Business]** Cart-recovery incentive" in report
    # must not bleed into the Code Gaps section
    gaps_section = report.split("## 4. Code Gaps")[1].split("## 5.")[0]
    assert "Cart-recovery incentive" not in gaps_section


def test_customer_review_section_surfaces_voc_findings_and_theme_table():
    state = _base_state()
    state["findings"] = [
        {
            "rank": 4, "origin": "voc", "stage": "payments", "hypothesis": "payment complaints",
            "confidence": "high", "confirm_via": "x", "theme": "payment/refund", "review_count": 41,
            "top_quotes": ["[1★ 2026-05-09] terrible refund experience"],
        },
    ]
    state["voc"] = {
        "reviews_meta": {"total": 100, "negatives": 41, "threshold": 20},
        "themes": [{"theme": "payment/refund", "count": 41, "escalated": True}],
        "per_finding_quotes": {},
    }

    report = _report(state)

    assert "## 2. Customer Review Analysis (Voice of Customer)" in report
    assert "payment/refund" in report
    assert "41 users report this" in report
    assert "terrible refund experience" in report
    # a VoC finding must not also appear in the warehouse-only findings section
    warehouse_section = report.split("## 3. Drop-off Findings")[1].split("## 4.")[0]
    assert "payment complaints" not in warehouse_section
