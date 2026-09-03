"""The Analyst's ONLY data access in phase 2: a whitelisted, k-floored
aggregation over precomputed fixture slices (TCD Appendix A #7 — cohort cuts
live in fixture files, not in Snapshot). Never free-form SQL from the model.
"""
from typing import Any, Optional

from app.agents.analyst.phase1 import K_FLOOR


class AggregateTool:
    """cuts shape (from fixtures/<journey>/cohort_cuts.json):
    { dimension: { "rows": [ {segment, entered, converted?} ... ],
                   "distribution_only": bool } }
    distribution_only=True (e.g. pd_category — order_placed CT events carry
    null category) => rows have no converted counts; only shares are valid.
    """

    def __init__(self, cuts: dict[str, Any], whitelist: list[str], k: int = K_FLOOR):
        self.cuts = cuts
        self.whitelist = set(whitelist)
        self.k = k
        self.calls_made = 0

    @property
    def dimensions_with_data(self) -> list[str]:
        return sorted(set(self.cuts) & self.whitelist)

    def aggregate(self, stage: str, dimension: str,
                  compare_with_converted: bool = True) -> dict[str, Any]:
        self.calls_made += 1
        if dimension not in self.whitelist:
            return {"error": f"dimension '{dimension}' is not whitelisted",
                    "allowed": sorted(self.whitelist)}
        cut = self.cuts.get(dimension)
        if cut is None:
            return {"error": f"no cohort data for dimension '{dimension}'",
                    "no_data": True,
                    "dimensions_with_data": sorted(set(self.cuts) & self.whitelist),
                    "rows": []}
        rows = []
        for r in cut.get("rows", []):
            if r.get("entered", 0) < self.k:
                rows.append({"segment": r.get("segment"), "suppressed": True})
                continue
            out = {"segment": r.get("segment"), "entered": r.get("entered")}
            if compare_with_converted and not cut.get("distribution_only") and "converted" in r:
                out["converted"] = r["converted"]
                out["rate"] = round(r["converted"] / r["entered"], 4) if r["entered"] else None
            rows.append(out)
        return {"stage": stage, "dimension": dimension, "rows": rows,
                "distribution_only": bool(cut.get("distribution_only", False))}
