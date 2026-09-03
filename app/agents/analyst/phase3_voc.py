"""Analyst phase 3 — VoC corroboration + threshold escalation.

Single primary theme per review: the journey's lexicon is PRIORITY-ORDERED and
the first matching theme wins, so counts cannot double-trigger. Any theme with
MORE than `escalation_threshold` negative reviews in the window becomes a
VoC-originated Finding routed to Code Scout with the theme's pre-derived
search terms. Its evidence IS the review count — a countable fact; funnel
magnitudes stay warehouse-only (bias rule). Quotes carry rating+date, never
identity (PII scrubbed at ingest by the Fetcher).
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from app.schemas.contracts import Finding, Voc, VocQuote

NEGATIVE_MAX_SCORE = 2


def classify_review(text: str, themes: list[dict]) -> str:
    t = (text or "").lower()
    for theme in themes:  # priority order — first match wins
        if any(kw.lower() in t for kw in theme["keywords"]):
            return theme["name"]
    return "unmapped"


def filter_by_days(reviews: list[dict], days: Optional[int]) -> tuple[list[dict], dict]:
    """Keep reviews from the last `days`, measured from the newest review present.

    Anchored to the corpus, not to wall-clock now(): the fixture is a frozen
    capture, and anchoring to today would silently return nothing the moment it
    ages past the window. Returns the real span alongside, so a report can state
    what it actually looked at rather than what was asked for.
    """
    if not days:
        return reviews, {}
    dated = [(str(r.get("at") or "")[:10], r) for r in reviews]
    dated = [(d, r) for d, r in dated if len(d) == 10]
    if not dated:
        return reviews, {"review_window_days": days, "note": "no dated reviews; window ignored"}
    newest = max(d for d, _ in dated)
    y, m, dd = (int(x) for x in newest.split("-"))
    cutoff = date(y, m, dd) - timedelta(days=days - 1)
    kept = [r for d, r in dated if date(*(int(x) for x in d.split("-"))) >= cutoff]
    return kept, {"review_window_days": days, "review_window_from": cutoff.isoformat(),
                  "review_window_to": newest, "reviews_in_window": len(kept),
                  "reviews_available": len(reviews)}


def run_voc(reviews: list[dict], journey_voc_cfg: dict, next_rank: int,
            themes_per_review: Optional[list[str]] = None,
            extra_meta: Optional[dict] = None) -> tuple[list[Finding], Voc]:
    themes_cfg = journey_voc_cfg["themes"]
    threshold = int(journey_voc_cfg.get("escalation_threshold", 20))
    by_theme_cfg = {t["name"]: t for t in themes_cfg}

    # themes_per_review lets the caller supply semantic classifications (one per
    # review, same order); without it we fall back to the keyword lexicon.
    assigned = list(themes_per_review) if themes_per_review else None
    negatives, neg_themes = [], []
    for i, r in enumerate(reviews):
        if r.get("score", 5) > NEGATIVE_MAX_SCORE:
            continue
        negatives.append(r)
        neg_themes.append(assigned[i] if assigned and i < len(assigned)
                          else classify_review(r.get("text", ""), themes_cfg))

    buckets: dict[str, list[dict]] = defaultdict(list)
    for r, theme in zip(negatives, neg_themes):
        buckets[theme if theme in by_theme_cfg or theme == "unmapped" else "unmapped"].append(r)

    voc = Voc(
        reviews_meta={"total": len(reviews), "negatives": len(negatives),
                      "threshold": threshold, **(extra_meta or {})},
        themes=[{"theme": name, "count": len(items),
                 "escalated": name != "unmapped" and len(items) > threshold}
                for name, items in sorted(buckets.items(), key=lambda kv: -len(kv[1]))],
    )

    findings: list[Finding] = []
    rank = next_rank
    for name, items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if name == "unmapped" or len(items) <= threshold:
            continue
        cfg = by_theme_cfg[name]
        top = sorted(items, key=lambda r: -r.get("thumbs", 0))[:3]
        quotes = [f"[{q.get('score')}★ {str(q.get('at',''))[:10]}] {q.get('text','')[:180]}"
                  for q in top]
        findings.append(Finding(
            rank=rank, origin="voc", stage=cfg["routing_stage"],
            hypothesis=(f"{len(items)} of {len(negatives)} negative Play Store reviews in the "
                        f"window share the theme '{name}' — users repeatedly report this problem"),
            confidence="high" if len(items) >= 2 * threshold else "medium",
            confirm_via=("Correlate the reviews' dates/app versions with the matching funnel "
                         "segment; then A/B the proposed fix and watch the theme count fall"),
            theme=name,
            theme_search_terms=list(cfg.get("search_terms", [])),
            review_count=len(items),
            top_quotes=quotes,
        ))
        voc.per_finding_quotes[str(rank)] = [
            VocQuote(rating=q.get("score", 1), date=str(q.get("at", ""))[:10],
                     text=q.get("text", "")[:300], theme=name) for q in top]
        rank += 1
    return findings, voc


CORROBORATION_FLOOR = 5  # fewer matching reviews than this is noise, not corroboration


def corroborate(warehouse_findings: list[Finding], voc: Voc,
                journey_voc_cfg: dict) -> None:
    """Attach VoC corroboration to warehouse findings whose routing stage has a
    matching theme cluster. Several themes can share one routing stage — pick
    the LARGEST cluster, and only attach when it clears the floor (a 3-review
    cluster corroborates nothing). Mutates findings in place."""
    counts = {t["theme"]: t["count"] for t in voc.themes}
    best_by_stage: dict[str, tuple[str, int]] = {}
    for theme in journey_voc_cfg["themes"]:
        n = counts.get(theme["name"], 0)
        stage = theme["routing_stage"]
        if n >= CORROBORATION_FLOOR and n > best_by_stage.get(stage, ("", 0))[1]:
            best_by_stage[stage] = (theme["name"], n)
    for f in warehouse_findings:
        hit = best_by_stage.get(f.stage)
        if hit and not f.theme:
            f.theme, f.review_count = hit
