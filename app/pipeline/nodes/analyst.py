"""
Agent 2 — Analyst node wrapper. OWNER: Nakul (logic) / Mohit (wiring).

Thin adapter: converts the orchestrator's dict GraphState to/from the
pydantic RunState that app.agents.analyst.analyst.run_analyst speaks
natively, and supplies the `llm` callable (sphere-platform in real mode,
SphereClient(mode="replay") in demo_mode — a real recorded LLM session
against the real fixture data, not a hand-written script: see
fixtures/llm_replay/funnel-hypothesis-generation/{0..4}.json, 4
drill-down turns landing on 5 real findings including the rx-gated
30.0%-vs-39.0% one. Switched from a 2-turn hand-written stand-in per
PR #1 review M2 — that script reproduced less than the real verified
run already sitting in the tree.
"""
import json
from pathlib import Path
from typing import Any

from app.agents.analyst.analyst import run_analyst
from app.config import get_settings
from app.integrations.sphere import SphereClient, _live_llm_wanted, make_use_case_llm, replay_root_for
from app.pipeline.state import GraphState
from app.schemas.contracts import RunState

SPHERE_IDS_PATH = Path("fixtures/pd_checkout/sphere_ids.json")


def _demo_llm(journey: str = "pd_checkout") -> Any:
    client = SphereClient(mode="replay", replay_root=replay_root_for(journey))
    return lambda ctx: client.call("funnel-hypothesis-generation", 0, ctx)


def _sphere_llm() -> Any:
    settings = get_settings()
    ids = json.loads(SPHERE_IDS_PATH.read_text())
    template_id = next(
        u["template_id"] for u in ids["use_cases"] if u["name"] == settings.llm_use_case_funnel_dropoff
    )
    client = SphereClient(mode="sphere", service_type=settings.sphere_platform_service_type)

    def llm(ctx: dict) -> dict:
        # Template 21687 renders exactly one placeholder, {analysis_context}.
        # Flattening ctx into per-key params rendered an EMPTY prompt on the
        # first live API run; the model said so in its own reply.
        return client.call(settings.llm_use_case_funnel_dropoff, template_id,
                           {"analysis_context": json.dumps(ctx)})

    return llm


# Scripted correlation reasoning - NOT a live LLM call (PR #12 review point 2,
# Nakul). fixtures/llm_replay/ is a recorded-session guarantee everywhere else
# in this tree (see this module's own docstring above); voc-funnel-correlation
# has never been provisioned, so nothing under llm_replay/ can honestly be a
# recording for it. Matches app.pipeline.nodes.code_scout's _DEMO_REMEDIES
# pattern: hand-authored data lives in code, clearly labeled, not disguised
# as a replay fixture.
_DEMO_CORRELATIONS = [
    {
        "correlated": True,
        "theme": "cs/support",
        "rationale": (
            "The finding describes users stalling mid-flow after an unresolved issue "
            "with no path forward. The 'cs/support' theme's sample quotes independently "
            "describe slow or unreachable customer service at that same point in the "
            "journey - both plausibly describe the same missing real-time-support "
            "capability, even though this finding's own stage was never pre-mapped to "
            "cs/support in the journey config."
        ),
    },
    {
        "correlated": False,
        "theme": None,
        "rationale": (
            "No theme's sample quotes describe a problem consistent with this finding's "
            "hypothesis - the closest cluster (stock/medicine) is about inventory "
            "availability, unrelated to this finding's drop point."
        ),
    },
]


def _demo_correlation_llm() -> Any:
    """Phase 3.5 (2026-09-04) - scripted, not live. Sequential, like
    SphereClient's own replay mode: call N returns _DEMO_CORRELATIONS[N],
    repeating the last entry once exhausted."""
    calls = {"n": 0}

    def llm(ctx: dict) -> dict:
        i = min(calls["n"], len(_DEMO_CORRELATIONS) - 1)
        calls["n"] += 1
        return _DEMO_CORRELATIONS[i]

    return llm


def analyst_node(state: GraphState) -> GraphState:
    # "reviews" is pipeline-level input (like cohort_cuts), not a RunState
    # field - it's threaded to run_analyst() as its own argument below, same
    # as "error" was already excluded for being pipeline-only, not agent state.
    run_state = RunState(**{k: v for k, v in state.items() if k not in ("error", "reviews")})

    demo_mode = bool(state.get("demo_mode", True))
    journey = state.get("journey", "pd_checkout")
    live_wanted = _live_llm_wanted(demo_mode)
    llm = _sphere_llm() if live_wanted else _demo_llm(journey)

    voc_llm = make_use_case_llm(get_settings().llm_use_case_voc_theme_classification,
                                demo_mode, journey=journey)

    # Phase 3.5 (PR #12): demo mode uses the scripted _DEMO_CORRELATIONS above;
    # live mode uses the shared factory, which returns None (not a raise) until
    # voc-funnel-correlation is actually provisioned - run_analyst treats a
    # None correlation_llm as "skip this pass", never a crash. This replaces
    # an earlier hand-rolled _sphere_correlation_llm, which duplicated what
    # make_use_case_llm already does more safely and consistently.
    correlation_llm = (
        _demo_correlation_llm() if not live_wanted
        else make_use_case_llm(get_settings().llm_use_case_voc_correlation, demo_mode, journey=journey)
    )

    # 2026-09-04: reviews now come from the Fetcher via GraphState, not from
    # run_analyst()'s own demo-mode fixture fallback - the fetcher_node is
    # what actually owns fetching/scrubbing them. `or None` preserves that
    # fallback as a safety net for any caller whose state doesn't have this
    # key yet (e.g. an older checkpoint), not as the intended path.
    reviews = state.get("reviews") or None

    out = run_analyst(run_state, llm=llm, reviews=reviews, voc_llm=voc_llm, correlation_llm=correlation_llm)
    out = _apply_scope(out)

    return {**state, **out.model_dump()}


def _apply_scope(run_state: RunState) -> RunState:
    """
    Prompt-scoped analysis (decision #13): POST /runs {"dimensions":
    ["payments"]} narrows what surfaces to just that routing category
    instead of the full journey. Applied here, after run_analyst() returns,
    rather than inside it: it's a presentation-time filter on findings that
    already exist, not a change to how the Analyst explores — the drill-down
    budget and agentic search are unaffected, so scoping never costs search
    budget on categories it then discards.

    Ranks are left untouched on purpose (no renumbering to 1..N): a scoped
    finding keeps the severity rank it actually earned across the whole
    funnel, so "#3" stays visibly the third-worst drop-off even when
    everything else is filtered out — renumbering it to "#1" would overstate
    it. An empty result after filtering is a valid, honest outcome (nothing
    in the requested scope cleared the evidence gate) — downstream nodes
    already handle zero findings without erroring.
    """
    if not run_state.requested_dimensions:
        return run_state
    scope = set(run_state.requested_dimensions)
    run_state.findings = [f for f in run_state.findings if f.stage in scope]
    return run_state
