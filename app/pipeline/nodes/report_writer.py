"""
Analysis report renderer (FR-04). OWNER: Mohit.

Renders the full run into an elaborate, sectioned Markdown report — one
section per analysis type (funnel, customer review/VoC, code gaps/bugs,
suggested improvements) rather than one flat "Findings" list, each closing
with a brief summary line (Halodoc hackathon chat, 2026-09-04: "separate
sections for all types of analysis... each section very elaborate... brief
summary on each section"). Every number here must trace back to a
snapshot/trend/voc/code_gap/suggestion row already on RunState — this file
renders, it never computes a fact the pipeline didn't already produce.
"""
from app.pipeline.state import GraphState
from app.schemas.contracts import (
    AdoptionDelta,
    CodeGap,
    Finding,
    RunState,
    StageDelta,
    Suggestion,
    VocThemeDelta,
)

SUGGESTION_TYPE_LABELS = {"tech": "Tech", "business": "Business", "process": "Process"}


# ---------------------------------------------------------------- funnel ---

def _funnel_table(stages: list[dict]) -> str:
    rows = ["| Stage | Entered | Converted | CVR | Suppressed |", "|---|---|---|---|---|"]
    for s in stages:
        cvr = f"{s['converted'] / s['entered']:.1%}" if s["entered"] else "n/a"
        rows.append(f"| {s['stage']} | {s['entered']} | {s['converted']} | {cvr} | {'yes' if s.get('suppressed') else 'no'} |")
    return "\n".join(rows)


def _ranked_reasons(reasons: list[dict]) -> str:
    ranked = sorted(reasons, key=lambda r: r["count"], reverse=True)
    return "\n".join(f"- {r['cancellation_reason']}: {r['count']}" for r in ranked) or "_none recorded_"


def _stage_delta_table(deltas: list[StageDelta]) -> str:
    if not deltas:
        return "_no period-over-period comparison available for this window_"
    rows = ["| Stage | Segment | Previous | Current | Δ pp | Maturing |", "|---|---|---|---|---|---|"]
    for d in deltas:
        rows.append(
            f"| {d.stage} | {d.segment or 'all'} | {d.previous_rate:.1%} | {d.current_rate:.1%} | "
            f"{d.delta_pp:+.1f} | {'yes — right-censored, treat as provisional' if d.maturing else 'no'} |"
        )
    return "\n".join(rows)


def _adoption_table(adoption: list[AdoptionDelta]) -> str:
    if not adoption:
        return "_no feature-adoption movement recorded this window_"
    rows = ["| Feature | Previous | Current | Trend |", "|---|---|---|---|"]
    for a in adoption:
        rows.append(f"| {a.feature} | {a.previous_count} | {a.current_count} | {a.trend} |")
    return "\n".join(rows)


def _funnel_section(snapshot, trend) -> str:
    matured = [d for d in trend.deltas if d.maturing]
    biggest = max((d for d in trend.deltas if not d.maturing), key=lambda d: abs(d.delta_pp), default=None)
    summary_bits = [f"{len(snapshot.stages)} stage row(s) analysed"]
    if biggest:
        direction = "up" if biggest.delta_pp > 0 else "down"
        summary_bits.append(f"biggest mover: `{biggest.stage}` {direction} {abs(biggest.delta_pp):.1f}pp")
    if matured:
        summary_bits.append(f"{len(matured)} stage(s) right-censored this window — treat as provisional")

    return f"""## 1. Funnel Analysis

### Funnel

{_funnel_table([s.model_dump() for s in snapshot.stages])}

### Ranked drop-off reasons

{_ranked_reasons([r.model_dump() for r in snapshot.reasons])}

### Period-over-period stage movement

{_stage_delta_table(trend.deltas)}

### Feature adoption movement

{_adoption_table(trend.adoption)}

### Narrative

{trend.narrative or "_no trend narrative generated this run_"}

**Summary:** {'; '.join(summary_bits)}.
"""


# --------------------------------------------------------- customer review ---

def _voc_theme_table(themes: list[dict]) -> str:
    if not themes:
        return "_no review themes classified this window_"
    ranked = sorted(themes, key=lambda t: t.get("count", 0), reverse=True)
    rows = ["| Theme | Negative reviews | Escalated to a finding |", "|---|---|---|"]
    for t in ranked:
        rows.append(f"| {t['theme']} | {t['count']} | {'yes' if t.get('escalated') else 'no'} |")
    return "\n".join(rows)


def _voc_theme_delta_table(deltas: list[VocThemeDelta]) -> str:
    if not deltas:
        return "_no prior-window review data to compare against_"
    rows = ["| Theme | Previous | Current | Trend |", "|---|---|---|---|"]
    for d in deltas:
        rows.append(f"| {d.theme} | {d.previous_count} | {d.current_count} | {d.trend} |")
    return "\n".join(rows)


def _quote_lines_for_finding(f: Finding, per_finding_quotes: dict) -> str:
    """f.top_quotes is already-formatted "[N★ date] text" strings (Analyst's
    own rendering); per_finding_quotes carries the same underlying quotes as
    structured VocQuote objects for a warehouse finding that converged with
    a VoC theme instead (the "human moment" case — see prd_generator.py's
    _collect_quotes). Prefer the former since it needs no reformatting."""
    if f.top_quotes:
        return "\n\n".join(f"> {q}" for q in f.top_quotes[:3])
    quotes = per_finding_quotes.get(str(f.rank), [])
    if not quotes:
        return ""
    return "\n\n".join(f"> {q.rating}★ · {q.date} — \"{q.text}\"" for q in quotes[:3])


def _voc_findings_section(voc_findings: list[Finding], per_finding_quotes: dict) -> str:
    if not voc_findings:
        return "_no review-driven finding escalated to the top ranks this window_"
    blocks = []
    for f in sorted(voc_findings, key=lambda f: f.rank):
        block = (
            f"**#{f.rank} routes to `{f.stage}`** — {f.hypothesis} "
            f"({f.review_count} users report this; confidence {f.confidence})"
        )
        quote_text = _quote_lines_for_finding(f, per_finding_quotes)
        if quote_text:
            block += "\n\n" + quote_text
        blocks.append(block)
    return "\n\n".join(blocks)


def _customer_review_section(voc, voc_findings: list[Finding], voc_theme_deltas: list[VocThemeDelta]) -> str:
    meta = voc.reviews_meta
    total = meta.get("total", 0)
    negatives = meta.get("negatives", 0)
    escalated = [t for t in voc.themes if t.get("escalated")]
    summary_bits = [f"{total} review(s) pulled, {negatives} negative"]
    if escalated:
        summary_bits.append(
            f"{len(escalated)} theme(s) escalated to a finding: {', '.join(t['theme'] for t in escalated)}"
        )
    else:
        summary_bits.append("no theme cleared the escalation threshold this window")

    return f"""## 2. Customer Review Analysis (Voice of Customer)

### Review volume

- Total reviews pulled: {total}
- Negative reviews (rating ≤ 2): {negatives}
- Escalation threshold: {meta.get('threshold', 'n/a')} negative reviews per theme

### Theme breakdown

{_voc_theme_table(voc.themes)}

### Theme movement vs prior window

{_voc_theme_delta_table(voc_theme_deltas)}

### Escalated findings & representative quotes

{_voc_findings_section(voc_findings, voc.per_finding_quotes)}

**Summary:** {'; '.join(summary_bits)}.
"""


# -------------------------------------------------------- warehouse findings ---

def _evidence_phrase(f: Finding) -> str:
    if f.origin == "voc":
        return f"{f.review_count} users report this in reviews (theme: {f.theme})"
    return ", ".join(f"{e.metric}={e.value}" for e in f.evidence)


def _warehouse_findings_section(warehouse_findings: list[Finding]) -> str:
    if not warehouse_findings:
        return "## 3. Drop-off Findings\n\n_no warehouse-driven findings this run_\n\n**Summary:** no warehouse findings.\n"
    lines = []
    for f in sorted(warehouse_findings, key=lambda f: f.rank):
        lines.append(
            f"**#{f.rank} {f.stage}** — {f.hypothesis} "
            f"(confidence {f.confidence}; {_evidence_phrase(f)})"
        )
    high_conf = sum(1 for f in warehouse_findings if f.confidence == "high")
    return f"""## 3. Drop-off Findings (funnel-data-driven, ranked by magnitude)

{chr(10).join(lines)}

**Summary:** {len(warehouse_findings)} finding(s), {high_conf} at high confidence.
"""


# ------------------------------------------------------------ code gaps ---

def _remedy_line(r) -> str:
    n = len(r.searched_terms)
    if r.status == "absent":
        return f"  - **[not found in {n} search{'es' if n != 1 else ''}]** {r.proposal}"
    if r.status == "exists":
        return f"  - **[already built]** {r.proposal} (`{r.evidence_file}:{r.evidence_line}`)"
    if r.status == "partial":
        return f"  - **[partial match]** {r.proposal} — {r.evidence_file or 'related code found'}"
    return f"  - **[unverified]** {r.proposal}"


def _code_gaps_section(code_gaps: list[CodeGap]) -> str:
    if not code_gaps:
        return "## 4. Code Gaps & Bugs\n\n_Code Scout did not run, or routed no findings, this run_\n\n**Summary:** no code gaps.\n"

    found = [g for g in code_gaps if g.mechanism_found]
    not_found = [g for g in code_gaps if not g.mechanism_found]

    blocks = []
    for g in sorted(found, key=lambda g: g.finding_rank):
        block = (
            f"**Finding #{g.finding_rank} — `{g.gap_class}` in `{g.repo}`**\n\n"
            f"{g.gap_statement}\n\n"
            f"Location: `{g.file}:{g.line}`"
        )
        if g.remedies:
            block += "\n\nRemedy Loop verdicts:\n" + "\n".join(_remedy_line(r) for r in g.remedies)
        blocks.append(block)
    for g in sorted(not_found, key=lambda g: g.finding_rank):
        blocks.append(
            f"**Finding #{g.finding_rank} — no mechanism found in `{g.repo}`**\n\n"
            f"Searched {g.searches_run} time(s); reason: `{g.no_match_reason}`."
        )

    total_remedies = sum(len(g.remedies) for g in found)
    body = "\n\n".join(blocks)
    return f"""## 4. Code Gaps & Bugs

{body}

**Summary:** {len(found)} mechanism(s) pinned across {len(code_gaps)} gap(s) explored, {total_remedies} remedy verdict(s).
"""


# -------------------------------------------------------- suggestions ---

def _suggestion_line(s: Suggestion) -> str:
    label = SUGGESTION_TYPE_LABELS[s.suggestion_type]
    verdict = {
        "exists": f"already built — do not re-propose (`{s.evidence_file}:{s.evidence_line}`)",
        "absent": "not found in code — candidate",
        "partial": f"needs a closer look — partial match ({s.evidence_file or 'related code found'})",
        "unverified": "unverified — budget exhausted before the check ran",
        "not_applicable": "no code verification needed",
    }[s.verification_status]
    return f"- **[{label}]** {s.title} ({verdict}) — {s.description} _{s.rationale}_"


def _suggestions_section(suggestions: list[Suggestion]) -> str:
    if not suggestions:
        return (
            "## 5. Suggested Improvements (Business / Process / Tech)\n\n"
            "_no improvement ideas surfaced this run_\n\n**Summary:** none.\n"
        )
    by_finding: dict[int, list[Suggestion]] = {}
    for s in suggestions:
        by_finding.setdefault(s.finding_rank, []).append(s)

    blocks = []
    for rank in sorted(by_finding):
        items = by_finding[rank]
        blocks.append(f"**Finding #{rank}**\n\n" + "\n".join(_suggestion_line(s) for s in items))

    counts = {t: sum(1 for s in suggestions if s.suggestion_type == t) for t in ("tech", "business", "process")}
    summary = ", ".join(f"{n} {t}" for t, n in counts.items() if n)
    body = "\n\n".join(blocks)
    return f"""## 5. Suggested Improvements (Business / Process / Tech)

{body}

**Summary:** {len(suggestions)} suggestion(s) — {summary}.
"""


# ------------------------------------------------------------------ node ---

def report_writer_node(state: GraphState) -> GraphState:
    run_state = RunState(**{k: v for k, v in state.items() if k not in ("error", "reviews")})
    warehouse_findings = [f for f in run_state.findings if f.origin == "warehouse"]
    voc_findings = [f for f in run_state.findings if f.origin == "voc"]

    report = f"""# CareLoop Analysis Report — run {run_state.run_id}

**Window:** {run_state.window_start} to {run_state.window_end}

{_funnel_section(run_state.snapshot, run_state.trend_report)}

{_customer_review_section(run_state.voc, voc_findings, run_state.trend_report.voc_theme_deltas)}

{_warehouse_findings_section(warehouse_findings)}

{_code_gaps_section(run_state.code_gaps)}

{_suggestions_section(run_state.suggestions)}

## 6. Data-quality notes

- Segments below k={25} suppressed per privacy policy and marked above.
- {"Insufficient data" if not run_state.findings else f"{len(run_state.findings)} finding(s) produced this run."}
"""
    return {**state, "artifacts": state.get("artifacts", []) + [{"kind": "report_md", "content": report}]}
