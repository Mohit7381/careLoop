"""Analyst phase 2 — the agentic drill-down loop.

The LLM (sphere use case `funnel-hypothesis-generation`, template v4, strict
output schema) sees ONLY aggregates: the funnel table, the reason clusters,
and its own trail. It answers with either next_question{dimension} or
done+findings. The tool enforces the whitelist and the k-floor; this loop
enforces the budget. Everything the model asks and sees is persisted to
drilldown_trail — the trail renders in the UI and is half the demo.
"""
import json
import re
from typing import Any, Callable

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

from app.agents.analyst.aggregate_tool import AggregateTool
from app.schemas.contracts import DrilldownStep, Finding

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


def _num(e: Any) -> Any:
    """Evidence arrives as prose like 'user_total: 199,417' or 'lost 417,569
    (share 0.6452)' — extract the FIRST number anywhere in the string."""
    if isinstance(e, (int, float)):
        return float(e)
    m = _NUM_RE.search(str(e))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def run_drilldown(llm: LLMCall, tool: AggregateTool, top_gap: dict,
                  phase1_summary: dict, journey_routing_keys: list[str],
                  routing_for_gap: str, budget: int = BUDGET
                  ) -> tuple[list[Finding], list[DrilldownStep]]:
    trail: list[DrilldownStep] = []
    findings: list[Finding] = []
    for _ in range(budget + 1):  # +1: final synthesis turn after budget exhausts
        ctx = {
            "top_gap": top_gap,
            "phase1": phase1_summary,
            "drilldown_trail": [s.model_dump() for s in trail],
            # only dimensions that actually HAVE cohort data — asking for others wastes budget
            "allowed_dimensions": tool.dimensions_with_data,
            "dimensions_already_tried": sorted({s.dimension for s in trail}),
            "budget_remaining": budget - len(trail),
        }
        out = llm(ctx)
        if out.get("findings"):
            findings = _parse_findings(out["findings"], journey_routing_keys, routing_for_gap)
        if out.get("done") or len(trail) >= budget:
            break
        nq = out.get("next_question") or {}
        dim = nq.get("dimension", "")
        result = tool.aggregate(top_gap.get("to_stage", "confirmed"), dim)
        trail.append(DrilldownStep(
            question=nq.get("rationale", f"cut by {dim}"),
            dimension=dim,
            result_rows=result.get("rows", []),
            note=("no cohort data — pick from dimensions_with_data" if result.get("no_data")
                  else "rejected: not whitelisted" if "error" in result
                  else "distribution_only" if result.get("distribution_only") else None),
        ))
    return findings, trail
