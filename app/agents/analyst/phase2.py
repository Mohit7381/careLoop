"""Analyst phase 2 — the agentic drill-down loop.

The LLM (sphere use case `funnel-hypothesis-generation`, template v4, strict
output schema) sees ONLY aggregates: the funnel table, the reason clusters,
and its own trail. It answers with either next_question{dimension} or
done+findings. The tool enforces the whitelist and the k-floor; this loop
enforces the budget. Everything the model asks and sees is persisted to
drilldown_trail — the trail renders in the UI and is half the demo.
"""
import json
import logging
import re
from typing import Optional, Any, Callable

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

from app.agents.analyst.aggregate_tool import AggregateTool
from app.schemas.contracts import DrilldownStep, Finding, GrowthIdea

logger = logging.getLogger(__name__)

BUDGET = 10

LLMCall = Callable[[dict[str, Any]], dict[str, Any]]  # context -> parsed model output


def _parse_findings(raw: list[dict], journey_routing_keys: list[str],
                    top_gap_stage: str) -> list[Finding]:
    findings = []
    for i, f in enumerate(raw or []):
        stage = f.get("stage") or top_gap_stage
        if stage not in journey_routing_keys:
            stage = top_gap_stage  # LLM speaks funnel-stage; Analyst owns routing
        findings.append(Finding(
            rank=i + 1, origin="warehouse", stage=stage,
            hypothesis=f.get("hypothesis", ""),
            confidence=f.get("confidence", "low"),
            confirm_via=f.get("confirm_via", ""),
            evidence=[{"type": "drilldown", "metric": str(e)[:120], "value": _num(e)}
                      for e in f.get("evidence", []) if _num(e) is not None],
        ))
    return findings


def _parse_growth_ideas(raw: list[dict]) -> list[GrowthIdea]:
    """Only ever populated on the concluding turn (see run_drilldown). A
    malformed entry — missing fields, or the wrong evidence/inspiration
    pairing GrowthIdea.model_post_init enforces — is dropped rather than
    aborting the whole run over one idea, matching this pipeline's usual
    per-item resilience."""
    ideas = []
    for g in raw or []:
        inspiration = g.get("inspiration")
        evidence = (
            [{"type": "drilldown", "metric": str(e)[:120], "value": _num(e)}
             for e in (g.get("evidence") or []) if _num(e) is not None]
            if inspiration == "funnel_data" else []
        )
        try:
            ideas.append(GrowthIdea(
                title=g.get("title", ""),
                description=g.get("description", ""),
                rationale=g.get("rationale", ""),
                inspiration=inspiration,
                target_stage=g.get("target_stage"),
                evidence=evidence,
            ))
        except ValueError as exc:
            logger.warning("dropping malformed growth idea (%r): %s", g.get("title"), exc)
    return ideas


def _num(e: Any) -> Any:
    """Extract the CITED number from a prose evidence string.

    The model writes evidence as "label: value" prose, and labels themselves
    contain digits — 'price_band: 75k_200k: 90,851' must yield 90851, not 75.
    Rule: drop numbers that are glued to letters (75k, 200k, gte_200k, v2) and
    take the LAST remaining standalone number, which is the value in every
    'label: ... : value' shape the model produces. Falls back to the first
    number if every candidate is label-glued.
    """
    if isinstance(e, (int, float)):
        return float(e)
    s = str(e)
    standalone = [m for m in _NUM_RE.finditer(s)
                  if not _glued(s, m.start(), m.end())]
    chosen = standalone[-1] if standalone else _NUM_RE.search(s)
    if not chosen:
        return None
    try:
        return float(chosen.group().replace(",", ""))
    except ValueError:
        return None


def _glued(s: str, start: int, end: int) -> bool:
    """True when the number touches a letter/underscore on either side —
    i.e. it is part of a label token (75k_200k) rather than a value."""
    before = s[start - 1] if start else ""
    after = s[end] if end < len(s) else ""
    return (before.isalpha() or before == "_") or (after.isalpha() or after == "_")


CUTS_PER_TURN = 2


def run_drilldown(llm: LLMCall, tool: AggregateTool, top_gap: dict,
                  phase1_summary: dict, journey_routing_keys: list[str],
                  routing_for_gap: str, budget: int = BUDGET,
                  voc_signals: Optional[list[dict]] = None,
                  ) -> tuple[list[Finding], list[DrilldownStep], list[GrowthIdea]]:
    trail: list[DrilldownStep] = []
    findings: list[Finding] = []
    growth_ideas: list[GrowthIdea] = []
    for _ in range(budget + 1):  # +1: final synthesis turn after budget exhausts
        tried = {s.dimension for s in trail}
        untried_rate_bearing = [d for d in tool.rate_bearing_dimensions if d not in tried]
        ctx = {
            "top_gap": top_gap,
            "phase1": phase1_summary,
            "drilldown_trail": [s.model_dump() for s in trail],
            # only dimensions that actually HAVE cohort data — asking for others wastes budget
            "allowed_dimensions": tool.dimensions_with_data,
            # of those, the ones carrying `converted` — the only cuts that can
            # show one segment converting worse than another. Prefer these.
            "rate_bearing_dimensions": tool.rate_bearing_dimensions,
            "rate_bearing_not_yet_tried": untried_rate_bearing,
            "dimensions_already_tried": sorted(tried),
            "budget_remaining": budget - len(trail),
            # Review themes, classified BEFORE the drill-down so the model can
            # use them to choose a cut. Context only: the evidence gate never
            # adds these counts to `shown`, so a finding that cites one is
            # rejected — funnel magnitudes stay warehouse-sourced.
            "voc_signals": voc_signals or [],
        }
        out = llm(ctx)
        if out.get("findings"):
            findings = _parse_findings(out["findings"], journey_routing_keys, routing_for_gap)
        # Growth ideas are only meaningful once the run has actually
        # concluded (the prompt is told never to send them otherwise), but
        # parse defensively off `done` rather than trusting that a stray
        # mid-run growth_ideas key never arrives.
        if out.get("done") and out.get("growth_ideas"):
            growth_ideas = _parse_growth_ideas(out["growth_ideas"])

        if len(trail) >= budget:
            break

        # Up to CUTS_PER_TURN dimensions are aggregated per model turn. Each turn
        # is a ~20 s sphere call and the turns are inherently sequential, so
        # letting the model name a second dimension (next_question.also_dimension,
        # template 21687 v8) halves the number of turns for the same trail.
        if out.get("done"):
            # EXPLORATION FLOOR. Concluding while a rate-bearing cut is still
            # untried is the one stopping condition we do not accept: those are
            # the only dimensions that can show a conversion gap, and a live run
            # was observed declaring done=True after 3 of 10 turns having never
            # looked at stock_status — which carries a 35.8pp spread against the
            # 9pp one it settled for. The choice of WHICH untried dimension is
            # deterministic (first alphabetically), not a second LLM call, so the
            # floor cannot itself be argued away by the model.
            if not untried_rate_bearing:
                break
            cuts = [(d, f"exploration floor: rate-bearing dimension '{d}' was never "
                        f"tried, so the run cannot conclude yet")
                    for d in untried_rate_bearing[:CUTS_PER_TURN]]
        else:
            nq = out.get("next_question") or {}
            dim = nq.get("dimension", "")
            cuts = [(dim, nq.get("rationale", f"cut by {dim}"))]
            also = (nq.get("also_dimension") or "").strip()
            if also and also != dim and also not in tried:
                cuts.append((also, f"second cut this turn: {also}"))

        for dim, rationale in cuts:
            if len(trail) >= budget:
                break
            result = tool.aggregate(top_gap.get("to_stage", "confirmed"), dim)
            trail.append(DrilldownStep(
                question=rationale,
                dimension=dim,
                result_rows=result.get("rows", []),
                note=("no cohort data — pick from dimensions_with_data" if result.get("no_data")
                      else "rejected: not whitelisted" if "error" in result
                      else "distribution_only" if result.get("distribution_only") else None),
            ))
    return findings, trail, growth_ideas
