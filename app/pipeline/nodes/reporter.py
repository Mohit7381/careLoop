"""
Reporter (rev 1.2/1.3). OWNER: Mohit.

Sits between Code Scout and the PRD generator. Computes period-over-period
deltas per stage/segment from the Fetcher's current+previous snapshot,
per-feature adoption movement from CT event counts, and VoC theme-share
movement. Turns the delta table into a short narrative — every sentence
tied to a delta row (same evidence-validator discipline as the Analyst).

The narrative is written by the `trend-narrative` sphere use case when an
`llm` is supplied, and by `_render_narrative` otherwise. The model only ever
sees the delta rows we chose to expose, each with an id, and template 21690's
schema forces every generated sentence to name one — so a sentence about a
comparison we deliberately refused to make (a right-censored stage, an
adoption event with no prior window) has no row to cite and cannot be written.
Anything that gets past that still goes through the numeric evidence gate.
The deterministic renderer stays as the fallback: this narrative is read by a
human who then approves a PRD, so a mechanical sentence beats a missing one.
"""
import logging
from typing import Any, Callable, Optional

from app.agents.code_scout.amplify import propose_feature_amplifications
from app.agents.evidence_gate import unsupported_numbers
from app.config import get_settings
from app.integrations.sphere import make_use_case_llm
from app.journeys import load_journey
from app.pipeline.state import GraphState
from app.schemas.contracts import AdoptionDelta, ShippedFix, StageDelta, TrendReport, VocThemeDelta

logger = logging.getLogger("careloop.reporter")
LLMCall = Callable[[dict[str, Any]], dict[str, Any]]

VOC_NOISE_FLOOR = 30
ADOPTION_FLAT_BAND = 0.05  # +/-5% counted as "flat"


def _rate(entered: int, converted: int) -> float:
    return round(converted / entered, 4) if entered else 0.0


def _downstream_maturing_stages(stage_order: list[str], maturing_stages: set[str]) -> set[str]:
    """
    A row's rate is entered->converted INTO the next stage, so the row that's
    actually right-censored is the one whose DOWNSTREAM neighbour is
    maturing, not the maturing stage's own row (that one is stage entry ->
    stage entry-equivalent and isn't the censored quantity). E.g. journey
    [created, confirmed, delivered] with maturing_stages=[delivered]: the
    'confirmed' row (confirmed->delivered) is censored, not 'delivered'
    itself (which is 100%->100% by construction and flagging it changes
    nothing) — caught in review, PR #1 B3.
    """
    out = set()
    for i, stage in enumerate(stage_order[:-1]):
        if stage_order[i + 1] in maturing_stages:
            out.add(stage)
    return out


def _stage_deltas(current: list[dict], previous: list[dict], stage_order: list[str], maturing_stages: set[str]) -> list[StageDelta]:
    """
    Appendix A #8: right-censored stages (e.g. "delivered") settle slowly —
    a fresh window looks artificially bad next to a matured one (94.5% vs
    69.2% on the frozen fixture). Those stages are marked `maturing` and
    excluded from the "biggest mover" ranking so the narrative never reports
    a phantom collapse; they're still reported, just not compared naively.
    """
    downstream_maturing = _downstream_maturing_stages(stage_order, maturing_stages)
    prev_by_key = {(s["stage"], s.get("segment", "all")): s for s in previous}
    deltas = []
    for cur in current:
        key = (cur["stage"], cur.get("segment", "all"))
        prev = prev_by_key.get(key)
        if not prev:
            continue
        prev_rate = _rate(prev["entered"], prev["converted"])
        cur_rate = _rate(cur["entered"], cur["converted"])
        deltas.append(
            StageDelta(
                stage=cur["stage"],
                segment=cur.get("segment"),
                previous_rate=prev_rate,
                current_rate=cur_rate,
                delta_pp=round((cur_rate - prev_rate) * 100, 2),
                maturing=cur["stage"] in downstream_maturing,
            )
        )
    comparable = [d for d in deltas if not d.maturing]
    maturing = [d for d in deltas if d.maturing]
    return sorted(comparable, key=lambda d: abs(d.delta_pp), reverse=True) + maturing


def _adoption_deltas(ct_events: list[dict]) -> tuple[list[AdoptionDelta], set[str]]:
    """
    Returns (deltas, no_prior_data) — the second is events with NO recorded
    previous-window row at all (as opposed to a real previous count of 0),
    e.g. the PD fixture's ct_events are current-window only. Absent data
    read as zero renders as fake 100% growth (review PR #1 M1) — callers
    must exclude no_prior_data events from prose, not just compute a trend.
    """
    by_event: dict[str, dict[str, int]] = {}
    seen_previous: set[str] = set()
    for row in ct_events:
        by_event.setdefault(row["event_name"], {"current": 0, "previous": 0})
        window = row.get("window", "current")
        by_event[row["event_name"]][window] += row["count"]
        if window == "previous":
            seen_previous.add(row["event_name"])

    deltas = []
    no_prior_data = set()
    for event_name, counts in by_event.items():
        prev, cur = counts["previous"], counts["current"]
        if event_name not in seen_previous:
            no_prior_data.add(event_name)
            trend = "flat"  # placeholder value; excluded from prose by callers
        elif prev == 0:
            trend = "faster" if cur > 0 else "flat"
        else:
            change = (cur - prev) / prev
            trend = "faster" if change > ADOPTION_FLAT_BAND else "slower" if change < -ADOPTION_FLAT_BAND else "flat"
        deltas.append(AdoptionDelta(feature=event_name, previous_count=prev, current_count=cur, trend=trend))
    return deltas, no_prior_data


def _voc_theme_deltas(themes: list[dict]) -> list[VocThemeDelta]:
    """
    Nakul's phase3_voc classifies a single window (no previous-window VoC
    count exists yet — that needs a second scrape run to compare against).
    previous_count is always 0 here; every escalated theme reads as
    "growing" until a real two-window VoC comparison lands.
    """
    deltas = []
    for theme in themes:
        cur = theme["count"]
        if cur < VOC_NOISE_FLOOR:
            continue
        deltas.append(VocThemeDelta(theme=theme["theme"], previous_count=0, current_count=cur, trend="growing"))
    return deltas


def _measure_shipped_impact(
    fix: dict, deltas: list[StageDelta], adoption: list[AdoptionDelta], events_by_rank: dict[int, set],
    top_gap_to_stage: Optional[str],
) -> dict:
    """Attaches a metric to a ShippedFix from a trend delta already computed
    above. Code Scout (app.agents.code_scout.impact) only ever supplies the
    commit-attribution half; this is the one place a number gets attached,
    and only when a real comparable delta exists — never a fabricated one.

    Prefers an adoption event named on the finding's own journey_events (the
    more literal "number of units" reading — e.g. a retention-push count)
    over the funnel stage's conversion rate; returns {} rather than pick an
    unrelated row when neither has a usable prior-window value.

    PR #22 review (Nakul): the conversion-rate branch used to compare
    `d.stage == fix["stage"]` — but StageDelta.stage is a FUNNEL stage
    (created/confirmed/delivered, from Fetcher's snapshot rows) while
    ShippedFix.stage is the finding's ROUTING CATEGORY (pharmacy_checkout/
    payments/…, a different vocabulary entirely) — they can never be equal,
    so this branch was dead code. Every finding in a run is about the same
    funnel transition (every cohort cut in drilldown_trail is taken at
    top_gap.to_stage — see phase2.run_drilldown), so that — not the
    routing category — is the right funnel-vocabulary value to compare
    a StageDelta against.
    """
    events = events_by_rank.get(fix["finding_rank"], set())
    for a in adoption:
        if a.feature in events and a.previous_count > 0:
            pct = round((a.current_count - a.previous_count) / a.previous_count * 100, 1)
            return {
                "metric_name": f"'{a.feature}' event volume", "metric_unit": "events",
                "previous_value": float(a.previous_count), "current_value": float(a.current_count),
                "pct_change": pct, "metric_ref": f"adoption:{a.feature}",
            }
    if top_gap_to_stage is not None:
        for d in deltas:
            if d.stage == top_gap_to_stage and not d.maturing and d.previous_rate > 0:
                pct = round((d.current_rate - d.previous_rate) / d.previous_rate * 100, 1)
                return {
                    "metric_name": f"conversion rate at '{d.stage}'", "metric_unit": "%",
                    "previous_value": round(d.previous_rate * 100, 2), "current_value": round(d.current_rate * 100, 2),
                    "pct_change": pct, "metric_ref": f"stage:{d.stage}",
                }
    return {}


def _render_narrative(
    deltas: list[StageDelta], adoption: list[AdoptionDelta], no_prior_data: set[str], voc: list[VocThemeDelta]
) -> str:
    """
    Absent previous-window data must never be read as zero and rendered as
    growth (review PR #1 M1) — adoption events in `no_prior_data` and every
    VoC theme (phase3_voc has no two-window comparison yet — Nakul's own
    note, previous_count is always a placeholder 0) are omitted from prose
    entirely rather than asserting a trend the data doesn't support.
    """
    lines = []
    if deltas:
        top = deltas[0]
        direction = "improved" if top.delta_pp > 0 else "worsened"
        lines.append(
            f"The biggest mover is '{top.stage}' ({top.segment}), which {direction} by "
            f"{abs(top.delta_pp)}pp ({top.previous_rate:.1%} -> {top.current_rate:.1%})."
        )
    movers = [a for a in adoption if a.trend != "flat" and a.feature not in no_prior_data]
    for a in movers[:3]:
        lines.append(f"'{a.feature}' usage is {a.trend} ({a.previous_count} -> {a.current_count}).")
    if voc:
        lines.append(
            "VoC theme volume this window (no prior-window comparison available yet): "
            + ", ".join(f"'{v.theme}' {v.current_count} negative reviews" for v in voc) + "."
        )
    if not lines:
        return "No stage, adoption, or VoC movement exceeded the noise floor this window."
    return " ".join(lines)


def _delta_rows(deltas, adoption, no_prior_data, voc, shipped_fixes=()) -> list[dict]:
    """The delta table the narrative model is allowed to reference.

    Every row gets an id, because template 21690's schema makes each generated
    sentence carry a `delta_ref` — a sentence with no row behind it cannot be
    written in the first place. Rows we deliberately refuse to compare
    (right-censored stages, adoption events with no prior window, VoC with no
    second scrape) are simply not in the table, so the model has nothing to
    assert a trend from.
    """
    rows = []
    for d in deltas:
        if d.maturing:
            continue
        if d.current_rate >= 0.9999 and d.previous_rate >= 0.9999:
            # The terminal stage's own row converts 100% -> 100% by construction
            # (nothing follows it). The narrative model once wrote "delivered
            # held steady at 100.00%" from it — true, vacuous, and confusing.
            continue
        rows.append({"id": f"stage:{d.stage}", "kind": "stage", "stage": d.stage,
                     "previous_rate": d.previous_rate, "current_rate": d.current_rate,
                     "delta_pp": d.delta_pp})
    for a in adoption:
        if a.feature in no_prior_data or a.trend == "flat":
            continue
        rows.append({"id": f"adoption:{a.feature}", "kind": "adoption", "feature": a.feature,
                     "previous_count": a.previous_count, "current_count": a.current_count,
                     "trend": a.trend})
    for v in voc:
        rows.append({"id": f"voc:{v.theme}", "kind": "voc_volume", "theme": v.theme,
                     "current_count": v.current_count,
                     "note": "single-window volume; no prior-window comparison exists yet"})
    for sf in shipped_fixes:
        if sf.get("metric_name") is None:
            continue
        rows.append({
            "id": f"shipped:{sf['finding_rank']}", "kind": "shipped_fix", "stage": sf["stage"],
            "commit_sha": sf["commit"]["short_sha"], "commit_date": sf["commit"]["date"],
            "metric_name": sf["metric_name"], "previous_value": sf["previous_value"],
            "current_value": sf["current_value"], "pct_change": sf["pct_change"],
            "note": "a fix shipped and this metric moved in the same window — correlation, not proven causation",
        })
    return rows


def _narrative_llm(llm: LLMCall, rows: list[dict]) -> tuple[str, str]:
    """Returns (narrative, source). Falls back rather than shipping bad prose."""
    if not rows:
        return "", "no_deltas"
    try:
        out = llm({"delta_table": rows})   # template 21690 renders {delta_table}
    except Exception as exc:                       # first-ever caller of 21690
        logger.warning("trend-narrative call failed (%s) — deterministic narrative", exc)
        return "", f"llm_error:{type(exc).__name__}"

    valid_refs = {r["id"] for r in rows}
    lines, dangling = [], []
    for line in out.get("narrative_lines") or []:
        ref, text = line.get("delta_ref"), (line.get("text") or "").strip()
        if not text:
            continue
        if ref not in valid_refs:
            dangling.append(ref)
            continue
        lines.append(text)

    if dangling:
        logger.warning("trend-narrative referenced unknown rows %s — deterministic narrative", dangling)
        return "", "dangling_delta_ref"
    if not lines:
        return "", "empty_narrative"

    narrative = " ".join(lines)
    invented = unsupported_numbers(narrative, rows)
    if invented:
        logger.warning("trend-narrative cited ungrounded numbers %s — deterministic narrative", invented)
        return "", f"ungrounded_numbers:{invented}"
    return narrative, "llm"


def reporter_node(state: GraphState, *, llm: Optional[LLMCall] = None) -> GraphState:
    if llm is None:
        llm = make_use_case_llm(get_settings().llm_use_case_trend_narrative,
                                bool(state.get("demo_mode", True)), journey=state.get("journey"))
    snapshot = state["snapshot"]
    journey_cfg = load_journey(state.get("journey", "pd_checkout"))
    maturing_stages = set(journey_cfg.get("maturing_stages", []))

    deltas = _stage_deltas(snapshot["stages"], snapshot["previous_stages"], journey_cfg["stages"], maturing_stages)
    adoption, no_prior_data = _adoption_deltas(snapshot["ct_events"])
    voc_deltas = _voc_theme_deltas(state["voc"].get("themes", []))

    events_by_rank = {f["rank"]: set(f.get("journey_events") or []) for f in state.get("findings", [])}
    top_gap_to_stage = state.get("top_gap_to_stage")
    shipped_models = [
        ShippedFix(**{**fix, **_measure_shipped_impact(fix, deltas, adoption, events_by_rank, top_gap_to_stage)})
        for fix in state.get("shipped_fixes", [])
    ]
    shipped_fixes = [sf.model_dump() for sf in shipped_models]

    # Auto-fetches every shipped fix that moved a real metric favourably
    # (pct_change > 0 — see app.agents.code_scout.amplify's module docstring
    # for why that's the "positive feedback" signal, not review sentiment)
    # and explores each for ideas that build forward on the win. None is
    # None in demo mode today (no scripted shipped-fix scenario exists yet),
    # exactly like shipped_fixes itself.
    amplification_llm = make_use_case_llm(
        get_settings().llm_use_case_code_gap, bool(state.get("demo_mode", True)), journey=state.get("journey"))
    feature_amplifications = [
        s.model_dump() for s in propose_feature_amplifications(amplification_llm, shipped_models)
    ]

    deterministic = _render_narrative(deltas, adoption, no_prior_data, voc_deltas)
    narrative, source = "", "deterministic"
    if llm is not None:
        narrative, source = _narrative_llm(
            llm, _delta_rows(deltas, adoption, no_prior_data, voc_deltas, shipped_fixes))
    if not narrative:
        narrative = deterministic
        source = source if source != "llm" else "deterministic"

    trend_report = TrendReport(
        deltas=deltas,
        adoption=adoption,
        voc_theme_deltas=voc_deltas,
        narrative=narrative,
    )

    return {
        **state,
        "status": "drafting_prd",
        "trend_report": trend_report.model_dump(),
        "shipped_fixes": shipped_fixes,
        "feature_amplifications": feature_amplifications,
        "narrative_source": source,
    }
