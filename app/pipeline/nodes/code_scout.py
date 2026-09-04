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

Rev 2 (PR #3 review): _live_search_fn's requests call had nothing catching
it, and search_fn(repo, term) is called from inside remedy_loop.py's
verify_remedy() loop for every remedy on every gap - one flaky GitLab
response during verification used to crash code_scout_node's entire run,
taking down every OTHER gap's (already-located, already-assessed) remedies
with it. Now wrapped and isolated per-gap in _run_remedies(); a failed gap
keeps its located mechanism but ships with remedies=[] (the same "not yet
verified" shape mechanism_found=False gaps already use) instead of losing
the whole run. Also applies the same docs/test path filter as
search_client.py's find_gap() (review D1) - _live_search_fn used to take
the top 3 raw hits unfiltered.
"""
import json
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
from typing import Any
from urllib.error import URLError

import requests

from app.agents.code_scout.assessor import SpherePlatformCodeGapAssessor, StubCodeGapAssessor
from app.agents.code_scout.errors import CodeScoutExternalError
from app.agents.code_scout.node import code_scout_node as _code_scout_node
from app.agents.code_scout.remedy_loop import run_remedy_loop
from app.agents.code_scout.routing import repos_for_stage
from app.agents.code_scout.search_client import FixtureSearchClient, LiveGitlabSearchClient, is_source_path
from app.config import get_settings
from app.integrations.sphere import SphereClient
from app.pipeline.state import GraphState
from app.schemas.contracts import CodeGap, RunState

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path("fixtures/code_scout")
SPHERE_IDS_PATH = Path("fixtures/pd_checkout/sphere_ids.json")
REMEDY_USE_CASE = "code-gap-assessment"

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
        try:
            resp = requests.get(
                f"{settings.gitlab_base_url}/api/v4/projects/{repo.replace('/', '%2F')}/search",
                headers={"PRIVATE-TOKEN": settings.gitlab_read_token},
                params={"scope": "blobs", "search": term},
                timeout=10,
            )
            resp.raise_for_status()
            hits = resp.json()
        except requests.RequestException as exc:
            raise CodeScoutExternalError(f"GitLab search failed for {repo!r}/{term!r}: {exc}") from exc
        except ValueError as exc:
            raise CodeScoutExternalError(f"GitLab search returned invalid JSON for {repo!r}/{term!r}: {exc}") from exc
        source_hits = [h for h in hits if isinstance(h, dict) and "path" in h and is_source_path(h["path"])]
        return [
            {"path": h["path"], "line": h.get("startline"), "snippet": h.get("data", "")[:400]}
            for h in source_hits[:3]
        ]

    return search_fn


def _live_remedy_llm(settings) -> Any:
    """Real wiring for the Remedy Loop's LLM role (contracts v3 decision #9),
    keyed on ctx["mode"] ("remedy_proposal" | "remedy_verification") exactly
    as remedy_loop.py's own docstring documents. Uses the same SphereClient
    + calling convention already confirmed live in
    scripts/run_remedy_loop_local.py (the whole ctx as one JSON-string
    "code_context" param) rather than re-guessing the contract."""
    ids = json.loads(SPHERE_IDS_PATH.read_text())
    template_id = next(u["template_id"] for u in ids["use_cases"] if u["name"] == REMEDY_USE_CASE)
    client = SphereClient(mode="sphere", service_type=settings.sphere_platform_service_type)

    def llm(ctx: dict) -> dict:
        try:
            return client.call(REMEDY_USE_CASE, template_id, {"code_context": json.dumps(ctx)})
        except URLError as exc:
            raise CodeScoutExternalError(f"Sphere Platform call failed (mode={ctx.get('mode')!r}): {exc}") from exc
        except RuntimeError as exc:
            # SphereClient._live() raises RuntimeError itself when status != "SUCCESS".
            raise CodeScoutExternalError(f"Sphere Platform call did not succeed (mode={ctx.get('mode')!r}): {exc}") from exc
        except ValueError as exc:
            raise CodeScoutExternalError(
                f"Sphere Platform returned invalid JSON (mode={ctx.get('mode')!r}): {exc}"
            ) from exc

    return llm


DEMO_REMEDIES_REPO = "timor/oms"  # the only repo the scripted verdicts below are actually about


REMEDY_WORKERS = 3


def _mechanism_key(gap: CodeGap) -> tuple:
    return (gap.repo, gap.file, gap.line)


def _run_remedies(run_state: RunState, gaps: list[CodeGap]) -> list[CodeGap]:
    """
    demo_mode's scripted remedies are specific to the timor/oms abandon
    mechanism — applying them to a gap in a different repo produced a
    consultation gap citing an orders-repo file as evidence (review PR #1
    M3). Only run the scripted loop for gaps in that repo; other repos get
    no remedies in demo_mode rather than a mismatched one.

    The loop runs ONCE per located mechanism (repo, file, line), not once
    per finding: in run 16 three of six findings pinned
    OrderAbandonConfiguration.java:8 and each re-proposed and re-verified
    the same remedies against the same code — the verdicts are a property
    of the mechanism, so siblings share them. Distinct mechanisms are
    verified concurrently.
    """
    settings = get_settings()
    from app.integrations.sphere import _live_llm_wanted
    live = _live_llm_wanted(run_state.demo_mode)
    llm = _live_remedy_llm(settings) if live else _demo_llm()
    search_fn = _live_search_fn(settings) if live else _demo_search_fn()
    findings_by_rank = {f.rank: f for f in run_state.findings}

    eligible = {
        i for i, g in enumerate(gaps)
        if g.mechanism_found and not (run_state.demo_mode and g.repo != DEMO_REMEDIES_REPO)
    }
    leaders: dict[tuple, int] = {}                 # mechanism -> first gap that carries it
    for i in sorted(eligible):
        leaders.setdefault(_mechanism_key(gaps[i]), i)

    def verify(i: int) -> CodeGap:
        gap = gaps[i]
        finding = findings_by_rank.get(gap.finding_rank)
        summary = finding.hypothesis if finding else gap.gap_statement
        repos = [r["repo"] for r in repos_for_stage(gap.stage, run_state.journey)]
        try:
            return run_remedy_loop(llm, search_fn, gap, summary, repos)
        except CodeScoutExternalError as exc:
            # A GitLab outage mid-verification used to crash the entire
            # code_scout_node run, taking down every other gap's remedies
            # with it. Ship this gap with its located mechanism intact but
            # remedies=[] (same "not yet verified" shape mechanism_found=False
            # gaps already use) rather than lose the whole run over one gap.
            logger.warning(
                "run_remedy_loop failed for finding #%s (%s): %s", gap.finding_rank, gap.repo, exc
            )
            return gap

    lead_indices = list(leaders.values())
    if len(lead_indices) <= 1:
        verified = [verify(i) for i in lead_indices]
    else:
        with ThreadPoolExecutor(max_workers=min(REMEDY_WORKERS, len(lead_indices))) as pool:
            verified = list(pool.map(verify, lead_indices))
    by_key = {_mechanism_key(g): g for g in verified}

    out = []
    for i, gap in enumerate(gaps):
        if i not in eligible:
            out.append(gap)
        elif leaders[_mechanism_key(gap)] == i:
            out.append(by_key[_mechanism_key(gap)])
        else:
            lead = by_key[_mechanism_key(gap)]
            if lead.remedies:
                logger.info("finding #%s shares mechanism %s:%s with finding #%s — reusing %d remedy verdict(s)",
                            gap.finding_rank, gap.file, gap.line, lead.finding_rank, len(lead.remedies))
            out.append(gap.model_copy(update={"remedies": [r.model_copy() for r in lead.remedies]}))
    return out


def code_scout_node(state: GraphState) -> GraphState:
    run_state = RunState(**{k: v for k, v in state.items() if k not in ("error", "reviews")})
    settings = get_settings()

    from app.integrations.sphere import _live_llm_wanted
    if not _live_llm_wanted(state.get("demo_mode", True)):
        search_client = FixtureSearchClient(FIXTURES_DIR)
        assessor = StubCodeGapAssessor()
    else:
        search_client = LiveGitlabSearchClient(host=settings.gitlab_base_url, token=settings.gitlab_read_token)
        assessor = SpherePlatformCodeGapAssessor(service_type=settings.sphere_platform_service_type)

    result = _code_scout_node(run_state, search_client=search_client, assessor=assessor)
    gaps_with_remedies = _run_remedies(run_state, result["code_gaps"])

    return {**state, "status": "reporting", "code_gaps": [g.model_dump() for g in gaps_with_remedies]}
