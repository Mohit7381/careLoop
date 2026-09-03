"""Code Scout's alternate output flow (Rev 3, PR #3): explore -> suggest ->
verify, producing Suggestion objects rather than CodeGap. Kept additive
alongside node.py's find_gap()-based code_scout_node - see contracts.py's
module docstring (decision #11) and this repo's PR #3 review (S2) for why
this isn't wired into app/pipeline/graph.py: which of the two Code Scout
output shapes (or both) ships is an explicit three-way decision (Nakul /
Mohit / Harshit), not something to force via whichever branch merges last.

  1. explore() the routing-matched repo(s) to inventory what already exists
     in that feature area (bounded by EXPLORATION_SEARCH_BUDGET).
  2. Generate suggestions via the assessor - improvements to what exists, or
     new features. NOT limited to code: business/process suggestions are
     equally valid and carry no code evidence.
  3. For suggestion_type="tech" only, verify against check_within_file()
     whether it's already built.

Shaped as a LangGraph node: a pure function taking RunState and returning a
dict of state updates. search_client/assessor are injected so tests (and
Day 1 vs Day 2) can swap Fixture/Stub for the live implementations without
touching this file.

External-call resilience (PR #3 review): explore()/propose_search_terms()/
propose_suggestions()/check_within_file() failing used to propagate and
crash the whole run. All four are now caught at finding/repo/verification
granularity - a bad call is logged and the run continues with whatever DID
resolve, and a verification failure reports "unverified" rather than being
conflated with "not_applicable" (nothing to check) or guessed at.
"""
from __future__ import annotations

import logging

from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.explore_search_client import ExploreSearchClient, GapLocation
from app.agents.code_scout.routing import repos_for_stage
from app.agents.code_scout.suggestion_assessor import FeatureSuggestionAssessor, SuggestionProposal
from app.schemas.contracts import Finding, RunState, Suggestion

logger = logging.getLogger(__name__)

EXPLORATION_SEARCH_BUDGET = 8  # searches to build the feature inventory, per finding
MAX_SUGGESTIONS_PER_FINDING = 5
VERIFICATION_PROXIMITY_LINES = 15  # "exists" if the signature is within this many lines of the cited mechanism


def suggestion_code_scout_node(
    state: RunState, *, search_client: ExploreSearchClient, assessor: FeatureSuggestionAssessor
) -> dict:
    new_suggestions: list[Suggestion] = []
    for finding in state.findings:
        new_suggestions.extend(_process_finding(finding, search_client, assessor, state.journey))
    return {"suggestions": [*state.suggestions, *new_suggestions]}


def _process_finding(
    finding: Finding, search_client: ExploreSearchClient, assessor: FeatureSuggestionAssessor, journey: str
) -> list[Suggestion]:
    try:
        search_terms = assessor.propose_search_terms(finding)
    except CodeScoutExternalError as exc:
        logger.warning("propose_search_terms failed for finding #%s: %s", finding.rank, exc)
        return []

    suggestions: list[Suggestion] = []

    for repo_info in repos_for_stage(finding.stage, journey):
        try:
            inventory, searches_run = search_client.explore(
                finding.rank, repo_info["repo"], search_terms, EXPLORATION_SEARCH_BUDGET
            )
        except CodeScoutExternalError as exc:
            logger.warning(
                "explore() failed for finding #%s in %r: %s", finding.rank, repo_info["repo"], exc
            )
            continue
        if not inventory:
            logger.info(
                "explore() found nothing for finding #%s in %r after %d search(es)",
                finding.rank, repo_info["repo"], searches_run,
            )
            continue

        try:
            proposals = assessor.propose_suggestions(finding, inventory)[:MAX_SUGGESTIONS_PER_FINDING]
        except CodeScoutExternalError as exc:
            logger.warning(
                "propose_suggestions failed for finding #%s in %r: %s", finding.rank, repo_info["repo"], exc
            )
            continue
        budget_remaining = EXPLORATION_SEARCH_BUDGET - searches_run

        for proposal in proposals:
            suggestions.append(
                _verify_and_build(
                    finding=finding,
                    proposal=proposal,
                    repo_info=repo_info,
                    inventory=inventory,
                    search_client=search_client,
                    search_terms=search_terms,
                    searches_run=searches_run,
                    budget_remaining=budget_remaining,
                )
            )
            if proposal.suggestion_type == "tech" and budget_remaining > 0:
                budget_remaining -= 1

    return suggestions


def _verify_and_build(
    *,
    finding: Finding,
    proposal: SuggestionProposal,
    repo_info: dict,
    inventory: list[GapLocation],
    search_client: ExploreSearchClient,
    search_terms: list[str],
    searches_run: int,
    budget_remaining: int,
) -> Suggestion:
    if proposal.suggestion_type != "tech" or not proposal.signature:
        # Business/process suggestions have nothing to verify against code,
        # and neither does a tech suggestion with no signature to check.
        return _suggestion(finding, proposal, repo_info, "not_applicable", search_terms, searches_run)

    if budget_remaining <= 0:
        # There WAS something to check, we just didn't get to it - distinct
        # from not_applicable: "we didn't check" must not read as "there
        # was nothing to check."
        return _suggestion(finding, proposal, repo_info, "unverified", search_terms, searches_run)

    try:
        evidence_line = search_client.check_within_file(
            finding.rank, repo_info["repo"], proposal.evidence_file, proposal.signature
        )
    except CodeScoutExternalError as exc:
        logger.warning(
            "check_within_file failed for finding #%s in %r: %s", finding.rank, repo_info["repo"], exc
        )
        return _suggestion(finding, proposal, repo_info, "unverified", search_terms, searches_run)

    mechanism_line = _line_for_file(inventory, proposal.evidence_file)

    if evidence_line is None:
        status = "absent"
    elif mechanism_line is not None and abs(evidence_line - mechanism_line) <= VERIFICATION_PROXIMITY_LINES:
        status = "exists"
    else:
        # Found in the same file, but far from the cited mechanism - the
        # capability exists in the codebase but isn't proven wired into this
        # specific path.
        status = "partial"

    return Suggestion(
        finding_rank=finding.rank,
        origin=finding.origin,
        stage=finding.stage,
        service=repo_info["service"],
        repo=repo_info["repo"],
        suggestion_type=proposal.suggestion_type,
        title=proposal.title,
        description=proposal.description,
        rationale=proposal.rationale,
        verification_status=status,
        evidence_file=proposal.evidence_file,
        evidence_line=evidence_line,
        search_terms_used=[*search_terms, proposal.signature],
        searches_run=searches_run + 1,
    )


def _suggestion(
    finding: Finding,
    proposal: SuggestionProposal,
    repo_info: dict,
    verification_status: str,
    search_terms: list[str],
    searches_run: int,
) -> Suggestion:
    return Suggestion(
        finding_rank=finding.rank,
        origin=finding.origin,
        stage=finding.stage,
        service=repo_info["service"],
        repo=repo_info["repo"],
        suggestion_type=proposal.suggestion_type,
        title=proposal.title,
        description=proposal.description,
        rationale=proposal.rationale,
        verification_status=verification_status,
        search_terms_used=search_terms,
        searches_run=searches_run,
    )


def _line_for_file(inventory: list[GapLocation], file: str) -> int | None:
    for loc in inventory:
        if loc.file == file:
            return loc.line
    return None
