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
from typing import Optional, Union

from app.pipeline.state import GraphState
from app.schemas.contracts import CodeGap, Finding, RunState, Suggestion, TrendReport, VocQuote

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


SUGGESTION_TYPE_LABELS = {"tech": "Tech", "business": "Business", "process": "Process"}


def _requirements_block(gap: Optional[CodeGap], suggestions: list[Suggestion]) -> str:
    """
    Functional requirements, numbered FR-N across BOTH sources in one list —
    a business/process suggestion is just as valid a requirement as a code
    fix (Harshit's ask, 2026-09-04: "not only PRD [code] — changes in the
    business, delivery, and other org verticals"), so it isn't relegated to
    a second-class appendix with its own numbering.

    Remedy Loop verdicts come first (Appendix A #9): ABSENT remedies become
    proposed FRs; EXISTING ones are surfaced so the PRD never re-proposes
    what's already built; PARTIAL needs a closer look; UNVERIFIED
    (status=None — the loop never actually searched, e.g. budget ran out
    first) gets its own honest label rather than folding into "partial"
    (PR #1 B4: "confirmed missing" is the strongest claim available and it
    was being attached to the verdict with the weakest support).

    Suggestions (tech/business/process, contracts.py decision #11) follow,
    continuing the same FR-N sequence, each labelled with its type and
    verification status so a reader can tell "proven missing" apart from
    "proposed, nothing to verify" apart from "we didn't get to check."
    """
    lines: list[str] = []
    n = 1

    if gap and gap.remedies:
        for r in gap.remedies:
            searched = len(r.searched_terms)
            tag = f"FR-{n}:"
            n += 1
            if r.status == "absent":
                lines.append(f"- {tag} **[FR candidate — not found in {searched} search{'es' if searched != 1 else ''}]** {r.proposal}")
            elif r.status == "exists":
                lines.append(
                    f"- {tag} **[Already built — do not re-propose]** {r.proposal} "
                    f"(`{r.evidence_file}:{r.evidence_line}`)"
                )
            elif r.status == "partial":
                lines.append(f"- {tag} **[Needs a closer look — partial match]** {r.proposal} — {r.evidence_file or 'related code found'}")
            else:
                lines.append(f"- {tag} **[Unverified — no search ran, e.g. budget exhausted first]** {r.proposal}")

    for s in suggestions:
        tag = f"FR-{n}:"
        n += 1
        type_label = SUGGESTION_TYPE_LABELS[s.suggestion_type]
        if s.verification_status == "exists":
            verdict = f"**[{type_label} — already built, do not re-propose]** ({s.evidence_file}:{s.evidence_line})"
        elif s.verification_status == "absent":
            verdict = f"**[{type_label} — not found in code, FR candidate]**"
        elif s.verification_status == "partial":
            verdict = f"**[{type_label} — needs a closer look, partial match]** ({s.evidence_file or 'related code found'})"
        elif s.verification_status == "unverified":
            verdict = f"**[{type_label} — unverified, budget exhausted before the check ran]**"
        else:  # not_applicable — business/process suggestions carry no code evidence by design
            verdict = f"**[{type_label} suggestion]**"
        lines.append(f"- {tag} {verdict} {s.title}: {s.description} — _{s.rationale}_")

    if not lines:
        return ""
    return "\n\n**Functional requirements (code fixes + suggested improvements, verified where applicable):**\n" + "\n".join(lines)


def _render_prd_llm_stub(
    finding: Finding,
    gaps: list[CodeGap],
    suggestions: list[Suggestion],
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

    requirements = _requirements_block(gap, suggestions)

    if gap and gap.mechanism_found:
        goals = f"Close the `{gap.gap_class}` gap at `{gap.repo}/{gap.file}:{gap.line}` without regressing existing behaviour."
        solution = (
            f"{GAP_CLASS_SOLUTION_HINTS[gap.gap_class]}\n\n"
            f"**Gap statement:** {gap.gap_statement}\n\n"
            f"**Location:** `{gap.repo}/{gap.file}:{gap.line}`"
            + (f"\n\n**Proposed change location:** {gap.proposed_change_location}" if gap.proposed_change_location else "")
            + requirements
        )
        scope = f"In scope: routing category `{finding.stage}` in `{gap.service}`. Out of scope: unrelated stages."
    elif gap and not gap.mechanism_found:
        goals = f"TODO(Code Scout): no mechanism found yet ({gap.no_match_reason}) — re-run the search or widen the term budget."
        solution = (
            f"Code Scout searched `{gap.repo}` ({gap.searches_run} of a 5-search budget) but found no matching "
            f"mechanism (reason: `{gap.no_match_reason}`). No code-level solution can be proposed until this resolves."
            + requirements
        )
        scope = f"In scope: routing category `{finding.stage}` in `{gap.repo}`. Out of scope: unrelated stages."
    elif suggestions:
        # No diagnosed code bug for this finding, but Code Scout's alternate
        # flow still surfaced improvement ideas (business/process/tech) —
        # that's a legitimate PRD on its own, not a TODO placeholder.
        repos = sorted({s.repo for s in suggestions})
        goals = f"Address the drop-off via the improvement(s) below rather than a diagnosed code bug — no code gap was located for this finding."
        solution = (
            f"Code Scout found no single diagnosed mechanism for this finding, but proposes the following "
            f"improvement(s) after exploring {', '.join(f'`{r}`' for r in repos)}."
            + requirements
        )
        scope = f"In scope: routing category `{finding.stage}` in {', '.join(f'`{r}`' for r in repos)}. Out of scope: unrelated stages."
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


MAX_PRDS_PER_RUN = 5


def prd_generator_node(state: GraphState) -> GraphState:
    """
    Generates one PRD per finding, not just the #1 ranked one — capped at
    MAX_PRDS_PER_RUN. `prd_draft` is kept as the #1 finding's markdown alone
    (existing field, other consumers read it) for backward compatibility;
    `prd_drafts` (new, additive) carries the full list.
    """
    run_state = RunState(**{k: v for k, v in state.items() if k != "error"})
    findings = sorted(run_state.findings, key=lambda f: f.rank)[:MAX_PRDS_PER_RUN]

    if not findings:
        return {**state, "prd_draft": None, "prd_drafts": [], "status": "completed", "error": "no_finding_to_draft_prd_for"}

    drafts = []
    for finding in findings:
        gaps = run_state.gaps_for(finding.rank)
        suggestions = run_state.suggestions_for(finding.rank)
        quotes = _collect_quotes(finding, run_state.voc.per_finding_quotes)
        title, body = _render_prd_llm_stub(
            finding,
            gaps,
            suggestions,
            run_state.trend_report,
            quotes,
            run_id=run_state.run_id,
            window_start=run_state.window_start,
            window_end=run_state.window_end,
        )
        drafts.append({"finding_rank": finding.rank, "title": title, "markdown": body})

    return {**state, "prd_draft": drafts[0]["markdown"], "prd_drafts": drafts, "status": "completed"}
