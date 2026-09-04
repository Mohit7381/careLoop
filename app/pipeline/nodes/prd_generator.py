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

import logging
from typing import Any, Callable, Optional

from app.agents.evidence_gate import unsupported_numbers
from app.config import get_settings
from app.integrations.sphere import make_use_case_llm
from app.pipeline.state import GraphState
from app.schemas.contracts import CodeGap, Finding, RunState, TrendReport, VocQuote

logger = logging.getLogger("careloop.prd")
LLMCall = Callable[[dict[str, Any]], dict[str, Any]]

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "prd_template.md"

GAP_CLASS_SOLUTION_HINTS = {
    "logic_flaw": "Fix the incorrect logic at the cited line so the system stops behaving contrary to intent.",
    "missing_retention_hook": (
        "Add the missing re-engagement hook at the cited line so the user is proactively reached "
        "(push/WA/email) before the flow terminates, instead of silently killing it."
    ),
    "ux_gap": "Close the experience gap at the cited surface — the mechanism works, but the user isn't guided through it.",
    "unclassified": (
        "The mechanism was located at the cited line but could not be auto-classified — review it "
        "and classify (logic flaw / missing retention hook / UX gap) before proposing a fix."
    ),
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


def _remedies_block(gap: CodeGap) -> str:
    """
    Appendix A #9: ABSENT remedies become the PRD's proposed FRs; EXISTING
    ones are surfaced so the PRD never proposes what's already built;
    PARTIAL is flagged as needing a closer look. UNVERIFIED (status=None —
    the loop never actually searched, e.g. budget ran out first) gets its
    own honest label rather than being folded into "partial" — reviewed in
    PR #1 B4: "confirmed missing" is the strongest claim available and it
    was being attached to the verdict with the weakest support.
    """
    if not gap.remedies:
        return ""
    lines = ["\n\n**Remedy Loop verdicts (proposed fixes, verified against the code):**"]
    for r in gap.remedies:
        n = len(r.searched_terms)
        if r.status == "absent":
            lines.append(f"- **[FR candidate — not found in {n} search{'es' if n != 1 else ''}]** {r.proposal}")
        elif r.status == "exists":
            lines.append(
                f"- **[Already built — do not re-propose]** {r.proposal} "
                f"(`{r.evidence_file}:{r.evidence_line}`)"
            )
        elif r.status == "partial":
            lines.append(f"- **[Needs a closer look — partial match]** {r.proposal} — {r.evidence_file or 'related code found'}")
        else:
            lines.append(f"- **[Unverified — no search ran, e.g. budget exhausted first]** {r.proposal}")
    return "\n".join(lines)


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
            + _remedies_block(gap)
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
    if finding.confidence == "low":
        open_questions += f"\n- Hypothesis confidence is only '{finding.confidence}' — treat as unconfirmed."
    if gap and not gap.mechanism_found:
        open_questions += f"\n- Code Scout found no mechanism ({gap.no_match_reason}); solution above is a placeholder."

    body = (
        template.replace("{{title}}", title)
        .replace("{{run_id}}", str(run_id))
        .replace("{{window_start}}", window_start)
        .replace("{{window_end}}", window_end)
        .replace("{{confidence}}", finding.confidence)
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


def _prd_inputs(finding, gaps, trend, quotes, run_id, window_start, window_end) -> dict:
    """Exactly what the drafting model is allowed to know.

    Remedy verdicts are passed as structured `status` values, not prose. The
    model may word a requirement however it likes; whether the fix is already
    built is decided by the Remedy Loop and cannot be upgraded by writing more
    confidently — which is the failure this pipeline has corrected twice
    already ("confirmed missing" on an unsearched remedy).
    """
    gap = gaps[0] if gaps else None
    return {
        "run_id": run_id,
        "window": {"start": window_start, "end": window_end},
        "finding": {
            "rank": finding.rank, "origin": finding.origin, "stage": finding.stage,
            "hypothesis": finding.hypothesis, "confidence": finding.confidence,
            "confirm_via": finding.confirm_via,
            "segments": [{"dimension": s.dimension, "value": s.value} for s in finding.segments],
            "evidence": [{"metric": e.metric, "value": e.value} for e in finding.evidence],
            "review_count": finding.review_count, "theme": finding.theme,
        },
        "code_gap": None if gap is None else {
            "repo": gap.repo, "service": gap.service, "file": gap.file, "line": gap.line,
            "mechanism_found": gap.mechanism_found, "gap_class": gap.gap_class,
            "gap_statement": gap.gap_statement, "no_match_reason": gap.no_match_reason,
            "proposed_change_location": gap.proposed_change_location,
            "remedies": [{"proposal": r.proposal, "status": r.status,
                          "evidence_file": r.evidence_file,
                          "searches_run": len(r.searched_terms)} for r in gap.remedies],
        },
        "trend_narrative": trend.narrative,
        "anecdotal_quotes": [{"text": getattr(q, "text", str(q)),
                              "rating": getattr(q, "rating", None)} for q in quotes[:2]],
        "rules": [
            "Every number must come from these inputs. Do not compute new totals.",
            "Express targets relatively ('recover 5% of X'), never as an invented absolute count.",
            "A remedy's status is given; never restate an absent remedy as confirmed or built.",
            "No angle brackets anywhere in the output.",
        ],
    }


def _render_prd_llm(llm: LLMCall, inputs: dict) -> tuple[str, str]:
    """Returns (markdown, source). Falls back rather than shipping bad prose."""
    try:
        out = llm({"prd_inputs": inputs})
    except Exception as exc:                       # first-ever caller of 21691
        logger.warning("prd-generation call failed (%s) — deterministic PRD", exc)
        return "", f"llm_error:{type(exc).__name__}"

    body = (out.get("prd_markdown") or "").strip()
    if len(body) < 200:
        logger.warning("prd-generation returned %d chars — deterministic PRD", len(body))
        return "", "too_short"

    invented = unsupported_numbers(body, inputs)
    if invented:
        logger.warning("prd-generation cited ungrounded numbers %s — deterministic PRD", invented)
        return "", f"ungrounded_numbers:{invented}"
    return body, "llm"


def _with_draft_banner(body: str, run_id: int, window_start: str, window_end: str,
                       confidence: str) -> str:
    """The banner is ours, not the model's.

    It is the one line that stops a generated document being mistaken for an
    approved one, so it is prepended deterministically and any model-authored
    version is dropped — a drafting model must not be able to omit or soften it.
    """
    banner = (f"> **DRAFT — needs human review.** Generated by CareLoop run `{run_id}` on "
              f"`{window_start}`–`{window_end}`. Hypothesis confidence: `{confidence}`. "
              f"Never auto-filed as a ticket or MR.")
    kept = [ln for ln in body.splitlines() if "DRAFT" not in ln or not ln.lstrip().startswith(">")]
    return "\n".join([kept[0], "", banner, ""] + kept[1:]) if kept and kept[0].startswith("#") \
        else "\n".join([banner, ""] + kept)


def prd_generator_node(state: GraphState, *, llm: Optional[LLMCall] = None) -> GraphState:
    if llm is None:
        llm = make_use_case_llm(get_settings().llm_use_case_prd_generation,
                                bool(state.get("demo_mode", True)))
    run_state = RunState(**{k: v for k, v in state.items() if k != "error"})
    top = run_state.top_finding()

    if top is None:
        return {**state, "prd_draft": None, "status": "completed", "error": "no_finding_to_draft_prd_for"}

    gaps = run_state.gaps_for(top.rank)
    quotes = _collect_quotes(top, run_state.voc.per_finding_quotes)

    _title, deterministic = _render_prd_llm_stub(
        top, gaps, run_state.trend_report, quotes,
        run_id=run_state.run_id,
        window_start=run_state.window_start,
        window_end=run_state.window_end,
    )

    body, source = "", "deterministic"
    if llm is not None:
        inputs = _prd_inputs(top, gaps, run_state.trend_report, quotes,
                             run_state.run_id, run_state.window_start, run_state.window_end)
        body, source = _render_prd_llm(llm, inputs)
        if body:
            body = _with_draft_banner(body, run_state.run_id, run_state.window_start,
                                      run_state.window_end, top.confidence)
    if not body:
        body, source = deterministic, (source if source != "llm" else "deterministic")

    return {**state, "prd_draft": body, "status": "completed", "prd_source": source}
