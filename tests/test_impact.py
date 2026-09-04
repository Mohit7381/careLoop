"""app/agents/code_scout/impact.py — closed-loop shipped-fix detection.

A Remedy verified `exists` proves nothing about WHEN it arrived; detection
hinges entirely on comparing the blamed commit's date against the run's own
baseline (prev_window_end, or window_start when none was given).
"""
from app.agents.code_scout.impact import detect_shipped_fixes
from app.schemas.contracts import CodeGap, Remedy, ShippedCommit


def _commit(date: str, sha: str = "abc123def456") -> ShippedCommit:
    return ShippedCommit(sha=sha, short_sha=sha[:8], author="a", date=date, message="m")


class _FakeCommitClient:
    def __init__(self, commit: ShippedCommit | None):
        self._commit = commit

    def blame_line(self, repo, file, line):
        return self._commit


def _gap_with_exists_remedy(evidence_file="Retention.java", evidence_line=42) -> CodeGap:
    return CodeGap(
        finding_rank=1, origin="warehouse", stage="pharmacy_checkout",
        service="oms", repo="timor/oms",
        mechanism_found=True, gap_class="missing_retention_hook", gap_statement="g",
        remedies=[Remedy(
            proposal="Retention push before final abandon", signature="RetentionService.push",
            status="exists", evidence_file=evidence_file, evidence_line=evidence_line,
        )],
    )


def test_a_commit_after_the_baseline_is_detected_as_shipped():
    gap = _gap_with_exists_remedy()
    client = _FakeCommitClient(_commit("2026-08-20"))

    shipped = detect_shipped_fixes([gap], [], client, window_start="2026-08-01", prev_window_end="2026-08-15")

    assert len(shipped) == 1
    sf = shipped[0]
    assert sf.finding_rank == 1
    assert sf.repo == "timor/oms"
    assert sf.evidence_file == "Retention.java"
    assert sf.commit.date == "2026-08-20"


def test_a_commit_before_the_baseline_is_not_shipped_it_just_predates_us():
    gap = _gap_with_exists_remedy()
    client = _FakeCommitClient(_commit("2026-07-01"))  # before prev_window_end

    shipped = detect_shipped_fixes([gap], [], client, window_start="2026-08-01", prev_window_end="2026-08-15")

    assert shipped == []


def test_falls_back_to_window_start_when_no_prev_window_end_given():
    gap = _gap_with_exists_remedy()
    client = _FakeCommitClient(_commit("2026-08-10"))  # after window_start, no prev_window_end supplied

    shipped = detect_shipped_fixes([gap], [], client, window_start="2026-08-01", prev_window_end=None)

    assert len(shipped) == 1


def test_a_partial_remedy_is_never_flagged_as_shipped():
    gap = _gap_with_exists_remedy()
    gap.remedies[0].status = "partial"
    client = _FakeCommitClient(_commit("2026-08-20"))

    shipped = detect_shipped_fixes([gap], [], client, window_start="2026-08-01", prev_window_end="2026-08-15")

    assert shipped == []


def test_a_gap_with_no_mechanism_found_is_skipped_entirely():
    gap = CodeGap(
        finding_rank=1, origin="warehouse", stage="pharmacy_checkout",
        service="oms", repo="timor/oms",
        mechanism_found=False, gap_statement="g", no_match_reason="no_results",
    )
    client = _FakeCommitClient(_commit("2026-08-20"))

    shipped = detect_shipped_fixes([gap], [], client, window_start="2026-08-01", prev_window_end="2026-08-15")

    assert shipped == []


def test_a_blame_lookup_that_fails_is_treated_as_not_detected_not_an_error():
    gap = _gap_with_exists_remedy()
    client = _FakeCommitClient(None)  # e.g. a GitLab outage — never raises, just returns None

    shipped = detect_shipped_fixes([gap], [], client, window_start="2026-08-01", prev_window_end="2026-08-15")

    assert shipped == []


def test_an_unparseable_baseline_skips_detection_rather_than_guessing():
    gap = _gap_with_exists_remedy()
    client = _FakeCommitClient(_commit("2026-08-20"))

    shipped = detect_shipped_fixes([gap], [], client, window_start="not-a-date", prev_window_end=None)

    assert shipped == []
