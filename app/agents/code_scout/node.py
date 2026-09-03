"""Agent 3 - Code Scout.

Read-only: names file:line, never writes a diff, never opens an MR.

Shaped as a LangGraph node: a pure function taking RunState and returning a
dict of state updates, matching the orchestrator's convention. search_client
and assessor are injected so tests (and Day 1 vs Day 2) can swap
FixtureSearchClient/StubCodeGapAssessor for the live implementations without
touching this file.

Rev 2 (PR #3 review): find_gap() failing for one repo (a GitLab outage, a
malformed response) used to propagate straight out of this function and
crash code_scout_node's whole run. Now caught per-repo - a bad repo is
logged and skipped, and the finding still gets a real (not fabricated)
mechanism_found=False verdict from whatever repos DID resolve, instead of
the entire run dying on one flaky call.
"""
from __future__ import annotations

import logging

from app.agents.code_scout.assessor import CodeGapAssessor
from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.routing import repos_for_stage
from app.agents.code_scout.search_client import SearchClient
from app.schemas.contracts import CodeGap, Finding, RunState

logger = logging.getLogger(__name__)

SEARCH_BUDGET_PER_FINDING = 5


def code_scout_node(
    state: RunState, *, search_client: SearchClient, assessor: CodeGapAssessor
) -> dict:
    new_gaps: list[CodeGap] = []
    for finding in state.findings:
        new_gaps.extend(_process_finding(finding, search_client, assessor, state.journey))
    return {"code_gaps": [*state.code_gaps, *new_gaps]}


def _process_finding(
    finding: Finding, search_client: SearchClient, assessor: CodeGapAssessor, journey: str
) -> list[CodeGap]:
    try:
        search_terms = assessor.propose_search_terms(finding)
    except CodeScoutExternalError as exc:
        # Without search terms there's nothing to search with - skip this
        # finding rather than let one bad assessor call kill the whole run.
        logger.warning("propose_search_terms failed for finding #%s: %s", finding.rank, exc)
        return []

    total_searches = 0

    for repo_info in repos_for_stage(finding.stage, journey):
        if total_searches >= SEARCH_BUDGET_PER_FINDING:
            break
        try:
            location, searches_run = search_client.find_gap(
                finding.rank, repo_info["repo"], search_terms
            )
        except CodeScoutExternalError as exc:
            # A failed repo lookup shouldn't stop other routing-matched
            # repos (or other findings) from being processed.
            logger.warning(
                "find_gap() failed for finding #%s in %r: %s", finding.rank, repo_info["repo"], exc
            )
            continue
        total_searches += searches_run
        if location is not None:
            assessment = assessor.assess(finding, location.file, location.snippet)
            return [
                CodeGap(
                    finding_rank=finding.rank,
                    origin=finding.origin,
                    stage=finding.stage,
                    service=repo_info["service"],
                    repo=repo_info["repo"],
                    mechanism_found=True,
                    gap_class=assessment.gap_class,
                    gap_statement=assessment.gap_statement,
                    file=location.file,
                    line=location.line,
                    snippet=location.snippet,
                    proposed_change_location=assessment.proposed_change_location,
                    search_terms_used=search_terms,
                    searches_run=total_searches,
                )
            ]

    # Nothing found in any routed repo within budget. mechanism_found=False is
    # a first-class outcome (contracts.py v3) - never fabricate a gap_class here.
    reason = "budget_exhausted" if total_searches >= SEARCH_BUDGET_PER_FINDING else "no_results"
    fallback_repo = repos_for_stage(finding.stage, journey)[0]
    return [
        CodeGap(
            finding_rank=finding.rank,
            origin=finding.origin,
            stage=finding.stage,
            service=fallback_repo["service"],
            repo=fallback_repo["repo"],
            mechanism_found=False,
            gap_class=None,
            gap_statement="No mechanism located for this finding within the search budget.",
            search_terms_used=search_terms,
            searches_run=total_searches,
            no_match_reason=reason,
        )
    ]
