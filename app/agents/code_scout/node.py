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

Rev 3: assessor.assess() (now a real sphere-backed call in live mode, not
just the offline stub) gets the same treatment - a classification failure
AFTER a mechanism was already located is caught and treated as "not found
in this repo" rather than crashing the whole run or fabricating a
gap_class. CodeGap has no "located but unclassified" state, so this is the
most honest outcome the current schema can express - search continues in
the remaining routed repos.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from app.agents.code_scout.assessor import CodeGapAssessor
from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.routing import repos_for_stage
from app.agents.code_scout.search_client import SearchClient, normalise_term
from app.journeys import load_journey
from app.schemas.contracts import CodeGap, DrilldownStep, Finding, RunState

logger = logging.getLogger(__name__)

SEARCH_BUDGET_PER_FINDING = 5


MAX_SEARCH_TERMS = 8


def _cited_dimensions(finding: Finding, trail: list[DrilldownStep]) -> list[str]:
    """Which drill-down cuts this finding is about, read off the trail: a cut is
    cited if the finding's text names the dimension or any of its segment
    labels (the model writes "1_item converts at 0.4422", not "item_count")."""
    text = " ".join([finding.hypothesis, *(e.metric for e in finding.evidence)]).lower()
    cited = []
    for step in trail:
        if not step.result_rows:
            continue
        labels = [str(r.get("segment", "")).lower() for r in step.result_rows]
        if step.dimension.lower() in text or any(l and l in text for l in labels):
            cited.append(step.dimension)
    return cited


def seed_search_terms(finding: Finding, assessor: CodeGapAssessor, journey_cfg: dict,
                      trail: list[DrilldownStep]) -> list[str]:
    """Order search seeds by how likely each is to exist in backend source.

    A live run searched timor/oms for pharmacy.click.confirm_cart_button,
    3_to_5_items and basket_size — analytics events and segment labels — and
    spent its whole budget on zero hits. Code identifiers come from the journey
    config's verified code_hints: first the cut the finding cites, then its
    routing category. The assessor's terms (VoC theme terms or the model's
    proposals) follow. Analytics event names go LAST: they are the finding's
    provenance, not vocabulary any repo contains. Multi-word terms reduce to
    their longest token because GitLab blob search is literal.

    An assessor failure is not fatal here: the hints are still searched, and
    the caller decides what to do when the list is empty.
    """
    hints = journey_cfg.get("code_hints") or {}
    ordered: list[str] = []
    for dim in _cited_dimensions(finding, trail):
        ordered += (hints.get("by_dimension") or {}).get(dim, [])
    ordered += (hints.get("by_stage") or {}).get(finding.stage, [])

    events = set(finding.journey_events or [])
    try:
        proposed = list(assessor.propose_search_terms(finding))
    except CodeScoutExternalError as exc:
        logger.warning("propose_search_terms failed for finding #%s (%s) — hints only",
                       finding.rank, exc)
        proposed = []
    ordered += [t for t in proposed if t not in events]
    ordered += [t for t in proposed if t in events]

    seen: set[str] = set()
    out: list[str] = []
    for raw in ordered:
        term = normalise_term(raw)
        if term and term.lower() not in seen:
            seen.add(term.lower())
            out.append(term)
    return out[:MAX_SEARCH_TERMS]


# Findings are independent of each other, so they are scouted concurrently.
# Run 16 (live) spent ~600 of 909 s in this stage: six findings, each with
# a search-term proposal, an assessment and a remedy loop, all sequential.
CODE_SCOUT_WORKERS = 3


def code_scout_node(
    state: RunState, *, search_client: SearchClient, assessor: CodeGapAssessor
) -> dict:
    journey_cfg = load_journey(state.journey)
    findings = list(state.findings)

    def scout(finding: Finding) -> list[CodeGap]:
        return _process_finding(finding, search_client, assessor, state.journey,
                                journey_cfg, state.drilldown_trail)

    if len(findings) <= 1:
        per_finding = [scout(f) for f in findings]
    else:
        with ThreadPoolExecutor(max_workers=min(CODE_SCOUT_WORKERS, len(findings))) as pool:
            per_finding = list(pool.map(scout, findings))      # order preserved

    new_gaps: list[CodeGap] = [g for gaps in per_finding for g in gaps]
    return {"code_gaps": [*state.code_gaps, *new_gaps]}


def _process_finding(
    finding: Finding, search_client: SearchClient, assessor: CodeGapAssessor, journey: str,
    journey_cfg: dict | None = None, trail: list[DrilldownStep] | None = None,
) -> list[CodeGap]:
    search_terms = seed_search_terms(finding, assessor, journey_cfg or load_journey(journey),
                                     trail or [])
    if not search_terms:
        # No hints for this stage and the assessor gave nothing — skip the
        # finding rather than let it kill the whole run.
        logger.warning("no search terms for finding #%s — skipped", finding.rank)
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
            try:
                assessment = assessor.assess(finding, location.file, location.snippet)
            except CodeScoutExternalError as exc:
                # The mechanism IS located — that is the hard part and the
                # part a reviewer wants. Losing it because the classification
                # call failed reported nine real hits as "no_results" on a
                # live run. Record the location honestly as unclassified.
                logger.warning(
                    "assess() failed for finding #%s in %r (%s): %s — recording as unclassified",
                    finding.rank, repo_info["repo"], location.file, exc,
                )
                from app.agents.code_scout.assessor import GapAssessment
                assessment = GapAssessment(
                    gap_class="unclassified",
                    gap_statement=(f"Mechanism located at {location.file}:{location.line}; "
                                   f"automated assessment unavailable ({exc})"),
                    proposed_change_location=None,
                )
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
