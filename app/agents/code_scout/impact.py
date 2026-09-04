"""Closed-loop impact detection — Code Scout phase 4 (2026-09-04).

A Remedy the Remedy Loop verifies `exists` proves the code is there NOW; it
proves nothing about WHEN it arrived — it could predate CareLoop entirely.
This module asks a sharper question of the exact evidence line the verifier
already cited: GitLab blame names the commit that last touched it. If that
commit landed after this run's own baseline (`prev_window_end` when the
caller supplied one, else `window_start` — "shipped during the period being
analysed"), the fix plausibly shipped since we last looked; if it predates
the baseline, the code was simply already there and this is not a "shipped
fix" event.

This is deliberately the narrowest claim commit history alone supports —
recency, not causation. Whether the shipped commit is *why* a funnel/VoC
metric moved is for Reporter to correlate (a delta row landing in the same
window) and for a human to judge, never for this module to assert.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Protocol

from app.schemas.contracts import CodeGap, Finding, ShippedCommit, ShippedFix


class CommitHistoryClient(Protocol):
    def blame_line(self, repo: str, file: str, line: int) -> Optional[ShippedCommit]:
        """The commit that last touched `file`'s `line` in `repo`, or None if
        it could not be determined (file/line not found, API failure, etc.)."""
        ...


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def detect_shipped_fixes(
    gaps: list[CodeGap],
    findings: list[Finding],
    commit_client: CommitHistoryClient,
    window_start: str,
    prev_window_end: Optional[str] = None,
) -> list[ShippedFix]:
    """One blame lookup per EXISTS-verified remedy across all of this run's
    gaps. `findings` is unused for attribution today (finding_rank/stage/
    origin/repo all come straight off the gap) but kept in the signature so a
    future caller can enrich the rationale with the finding's own hypothesis
    without changing this function's shape again.
    """
    baseline = _parse_date(prev_window_end) or _parse_date(window_start)
    if baseline is None:
        return []

    shipped: list[ShippedFix] = []
    for gap in gaps:
        if not gap.mechanism_found:
            continue
        for remedy in gap.remedies:
            if remedy.status != "exists" or not remedy.evidence_file or not remedy.evidence_line:
                continue
            commit = commit_client.blame_line(gap.repo, remedy.evidence_file, remedy.evidence_line)
            if commit is None:
                continue
            commit_date = _parse_date(commit.date)
            if commit_date is None or commit_date <= baseline:
                continue  # already existed as of the baseline — not "shipped since"
            shipped.append(ShippedFix(
                finding_rank=gap.finding_rank,
                origin=gap.origin,
                stage=gap.stage,
                repo=gap.repo,
                remedy_proposal=remedy.proposal,
                evidence_file=remedy.evidence_file,
                evidence_line=remedy.evidence_line,
                evidence_snippet=remedy.evidence_snippet,
                commit=commit,
            ))
    return shipped
