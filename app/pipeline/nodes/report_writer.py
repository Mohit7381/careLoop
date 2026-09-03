"""
Analysis report renderer (FR-04). OWNER: Mohit.

Renders the snapshot + hypotheses into a Markdown report: funnel table,
segment highlights, ranked reasons, data-quality notes (suppressed
segments marked). Every number here must trace back to a snapshot row —
don't compute anything the snapshot/findings don't already contain.
"""
from app.pipeline.state import GraphState
from app.schemas.contracts import Finding, RunState


def _funnel_table(stages: list[dict]) -> str:
    rows = ["| Stage | Entered | Converted | CVR | Suppressed |", "|---|---|---|---|---|"]
    for s in stages:
        cvr = f"{s['converted'] / s['entered']:.1%}" if s["entered"] else "n/a"
        rows.append(f"| {s['stage']} | {s['entered']} | {s['converted']} | {cvr} | {'yes' if s.get('suppressed') else 'no'} |")
    return "\n".join(rows)


def _ranked_reasons(reasons: list[dict]) -> str:
    ranked = sorted(reasons, key=lambda r: r["count"], reverse=True)
    return "\n".join(f"- {r['cancellation_reason']}: {r['count']}" for r in ranked) or "_none recorded_"


def _evidence_phrase(f: Finding) -> str:
    """Origin-aware phrasing: a funnel number for warehouse, 'N users report X' for voc."""
    if f.origin == "voc":
        return f"{f.review_count} users report this in reviews (theme: {f.theme})"
    return ", ".join(f"{e.metric}={e.value}" for e in f.evidence)


def _findings_section(findings: list[Finding]) -> str:
    lines = []
    for f in sorted(findings, key=lambda f: f.rank):
        lines.append(
            f"**#{f.rank} [{f.origin}] {f.stage}** — {f.hypothesis} "
            f"(confidence {f.confidence}; {_evidence_phrase(f)})"
        )
    return "\n\n".join(lines) or "_no findings this run_"


def report_writer_node(state: GraphState) -> GraphState:
    run_state = RunState(**{k: v for k, v in state.items() if k != "error"})
    snapshot = run_state.snapshot

    report = f"""# CareLoop Analysis Report — run {run_state.run_id}

**Window:** {run_state.window_start} to {run_state.window_end}

## Funnel

{_funnel_table([s.model_dump() for s in snapshot.stages])}

## Ranked drop-off reasons

{_ranked_reasons([r.model_dump() for r in snapshot.reasons])}

## Findings

{_findings_section(run_state.findings)}

## Trend

{run_state.trend_report.narrative}

## Data-quality notes

- Segments below k={25} suppressed per privacy policy and marked above.
- {"Insufficient data" if not run_state.findings else f"{len(run_state.findings)} finding(s) produced this run."}
"""
    return {**state, "artifacts": state.get("artifacts", []) + [{"kind": "report_md", "content": report}]}
