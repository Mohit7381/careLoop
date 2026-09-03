"""
PRD Generator (FR-05). OWNER: Mohit.

Fills the prd-generator template's 8 sections from findings + code_gaps +
trend_report + voc via the `prd-generation` sphere-platform use case.
<=2 user quotes in the Problem section, labelled anecdotal. Unverified
assumptions land in Section 8. Stamped DRAFT — never auto-filed.

`_render_prd_llm_stub` below does template-filling with plain string
formatting so this runs without live LLM credentials (Day 1 gate). Swap
it for a real sphere-platform call (use case:
settings.llm_use_case_prd_generation) when ready — keep the "<=2 quotes,
labelled anecdotal" and "unconfirmed assumptions -> Section 8" rules.
"""
from pathlib import Path
from typing import Union

from app.pipeline.state import GraphState
from app.schemas.contracts import CodeGap, Finding, RunState, TrendReport, VocQuote

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "prd_template.md"

GAP_CLASS_SOLUTION_HINTS = {
    "logic_flaw": "Fix the incorrect logic at the cited line so the system stops behaving contrary to intent.",
    "missing_retention_hook": (
        "Add the missing re-engagement hook at the cited line so the user is proactively reached "
        "(push/WA/email) before the flow terminates, instead of silently killing it."
    ),
    "ux_gap": "Close the experience gap at the cited surface — the mechanism works, but the user isn't guided through it.",
}


def _evidence_phrase(finding: Finding) -> str:
    """Origin-aware: a funnel number for warehouse, 'N users report X' for voc."""
    if finding.origin == "voc":
        return f"{finding.review_count} users report this in reviews (theme: {finding.theme})"
    return "; ".join(f"{e.metric}={e.value}" for e in finding.evidence)


def _quote_line(quote: Union[str, VocQuote, dict]) -> str:
    if isinstance(quote, str):
        return f'> "{quote}"'
    q = quote.model_dump() if hasattr(quote, "model_dump") else quote
    return f"> {q['rating']}★ · {q['date']} — \"{q['text']}\""


def _collect_quotes(finding: Finding, per_finding_quotes: dict) -> list:
    """
    voc-origin findings carry their own top_quotes; a warehouse-origin finding whose
    routing stage converged with a VoC theme (the demo's 'human moment') gets its
    quotes from Voc.per_finding_quotes instead.
    """
    if finding.top_quotes:
        return list(finding.top_quotes)
    return list(per_finding_quotes.get(str(finding.rank), []))


def _render_prd_llm_stub(
    finding: Finding,
    gaps: list[CodeGap],
    trend: TrendReport,
    quotes: list,
    run_id: int,
    window_start: str,
    window_end: str,
) -> tuple[str, str]:
    template = TEMPLATE_PATH.read_text()
    gap = gaps[0] if gaps else None
    quotes = quotes[:2]  # Section 3 rule: at most 2 quotes, labelled anecdotal

    quote_block = ""
    if quotes:
        quote_block = "\n\n**User voice (anecdotal):**\n" + "\n".join(_quote_line(q) for q in quotes)

    title = f"Fix: {finding.hypothesis.splitlines()[0][:80]}"
    problem = (
        f"{finding.hypothesis} Evidence: {_evidence_phrase(finding)}. "
        f"Confirm via: {finding.confirm_via}."
        + quote_block
    )
    segment_desc = ", ".join(f"{s.dimension}={s.value}" for s in finding.segments) or "all"
    background = f"Routing category `{finding.stage}` (segments: {segment_desc}). Trend context: {trend.narrative}"

    if gap and gap.mechanism_found:
        goals = f"Close the `{gap.gap_class}` gap at `{gap.repo}/{gap.file}:{gap.line}` without regressing existing behaviour."
        solution = (
            f"{GAP_CLASS_SOLUTION_HINTS[gap.gap_class]}\n\n"
            f"**Gap statement:** {gap.gap_statement}\n\n"
            f"**Location:** `{gap.repo}/{gap.file}:{gap.line}`"
            + (f"\n\n**Proposed change location:** {gap.proposed_change_location}" if gap.proposed_change_location else "")
        )
        scope = f"In scope: routing category `{finding.stage}` in `{gap.service}`. Out of scope: unrelated stages."
    elif gap and not gap.mechanism_found:
        goals = f"TODO(Code Scout): no mechanism found yet ({gap.no_match_reason}) — re-run the search or widen the term budget."
        solution = (
            f"Code Scout searched `{gap.repo}` ({gap.searches_run} of a 5-search budget) but found no matching "
            f"mechanism (reason: `{gap.no_match_reason}`). No code-level solution can be proposed until this resolves."
        )
        scope = f"In scope: routing category `{finding.stage}` in `{gap.repo}`. Out of scope: unrelated stages."
    else:
        goals = "TODO(Code Scout): no code gap was routed for this finding yet."
        solution = "TODO(Code Scout): pipeline ran without a resolved code_gap for the top finding."
        scope = f"In scope: routing category `{finding.stage}`. Out of scope: unrelated stages."

    success_metrics = (
        f"Stage conversion for routing category `{finding.stage}` moves within ±2pp of the Power BI baseline "
        f"post-fix; no regression in adjacent stages."
    )
    open_questions = "- " + finding.confirm_via
    if finding.confidence < 0.6:
        open_questions += f"\n- Hypothesis confidence is only {finding.confidence:.0%} — treat as unconfirmed."
    if gap and not gap.mechanism_found:
        open_questions += f"\n- Code Scout found no mechanism ({gap.no_match_reason}); solution above is a placeholder."

    body = (
        template.replace("{{title}}", title)
        .replace("{{run_id}}", str(run_id))
        .replace("{{window_start}}", window_start)
        .replace("{{window_end}}", window_end)
        .replace("{{confidence}}", f"{finding.confidence:.0%}")
        .replace("{{overview}}", f"CareLoop-generated fix proposal for the #{finding.rank} ranked drop-off finding.")
        .replace("{{background}}", background)
        .replace("{{problem}}", problem)
        .replace("{{goals}}", goals)
        .replace("{{gap_class}}", (gap.gap_class if gap and gap.gap_class else "unclassified"))
        .replace("{{solution}}", solution)
        .replace("{{scope}}", scope)
        .replace("{{success_metrics}}", success_metrics)
        .replace("{{open_questions}}", open_questions)
    )
    return title, body


def prd_generator_node(state: GraphState) -> GraphState:
    run_state = RunState(**{k: v for k, v in state.items() if k != "error"})
    top = run_state.top_finding()

    if top is None:
        return {**state, "prd_draft": None, "status": "completed", "error": "no_finding_to_draft_prd_for"}

    gaps = run_state.gaps_for(top.rank)
    quotes = _collect_quotes(top, run_state.voc.per_finding_quotes)

    _title, body = _render_prd_llm_stub(
        top,
        gaps,
        run_state.trend_report,
        quotes,
        run_id=run_state.run_id,
        window_start=run_state.window_start,
        window_end=run_state.window_end,
    )

    return {**state, "prd_draft": body, "status": "reporting"}
