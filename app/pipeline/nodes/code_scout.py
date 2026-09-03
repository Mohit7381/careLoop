"""
Agent 3 — Code Scout. OWNER: Harshit.

For each top finding: route to the owning service via the static
stage->repo table below (exact match on Finding.stage, a routing
category — not a funnel-stage id), have an LLM (`code-gap-assessment`
use case) propose 3-5 GitLab blob-search terms, fetch the top matching
files, and emit a CodeGap. `mechanism_found=False` is a first-class
outcome (mirrors the Analyst's "insufficient data" rule) — never guess a
gap_class when nothing was found. Read-only PAT; never writes diffs,
never opens MRs.

This file stubs the actual GitLab search + LLM search-term proposal —
swap `_search_terms_stub` and `_gitlab_blob_search_stub` for real calls
via app/integrations/gitlab_client.py before Day 2. Keep the CodeGap
contract shape stable; Mohit's Reporter/PRD nodes consume it.
"""
from app.pipeline.state import GraphState
from app.schemas.contracts import CodeGap, Finding, RoutingStage

# Routing table (from the service catalog) — exact match on the routing category, no fuzzy lookup.
STAGE_TO_REPO: dict[RoutingStage, list[str]] = {
    "consultation": ["bintan/consultation"],
    "pharmacy_checkout": ["timor/oms", "timor/fulfilment"],
    "payments": ["scrooge/payment-service"],
    "re_engagement": ["transformers/garuda"],
}

SEARCH_BUDGET_PER_FINDING = 5


def _search_terms_stub(finding: Finding) -> list[str]:
    """STUB — replace with the code-gap-assessment LLM call proposing 3-5 search terms."""
    if finding.origin == "voc" and finding.theme_search_terms:
        return finding.theme_search_terms
    return ["abandoned by system", "cancel", finding.stage]


def _gitlab_blob_search_stub(finding: Finding, repos: list[str], search_terms: list[str]) -> CodeGap:
    """
    STUB — replace with real GitLab blob search + file fetch
    (app/integrations/gitlab_client.py, read-only PAT).

    Hardcoded to the proven demo example (payment-timeout kill, routing
    category "consultation") so the pipeline is runnable end-to-end on
    Day 1 with a stubbed LLM. Harshit: any finding that isn't the proven
    example currently returns mechanism_found=False — replace both
    branches with real search + a genuine no_match_reason when the
    budget is actually exhausted.
    """
    if finding.stage == "consultation":
        return CodeGap(
            finding_rank=finding.rank,
            origin=finding.origin,
            stage=finding.stage,
            service="consultation",
            repo=repos[0] if repos else "bintan/consultation",
            mechanism_found=True,
            gap_class="missing_retention_hook",
            gap_statement=(
                "abandon script has no re-engagement hook; Garuda is never called before the kill"
            ),
            file="ConsultationDao.java",
            line=146,
            snippet="// TODO(Harshit): replace with the real fetched snippet (cap ~15 lines / 800 chars)",
            proposed_change_location="ConsultationDao.java:146, before GET_ABANDON_CONSULTATION executes",
            search_terms_used=search_terms,
            searches_run=2,
            no_match_reason=None,
        )

    return CodeGap(
        finding_rank=finding.rank,
        origin=finding.origin,
        stage=finding.stage,
        service=repos[0].split("/")[-1] if repos else "unknown",
        repo=repos[0] if repos else "unrouted",
        mechanism_found=False,
        gap_class=None,
        gap_statement="TODO(Harshit): stub has not run a real GitLab search for this routing category yet",
        search_terms_used=search_terms,
        searches_run=0,
        no_match_reason="no_results",
    )


def code_scout_node(state: GraphState) -> GraphState:
    findings = [Finding(**f) for f in state["findings"]]
    code_gaps: list[CodeGap] = []

    for finding in findings:
        repos = STAGE_TO_REPO.get(finding.stage, [])
        search_terms = _search_terms_stub(finding)[:SEARCH_BUDGET_PER_FINDING]
        gap = _gitlab_blob_search_stub(finding, repos, search_terms)
        code_gaps.append(gap)

    return {
        **state,
        "code_gaps": [g.model_dump() for g in code_gaps],
    }
