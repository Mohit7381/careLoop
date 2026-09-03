"""
Agent 3 — Code Scout node wrapper. OWNER: Harshit (logic) / Mohit (wiring).

Thin adapter: converts the orchestrator's dict GraphState to/from the
pydantic RunState that app.agents.code_scout.node.code_scout_node speaks
natively, injects the search client + assessor (fixture-backed in
demo_mode, live GitLab + a rule-based stand-in assessor otherwise), then
runs the Remedy Loop (contracts v3 decision #9) on every gap where a
mechanism was actually found — the LLM+search logic lives in
app.agents.code_scout.remedy_loop, this just supplies the two callables
it needs.
"""
from pathlib import Path
from typing import Any

import requests

from app.agents.code_scout.assessor import StubCodeGapAssessor
from app.agents.code_scout.node import code_scout_node as _code_scout_node
from app.agents.code_scout.remedy_loop import run_remedy_loop
from app.agents.code_scout.routing import repos_for_stage
from app.agents.code_scout.search_client import FixtureSearchClient, LiveGitlabSearchClient
from app.config import get_settings
from app.pipeline.state import GraphState
from app.schemas.contracts import CodeGap, RunState

FIXTURES_DIR = Path("fixtures/code_scout")

# Scripted remedy proposals/verdicts matching the plan's demo script exactly
# (the "verify moment" panel) — not a live LLM call. Real wiring is the same
# shape as analyst.py's _sphere_llm(): a `code-gap-assessment` sphere call
# keyed on ctx["mode"] ("remedy_proposal" | "remedy_verification").
_DEMO_REMEDIES = [
    {
        "proposal": "Pre-abandon retention hook — re-engage the user before the batch kills the cart",
        "signature": "RetentionService.tryReengage in the abandon path",
        "search_terms": ["CartAbandonAdapterService", "RetentionService.tryReengage"],
        "verdict": {"status": "absent", "refined_search_terms": []},
    },
    {
        "proposal": "Soft-abandon grace state (SOFT_ABANDONED) before final abandonment",
        "signature": "a SOFT_ABANDONED state set before the final kill",
        "search_terms": ["CartState", "SOFT_ABANDONED", "markSoftAbandoned"],
        "verdict": {"status": "absent", "refined_search_terms": []},
    },
    {
        "proposal": "Longer / excluded abandon timeout for prescription-gated carts",
        "signature": "an rx-aware abandon timeout override",
        "search_terms": ["InternalAbandonOrderResource"],
        "verdict": {
            "status": "partial",
            "evidence_file": "InternalAbandonOrderResource.java",
            "evidence_snippet": "abandon reversal exists internally, no rx-aware timeout",
            "refined_search_terms": [],
        },
    },
]


def _demo_llm():
    def llm(ctx: dict) -> dict:
        if ctx["mode"] == "remedy_proposal":
            return {"remedies": [{k: v for k, v in r.items() if k != "verdict"} for r in _DEMO_REMEDIES]}
        proposal = ctx["remedy"]["proposal"]
        match = next((r for r in _DEMO_REMEDIES if r["proposal"] == proposal), None)
        return match["verdict"] if match else {"status": "absent", "refined_search_terms": []}

    return llm


def _demo_search_fn():
    return lambda repo, term: []  # scripted verdicts above don't depend on hit content


def _live_search_fn(settings) -> Any:
    def search_fn(repo: str, term: str) -> list[dict]:
        resp = requests.get(
            f"{settings.gitlab_base_url}/api/v4/projects/{repo.replace('/', '%2F')}/search",
            headers={"PRIVATE-TOKEN": settings.gitlab_read_token},
            params={"scope": "blobs", "search": term},
            timeout=10,
        )
        resp.raise_for_status()
        return [{"path": h["path"], "line": h.get("startline"), "snippet": h.get("data", "")[:400]} for h in resp.json()[:3]]

    return search_fn


def _unwired_live_llm():
    def llm(ctx: dict) -> dict:
        raise NotImplementedError(
            "Remedy Loop has no live LLM wired yet — see app/agents/code_scout/remedy_loop.py's "
            "docstring (code-gap-assessment, template 21689, modes remedy_proposal/remedy_verification). "
            "Same seam as analyst.py's _sphere_llm(); not yet built here. Run in demo_mode until it is."
        )

    return llm


def _run_remedies(run_state: RunState, gaps: list[CodeGap]) -> list[CodeGap]:
    settings = get_settings()
    llm = _demo_llm() if run_state.demo_mode else _unwired_live_llm()
    search_fn = _demo_search_fn() if run_state.demo_mode else _live_search_fn(settings)
    findings_by_rank = {f.rank: f for f in run_state.findings}

    out = []
    for gap in gaps:
        if not gap.mechanism_found:
            out.append(gap)
            continue
        finding = findings_by_rank.get(gap.finding_rank)
        summary = finding.hypothesis if finding else gap.gap_statement
        repos = [r["repo"] for r in repos_for_stage(gap.stage, run_state.journey)]
        out.append(run_remedy_loop(llm, search_fn, gap, summary, repos))
    return out


def code_scout_node(state: GraphState) -> GraphState:
    run_state = RunState(**{k: v for k, v in state.items() if k != "error"})
    settings = get_settings()

    if state.get("demo_mode", True):
        search_client = FixtureSearchClient(FIXTURES_DIR)
    else:
        search_client = LiveGitlabSearchClient(host=settings.gitlab_base_url, token=settings.gitlab_read_token)
    assessor = StubCodeGapAssessor()  # TODO(Harshit/Nakul): swap for the real code-gap-assessment sphere call

    result = _code_scout_node(run_state, search_client=search_client, assessor=assessor)
    gaps_with_remedies = _run_remedies(run_state, result["code_gaps"])

    return {**state, "status": "reporting", "code_gaps": [g.model_dump() for g in gaps_with_remedies]}
