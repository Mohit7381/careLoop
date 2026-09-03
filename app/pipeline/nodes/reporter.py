"""
Reporter (rev 1.2/1.3). OWNER: Mohit.

Sits between Code Scout and the PRD generator. Computes period-over-period
deltas per stage/segment from the Fetcher's current+previous snapshot,
per-feature adoption movement from CT event counts, and VoC theme-share
movement. Turns the delta table into a short narrative — every sentence
tied to a delta row (same evidence-validator discipline as the Analyst).

The narrative renderer here is template-based so the pipeline is fully
runnable without live LLM credentials (Day 1 gate). Swap
`_render_narrative` for a real sphere-platform call
(use case: settings.llm_use_case_trend_narrative) when ready — keep the
"every sentence cites a delta row" rule when you do.
"""
from app.journeys import load_journey
from app.pipeline.state import GraphState
from app.schemas.contracts import AdoptionDelta, StageDelta, TrendReport, VocThemeDelta

VOC_NOISE_FLOOR = 30
ADOPTION_FLAT_BAND = 0.05  # +/-5% counted as "flat"


def _rate(entered: int, converted: int) -> float:
    return round(converted / entered, 4) if entered else 0.0


def _stage_deltas(current: list[dict], previous: list[dict], maturing_stages: set[str]) -> list[StageDelta]:
    """
    Appendix A #8: right-censored stages (e.g. "delivered") settle slowly —
    a fresh window looks artificially bad next to a matured one (94.5% vs
    69.2% on the frozen fixture). Those stages are marked `maturing` and
    excluded from the "biggest mover" ranking so the narrative never reports
    a phantom collapse; they're still reported, just not compared naively.
    """
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
                maturing=cur["stage"] in maturing_stages,
            )
        )
    comparable = [d for d in deltas if not d.maturing]
    maturing = [d for d in deltas if d.maturing]
    return sorted(comparable, key=lambda d: abs(d.delta_pp), reverse=True) + maturing


def _adoption_deltas(ct_events: list[dict]) -> list[AdoptionDelta]:
    by_event: dict[str, dict[str, int]] = {}
    for row in ct_events:
        by_event.setdefault(row["event_name"], {"current": 0, "previous": 0})
        by_event[row["event_name"]][row.get("window", "current")] += row["count"]

    deltas = []
    for event_name, counts in by_event.items():
        prev, cur = counts["previous"], counts["current"]
        if prev == 0:
            trend = "faster" if cur > 0 else "flat"
        else:
            change = (cur - prev) / prev
            trend = "faster" if change > ADOPTION_FLAT_BAND else "slower" if change < -ADOPTION_FLAT_BAND else "flat"
        deltas.append(AdoptionDelta(feature=event_name, previous_count=prev, current_count=cur, trend=trend))
    return deltas


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


def _render_narrative(deltas: list[StageDelta], adoption: list[AdoptionDelta], voc: list[VocThemeDelta]) -> str:
    lines = []
    if deltas:
        top = deltas[0]
        direction = "improved" if top.delta_pp > 0 else "worsened"
        lines.append(
            f"The biggest mover is '{top.stage}' ({top.segment}), which {direction} by "
            f"{abs(top.delta_pp)}pp ({top.previous_rate:.1%} -> {top.current_rate:.1%})."
        )
    movers = [a for a in adoption if a.trend != "flat"]
    for a in movers[:3]:
        lines.append(f"'{a.feature}' usage is {a.trend} ({a.previous_count} -> {a.current_count}).")
    for v in voc:
        lines.append(f"VoC theme '{v.theme}' is {v.trend} ({v.previous_count} -> {v.current_count} negative reviews).")
    if not lines:
        return "No stage, adoption, or VoC movement exceeded the noise floor this window."
    return " ".join(lines)


def reporter_node(state: GraphState) -> GraphState:
    snapshot = state["snapshot"]
    journey_cfg = load_journey(state.get("journey", "pd_checkout"))
    maturing_stages = set(journey_cfg.get("maturing_stages", []))

    deltas = _stage_deltas(snapshot["stages"], snapshot["previous_stages"], maturing_stages)
    adoption = _adoption_deltas(snapshot["ct_events"])
    voc_deltas = _voc_theme_deltas(state["voc"].get("themes", []))

    trend_report = TrendReport(
        deltas=deltas,
        adoption=adoption,
        voc_theme_deltas=voc_deltas,
        narrative=_render_narrative(deltas, adoption, voc_deltas),
    )

    return {
        **state,
        "status": "drafting_prd",
        "trend_report": trend_report.model_dump(),
    }
