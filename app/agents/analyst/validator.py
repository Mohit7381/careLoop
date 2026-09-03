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
    for item in finding.evidence:
        if any(abs(item.value - k) <= _TOL * max(1.0, abs(k)) for k in known):
            return True, "ok"
        # rates: accept a value derivable as a ratio of two known numbers
        if 0 < item.value < 1:
            for a in known:
                for b in known:
                    if b and abs(a / b - item.value) < 0.0005:
                        return True, "ok"
    return False, "no evidence value matches any number in snapshot or drill-down trail"


def filter_findings(findings: list[Finding], snapshot: Snapshot,
                    trail: list[DrilldownStep],
                    shown: Optional[set[float]] = None) -> tuple[list[Finding], list[dict]]:
    kept, rejected = [], []
    for f in findings:
        ok, why = validate_finding(f, snapshot, trail, shown)
        (kept if ok else rejected).append(f if ok else {"finding": f.hypothesis[:80], "reason": why})
    return kept, rejected
