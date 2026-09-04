"""The evidence validator — CareLoop's quality gate.

A finding that cannot cite a number present in the snapshot or drill-down
trail is rejected before it reaches RunState. "Insufficient data" is a valid
finding; an uncited claim is not. Patterns are correlations, never causes —
`confirm_via` is therefore mandatory and must be non-trivial.
"""
from typing import Any, Optional

from app.schemas.contracts import DrilldownStep, Finding, Snapshot

_TOL = 1e-6


def collect_numbers(obj: Any) -> set[float]:
    """Every numeric leaf in an arbitrary dict/list — used so the validator
    accepts any number the model was actually SHOWN (phase-1 summary etc.),
    not only raw snapshot rows. Cluster totals like 111,993 are legitimate
    citations because the model received them."""
    out: set[float] = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= collect_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= collect_numbers(v)
    return out


def _row_rates(entered, converted) -> set[float]:
    """The rates one row legitimately implies: its own conversion, and the
    complementary loss share. Nothing across rows."""
    out: set[float] = set()
    try:
        e, c = float(entered), float(converted)
    except (TypeError, ValueError):
        return out
    if e > 0:
        out.add(round(c / e, 4))
        out.add(round(1 - c / e, 4))
    return out


def _known_rates(snapshot: Snapshot, trail: list[DrilldownStep]) -> set[float]:
    """Rates the model could have derived honestly.

    Replaces an any-pair ratio test that accepted a rate if ANY two known
    numbers divided to it. With ~40 known numbers that is ~1,400 pairs, and a
    finding citing 0.0073 for a cut the run never answered passed because
    1433 (an "ITEMS UNAVAILABLE" reason count) / 201617 (last week's confirmed
    count) happens to equal it. A ratio of two unrelated numbers is not
    evidence, so a rate now has to be the conversion (or loss share) of ONE
    row the model was actually shown, or an explicit rate/share field on it.
    """
    rates: set[float] = set()
    for row in list(snapshot.stages) + list(snapshot.previous_stages):
        rates |= _row_rates(row.entered, row.converted)
    for step in trail:
        for row in step.result_rows:
            if "entered" in row and "converted" in row:
                rates |= _row_rates(row.get("entered"), row.get("converted"))
            for key in ("rate", "share", "share_of_prev", "conversion_from_previous"):
                v = row.get(key)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    rates.add(round(float(v), 4))
    return rates


def _known_numbers(snapshot: Snapshot, trail: list[DrilldownStep]) -> set[float]:
    known: set[float] = set()
    for row in list(snapshot.stages) + list(snapshot.previous_stages):
        known.update((float(row.entered), float(row.converted)))
    for r in snapshot.reasons:
        known.add(float(r.count))
    for e in snapshot.ct_events:
        known.add(float(e.count))
    for step in trail:
        for row in step.result_rows:
            for v in row.values():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    known.add(float(v))
    return known


def _same_number(cited: float, known: float) -> bool:
    if abs(known) >= 1:                      # a count: exact after rounding
        return abs(cited - known) <= 0.5
    # A rate: known rates are rounded to 4 decimals, so the only legitimate
    # difference is that rounding. 0.0005 let a PHARMACY loss share (0.6452)
    # pass as CONSULTATION's 18:00 conversion (0.6447) — with ~50 cohort rates
    # in the same band, a coincidence inside a 0.0005 window is likely.
    return abs(cited - known) <= 0.0001


def validate_finding(finding: Finding, snapshot: Snapshot,
                     trail: list[DrilldownStep],
                     shown: Optional[set[float]] = None) -> tuple[bool, str]:
    """Returns (valid, reason). VoC findings cite review counts; warehouse
    findings must cite at least one number that exists in the provided data."""
    if not finding.confirm_via or len(finding.confirm_via.strip()) < 10:
        return False, "confirm_via missing or trivial — correlations must name their experiment"

    if finding.origin == "voc":
        if not finding.review_count or finding.review_count <= 0:
            return False, "voc finding without a positive review_count"
        return True, "ok"

    if not finding.evidence:
        return False, "warehouse finding with no evidence items"
    known = _known_numbers(snapshot, trail) | (shown or set())
    rates = _known_rates(snapshot, trail) | {round(x, 4) for x in (shown or set()) if 0 < x < 1}
    # EVERY evidence value must trace back, not just one. "Any one matches"
    # meant a finding half made of invented numbers passed on the strength of
    # its one real citation, and it is how a pharmacy finding survived on the
    # consultation journey: one of its two values happened to coincide.
    def _traces(value: float) -> bool:
        if any(_same_number(value, k) for k in known):
            return True
        # a rate must be the conversion of a row the model was shown — never a
        # coincidental ratio of two unrelated numbers (see _known_rates)
        return 0 < value < 1 and any(_same_number(value, r) for r in rates)

    untraced = [item.value for item in finding.evidence if not _traces(item.value)]
    if untraced:
        return False, f"evidence values not in the shown data: {untraced[:4]}"
    return True, "ok"


def filter_findings(findings: list[Finding], snapshot: Snapshot,
                    trail: list[DrilldownStep],
                    shown: Optional[set[float]] = None) -> tuple[list[Finding], list[dict]]:
    kept, rejected = [], []
    for f in findings:
        ok, why = validate_finding(f, snapshot, trail, shown)
        (kept if ok else rejected).append(f if ok else {"finding": f.hypothesis[:80], "reason": why})
    return kept, rejected
